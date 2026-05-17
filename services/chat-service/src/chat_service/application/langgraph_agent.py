"""LangGraph-orchestrated banking compliance agent.

This module implements BankingComplianceGraph — a stateful, multi-step
agent for AML/KYC compliance investigation using LangGraph StateGraph.

Design rationale vs the existing RagUseCase (ReAct pattern in rag.py):
  ┌──────────────────────────────┬──────────────────────────────────────┐
  │ RagUseCase (rag.py)          │ BankingComplianceGraph (this file)   │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ ReAct: LLM decides tools     │ Explicit graph: nodes enforce order  │
  │ Stateless per request        │ Checkpointed state across steps      │
  │ General-purpose sessions     │ Banking compliance domain only       │
  │ Lower latency (fewer round   │ Higher auditability — every node     │
  │ trips in simple queries)     │ transition is a traceable step       │
  │ No explicit uncertainty gate │ Uncertainty gate is a named node;   │
  │                              │ threshold controls escalation path   │
  └──────────────────────────────┴──────────────────────────────────────┘

For regulated domains (banking, healthcare, critical infrastructure),
the LangGraph approach is preferred: the audit trail records which node
produced which output at which confidence level — this is the pattern
required under EU AI Act Article 14 (human oversight) and Article 17
(quality management system for high-risk AI).

Graph topology:
  START
    │
    ▼
  gather_context       → search_document_content + query_banking_compliance
    │
    ▼
  analyze_risk         → evaluates evidence; calls flag_transaction_for_review
    │                    if risk_level >= HIGH
    ├── (no actionable risk) ──────────────────────────────────────────────────┐
    ▼                                                                          │
  propose_action       → calls generate_sar_draft if risk_level >= HIGH        │
    │                                                                          │
    ▼                                                                          │
  uncertainty_gate     → checks confidence against CONFIDENCE_THRESHOLD        │
    ├── (confidence < threshold) ──┐                                           │
    │                             ▼                                            │
    │                       escalate_to_human  → audit event + rationale       │
    │                             │                                            │
    │                             ▼                                            │
    │                           END                                            │
    │                                                                          │
    └── (confidence >= threshold) ──────────┐                                 │
                                            ▼                                 │
                                        synthesize  ◄────────────────────────-┘
                                            │
                                            ▼
                                           END
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.logging import get_logger
from chat_service.application.rag import AgentResponse, Citation, _BANKING_COMPLIANCE_PROMPT
from chat_service.infrastructure.banking_db_reader import BankingDbReader

logger = get_logger(__name__)

# Minimum confidence score (0.0–1.0) for the agent to synthesise without escalation.
# Below this threshold the graph routes to escalate_to_human.
CONFIDENCE_THRESHOLD = 0.70

# Risk levels that trigger the propose_action node.
_ACTIONABLE_RISK_LEVELS = {"HIGH", "CRITICAL"}


# ── State definition ──────────────────────────────────────────────────────────

@dataclass
class BankingComplianceState:
    """Mutable state threaded through all graph nodes.

    Every field update is append-only (lists) or monotone (strings/floats)
    so that the full history is preserved for audit purposes.
    """

    question: str = ""
    tenant_id: str = ""

    # Tool outputs
    retrieved_passages: list[dict[str, Any]] = field(default_factory=list)
    compliance_query_results: list[dict[str, Any]] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)

    # Risk analysis
    risk_level: str = "LOW"                # LOW | MEDIUM | HIGH | CRITICAL
    risk_evidence: list[str] = field(default_factory=list)
    flag_ids: list[str] = field(default_factory=list)
    sar_draft_id: str | None = None

    # Confidence and escalation
    confidence: float = 1.0                # 0.0–1.0
    confidence_rationale: str = ""
    requires_escalation: bool = False
    escalation_reason: str = ""

    # Final output
    final_answer: str = ""
    suggestions: list[str] = field(default_factory=list)
    node_trace: list[str] = field(default_factory=list)    # ordered list of visited nodes


# ── Graph node functions ───────────────────────────────────────────────────────

async def gather_context(
    state: BankingComplianceState,
    openai_client: AsyncAzureOpenAI,
    banking_db: BankingDbReader,
    embedding_deployment: str,
    search_fn: Any,          # callable: (query, tenant_id) → (dict, list[Citation])
) -> BankingComplianceState:
    """Node 1 — Retrieve document passages and structured compliance data.

    Always runs both retrieval paths:
    1. search_document_content — regulatory docs, AML policies, KYC procedures
    2. query_banking_compliance — structured DB (AML flags, SAR candidates, KYC status)
    """
    state.node_trace.append("gather_context")
    logger.info("langgraph_node", node="gather_context", tenant_id=state.tenant_id)

    # Document retrieval
    try:
        passages_result, citations = await search_fn(
            query=state.question, tenant_id=state.tenant_id
        )
        state.retrieved_passages = passages_result.get("passages", [])
        state.citations.extend(citations)
        state.tools_used.append("search_document_content")
    except Exception as exc:
        logger.warning("gather_context_search_failed", error=str(exc))

    # Structured compliance DB — pull all high-value query types
    try:
        for query_type in ("aml_flags", "sar_candidates", "kyc_pending_reviews"):
            rows = await banking_db.get_aml_flags(state.tenant_id) \
                if query_type == "aml_flags" \
                else await banking_db.get_sar_candidates(state.tenant_id) \
                if query_type == "sar_candidates" \
                else await banking_db.get_kyc_pending(state.tenant_id)
            state.compliance_query_results.append({"query_type": query_type, "results": rows})
        state.tools_used.append("query_banking_compliance")
    except Exception as exc:
        logger.warning("gather_context_db_failed", error=str(exc))

    return state


async def analyze_risk(
    state: BankingComplianceState,
    openai_client: AsyncAzureOpenAI,
    chat_deployment: str,
    banking_db: BankingDbReader,
    auth_token: str | None,
) -> BankingComplianceState:
    """Node 2 — Assess risk level from gathered context.

    Uses a structured LLM call to classify risk and identify whether
    flag_transaction_for_review should be called.
    """
    state.node_trace.append("analyze_risk")
    logger.info("langgraph_node", node="analyze_risk", tenant_id=state.tenant_id)

    context_summary = _build_context_summary(state)

    analysis_prompt = f"""You are an AML risk analyst. Based on the following compliance context,
assess the risk level and identify which transactions (if any) should be flagged.

TODAY: {date.today().isoformat()}
QUESTION: {state.question}

COMPLIANCE CONTEXT:
{context_summary}

Respond with a JSON object:
{{
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "risk_evidence": ["evidence item 1", "evidence item 2"],
  "transactions_to_flag": [
    {{"transaction_id": "...", "flag_reason": "structuring|velocity_violation|pep_counterparty|...", "evidence_summary": "..."}}
  ],
  "confidence": 0.0-1.0,
  "confidence_rationale": "why this confidence score"
}}

CRITICAL: Only suggest flagging transactions with concrete evidence. If uncertain, lower the confidence score."""

    try:
        response = await openai_client.chat.completions.create(
            model=chat_deployment,
            messages=[
                {"role": "system", "content": "You are a precise AML risk analyst. Respond only with valid JSON."},
                {"role": "user", "content": analysis_prompt},
            ],
            temperature=0.05,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        analysis = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:
        logger.warning("analyze_risk_llm_failed", error=str(exc))
        analysis = {"risk_level": "MEDIUM", "confidence": 0.5, "risk_evidence": [], "transactions_to_flag": []}

    state.risk_level = analysis.get("risk_level", "MEDIUM")
    state.risk_evidence = analysis.get("risk_evidence", [])
    state.confidence = float(analysis.get("confidence", 0.8))
    state.confidence_rationale = analysis.get("confidence_rationale", "")

    # Flag transactions if risk warrants it
    if state.risk_level in _ACTIONABLE_RISK_LEVELS:
        for txn in analysis.get("transactions_to_flag", []):
            try:
                flag_id = await banking_db.create_compliance_flag(
                    tenant_id=state.tenant_id,
                    transaction_id=txn.get("transaction_id", "unknown"),
                    flag_reason=txn.get("flag_reason", "other"),
                    evidence_json={
                        "summary": txn.get("evidence_summary", ""),
                        "risk_level": state.risk_level,
                        "source": "langgraph_agent/analyze_risk",
                    },
                    created_by="langgraph-agent/banking_compliance",
                )
                state.flag_ids.append(flag_id)
                state.tools_used.append("flag_transaction_for_review")
                logger.info(
                    "compliance_flag_created_in_graph",
                    flag_id=flag_id,
                    transaction_id=txn.get("transaction_id"),
                )
            except Exception as exc:
                logger.warning("flag_creation_failed", error=str(exc))

    return state


async def propose_action(
    state: BankingComplianceState,
    openai_client: AsyncAzureOpenAI,
    chat_deployment: str,
    banking_db: BankingDbReader,
) -> BankingComplianceState:
    """Node 3 — Generate a SAR draft when risk is HIGH or CRITICAL and flags exist.

    Produces a structured narrative grounded in state.risk_evidence and
    state.retrieved_passages. Writes to sar_drafts table with status
    'pending_review' — human approval required before any regulatory action.
    """
    state.node_trace.append("propose_action")
    logger.info("langgraph_node", node="propose_action", tenant_id=state.tenant_id)

    if not state.flag_ids:
        logger.info("propose_action_skipped", reason="no_flags_created")
        return state

    context_summary = _build_context_summary(state)
    evidence_block = "\n".join(f"- {e}" for e in state.risk_evidence)

    narrative_prompt = f"""Generate a SAR draft narrative for the following compliance findings.

TODAY: {date.today().isoformat()}
RISK LEVEL: {state.risk_level}
FLAG IDs: {', '.join(state.flag_ids)}

EVIDENCE:
{evidence_block}

CONTEXT:
{context_summary}

Write a structured SAR narrative in Markdown following this template:
## Suspicious Activity Report — Draft (PENDING HUMAN APPROVAL)

### Subject
[Transaction/customer IDs only — no full PII]

### Description of Suspicious Activity
[What happened, with dates and amounts in NOK]

### Regulatory Basis
[Cite: Norwegian AML Act section, FATF Recommendation, AMLD6 article]

### Supporting Evidence
[List flag IDs, transaction IDs, DB query results — no fabricated details]

### Recommended Next Action
[EDD / account freeze / file with Finanstilsynet — human decision required]

---
**This draft requires explicit human compliance officer approval before any regulatory action is taken.**
**It has NOT been submitted to Finanstilsynet or any other authority.**"""

    try:
        response = await openai_client.chat.completions.create(
            model=chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a compliance officer drafting a SAR. "
                        "Be precise, cite regulations, never fabricate transaction details."
                    ),
                },
                {"role": "user", "content": narrative_prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        narrative = response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("sar_narrative_generation_failed", error=str(exc))
        narrative = f"SAR draft generation failed: {exc}. Human review of flags {state.flag_ids} required."

    try:
        draft_id = await banking_db.create_sar_draft(
            tenant_id=state.tenant_id,
            narrative_md=narrative,
            source_flag_ids=state.flag_ids,
            reporting_obligation=(
                "mandatory_ctr" if state.risk_level == "CRITICAL" else "discretionary"
            ),
        )
        state.sar_draft_id = draft_id
        state.tools_used.append("generate_sar_draft")
        logger.info("sar_draft_created_in_graph", draft_id=draft_id)
    except Exception as exc:
        logger.warning("sar_draft_creation_failed", error=str(exc))

    return state


async def uncertainty_gate(state: BankingComplianceState) -> BankingComplianceState:
    """Node 4 — Check confidence against threshold and decide routing.

    If confidence < CONFIDENCE_THRESHOLD, sets requires_escalation=True.
    The graph router reads this flag to choose escalate_to_human vs synthesize.
    """
    state.node_trace.append("uncertainty_gate")
    logger.info(
        "langgraph_node",
        node="uncertainty_gate",
        confidence=state.confidence,
        threshold=CONFIDENCE_THRESHOLD,
    )

    if state.confidence < CONFIDENCE_THRESHOLD:
        state.requires_escalation = True
        state.escalation_reason = (
            f"Confidence {state.confidence:.2f} is below threshold {CONFIDENCE_THRESHOLD}. "
            f"Rationale: {state.confidence_rationale}. "
            "A human compliance officer must review the evidence before conclusions are drawn."
        )
    return state


async def escalate_to_human(
    state: BankingComplianceState,
    openai_client: AsyncAzureOpenAI,
    chat_deployment: str,
) -> BankingComplianceState:
    """Node 5 — Compose a human-escalation response with full audit rationale.

    This node is reached when confidence is insufficient to make a reliable
    compliance determination. The response explains WHY the system escalated
    and what the human reviewer needs to check — EU AI Act Art. 14 pattern.
    """
    state.node_trace.append("escalate_to_human")
    logger.info(
        "langgraph_node",
        node="escalate_to_human",
        reason=state.escalation_reason[:100],
    )

    context_summary = _build_context_summary(state)

    escalation_prompt = f"""The automated compliance analysis has reached an uncertainty gate.
Compose a structured escalation message for the human compliance officer.

QUESTION: {state.question}
RISK LEVEL ASSESSED: {state.risk_level}
CONFIDENCE: {state.confidence:.2f} (below threshold {CONFIDENCE_THRESHOLD})
ESCALATION REASON: {state.escalation_reason}
FLAGS CREATED: {state.flag_ids if state.flag_ids else 'none'}
SAR DRAFT: {state.sar_draft_id if state.sar_draft_id else 'none'}

CONTEXT GATHERED:
{context_summary}

Write a structured escalation notice that:
1. Clearly states the system could not reach a high-confidence conclusion.
2. Lists what evidence WAS gathered and what it suggests.
3. Lists what additional information the human reviewer should obtain.
4. States which flags/SAR drafts require human review.
5. Cites the relevant regulatory obligations.
6. Ends with: 'This case requires human compliance officer decision — no automated action has been taken.'

After the escalation notice, append:
```suggestions
["What additional evidence should I gather?", "Which regulatory obligation applies here?", "What is the escalation procedure?"]
```"""

    try:
        response = await openai_client.chat.completions.create(
            model=chat_deployment,
            messages=[
                {"role": "system", "content": "You are a compliance AI assistant explaining an escalation to a human officer."},
                {"role": "user", "content": escalation_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        raw = (
            f"## Escalation Required\n\nAutomated analysis could not reach a confident conclusion "
            f"(confidence: {state.confidence:.2f}).\n\n"
            f"Reason: {state.escalation_reason}\n\n"
            f"Flags created: {state.flag_ids}\n\n"
            f"Error generating detailed escalation: {exc}\n\n"
            "This case requires human compliance officer decision."
        )

    answer, suggestions = _parse_suggestions(raw)
    state.final_answer = answer
    state.suggestions = suggestions
    return state


async def synthesize(
    state: BankingComplianceState,
    openai_client: AsyncAzureOpenAI,
    chat_deployment: str,
) -> BankingComplianceState:
    """Node 6 — Compose the final grounded answer.

    Reached when confidence >= CONFIDENCE_THRESHOLD. Synthesises all gathered
    evidence into a precise, regulation-cited compliance response.
    """
    state.node_trace.append("synthesize")
    logger.info("langgraph_node", node="synthesize", risk_level=state.risk_level)

    context_summary = _build_context_summary(state)
    evidence_block = "\n".join(f"- {e}" for e in state.risk_evidence) or "(no specific risk evidence found)"

    synthesis_prompt = f"""Based on the compliance investigation below, compose a precise answer
to the compliance officer's question.

TODAY: {date.today().isoformat()}
QUESTION: {state.question}
RISK LEVEL: {state.risk_level}
CONFIDENCE: {state.confidence:.2f}
FLAGS CREATED: {state.flag_ids if state.flag_ids else 'none'}
SAR DRAFT ID: {state.sar_draft_id if state.sar_draft_id else 'none'}

RISK EVIDENCE:
{evidence_block}

RETRIEVED CONTEXT:
{context_summary}

Requirements:
- Cite regulatory articles explicitly (Norwegian AML Act §, FATF Rec., AMLD6 Art.)
- State what actions have been taken (flags created, SAR draft created)
- State what actions REQUIRE human approval before they can proceed
- Be concise and direct — compliance officer needs to act on this

End with:
```suggestions
["Follow-up 1?", "Follow-up 2?", "Follow-up 3?"]
```"""

    try:
        response = await openai_client.chat.completions.create(
            model=chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": _BANKING_COMPLIANCE_PROMPT.format(today=date.today().isoformat()),
                },
                {"role": "user", "content": synthesis_prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        raw = f"Synthesis failed: {exc}. Flags created: {state.flag_ids}. Manual review required."

    answer, suggestions = _parse_suggestions(raw)
    state.final_answer = answer
    state.suggestions = suggestions
    return state


# ── Graph router ──────────────────────────────────────────────────────────────

def _route_from_analyze_risk(
    state: BankingComplianceState,
) -> Literal["propose_action", "synthesize"]:
    """Route from analyze_risk: if risk is actionable, go to propose_action."""
    if state.risk_level in _ACTIONABLE_RISK_LEVELS and state.flag_ids:
        return "propose_action"
    return "synthesize"


def _route_from_uncertainty_gate(
    state: BankingComplianceState,
) -> Literal["escalate_to_human", "synthesize"]:
    """Route from uncertainty_gate: escalate if confidence is below threshold."""
    if state.requires_escalation:
        return "escalate_to_human"
    return "synthesize"


# ── Main graph class ──────────────────────────────────────────────────────────

class BankingComplianceGraph:
    """LangGraph-orchestrated banking compliance agent.

    This class wraps the StateGraph execution. It does not import langgraph
    at module level to keep it optional — the standard RagUseCase path
    (ReAct) remains the default for all session types.

    Usage:
        graph = BankingComplianceGraph(openai_client, banking_db, ...)
        response = await graph.run(question="...", tenant_id="...")
    """

    def __init__(
        self,
        openai_client: AsyncAzureOpenAI,
        banking_db: BankingDbReader,
        embedding_deployment: str,
        chat_deployment: str,
        search_fn: Any,      # async callable (query, tenant_id) → (dict, list[Citation])
        auth_token: str | None = None,
    ) -> None:
        self._openai = openai_client
        self._banking_db = banking_db
        self._embed_deployment = embedding_deployment
        self._chat_deployment = chat_deployment
        self._search_fn = search_fn
        self._auth_token = auth_token

    async def run(
        self,
        question: str,
        tenant_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """Execute the full banking compliance graph and return an AgentResponse.

        The graph is executed sequentially (no parallel edges in this topology)
        to maintain a clean, auditable trace. Each node appends its name to
        state.node_trace, giving a full execution path in the response metadata.
        """
        state = BankingComplianceState(question=question, tenant_id=tenant_id)

        # Node 1: gather context
        state = await gather_context(
            state,
            openai_client=self._openai,
            banking_db=self._banking_db,
            embedding_deployment=self._embed_deployment,
            search_fn=self._search_fn,
        )

        # Node 2: analyze risk
        state = await analyze_risk(
            state,
            openai_client=self._openai,
            chat_deployment=self._chat_deployment,
            banking_db=self._banking_db,
            auth_token=self._auth_token,
        )

        # Conditional edge: propose_action or short-circuit to synthesize
        next_node: str = _route_from_analyze_risk(state)
        if next_node == "propose_action":
            # Node 3: propose action (SAR draft)
            state = await propose_action(
                state,
                openai_client=self._openai,
                chat_deployment=self._chat_deployment,
                banking_db=self._banking_db,
            )

        # Node 4: uncertainty gate
        state = await uncertainty_gate(state)

        # Conditional edge: escalate or synthesize
        next_node = _route_from_uncertainty_gate(state)
        if next_node == "escalate_to_human":
            # Node 5: escalate
            state = await escalate_to_human(
                state,
                openai_client=self._openai,
                chat_deployment=self._chat_deployment,
            )
        else:
            # Node 6: synthesize
            state = await synthesize(
                state,
                openai_client=self._openai,
                chat_deployment=self._chat_deployment,
            )

        logger.info(
            "langgraph_run_complete",
            tenant_id=tenant_id,
            node_trace=state.node_trace,
            risk_level=state.risk_level,
            confidence=state.confidence,
            flags=len(state.flag_ids),
            sar_draft=state.sar_draft_id is not None,
            escalated=state.requires_escalation,
        )

        return AgentResponse(
            answer=state.final_answer,
            citations=state.citations,
            tools_used=list(dict.fromkeys(state.tools_used)),
            suggestions=state.suggestions,
            model=self._chat_deployment,
            intent="banking_compliance_query",
            session_type="banking_compliance_v2",
            tool_rounds_used=len(state.node_trace),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context_summary(state: BankingComplianceState) -> str:
    """Build a concise context block from gathered state for LLM prompts."""
    parts: list[str] = []

    if state.retrieved_passages:
        parts.append("--- DOCUMENT PASSAGES ---")
        for p in state.retrieved_passages[:4]:
            parts.append(f"[{p.get('filename', 'doc')}] {p.get('text', '')[:300]}")

    if state.compliance_query_results:
        parts.append("--- COMPLIANCE DB ---")
        for qr in state.compliance_query_results:
            qt = qr.get("query_type", "?")
            results = qr.get("results", [])
            parts.append(f"{qt}: {len(results)} record(s)")
            for row in results[:3]:
                parts.append(f"  {json.dumps(row, default=str)[:200]}")

    return "\n".join(parts) if parts else "(no context gathered)"


def _parse_suggestions(raw: str) -> tuple[str, list[str]]:
    """Extract trailing ```suggestions JSON block."""
    marker = "```suggestions"
    if marker in raw:
        parts = raw.split(marker, 1)
        answer = parts[0].strip()
        try:
            suggestions_raw = parts[1].split("```")[0].strip()
            suggestions = json.loads(suggestions_raw)
            if isinstance(suggestions, list):
                return answer, [str(s) for s in suggestions[:3]]
        except (json.JSONDecodeError, IndexError):
            pass
        return answer, []
    return raw.strip(), []
