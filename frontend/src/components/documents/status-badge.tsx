import clsx from "clsx";
import type { DocumentStatus } from "@/lib/api";

const config: Record<DocumentStatus, { label: string; className: string }> = {
  uploaded:   { label: "Uploaded",   className: "bg-gray-100 text-gray-700" },
  parsing:    { label: "Parsing…",   className: "bg-blue-50 text-blue-700" },
  parsed:     { label: "Parsed",     className: "bg-blue-100 text-blue-700" },
  extracting: { label: "Extracting…",className: "bg-yellow-50 text-yellow-700" },
  extracted:  { label: "Extracted",  className: "bg-yellow-100 text-yellow-700" },
  indexing:   { label: "Indexing…",  className: "bg-purple-50 text-purple-700" },
  ready:      { label: "Ready",      className: "bg-green-100 text-green-700" },
  failed:     { label: "Failed",     className: "bg-red-100 text-red-700" },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, className } = config[status] ?? config.uploaded;
  return <span className={clsx("badge", className)}>{label}</span>;
}
