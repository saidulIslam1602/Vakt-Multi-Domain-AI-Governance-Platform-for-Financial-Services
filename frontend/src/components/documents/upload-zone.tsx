"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useQueryClient } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api";
import { Upload, CheckCircle, AlertCircle, X } from "lucide-react";
import clsx from "clsx";

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "text/plain": [".txt"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
};

interface FileState {
  file: File;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
  document_id?: string;
}

export function UploadZone() {
  const [files, setFiles] = useState<FileState[]>([]);
  const queryClient = useQueryClient();

  const onDrop = useCallback(
    async (accepted: File[]) => {
      const newFiles: FileState[] = accepted.map((f) => ({ file: f, status: "pending" }));
      setFiles((prev) => [...prev, ...newFiles]);

      for (const fileState of newFiles) {
        setFiles((prev) =>
          prev.map((f) =>
            f.file === fileState.file ? { ...f, status: "uploading" } : f
          )
        );
        try {
          const result = await documentsApi.upload(fileState.file);
          setFiles((prev) =>
            prev.map((f) =>
              f.file === fileState.file
                ? { ...f, status: "success", document_id: result.document_id }
                : f
            )
          );
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : "Upload failed";
          setFiles((prev) =>
            prev.map((f) =>
              f.file === fileState.file ? { ...f, status: "error", error: msg } : f
            )
          );
        }
      }
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    [queryClient]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: 50 * 1024 * 1024,
    multiple: true,
  });

  const remove = (file: File) =>
    setFiles((prev) => prev.filter((f) => f.file !== file));

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={clsx(
          "cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors",
          isDragActive
            ? "border-brand-500 bg-brand-50"
            : "border-gray-200 hover:border-brand-400 hover:bg-gray-50"
        )}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto mb-3 text-gray-400" size={32} strokeWidth={1.5} />
        <p className="text-sm font-medium text-gray-700">
          {isDragActive ? "Drop files here…" : "Drag & drop files, or click to select"}
        </p>
        <p className="mt-1 text-xs text-gray-400">PDF, DOCX, XLSX, TXT, PNG, JPEG — max 50 MB</p>
      </div>

      {files.length > 0 && (
        <ul className="card divide-y divide-gray-50">
          {files.map(({ file, status, error }) => (
            <li key={file.name} className="flex items-center gap-3 px-4 py-3">
              {status === "success" && <CheckCircle size={16} className="text-green-500 shrink-0" />}
              {status === "error" && <AlertCircle size={16} className="text-red-500 shrink-0" />}
              {status === "uploading" && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent shrink-0" />
              )}
              {status === "pending" && <span className="h-4 w-4 rounded-full bg-gray-200 shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-gray-900">{file.name}</p>
                {error && <p className="text-xs text-red-600">{error}</p>}
              </div>
              <button
                onClick={() => remove(file)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
