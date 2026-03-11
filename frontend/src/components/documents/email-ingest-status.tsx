"use client";

import { useQuery } from "@tanstack/react-query";
import { emailIngestApi } from "@/lib/api";
import { Mail, CheckCircle, XCircle, Clock, Loader2, AlertCircle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

/**
 * Read-only status panel shown on the Upload page when the IMAP email
 * poller is configured. Polls every 60 s so the CFO always sees a
 * fresh picture without manual refresh.
 */
export function EmailIngestStatus() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["email-ingest-status"],
    queryFn: () => emailIngestApi.getStatus(),
    // Refresh every 60 s — lightweight endpoint, no heavy DB query
    refetchInterval: 60_000,
    // Don't show a hard error if the endpoint isn't deployed yet
    retry: 1,
  });

  // While loading show a subtle skeleton
  if (isLoading) {
    return (
      <div className="rounded-xl border border-slate-100 bg-white p-5 flex items-center gap-3 text-slate-400 text-sm">
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
        Checking email ingest status…
      </div>
    );
  }

  // If the endpoint doesn't exist yet (404 / network error) hide silently
  if (isError || !data) return null;

  // If the feature is explicitly disabled, show a calm notice
  if (!data.enabled) {
    return (
      <div className="rounded-xl border border-slate-100 bg-slate-50 p-5">
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Mail className="h-4 w-4 shrink-0" />
          <span>
            <span className="font-semibold">Email ingestion</span> is{" "}
            <span className="font-semibold text-slate-400">disabled</span>. Set{" "}
            <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">
              EMAIL_INGEST_ENABLED=true
            </code>{" "}
            in your environment to activate automatic email attachment ingestion.
          </span>
        </div>
      </div>
    );
  }

  const hasErrors = data.errors_today > 0;

  return (
    <div className="rounded-xl border border-violet-100 bg-violet-50 p-5 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 shadow-sm">
            <Mail className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-800">Email Ingest</p>
            <p className="text-xs text-slate-500">
              Polling <span className="font-medium">{data.imap_mailbox}</span> on{" "}
              <span className="font-medium">{data.imap_host}</span>
            </p>
          </div>
        </div>
        {/* Active indicator */}
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700">
          <CheckCircle className="h-3.5 w-3.5" />
          Active
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <StatPill
          icon={Mail}
          value={data.ingested_today}
          label="ingested today"
          color="text-violet-700"
        />
        <StatPill
          icon={Clock}
          value={
            data.last_poll_at
              ? formatDistanceToNow(new Date(data.last_poll_at), { addSuffix: true })
              : "never"
          }
          label="last poll"
          color="text-slate-600"
        />
        <StatPill
          icon={hasErrors ? AlertCircle : CheckCircle}
          value={data.errors_today}
          label="errors today"
          color={hasErrors ? "text-rose-600" : "text-emerald-600"}
        />
      </div>

      {/* Error hint */}
      {hasErrors && (
        <div className="flex items-center gap-2 rounded-lg bg-rose-50 border border-rose-100 px-3 py-2 text-xs text-rose-700">
          <XCircle className="h-3.5 w-3.5 shrink-0" />
          {data.errors_today} attachment{data.errors_today !== 1 ? "s" : ""} failed to ingest
          today. Check the ingest-service logs for details.
        </div>
      )}
    </div>
  );
}

// ── Internal helper ────────────────────────────────────────────────────────

function StatPill({
  icon: Icon,
  value,
  label,
  color,
}: {
  icon: React.ElementType;
  value: number | string;
  label: string;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg bg-white border border-slate-100 px-3 py-2 text-center">
      <Icon className={`h-4 w-4 mb-1 ${color}`} />
      <p className={`text-sm font-bold leading-none ${color}`}>{value}</p>
      <p className="text-[10px] text-slate-400 mt-0.5">{label}</p>
    </div>
  );
}
