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
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(response.ok
      ? "服务返回了无效数据，请稍后重试。"
      : `服务返回错误（HTTP ${response.status}），请检查后端服务后重试。`);
  }

  if (!response.ok) {
    const message = data?.detail || data?.message;
    if (typeof message === "string" && message) throw new Error(message);
    if (Array.isArray(message)) {
      const details = message.map((item) => {
        if (!item || typeof item.msg !== "string") return "";
        const field = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== "body").join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      }).filter(Boolean).join("；");
      if (details) throw new Error(details);
    }
    throw new Error(`服务返回错误（HTTP ${response.status}），请稍后重试。`);
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
