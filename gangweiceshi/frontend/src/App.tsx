import {
  Activity,
  Archive,
  BookOpenText,
  CheckCircle2,
  Clipboard,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Video,
  Workflow
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  BiliProcessResponse,
  HealthResponse,
  SearchResponse,
  UnifiedDailyResponse,
  WechatProcessResponse,
  getHealth,
  processBilibili,
  processWechat,
  runUnifiedDaily,
  searchKnowledge
} from "./api";
import "./styles.css";

type View = "dashboard" | "bilibili" | "wechat" | "daily" | "search";

type AsyncState<T> = {
  loading: boolean;
  error: string;
  data: T | null;
};

const initialState = { loading: false, error: "", data: null };

function useAsyncState<T>() {
  return useState<AsyncState<T>>(initialState as AsyncState<T>);
}

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [health, setHealth] = useState<AsyncState<HealthResponse>>(initialState);

  const refreshHealth = async () => {
    setHealth({ loading: true, error: "", data: health.data });
    try {
      const data = await getHealth();
      setHealth({ loading: false, error: "", data });
    } catch (error) {
      setHealth({ loading: false, error: getErrorMessage(error), data: null });
    }
  };

  useEffect(() => {
    void refreshHealth();
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Archive size={22} />
          </div>
          <div>
            <strong>知识沉淀控制台</strong>
            <span>Bilibili / 微信 / Obsidian</span>
          </div>
        </div>

        <nav className="nav-list">
          <NavButton icon={<Activity />} label="总览" active={view === "dashboard"} onClick={() => setView("dashboard")} />
          <NavButton icon={<Video />} label="B站处理" active={view === "bilibili"} onClick={() => setView("bilibili")} />
          <NavButton icon={<FileText />} label="微信处理" active={view === "wechat"} onClick={() => setView("wechat")} />
          <NavButton icon={<Workflow />} label="统一日报" active={view === "daily"} onClick={() => setView("daily")} />
          <NavButton icon={<Search />} label="知识检索" active={view === "search"} onClick={() => setView("search")} />
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Docker Web Console</p>
            <h1>{getViewTitle(view)}</h1>
          </div>
          <button className="ghost-button" onClick={refreshHealth} disabled={health.loading}>
            {health.loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            刷新状态
          </button>
        </header>

        {view === "dashboard" && <Dashboard health={health} setView={setView} />}
        {view === "bilibili" && <BilibiliPanel />}
        {view === "wechat" && <WechatPanel />}
        {view === "daily" && <DailyPanel />}
        {view === "search" && <SearchPanel />}
      </main>
    </div>
  );
}

function Dashboard({ health, setView }: { health: AsyncState<HealthResponse>; setView: (view: View) => void }) {
  const cards = [
    { title: "B站视频处理", desc: "提交视频链接，完成音频转写、AI 摘要和 Obsidian 入库。", icon: <Video />, view: "bilibili" as View },
    { title: "微信文章处理", desc: "提交公众号文章链接，抽取正文并生成结构化知识卡片。", icon: <FileText />, view: "wechat" as View },
    { title: "统一日报", desc: "触发 B站 + 微信内容聚合，生成跨平台知识日报。", icon: <Workflow />, view: "daily" as View },
    { title: "知识检索", desc: "基于 Qdrant 对 Obsidian 内容做语义搜索。", icon: <Search />, view: "search" as View }
  ];

  return (
    <section className="stack">
      <div className="status-grid">
        <StatusTile title="python_api" value={health.data?.status ?? "unknown"} loading={health.loading} error={health.error} />
        <StatusTile title="Qdrant" value={health.data?.vector_db ?? "unknown"} loading={health.loading} error={health.error} />
      </div>

      <div className="card-grid">
        {cards.map((card) => (
          <button key={card.title} className="feature-card" onClick={() => setView(card.view)}>
            <span className="feature-icon">{card.icon}</span>
            <strong>{card.title}</strong>
            <span>{card.desc}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function BilibiliPanel() {
  const [url, setUrl] = useState("https://www.bilibili.com/video/BV1RTGs6ZEf6/");
  const [useScrapling, setUseScrapling] = useState(true);
  const [state, setState] = useAsyncState<BiliProcessResponse>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) {
      setState({ loading: false, error: "请输入 Bilibili 视频链接。", data: null });
      return;
    }
    setState({ loading: true, error: "", data: null });
    try {
      setState({ loading: false, error: "", data: await processBilibili({ url: url.trim(), use_scrapling: useScrapling }) });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), data: null });
    }
  };

  return (
    <section className="panel-layout">
      <FormCard title="处理 Bilibili 视频" description="长视频会下载音频并调用 ASR，通常需要几十秒到数分钟。">
        <form onSubmit={submit} className="form-stack">
          <TextInput label="视频链接" value={url} onChange={setUrl} placeholder="https://www.bilibili.com/video/BV..." />
          <label className="toggle-row">
            <input type="checkbox" checked={useScrapling} onChange={(event) => setUseScrapling(event.target.checked)} />
            <span>启用 Scrapling 元数据增强</span>
          </label>
          <SubmitButton loading={state.loading} label="开始处理" />
        </form>
      </FormCard>

      <ResultCard state={state}>
        {(data) => (
          <ResultBlock
            title={data.video_title || "B站处理完成"}
            summary={data.summary}
            filepath={data.filepath}
            tags={data.tags}
            extra={data.transcript_preview}
          />
        )}
      </ResultCard>
    </section>
  );
}

function WechatPanel() {
  const [url, setUrl] = useState("");
  const [state, setState] = useAsyncState<WechatProcessResponse>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) {
      setState({ loading: false, error: "请输入微信公众号文章链接。", data: null });
      return;
    }
    setState({ loading: true, error: "", data: null });
    try {
      setState({ loading: false, error: "", data: await processWechat({ url: url.trim() }) });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), data: null });
    }
  };

  return (
    <section className="panel-layout">
      <FormCard title="处理微信公众号文章" description="提交文章链接后，后端会抽取正文并写入 Obsidian。">
        <form onSubmit={submit} className="form-stack">
          <TextInput label="文章链接" value={url} onChange={setUrl} placeholder="https://mp.weixin.qq.com/s/..." />
          <SubmitButton loading={state.loading} label="开始处理" />
        </form>
      </FormCard>

      <ResultCard state={state}>
        {(data) => (
          <ResultBlock
            title={data.title || "微信文章处理完成"}
            summary={data.summary}
            filepath={data.filepath}
            tags={data.tags}
          />
        )}
      </ResultCard>
    </section>
  );
}

function DailyPanel() {
  const [maxVideos, setMaxVideos] = useState(10);
  const [maxArticles, setMaxArticles] = useState(10);
  const [state, setState] = useAsyncState<UnifiedDailyResponse>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setState({ loading: true, error: "", data: null });
    try {
      setState({ loading: false, error: "", data: await runUnifiedDaily(maxVideos, maxArticles) });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), data: null });
    }
  };

  return (
    <section className="panel-layout">
      <FormCard title="生成统一日报" description="调用 B站 + 微信聚合接口，适合手动触发每日知识沉淀。">
        <form onSubmit={submit} className="form-stack">
          <NumberInput label="最多处理 B站视频数" value={maxVideos} onChange={setMaxVideos} min={1} max={20} />
          <NumberInput label="最多处理微信文章数" value={maxArticles} onChange={setMaxArticles} min={1} max={30} />
          <SubmitButton loading={state.loading} label="生成日报" />
        </form>
      </FormCard>

      <ResultCard state={state}>
        {(data) => (
          <div className="result-stack">
            <h2>{data.report_title}</h2>
            <div className="metrics">
              <Metric label="B站" value={data.bili_processed ?? "-"} />
              <Metric label="微信" value={data.wechat_processed ?? "-"} />
              <Metric label="发现文章" value={data.wechat_discovered ?? "-"} />
            </div>
            <CopyButton value={data.report_text} label="复制日报内容" />
            <pre className="report-box">{data.report_text}</pre>
          </div>
        )}
      </ResultCard>
    </section>
  );
}

function SearchPanel() {
  const [query, setQuery] = useState("跨境电商选品");
  const [limit, setLimit] = useState(5);
  const [state, setState] = useAsyncState<SearchResponse>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) {
      setState({ loading: false, error: "请输入检索关键词。", data: null });
      return;
    }
    setState({ loading: true, error: "", data: null });
    try {
      setState({ loading: false, error: "", data: await searchKnowledge({ query: query.trim(), limit }) });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), data: null });
    }
  };

  return (
    <section className="panel-layout">
      <FormCard title="语义检索知识库" description="从 Obsidian 知识库向量索引中搜索相关内容片段。">
        <form onSubmit={submit} className="form-stack">
          <TextInput label="查询词" value={query} onChange={setQuery} placeholder="例如：亚马逊广告优化" />
          <NumberInput label="返回数量" value={limit} onChange={setLimit} min={1} max={10} />
          <SubmitButton loading={state.loading} label="开始检索" />
        </form>
      </FormCard>

      <ResultCard state={state}>
        {(data) => (
          <div className="result-stack">
            <h2>检索结果：{data.query}</h2>
            {data.results.map((item, index) => (
              <article className="search-result" key={`${item.source_file}-${index}`}>
                <div className="search-meta">
                  <strong>{item.source_file}</strong>
                  <span>score {item.score.toFixed(3)}</span>
                </div>
                <p>{item.text}</p>
                {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a>}
              </article>
            ))}
          </div>
        )}
      </ResultCard>
    </section>
  );
}

function NavButton({ icon, label, active, onClick }: { icon: ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button className={`nav-button ${active ? "active" : ""}`} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function StatusTile({ title, value, loading, error }: { title: string; value: string; loading: boolean; error: string }) {
  const ok = !error && value && value !== "unknown";
  return (
    <div className="status-tile">
      <span>{title}</span>
      <strong className={ok ? "ok" : "bad"}>
        {loading ? <Loader2 className="spin" size={18} /> : ok ? <CheckCircle2 size={18} /> : null}
        {error || value}
      </strong>
    </div>
  );
}

function FormCard({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      <p className="muted">{description}</p>
      {children}
    </section>
  );
}

function ResultCard<T>({ state, children }: { state: AsyncState<T>; children: (data: T) => ReactNode }) {
  return (
    <section className="card result-card">
      <h2>执行结果</h2>
      {state.loading && <LoadingBlock />}
      {state.error && <div className="error-box">{state.error}</div>}
      {!state.loading && !state.error && !state.data && <EmptyBlock />}
      {state.data && children(state.data)}
    </section>
  );
}

function ResultBlock({ title, summary, filepath, tags, extra }: { title: string; summary: string; filepath: string; tags: string[]; extra?: string }) {
  return (
    <div className="result-stack">
      <h2>{title}</h2>
      <p>{summary}</p>
      <div className="tag-list">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      <div className="copy-row">
        <CopyButton value={summary} label="复制摘要" />
        <CopyButton value={filepath} label="复制文件路径" />
      </div>
      <code className="file-path">{filepath}</code>
      {extra && <pre className="report-box">{extra}</pre>}
    </div>
  );
}

function TextInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberInput({ label, value, onChange, min, max }: { label: string; value: number; onChange: (value: number) => void; min: number; max: number }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function SubmitButton({ loading, label }: { loading: boolean; label: string }) {
  return (
    <button className="primary-button" disabled={loading}>
      {loading ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
      {loading ? "处理中" : label}
    </button>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const disabled = !value;
  const copy = async () => {
    if (disabled) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <button className="secondary-button" onClick={copy} disabled={disabled}>
      <Clipboard size={15} />
      {copied ? "已复制" : label}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function LoadingBlock() {
  return (
    <div className="empty-block">
      <Loader2 className="spin" size={24} />
      <span>任务执行中，长视频或日报任务可能需要数分钟。</span>
    </div>
  );
}

function EmptyBlock() {
  return (
    <div className="empty-block">
      <BookOpenText size={24} />
      <span>提交任务后，这里会显示处理结果。</span>
    </div>
  );
}

function getViewTitle(view: View) {
  return {
    dashboard: "系统总览",
    bilibili: "B站视频处理",
    wechat: "微信公众号处理",
    daily: "统一日报",
    search: "知识库检索"
  }[view];
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export default App;
