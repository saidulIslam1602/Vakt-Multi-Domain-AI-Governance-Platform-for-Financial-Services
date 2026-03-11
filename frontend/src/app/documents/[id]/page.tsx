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

// ── CFO Finance fields panel ───────────────────────────────────────────────

function CfoFinancePanel({ ext }: { ext: Partial<ExtractionResult> }) {
  const [expanded, setExpanded] = useState(true);
  const fields: { label: string; key: keyof ExtractionResult }[] = [
    { label: "Category", key: "document_category" },
    { label: "Invoice #", key: "invoice_number" },
    { label: "Invoice Date", key: "invoice_date" },
    { label: "Due Date", key: "due_date" },
    { label: "Total Amount", key: "total_amount" },
    { label: "Net Amount", key: "net_amount" },
    { label: "VAT Amount", key: "vat_amount" },
    { label: "VAT Rate", key: "vat_rate" },
    { label: "Currency", key: "currency" },
    { label: "Vendor", key: "vendor_name" },
    { label: "Vendor Org #", key: "vendor_org_number" },
    { label: "Vendor IBAN", key: "vendor_iban" },
    { label: "Buyer", key: "buyer_name" },
    { label: "Payment Terms", key: "payment_terms" },
    { label: "Bank Account", key: "bank_account" },
    { label: "Reference / KID", key: "reference_number" },
    { label: "Contract Value", key: "contract_value" },
    { label: "Contract Start", key: "contract_start_date" },
    { label: "Contract End", key: "contract_end_date" },
    { label: "Renewal Clause", key: "renewal_clause" },
    { label: "Cost Center", key: "cost_center" },
    { label: "GL Account", key: "gl_account" },
  ];

  const populated = fields.filter((f) => {
    const v = ext[f.key];
    return v !== undefined && v !== null && v !== "";
  });

  if (populated.length === 0) return null;

  return (
    <div className="card p-6">
      <button
        className="flex items-center justify-between w-full mb-4"
        onClick={() => setExpanded((e) => !e)}
      >
        <h2 className="text-slate-800">Financial Details</h2>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>
      {expanded && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
          {populated.map((f) => {
            const val = ext[f.key];
            const displayVal =
              typeof val === "boolean"
                ? val
                  ? "Yes"
                  : "No"
                : String(val ?? "");
            return (
              <div key={f.key} className="flex flex-col">
                <dt className="text-xs font-medium text-slate-400 uppercase tracking-wide">
                  {f.label}
                </dt>
                <dd className="text-sm font-medium text-slate-800 mt-0.5">
                  {displayVal}
                </dd>
              </div>
            );
          })}
          {ext.approval_required && (
            <div className="col-span-2 mt-1">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-amber-50 text-amber-700 px-3 py-1.5 rounded-full border border-amber-200">
                <AlertTriangle className="h-3.5 w-3.5" />
                Approval required (high-value or unusual terms)
              </span>
            </div>
          )}
        </dl>
      )}
    </div>
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
        {ext && <CfoFinancePanel ext={ext} />}

        {/* Core extraction metadata */}
        {ext && (
          <div className="card p-6 space-y-6">
            <h2>Extracted Metadata</h2>
            <ExtractionField
              label="Summary"
              value={ext.summary ?? ""}
              multiline
              onChange={(v) => { setExtraction((p) => ({ ...p, summary: v })); setDirty(true); }}
            />
            <ExtractionListField
              label="Parties"
              values={ext.parties ?? []}
              onChange={(v) => { setExtraction((p) => ({ ...p, parties: v })); setDirty(true); }}
            />
            <ExtractionListField
              label="Dates"
              values={ext.dates ?? []}
              onChange={(v) => { setExtraction((p) => ({ ...p, dates: v })); setDirty(true); }}
            />
            <ExtractionListField
              label="Amounts"
              values={ext.amounts ?? []}
              onChange={(v) => { setExtraction((p) => ({ ...p, amounts: v })); setDirty(true); }}
            />
            <ExtractionListField
              label="Key Terms"
              values={ext.key_terms ?? []}
              onChange={(v) => { setExtraction((p) => ({ ...p, key_terms: v })); setDirty(true); }}
            />
          </div>
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
