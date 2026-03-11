"use client";

import { useRef, useState } from "react";
import { documentsApi, type BulkUploadResponse, type BulkUploadItem } from "@/lib/api";
import { Archive, CheckCircle, XCircle, Loader2, UploadCloud } from "lucide-react";

type UploadState = "idle" | "uploading" | "done" | "error";

function ResultRow({ item }: { item: BulkUploadItem }) {
  const ok = item.status === "queued";
  return (
    <div className="flex items-center gap-3 py-1.5 text-xs border-b border-slate-50 last:border-0">
      {ok ? (
        <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-500" />
      ) : (
        <XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" />
      )}
      <span className="flex-1 truncate text-slate-700">{item.filename}</span>
      <span className={`font-medium ${ok ? "text-green-600" : "text-red-500"}`}>
        {item.status}
      </span>
      {item.error && (
        <span className="text-slate-400 truncate max-w-[140px]" title={item.error}>
          {item.error}
        </span>
      )}
    </div>
  );
}

export function BulkUploadZone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [result, setResult] = useState<BulkUploadResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  async function handleFile(file: File) {
    if (!file.name.endsWith(".zip")) {
      setErrorMsg("Please select a .zip file.");
      setState("error");
      return;
    }
    setState("uploading");
    setResult(null);
    setErrorMsg("");
    try {
      const res = await documentsApi.bulkUpload(file);
      setResult(res);
      setState("done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setErrorMsg(msg);
      setState("error");
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }

  const reset = () => {
    setState("idle");
    setResult(null);
    setErrorMsg("");
  };

  return (
    <div>
      {state === "idle" || state === "error" ? (
        <>
          <div
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => inputRef.current?.click()}
            className="flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 px-6 py-10 cursor-pointer hover:border-brand-400 hover:bg-brand-50 transition-colors"
          >
            <Archive className="h-8 w-8 text-slate-300" />
            <div className="text-center">
              <p className="text-sm font-medium text-slate-600">
                Drop a ZIP file here or{" "}
                <span className="text-brand-600 underline underline-offset-2">browse</span>
              </p>
              <p className="text-xs text-slate-400 mt-1">Only .zip files accepted</p>
            </div>
            {state === "error" && (
              <p className="text-xs text-red-500 mt-1">{errorMsg}</p>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={onInputChange}
          />
        </>
      ) : state === "uploading" ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-6 py-10">
          <Loader2 className="h-8 w-8 text-brand-500 animate-spin" />
          <p className="text-sm text-slate-500">Uploading and queuing files…</p>
        </div>
      ) : (
        result && (
          <div className="card p-5">
            {/* Summary */}
            <div className="flex items-center gap-4 mb-4">
              <UploadCloud className="h-5 w-5 text-green-500" />
              <div className="text-sm">
                <span className="font-semibold text-slate-800">{result.total_files} files</span>
                {" · "}
                <span className="text-green-600">{result.queued} queued</span>
                {result.skipped > 0 && (
                  <span className="text-slate-400"> · {result.skipped} skipped</span>
                )}
                {result.errors > 0 && (
                  <span className="text-red-500"> · {result.errors} errors</span>
                )}
              </div>
              <button onClick={reset} className="ml-auto btn-secondary py-1 px-3 text-xs">
                Upload Another
              </button>
            </div>
            {/* Per-file results */}
            <div className="max-h-64 overflow-y-auto">
              {result.results.map((item, i) => (
                <ResultRow key={i} item={item} />
              ))}
            </div>
          </div>
        )
      )}
    </div>
  );
}
