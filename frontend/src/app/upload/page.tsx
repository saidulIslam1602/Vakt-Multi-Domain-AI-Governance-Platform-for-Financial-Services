import { UploadZone } from "@/components/documents/upload-zone";

export default function UploadPage() {
  return (
    <div className="px-8 py-8 max-w-2xl">
      <p className="section-label">Ingest</p>
      <h1 className="mb-1">Upload Documents</h1>
      <p className="mb-8 text-sm text-slate-500">
        PDF, DOCX, XLSX, TXT, or images. Each file is parsed, AI-extracted,
        and indexed automatically.
      </p>
      <UploadZone />
    </div>
  );
}
