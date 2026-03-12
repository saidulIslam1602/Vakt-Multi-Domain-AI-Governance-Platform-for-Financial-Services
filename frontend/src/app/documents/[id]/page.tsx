"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { documentsApi, type ExtractionResult, type HistoryEntry } from "@/lib/api";
import { StatusBadge } from "@/components/documents/status-badge";
import { SourceBadge } from "@/components/documents/source-badge";
import { ChatPanel } from "@/components/chat/chat-panel";
import { format } from "date-fns";
import { useState } from "react";
import {
  Save,
  Trash2,
  Loader2,
  ArrowLeft,
  Download,
  History,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileText,
  Building2,
  CreditCard,
  ScrollText,
  Tag,
} from "lucide-react";
import Link from "next/link";

// ── Helpers ────────────────────────────────────────────────────────────────

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    score < 0.5
      ? "bg-rose-100 text-rose-700"
      : score < 0.7
        ? "bg-amber-100 text-amber-700"
        : "bg-emerald-100 text-emerald-700";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      {pct}% confidence
    </span>
  );
}

function ReviewBadge({ status }: { status: string | undefined }) {
  if (!status || status === "not_required") return null;
  const map: Record<string, { label: string; icon: typeof Clock; color: string }> = {
    pending_review: { label: "Needs Review", icon: Clock, color: "bg-amber-100 text-amber-700" },
    approved: { label: "Approved", icon: CheckCircle, color: "bg-emerald-100 text-emerald-700" },
    rejected: { label: "Rejected", icon: XCircle, color: "bg-rose-100 text-rose-700" },
  };
  const cfg = map[status];
  if (!cfg) return null;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.color}`}>
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

// ── Field row ──────────────────────────────────────────────────────────────

function FieldRow({ label, value, highlight }: { label: string; value: string | undefined | null; highlight?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline justify-between py-2 border-b border-slate-50 last:border-0">
      <span className="text-xs text-slate-400 font-medium w-36 shrink-0">{label}</span>
      <span className={`text-sm text-right ml-4 ${highlight ? "font-bold text-slate-900" : "text-slate-700"}`}>
        {value}
      </span>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────────────────

function SectionCard({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
}: {
  icon: typeof FileText;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const hasContent = !!children;
  if (!hasContent) return null;
  return (
    <div className="rounded-xl border border-slate-100 bg-white shadow-sm overflow-hidden">
      <button
        className="flex items-center justify-between w-full px-5 py-3.5 bg-slate-50 hover:bg-slate-100 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2.5">
          <Icon className="h-4 w-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-700">{title}</span>
        </div>
        {open
          ? <ChevronUp className="h-4 w-4 text-slate-400" />
          : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>
      {open && <div className="px-5 py-3">{children}</div>}
    </div>
  );
}

// ── CFO Finance panel (redesigned) ────────────────────────────────────────

function CfoFinancePanel({
  ext,
  onChange,
}: {
  ext: Partial<ExtractionResult>;
  onChange: (key: keyof ExtractionResult, value: string) => void;
}) {
  const hasInvoice = ext.invoice_number || ext.invoice_date || ext.due_date
    || ext.total_amount || ext.net_amount || ext.vat_amount || ext.vat_rate || ext.currency;
  const hasVendor = ext.vendor_name || ext.vendor_org_number || ext.vendor_address
    || ext.vendor_iban || ext.buyer_name;
  const hasPayment = ext.payment_terms || ext.bank_account || ext.reference_number;
  const hasContract = ext.contract_value || ext.contract_start_date
    || ext.contract_end_date || ext.renewal_clause;
  const hasGL = ext.cost_center || ext.gl_account;

  if (!hasInvoice && !hasVendor && !hasPayment && !hasContract && !hasGL) return null;

  return (
    <div className="space-y-3">
      {/* Approval banner */}
      {ext.approval_required && (
        <div className="flex items-center gap-2.5 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
          <p className="text-sm font-semibold text-amber-800">
            Approval required — high-value or unusual terms
          </p>
        </div>
      )}

      {/* Invoice / Amounts */}
      {hasInvoice && (
        <SectionCard icon={FileText} title="Invoice & Amounts">
          {/* Key amounts highlighted at top */}
          {(ext.total_amount || ext.net_amount) && (
            <div className="flex gap-4 mb-4 pt-1">
              {ext.total_amount && (
                <div className="flex-1 rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                  <p className="text-xs text-slate-400 mb-0.5">Total Amount</p>
                  <p className="text-xl font-bold text-slate-900">{ext.total_amount}</p>
                  {ext.currency && <p className="text-xs text-slate-400 mt-0.5">{ext.currency}</p>}
                </div>
              )}
              {ext.vat_amount && (
                <div className="flex-1 rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                  <p className="text-xs text-slate-400 mb-0.5">VAT ({ext.vat_rate ?? ""})</p>
                  <p className="text-xl font-bold text-slate-900">{ext.vat_amount}</p>
                </div>
              )}
              {ext.net_amount && (
                <div className="flex-1 rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                  <p className="text-xs text-slate-400 mb-0.5">Net Amount</p>
                  <p className="text-xl font-bold text-slate-900">{ext.net_amount}</p>
                </div>
              )}
            </div>
          )}
          <FieldRow label="Invoice #" value={ext.invoice_number} />
          <FieldRow label="Invoice Date" value={ext.invoice_date} />
          <FieldRow
            label="Due Date"
            value={ext.due_date}
            highlight={!!ext.due_date && new Date(ext.due_date) < new Date()}
          />
          <FieldRow label="Document Category" value={ext.document_category} />
        </SectionCard>
      )}

      {/* Vendor / Parties */}
      {hasVendor && (
        <SectionCard icon={Building2} title="Vendor & Parties">
          <FieldRow label="Vendor" value={ext.vendor_name} highlight />
          <FieldRow label="Org Number" value={ext.vendor_org_number} />
          <FieldRow label="Address" value={ext.vendor_address} />
          <FieldRow label="IBAN" value={ext.vendor_iban} />
          <FieldRow label="Buyer" value={ext.buyer_name} />
        </SectionCard>
      )}

      {/* Payment */}
      {hasPayment && (
        <SectionCard icon={CreditCard} title="Payment Details">
          <FieldRow label="Payment Terms" value={ext.payment_terms} />
          <FieldRow label="Bank Account" value={ext.bank_account} />
          <FieldRow label="Reference / KID" value={ext.reference_number} />
        </SectionCard>
      )}

      {/* Contract */}
      {hasContract && (
        <SectionCard icon={ScrollText} title="Contract">
          <FieldRow label="Contract Value" value={ext.contract_value} highlight />
          <FieldRow label="Start Date" value={ext.contract_start_date} />
          <FieldRow label="End Date" value={ext.contract_end_date} />
          <FieldRow label="Renewal Clause" value={ext.renewal_clause} />
        </SectionCard>
      )}

      {/* GL / Cost center */}
      {hasGL && (
        <SectionCard icon={Tag} title="Accounting">
          <FieldRow label="Cost Center" value={ext.cost_center} />
          <FieldRow label="GL Account" value={ext.gl_account} />
        </SectionCard>
      )}
    </div>
  );
}

// ── Raw extraction accordion ───────────────────────────────────────────────

function FinancialReportPanel({
  ext,
}: {
  ext: Partial<ExtractionResult>;
}) {
  const hasReport = ext.report_period || ext.report_type || ext.total_revenue
    || ext.total_expenses || ext.ebitda || ext.net_profit;
  const hasLedger = ext.ledger_entries && ext.ledger_entries.length > 0;
  const hasLineItems = ext.report_line_items && ext.report_line_items.length > 0;

  if (!hasReport && !hasLedger && !hasLineItems) return null;

  return (
    <SectionCard icon={Tag} title="Financial Report">
      {hasReport && (
        <div className="space-y-0 mb-4">
          <FieldRow label="Report Type" value={ext.report_type} />
          <FieldRow label="Period" value={ext.report_period} highlight />
          <FieldRow label="Total Revenue" value={ext.total_revenue} highlight />
          <FieldRow label="Total Expenses" value={ext.total_expenses} />
          <FieldRow label="EBITDA" value={ext.ebitda} />
          <FieldRow label="Net Profit" value={ext.net_profit} highlight />
          <FieldRow label="Posting Period" value={ext.posting_period} />
          <FieldRow label="Journal Ref" value={ext.journal_ref} />
          <FieldRow label="Department" value={ext.department} />
          <FieldRow label="Store / Location" value={ext.store_location} />
        </div>
      )}
      {hasLineItems && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Line Items ({ext.report_line_items!.length})
          </p>
          <div className="overflow-x-auto rounded-lg border border-slate-100">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-400 uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2 text-left">Account</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                  <th className="px-3 py-2 text-left">Period</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {ext.report_line_items!.map((item, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-700">{item.account}</td>
                    <td className="px-3 py-2 text-right font-medium text-slate-900">{item.amount}</td>
                    <td className="px-3 py-2 text-slate-400">{item.period ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {hasLedger && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Ledger Entries ({ext.ledger_entries!.length})
          </p>
          <div className="overflow-x-auto rounded-lg border border-slate-100">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-400 uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-left">Account</th>
                  <th className="px-3 py-2 text-right">Debit</th>
                  <th className="px-3 py-2 text-right">Credit</th>
                  <th className="px-3 py-2 text-left">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {ext.ledger_entries!.map((e, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{e.date}</td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{e.account_code} {e.account_name}</td>
                    <td className="px-3 py-2 text-right text-emerald-700 font-medium whitespace-nowrap">{e.debit ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-rose-600 font-medium whitespace-nowrap">{e.credit ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-500 max-w-xs truncate">{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

// ── Raw extraction accordion ───────────────────────────────────────────────

function RawExtractionPanel({
  ext,
  onChange,
}: {
  ext: Partial<ExtractionResult>;
  onSetDirty?: () => void;
  onChange: (key: keyof ExtractionResult, value: string | string[]) => void;
}) {
  return (
    <SectionCard icon={History} title="Raw Extraction Data" defaultOpen={true}>
      <p className="text-xs text-slate-400 mb-4">
        Raw arrays extracted by the AI — edit chips to correct mistakes before saving.
      </p>
      <div className="space-y-5">
        <ExtractionField
          label="Summary"
          value={ext.summary ?? ""}
          multiline
          onChange={(v) => onChange("summary", v)}
        />
        <ExtractionListField
          label="Parties"
          values={ext.parties ?? []}
          onChange={(v) => onChange("parties", v)}
        />
        <ExtractionListField
          label="Dates"
          values={ext.dates ?? []}
          onChange={(v) => onChange("dates", v)}
        />
        <ExtractionListField
          label="Amounts"
          values={ext.amounts ?? []}
          onChange={(v) => onChange("amounts", v)}
        />
        <ExtractionListField
          label="Key Terms"
          values={ext.key_terms ?? []}
          onChange={(v) => onChange("key_terms", v)}
        />
      </div>
    </SectionCard>
  );
}

// ── History panel ──────────────────────────────────────────────────────────

function HistoryPanel({ documentId }: { documentId: string }) {
  const [open, setOpen] = useState(false);

  const { data: history = [], isLoading } = useQuery({
    queryKey: ["document-history", documentId],
    queryFn: () => documentsApi.getHistory(documentId),
    enabled: open,
  });

  return (
    <div className="card p-6">
      <button
        className="flex items-center justify-between w-full"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-slate-400" />
          <h2 className="text-slate-800">Extraction History</h2>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>
      {open && (
        <div className="mt-4 space-y-3">
          {isLoading ? (
            <div className="text-sm text-slate-400 animate-pulse">Loading history…</div>
          ) : history.length === 0 ? (
            <p className="text-sm text-slate-400">No history recorded yet.</p>
          ) : (
            history.map((entry: HistoryEntry) => (
              <div
                key={entry.history_id}
                className="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 text-xs space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-700">{entry.changed_by}</span>
                  <span className="text-slate-400">
                    {format(new Date(entry.changed_at), "dd MMM yyyy HH:mm")}
                  </span>
                </div>
                {entry.change_reason && (
                  <p className="text-slate-500 italic">"{entry.change_reason}"</p>
                )}
                {typeof entry.extraction?.confidence_score === "number" && (
                  <ConfidenceBadge score={entry.extraction.confidence_score} />
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Download button ────────────────────────────────────────────────────────

function DownloadButton({ documentId }: { documentId: string }) {
  const downloadMutation = useMutation({
    mutationFn: () => documentsApi.getDownloadUrl(documentId),
    onSuccess: (data) => {
      const a = document.createElement("a");
      a.href = data.url;
      a.download = data.filename;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.click();
    },
  });

  return (
    <button
      onClick={() => downloadMutation.mutate()}
      disabled={downloadMutation.isPending}
      className="btn-secondary flex items-center gap-1.5"
      title="Download original document"
    >
      {downloadMutation.isPending ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        <Download size={14} />
      )}
      Download
    </button>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: doc, isLoading } = useQuery({
    queryKey: ["document", id],
    queryFn: () => documentsApi.get(id),
    refetchInterval: (q) =>
      q.state.data && ["ready", "failed"].includes(q.state.data.status) ? false : 5000,
  });

  const [extraction, setExtraction] = useState<Partial<ExtractionResult>>({});
  const [dirty, setDirty] = useState(false);

  const saveMutation = useMutation({
    mutationFn: () => documentsApi.updateExtraction(id, extraction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", id] });
      setDirty(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => documentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      router.push("/documents");
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-brand-500" size={24} />
      </div>
    );
  }

  if (!doc) return null;

  const ext = { ...doc.extraction, ...extraction };

  return (
    <div className="flex h-screen">
      {/* Main panel */}
      <div className="flex-1 overflow-y-auto px-8 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start gap-3">
          <Link href="/documents" className="text-gray-400 hover:text-gray-700 transition-colors mt-1">
            <ArrowLeft size={18} />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="truncate">{doc.filename}</h1>
              <StatusBadge status={doc.status} />
              <SourceBadge source={(doc as any).ingest_source} />
              <ReviewBadge status={(doc as any).review_status} />
              {ext.confidence_score !== undefined && (
                <ConfidenceBadge score={ext.confidence_score} />
              )}
            </div>
            <p className="text-sm text-gray-400 mt-0.5">
              {doc.page_count ? `${doc.page_count} pages · ` : ""}
              {doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(0)} KB · ` : ""}
              Uploaded {format(new Date(doc.uploaded_at), "dd MMM yyyy")}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <DownloadButton documentId={id} />
            {dirty && (
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="btn-primary flex items-center gap-1.5"
              >
                {saveMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                Save
              </button>
            )}
            <button
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="btn-secondary text-red-600 border-red-100 hover:bg-red-50"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {doc.error_message && (
          <div className="rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
            {doc.error_message}
          </div>
        )}

        {/* CFO Financial Details */}
        {ext && (
          <CfoFinancePanel
            ext={ext}
            onChange={(key, value) => {
              setExtraction((p) => ({ ...p, [key]: value }));
              setDirty(true);
            }}
          />
        )}

        {/* Financial Report / Payroll / Ledger details */}
        {ext && <FinancialReportPanel ext={ext} />}

        {/* Raw extraction data */}
        {ext && (
          <RawExtractionPanel
            ext={ext}
            onChange={(key, value) => {
              setExtraction((p) => ({ ...p, [key]: value }));
              setDirty(true);
            }}
          />
        )}

        {/* Audit history */}
        <HistoryPanel documentId={id} />
      </div>

      {/* Chat side panel */}
      <div className="w-96 border-l border-gray-100 flex flex-col bg-gray-50">
        <div className="px-4 py-4 border-b border-gray-100 bg-white">
          <h3>Chat with document</h3>
          <p className="text-xs text-gray-400 mt-0.5">Ask questions about this document</p>
        </div>
        <div className="flex-1 overflow-hidden">
          <ChatPanel documentIds={[id]} />
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function ExtractionField({
  label,
  value,
  multiline,
  onChange,
}: {
  label: string;
  value: string;
  multiline?: boolean;
  onChange: (_v: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
        {label}
      </label>
      {multiline ? (
        <textarea
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
          rows={4}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

function ExtractionListField({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (_v: string[]) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
        {label}
      </label>
      <div className="flex flex-wrap gap-2">
        {values.map((v, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-700"
          >
            {v}
            <button
              className="text-gray-400 hover:text-red-500"
              onClick={() => onChange(values.filter((_, j) => j !== i))}
            >
              ×
            </button>
          </span>
        ))}
        <button
          className="rounded-full border border-dashed border-gray-300 px-2.5 py-1 text-xs text-gray-400 hover:border-brand-400 hover:text-brand-600"
          onClick={() => {
            const val = prompt(`Add ${label.toLowerCase()}`);
            if (val?.trim()) onChange([...values, val.trim()]);
          }}
        >
          + Add
        </button>
      </div>
    </div>
  );
}
