"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  chatApi,
  type ChatMessage,
  type Citation,
  type ChatIntent,
} from "@/lib/api";
import {
  Send,
  Bot,
  User,
  Loader2,
  ChevronDown,
  ChevronUp,
  FileText,
  Database,
  Search,
  Sparkles,
  AlertCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import Link from "next/link";

// ── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  tools_used?: string[];
  suggestions?: string[];
  intent?: ChatIntent;
  loading?: boolean;
  error?: boolean;
}

interface ChatPanelProps {
  documentIds?: string[];
  /** When true, shows the quick-ask bar and a larger input */
  fullPage?: boolean;
}

// ── Intent badge ─────────────────────────────────────────────────────────────

const INTENT_LABELS: Record<ChatIntent, { label: string; color: string }> = {
  general: { label: "General", color: "bg-slate-100 text-slate-600" },
  financial_data: { label: "Financial Data", color: "bg-emerald-100 text-emerald-700" },
  content_search: { label: "Document Search", color: "bg-blue-100 text-blue-700" },
  invoice_query: { label: "Invoice", color: "bg-amber-100 text-amber-700" },
  contract_query: { label: "Contract", color: "bg-purple-100 text-purple-700" },
  approval_query: { label: "Approvals", color: "bg-rose-100 text-rose-700" },
  analytics: { label: "Analytics", color: "bg-indigo-100 text-indigo-700" },
  vendor_query: { label: "Vendor", color: "bg-teal-100 text-teal-700" },
  document_lookup: { label: "Document", color: "bg-sky-100 text-sky-700" },
};

function IntentBadge({ intent }: { intent: ChatIntent }) {
  const cfg = INTENT_LABELS[intent] ?? INTENT_LABELS.general;
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

// ── Tool indicator ────────────────────────────────────────────────────────────

function ToolIndicator({ tools }: { tools: string[] }) {
  if (!tools.length) return null;
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-1">
      {tools.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 text-[10px] text-slate-400 bg-slate-50 border border-slate-100 px-1.5 py-0.5 rounded"
        >
          {t === "query_financial_database" ? (
            <Database className="h-2.5 w-2.5" />
          ) : (
            <Search className="h-2.5 w-2.5" />
          )}
          {t === "query_financial_database" ? "DB query" : "Doc search"}
        </span>
      ))}
    </div>
  );
}

// ── Citations panel ───────────────────────────────────────────────────────────

function CitationsPanel({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);
  if (!citations.length) return null;
  return (
    <div className="mt-2 border border-slate-100 rounded-xl overflow-hidden text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center justify-between w-full px-3 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
      >
        <span className="flex items-center gap-1.5 font-medium text-slate-600">
          <FileText className="h-3 w-3" />
          {citations.length} source{citations.length !== 1 ? "s" : ""}
        </span>
        {open ? (
          <ChevronUp className="h-3 w-3 text-slate-400" />
        ) : (
          <ChevronDown className="h-3 w-3 text-slate-400" />
        )}
      </button>
      {open && (
        <ul className="divide-y divide-slate-100 bg-white max-h-48 overflow-y-auto">
          {citations.map((c, i) => (
            <li key={c.chunk_id} className="px-3 py-2 space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <Link
                  href={`/documents/${c.document_id}`}
                  className="font-medium text-brand-600 hover:underline truncate"
                >
                  {c.filename || c.document_id}
                </Link>
                <div className="flex items-center gap-1.5 shrink-0">
                  {c.page && (
                    <span className="text-slate-400">p.{c.page}</span>
                  )}
                  <span className="text-slate-300">
                    {Math.round(c.score * 100)}%
                  </span>
                </div>
              </div>
              <p className="text-slate-500 line-clamp-2 leading-relaxed">
                [{i + 1}] {c.text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Suggestion chips ──────────────────────────────────────────────────────────

function SuggestionChips({
  suggestions,
  onSelect,
}: {
  suggestions: string[];
  onSelect: (_q: string) => void;
}) {
  if (!suggestions.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onSelect(s)}
          className="text-xs bg-brand-50 text-brand-700 border border-brand-100 hover:bg-brand-100 px-2.5 py-1 rounded-full transition-colors text-left"
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// ── Chat bubble ───────────────────────────────────────────────────────────────

function ChatBubble({
  message,
  onSuggestionClick,
}: {
  message: Message;
  onSuggestionClick: (_q: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={clsx("flex gap-2.5", isUser && "flex-row-reverse")}>
      <div
        className={clsx(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white mt-0.5",
          isUser ? "bg-brand-600" : "bg-slate-800"
        )}
      >
        {isUser ? <User size={13} /> : <Bot size={13} />}
      </div>
      <div className={clsx("flex-1 min-w-0", isUser && "flex flex-col items-end")}>
        {/* Bubble */}
        <div
          className={clsx(
            "rounded-2xl px-4 py-2.5 text-sm max-w-full",
            isUser
              ? "bg-brand-600 text-white rounded-tr-sm inline-block max-w-[80%]"
              : "bg-white border border-gray-100 text-gray-900 rounded-tl-sm w-full"
          )}
        >
          {message.loading ? (
            <span className="flex gap-1 items-center text-gray-400">
              <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
              <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
            </span>
          ) : message.error ? (
            <span className="flex items-center gap-1.5 text-rose-600">
              <AlertCircle size={14} /> Something went wrong. Please try again.
            </span>
          ) : (
            <ReactMarkdown className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0.5">
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Metadata (only on assistant messages) */}
        {!isUser && !message.loading && !message.error && (
          <div className="w-full mt-1 space-y-1">
            {message.intent && message.intent !== "general" && (
              <div className="flex items-center gap-2">
                <IntentBadge intent={message.intent} />
                <ToolIndicator tools={message.tools_used ?? []} />
              </div>
            )}
            {message.citations && <CitationsPanel citations={message.citations} />}
            {message.suggestions && (
              <SuggestionChips
                suggestions={message.suggestions}
                onSelect={onSuggestionClick}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Quick-ask bar ─────────────────────────────────────────────────────────────

const CFO_QUICK_ASKS = [
  "Which invoices are overdue?",
  "Contracts expiring in 90 days?",
  "Documents pending my approval?",
  "Show all invoices from last month",
  "What are the payment terms in the latest contract?",
  "Total VAT on invoices this quarter?",
];

function QuickAskBar({ onSelect }: { onSelect: (_q: string) => void }) {
  return (
    <div className="flex items-start gap-2 px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white">
      <Sparkles className="h-3.5 w-3.5 text-brand-500 mt-0.5 shrink-0" />
      <div className="flex flex-wrap gap-1.5">
        {CFO_QUICK_ASKS.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="text-xs text-slate-600 bg-white border border-slate-200 hover:border-brand-400 hover:text-brand-700 px-2.5 py-1 rounded-full transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChatPanel({ documentIds, fullPage = false }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(
    async (question?: string) => {
      const q = (question ?? input).trim();
      if (!q || isLoading) return;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: q }]);
      setIsLoading(true);

      // Placeholder bubble
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", loading: true },
      ]);

      try {
        const history: ChatMessage[] = messages.map((m) => ({
          role: m.role,
          content: m.content,
        }));
        const response = await chatApi.ask(q, history, documentIds);

        setMessages((prev) => [
          ...prev.slice(0, -1),
          {
            role: "assistant",
            content: response.answer,
            citations: response.citations,
            tools_used: response.tools_used,
            suggestions: response.suggestions,
            intent: response.intent,
          },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev.slice(0, -1),
          { role: "assistant", content: "", error: true },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, messages, documentIds]
  );

  const handleSuggestion = useCallback(
    (q: string) => {
      if (!isLoading) send(q);
    },
    [isLoading, send]
  );

  return (
    <div className="flex flex-col h-full">
      {/* Quick-ask bar */}
      <QuickAskBar onSelect={handleSuggestion} />

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-12 text-gray-400">
            <Bot size={36} strokeWidth={1.2} className="text-brand-300" />
            <p className="text-sm font-medium text-slate-500">
              CFO Document Assistant
            </p>
            <p className="text-xs text-center text-slate-400 max-w-xs leading-relaxed">
              Ask about invoices, contracts, reports — or use the quick-ask
              buttons above. I have access to both document text and structured
              financial data.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <ChatBubble
            key={i}
            message={msg}
            onSuggestionClick={handleSuggestion}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-100 px-4 py-3 bg-white">
        <div className="flex items-end gap-2">
          <textarea
            className={clsx(
              "flex-1 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm",
              "placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-400",
              "focus:border-transparent resize-none leading-relaxed",
              fullPage ? "min-h-[72px]" : "min-h-[40px] max-h-[120px]"
            )}
            placeholder="Ask anything about your documents…"
            value={input}
            rows={fullPage ? 3 : 1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={isLoading}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || isLoading}
            className="btn-primary px-3 py-2.5 rounded-xl shrink-0 disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-slate-400 mt-1.5 pl-1">
          Answers are grounded in your uploaded documents · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
