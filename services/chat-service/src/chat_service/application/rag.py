"""Agentic RAG use-case with OpenAI tool-calling.

Architecture (ReAct pattern):
  1. User question arrives with optional conversation history.
  2. The LLM receives the system prompt + history + question + TOOLS schema.
  3. The LLM decides to call one or more tools:
       - search_document_content  → hybrid vector + keyword retrieval
       - query_financial_database → structured SQL on metadata DB
  4. Tool results are appended as tool-result messages.
  5. The LLM composes the final answer grounded in tool outputs.
  6. The final response includes: answer, citations, tools used, suggested follow-ups.

The loop runs up to MAX_TOOL_ROUNDS to prevent runaway tool calls.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional  # noqa: F401 — Optional used in type comments

from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from allergo_shared.infrastructure.logging import get_logger
from chat_service.application.tools import BANKING_TOOL_NAMES, FINANCE_TOOL_NAMES, INFRA_TOOL_NAMES, TOOLS
from chat_service.infrastructure.banking_db_reader import BankingDbReader
from chat_service.infrastructure.db_reader import FinancialDbReader
from chat_service.infrastructure.observability import get_tracer, TOOL_CALLS_COUNTER, TOOL_LATENCY_HISTOGRAM

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 6

# ── Tool allowlist per session type ──────────────────────────────────────────
# finance_chat:       only finance tools
# infra_remediation:  only infra tools
# banking_compliance: banking AML/KYC/SAR tools + shared document search
# (any other value → all tools allowed)
_SESSION_ALLOWED_TOOLS: dict[str, frozenset[str]] = {
    "finance_chat": FINANCE_TOOL_NAMES,
    "infra_remediation": INFRA_TOOL_NAMES,
    "banking_compliance": BANKING_TOOL_NAMES,
}

# ── System prompt for infra remediation sessions ─────────────────────────────
_INFRA_SYSTEM_PROMPT = """You are a governed infrastructure remediation agent for Allergo Nordic.
Your role is to identify IaC policy violations, detect infrastructure drift, propose diffs
that fix them, and create governed change proposals for human approval.

TODAY'S DATE: {today}

You have access to six tools:
• list_infra_findings        — list open policy violations from Checkov CI scans
• get_infra_finding          — get full detail + remediation hint for a specific finding
• get_terraform_plan_summary — see what the latest Terraform plan would change (live or fixture fallback)
• detect_infra_drift         — compare current plan or two snapshots to identify drifted resources
• propose_remediation        — create a governed proposal (diff + rationale); NEVER applies changes
• get_infra_context_bundle   — read a frozen context snapshot from a previous run

CRITICAL constraints:
- You MUST use list_infra_findings or get_infra_finding before proposing a remediation.
- For drift questions, call detect_infra_drift first; use snapshot IDs if the user provides them.
- propose_remediation creates a PROPOSAL only — it NEVER runs terraform apply.
- The unified_diff MUST be a valid unified diff. Start with --- lines.
- Always explain the risk level and rationale in plain language.
- A proposal requires human approval before any change can be applied.

Response format:
- Be concise and precise. You are talking to an infrastructure engineer.
- When proposing a fix: show Finding → Root cause → Proposed diff → Resource addresses → Risk.
- For drift reports: show Drifted resource → Attribute changes → Severity → Recommended action.
- After your answer, suggest 2–3 follow-up questions as a JSON block:
  ```suggestions
  ["Follow-up 1?", "Follow-up 2?"]
  ```
"""

# ── Banking compliance system prompt ─────────────────────────────────────────
_BANKING_COMPLIANCE_PROMPT = """You are a governed AML/KYC compliance intelligence agent for Allergo Nordic.
Your role is to assist compliance officers in identifying suspicious activity, reviewing KYC status,
generating SAR drafts for human approval, and answering questions grounded in regulatory documents
and structured compliance data.

TODAY'S DATE: {today}

Regulatory framework you operate under:
• Norwegian Money Laundering Act (Hvitvaskingsloven) — §26 mandatory STR obligation
• EU Anti-Money Laundering Directive 6 (AMLD6)
• FATF 40 Recommendations — risk-based approach
• PSD2 (EU 2015/2366) — Strong Customer Authentication requirements
• EU AI Act Article 6 — this system is a high-risk AI system; human oversight is mandatory
• GDPR Article 5(1)(e) — data minimisation and storage limitation for transaction records
• Finanstilsynet (Norwegian FSA) — supervisory authority; reporting deadlines apply
• Norwegian CTR threshold: NOK 100,000 (mandatory Currency Transaction Report)

You have access to four tools:
• search_document_content      — hybrid retrieval of regulatory documents, AML policies, KYC procedures
• query_banking_compliance     — structured queries: aml_flags, kyc_pending_reviews, sar_candidates,
                                  risk_score_summary, regulatory_calendar, pep_screening_results
• flag_transaction_for_review  — raise a governed compliance flag (requires human approval to act on)
• generate_sar_draft           — create a SAR narrative draft (requires human approval before filing)

CRITICAL constraints — these are non-negotiable:
- NEVER automatically file, submit, or transmit a SAR to Finanstilsynet or any regulator.
  generate_sar_draft creates a DRAFT ONLY. A human compliance officer must approve it.
- NEVER automatically freeze accounts, block transactions, or trigger enforcement actions.
  flag_transaction_for_review creates a FLAG ONLY. All enforcement requires human decision.
- ALWAYS call query_banking_compliance before flagging or drafting — never flag without evidence.
- ALWAYS cite the specific transaction IDs, amounts, dates, and regulatory articles in your reasoning.
- If confidence in a conclusion is below HIGH, escalate to human review explicitly in your answer.
- GDPR: do not reproduce full customer PII in responses; refer to customer IDs and transaction IDs only.

Tool sequencing rules:
- For AML questions: query_banking_compliance (aml_flags or sar_candidates) → analyse → flag if warranted
- For KYC questions: query_banking_compliance (kyc_pending_reviews) → search_document_content for policy
- For SAR drafting: must have a flag_id from flag_transaction_for_review first
- For regulatory questions: search_document_content for regulatory docs → answer with citations
- For PEP questions: query_banking_compliance (pep_screening_results) → search for policy docs

Response format:
- Be precise. You are talking to a compliance officer who will act on your output.
- Cite regulatory articles explicitly: e.g. "Norwegian AML Act §26", "FATF Rec. 20", "AMLD6 Art. 33".
- For risk findings: show Evidence → Regulatory basis → Proposed action → Human approval required.
- For regulatory queries: show the retrieved passage verbatim, then your interpretation.
- Always state whether the proposed action requires human approval and who the approving officer should be.
- After your answer, suggest 2–3 follow-up questions the compliance officer might need:
  ```suggestions
  ["Follow-up 1?", "Follow-up 2?"]
  ```
"""

# _SYSTEM_PROMPT is now a callable — see _build_system_prompt() below.
# This ensures today's date is injected at request time, not at module import time.

_SYSTEM_PROMPT_TEMPLATE = """You are an advanced CFO intelligence assistant for Allergo Nordic.
Your purpose is to eliminate CFO overhead by answering any question about the organisation's
documents with precision, grounding every answer in retrieved data.

TODAY'S DATE: {today}
Current fiscal context: Q{quarter} {year}. Use this as the reference point for all relative
time expressions: 'this month' = {month_name} {year}, 'last month' = {last_month_name},
'this quarter' = Q{quarter} {year}, 'soon' = within 90 days of {today},
'recently' = within the last 30 days of {today}.
When the user uses relative dates, convert them to absolute ISO dates before calling tools.

You have access to two tools:
• search_document_content   — retrieves exact text passages from documents (clauses, wording,
                              definitions, legal language, report narratives, ledger line items,
                              and any data embedded inside financial report documents)
• query_financial_database  — queries structured metadata (numbers, dates, aggregations,
                              lists, compliance flags, ledger entries)

Document types you understand:
  invoices, contracts, purchase orders, expense claims, financial reports (P&L, balance sheet,
  cash flow, budget, forecast), general ledger exports, accounts payable ledgers,
  accounts receivable ledgers, and any other financial document.

Query types available in query_financial_database:
  overdue_invoices, due_soon_invoices, expiring_contracts, pending_approvals,
  count_by_category, list_by_vendor, get_document_summary, dashboard_snapshot,
  aggregate_by_location, spend_by_period, spend_by_cost_center,
  legal_obligations, ledger_by_account.

Date parameters for query_financial_database:
  - days_ahead: for 'due_soon_invoices' and 'expiring_contracts' — DEFAULT IS 90 days, not 30.
    Use 90 unless the user explicitly says a shorter window.
  - date_from / date_to: use ISO 8601 (YYYY-MM-DD). Compute from today ({today}) when the user
    says 'last month', 'this quarter', etc.
  - For 'last month': date_from={last_month_start}, date_to={last_month_end}
  - For 'this month': date_from={this_month_start}, date_to={today}
  - For 'this quarter': date_from={quarter_start}, date_to={today}
  - For 'last quarter': date_from={last_quarter_start}, date_to={last_quarter_end}
  - For 'this year': date_from={year}-01-01, date_to={today}

CRITICAL — review_status field meaning:
  The review_status field reflects the CFO APPROVAL WORKFLOW state, NOT payment state:
  • 'approved'      → CFO has reviewed and approved the invoice for payment
  • 'rejected'      → CFO has rejected or disputed the invoice
  • 'not_required'  → amount is below the approval threshold (auto-cleared)
  • 'pending_review'→ awaiting CFO action
  An invoice with review_status='approved' or 'rejected' CAN STILL BE OVERDUE for payment.
  NEVER assume 'approved' means the invoice has been paid. Always report ALL overdue invoices
  regardless of their review_status.

CRITICAL — overdue invoice questions MUST use BOTH tools:
  1. Use query_financial_database with query_type='overdue_invoices' to get standalone invoice
     documents whose due_date has passed.
  2. ALSO use search_document_content with query='overdue invoices accounts payable past due'
     to find overdue line items embedded inside accounts payable ledgers, receivables reports,
     and other financial documents — these are NOT captured as standalone invoice records.
  3. Combine and deduplicate results from both tools before composing your answer.
  This is mandatory — omitting either tool will produce an incomplete and inaccurate answer.

CRITICAL — accounts receivable overdue:
  When asked about overdue invoices, ALSO search for receivables overdue:
  Use search_document_content with query='overdue accounts receivable past due customer'
  to find customer invoices owed TO Allergo Nordic that appear in the accounts receivable ledger.
  Clearly label results as either:
  • Accounts Payable (AP) — money Allergo Nordic OWES to vendors
  • Accounts Receivable (AR) — money OWED TO Allergo Nordic by customers

CRITICAL — spend / amount questions:
  The tool result includes a 'total_amount_nok' field with the numeric sum already calculated.
  Use that figure directly. Do NOT attempt to sum string-formatted amounts yourself.
  If total_amount_nok is null or 0, use search_document_content to find amounts in document text.

CRITICAL — VAT / tax questions:
  When the CFO asks about total VAT, VAT amounts, or tax on invoices:
  1. Use query_financial_database with query_type='spend_by_period' and
     document_category='invoice'. The result includes 'total_vat_nok' and
     'total_net_nok' per period — use these directly.
  2. Apply date_from / date_to to scope to the requested period
     (e.g. 'this quarter' → date_from={quarter_start}, date_to={today}).
  3. Sum total_vat_nok across all returned periods for a grand total.
  4. If total_vat_nok is 0 or null for all periods, fall back to
     search_document_content with query='VAT MVA tax amount invoice'.
  Never attempt to calculate VAT from total_amount yourself.

CRITICAL — contracts expiry:
  When the CFO asks about expiring contracts without specifying a window, use days_ahead=90.
  A contract expiring within 90 days is urgent — always surface it even if the user just says
  'soon' or 'expiring'. The DB query already returns contract value and end dates — only call
  search_document_content additionally if the user explicitly asks about renewal clauses,
  termination terms, or penalty wording.

CRITICAL — contract financial accuracy:
  Each contract record contains TWO amount fields. Always use the correct one:
  • annual_recurring_fee  = the ONGOING annual cost (use for budget, penalty calculations,
                            break-even analysis, and anything about "yearly cost").
  • amount (contract_value) = may include one-time setup/implementation fees — do NOT use
                              this as the recurring cost unless annual_recurring_fee is absent.
  If both are present and different, state BOTH and explain the difference to the CFO.

CRITICAL — renewal status (auto-renewed contracts):
  The DB record includes renewal_status, renewal_deadline, and renewed_until fields.
  • If renewal_status = "auto_renewed": the contract has ALREADY been renewed automatically.
    The CFO MISSED the renewal deadline. You MUST clearly state:
    - That the renewal deadline has passed
    - The new end date (renewed_until)
    - The only exit now is paying the penalty clause
    Never present an auto-renewed contract as if the CFO still has a choice to renew or not.
  • If renewal_deadline is present and still in the future: warn the CFO of the exact deadline.
  • Always surface penalty_clause and termination_clause from the record verbatim.

Guidelines:
- ALWAYS use at least one tool before answering. Never answer from memory alone.
- For numbers, amounts, dates, counts, aggregations → use query_financial_database.
- For clauses, wording, legal text, report narratives, document content, ledger line items
  embedded in reports → use search_document_content.
- For strategic questions (shutdown, cost comparison, risk assessment) → use BOTH tools:
    1. query_financial_database for the financial data (spend, contracts, location aggregates)
    2. search_document_content for the legal and contractual context
    Then synthesise a structured recommendation.
- For legal questions: use legal_obligations query type AND search for specific clause wording.
- For ledger/accounting: use ledger_by_account for journal entries, spend_by_period for trends.
- For location/store analysis: use aggregate_by_location then search for relevant contracts.
- Call tools multiple times if needed — up to 6 rounds. Do not stop early on complex questions.

Response format:
- Be concise, professional, and direct — the user is a busy CFO.
- Present amounts with currency (e.g. NOK 125,000).
- Format lists as bullet points with key details on each line.
- For overdue invoices: group by AP (payables) and AR (receivables), include totals for each.
- For strategic decisions, use a short structured recommendation with: Facts → Risk → Recommendation.
- If data is not available in any tool result, say so clearly. Never fabricate numbers.
- After your answer, suggest 2–3 relevant follow-up questions the CFO might want to ask next.
  Format them as a JSON block at the very end:
  ```suggestions
  ["Follow-up question 1?", "Follow-up question 2?", "Follow-up question 3?"]
  ```
"""


# ── Drift / security helpers (module-level, no I/O) ──────────────────────────

#: Terraform resource types that carry security-sensitive attributes.
_SECURITY_SENSITIVE_TYPES: frozenset[str] = frozenset(
    {
        "azurerm_key_vault",
        "azurerm_key_vault_secret",
        "azurerm_network_security_group",
        "azurerm_network_security_rule",
        "azurerm_storage_account",
        "azurerm_postgresql_flexible_server",
        "azurerm_sql_server",
        "azurerm_kubernetes_cluster",
        "azurerm_role_assignment",
        "aws_security_group",
        "aws_s3_bucket",
        "aws_iam_role_policy",
        "aws_eks_cluster",
        "google_storage_bucket",
        "google_container_cluster",
    }
)

#: Attributes whose change from a permissive to restrictive value indicates a security fix,
#: and from restrictive to permissive indicates a regression.
_SECURITY_REGRESSION_ATTRS: dict[str, tuple[Any, Any]] = {
    # attr: (permissive_value, restrictive_value)
    "purge_protection_enabled": (False, True),
    "allow_blob_public_access": (True, False),
    "public_network_access_enabled": (True, False),
    "ssl_enforcement_enabled": (False, True),
    "https_only": (False, True),
    "enable_rbac_authorization": (False, True),
}


def _assess_security_risk(
    resource_type: str,
    before: dict,
    after: dict,
    action: str,
) -> dict[str, Any] | None:
    """Return a security risk entry if this resource change looks like a regression."""
    if resource_type not in _SECURITY_SENSITIVE_TYPES:
        return None
    if action == "no-op":
        return None
    regressions: list[str] = []
    fixes: list[str] = []
    for attr, (permissive_val, restrictive_val) in _SECURITY_REGRESSION_ATTRS.items():
        before_val = before.get(attr)
        after_val = after.get(attr)
        if before_val is None and after_val is None:
            continue
        if before_val == restrictive_val and after_val == permissive_val:
            regressions.append(attr)
        elif before_val == permissive_val and after_val == restrictive_val:
            fixes.append(attr)
    if regressions:
        return {
            "address": None,  # filled in by caller if available
            "resource_type": resource_type,
            "action": action,
            "regressions": regressions,
            "fixes": fixes,
            "severity": "HIGH",
            "note": f"Security regression detected: {regressions}",
        }
    return None


def _classify_drift_severity(resource_type: str, changed_attributes: list[str]) -> str:
    """Heuristically classify the severity of a drifted resource.

    Returns one of: CRITICAL | HIGH | MEDIUM | LOW
    """
    if resource_type in _SECURITY_SENSITIVE_TYPES:
        security_attrs = set(_SECURITY_REGRESSION_ATTRS.keys())
        if security_attrs.intersection(changed_attributes):
            return "HIGH"
        return "MEDIUM"
    # Deletions or replacements on data stores are always high
    if any(t in resource_type for t in ("database", "storage", "postgresql", "sql", "cosmos")):
        return "HIGH"
    # Network changes are medium
    if any(t in resource_type for t in ("network", "subnet", "firewall", "nsg")):
        return "MEDIUM"
    return "LOW"


def _build_system_prompt() -> str:
    """Build the system prompt with today's date injected at call time."""
    from datetime import date, timedelta

    today = date.today()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1

    month_name = today.strftime("%B")
    # Last month
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_name = last_month_start.strftime("%B %Y")

    # Quarter boundaries
    quarter_start_month = (quarter - 1) * 3 + 1
    quarter_start = date(year, quarter_start_month, 1)
    # Last quarter
    last_q_start_month = quarter_start_month - 3
    if last_q_start_month <= 0:
        last_q_start_month += 12
        last_q_year = year - 1
    else:
        last_q_year = year
    last_quarter_start = date(last_q_year, last_q_start_month, 1)
    last_quarter_end = quarter_start - timedelta(days=1)

    return _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        year=year,
        quarter=quarter,
        month_name=month_name,
        last_month_name=last_month_name,
        last_month_start=last_month_start.isoformat(),
        last_month_end=last_month_end.isoformat(),
        this_month_start=first_of_this_month.isoformat(),
        quarter_start=quarter_start.isoformat(),
        last_quarter_start=last_quarter_start.isoformat(),
        last_quarter_end=last_quarter_end.isoformat(),
    )


# _SYSTEM_PROMPT is intentionally NOT pre-computed at import time.
# es_rag.py imports this name; both files call _build_system_prompt() at request time
# so the injected date is always correct (no stale date after midnight).
_SYSTEM_PROMPT: str = ""  # placeholder — real value built per-request in _build_messages()


_INTENT_MAP = {
    "overdue_invoices": "invoice_query",
    "due_soon_invoices": "invoice_query",
    "expiring_contracts": "contract_query",
    "pending_approvals": "approval_query",
    "count_by_category": "analytics",
    "list_by_vendor": "vendor_query",
    "get_document_summary": "document_lookup",
    "dashboard_snapshot": "analytics",
    "aggregate_by_location": "location_analytics",
    "spend_by_period": "spend_analytics",
    "spend_by_cost_center": "spend_analytics",
    "legal_obligations": "legal_compliance",
    "ledger_by_account": "ledger_query",
}


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Citation:
    chunk_id: str
    document_id: str
    filename: str
    text: str
    score: float
    page: int | None = None


@dataclass
class AgentResponse:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    model: str = ""
    intent: str = "general"
    session_type: str = "finance_chat"
    tool_rounds_used: int = 0


class RagUseCase:
    def __init__(
        self,
        search_client: SearchClient,
        openai_client: AsyncAzureOpenAI,
        db_reader: FinancialDbReader,
        embedding_deployment: str,
        chat_deployment: str,
        top_k: int = 4,
        document_service_url: str = "http://localhost:8002",
        banking_db_reader: BankingDbReader | None = None,
    ) -> None:
        self._search = search_client
        self._openai = openai_client
        self._db = db_reader
        self._banking_db = banking_db_reader
        self._embed_deployment = embedding_deployment
        self._chat_deployment = chat_deployment
        self._top_k = min(top_k, 12)
        self._doc_service_url = document_service_url.rstrip("/")

    # ── Public API ────────────────────────────────────────────────────────────

    async def answer(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
        session_type: str = "finance_chat",
        auth_token: str | None = None,
    ) -> AgentResponse:
        """Run the agentic tool-calling loop and return a structured response."""
        allowed_tools = _SESSION_ALLOWED_TOOLS.get(session_type)
        session_tools = self._session_tools(session_type)
        messages = self._build_messages(question, history, session_type)
        citations: list[Citation] = []
        tools_used: list[str] = []
        rounds_used = 0

        for _round in range(MAX_TOOL_ROUNDS):
            rounds_used = _round + 1
            response = await self._openai.chat.completions.create(  # type: ignore[call-overload]
                model=self._chat_deployment,
                messages=messages,  # type: ignore[arg-type]
                tools=session_tools,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1024,
            )
            msg = response.choices[0].message

            # No more tool calls — final answer
            if not msg.tool_calls:
                answer_raw = msg.content or ""
                answer, suggestions = self._parse_suggestions(answer_raw)
                intent = self._detect_intent(tools_used)
                logger.info(
                    "agent_answer_ready",
                    tenant_id=tenant_id,
                    session_type=session_type,
                    tools=tools_used,
                    citations=len(citations),
                    rounds=rounds_used,
                )
                return AgentResponse(
                    answer=answer,
                    citations=citations,
                    tools_used=list(dict.fromkeys(tools_used)),
                    suggestions=suggestions,
                    model=response.model,
                    intent=intent,
                    session_type=session_type,
                    tool_rounds_used=rounds_used,
                )

            # Policy gate — check each tool call before executing
            messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]
            tool_results = await asyncio.gather(
                *[
                    self._execute_tool(
                        tc, tenant_id, document_ids,
                        allowed_tools=allowed_tools,
                        session_type=session_type,
                        auth_token=auth_token,
                    )
                    for tc in msg.tool_calls
                ]
            )
            for tool_call, (result, new_citations) in zip(msg.tool_calls, tool_results):
                citations.extend(new_citations)
                if tool_call.function.name == "query_financial_database":
                    try:
                        qt = json.loads(tool_call.function.arguments).get("query_type", tool_call.function.name)
                        tools_used.append(qt)
                    except Exception:
                        tools_used.append(tool_call.function.name)
                else:
                    tools_used.append(tool_call.function.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # Fallback if max rounds exceeded — ask for final answer without tools
        messages.append(
            {"role": "user", "content": "Please summarise your findings now."}
        )
        final = await self._openai.chat.completions.create(
            model=self._chat_deployment,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_tokens=1500,
        )
        answer_raw = final.choices[0].message.content or ""
        answer, suggestions = self._parse_suggestions(answer_raw)
        return AgentResponse(
            answer=answer,
            citations=citations,
            tools_used=list(dict.fromkeys(tools_used)),
            suggestions=suggestions,
            model=final.model,
            intent=self._detect_intent(tools_used),
            session_type=session_type,
            tool_rounds_used=MAX_TOOL_ROUNDS,
        )

    async def answer_stream(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
        session_type: str = "finance_chat",
        auth_token: str | None = None,
    ) -> "tuple[AgentResponse, AsyncIterator[str]]":
        """Run tool calls first (non-streaming), then stream the final answer."""
        allowed_tools = _SESSION_ALLOWED_TOOLS.get(session_type)
        session_tools = self._session_tools(session_type)
        # Phase 1: collect tool results
        messages = self._build_messages(question, history, session_type)
        citations: list[Citation] = []
        tools_used: list[str] = []

        for _round in range(MAX_TOOL_ROUNDS):
            response = await self._openai.chat.completions.create(  # type: ignore[call-overload]
                model=self._chat_deployment,
                messages=messages,  # type: ignore[arg-type]
                tools=session_tools,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1024,
            )
            msg = response.choices[0].message
            if not msg.tool_calls:
                break
            messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]
            # Execute all tool calls in this round concurrently
            tc_results = await asyncio.gather(
                *[
                    self._execute_tool(
                        tc, tenant_id, document_ids,
                        allowed_tools=allowed_tools,
                        session_type=session_type,
                        auth_token=auth_token,
                    )
                    for tc in msg.tool_calls
                ]
            )
            for tc, (result, new_cits) in zip(msg.tool_calls, tc_results):
                citations.extend(new_cits)
                if tc.function.name == "query_financial_database":
                    try:
                        qt = json.loads(tc.function.arguments).get("query_type", tc.function.name)
                        tools_used.append(qt)
                    except Exception:
                        tools_used.append(tc.function.name)
                else:
                    tools_used.append(tc.function.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # Phase 2: stream the final synthesis
        stream = await self._openai.chat.completions.create(  # type: ignore[call-overload]
            model=self._chat_deployment,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_tokens=1500,
            stream=True,
        )

        meta = AgentResponse(
            answer="",
            citations=citations,
            tools_used=list(dict.fromkeys(tools_used)),
            suggestions=[],
            intent=self._detect_intent(tools_used),
        )

        async def _token_gen() -> AsyncIterator[str]:
            async for chunk in stream:  # type: ignore[union-attr]
                if not chunk.choices:  # Azure OpenAI sends empty choices on the final chunk
                    continue
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta

        return meta, _token_gen()

    # ── Tool execution ────────────────────────────────────────────────────────

    async def _execute_tool(
        self,
        tool_call: ChatCompletionMessageToolCall,
        tenant_id: str,
        document_ids: list[str] | None,
        allowed_tools: frozenset[str] | None = None,
        session_type: str = "finance_chat",
        auth_token: str | None = None,
    ) -> tuple[Any, list[Citation]]:
        import time as _time

        name = tool_call.function.name
        try:
            args: dict[str, Any] = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {"error": "Invalid tool arguments"}, []

        # Policy gate: if an allowlist is configured for this session type, enforce it
        if allowed_tools is not None and name not in allowed_tools:
            logger.warning(
                "tool_policy_violation",
                tool=name,
                session_type=session_type,
                tenant_id=tenant_id,
            )
            await self._emit_audit(
                tenant_id=tenant_id,
                actor=f"chat-agent/{session_type}",
                action="chat.tool_policy_violation",
                resource_type="tool",
                resource_id=name,
                metadata={
                    "tool_name": name,
                    "session_type": session_type,
                    "allowed_tools": list(allowed_tools),
                },
                auth_token=auth_token,
            )
            return {
                "error": f"Tool '{name}' is not allowed in session_type='{session_type}'. "
                f"Allowed: {sorted(allowed_tools)}"
            }, []

        # Finance tools
        if name == "search_document_content":
            return await self._tool_search(
                query=args.get("query", ""),
                document_ids=args.get("document_ids") or document_ids,
                top_k=min(int(args.get("top_k", 6)), 12),
                tenant_id=tenant_id,
            )

        if name == "query_financial_database":
            return await self._tool_db(args, tenant_id), []

        # All remaining tools — wrapped with OTel span + Prometheus metrics per tool call
        _t0 = _time.monotonic()
        _tracer = get_tracer()
        with _tracer.start_as_current_span(f"tool.{name}") as _span:
            _span.set_attribute("tool.name", name)
            _span.set_attribute("session.type", session_type)
            _span.set_attribute("tool.round", 0)
            _span.set_attribute("tenant.id", tenant_id)
            try:
                if name == "list_infra_findings":
                    _r, _c = await self._tool_list_findings(args, tenant_id, auth_token), []
                elif name == "get_infra_finding":
                    _r, _c = await self._tool_get_finding(args, tenant_id, auth_token), []
                elif name == "get_terraform_plan_summary":
                    _r, _c = await self._tool_plan_summary(), []
                elif name == "propose_remediation":
                    _r, _c = await self._tool_propose_remediation(args, tenant_id, auth_token), []
                elif name == "get_infra_context_bundle":
                    _r, _c = await self._tool_get_context_bundle(args, tenant_id, auth_token), []
                elif name == "detect_infra_drift":
                    _r, _c = await self._tool_detect_drift(args, tenant_id, auth_token), []
                elif name == "query_banking_compliance":
                    _r, _c = await self._tool_query_banking_compliance(args, tenant_id), []
                elif name == "flag_transaction_for_review":
                    _r, _c = await self._tool_flag_transaction(args, tenant_id, auth_token), []
                elif name == "generate_sar_draft":
                    _r, _c = await self._tool_generate_sar_draft(args, tenant_id, auth_token), []
                else:
                    _r, _c = {"error": f"Unknown tool: {name}"}, []
            except Exception as _exc:
                _span.record_exception(_exc)
                raise
            finally:
                _elapsed = _time.monotonic() - _t0
                TOOL_CALLS_COUNTER.labels(session_type=session_type, tool_name=name).inc()
                TOOL_LATENCY_HISTOGRAM.labels(
                    session_type=session_type, tool_name=name
                ).observe(_elapsed)
        return _r, _c

    # ── Infra tool implementations ────────────────────────────────────────────

    async def _doc_service_get(
        self,
        path: str,
        tenant_id: str,
        params: dict[str, Any] | None = None,
        auth_token: str | None = None,
    ) -> Any:
        """GET request to the document-service API."""
        import aiohttp

        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        url = f"{self._doc_service_url}/api/v1{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params or {}) as resp:
                if resp.status == 404:
                    return {"error": "Not found"}
                resp.raise_for_status()
                return await resp.json()

    async def _doc_service_post(
        self,
        path: str,
        tenant_id: str,
        body: dict[str, Any],
        auth_token: str | None = None,
    ) -> Any:
        """POST request to the document-service API."""
        import aiohttp

        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        url = f"{self._doc_service_url}/api/v1{path}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as resp:
                if resp.status in (204,):
                    return {}
                resp.raise_for_status()
                return await resp.json()

    async def _emit_audit(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        metadata: dict[str, Any],
        auth_token: str | None,
    ) -> None:
        """Fire-and-forget audit event via document-service HTTP endpoint."""
        try:
            await self._doc_service_post(
                "/audit",
                tenant_id,
                {
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "metadata": metadata,
                },
                auth_token=auth_token,
            )
        except Exception as exc:
            logger.warning("audit_emit_failed", error=str(exc))

    async def _tool_list_findings(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": min(int(args.get("limit", 20)), 50),
            "offset": int(args.get("offset", 0)),
        }
        if args.get("severity"):
            params["severity"] = args["severity"]
        try:
            findings = await self._doc_service_get("/posture/findings", tenant_id, params, auth_token)
            return {"findings": findings, "count": len(findings) if isinstance(findings, list) else 0}
        except Exception as exc:
            return {"error": f"Failed to list findings: {exc}"}

    async def _tool_get_finding(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        finding_id = args.get("finding_id", "")
        if not finding_id:
            return {"error": "finding_id is required"}
        try:
            return await self._doc_service_get(f"/posture/findings/{finding_id}", tenant_id, auth_token=auth_token)
        except Exception as exc:
            return {"error": f"Failed to get finding: {exc}"}

    async def _tool_plan_summary(self) -> dict[str, Any]:
        """Return a structured Terraform plan summary.

        Resolution order:
        1. TERRAFORM_PLAN_PATH env var → parse a local tfplan.json produced by
           ``terraform show -json tfplan.binary > tfplan.json``
        2. TFC_TOKEN + TFC_WORKSPACE_ID env vars → Terraform Cloud API (latest run)
        3. Fixture file (labelled ``fixture_fallback`` so the LLM knows it is not live)
        """
        import json
        import os
        from pathlib import Path

        def _parse_plan_data(data: dict) -> dict[str, Any]:
            changes = data.get("resource_changes", [])
            action_counts: dict[str, int] = {}
            resources = []
            security_risks: list[dict] = []
            for rc in changes:
                raw_actions = rc.get("change", {}).get("actions", ["no-op"])
                action = "no-op" if raw_actions == ["no-op"] else raw_actions[0]
                action_counts[action] = action_counts.get(action, 0) + 1
                before = rc.get("change", {}).get("before") or {}
                after = rc.get("change", {}).get("after") or {}
                entry: dict[str, Any] = {
                    "address": rc.get("address"),
                    "type": rc.get("type"),
                    "action": action,
                }
                if action != "no-op":
                    changed_attrs = [k for k in set(list(before) + list(after)) if before.get(k) != after.get(k)]
                    if changed_attrs:
                        entry["changed_attributes"] = changed_attrs
                resources.append(entry)
                risk = _assess_security_risk(rc.get("type", ""), before, after, action)
                if risk:
                    security_risks.append(risk)
            return {
                "terraform_version": data.get("terraform_version"),
                "resource_changes_count": len(changes),
                "action_summary": action_counts,
                "resources": resources,
                "security_risks": security_risks,
            }

        # ── Strategy 1: local tfplan.json ────────────────────────────────────
        plan_path_env = os.environ.get("TERRAFORM_PLAN_PATH", "")
        if plan_path_env:
            plan_path = Path(plan_path_env)
            try:
                with plan_path.open() as fh:
                    data = json.load(fh)
                logger.info("plan_loaded_from_local_file", path=plan_path_env)
                return {"source": "local_file", "path": plan_path_env, **_parse_plan_data(data)}
            except Exception as exc:
                logger.warning("plan_local_file_failed", path=plan_path_env, error=str(exc))

        # ── Strategy 2: Terraform Cloud API ──────────────────────────────────
        tfc_token = os.environ.get("TFC_TOKEN", "")
        tfc_workspace = os.environ.get("TFC_WORKSPACE_ID", "")
        if tfc_token and tfc_workspace:
            try:
                import aiohttp
                headers = {
                    "Authorization": f"Bearer {tfc_token}",
                    "Content-Type": "application/vnd.api+json",
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    runs_url = f"https://app.terraform.io/api/v2/workspaces/{tfc_workspace}/runs"
                    async with session.get(runs_url, params={"page[size]": "1"}) as resp:
                        resp.raise_for_status()
                        runs = await resp.json()
                    runs_data = runs.get("data", [])
                    if not runs_data:
                        raise ValueError("No runs found in Terraform Cloud workspace")
                    run_id = runs_data[0]["id"]
                    run_status = runs_data[0]["attributes"]["status"]
                    plan_url = f"https://app.terraform.io/api/v2/runs/{run_id}/plan/json-output"
                    async with session.get(plan_url) as plan_resp:
                        plan_resp.raise_for_status()
                        data = await plan_resp.json()
                logger.info("plan_loaded_from_tfc", workspace=tfc_workspace, run_id=run_id)
                return {
                    "source": "terraform_cloud",
                    "workspace_id": tfc_workspace,
                    "run_id": run_id,
                    "run_status": run_status,
                    **_parse_plan_data(data),
                }
            except Exception as exc:
                logger.warning("plan_tfc_api_failed", workspace=tfc_workspace, error=str(exc))

        # ── Strategy 3: fixture fallback ─────────────────────────────────────
        fixture = (
            Path(__file__).parent.parent.parent.parent.parent.parent
            / "fixtures"
            / "terraform-plan-sample.json"
        )
        try:
            if fixture.exists():
                with fixture.open() as fh:
                    data = json.load(fh)
                logger.info("plan_loaded_from_fixture")
                return {"source": "fixture_fallback", **_parse_plan_data(data)}
        except Exception as exc:
            logger.warning("plan_fixture_load_failed", error=str(exc))

        return {
            "source": "unavailable",
            "error": (
                "No plan source configured. "
                "Set TERRAFORM_PLAN_PATH (path to tfplan.json) or "
                "TFC_TOKEN + TFC_WORKSPACE_ID for Terraform Cloud."
            ),
        }

    async def _tool_detect_drift(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        """Detect infrastructure drift.

        Two modes:
        - Snapshot comparison: provide ``snapshot_id_baseline`` + ``snapshot_id_current``
          to diff two stored infra_context_snapshots from the document-service.
        - Plan analysis: no snapshot IDs → analyse the current Terraform plan and
          surface any non-no-op resource changes with severity classification.
        """
        snapshot_id_baseline = args.get("snapshot_id_baseline", "")
        snapshot_id_current = args.get("snapshot_id_current", "")

        if snapshot_id_baseline and snapshot_id_current:
            # ── Snapshot comparison mode ──────────────────────────────────────
            try:
                baseline = await self._doc_service_get(
                    f"/posture/snapshots/{snapshot_id_baseline}", tenant_id, auth_token=auth_token
                )
                current_snap = await self._doc_service_get(
                    f"/posture/snapshots/{snapshot_id_current}", tenant_id, auth_token=auth_token
                )
            except Exception as exc:
                return {"error": f"Failed to retrieve snapshots for drift comparison: {exc}"}

            def _index(snap: dict) -> dict[str, dict]:
                return {
                    r["address"]: r
                    for r in (snap.get("terraform_plan", {}).get("resources") or [])
                }

            baseline_idx = _index(baseline)
            current_idx = _index(current_snap)

            drifted: list[dict] = []
            added: list[dict] = []
            removed: list[dict] = []

            for addr, curr_r in current_idx.items():
                if addr not in baseline_idx:
                    added.append({
                        "address": addr,
                        "type": curr_r.get("type"),
                        "status": "added_since_baseline",
                    })
                elif curr_r.get("action") != baseline_idx[addr].get("action"):
                    changed_attrs = curr_r.get("changed_attributes", [])
                    drifted.append({
                        "address": addr,
                        "type": curr_r.get("type"),
                        "baseline_action": baseline_idx[addr].get("action"),
                        "current_action": curr_r.get("action"),
                        "changed_attributes": changed_attrs,
                        "severity": _classify_drift_severity(curr_r.get("type", ""), changed_attrs),
                    })

            for addr in baseline_idx:
                if addr not in current_idx:
                    removed.append({
                        "address": addr,
                        "type": baseline_idx[addr].get("type"),
                        "status": "removed_since_baseline",
                    })

            return {
                "source": "snapshot_comparison",
                "baseline_snapshot_id": snapshot_id_baseline,
                "current_snapshot_id": snapshot_id_current,
                "drift_count": len(drifted),
                "added_count": len(added),
                "removed_count": len(removed),
                "drifted_resources": drifted,
                "added_resources": added,
                "removed_resources": removed,
                "requires_review": len(drifted) + len(removed) > 0,
                "recommendation": (
                    f"{len(drifted)} resource(s) drifted, {len(removed)} removed. Review before next apply."
                    if drifted or removed
                    else "No drift detected between the two snapshots."
                ),
            }

        # ── Plan analysis mode ────────────────────────────────────────────────
        plan = await self._tool_plan_summary()
        if "error" in plan and plan.get("source") == "unavailable":
            return plan

        resources = plan.get("resources", [])
        drifted = [
            {
                "address": r["address"],
                "type": r.get("type"),
                "action": r["action"],
                "changed_attributes": r.get("changed_attributes", []),
                "severity": _classify_drift_severity(
                    r.get("type", ""), r.get("changed_attributes", [])
                ),
            }
            for r in resources
            if r.get("action") not in ("no-op", None)
        ]
        security_risks = plan.get("security_risks", [])

        return {
            "source": plan.get("source", "plan"),
            "plan_terraform_version": plan.get("terraform_version"),
            "total_resources_in_plan": len(resources),
            "drift_count": len(drifted),
            "drifted_resources": drifted,
            "security_risk_count": len(security_risks),
            "security_risks": security_risks,
            "action_summary": plan.get("action_summary", {}),
            "requires_review": len(drifted) > 0,
            "recommendation": (
                f"{len(drifted)} resource(s) have pending changes — review before apply."
                if drifted
                else "No drift detected — Terraform plan is clean (all no-op)."
            ),
        }

    async def _tool_propose_remediation(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        """Create an agent_workflow_run + change_proposal via document-service."""
        finding_id = args.get("finding_id", "")
        unified_diff = args.get("unified_diff", "")
        rationale_md = args.get("rationale_md", "")
        resource_addresses = args.get("resource_addresses", [])
        risk_level = args.get("risk_level", "medium")

        if not all([finding_id, unified_diff, rationale_md]):
            return {"error": "finding_id, unified_diff, and rationale_md are required"}

        try:
            run = await self._doc_service_post(
                "/posture/runs",
                tenant_id,
                {
                    "session_type": "infra_remediation",
                    "max_tool_rounds": MAX_TOOL_ROUNDS,
                    "metadata": {"source_finding_id": finding_id},
                },
                auth_token=auth_token,
            )
            run_id = run.get("id")
            if not run_id:
                return {"error": "Failed to create run — no id in response"}

            proposal = await self._doc_service_post(
                f"/posture/runs/{run_id}/proposals",
                tenant_id,
                {
                    "unified_diff": unified_diff,
                    "rationale_md": rationale_md,
                    "resource_addresses": resource_addresses,
                    "risk_level": risk_level,
                },
                auth_token=auth_token,
            )
            return {
                "status": "proposal_created",
                "run_id": run_id,
                "proposal_id": proposal.get("id"),
                "workflow_state": "proposing",
                "next_step": "Human approval required at POST /posture/proposals/{id}/approve",
                "note": "This is a PROPOSAL only — no Terraform apply has been triggered.",
            }
        except Exception as exc:
            return {"error": f"Failed to create proposal: {exc}"}

    async def _tool_get_context_bundle(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        snapshot_id = args.get("snapshot_id", "")
        if not snapshot_id:
            return {"error": "snapshot_id is required"}
        try:
            return await self._doc_service_get(
                f"/posture/snapshots/{snapshot_id}", tenant_id, auth_token=auth_token
            )
        except Exception as exc:
            return {"error": f"Failed to get context bundle: {exc}"}

    # ── Banking compliance tool implementations ───────────────────────────────

    async def _tool_query_banking_compliance(
        self, args: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]:
        """Dispatch to BankingDbReader for structured AML/KYC/SAR queries."""
        from datetime import date as _date

        if self._banking_db is None:
            return {"error": "Banking compliance DB reader not configured for this deployment."}

        q = args.get("query_type", "")
        today_str = _date.today().isoformat()
        limit = min(int(args.get("limit", 20)), 50)
        risk_level = args.get("risk_level")
        date_from = args.get("date_from")
        date_to = args.get("date_to")

        if q == "aml_flags":
            rows = await self._banking_db.get_aml_flags(tenant_id, risk_level=risk_level, limit=limit)
            return {"query": q, "as_of": today_str, "count": len(rows), "flags": rows}

        if q == "kyc_pending_reviews":
            rows = await self._banking_db.get_kyc_pending(tenant_id, limit=limit)
            return {"query": q, "as_of": today_str, "count": len(rows), "customers": rows}

        if q == "sar_candidates":
            rows = await self._banking_db.get_sar_candidates(
                tenant_id, date_from=date_from, date_to=date_to, limit=limit
            )
            return {
                "query": q,
                "as_of": today_str,
                "ctr_threshold_nok": 100000,
                "count": len(rows),
                "transactions": rows,
            }

        if q == "risk_score_summary":
            summary = await self._banking_db.get_risk_score_summary(tenant_id)
            return {"query": q, "as_of": today_str, "summary": summary}

        if q == "regulatory_calendar":
            rows = await self._banking_db.get_regulatory_calendar(tenant_id)
            return {"query": q, "as_of": today_str, "count": len(rows), "deadlines": rows}

        if q == "pep_screening_results":
            rows = await self._banking_db.get_pep_screening_results(tenant_id, limit=limit)
            return {"query": q, "as_of": today_str, "count": len(rows), "pep_hits": rows}

        return {"error": f"Unknown banking query_type: {q}"}

    async def _tool_flag_transaction(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        """Write a governed compliance flag record — HITL required to act on it."""
        transaction_id = args.get("transaction_id", "")
        flag_reason = args.get("flag_reason", "")
        evidence_summary = args.get("evidence_summary", "")
        risk_level = args.get("risk_level", "high")

        if not all([transaction_id, flag_reason, evidence_summary]):
            return {"error": "transaction_id, flag_reason, and evidence_summary are required"}

        if self._banking_db is None:
            return {"error": "Banking compliance DB reader not configured for this deployment."}

        try:
            flag_id = await self._banking_db.create_compliance_flag(
                tenant_id=tenant_id,
                transaction_id=transaction_id,
                flag_reason=flag_reason,
                evidence_json={"summary": evidence_summary, "risk_level": risk_level},
                created_by="chat-agent/banking_compliance",
            )
            await self._emit_audit(
                tenant_id=tenant_id,
                actor="chat-agent/banking_compliance",
                action="banking.compliance_flag_created",
                resource_type="transaction",
                resource_id=transaction_id,
                metadata={
                    "flag_id": flag_id,
                    "flag_reason": flag_reason,
                    "risk_level": risk_level,
                },
                auth_token=auth_token,
            )
            return {
                "status": "flag_created",
                "flag_id": flag_id,
                "transaction_id": transaction_id,
                "flag_reason": flag_reason,
                "risk_level": risk_level,
                "workflow_state": "open",
                "next_step": "Human compliance officer review required before any regulatory action.",
                "note": "This flag does NOT automatically freeze the account or file a SAR.",
            }
        except Exception as exc:
            return {"error": f"Failed to create compliance flag: {exc}"}

    async def _tool_generate_sar_draft(
        self, args: dict[str, Any], tenant_id: str, auth_token: str | None
    ) -> dict[str, Any]:
        """Write a SAR draft record — human approval required before any regulatory submission."""
        flag_ids = args.get("flag_ids", [])
        narrative_md = args.get("narrative_md", "")
        reporting_obligation = args.get("reporting_obligation", "discretionary")

        if not flag_ids or not narrative_md:
            return {"error": "flag_ids (non-empty) and narrative_md are required"}

        if self._banking_db is None:
            return {"error": "Banking compliance DB reader not configured for this deployment."}

        try:
            draft_id = await self._banking_db.create_sar_draft(
                tenant_id=tenant_id,
                narrative_md=narrative_md,
                source_flag_ids=flag_ids,
                reporting_obligation=reporting_obligation,
            )
            await self._emit_audit(
                tenant_id=tenant_id,
                actor="chat-agent/banking_compliance",
                action="banking.sar_draft_created",
                resource_type="sar_draft",
                resource_id=draft_id,
                metadata={
                    "flag_ids": flag_ids,
                    "reporting_obligation": reporting_obligation,
                },
                auth_token=auth_token,
            )
            return {
                "status": "sar_draft_created",
                "draft_id": draft_id,
                "source_flag_ids": flag_ids,
                "reporting_obligation": reporting_obligation,
                "workflow_state": "pending_review",
                "next_step": "Human compliance officer must approve before filing with Finanstilsynet.",
                "note": "This SAR draft has NOT been submitted to any regulator. Human approval required.",
            }
        except Exception as exc:
            return {"error": f"Failed to create SAR draft: {exc}"}

    # ── Session helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _session_tools(session_type: str) -> list[dict]:
        """Return the TOOLS subset allowed for this session_type."""
        allowed = _SESSION_ALLOWED_TOOLS.get(session_type)
        if allowed is None:
            return TOOLS  # all tools
        return [t for t in TOOLS if t["function"]["name"] in allowed]

    async def _tool_search(
        self,
        query: str,
        document_ids: list[str] | None,
        top_k: int,
        tenant_id: str,
    ) -> tuple[dict, list[Citation]]:
        """Hybrid vector + keyword search."""
        embed_resp = await self._openai.embeddings.create(
            model=self._embed_deployment, input=[query]
        )
        embedding = embed_resp.data[0].embedding

        vector_query = VectorizedQuery(
            vector=embedding, k_nearest_neighbors=top_k, fields="embedding"
        )
        odata_filter = f"tenant_id eq '{tenant_id}'"
        if document_ids:
            id_filter = " or ".join(f"document_id eq '{d}'" for d in document_ids)
            odata_filter += f" and ({id_filter})"

        results = await self._search.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=odata_filter,
            top=top_k,
            select=["id", "document_id", "text", "filename", "page_number"],
        )

        passages: list[dict] = []
        citations: list[Citation] = []
        async for r in results:
            passages.append(
                {
                    "chunk_index": len(passages) + 1,
                    "document_id": r["document_id"],
                    "filename": r.get("filename", ""),
                    "text": r["text"],
                    "score": round(r["@search.score"], 4),
                    "page": r.get("page_number"),
                }
            )
            citations.append(
                Citation(
                    chunk_id=r["id"],
                    document_id=r["document_id"],
                    filename=r.get("filename", ""),
                    text=r["text"],
                    score=r["@search.score"],
                    page=r.get("page_number"),
                )
            )

        return {"passages": passages, "total_retrieved": len(passages)}, citations

    async def _tool_db(self, args: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        """Dispatch to the appropriate FinancialDbReader method."""
        from datetime import date as _date
        today_str = _date.today().isoformat()
        q = args.get("query_type", "")

        if q == "overdue_invoices":
            records = await self._db.get_overdue_invoices(tenant_id)
            recs = [_rec(r) for r in records]
            # Annotate with days_overdue for LLM accuracy
            for r in recs:
                if r.get("due_date"):
                    try:
                        from datetime import datetime
                        delta = (_date.today() - datetime.fromisoformat(r["due_date"]).date()).days
                        r["days_overdue"] = delta
                    except Exception:
                        pass
            return {"query": q, "as_of": today_str, "count": len(recs), "records": recs}

        if q == "due_soon_invoices":
            days = int(args.get("days_ahead", 90))
            records = await self._db.get_due_soon_invoices(tenant_id, days)
            return {"query": q, "as_of": today_str, "days_ahead": days, "count": len(records), "records": [_rec(r) for r in records]}

        if q == "expiring_contracts":
            days = int(args.get("days_ahead", 90))
            records = await self._db.get_expiring_contracts(tenant_id, days)
            recs = [_rec(r) for r in records]
            for r in recs:
                if r.get("due_date"):
                    try:
                        from datetime import datetime
                        delta = (datetime.fromisoformat(r["due_date"]).date() - _date.today()).days
                        r["days_until_expiry"] = delta
                    except Exception:
                        pass
            return {"query": q, "as_of": today_str, "days_ahead": days, "count": len(recs), "records": recs}

        if q == "pending_approvals":
            records = await self._db.list_pending_approvals(tenant_id)
            return {"query": q, "as_of": today_str, "count": len(records), "records": [_rec(r) for r in records]}

        if q == "count_by_category":
            rows = await self._db.count_by_category(
                tenant_id,
                date_from=args.get("date_from"),
                date_to=args.get("date_to"),
            )
            return {"query": q, "as_of": today_str, "categories": rows}

        if q == "list_by_vendor":
            vendor = args.get("vendor_name", "")
            if not vendor:
                return {"error": "vendor_name is required for list_by_vendor"}
            records = await self._db.list_by_vendor(
                tenant_id, vendor, args.get("document_category")
            )
            return {"query": q, "as_of": today_str, "vendor": vendor, "count": len(records), "records": [_rec(r) for r in records]}

        if q == "get_document_summary":
            doc_id = args.get("document_id", "")
            if not doc_id:
                return {"error": "document_id is required for get_document_summary"}
            summary = await self._db.get_document_summary(tenant_id, doc_id)
            return {"query": q, "as_of": today_str, "document": summary}

        if q == "dashboard_snapshot":
            snap = await self._db.get_dashboard_snapshot(tenant_id)
            return {"query": q, "as_of": today_str, "snapshot": snap}

        if q == "aggregate_by_location":
            rows = await self._db.aggregate_by_location(
                tenant_id,
                document_category=args.get("document_category"),
                date_from=args.get("date_from"),
                date_to=args.get("date_to"),
            )
            return {"query": q, "as_of": today_str, "count": len(rows), "locations": rows}

        if q == "spend_by_period":
            rows = await self._db.spend_by_period(
                tenant_id,
                period_unit=args.get("period_unit", "month"),
                document_category=args.get("document_category"),
                date_from=args.get("date_from"),
                date_to=args.get("date_to"),
            )
            return {"query": q, "as_of": today_str, "period_unit": args.get("period_unit", "month"), "periods": rows}

        if q == "spend_by_cost_center":
            rows = await self._db.spend_by_cost_center(
                tenant_id,
                document_category=args.get("document_category"),
                date_from=args.get("date_from"),
                date_to=args.get("date_to"),
            )
            return {"query": q, "as_of": today_str, "count": len(rows), "cost_centers": rows}

        if q == "legal_obligations":
            rows = await self._db.get_legal_obligations(
                tenant_id,
                include_risk_only=bool(args.get("include_risk_only", False)),
                location=args.get("location"),
            )
            return {"query": q, "as_of": today_str, "count": len(rows), "contracts": rows}

        if q == "ledger_by_account":
            rows = await self._db.ledger_by_account(
                tenant_id,
                account_code=args.get("account_code"),
                posting_period=args.get("posting_period"),
                location=args.get("location"),
            )
            return {"query": q, "as_of": today_str, "count": len(rows), "ledger_documents": rows}

        return {"error": f"Unknown query_type: {q}"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_messages(
        question: str, history: list[ChatMessage] | None, session_type: str = "finance_chat"
    ) -> list[dict[str, str]]:
        from datetime import date
        today = date.today().isoformat()
        if session_type == "infra_remediation":
            system_content = _INFRA_SYSTEM_PROMPT.format(today=today)
        elif session_type == "banking_compliance":
            system_content = _BANKING_COMPLIANCE_PROMPT.format(today=today)
        else:
            system_content = _build_system_prompt()
        msgs: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        for h in (history or [])[-10:]:  # Keep last 10 turns to manage context
            msgs.append({"role": h.role, "content": h.content})
        msgs.append({"role": "user", "content": question})
        return msgs

    @staticmethod
    def _parse_suggestions(raw: str) -> tuple[str, list[str]]:
        """Split the answer from the trailing suggestions JSON block."""
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

    @staticmethod
    def _detect_intent(tools_used: list[str]) -> str:
        # Prefer the most specific intent from query_financial_database calls
        # tools_used contains tool names; for DB calls we need the query_type
        # which is embedded in the tool_call args — we use a coarser mapping here
        # but es_rag._detect_intent has the same logic
        if not tools_used:
            return "general"
        # Banking compliance tools take priority when present
        if "generate_sar_draft" in tools_used:
            return "sar_draft"
        if "flag_transaction_for_review" in tools_used:
            return "compliance_flag"
        if "query_banking_compliance" in tools_used:
            return "banking_compliance_query"
        # Use the _INTENT_MAP on db query types stored in tools_used
        for tool in tools_used:
            if tool in _INTENT_MAP:
                return _INTENT_MAP[tool]
        # Fallback: any DB call is financial_data, any search is content_search
        if "query_financial_database" in tools_used:
            return "financial_data"
        if "search_document_content" in tools_used:
            return "content_search"
        return "general"


def _rec(r: Any) -> dict:
    """Serialise a FinancialRecord to a plain dict, including any extra contract fields."""
    base = {
        "document_id": r.document_id,
        "filename": r.filename,
        "category": r.document_category,
        "vendor": r.vendor_name,
        "amount": r.total_amount,
        "due_date": r.due_date,
        "invoice_number": r.invoice_number,
        "currency": r.currency,
        "status": r.status,
        "review_status": r.review_status,
    }
    # Merge in any extra fields (annual_recurring_fee, renewal_status, etc.)
    if hasattr(r, "extra") and r.extra:
        base.update(r.extra)
    return base
