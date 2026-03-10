"""OpenAI function/tool definitions for the CFO chat agent.

The LLM decides which tools to call. Each tool maps 1:1 to a method
on FinancialDbReader or the vector search pipeline.

Design:
  - search_document_content  → vector + keyword hybrid retrieval
  - query_financial_database → structured SQL against the metadata DB
  - get_dashboard_snapshot   → high-level KPIs in one shot

The agentic loop in RagUseCase can call tools multiple times before
composing the final answer (ReAct pattern).
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_document_content",
            "description": (
                "Semantically search the full text of uploaded documents using hybrid "
                "vector + keyword retrieval. Use this when the question asks about "
                "clauses, terms, conditions, specific wording, or any content that "
                "lives in the body of a document (contract clauses, report sections, "
                "definitions, obligations, warranties, termination rights, penalty "
                "language, governing law, legal obligations, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of document IDs to restrict the search to.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of passages to retrieve (default 6, max 12).",
                        "default": 6,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_financial_database",
            "description": (
                "Query the structured financial metadata database for precise numbers, "
                "lists, counts, and date-based lookups. Use this for: overdue invoices, "
                "upcoming due dates, expiring contracts, pending approvals, vendor lookup, "
                "document counts by category, fetching all metadata for a specific document, "
                "aggregating costs/documents by store location or branch, spend analysis by "
                "time period or cost center, legal compliance overview with obligation "
                "deadlines and risk flags, and general ledger journal entry queries by "
                "account code or posting period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "overdue_invoices",
                            "due_soon_invoices",
                            "expiring_contracts",
                            "pending_approvals",
                            "count_by_category",
                            "list_by_vendor",
                            "get_document_summary",
                            "dashboard_snapshot",
                            "aggregate_by_location",
                            "spend_by_period",
                            "spend_by_cost_center",
                            "legal_obligations",
                            "ledger_by_account",
                        ],
                        "description": (
                            "overdue_invoices: invoices past their due date. "
                            "due_soon_invoices: invoices due within N days. "
                            "expiring_contracts: contracts ending within N days. "
                            "pending_approvals: docs awaiting CFO review. "
                            "count_by_category: document counts grouped by type. "
                            "list_by_vendor: all docs from a specific vendor. "
                            "get_document_summary: full metadata for one document. "
                            "dashboard_snapshot: total KPIs in one shot including legal risk count. "
                            "aggregate_by_location: costs and contracts grouped by store/branch location — "
                            "use for store shutdown analysis. "
                            "spend_by_period: invoice/document spend aggregated by month, quarter, or year — "
                            "use for trend analysis and budget vs actuals. "
                            "spend_by_cost_center: spend grouped by cost center and department — "
                            "use for department budget tracking. "
                            "legal_obligations: all contracts with legal fields: obligations, termination "
                            "rights, penalty clauses, liability caps, and risk flags — use for compliance overview. "
                            "ledger_by_account: general ledger journal entries from uploaded ledger exports, "
                            "filterable by GL account code or posting period."
                        ),
                    },
                    "vendor_name": {
                        "type": "string",
                        "description": "Vendor/supplier name to filter by (used with list_by_vendor).",
                    },
                    "document_category": {
                        "type": "string",
                        "enum": ["invoice", "contract", "financial_report", "purchase_order", "expense_claim"],
                        "description": "Document type filter.",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Specific document ID (used with get_document_summary).",
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Lookahead window in days (for due_soon_invoices and expiring_contracts). Default 30.",
                        "default": 30,
                    },
                    "date_from": {
                        "type": "string",
                        "description": "ISO 8601 date (YYYY-MM-DD) for range start.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "ISO 8601 date (YYYY-MM-DD) for range end.",
                    },
                    "location": {
                        "type": "string",
                        "description": (
                            "Store, branch, or office location name to filter by. "
                            "Used with aggregate_by_location, legal_obligations, ledger_by_account."
                        ),
                    },
                    "period_unit": {
                        "type": "string",
                        "enum": ["month", "quarter", "year"],
                        "description": "Aggregation granularity for spend_by_period. Default 'month'.",
                        "default": "month",
                    },
                    "account_code": {
                        "type": "string",
                        "description": (
                            "GL account code prefix or account name fragment to filter ledger entries. "
                            "E.g. '6400' for all rent accounts, '5' for all revenue accounts."
                        ),
                    },
                    "posting_period": {
                        "type": "string",
                        "description": "Accounting period for ledger_by_account, e.g. '2025-02' or '2025-Q1'.",
                    },
                    "include_risk_only": {
                        "type": "boolean",
                        "description": "For legal_obligations: if true, return only documents with legal_risk_flag=true.",
                        "default": False,
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]
