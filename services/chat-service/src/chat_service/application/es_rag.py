"""Elasticsearch-backed RAG use-case (local development / self-hosted).

Drop-in replacement for RagUseCase when the configured search endpoint
points to an Elasticsearch instance instead of Azure AI Search.

The vector search uses Elasticsearch's native kNN query (ES 8.x) and
the keyword fallback uses multi-match BM25.  The result shape is
identical to the Azure Search path so all downstream route handlers
remain unchanged.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import aiohttp
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.logging import get_logger
from chat_service.application.rag import (
    AgentResponse,
    ChatMessage,
    Citation,
    MAX_TOOL_ROUNDS,
    _build_system_prompt,
    _INTENT_MAP,
    _rec,
)
from chat_service.application.tools import TOOLS
from chat_service.infrastructure.db_reader import FinancialDbReader

logger = get_logger(__name__)


class ElasticsearchRagUseCase:
    """RagUseCase variant that retrieves passages from Elasticsearch.

    The tool-calling loop and DB-reader dispatch are identical to
    RagUseCase; only the ``search_document_content`` tool implementation
    differs — it issues an HTTP request to ES instead of using the
    Azure SDK SearchClient.
    """

    def __init__(
        self,
        es_endpoint: str,
        index_name: str,
        openai_client: AsyncAzureOpenAI,
        db_reader: FinancialDbReader,
        embedding_deployment: str,
        chat_deployment: str,
        top_k: int = 6,
    ) -> None:
        # Normalise endpoint: strip trailing slash
        self._es_endpoint = es_endpoint.rstrip("/")
        self._index = index_name
        self._openai = openai_client
        self._db = db_reader
        self._embed_deployment = embedding_deployment
        self._chat_deployment = chat_deployment
        self._top_k = min(top_k, 12)

    # ── Public API (same signature as RagUseCase) ─────────────────────────────

    async def answer(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
    ) -> AgentResponse:
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

            if not msg.tool_calls:
                answer_raw = msg.content or ""
                answer, suggestions = _parse_suggestions(answer_raw)
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
                    intent=_detect_intent(tools_used),
                )

            messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]
            for tool_call in msg.tool_calls:
                result, new_cits = await self._execute_tool(
                    tool_call, tenant_id, document_ids
                )
                citations.extend(new_cits)
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

        # Fallback when max rounds exceeded
        messages.append({"role": "user", "content": "Please summarise your findings now."})
        final = await self._openai.chat.completions.create(
            model=self._chat_deployment,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_tokens=2048,
        )
        answer_raw = final.choices[0].message.content or ""
        answer, suggestions = _parse_suggestions(answer_raw)
        return AgentResponse(
            answer=answer,
            citations=citations,
            tools_used=list(dict.fromkeys(tools_used)),
            suggestions=suggestions,
            model=final.model,
            intent=_detect_intent(tools_used),
        )

    async def answer_stream(
        self,
        question: str,
        tenant_id: str,
        history: list[ChatMessage] | None = None,
        document_ids: list[str] | None = None,
    ) -> "tuple[AgentResponse, AsyncIterator[str]]":
        """Tool-call phase (blocking) → streaming final answer."""
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
            intent=_detect_intent(tools_used),
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
        tool_call: Any,
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
        """Hybrid kNN + BM25 search against Elasticsearch."""
        # 1. Embed the query
        embed_resp = await self._openai.embeddings.create(
            model=self._embed_deployment, input=[query]
        )
        embedding = embed_resp.data[0].embedding

        # 2. Build the ES query
        must_filter: list[dict] = [{"term": {"tenant_id": tenant_id}}]
        if document_ids:
            must_filter.append({"terms": {"document_id": document_ids}})

        es_query = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": query, "fields": ["text", "filename"]}}],
                    "filter": must_filter,
                }
            },
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": top_k,
                "num_candidates": top_k * 5,
                "filter": {"bool": {"filter": must_filter}},
            },
            "_source": ["id", "document_id", "text", "filename", "page_number"],
        }

        # 3. Execute against ES
        url = f"{self._es_endpoint}/{self._index}/_search"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=es_query,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                body = await resp.json()

        hits = body.get("hits", {}).get("hits", [])
        passages: list[dict] = []
        citations: list[Citation] = []

        for h in hits:
            src = h.get("_source", {})
            score = h.get("_score", 0.0) or 0.0
            passages.append(
                {
                    "chunk_index": len(passages) + 1,
                    "document_id": src.get("document_id", ""),
                    "filename": src.get("filename", ""),
                    "text": src.get("text", ""),
                    "score": round(float(score), 4),
                    "page": src.get("page_number"),
                }
            )
            citations.append(
                Citation(
                    chunk_id=src.get("id", h["_id"]),
                    document_id=src.get("document_id", ""),
                    filename=src.get("filename", ""),
                    text=src.get("text", ""),
                    score=float(score),
                    page=src.get("page_number"),
                )
            )

        return {"passages": passages, "total_retrieved": len(passages)}, citations

    async def _tool_db(self, args: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        """Dispatch to the appropriate FinancialDbReader method (identical to RagUseCase)."""
        from datetime import date as _date
        q = args.get("query_type", "")
        today = _date.today()
        today_str = today.isoformat()

        if q == "overdue_invoices":
            records = await self._db.get_overdue_invoices(tenant_id)
            annotated = []
            for r in records:
                rec = _rec(r)
                rec["as_of"] = today_str
                try:
                    due = _date.fromisoformat(str(getattr(r, "due_date", "") or ""))
                    rec["days_overdue"] = (today - due).days
                except Exception:
                    pass
                annotated.append(rec)
            return {"query": q, "as_of": today_str, "count": len(annotated), "records": annotated}
        if q == "due_soon_invoices":
            days = int(args.get("days_ahead", 90))
            records = await self._db.get_due_soon_invoices(tenant_id, days)
            annotated = []
            for r in records:
                rec = _rec(r)
                rec["as_of"] = today_str
                try:
                    due = _date.fromisoformat(str(getattr(r, "due_date", "") or ""))
                    rec["days_until_due"] = (due - today).days
                except Exception:
                    pass
                annotated.append(rec)
            return {"query": q, "as_of": today_str, "days_ahead": days, "count": len(annotated), "records": annotated}
        if q == "expiring_contracts":
            days = int(args.get("days_ahead", 90))
            records = await self._db.get_expiring_contracts(tenant_id, days)
            annotated = []
            for r in records:
                rec = _rec(r)
                rec["as_of"] = today_str
                try:
                    exp = _date.fromisoformat(str(getattr(r, "contract_end_date", "") or ""))
                    rec["days_until_expiry"] = (exp - today).days
                except Exception:
                    pass
                annotated.append(rec)
            return {"query": q, "as_of": today_str, "days_ahead": days, "count": len(annotated), "records": annotated}
        if q == "pending_approvals":
            records = await self._db.list_pending_approvals(tenant_id)
            return {"query": q, "as_of": today_str, "count": len(records), "records": [_rec(r) for r in records]}
        if q == "count_by_category":
            rows = await self._db.count_by_category(
                tenant_id, date_from=args.get("date_from"), date_to=args.get("date_to")
            )
            return {"query": q, "as_of": today_str, "categories": rows}
        if q == "list_by_vendor":
            vendor = args.get("vendor_name", "")
            if not vendor:
                return {"error": "vendor_name is required for list_by_vendor"}
            records = await self._db.list_by_vendor(tenant_id, vendor, args.get("document_category"))
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
        for h in (history or [])[-10:]:
            msgs.append({"role": h.role, "content": h.content})
        msgs.append({"role": "user", "content": question})
        return msgs

    @staticmethod
    def _parse_suggestions(raw: str) -> tuple[str, list[str]]:
        """Extract trailing ```suggestions JSON block from the model answer."""
        return _parse_suggestions(raw)


def _parse_suggestions(raw: str) -> tuple[str, list[str]]:
    """Extract trailing ```suggestions JSON block from the model answer."""
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


def _detect_intent(tools_used: list[str]) -> str:
    if not tools_used:
        return "general"
    for tool in tools_used:
        intent = _INTENT_MAP.get(tool)
        if intent:
            return intent
        if tool == "search_document_content":
            return "content_search"
    return "general"
