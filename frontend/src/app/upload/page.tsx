import { UploadZone } from "@/components/documents/upload-zone";
import { BulkUploadZone } from "@/components/documents/bulk-upload-zone";

export default function UploadPage() {
  return (
    <div className="px-8 py-8 max-w-2xl">
      <p className="section-label">Ingest</p>
      <h1 className="mb-1">Upload Documents</h1>
      <p className="mb-8 text-sm text-slate-500">
        PDF, DOCX, XLSX, TXT, or images. Each file is parsed, AI-extracted,
        and indexed automatically.
      </p>

      {/* Single-file upload */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Single File</h2>
        <UploadZone />
      </div>

      {/* Bulk ZIP upload */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 mb-1">Bulk Upload (ZIP)</h2>
        <p className="text-xs text-slate-400 mb-3">
          Pack multiple documents into a ZIP file and upload them all at once.
        </p>
        <BulkUploadZone />
      </div>
    </div>
  );
}
