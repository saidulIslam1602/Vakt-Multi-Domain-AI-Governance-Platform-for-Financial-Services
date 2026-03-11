"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  alertsApi,
  type AlertRuleResponse,
  type AlertEventResponse,
  type AlertRuleCreate,
  type TriggerType,
} from "@/lib/api";
import { Bell, Plus, Trash2, ToggleLeft, ToggleRight, CheckCheck, X } from "lucide-react";

const TRIGGER_OPTIONS: { value: TriggerType; label: string; hasThreshold: boolean; hasdays: boolean }[] = [
  { value: "legal_risk",               label: "Legal Risk Flag",              hasThreshold: false, hasdays: false },
  { value: "low_confidence",           label: "Low Confidence Score",         hasThreshold: true,  hasdays: false },
  { value: "invoice_amount_threshold", label: "Invoice Amount Exceeds",       hasThreshold: true,  hasdays: false },
  { value: "contract_expiring",        label: "Contract Expiring (days)",     hasThreshold: false, hasdays: true  },
  { value: "invoice_overdue",          label: "Invoice Overdue",              hasThreshold: false, hasdays: false },
  { value: "pending_review_threshold", label: "Pending Review > Threshold",   hasThreshold: true,  hasdays: false },
];

const TRIGGER_LABELS: Record<TriggerType, string> = {
  legal_risk: "Legal Risk",
  low_confidence: "Low Confidence",
  invoice_amount_threshold: "Amount Threshold",
  contract_expiring: "Contract Expiring",
  invoice_overdue: "Invoice Overdue",
  pending_review_threshold: "Pending Review",
};

function RuleRow({
  rule,
  onDelete,
  onToggle,
}: {
  rule: AlertRuleResponse;
  onDelete: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between py-3 px-4 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-800 truncate">{rule.name}</p>
        <p className="text-xs text-slate-400 mt-0.5">
          {TRIGGER_LABELS[rule.trigger_type]}
          {rule.threshold_value != null && ` · threshold: ${rule.threshold_value}`}
          {rule.days_before != null && ` · ${rule.days_before} days before`}
        </p>
      </div>
      <div className="flex items-center gap-3 ml-4 shrink-0">
        <button
          onClick={() => onToggle(rule.rule_id)}
          title={rule.enabled ? "Disable" : "Enable"}
          className="text-slate-400 hover:text-brand-600 transition-colors"
        >
          {rule.enabled ? (
            <ToggleRight className="h-5 w-5 text-brand-600" />
          ) : (
            <ToggleLeft className="h-5 w-5" />
          )}
        </button>
        <button
          onClick={() => onDelete(rule.rule_id)}
          className="text-slate-300 hover:text-red-500 transition-colors"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function EventCard({ event, onAck }: { event: AlertEventResponse; onAck: (id: string) => void }) {
  return (
    <div
      className={`p-4 rounded-lg border transition-colors ${
        event.acknowledged
          ? "border-slate-100 bg-white opacity-60"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-0.5">
            {TRIGGER_LABELS[event.trigger_type]}
          </p>
          <p className="text-sm text-slate-700">{event.message}</p>
          <p className="text-[10px] text-slate-400 mt-1">
            {new Date(event.created_at).toLocaleString()}
          </p>
        </div>
        {!event.acknowledged && (
          <button
            onClick={() => onAck(event.event_id)}
            className="shrink-0 text-xs text-amber-600 hover:text-amber-800 font-medium"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<AlertRuleCreate>({
    name: "",
    trigger_type: "legal_risk",
    threshold_value: undefined,
    days_before: undefined,
    document_category: "",
    channels: [],
  });

  const { data: rules = [] } = useQuery<AlertRuleResponse[]>({
    queryKey: ["alertRules"],
    queryFn: () => alertsApi.getRules(),
  });

  const { data: events = [] } = useQuery<AlertEventResponse[]>({
    queryKey: ["alertEvents"],
    queryFn: () => alertsApi.getEvents(false),
    refetchInterval: 30_000,
  });

  const createRule = useMutation({
    mutationFn: (data: AlertRuleCreate) => alertsApi.createRule(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alertRules"] });
      setShowForm(false);
      setForm({ name: "", trigger_type: "legal_risk" });
    },
  });

  const deleteRule = useMutation({
    mutationFn: (id: string) => alertsApi.deleteRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alertRules"] }),
  });

  const toggleRule = useMutation({
    mutationFn: (id: string) => alertsApi.toggleRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alertRules"] }),
  });

  const ackEvent = useMutation({
    mutationFn: (id: string) => alertsApi.acknowledgeEvent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alertEvents"] }),
  });

  const ackAll = useMutation({
    mutationFn: () => alertsApi.acknowledgeAll(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alertEvents"] }),
  });

  const selectedTrigger = TRIGGER_OPTIONS.find((t) => t.value === form.trigger_type);
  const unread = events.filter((e) => !e.acknowledged).length;

  return (
    <div className="px-8 py-8 max-w-4xl">
      <p className="section-label">Settings</p>
      <h1 className="mb-1">Alerts</h1>
      <p className="mb-8 text-sm text-slate-500">
        Proactive rules that fire when documents match your criteria — legal risk, high amounts, expiring contracts, and more.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Rules panel ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-800 text-sm flex items-center gap-1.5">
              <Bell className="h-4 w-4 text-brand-500" /> Rules ({rules.length})
            </h2>
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-primary py-1.5 px-3 text-xs"
            >
              <Plus className="h-3.5 w-3.5" />
              New Rule
            </button>
          </div>

          {showForm && (
            <div className="card p-4 mb-3 space-y-3">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Create Rule</p>
              <input
                className="input w-full text-sm"
                placeholder="Rule name (e.g. High invoice alert)"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <select
                className="input w-full text-sm"
                value={form.trigger_type}
                onChange={(e) =>
                  setForm({ ...form, trigger_type: e.target.value as TriggerType })
                }
              >
                {TRIGGER_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              {selectedTrigger?.hasThreshold && (
                <input
                  className="input w-full text-sm"
                  type="number"
                  placeholder="Threshold value"
                  value={form.threshold_value ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, threshold_value: e.target.value ? Number(e.target.value) : undefined })
                  }
                />
              )}
              {selectedTrigger?.hasdays && (
                <input
                  className="input w-full text-sm"
                  type="number"
                  placeholder="Days before expiry"
                  value={form.days_before ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, days_before: e.target.value ? Number(e.target.value) : undefined })
                  }
                />
              )}
              <div className="flex gap-2">
                <button
                  className="btn-primary py-1.5 px-3 text-xs flex-1"
                  disabled={!form.name || createRule.isPending}
                  onClick={() => createRule.mutate(form)}
                >
                  {createRule.isPending ? "Saving…" : "Save Rule"}
                </button>
                <button
                  className="btn-secondary py-1.5 px-3 text-xs"
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {rules.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-8">No rules yet. Create one above.</p>
            ) : (
              rules.map((r) => (
                <RuleRow
                  key={r.rule_id}
                  rule={r}
                  onDelete={(id) => deleteRule.mutate(id)}
                  onToggle={(id) => toggleRule.mutate(id)}
                />
              ))
            )}
          </div>
        </section>

        {/* ── Events panel ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-800 text-sm">
              Events
              {unread > 0 && (
                <span className="ml-2 inline-flex items-center justify-center h-5 w-5 rounded-full bg-amber-500 text-white text-[10px] font-bold">
                  {unread}
                </span>
              )}
            </h2>
            {unread > 0 && (
              <button
                onClick={() => ackAll.mutate()}
                className="btn-secondary py-1.5 px-3 text-xs"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Dismiss All
              </button>
            )}
          </div>

          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
            {events.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-8">No alert events yet. Rules fire automatically after document extraction.</p>
            ) : (
              events.map((ev) => (
                <EventCard key={ev.event_id} event={ev} onAck={(id) => ackEvent.mutate(id)} />
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
