export type HealthResponse = {
  status: string;
  vector_db?: string;
  model_configured?: boolean;
};

export type IndexStatus = {
  status: "idle" | "running" | "succeeded" | "failed";
  chunks: number | null;
  error: string;
  finished_at: string | null;
};

export type DocumentsResponse = {
  documents: { path: string; size_bytes: number; modified_at: string }[];
  total: number;
};

export function getDocuments() {
  return request<DocumentsResponse>("/api/knowledge/documents");
}

export function getIndexStatus() {
  return request<IndexStatus>("/api/knowledge/index");
}

export function startIndex() {
  return request<IndexStatus>("/api/knowledge/index", { method: "POST" });
}

export type AskResponse = {
  status: "answered" | "insufficient_context" | "no_data";
  answer: string;
  citation_ids: number[];
  sources: (SearchResultItem & { id: number })[];
};

export type ContentResponse = {
  status: string;
  filepath: string;
  summary: string;
  key_points: string[];
  modules: { title: string; items: string[] }[];
  tags: string[];
};

export function processContent(payload: { title: string; url: string; raw_text: string }) {
  return request<ContentResponse>("/api/process_content", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function askKnowledge(question: string) {
  return request<AskResponse>("/api/ask_knowledge", {
    method: "POST",
    body: JSON.stringify({ question })
  });
}

export type BiliProcessResponse = {
  status: string;
  filepath: string;
  summary: string;
  key_points: string[];
  tags: string[];
  transcript_preview?: string;
  video_title?: string;
  video_stat?: Record<string, unknown>;
};

export type WechatProcessResponse = {
  status: string;
  filepath: string;
  summary: string;
  key_points: string[];
  tags: string[];
  title?: string;
};

export type UnifiedDailyResponse = {
  status: string;
  report_title: string;
  report_text: string;
  bili_processed?: number;
  wechat_processed?: number;
  wechat_discovered?: number;
  total_processed?: number;
  failed?: number;
  skipped?: number;
};

export type SearchResultItem = {
  text: string;
  source_file: string;
  source_url: string;
  score: number;
  h1?: string;
  h2?: string;
  h3?: string;
};

export type SearchResponse = {
  query: string;
  results: SearchResultItem[];
  total: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }

  return data as T;
}

export function getHealth() {
  return request<HealthResponse>("/health");
}

export function processBilibili(payload: { url: string; use_scrapling: boolean }) {
  return request<BiliProcessResponse>("/api/process_bilibili", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function processWechat(payload: { url: string }) {
  return request<WechatProcessResponse>("/api/process_wechat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runUnifiedDaily(maxVideos: number, maxArticles: number) {
  const params = new URLSearchParams({
    max_videos: String(maxVideos),
    max_articles: String(maxArticles)
  });
  return request<UnifiedDailyResponse>(`/api/unified_daily?${params.toString()}`, {
    method: "POST"
  });
}

export function searchKnowledge(payload: { query: string; limit: number }) {
  return request<SearchResponse>("/api/search_knowledge", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
