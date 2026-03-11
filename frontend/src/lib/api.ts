/**
 * Typed API client for all backend services.
 * All requests go through Next.js rewrites → appropriate microservice.
 */

import axios, { type AxiosInstance } from "axios";

export type DocumentStatus =
  | "uploaded"
  | "parsing"
  | "parsed"
  | "extracting"
  | "extracted"
  | "indexing"
  | "ready"
  | "failed";

export type DocumentType = "pdf" | "docx" | "xlsx" | "txt" | "html" | "image" | "unknown";

export interface DocumentListItem {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  document_type: DocumentType;
  uploaded_at: string;
  updated_at: string;
}

export interface ExtractionResult {
  dates: string[];
  parties: string[];
  amounts: string[];
  key_terms: string[];
  summary: string;
  confidence_score: number;
  // CFO-specific fields (all optional — undefined when not extracted)
  document_category?: string;
  invoice_number?: string;
  invoice_date?: string;
  due_date?: string;
  total_amount?: string;
  net_amount?: string;
  vat_amount?: string;
  vat_rate?: string;
  currency?: string;
  vendor_name?: string;
  vendor_org_number?: string;
  vendor_address?: string;
  vendor_iban?: string;
  buyer_name?: string;
  buyer_org_number?: string;
  payment_terms?: string;
  bank_account?: string;
  reference_number?: string;
  contract_value?: string;
  contract_start_date?: string;
  contract_end_date?: string;
  renewal_clause?: string;
  cost_center?: string;
  gl_account?: string;
  approval_required?: boolean;
}

export type ReviewStatus =
  | "not_required"
  | "pending_review"
  | "approved"
  | "rejected";

export interface ReviewItem {
  document_id: string;
  filename: string;
  review_status: ReviewStatus;
  needs_review: boolean;
  confidence_score: number | null;
  total_amount: string | null;
  vendor_name: string | null;
  document_category: string | null;
  uploaded_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface HistoryEntry {
  history_id: string;
  document_id: string;
  extraction: ExtractionResult;
  changed_by: string;
  changed_at: string;
  change_reason: string | null;
}

export interface DownloadUrlResponse {
  document_id: string;
  filename: string;
  url: string;
  expires_in_seconds: number;
}

export interface WebhookConfig {
  webhook_id: string;
  name: string;
  url: string;
  events: string[];
  enabled: boolean;
  created_at: string;
}

export interface DashboardStats {
  total_documents: number;
  pending_review: number;
  approved: number;
  rejected: number;
  failed: number;
  total_amount_sum: string | null;
}

export interface DocumentDetail extends DocumentListItem {
  tenant_id: string;
  page_count: number | null;
  size_bytes: number | null;
  error_message: string | null;
  extraction: ExtractionResult | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  text: string;
  score: number;
  highlights: string[];
}

export interface SearchResult {
  query: string;
  hits: SearchHit[];
  total: number;
  search_mode: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  filename: string;
  text: string;
  score: number;
  page: number | null;
}

export type ChatIntent =
  | "general"
  | "financial_data"
  | "content_search"
  | "invoice_query"
  | "contract_query"
  | "approval_query"
  | "analytics"
  | "vendor_query"
  | "document_lookup";

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  tools_used: string[];
  suggestions: string[];
  model: string;
  intent: ChatIntent;
}

export interface StreamMetadata {
  type: "metadata";
  citations: Citation[];
  tools_used: string[];
  intent: ChatIntent;
}

export interface StreamToken {
  type: "token";
  delta: string;
}

export interface StreamSuggestions {
  type: "suggestions";
  suggestions: string[];
}

function createClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL });
  client.interceptors.request.use((config) => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
  return client;
}

// Base URLs map to Next.js rewrites in next.config.ts.
// Each client base URL already includes the service path prefix,
// so route paths below should NOT repeat it.
const ingestClient = createClient("/api/ingest/documents");
const documentClient = createClient("/api/documents/documents");
const searchClient = createClient("/api/search/search");
const chatClient = createClient("/api/chat/chat");

export const documentsApi = {
  upload: async (file: File): Promise<{ document_id: string }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await ingestClient.post<{ document_id: string }>("/", form);
    return res.data;
  },

  bulkUpload: async (zipFile: File): Promise<BulkUploadResponse> => {
    const form = new FormData();
    form.append("file", zipFile);
    const res = await ingestClient.post<BulkUploadResponse>("/bulk", form);
    return res.data;
  },

  list: async (params: {
    limit?: number;
    offset?: number;
    status?: DocumentStatus;
  } = {}): Promise<DocumentListResponse> => {
    const res = await documentClient.get<DocumentListResponse>("/", { params });
    return res.data;
  },

  get: async (id: string): Promise<DocumentDetail> => {
    const res = await documentClient.get<DocumentDetail>(`/${id}`);
    return res.data;
  },

  updateExtraction: async (
    id: string,
    patch: Partial<ExtractionResult>
  ): Promise<DocumentDetail> => {
    const res = await documentClient.patch<DocumentDetail>(`/${id}/extraction`, patch);
    return res.data;
  },

  delete: async (id: string): Promise<void> => {
    await documentClient.delete(`/${id}`);
  },

  getDownloadUrl: async (
    id: string,
    expiryHours = 1
  ): Promise<DownloadUrlResponse> => {
    const res = await documentClient.get<DownloadUrlResponse>(
      `/${id}/download-url`,
      { params: { expiry_hours: expiryHours } }
    );
    return res.data;
  },

  getHistory: async (id: string): Promise<HistoryEntry[]> => {
    const res = await documentClient.get<HistoryEntry[]>(`/${id}/history`);
    return res.data;
  },

  getReviewQueue: async (params: {
    review_status?: ReviewStatus;
    limit?: number;
    offset?: number;
  } = {}): Promise<ReviewItem[]> => {
    const res = await documentClient.get<ReviewItem[]>("/review/queue", {
      params,
    });
    return res.data;
  },

  submitReview: async (
    id: string,
    decision: "approved" | "rejected",
    reason?: string
  ): Promise<void> => {
    await documentClient.patch(`/review/queue/${id}`, { decision, reason });
  },

  getDashboardStats: async (): Promise<DashboardStats> => {
    const res = await documentClient.get<DashboardStats>("/stats");
    return res.data;
  },
};

const webhookClient = createClient("/api/documents/webhooks");

export const webhooksApi = {
  list: async (): Promise<WebhookConfig[]> => {
    const res = await webhookClient.get<WebhookConfig[]>("/");
    return res.data;
  },

  create: async (data: {
    name: string;
    url: string;
    events: string[];
  }): Promise<WebhookConfig> => {
    const res = await webhookClient.post<WebhookConfig>("/", data);
    return res.data;
  },

  update: async (
    id: string,
    patch: { enabled?: boolean; events?: string[] }
  ): Promise<WebhookConfig> => {
    const res = await webhookClient.patch<WebhookConfig>(`/${id}`, patch);
    return res.data;
  },

  delete: async (id: string): Promise<void> => {
    await webhookClient.delete(`/${id}`);
  },
};

export const searchApi = {
  search: async (query: string, documentIds?: string[]): Promise<SearchResult> => {
    const res = await searchClient.post<SearchResult>("/", {
      query,
      top: 10,
      document_ids: documentIds,
    });
    return res.data;
  },
};

// ─── New types ────────────────────────────────────────────────────────────────

export interface BulkUploadItem {
  filename: string;
  document_id: string | null;
  status: string;
  error: string | null;
}

export interface BulkUploadResponse {
  total_files: number;
  queued: number;
  skipped: number;
  errors: number;
  results: BulkUploadItem[];
}

export interface TagsResponse {
  document_id: string;
  tags: string[];
}

export type TriggerType =
  | "invoice_overdue"
  | "invoice_amount_threshold"
  | "contract_expiring"
  | "legal_risk"
  | "low_confidence"
  | "pending_review_threshold";

export interface AlertRuleCreate {
  name: string;
  trigger_type: TriggerType;
  threshold_value?: number;
  days_before?: number;
  document_category?: string;
  channels?: string[];
}

export interface AlertRuleResponse extends AlertRuleCreate {
  rule_id: string;
  tenant_id: string;
  enabled: boolean;
  created_at: string;
}

export interface AlertEventResponse {
  event_id: string;
  rule_id: string;
  document_id: string;
  trigger_type: TriggerType;
  message: string;
  metadata: Record<string, unknown>;
  acknowledged: boolean;
  created_at: string;
}

export interface SpendDataPoint {
  month: string;     // "2024-01"
  count: number;
  total_amount: number;
}

export interface VendorConcentration {
  vendor_name: string;
  count: number;
  percentage: number;
}

export interface ExpiryItem {
  document_id: string;
  filename: string;
  vendor_name: string | null;
  contract_end_date: string;
  days_until_expiry: number;
  contract_value: string | null;
}

export interface AnalyticsResponse {
  spend_by_month: SpendDataPoint[];
  vendor_concentration: VendorConcentration[];
  upcoming_expiries: ExpiryItem[];
}

export interface SavedQuery {
  query_id: string;
  name: string;
  question: string;
  created_at: string;
}

// ─── Extended API clients ──────────────────────────────────────────────────────

const alertsClient = createClient("/api/documents/alerts");
const tagsClient   = createClient("/api/documents/documents");
const statsClient  = createClient("/api/documents/stats");
const savedClient  = createClient("/api/chat/chat/saved");

export const tagsApi = {
  get: async (documentId: string): Promise<TagsResponse> => {
    const res = await tagsClient.get<TagsResponse>(`/${documentId}/tags`);
    return res.data;
  },
  set: async (documentId: string, tags: string[]): Promise<TagsResponse> => {
    const res = await tagsClient.put<TagsResponse>(`/${documentId}/tags`, { tags });
    return res.data;
  },
};

export const alertsApi = {
  getRules: async (): Promise<AlertRuleResponse[]> => {
    const res = await alertsClient.get<AlertRuleResponse[]>("/rules");
    return res.data;
  },
  createRule: async (data: AlertRuleCreate): Promise<AlertRuleResponse> => {
    const res = await alertsClient.post<AlertRuleResponse>("/rules", data);
    return res.data;
  },
  deleteRule: async (ruleId: string): Promise<void> => {
    await alertsClient.delete(`/rules/${ruleId}`);
  },
  toggleRule: async (ruleId: string): Promise<AlertRuleResponse> => {
    const res = await alertsClient.patch<AlertRuleResponse>(`/rules/${ruleId}/toggle`);
    return res.data;
  },
  getEvents: async (unreadOnly = false): Promise<AlertEventResponse[]> => {
    const res = await alertsClient.get<AlertEventResponse[]>("/events", {
      params: { unread_only: unreadOnly },
    });
    return res.data;
  },
  acknowledgeEvent: async (eventId: string): Promise<void> => {
    await alertsClient.patch(`/events/${eventId}/acknowledge`);
  },
  acknowledgeAll: async (): Promise<void> => {
    await alertsClient.post("/events/acknowledge-all");
  },
};

export const analyticsApi = {
  get: async (params: { months?: number; expiry_days?: number } = {}): Promise<AnalyticsResponse> => {
    const res = await statsClient.get<AnalyticsResponse>("/analytics", { params });
    return res.data;
  },
};

export const savedQueriesApi = {
  list: async (): Promise<SavedQuery[]> => {
    const res = await savedClient.get<SavedQuery[]>("/");
    return res.data;
  },
  save: async (name: string, question: string): Promise<SavedQuery> => {
    const res = await savedClient.post<SavedQuery>("/", { name, question });
    return res.data;
  },
  delete: async (queryId: string): Promise<void> => {
    await savedClient.delete(`/${queryId}`);
  },
};

export const exportApi = {
  /** Triggers a CSV download in the browser. */
  downloadCsv: (params: { document_category?: string; review_status?: string } = {}): void => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const search = new URLSearchParams();
    if (params.document_category) search.set("document_category", params.document_category);
    if (params.review_status)     search.set("review_status", params.review_status);
    const qs = search.toString() ? `?${search.toString()}` : "";
    const url = `/api/documents/documents/export.csv${qs}`;
    const a = document.createElement("a");
    a.href = url;
    if (token) {
      // For auth-gated endpoints open in same tab; browser will follow redirect
    }
    a.download = "allergo_export.csv";
    a.click();
  },
};

export const chatApi = {
  ask: async (
    question: string,
    history: ChatMessage[],
    documentIds?: string[]
  ): Promise<ChatResponse> => {
    const res = await chatClient.post<ChatResponse>("/", {
      question,
      history,
      document_ids: documentIds,
      stream: false,
    });
    return res.data;
  },

  /** Returns a native ReadableStream for SSE — parse with parseSseStream(). */
  askStream: async (
    question: string,
    history: ChatMessage[],
    documentIds?: string[]
  ): Promise<ReadableStream<Uint8Array>> => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const resp = await fetch("/api/chat/chat/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        question,
        history,
        document_ids: documentIds,
        stream: true,
      }),
    });
    if (!resp.ok || !resp.body) throw new Error("Stream request failed");
    return resp.body;
  },
};
