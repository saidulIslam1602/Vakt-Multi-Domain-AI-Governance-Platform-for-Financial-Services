import { Mail, Upload, FolderArchive } from "lucide-react";
import type { IngestSource } from "@/lib/api";

const CONFIG: Record<
  IngestSource,
  { label: string; icon: React.ElementType; className: string }
> = {
  email: {
    label: "Email",
    icon: Mail,
    className:
      "inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-violet-100 text-violet-700",
  },
  bulk: {
    label: "Bulk",
    icon: FolderArchive,
    className:
      "inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-sky-100 text-sky-700",
  },
  upload: {
    label: "Upload",
    icon: Upload,
    className:
      "inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-500",
  },
};

/**
 * Renders a small coloured pill showing how a document entered the system.
 * Renders nothing when `source` is undefined (old records without source data).
 */
export function SourceBadge({ source }: { source?: IngestSource }) {
  if (!source) return null;
  const cfg = CONFIG[source];
  const Icon = cfg.icon;
  return (
    <span className={cfg.className}>
      <Icon className="h-3 w-3 shrink-0" />
      {cfg.label}
    </span>
  );
}
