// Typed client for the FastAPI backend. The browser calls same-origin `/api/*`,
// which Next.js rewrites to the API (see next.config.ts), so there is no CORS.

// ---------- Types (mirroring the backend responses) ----------

export type Role = "admin" | "agent" | "viewer";

export interface DemoUser {
  email: string;
  name: string;
  role: Role;
  workspace: string;
}

export interface Me {
  user: { id: string; email: string; name: string; role: Role; workspace_id: string };
  workspace: { id: string; name: string; slug: string };
}

export interface Meta {
  llm: { enabled: boolean; model: string | null; effort: string | null };
  prompt_version: string;
  embedding_model: string;
  reranker_model: string | null;
  retrieval: {
    mode: string;
    k: number;
    candidates: number;
    rrf_k: number;
    min_rerank_score: number | null;
  };
  index: { current_chunks: number };
}

export interface Customer {
  id: string;
  external_id: string;
  name: string;
  plan: string;
  account_status: string;
}

export interface Ticket {
  id: string;
  external_id: string;
  subject: string;
  body: string;
  status: string;
  priority: string;
  tags: string[];
  created_at: string;
}

export interface Citation {
  source_id: string;
  chunk_id: string;
  document_id: string;
  document_title: string;
  filename: string;
  version_number: number;
  heading: string;
  page_start: number | null;
  page_end: number | null;
  snippet: string;
  rerank_score: number | null;
  relevance: number | null;
}

export interface ToolCallOut {
  id: string;
  tool_name: string;
  arguments: unknown;
  status: string; // ok | denied | error | timeout
  error_code: string | null;
  attempts: number;
  latency_ms: number | null;
  result: unknown;
}

export interface ProposedActionSummary {
  id: string | null;
  type: string;
  ticket_id: string;
  value: string;
  reason: string;
  error: string | null;
}

export interface QueryResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  abstained: boolean;
  missing_information: string;
  citations: Citation[];
  sources: Citation[];
  tool_calls: ToolCallOut[];
  proposed_action: ProposedActionSummary | null;
  mode: "llm" | "offline";
  model: string | null;
  warnings: string[];
  retrieval: { mode: string; trace_id: string | null; latency_ms: number };
  latency_ms: number;
}

export interface TraceCandidate {
  chunk_id: string;
  filename: string;
  heading: string;
  dense_rank: number | null;
  lexical_rank: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
  selected: boolean;
}

export interface MessageTrace {
  message: { id: string; content: string; data: Record<string, unknown> };
  retrieval: {
    query: string;
    params: Record<string, unknown>;
    results: TraceCandidate[];
    latency_ms: number;
  } | null;
  tool_calls: ToolCallOut[];
}

export type SearchMode = "dense" | "lexical" | "hybrid" | "hybrid_rerank";
export const SEARCH_MODES: SearchMode[] = ["dense", "lexical", "hybrid", "hybrid_rerank"];

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  filename: string;
  version_number: number;
  heading_path: string[];
  content: string;
  page_start: number | null;
  page_end: number | null;
  dense_rank: number | null;
  lexical_rank: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  latency_ms: number;
  params: Record<string, unknown>;
  results: SearchResult[];
}

export type IngestionStatus = "pending" | "processing" | "ready" | "failed";

export interface Version {
  id: string;
  version_number: number;
  content_hash: string;
  file_size_bytes: number;
  status: IngestionStatus;
  is_current: boolean;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface Source {
  id: string;
  title: string;
  filename: string;
  source_type: "pdf" | "markdown" | "html" | "text";
  /** Excluded from retrieval (outdated/superseded), kept for history. */
  deprecated: boolean;
  created_at: string;
  updated_at: string;
  latest_version: Version | null;
}

export interface SourceDetail extends Source {
  versions: Version[];
}

export interface UploadResult {
  document_id: string;
  title: string;
  filename: string;
  source_type: string;
  duplicate: boolean;
  version: Version;
}

export interface Chunk {
  id: string;
  chunk_index: number;
  version_number: number;
  heading_path: string[];
  content: string;
  token_count: number;
  page_start: number | null;
  page_end: number | null;
  char_start: number;
  char_end: number;
  contains_table: boolean;
  embedding_model: string | null;
}

export type ActionStatus = "pending" | "approved" | "rejected" | "executed" | "failed";

export interface Action {
  id: string;
  action_type: string;
  status: ActionStatus;
  customer: string;
  ticket: string;
  ticket_subject: string;
  value: string;
  final_value: string | null;
  reason: string;
  proposed_by: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  result: unknown;
  error: string | null;
  message_id: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string;
  data: Record<string, unknown>;
  created_at: string;
}

/** Produced by evals/run_eval.py; rendered generically, only a few keys are relied on. */
export type EvalReport = Record<string, unknown>;

// ---------- Errors ----------

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/** FastAPI errors are `{"detail": "text"}` or `{"detail": [{loc, msg}, ...]}` (422). */
function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const item = d as { loc?: unknown[]; msg?: string };
        const loc = (item.loc ?? []).filter((p) => p !== "body").join(".");
        return loc ? `${loc}: ${item.msg}` : String(item.msg ?? JSON.stringify(d));
      })
      .join("; ");
  }
  return detail == null ? "" : JSON.stringify(detail);
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return String(err);
}

// ---------- Request helper ----------

let currentUserEmail = "";

/** Set by the UserProvider; every request sends it as `X-User` (stand-in for auth). */
export function setApiUser(email: string) {
  currentUserEmail = email;
}

type Query = Record<string, string | number | boolean | null | undefined>;

async function request<T>(
  path: string,
  init: { method?: string; json?: unknown; form?: FormData; query?: Query } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (currentUserEmail) headers["X-User"] = currentUserEmail;
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.form) {
    body = init.form; // the browser sets the multipart boundary
  }

  let url = path;
  if (init.query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(init.query)) {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  let res: Response;
  try {
    res = await fetch(url, { method: init.method ?? "GET", headers, body, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    if (data && typeof data === "object" && "detail" in data) {
      detail = formatDetail((data as { detail: unknown }).detail);
    } else if (res.status >= 500 && res.status !== 503) {
      detail = "The API returned a server error (or is unreachable from the Next.js server).";
    } else if (typeof data === "string" && data) {
      detail = data.slice(0, 300);
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return data as T;
}

// ---------- Endpoints ----------

export const api = {
  users: () => request<DemoUser[]>("/api/users"),
  me: () => request<Me>("/api/me"),
  meta: () => request<Meta>("/api/meta"),

  customers: () => request<Customer[]>("/api/customers"),
  tickets: (customerId: string) => request<Ticket[]>(`/api/customers/${customerId}/tickets`),

  query: (body: {
    question: string;
    customer_id?: string | null;
    conversation_id?: string | null;
  }) => request<QueryResponse>("/api/copilot/query", { method: "POST", json: body }),
  feedback: (messageId: string, feedback: "helpful" | "unhelpful") =>
    request<void>(`/api/copilot/messages/${messageId}/feedback`, {
      method: "POST",
      json: { feedback },
    }),
  trace: (messageId: string) => request<MessageTrace>(`/api/copilot/messages/${messageId}/trace`),

  search: (q: string, mode: SearchMode, k: number) =>
    request<SearchResponse>("/api/search", { query: { q, mode, k } }),

  sources: () => request<Source[]>("/api/sources"),
  source: (id: string) => request<SourceDetail>(`/api/sources/${id}`),
  upload: (file: File, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    return request<UploadResult>("/api/sources", { method: "POST", form });
  },
  reindex: (id: string) => request<Version>(`/api/sources/${id}/reindex`, { method: "POST" }),
  setDeprecated: (id: string, deprecated: boolean) =>
    request<SourceDetail>(`/api/sources/${id}`, { method: "PATCH", json: { deprecated } }),
  chunks: (id: string) => request<Chunk[]>(`/api/sources/${id}/chunks`),

  actions: (status?: ActionStatus) => request<Action[]>("/api/actions", { query: { status } }),
  approve: (id: string, body: { edited_value?: string | null; note?: string | null }) =>
    request<Action>(`/api/actions/${id}/approve`, { method: "POST", json: body }),
  reject: (id: string, body: { note?: string | null }) =>
    request<Action>(`/api/actions/${id}/reject`, { method: "POST", json: body }),

  auditEvents: (limit = 100) => request<AuditEvent[]>("/api/audit-events", { query: { limit } }),
  latestEvaluation: () => request<EvalReport>("/api/evaluations/latest"),
};
