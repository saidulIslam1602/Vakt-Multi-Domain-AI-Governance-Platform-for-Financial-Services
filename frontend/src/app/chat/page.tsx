"use client";

import { ChatPanel } from "@/components/chat/chat-panel";
import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";

const CAPABILITIES = [
  {
    category: "Invoices",
    examples: [
      "Which invoices are overdue?",
      "Show all invoices from Telenor",
      "What is the total VAT amount this quarter?",
      "Which invoices have payment terms longer than 30 days?",
    ],
  },
  {
    category: "Contracts",
    examples: [
      "Which contracts expire in the next 90 days?",
      "What does the liability clause say in the Sopra contract?",
      "Show contracts with auto-renewal clauses",
      "What is the total value of active contracts?",
    ],
  },
  {
    category: "Approvals",
    examples: [
      "Which documents need my approval?",
      "Show invoices flagged for high-value approval",
      "What was rejected last week and why?",
    ],
  },
  {
    category: "Reports & Analysis",
    examples: [
      "Summarise the Q3 financial report",
      "How many documents are in each category?",
      "Which vendors have the most outstanding invoices?",
      "Give me a financial snapshot of this month",
    ],
  },
];

export default function ChatPage() {
  return (
    <div className="flex h-full bg-slate-50">
      {/* Left: capabilities reference */}
      <aside className="hidden lg:flex flex-col w-72 border-r border-slate-100 bg-white overflow-y-auto">
        <div className="px-5 pt-6 pb-4 border-b border-slate-100">
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600 mb-4"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Dashboard
          </Link>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-500" />
            <h2 className="font-semibold text-slate-800 text-sm">What I can answer</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            I search document text AND your structured financial database simultaneously.
          </p>
        </div>
        <div className="px-4 py-4 space-y-5">
          {CAPABILITIES.map((cap) => (
            <div key={cap.category}>
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">
                {cap.category}
              </p>
              <ul className="space-y-1">
                {cap.examples.map((ex) => (
                  <li
                    key={ex}
                    className="text-xs text-slate-500 leading-relaxed pl-2 border-l-2 border-slate-100 hover:border-brand-400 hover:text-brand-700 transition-colors cursor-default"
                  >
                    {ex}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* How it works */}
        <div className="mt-auto px-5 py-4 border-t border-slate-100 bg-slate-50">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-2">
            How it works
          </p>
          <ol className="text-[10px] text-slate-400 space-y-1.5 leading-relaxed list-decimal pl-3">
            <li>GPT-4o reads your question</li>
            <li>Searches document text (semantic + keyword)</li>
            <li>Queries financial DB (dates, amounts, counts)</li>
            <li>Synthesises a grounded answer with citations</li>
            <li>Suggests follow-up questions</li>
          </ol>
        </div>
      </aside>

      {/* Right: chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-6 py-4 border-b border-slate-100 bg-white flex items-center justify-between">
          <div>
            <h1 className="font-semibold text-slate-900">CFO Document Assistant</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Powered by GPT-4o · Azure AI Search · Structured financial database
            </p>
          </div>
          <Link
            href="/dashboard"
            className="lg:hidden text-sm text-brand-600 hover:underline"
          >
            ← Dashboard
          </Link>
        </div>
        <div className="flex-1 overflow-hidden">
          <ChatPanel fullPage />
        </div>
      </div>
    </div>
  );
}
