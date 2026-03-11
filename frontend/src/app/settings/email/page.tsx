"use client";

/**
 * Settings › Email Ingestion page
 *
 * Lets each tenant self-manage their IMAP inbox registration:
 *  • View current config (password always masked)
 *  • Enable / disable ingestion with one toggle
 *  • Edit connection settings + filter rules
 *  • Test credentials before saving
 *  • Delete the config (stops the live poller)
 *
 * Live poller status badge auto-refreshes every 30 s.
 */

import { useEffect, useRef, useState } from "react";
import {
  emailConfigApi,
  type EmailConfigCreatePayload,
  type EmailConfigPatchPayload,
  type EmailIngestConfig,
  type EmailPollerStatus,
  type EmailPollerStatusEntry,
} from "@/lib/api";

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<EmailPollerStatus, string> = {
  idle:     "bg-yellow-100 text-yellow-800",
  running:  "bg-green-100  text-green-800",
  error:    "bg-red-100    text-red-800",
  disabled: "bg-gray-100   text-gray-500",
};

function StatusBadge({ status }: { status: EmailPollerStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold capitalize ${STATUS_STYLES[status]}`}
    >
      <span
        className={`mr-1.5 h-2 w-2 rounded-full ${
          status === "running" ? "animate-pulse bg-green-500" : "bg-current opacity-60"
        }`}
      />
      {status}
    </span>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function field(
  label: string,
  children: React.ReactNode,
  hint?: string,
) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {children}
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function input(
  props: React.InputHTMLAttributes<HTMLInputElement>,
) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400 ${props.className ?? ""}`}
    />
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const EMPTY_FORM: EmailConfigCreatePayload = {
  imap_host: "",
  imap_port: 993,
  imap_username: "",
  imap_password: "",
  imap_mailbox: "INBOX",
  use_ssl: true,
  poll_interval_sec: 300,
  enabled: true,
  allowed_senders: "",
  blocked_senders: "",
  required_subject_kw: "",
  blocked_subject_kw: "",
  min_attachment_bytes: 1024,
  max_attachment_bytes: 52_428_800,
};

export default function EmailIngestSettingsPage() {
  const [config, setConfig] = useState<EmailIngestConfig | null>(null);
  const [pollerStatus, setPollerStatus] = useState<EmailPollerStatusEntry | null>(null);
  const [form, setForm] = useState<EmailConfigCreatePayload>(EMPTY_FORM);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load current config on mount ──────────────────────────────────────────

  useEffect(() => {
    loadConfig();
    loadPollerStatus();

    // Refresh poller status every 30 s
    pollerRef.current = setInterval(loadPollerStatus, 30_000);
    return () => {
      if (pollerRef.current) clearInterval(pollerRef.current);
    };
  }, []);

  async function loadConfig() {
    setLoading(true);
    try {
      const cfg = await emailConfigApi.get();
      setConfig(cfg);
      setForm({
        imap_host: cfg.imap_host,
        imap_port: cfg.imap_port,
        imap_username: cfg.imap_username,
        imap_password: "",           // never pre-fill the password field
        imap_mailbox: cfg.imap_mailbox,
        use_ssl: cfg.use_ssl,
        poll_interval_sec: cfg.poll_interval_sec,
        enabled: cfg.enabled,
        allowed_senders: cfg.allowed_senders,
        blocked_senders: cfg.blocked_senders,
        required_subject_kw: cfg.required_subject_kw,
        blocked_subject_kw: cfg.blocked_subject_kw,
        min_attachment_bytes: cfg.min_attachment_bytes,
        max_attachment_bytes: cfg.max_attachment_bytes,
      });
    } catch {
      // 404 = not configured yet — that's fine
      setConfig(null);
      setForm(EMPTY_FORM);
    } finally {
      setLoading(false);
    }
  }

  async function loadPollerStatus() {
    try {
      const s = await emailConfigApi.getPollerStatus();
      setPollerStatus(s);
    } catch {
      setPollerStatus(null);
    }
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      if (config) {
        // PATCH — only send non-empty password
        const patch: EmailConfigPatchPayload = { ...form };
        if (!patch.imap_password) delete patch.imap_password;
        const updated = await emailConfigApi.update(patch);
        setConfig(updated);
        setSuccess("Email config updated successfully.");
      } else {
        if (!form.imap_password) {
          setError("Password is required when creating a new config.");
          return;
        }
        const created = await emailConfigApi.create(form);
        setConfig(created);
        setSuccess("Email ingestion configured successfully.");
      }
      setIsEditing(false);
      await loadPollerStatus();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to save email config.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSaving(false);
    }
  }

  // ── Toggle enabled ────────────────────────────────────────────────────────

  async function handleToggleEnabled() {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await emailConfigApi.update({ enabled: !config.enabled });
      setConfig(updated);
      await loadPollerStatus();
    } catch {
      setError("Failed to toggle ingestion status.");
    } finally {
      setSaving(false);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  async function handleDelete() {
    if (!confirm("Remove email ingestion config and stop the poller? This cannot be undone.")) return;
    setSaving(true);
    setError(null);
    try {
      await emailConfigApi.delete();
      setConfig(null);
      setForm(EMPTY_FORM);
      setPollerStatus(null);
      setSuccess("Email ingestion config deleted.");
    } catch {
      setError("Failed to delete email config.");
    } finally {
      setSaving(false);
    }
  }

  // ── Test connection ───────────────────────────────────────────────────────

  async function handleTestConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await emailConfigApi.testConnection({
        imap_host: form.imap_host,
        imap_port: form.imap_port,
        imap_username: form.imap_username,
        imap_password: form.imap_password || "",
        imap_mailbox: form.imap_mailbox,
        use_ssl: form.use_ssl,
      });
      setTestResult(result);
    } catch {
      setTestResult({ success: false, message: "Test request failed. Check network / service." });
    } finally {
      setTesting(false);
    }
  }

  // ── Form helpers ──────────────────────────────────────────────────────────

  function set(key: keyof EmailConfigCreatePayload, value: unknown) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email Ingestion</h1>
          <p className="mt-1 text-sm text-gray-500">
            Connect an IMAP mailbox to automatically ingest document attachments.
          </p>
        </div>
        {config && (
          <StatusBadge status={pollerStatus?.task_running ? "running" : config.status} />
        )}
      </div>

      {/* Alerts */}
      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-md bg-green-50 p-4 text-sm text-green-700">
          {success}
        </div>
      )}

      {/* Current config summary (view mode) */}
      {config && !isEditing && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Current Configuration</h2>
            <div className="flex gap-2">
              <button
                onClick={handleToggleEnabled}
                disabled={saving}
                className={`rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                  config.enabled
                    ? "bg-green-100 text-green-800 hover:bg-green-200"
                    : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                }`}
              >
                {config.enabled ? "Enabled" : "Disabled"}
              </button>
              <button
                onClick={() => { setIsEditing(true); setSuccess(null); setError(null); }}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Edit
              </button>
              <button
                onClick={handleDelete}
                disabled={saving}
                className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
              >
                Delete
              </button>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div><dt className="font-medium text-gray-500">IMAP Host</dt><dd className="text-gray-900">{config.imap_host}</dd></div>
            <div><dt className="font-medium text-gray-500">Port / SSL</dt><dd className="text-gray-900">{config.imap_port} / {config.use_ssl ? "SSL" : "STARTTLS"}</dd></div>
            <div><dt className="font-medium text-gray-500">Username</dt><dd className="text-gray-900">{config.imap_username}</dd></div>
            <div><dt className="font-medium text-gray-500">Mailbox</dt><dd className="text-gray-900">{config.imap_mailbox}</dd></div>
            <div><dt className="font-medium text-gray-500">Poll Interval</dt><dd className="text-gray-900">{config.poll_interval_sec}s</dd></div>
            <div><dt className="font-medium text-gray-500">Last Polled</dt><dd className="text-gray-900">{config.last_polled_at ? new Date(config.last_polled_at).toLocaleString() : "Never"}</dd></div>
            {config.status_message && (
              <div className="col-span-2">
                <dt className="font-medium text-gray-500">Status Message</dt>
                <dd className="text-red-700">{config.status_message}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* No config yet */}
      {!config && !isEditing && (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <svg className="mx-auto h-10 w-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <h3 className="mt-3 text-sm font-medium text-gray-900">No email config yet</h3>
          <p className="mt-1 text-sm text-gray-500">Connect an IMAP mailbox to start ingesting documents automatically.</p>
          <button
            onClick={() => setIsEditing(true)}
            className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            Connect mailbox
          </button>
        </div>
      )}

      {/* Edit / Create form */}
      {isEditing && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">
            {config ? "Edit Configuration" : "Connect Mailbox"}
          </h2>

          {/* Connection */}
          <section className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Connection</h3>

            {field("IMAP Host", input({
              type: "text",
              placeholder: "imap.gmail.com",
              value: form.imap_host,
              onChange: (e) => set("imap_host", e.target.value),
            }))}

            <div className="grid grid-cols-2 gap-4">
              {field("Port", input({
                type: "number",
                value: form.imap_port,
                onChange: (e) => set("imap_port", Number(e.target.value)),
              }))}

              {field("", (
                <label className="flex items-center gap-2 pt-7 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.use_ssl}
                    onChange={(e) => set("use_ssl", e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600"
                  />
                  <span className="text-sm text-gray-700">Use SSL/TLS</span>
                </label>
              ))}
            </div>

            {field("Username", input({
              type: "email",
              placeholder: "invoices@yourcompany.com",
              value: form.imap_username,
              onChange: (e) => set("imap_username", e.target.value),
            }))}

            {field(
              config ? "Password (leave blank to keep current)" : "Password",
              input({
                type: "password",
                placeholder: config ? "••••••••" : "App password or IMAP password",
                value: form.imap_password,
                onChange: (e) => set("imap_password", e.target.value),
                autoComplete: "new-password",
              }),
              "Use an App Password for Gmail / Outlook (not your account password).",
            )}

            {field("Mailbox / Folder", input({
              type: "text",
              placeholder: "INBOX",
              value: form.imap_mailbox,
              onChange: (e) => set("imap_mailbox", e.target.value),
            }))}

            {field(
              "Poll Interval (seconds)",
              input({
                type: "number",
                min: 60,
                value: form.poll_interval_sec,
                onChange: (e) => set("poll_interval_sec", Number(e.target.value)),
              }),
              "Minimum 60 seconds. Default is 300 (5 minutes).",
            )}
          </section>

          {/* Filters */}
          <section className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Filters (optional)</h3>

            {field(
              "Allowed Senders",
              input({
                type: "text",
                placeholder: "vendor@acme.com, @partner.no",
                value: form.allowed_senders,
                onChange: (e) => set("allowed_senders", e.target.value),
              }),
              "Comma-separated addresses or @domain. Empty = accept all senders.",
            )}

            {field(
              "Blocked Senders",
              input({
                type: "text",
                placeholder: "noreply@salesforce.com",
                value: form.blocked_senders,
                onChange: (e) => set("blocked_senders", e.target.value),
              }),
              "Always skip these senders (deny-override).",
            )}

            {field(
              "Required Subject Keywords",
              input({
                type: "text",
                placeholder: "invoice, 2026",
                value: form.required_subject_kw,
                onChange: (e) => set("required_subject_kw", e.target.value),
              }),
              "ALL keywords must appear in the subject (comma-separated).",
            )}

            {field(
              "Blocked Subject Keywords",
              input({
                type: "text",
                placeholder: "newsletter, unsubscribe",
                value: form.blocked_subject_kw,
                onChange: (e) => set("blocked_subject_kw", e.target.value),
              }),
              "Skip emails whose subject contains ANY of these.",
            )}

            <div className="grid grid-cols-2 gap-4">
              {field(
                "Min Attachment (bytes)",
                input({
                  type: "number",
                  min: 0,
                  value: form.min_attachment_bytes,
                  onChange: (e) => set("min_attachment_bytes", Number(e.target.value)),
                }),
                "Default: 1 024 (1 KB)",
              )}
              {field(
                "Max Attachment (bytes)",
                input({
                  type: "number",
                  min: 1,
                  value: form.max_attachment_bytes,
                  onChange: (e) => set("max_attachment_bytes", Number(e.target.value)),
                }),
                "Default: 52 428 800 (50 MB)",
              )}
            </div>
          </section>

          {/* Enable toggle */}
          <label className="flex items-center gap-3 cursor-pointer">
            <div
              onClick={() => set("enabled", !form.enabled)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                form.enabled ? "bg-indigo-600" : "bg-gray-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  form.enabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </div>
            <span className="text-sm font-medium text-gray-700">
              {form.enabled ? "Ingestion enabled" : "Ingestion disabled"}
            </span>
          </label>

          {/* Test connection result */}
          {testResult && (
            <div
              className={`rounded-md p-3 text-sm ${
                testResult.success ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
              }`}
            >
              {testResult.success ? "✓ " : "✗ "}
              {testResult.message}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-md bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : config ? "Save Changes" : "Connect Mailbox"}
            </button>

            <button
              onClick={handleTestConnection}
              disabled={testing || !form.imap_host || !form.imap_username}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {testing ? "Testing…" : "Test Connection"}
            </button>

            {config && (
              <button
                onClick={() => { setIsEditing(false); setTestResult(null); setError(null); }}
                className="ml-auto text-sm text-gray-500 hover:text-gray-700"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}

      {/* Poller live status */}
      {pollerStatus && config && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs text-gray-500">
          <span className="font-medium text-gray-700">Live poller: </span>
          {pollerStatus.task_running
            ? `running — polling ${pollerStatus.host} / ${pollerStatus.mailbox} every ${pollerStatus.interval_sec}s`
            : "not running"}
          <span className="ml-2 text-gray-400">(refreshes every 30 s)</span>
        </div>
      )}
    </div>
  );
}
