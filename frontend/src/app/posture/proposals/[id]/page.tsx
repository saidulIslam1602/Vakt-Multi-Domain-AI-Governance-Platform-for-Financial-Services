"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GitPullRequest,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ChevronLeft,
  Download,
  Copy,
  Check,
} from "lucide-react";
import Link from "next/link";
import { use } from "react";
import {
  proposalsApi,
  type AgentWorkflowRun,
  type ChangeProposal,
  type WorkflowState,
} from "@/lib/api";

// ── State badge (same as list page) ──────────────────────────────────────────

const STATE_CFG: Record<string, { label: string; color: string }> = {
  gathering_context: { label: "Gathering context", color: "bg-slate-100 text-slate-600" },
  proposing:         { label: "Proposing",          color: "bg-blue-100 text-blue-700" },
  validating:        { label: "Validating",          color: "bg-amber-100 text-amber-700" },
  pending_approval:  { label: "Pending approval",   color: "bg-yellow-100 text-yellow-800" },
  approved:          { label: "Approved",            color: "bg-emerald-100 text-emerald-700" },
  rejected:          { label: "Rejected",            color: "bg-rose-100 text-rose-700" },
  failed_validation: { label: "Failed validation",  color: "bg-red-100 text-red-700" },
  context_frozen:    { label: "Context frozen",     color: "bg-indigo-100 text-indigo-700" },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CFG[state] ?? { label: state, color: "bg-slate-100 text-slate-600" };
  return (
    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

function RiskBadge({ risk }: { risk: string | null }) {
  if (!risk) return null;
  const color =
    risk === "critical" ? "bg-rose-100 text-rose-800"
    : risk === "high"   ? "bg-orange-100 text-orange-800"
    : risk === "medium" ? "bg-amber-100 text-amber-800"
    : "bg-slate-100 text-slate-600";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      Risk: {risk}
    </span>
  );
}

// ── Copy-to-clipboard helper ──────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      type="button"
      onClick={handle}
      className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// ── Decision modal ────────────────────────────────────────────────────────────

function DecisionModal({
  action,
  onConfirm,
  onCancel,
  isPending,
}: {
  action: "approve" | "reject";
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [reason, setReason] = useState("");
  const isApprove = action === "approve";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center gap-2">
          {isApprove ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          ) : (
            <XCircle className="h-5 w-5 text-rose-600" />
          )}
          <h2 className="text-lg font-semibold text-slate-900">
            {isApprove ? "Approve proposal" : "Reject proposal"}
          </h2>
        </div>
        <p className="text-sm text-slate-500">
          {isApprove
            ? "Approving will mark this proposal as approved and write an audit event."
            : "Rejecting will close this proposal without applying changes."}
        </p>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="reason">
            Reason <span className="text-slate-400">(optional)</span>
          </label>
          <textarea
            id="reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            placeholder="Add a short note for the audit trail…"
          />
        </div>
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(reason)}
            disabled={isPending}
            className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors disabled:opacity-50 ${
              isApprove
                ? "bg-emerald-600 hover:bg-emerald-700"
                : "bg-rose-600 hover:bg-rose-700"
            }`}
          >
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : isApprove ? "Approve" : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProposalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: runId } = use(params);
  const queryClient = useQueryClient();
  const [decisionModal, setDecisionModal] = useState<"approve" | "reject" | null>(null);

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: ["posture-run", runId],
    queryFn: () => proposalsApi.getRun(runId),
  });

  // Fetch the proposal linked to this run (by listing runs then matching)
  const { data: proposal, isLoading: proposalLoading } = useQuery({
    queryKey: ["posture-proposal-for-run", runId],
    queryFn: async (): Promise<ChangeProposal | null> => {
      // We load by getting run's proposal via runs/{id}/proposals doesn't exist yet;
      // so we do GET /posture/proposals — but we don't have that list endpoint.
      // Instead the list page navigated here with run id, we need the proposal id.
      // Workaround: store proposal id in sessionStorage on creation, or use run metadata.
      // For the detail page we expose a "load proposal" section that fetches by proposal id.
      // Real solution: the frontend would navigate to /proposals/[proposal_id] instead.
      // Here we store proposal context via the "create proposal" flow.
      return null;
    },
    enabled: false, // only loaded when proposal id is known
  });

  const approveMutation = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      proposalsApi.approveProposal(proposalId, reason || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posture-run", runId] });
      queryClient.invalidateQueries({ queryKey: ["posture-runs"] });
      setDecisionModal(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      proposalsApi.rejectProposal(proposalId, reason || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posture-run", runId] });
      queryClient.invalidateQueries({ queryKey: ["posture-runs"] });
      setDecisionModal(null);
    },
  });

  const snapshotMutation = useMutation({
    mutationFn: () => proposalsApi.createSnapshot(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posture-run", runId] });
    },
  });

  if (runLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <AlertTriangle className="h-10 w-10 text-rose-400" />
        <p className="text-slate-600">Run not found.</p>
        <Link href="/posture/proposals" className="text-brand-600 hover:underline text-sm">
          Back to proposals
        </Link>
      </div>
    );
  }

  const isPendingDecision = run.workflow_state === "pending_approval";
  const isDecided = run.workflow_state === "approved" || run.workflow_state === "rejected";

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <Link
              href="/posture/proposals"
              className="text-sm text-slate-500 hover:text-brand-600 inline-flex items-center gap-1 mb-2"
            >
              <ChevronLeft className="h-4 w-4" /> Back to proposals
            </Link>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <GitPullRequest className="h-7 w-7 text-brand-600" />
              Run detail
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {!isDecided && run.workflow_state !== "context_frozen" && (
              <button
                type="button"
                onClick={() => snapshotMutation.mutate()}
                disabled={snapshotMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50"
              >
                {snapshotMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                Freeze context
              </button>
            )}
          </div>
        </div>

        {/* Run metadata card */}
        <div className="bg-white rounded-xl border shadow-sm p-6 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <StateBadge state={run.workflow_state} />
            <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
              {run.session_type}
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Run ID</dt>
              <dd className="font-mono text-xs text-slate-700 mt-0.5 flex items-center gap-2">
                {run.id}
                <CopyButton text={run.id} />
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Created by</dt>
              <dd className="text-slate-700 mt-0.5">{run.created_by}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Created at</dt>
              <dd className="text-slate-700 mt-0.5">{new Date(run.created_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Tool rounds</dt>
              <dd className="text-slate-700 mt-0.5">
                {run.tool_rounds_used} / {run.max_tool_rounds}
              </dd>
            </div>
          </dl>
        </div>

        {/* Proposal card — shown when the run has a linked proposal */}
        <ProposalCard
          runId={runId}
          run={run}
          isPendingDecision={isPendingDecision}
          isDecided={isDecided}
          onApprove={(proposalId) => setDecisionModal("approve")}
          onReject={(proposalId) => setDecisionModal("reject")}
          approveRejectPending={approveMutation.isPending || rejectMutation.isPending}
          decisionModal={decisionModal}
          onDecisionConfirm={(reason, proposalId) => {
            if (decisionModal === "approve") {
              approveMutation.mutate({ proposalId, reason });
            } else {
              rejectMutation.mutate({ proposalId, reason });
            }
          }}
          onDecisionCancel={() => setDecisionModal(null)}
        />

        {/* Metadata JSON */}
        {Object.keys(run.metadata_json).length > 0 && (
          <div className="bg-white rounded-xl border shadow-sm p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Run metadata</h3>
            <pre className="text-xs bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto">
              {JSON.stringify(run.metadata_json, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </main>
  );
}

// ── Proposal card (fetches its own proposal by run_id indirection) ────────────

function ProposalCard({
  runId,
  run,
  isPendingDecision,
  isDecided,
  onApprove,
  onReject,
  approveRejectPending,
  decisionModal,
  onDecisionConfirm,
  onDecisionCancel,
}: {
  runId: string;
  run: AgentWorkflowRun;
  isPendingDecision: boolean;
  isDecided: boolean;
  onApprove: (proposalId: string) => void;
  onReject: (proposalId: string) => void;
  approveRejectPending: boolean;
  decisionModal: "approve" | "reject" | null;
  onDecisionConfirm: (reason: string, proposalId: string) => void;
  onDecisionCancel: () => void;
}) {
  const [proposalId, setProposalId] = useState("");
  const [inputId, setInputId] = useState("");
  const [exportData, setExportData] = useState<import("@/lib/api").ProposalExport | null>(null);
  const [exporting, setExporting] = useState(false);

  const { data: proposal, isLoading, error } = useQuery({
    queryKey: ["posture-proposal", proposalId],
    queryFn: () => proposalsApi.getProposal(proposalId),
    enabled: !!proposalId,
  });

  const handleExport = async () => {
    if (!proposal) return;
    setExporting(true);
    try {
      const exp = await proposalsApi.exportProposal(proposal.id);
      setExportData(exp);
    } finally {
      setExporting(false);
    }
  };

  const hasProposalState =
    run.workflow_state !== "gathering_context" && run.workflow_state !== "context_frozen";

  if (!hasProposalState && !proposalId) return null;

  return (
    <div className="bg-white rounded-xl border shadow-sm p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">Change proposal</h2>
        {!proposalId && (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={inputId}
              onChange={(e) => setInputId(e.target.value)}
              placeholder="Proposal UUID"
              className="border border-slate-200 rounded px-2 py-1 text-xs font-mono w-72 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <button
              type="button"
              onClick={() => setProposalId(inputId.trim())}
              disabled={!inputId.trim()}
              className="px-3 py-1.5 text-xs bg-brand-600 text-white rounded hover:bg-brand-700 disabled:opacity-40"
            >
              Load
            </button>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      )}

      {error && (
        <p className="text-sm text-rose-600">Could not load proposal — check the ID and try again.</p>
      )}

      {proposal && (
        <div className="space-y-5">
          {/* Risk + resource addresses */}
          <div className="flex items-center gap-3 flex-wrap">
            <RiskBadge risk={proposal.risk_level} />
            {proposal.validation_errors && Object.keys(proposal.validation_errors).length > 0 && (
              <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-semibold flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" /> Validation errors
              </span>
            )}
            {proposal.decided_at && (
              <span className="text-xs text-slate-400">
                Decided by <strong>{proposal.decided_by}</strong>{" "}
                at {new Date(proposal.decided_at).toLocaleString()}
              </span>
            )}
          </div>

          {proposal.resource_addresses.length > 0 && (
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Resources</p>
              <ul className="space-y-1">
                {proposal.resource_addresses.map((addr) => (
                  <li
                    key={addr}
                    className="text-xs font-mono bg-slate-50 border border-slate-100 px-3 py-1 rounded"
                  >
                    {addr}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Rationale */}
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-400 mb-2">Rationale</p>
            <div className="prose prose-sm max-w-none text-slate-700 bg-slate-50 rounded-lg p-4 text-sm whitespace-pre-wrap">
              {proposal.rationale_md || <em className="text-slate-400">No rationale provided.</em>}
            </div>
          </div>

          {/* Diff */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs uppercase tracking-wide text-slate-400">Unified diff</p>
              <CopyButton text={proposal.unified_diff} />
            </div>
            <pre className="text-xs bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto leading-relaxed">
              {proposal.unified_diff.split("\n").map((line, i) => {
                const cls =
                  line.startsWith("+") && !line.startsWith("+++")
                    ? "text-emerald-400"
                    : line.startsWith("-") && !line.startsWith("---")
                    ? "text-rose-400"
                    : line.startsWith("@@")
                    ? "text-sky-400"
                    : "";
                return (
                  <span key={i} className={cls}>
                    {line}
                    {"\n"}
                  </span>
                );
              })}
            </pre>
          </div>

          {/* Validation errors */}
          {proposal.validation_errors && Object.keys(proposal.validation_errors).length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 space-y-2">
              <p className="text-xs font-semibold text-red-700 uppercase tracking-wide">
                Validation errors
              </p>
              {Object.entries(proposal.validation_errors).map(([field, msg]) => (
                <p key={field} className="text-sm text-red-600">
                  <span className="font-mono font-semibold">{field}:</span> {msg}
                </p>
              ))}
            </div>
          )}

          {/* Action buttons */}
          {isPendingDecision && (
            <div className="flex gap-3 pt-1">
              <button
                type="button"
                onClick={() => onApprove(proposal.id)}
                disabled={approveRejectPending}
                className="flex-1 py-2.5 bg-emerald-600 text-white text-sm font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <CheckCircle2 className="h-4 w-4" />
                Approve
              </button>
              <button
                type="button"
                onClick={() => onReject(proposal.id)}
                disabled={approveRejectPending}
                className="flex-1 py-2.5 bg-rose-600 text-white text-sm font-semibold rounded-lg hover:bg-rose-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <XCircle className="h-4 w-4" />
                Reject
              </button>
            </div>
          )}

          {/* Export */}
          <div className="pt-1 border-t border-slate-100">
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600"
            >
              {exporting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Export as PR artifact
            </button>
            {exportData && (
              <div className="mt-4 space-y-4">
                <div>
                  <p className="text-xs uppercase text-slate-400 mb-1">PR title</p>
                  <p className="font-mono text-xs bg-slate-50 border rounded px-3 py-2">
                    {exportData.pr_title}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-400 mb-1">PR body</p>
                  <pre className="text-xs bg-slate-50 border rounded px-3 py-3 overflow-x-auto whitespace-pre-wrap">
                    {exportData.pr_body}
                  </pre>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-400 mb-1">Git apply instructions</p>
                  <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto">
                    {exportData.git_apply_instructions}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Decision modal */}
      {decisionModal && proposal && (
        <DecisionModal
          action={decisionModal}
          onConfirm={(reason) => onDecisionConfirm(reason, proposal.id)}
          onCancel={onDecisionCancel}
          isPending={approveRejectPending}
        />
      )}
    </div>
  );
}
