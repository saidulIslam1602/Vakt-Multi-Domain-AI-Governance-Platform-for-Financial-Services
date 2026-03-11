"use client";

import { exportApi } from "@/lib/api";
import { Download } from "lucide-react";

export function ExportCsvButton({
  documentCategory,
  reviewStatus,
}: {
  documentCategory?: string;
  reviewStatus?: string;
} = {}) {
  return (
    <button
      onClick={() =>
        exportApi.downloadCsv({
          document_category: documentCategory,
          review_status: reviewStatus,
        })
      }
      className="btn-secondary"
      title="Export all documents as CSV"
    >
      <Download className="h-4 w-4" />
      Export CSV
    </button>
  );
}
