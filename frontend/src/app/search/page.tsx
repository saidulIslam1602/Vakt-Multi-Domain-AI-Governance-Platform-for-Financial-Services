"use client";

import { useState } from "react";
import { searchApi, type SearchHit } from "@/lib/api";
import { Search, Loader2, FileText } from "lucide-react";
import Link from "next/link";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const res = await searchApi.search(query);
      setResults(res.hits);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="px-8 py-8 max-w-3xl">
      {/* Header */}
      <p className="section-label">Intelligence</p>
      <h1 className="mb-1">Search Documents</h1>
      <p className="mb-6 text-sm text-slate-500">
        Hybrid full-text and semantic search across all indexed documents.
      </p>

      {/* Search input */}
      <div className="flex gap-2 mb-8">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={15} />
          <input
            className="input pl-9"
            placeholder="Search by keyword, concept, or question…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
        </div>
        <button
          onClick={search}
          disabled={!query.trim() || loading}
          className="btn-primary"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : "Search"}
        </button>
      </div>

      {/* Empty state */}
      {searched && !loading && results.length === 0 && (
        <div className="card flex flex-col items-center gap-3 py-12 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100">
            <Search className="h-5 w-5 text-slate-400" />
          </div>
          <div>
            <p className="font-semibold text-slate-700">No results found</p>
            <p className="text-sm text-slate-400 mt-0.5">
              Try a different keyword or phrase.
            </p>
          </div>
        </div>
      )}

      {/* Results — card style per Nordic inspiration */}
      <div className="space-y-3">
        {results.map((hit, i) => (
          <div key={hit.chunk_id} className="card-hover p-5">
            <div className="flex items-start gap-3">
              {/* Doc icon */}
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 mt-0.5">
                <FileText className="h-4 w-4 text-brand-500" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <Link
                    href={`/documents/${hit.document_id}`}
                    className="text-sm font-semibold text-brand-600 hover:text-brand-700 hover:underline truncate"
                  >
                    {(hit as any).filename || `Document ${i + 1}`}
                  </Link>
                  <span className="text-[11px] text-slate-400 shrink-0 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded-full">
                    {Math.round(hit.score * 100)}% match
                  </span>
                </div>
                {hit.highlights.length > 0 ? (
                  <p
                    className="text-sm text-slate-600 leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: hit.highlights[0] }}
                  />
                ) : (
                  <p className="text-sm text-slate-600 leading-relaxed line-clamp-3">
                    {hit.text}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
