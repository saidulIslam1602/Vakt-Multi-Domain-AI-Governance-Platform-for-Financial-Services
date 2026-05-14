"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GitPullRequest,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  proposalsApi,
  type AgentWorkflowRun,
  type WorkflowState,
} from "@/lib/api";

const PAGE_SIZE = 20;

const STATE_LABELS: Record<WorkflowState, { label: string; color: string; icon: React.ReactNode }> = {
  gathering_context: { label: "Gathering context", color: "bg-slate-100 text-slate-600", icon: <Clock className="h-3 w-3" /> },
  proposing:         { label: "Proposing",         color: "bg-blue-100 text-blue-700",   icon: <Clock className="h-3 w-3" /> },
  validating:        { label: "Validating",         color: "bg-amber-100 text-amber-700", icon: <Clock className="h-3 w-3" /> },
  pending_approval:  { label: "Pending approval",  color: "bg-yellow-100 text-yellow-800", icon: <AlertTriangle className="h-3 w-3" /> },
  approved:          { label: "Approved",           color: "bg-emerald-100 text-emerald-700", icon: <CheckCircle2 className="h-3 w-3" /> },
  rejected:          { label: "Rejected",           color: "bg-rose-100 text-rose-700",   icon: <XCircle className="h-3 w-3" /> },
  failed_validation: { label: "Failed validation", color: "bg-red-100 text-red-700",     icon: <XCircle className="h-3 w-3" /> },
  context_frozen:    { label: "Context frozen",    color: "bg-indigo-100 text-indigo-700", icon: <Clock className="h-3 w-3" /> },
};

function StateBadge({ state }: { state: WorkflowState }) {
  const cfg = STATE_LABELS[state] ?? {
    label: state,
    color: "bg-slate-100 text-slate-600",
    icon: <Clock className="h-3 w-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.color}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

export default function ProposalsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [stateFilter, setStateFilter] = useState<WorkflowState | undefined>(undefined);
  const [offset, setOffset] = useState(0);

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["posture-runs", stateFilter, offset],
    queryFn: () =>
      proposalsApi.listRuns({
        workflow_state: stateFilter,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  const createRun = useMutation({
    mutationFn: () =>
      proposalsApi.createRun({ session_type: "infra_remediation", max_tool_rounds: 6 }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["posture-runs"] });
      router.push(`/posture/proposals/${run.id}`);
    },
  });

  const filterTabs: { label: string; value: WorkflowState | undefined }[] = [
    { label: "All", value: undefined },
    { label: "Pending approval", value: "pending_approval" },
    { label: "Approved", value: "approved" },
    { label: "Rejected", value: "rejected" },
    { label: "Failed", value: "failed_validation" },
  ];

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <GitPullRequest className="h-7 w-7 text-brand-600" />
              Change proposals
            </h1>
            <p className="text-slate-500 text-sm mt-0.5">
              Agent-generated infrastructure remediation proposals — review, validate, approve, or reject.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/posture/findings" className="text-sm text-brand-600 hover:underline">
              ← Findings
            </Link>
            <button
              type="button"
              onClick={() => createRun.mutate()}
              disabled={createRun.isPending}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {createRun.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              New run
            </button>
          </div>
        </div>

        {/* State filter tabs */}
        <div className="flex flex-wrap gap-1 bg-white rounded-xl border p-1 w-fit shadow-sm">
          {filterTabs.map((tab) => (
            <button
              key={tab.label}
              type="button"
              onClick={() => {
                setStateFilter(tab.value);
                setOffset(0);
              }}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                stateFilter === tab.value
                  ? "bg-brand-500 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Runs table */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="flex justify-center py-16 text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : runs.length === 0 ? (
            <div className="py-16 text-center text-slate-500 text-sm">
              No runs found. Click{" "}
              <span className="font-medium text-brand-600">New run</span> to start a workflow.
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {runs.map((run: AgentWorkflowRun) => (
                <li key={run.id}>
                  <Link
                    href={`/posture/proposals/${run.id}`}
                    className="w-full text-left px-5 py-4 hover:bg-slate-50 transition-colors flex items-start gap-4 block"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3 flex-wrap">
                        <StateBadge state={run.workflow_state as WorkflowState} />
                        <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
                          {run.session_type}
                        </span>
                      </div>
                      <p className="font-mono text-xs text-slate-400 mt-1.5">{run.id}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Created by <span className="font-medium">{run.created_by}</span>{" "}
                        · {new Date(run.created_at).toLocaleString()}
                        {" "}· rounds {run.tool_rounds_used}/{run.max_tool_rounds}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Pagination */}
        <div className="flex justify-between items-center text-sm text-slate-500">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" /> Previous
          </button>
          <span>Showing {runs.length} runs</span>
          <button
            type="button"
            disabled={runs.length < PAGE_SIZE}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            Next <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </main>
  );
}
