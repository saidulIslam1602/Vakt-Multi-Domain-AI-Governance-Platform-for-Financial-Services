import Link from "next/link";
import { DocumentList } from "@/components/documents/document-list";
import { Upload, Clock } from "lucide-react";

export default function DocumentsPage() {
  return (
    <div className="px-8 py-8 max-w-5xl">
      {/* Header — Nordic section-label pattern */}
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="section-label">Library</p>
          <h1>Documents</h1>
          <p className="mt-1 text-sm text-slate-500">
            All uploaded documents and their AI processing status.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/review" className="btn-secondary">
            <Clock className="h-4 w-4" />
            Review Queue
          </Link>
          <Link href="/upload" className="btn-primary">
            <Upload className="h-4 w-4" />
            Upload
          </Link>
        </div>
      </div>
      <DocumentList />
    </div>
  );
}
