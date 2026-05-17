"""OpenAI function/tool definitions for the CFO, infra-remediation, and banking compliance agents.

The LLM decides which tools to call. Each tool maps 1:1 to a handler
in RagUseCase._execute_tool.

Finance tools (session_type=finance_chat):
  - search_document_content  → vector + keyword hybrid retrieval
  - query_financial_database → structured SQL against the metadata DB

Infra remediation tools (session_type=infra_remediation):
  - list_infra_findings       → paginated infra_findings via document-service
  - get_infra_finding         → single finding detail
  - get_terraform_plan_summary → fixture-backed plan summary
  - propose_remediation        → creates agent_workflow_run + change_proposal
  - get_infra_context_bundle   → reads a stored infra_context_snapshots row

Banking compliance tools (session_type=banking_compliance):
  - search_document_content      → shared hybrid retrieval (grounding for regulatory docs)
  - query_banking_compliance     → structured AML/KYC/SAR queries against compliance DB
  - flag_transaction_for_review  → raises a governed compliance flag (HITL required)
  - generate_sar_draft           → creates a SAR-style narrative draft (HITL required)

The agentic loop in RagUseCase can call tools multiple times before
composing the final answer (ReAct pattern).
"""

from __future__ import annotations

FINANCE_TOOL_NAMES = frozenset({"search_document_content", "query_financial_database"})
INFRA_TOOL_NAMES = frozenset(
    {
        "list_infra_findings",
        "get_infra_finding",
        "get_terraform_plan_summary",
        "detect_infra_drift",
        "propose_remediation",
        "get_infra_context_bundle",
    }
)
BANKING_TOOL_NAMES = frozenset(
    {
        "search_document_content",
        "query_banking_compliance",
        "flag_transaction_for_review",
        "generate_sar_draft",
    }
)

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
                            "use for trend analysis, budget vs actuals, and VAT/tax totals. "
                            "Result includes total_amount_nok (gross), total_vat_nok (VAT only), "
                            "and total_net_nok (net ex-VAT) per period. "
                            "Always use this query_type when asked about total VAT or tax amounts. "
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
                        "description": "Lookahead window in days (for due_soon_invoices and expiring_contracts). Default 90. Use 90 unless the user explicitly specifies a shorter window.",
                        "default": 90,
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
    # ── Infra remediation tools ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_infra_findings",
            "description": (
                "List IaC / policy findings from the infra_findings table. "
                "Use to enumerate open policy violations before proposing remediations. "
                "Supports optional severity filter (HIGH / MEDIUM / LOW / CRITICAL) and pagination."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW", "CRITICAL", "INFORMATIONAL"],
                        "description": "Filter by severity level. Omit to return all severities.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of findings to return (default 20, max 50).",
                        "default": 20,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                        "default": 0,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_infra_finding",
            "description": (
                "Retrieve the full detail (including detail_json) for a single infra finding by ID. "
                "Use after list_infra_findings to get remediation_hint and scanner metadata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "finding_id": {
                        "type": "string",
                        "description": "UUID of the infra finding.",
                    },
                },
                "required": ["finding_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_terraform_plan_summary",
            "description": (
                "Return a structured summary of the most recent Terraform plan, "
                "including resource change counts (create/update/delete/no-op), "
                "the list of resources being modified with changed attributes, "
                "and any detected security risks. "
                "Resolves from: (1) TERRAFORM_PLAN_PATH env var (local tfplan.json), "
                "(2) Terraform Cloud API via TFC_TOKEN + TFC_WORKSPACE_ID, "
                "(3) fixture file as fallback — source field indicates which was used."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_infra_drift",
            "description": (
                "Detect infrastructure drift by analysing the current Terraform plan "
                "or comparing two stored infra context snapshots. "
                "Returns a list of drifted resources with severity (CRITICAL/HIGH/MEDIUM/LOW), "
                "changed attributes, security risk flags, and a recommendation. "
                "Use this when the user asks about drift, unexpected changes, state mismatches, "
                "or wants to know what has changed since a baseline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "snapshot_id_baseline": {
                        "type": "string",
                        "description": (
                            "UUID of the baseline infra_context_snapshot to compare from. "
                            "If omitted, the current Terraform plan is used instead."
                        ),
                    },
                    "snapshot_id_current": {
                        "type": "string",
                        "description": (
                            "UUID of the current infra_context_snapshot to compare to. "
                            "Required when snapshot_id_baseline is provided."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remediation",
            "description": (
                "Create a governed change proposal for a specific finding. "
                "This creates an agent_workflow_run and attaches a change_proposal with "
                "a unified diff, rationale, and resource addresses. "
                "The proposal starts in 'proposing' state and requires human approval. "
                "NEVER call this tool to apply Terraform — it only creates a proposal record."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "finding_id": {
                        "type": "string",
                        "description": "UUID of the infra finding being remediated.",
                    },
                    "unified_diff": {
                        "type": "string",
                        "description": (
                            "A valid unified diff (---/+++ lines) showing the Terraform change. "
                            "Must start with ---, diff, @@, or +."
                        ),
                    },
                    "rationale_md": {
                        "type": "string",
                        "description": "Markdown explanation of why this change fixes the finding.",
                    },
                    "resource_addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Terraform resource addresses affected (e.g. azurerm_key_vault.main).",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Estimated risk of applying this change.",
                        "default": "medium",
                    },
                },
                "required": ["finding_id", "unified_diff", "rationale_md", "resource_addresses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_infra_context_bundle",
            "description": (
                "Retrieve a previously frozen infra context snapshot by its ID. "
                "The bundle contains findings, pipeline run, and terraform plan summary "
                "at the time the snapshot was created. Use to ground answers in a specific "
                "point-in-time state rather than live queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "snapshot_id": {
                        "type": "string",
                        "description": "UUID of the infra_context_snapshots row.",
                    },
                },
                "required": ["snapshot_id"],
            },
        },
    },
    # ── Banking compliance tools ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "query_banking_compliance",
            "description": (
                "Query the structured AML/KYC/SAR compliance database. "
                "Use for: listing open AML flags, finding customers with expired/pending KYC, "
                "identifying transactions above Norwegian CTR reporting thresholds (NOK 100,000), "
                "retrieving PEP screening hits pending manual review, summarising portfolio risk "
                "score distribution, and checking upcoming regulatory reporting deadlines. "
                "Always use this tool before flagging a transaction or drafting a SAR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "aml_flags",
                            "kyc_pending_reviews",
                            "sar_candidates",
                            "risk_score_summary",
                            "regulatory_calendar",
                            "pep_screening_results",
                        ],
                        "description": (
                            "aml_flags: open AML compliance flags awaiting human review. "
                            "kyc_pending_reviews: customers with expired or pending KYC status. "
                            "sar_candidates: transactions above CTR threshold (NOK 100,000) "
                            "or matching structuring/velocity/layering patterns. "
                            "risk_score_summary: aggregated risk score distribution across portfolio. "
                            "regulatory_calendar: upcoming Finanstilsynet reporting deadlines. "
                            "pep_screening_results: PEP hits from latest screening run, pending review."
                        ),
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                        "description": "Filter results by minimum risk level. Omit to return all levels.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "ISO 8601 date (YYYY-MM-DD) range start for time-bounded queries.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "ISO 8601 date (YYYY-MM-DD) range end.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum records to return (default 20, max 50).",
                        "default": 20,
                    },
                },
                "required": ["query_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_transaction_for_review",
            "description": (
                "Raise a governed compliance flag on a specific transaction or customer, "
                "triggering enhanced due diligence. This writes a record to the compliance_flags "
                "table with status 'open' and returns a flag_id. "
                "A human compliance officer MUST review and approve the flag before any "
                "regulatory action (freeze, SAR filing, account closure) can be taken. "
                "NEVER use this tool to automatically trigger regulatory actions — "
                "it only creates a reviewable flag record. "
                "Always call query_banking_compliance first to gather evidence before flagging."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "ID of the transaction to flag (from sar_candidates or aml_flags results).",
                    },
                    "flag_reason": {
                        "type": "string",
                        "enum": [
                            "structuring",
                            "velocity_violation",
                            "pep_counterparty",
                            "layering_pattern",
                            "unusual_geography",
                            "kyc_mismatch",
                            "threshold_breach",
                            "other",
                        ],
                        "description": "Primary AML/compliance reason for the flag.",
                    },
                    "evidence_summary": {
                        "type": "string",
                        "description": (
                            "Plain-language summary of the evidence supporting this flag. "
                            "Must cite specific transaction IDs, amounts, dates, or document passages."
                        ),
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Estimated compliance risk level of this flag.",
                        "default": "high",
                    },
                },
                "required": ["transaction_id", "flag_reason", "evidence_summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sar_draft",
            "description": (
                "Generate a structured Suspicious Activity Report (SAR) draft narrative "
                "grounded in compliance flags and retrieved regulatory documents. "
                "This writes a draft to the sar_drafts table with status 'pending_review'. "
                "CRITICAL: This tool NEVER submits a SAR to Finanstilsynet or any regulator. "
                "The draft requires explicit human approval before it can be marked 'approved'. "
                "Only call this after flag_transaction_for_review has been called and a flag_id exists. "
                "The narrative must cite source documents and flag IDs — never fabricate transaction details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "flag_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One or more compliance flag IDs that this SAR covers.",
                    },
                    "narrative_md": {
                        "type": "string",
                        "description": (
                            "Markdown-formatted SAR narrative. Must include: "
                            "1. Subject description (transaction/customer ID only, no PII beyond what is in DB). "
                            "2. Description of suspicious activity with dates and amounts. "
                            "3. Regulatory basis (FATF recommendation, EU AMLD6 article, Norwegian AML Act section). "
                            "4. List of source evidence (flag IDs, document IDs, DB query results). "
                            "5. Recommended next action (EDD, freeze, file with Finanstilsynet). "
                            "6. Explicit statement: 'This draft requires human compliance officer approval.'"
                        ),
                    },
                    "reporting_obligation": {
                        "type": "string",
                        "enum": ["discretionary", "mandatory_ctr", "mandatory_str"],
                        "description": (
                            "discretionary: voluntary SAR based on suspicion. "
                            "mandatory_ctr: Currency Transaction Report — transactions >= NOK 100,000. "
                            "mandatory_str: Suspicious Transaction Report — mandatory under Norwegian AML Act §26."
                        ),
                        "default": "discretionary",
                    },
                },
                "required": ["flag_ids", "narrative_md"],
            },
        },
    },
]
