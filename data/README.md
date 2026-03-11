# Allergo Nordic — Sample Test Data

This folder contains **6 realistic sample documents** for testing the full platform feature set.
All documents are Norwegian-context business documents that exercise different extraction paths,
alert triggers, and chat queries.

---

## 📁 Folder Structure

```
data/
├── invoices/
│   ├── invoice_telenor_2026_01.txt            Standard telecom invoice
│   ├── invoice_nordiccloud_high_value.txt     High-value IT consulting invoice
│   └── invoice_overdue_bergen_renhold.txt     100-day overdue facility invoice
├── contracts/
│   ├── contract_visma_erp_license.txt         ERP software license (expiring soon)
│   └── contract_office_lease_oslo.txt         Office lease (legal risk flags)
├── reports/
│   └── financial_report_q1_2026.txt           Q1 2026 income statement
├── ledger/
│   ├── ledger_january_2026.txt                General ledger — Jan 2026 (17 journal entries)
│   ├── ledger_february_2026.txt               General ledger — Feb 2026 (19 journal entries)
│   ├── accounts_payable_q1_2026.txt           AP subledger — 7 vendors, ageing analysis
│   └── accounts_receivable_q1_2026.txt        AR subledger — 5 customers, DSO, ageing
└── bulk_upload_sample.zip                     All 10 docs zipped for bulk upload test
```

---

## 🧪 Feature Test Matrix

| File | Category | Key Extracted Fields | Features Tested |
|---|---|---|---|
| `invoice_telenor_2026_01.txt` | `invoice` | vendor, amount NOK 15 072.50, KID, due date, GL 6800 | Upload, parse, search, chat |
| `invoice_nordiccloud_high_value.txt` | `invoice` | NOK 603 750 total, `approval_required=true`, GL 7300 | **Review queue** (high-confidence + >100k), **alert: amount threshold** |
| `invoice_overdue_bergen_renhold.txt` | `invoice` | due_date 2025-12-01, 100 days overdue, penalty clause | **Alert: invoice_overdue**, review queue |
| `contract_visma_erp_license.txt` | `contract` | contract_end_date 2026-04-15, renewal clause, force_majeure, indemnity | **Alert: contract_expiring** (35 days), renewal risk |
| `contract_office_lease_oslo.txt` | `contract` | contract_end_date 2029-06-30, `legal_risk_flag=true`, penalty NOK 930k | **Alert: legal_risk**, legal clause analysis |
| `financial_report_q1_2026.txt` | `financial_report` | EBITDA NOK 2.3M, net_profit NOK 1.623M, 14 line items, Q1 2026 | **Analytics charts**, CFO chat queries |
| `ledger_january_2026.txt` | `financial_report` | 17 journal entries, bilag B0101–B0117, Jan posting period, opening balances | **Ledger entries** extraction, chat: "journal entries" |
| `ledger_february_2026.txt` | `financial_report` | 19 journal entries, B0201–B0219, VAT settlement, interest expense | **Ledger entries**, multi-month comparison |
| `accounts_payable_q1_2026.txt` | `financial_report` | 7 vendors, ageing analysis, NOK 1.245M total AP, overdue flagged | **AP queries**, overdue vendor detection |
| `accounts_receivable_q1_2026.txt` | `financial_report` | 5 enterprise customers, DSO 24.3 days, NOK 1.823M AR, 94.2% collection | **AR queries**, revenue recognition, DSO |

---

## 🚀 How to Test Each Feature

### 1. Single File Upload
→ Go to **Upload** page → drop any `.txt` file from this folder
→ Watch status change: `uploaded → parsing → parsed → extracting → extracted → indexing → ready`
→ Takes ~20-40 seconds per file

### 2. Bulk ZIP Upload
→ Go to **Upload** page → ZIP section → drop `bulk_upload_sample.zip`
→ All 6 docs queued at once; per-file status report shown

### 3. Review Queue
→ Go to **Review Queue** after uploading `invoice_nordiccloud_high_value.txt`
→ Should appear with `pending_review` status (amount > NOK 100k triggers this)
→ Try **Approve** or **Reject** with a reason

### 4. Analytics Charts
→ Go to **Analytics** after uploading the financial report and invoices
→ "Document Volume by Month" bar chart should populate
→ "Top Vendor Concentration" pie chart shows Telenor, NordicCloud, Bergen Renhold, Visma
→ "Upcoming Contract Expiries" table shows Visma (expiring 2026-04-15)

### 5. Alerts
→ Go to **Alerts** → create these rules to test triggering:

| Alert Rule | Trigger Type | Threshold |
|---|---|---|
| High-value invoice | `invoice_amount_threshold` | Threshold: 100000 |
| Overdue invoices | `invoice_overdue` | Days: 30 |
| Contract expiring soon | `contract_expiring` | Days before: 60 |
| Legal risk flag | `legal_risk` | — |

### 6. AI Assistant (Chat) — Suggested Test Questions

**Invoice queries:**
- *"Which invoices are overdue?"*
- *"Show me all invoices from NordicCloud"*
- *"What is the total amount due to our vendors this month?"*
- *"Which invoices require CFO approval?"*

**Contract queries:**
- *"Which contracts are expiring in the next 90 days?"*
- *"What are the termination terms in the Visma contract?"*
- *"Summarise all legal risks in our contracts"*
- *"What is the penalty if we exit the Oslo office lease early?"*

**Financial analysis:**
- *"What was our EBITDA in Q1 2026?"*
- *"What were our top 3 cost drivers in Q1 2026?"*
- *"How did revenue grow compared to Q1 2025?"*
- *"What is our net profit margin for Q1 2026?"*

**Cross-document:**
- *"Give me a CFO summary of all documents"*
- *"What are the biggest financial risks facing Allergo Nordic?"*

### 7. Search
→ Go to **Search**
→ Try: `"KID"`, `"force majeure"`, `"EBITDA"`, `"Bergen"`, `"NordicCloud"`

### 8. CSV Export
→ Go to **Documents** → click **Export CSV**
→ Downloads all document metadata with extraction fields

### 9. Document Detail
→ Click any document in the Documents list
→ See full extracted fields, edit individual values, view audit trail

---

## 📌 Notes

- Documents are `.txt` files — the parser handles plain text natively
- The overdue invoice date (2025-12-01) is intentionally in the past to trigger overdue alerts
- The Visma contract ends 2026-04-15 (~35 days from today) — will trigger `contract_expiring` alert
- The office lease has `legal_risk_flag = true` due to 3 non-standard clauses flagged in section 7
- The NordicCloud invoice totals NOK 603,750 which exceeds the NOK 100,000 threshold → `approval_required = true`
