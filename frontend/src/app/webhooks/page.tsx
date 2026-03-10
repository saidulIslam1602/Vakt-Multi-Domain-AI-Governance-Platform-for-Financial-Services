"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ToggleLeft, ToggleRight, Link2 } from "lucide-react";
import Link from "next/link";
import { webhooksApi, type WebhookConfig } from "@/lib/api";

const SUPPORTED_EVENTS = [
  "document.uploaded",
  "document.ready",
  "document.failed",
  "document.review_required",
  "document.approved",
  "document.rejected",
];

function NewWebhookForm({ onSuccess }: { onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>(["document.ready"]);

  const createMutation = useMutation({
    mutationFn: () => webhooksApi.create({ name, url, events }),
    onSuccess,
  });

  const toggleEvent = (e: string) =>
    setEvents((prev) =>
      prev.includes(e) ? prev.filter((x) => x !== e) : [...prev, e]
    );

  return (
    <div className="bg-white rounded-2xl border shadow-sm p-6 space-y-4">
      <h3 className="font-semibold text-slate-800">New Webhook</h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-slate-600 mb-1">Name</label>
          <input
            className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            placeholder="ERP integration"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Endpoint URL</label>
          <input
            className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            placeholder="https://your-erp.example.com/hooks/allergo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
      </div>
      <div>
        <label className="block text-sm text-slate-600 mb-2">Subscribe to events</label>
        <div className="flex flex-wrap gap-2">
          {SUPPORTED_EVENTS.map((ev) => (
            <button
              key={ev}
              type="button"
              onClick={() => toggleEvent(ev)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                events.includes(ev)
                  ? "bg-brand-500 text-white border-brand-500"
                  : "bg-white text-slate-600 border-slate-200 hover:border-brand-300"
              }`}
            >
              {ev}
            </button>
          ))}
        </div>
      </div>
      <button
        onClick={() => createMutation.mutate()}
        disabled={!name || !url || events.length === 0 || createMutation.isPending}
        className="btn-primary disabled:opacity-50"
      >
        {createMutation.isPending ? "Creating…" : "Create Webhook"}
      </button>
      {createMutation.isError && (
        <p className="text-sm text-rose-600">Failed to create. Check URL format and try again.</p>
      )}
    </div>
  );
}

function WebhookRow({ webhook }: { webhook: WebhookConfig }) {
  const queryClient = useQueryClient();

  const toggleMutation = useMutation({
    mutationFn: () => webhooksApi.update(webhook.webhook_id, { enabled: !webhook.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["webhooks"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => webhooksApi.delete(webhook.webhook_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["webhooks"] }),
  });

  return (
    <div className="flex items-start justify-between px-6 py-4 hover:bg-slate-50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">{webhook.name}</span>
          {!webhook.enabled && (
            <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
              disabled
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-0.5 truncate">{webhook.url}</p>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {webhook.events.map((ev) => (
            <span
              key={ev}
              className="text-xs bg-brand-50 text-brand-700 px-1.5 py-0.5 rounded"
            >
              {ev}
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2 ml-4 shrink-0">
        <button
          onClick={() => toggleMutation.mutate()}
          title={webhook.enabled ? "Disable" : "Enable"}
          className="text-slate-400 hover:text-brand-500 transition-colors"
        >
          {webhook.enabled ? (
            <ToggleRight className="h-5 w-5 text-emerald-500" />
          ) : (
            <ToggleLeft className="h-5 w-5" />
          )}
        </button>
        <button
          onClick={() => deleteMutation.mutate()}
          title="Delete webhook"
          className="text-slate-400 hover:text-rose-500 transition-colors"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export default function WebhooksPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { data: webhooks = [], isLoading } = useQuery({
    queryKey: ["webhooks"],
    queryFn: webhooksApi.list,
  });

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Webhook Integrations</h1>
            <p className="text-slate-500 text-sm mt-0.5">
              Connect your ERP, accounting system, or internal tooling via outbound webhooks.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-sm text-brand-600 hover:underline">
              ← Dashboard
            </Link>
            <button
              onClick={() => setShowForm((s) => !s)}
              className="btn-primary flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              {showForm ? "Cancel" : "Add Webhook"}
            </button>
          </div>
        </div>

        {showForm && (
          <NewWebhookForm
            onSuccess={() => {
              setShowForm(false);
              queryClient.invalidateQueries({ queryKey: ["webhooks"] });
            }}
          />
        )}

        <div className="bg-white rounded-2xl border shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="py-16 text-center text-slate-400 animate-pulse">Loading…</div>
          ) : webhooks.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <Link2 className="h-10 w-10 mx-auto mb-2 text-slate-300" />
              <p className="font-medium">No webhooks configured yet.</p>
              <p className="text-sm mt-1">
                Add a webhook to notify external systems when documents are processed.
              </p>
            </div>
          ) : (
            <ul className="divide-y">
              {webhooks.map((wh) => (
                <li key={wh.webhook_id}>
                  <WebhookRow webhook={wh} />
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Payload reference */}
        <section className="bg-white rounded-2xl border shadow-sm p-6">
          <h3 className="font-semibold text-slate-700 mb-3">Payload Format</h3>
          <pre className="text-xs bg-slate-800 text-slate-100 rounded-xl p-4 overflow-auto">
{`{
  "event": "document.ready",
  "tenant_id": "your-tenant-id",
  "document_id": "3f2504e0-...",
  "timestamp": 1741700000,
  "data": { /* event-specific payload */ }
}`}
          </pre>
          <p className="text-xs text-slate-500 mt-3">
            Each request includes an{" "}
            <code className="text-brand-600">X-Allergo-Signature</code> header
            (HMAC-SHA256) for verification. Signing secret is shown only at
            creation time.
          </p>
        </section>
      </div>
    </main>
  );
}
