"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { documentsApi, type ReviewItem, type ReviewStatus } from "@/lib/api";

const STATUS_TABS: { label: string; value: ReviewStatus }[] = [
  { label: "Pending Review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
];

const PAGE_SIZE = 20;

function ConfidenceBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  const color =
    score < 0.5
      ? "bg-rose-100 text-rose-700"
      : score < 0.7
        ? "bg-amber-100 text-amber-700"
        : "bg-emerald-100 text-emerald-700";
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
      {pct}% confidence
    </span>
  );
}

export default function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ReviewStatus>("pending_review");
  const [offset, setOffset] = useState(0);
  // Track which document is being actioned and what decision is in-flight
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["review-queue", activeTab, offset],
    queryFn: () =>
      documentsApi.getReviewQueue({
        review_status: activeTab,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approved" | "rejected" }) =>
      documentsApi.submitReview(id, decision),
    onMutate: ({ id }) => {
      setPendingId(id);
      setError(null);
    },
    onSuccess: () => {
      setPendingId(null);
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: (err: unknown) => {
      setPendingId(null);
      const msg = err instanceof Error ? err.message : "Request failed. Please try again.";
      setError(msg);
    },
  });

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Review Queue</h1>
            <p className="text-slate-500 text-sm mt-0.5">
              Documents flagged for CFO review — low confidence or high-value approvals
            </p>
          </div>
          <Link href="/dashboard" className="text-sm text-brand-600 hover:underline">
            ← Dashboard
          </Link>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-white rounded-xl border p-1 w-fit shadow-sm">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => { setActiveTab(tab.value); setOffset(0); setError(null); }}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.value
                  ? "bg-brand-500 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Error banner */}
        {error && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700 flex items-center justify-between">
            <span>⚠ {error}</span>
            <button onClick={() => setError(null)} className="ml-4 text-rose-400 hover:text-rose-700 font-bold">✕</button>
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-2xl border shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="py-16 text-center text-slate-400 animate-pulse">
              Loading...
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <CheckCircle className="h-10 w-10 mx-auto mb-2 text-emerald-400" />
              <p className="font-medium">No documents in this category.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left px-5 py-3 text-slate-500 font-medium">Document</th>
                  <th className="text-left px-4 py-3 text-slate-500 font-medium">Vendor</th>
                  <th className="text-left px-4 py-3 text-slate-500 font-medium">Amount</th>
                  <th className="text-left px-4 py-3 text-slate-500 font-medium">Confidence</th>
                  <th className="text-left px-4 py-3 text-slate-500 font-medium">Category</th>
                  {activeTab === "pending_review" && (
                    <th className="text-right px-5 py-3 text-slate-500 font-medium">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((item: ReviewItem) => {
                  const isThisRowPending = pendingId === item.document_id;
                  const anyPending = pendingId !== null;
                  return (
                    <tr key={item.document_id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-3">
                        <Link
                          href={`/documents/${item.document_id}`}
                          className="font-medium text-brand-600 hover:underline truncate max-w-xs block"
                        >
                          {item.filename}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {item.vendor_name ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-700 font-medium">
                        {item.total_amount ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <ConfidenceBadge score={item.confidence_score} />
                      </td>
                      <td className="px-4 py-3 text-slate-500 capitalize">
                        {item.document_category ?? "—"}
                      </td>
                      {activeTab === "pending_review" && (
                        <td className="px-5 py-3 text-right">
                          {isThisRowPending ? (
                            <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…
                            </span>
                          ) : (
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() =>
                                  reviewMutation.mutate({ id: item.document_id, decision: "approved" })
                                }
                                disabled={anyPending}
                                className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1 text-xs font-semibold transition-colors"
                              >
                                <CheckCircle className="h-3.5 w-3.5" /> Approve
                              </button>
                              <button
                                onClick={() =>
                                  reviewMutation.mutate({ id: item.document_id, decision: "rejected" })
                                }
                                disabled={anyPending}
                                className="inline-flex items-center gap-1 rounded-lg bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1 text-xs font-semibold transition-colors"
                              >
                                <XCircle className="h-3.5 w-3.5" /> Reject
                              </button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {items.length === PAGE_SIZE && (
          <div className="flex items-center justify-end gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              className="p-2 rounded-lg border disabled:opacity-40 hover:bg-slate-100"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm text-slate-600 px-2">
              Page {Math.floor(offset / PAGE_SIZE) + 1}
            </span>
            <button
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              className="p-2 rounded-lg border hover:bg-slate-100"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
