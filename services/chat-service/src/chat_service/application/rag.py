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

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from allergo_shared.infrastructure.logging import get_logger
from chat_service.application.tools import TOOLS
from chat_service.infrastructure.db_reader import FinancialDbReader

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 6

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

CRITICAL — contracts expiry:
  When the CFO asks about expiring contracts without specifying a window, use days_ahead=90.
  A contract expiring within 90 days is urgent — always surface it even if the user just says
  'soon' or 'expiring'. Also use search_document_content to find renewal clauses and penalties.

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


# Keep _SYSTEM_PROMPT as an alias used by es_rag.py — it imports this symbol directly.
# es_rag.py will call _build_system_prompt() via _build_messages() override below.
_SYSTEM_PROMPT = _build_system_prompt()  # fallback static reference; actual use is dynamic


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


class RagUseCase:
    def __init__(
        self,
        search_client: SearchClient,
        openai_client: AsyncAzureOpenAI,
        db_reader: FinancialDbReader,
        embedding_deployment: str,
        chat_deployment: str,
        top_k: int = 6,
    ) -> None:
        self._search = search_client
        self._openai = openai_client
        self._db = db_reader
        self._embed_deployment = embedding_deployment
        self._chat_deployment = chat_deployment
        self._top_k = min(top_k, 12)

    # ── Public API ────────────────────────────────────────────────────────────

    async def answer(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
    ) -> AgentResponse:
        """Run the agentic tool-calling loop and return a structured response."""
        messages = self._build_messages(question, history)
        citations: list[Citation] = []
        tools_used: list[str] = []

        for _round in range(MAX_TOOL_ROUNDS):
            response = await self._openai.chat.completions.create(  # type: ignore[call-overload]
                model=self._chat_deployment,
                messages=messages,  # type: ignore[arg-type]
                tools=TOOLS,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0.1,
                max_tokens=2048,
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
                    tools=tools_used,
                    citations=len(citations),
                    rounds=_round + 1,
                )
                return AgentResponse(
                    answer=answer,
                    citations=citations,
                    tools_used=list(dict.fromkeys(tools_used)),
                    suggestions=suggestions,
                    model=response.model,
                    intent=intent,
                )

            # Execute each tool call the LLM requested
            messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]
            for tool_call in msg.tool_calls:
                result, new_citations = await self._execute_tool(
                    tool_call, tenant_id, document_ids
                )
                citations.extend(new_citations)
                # For DB calls, record the query_type for accurate intent detection
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
            max_tokens=2048,
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
        )

    async def answer_stream(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
    ) -> "tuple[AgentResponse, AsyncIterator[str]]":
        """Run tool calls first (non-streaming), then stream the final answer."""
        # Phase 1: collect tool results
        messages = self._build_messages(question, history)
        citations: list[Citation] = []
        tools_used: list[str] = []

        for _round in range(MAX_TOOL_ROUNDS):
            response = await self._openai.chat.completions.create(  # type: ignore[call-overload]
                model=self._chat_deployment,
                messages=messages,  # type: ignore[arg-type]
                tools=TOOLS,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1024,  # Enough for tool selection + arguments; 128 was too small
            )
            msg = response.choices[0].message
            if not msg.tool_calls:
                break
            messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]
            for tc in msg.tool_calls:
                result, new_cits = await self._execute_tool(tc, tenant_id, document_ids)
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
            max_tokens=2048,
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
    ) -> tuple[Any, list[Citation]]:
        name = tool_call.function.name
        try:
            args: dict[str, Any] = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {"error": "Invalid tool arguments"}, []

        if name == "search_document_content":
            return await self._tool_search(
                query=args.get("query", ""),
                document_ids=args.get("document_ids") or document_ids,
                top_k=min(int(args.get("top_k", 6)), 12),
                tenant_id=tenant_id,
            )

        if name == "query_financial_database":
            return await self._tool_db(args, tenant_id), []

        return {"error": f"Unknown tool: {name}"}, []

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
        question: str, history: list[ChatMessage] | None
    ) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt()}]
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
    """Serialise a FinancialRecord to a plain dict."""
    return {
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
