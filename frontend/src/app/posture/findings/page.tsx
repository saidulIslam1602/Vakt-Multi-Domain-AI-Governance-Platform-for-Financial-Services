"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, Loader2, X, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import {
  postureApi,
  type InfraFindingDetail,
  type InfraFindingListItem,
} from "@/lib/api";

const PAGE_SIZE = 20;

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity.toUpperCase();
  const color =
    s === "CRITICAL" || s === "HIGH"
      ? "bg-rose-100 text-rose-800"
      : s === "MEDIUM"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>{severity}</span>
  );
}

export default function InfraFindingsPage() {
  const [severityFilter, setSeverityFilter] = useState<string | undefined>(undefined);
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["infra-findings", severityFilter, offset],
    queryFn: () =>
      postureApi.listFindings({
        severity: severityFilter,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  const { data: detail } = useQuery({
    queryKey: ["infra-finding", selectedId],
    queryFn: () => postureApi.getFinding(selectedId!),
    enabled: !!selectedId,
  });

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <ShieldAlert className="h-7 w-7 text-brand-600" />
              Infrastructure findings
            </h1>
            <p className="text-slate-500 text-sm mt-0.5">
              IaC policy signals — aligned with CI scanners (Checkov). Fixtures seeded locally for demos.
            </p>
          </div>
          <Link href="/dashboard" className="text-sm text-brand-600 hover:underline">
            ← Dashboard
          </Link>
        </div>

        <div className="flex flex-wrap gap-1 bg-white rounded-xl border p-1 w-fit shadow-sm">
          {[
            { label: "All", value: undefined as string | undefined },
            { label: "High", value: "HIGH" },
            { label: "Medium", value: "MEDIUM" },
            { label: "Low", value: "LOW" },
          ].map((tab) => (
            <button
              key={tab.label}
              type="button"
              onClick={() => {
                setSeverityFilter(tab.value);
                setOffset(0);
              }}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                severityFilter === tab.value
                  ? "bg-brand-500 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="flex justify-center py-16 text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-slate-500 text-sm">
              No findings for this tenant. Run Postgres migrations (includes demo seeds for{" "}
              <code className="text-xs bg-slate-100 px-1 rounded">dev-tenant</code>).
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((row: InfraFindingListItem) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(row.id)}
                    className="w-full text-left px-5 py-4 hover:bg-slate-50 transition-colors flex items-start gap-4"
                  >
                    <SeverityBadge severity={row.severity} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-slate-900">{row.title}</p>
                      <p className="text-xs text-slate-500 mt-1 font-mono">{row.rule_id}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {[row.file_path, row.line_start != null ? `:${row.line_start}` : null]
                          .filter(Boolean)
                          .join("")}
                        {row.policy_pack_ref ? ` · ${row.policy_pack_ref}` : ""}
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex justify-between items-center text-sm text-slate-500">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" /> Previous
          </button>
          <span>Showing {items.length} (page offset {offset})</span>
          <button
            type="button"
            disabled={items.length < PAGE_SIZE}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            Next <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {selectedId && (
        <FindingDrawer finding={detail} onClose={() => setSelectedId(null)} />
      )}
    </main>
  );
}

function FindingDrawer({
  finding,
  onClose,
}: {
  finding: InfraFindingDetail | undefined;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30">
      <button type="button" className="flex-1 cursor-default" aria-label="Close" onClick={onClose} />
      <aside className="w-full max-w-lg bg-white shadow-xl h-full overflow-y-auto border-l border-slate-200">
        <div className="sticky top-0 bg-white border-b border-slate-100 px-5 py-4 flex justify-between items-center">
          <h2 className="font-semibold text-slate-900">Finding detail</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5 space-y-4 text-sm">
          {!finding ? (
            <div className="flex justify-center py-12 text-slate-400">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <SeverityBadge severity={finding.severity} />
                <span className="font-mono text-xs text-slate-500">{finding.rule_id}</span>
              </div>
              <h3 className="text-base font-semibold text-slate-900">{finding.title}</h3>
              <dl className="space-y-2 text-slate-600">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-400">Location</dt>
                  <dd className="font-mono text-xs mt-0.5">
                    {finding.file_path ?? "—"}
                    {finding.line_start != null ? `:${finding.line_start}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-400">Policy pack</dt>
                  <dd>{finding.policy_pack_ref ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-400">Remediation</dt>
                  <dd className="text-slate-700">{finding.remediation_hint ?? "—"}</dd>
                </div>
              </dl>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400 mb-2">
                  Scanner metadata (JSON)
                </p>
                <pre className="text-xs bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto">
                  {JSON.stringify(finding.detail_json, null, 2)}
                </pre>
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
