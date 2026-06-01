export type HealthResponse = {
  status: string;
  vector_db?: string;
};

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
