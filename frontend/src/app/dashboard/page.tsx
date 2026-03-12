"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  Clock,
  FileText,
  AlertTriangle,
  XCircle,
  ArrowRight,
  Upload,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { documentsApi } from "@/lib/api";
// ── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  iconBg,
  href,
  trend,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  iconBg: string;
  href?: string;
  trend?: string;
}) {
  const inner = (
    <div className="card-hover flex flex-col gap-4 p-6 h-full">
      <div className="flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${iconBg}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        {href && <ArrowRight className="h-4 w-4 text-slate-300 group-hover:text-brand-500 transition-colors" />}
      </div>
      <div>
        <p className="text-3xl font-bold text-slate-900 leading-none">{value}</p>
        <p className="text-xs font-medium text-slate-500 mt-1.5">{label}</p>
        {trend && (
          <p className="flex items-center gap-1 text-xs text-emerald-600 mt-1">
            <TrendingUp className="h-3 w-3" /> {trend}
          </p>
        )}
      </div>
    </div>
  );
  return href ? (
    <Link href={href} className="group block">
      {inner}
    </Link>
  ) : (
    inner
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => documentsApi.getDashboardStats(),
    refetchInterval: 30_000,
  });

  const { data: reviewItems } = useQuery({
    queryKey: ["review-queue-preview"],
    queryFn: () =>
      documentsApi.getReviewQueue({ review_status: "pending_review", limit: 5 }),
  });

  const v = (n: number | undefined) => (isLoading ? "—" : (n ?? 0));

  return (
    <div className="px-8 py-8 max-w-6xl space-y-10">
      {/* Page header — Nordic section-label pattern */}
      <div>
        <p className="section-label">Overview</p>
        <h1>CFO Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">
          Financial documents · Review queue · Audit trail
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <StatCard
          label="Total Documents"
          value={v(stats?.total_documents)}
          icon={FileText}
          iconBg="bg-brand-600"
          href="/documents"
        />
        <StatCard
          label="Pending Review"
          value={v(stats?.pending_review)}
          icon={Clock}
          iconBg="bg-amber-500"
          href="/review"
        />
        <StatCard
          label="Approved"
          value={v(stats?.approved)}
          icon={CheckCircle}
          iconBg="bg-emerald-500"
        />
        <StatCard
          label="Rejected"
          value={v(stats?.rejected)}
          icon={XCircle}
          iconBg="bg-rose-500"
        />
        <StatCard
          label="Auto-Processed"
          value={v(stats?.not_required)}
          icon={CheckCircle}
          iconBg="bg-slate-500"
        />
        <StatCard
          label="Failed"
          value={v(stats?.failed)}
          icon={AlertTriangle}
          iconBg="bg-slate-400"
        />
      </div>

      {/* Review queue preview */}
      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <p className="section-label">Action Required</p>
            <h2>Pending Review</h2>
          </div>
          <Link
            href="/review"
            className="flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            View all <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        {!reviewItems || reviewItems.length === 0 ? (
          <div className="card flex flex-col items-center gap-3 py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50">
              <CheckCircle className="h-6 w-6 text-emerald-500" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-700">All clear</p>
              <p className="text-sm text-slate-400 mt-0.5">No documents need review.</p>
            </div>
          </div>
        ) : (
          <div className="card overflow-hidden divide-y divide-slate-50">
            {reviewItems.map((item) => (
              <Link
                key={item.document_id}
                href={`/documents/${item.document_id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors group"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-slate-800 truncate group-hover:text-brand-700 transition-colors">
                    {item.filename}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {item.vendor_name ?? "Unknown vendor"}
                    {item.total_amount ? ` · ${item.total_amount}` : ""}
                    {item.document_category ? ` · ${item.document_category}` : ""}
                  </p>
                </div>
                <div className="ml-4 flex items-center gap-2 shrink-0">
                  {item.confidence_score !== null && (
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        (item.confidence_score ?? 0) < 0.7
                          ? "bg-amber-100 text-amber-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {Math.round((item.confidence_score ?? 0) * 100)}% conf.
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-100 text-amber-700">
                    <Clock className="h-3 w-3" /> Review
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Quick actions */}
      <section>
        <p className="section-label">Quick Actions</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          {[
            { href: "/upload", label: "Upload Document", sub: "PDF, DOCX, XLSX…", icon: Upload, color: "bg-brand-50 text-brand-600" },
            { href: "/review", label: "Review Queue", sub: `${v(stats?.pending_review)} pending`, icon: Clock, color: "bg-amber-50 text-amber-600" },
            { href: "/search", label: "Search Docs", sub: "Full-text & semantic", icon: FileText, color: "bg-purple-50 text-purple-600" },
            { href: "/chat", label: "AI Assistant", sub: "Ask anything", icon: AlertTriangle, color: "bg-emerald-50 text-emerald-600" },
          ].map(({ href, label, sub, icon: Icon, color }) => (
            <Link
              key={href}
              href={href}
              className="card-hover flex items-start gap-3 px-5 py-4 group"
            >
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${color}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800 group-hover:text-brand-700 transition-colors">
                  {label}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{sub}</p>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
