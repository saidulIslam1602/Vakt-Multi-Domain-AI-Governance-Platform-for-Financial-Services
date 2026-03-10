"use client";

import { useQuery } from "@tanstack/react-query";
import { documentsApi, type DocumentListItem } from "@/lib/api";
import { StatusBadge } from "./status-badge";
import { format } from "date-fns";
import Link from "next/link";
import { FileText, AlertCircle, Loader2, Clock, FileSpreadsheet, FileType } from "lucide-react";

const FILE_ICON: Record<string, React.ElementType> = {
  pdf: FileType,
  docx: FileText,
  xlsx: FileSpreadsheet,
  txt: FileText,
};

function DocTypeIcon({ type }: { type: string }) {
  const Icon = FILE_ICON[type] ?? FileText;
  return <Icon className="h-4 w-4 text-slate-400 shrink-0" />;
}

export function DocumentList() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents"],
    queryFn: () => documentsApi.list({ limit: 50 }),
    refetchInterval: 5000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="animate-spin text-brand-500" size={22} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
        <AlertCircle size={16} className="shrink-0" />
        Failed to load documents. Check your connection and try again.
      </div>
    );
  }

  if (!data?.items.length) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-slate-400">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100">
          <FileText size={28} strokeWidth={1.5} className="text-slate-300" />
        </div>
        <div className="text-center">
          <p className="font-semibold text-slate-600">No documents yet</p>
          <p className="text-sm text-slate-400 mt-0.5">Upload your first document to get started.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.items.map((doc) => (
        <DocumentCard key={doc.document_id} doc={doc} />
      ))}
    </div>
  );
}

function DocumentCard({ doc }: { doc: DocumentListItem & { needs_review?: boolean; review_status?: string } }) {
  return (
    <Link href={`/documents/${doc.document_id}`} className="block group">
      <div className="card-hover flex items-center gap-4 px-5 py-4">
        {/* File type icon */}
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-50 border border-slate-100 group-hover:border-brand-100 group-hover:bg-brand-50 transition-colors">
          <DocTypeIcon type={doc.document_type} />
        </div>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-semibold text-slate-900 truncate group-hover:text-brand-700 transition-colors">
              {doc.filename}
            </p>
            <span className="text-xs text-slate-300 uppercase font-medium tracking-wide shrink-0">
              {doc.document_type}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <Clock className="h-3 w-3 text-slate-300 shrink-0" />
            <span className="text-xs text-slate-400">
              {format(new Date(doc.uploaded_at), "dd MMM yyyy, HH:mm")}
            </span>
          </div>
        </div>

        {/* Badges */}
        <div className="flex items-center gap-2 shrink-0">
          {doc.needs_review && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-100 text-amber-700">
              <Clock className="h-3 w-3" /> Review
            </span>
          )}
          <StatusBadge status={doc.status} />
        </div>
      </div>
    </Link>
  );
}
