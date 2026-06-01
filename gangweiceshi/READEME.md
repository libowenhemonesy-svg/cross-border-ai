# 跨境电商 AI 情报分析系统

## 项目概述

跨平台内容自动化沉淀工作流，演进为高阶跨境电商情报分析平台。核心能力：
- 多源内容接入（文本 / B 站视频 / n8n Webhook）
- AI 语义提取（中文摘要 + 英文逐句精读 + 标签分类）
- 向量知识检索（Qdrant + BGE-M3 Embedding）
- Obsidian Markdown 知识库自动沉淀

## 架构总览

```
┌─ 入口层 ────────────────────────────────────────────┐
│  n8n (5678)          ← 工作流编排 / Webhook 触发     │
│  Cloudflare Tunnel   ← 公网穿透 (trycloudflare.com) │
│  FastAPI (8000)      ← REST API 网关                │
└─────────────────────────────────────────────────────┘
                          ↓
┌─ AI 引擎 (硅基流动 SiliconFlow) ────────────────────┐
│  DeepSeek-V3         ← LLM 语义提取 / 长难句精读     │
│  TeleAI/TeleSpeechASR ← B 站音频转录                 │
│  BAAI/bge-m3         ← 文本向量化 (1024 维)          │
└─────────────────────────────────────────────────────┘
                          ↓
┌─ 存储层 ────────────────────────────────────────────┐
│  Obsidian Vault      ← ./obsidian_vault (Markdown)  │
│  Qdrant (6333)       ← ./qdrant_data (向量持久化)   │
└─────────────────────────────────────────────────────┘
```

## Docker 服务

| 服务 | 镜像 | 端口 | 挂载 |
|------|------|------|------|
| `n8n` | `docker.n8n.io/n8nio/n8n` | 5678 | `./n8n_data:/home/node/.n8n`, `./obsidian_vault:/obsidian` |
| `python_api` | 本地构建 `./data_extractors` | 8000 | `./obsidian_vault:/obsidian`, `./data_extractors/cookies.txt:/cookies/bilibili.txt` |
| `vector_db` | `qdrant/qdrant:latest` | 6333 | `./qdrant_data:/qdrant/storage` |
| `cloudflare_tunnel` | `cloudflare/cloudflared:latest` | - | 无（TCP 隧道） |

## 文件清单

### 根目录

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | 四服务编排，含 API Key 与挂载配置 |
| `n8n_workflow.json` | n8n 工作流导出（Webhook → Format → HTTP Request） |
| `test_trigger.py` | 向 n8n Webhook 发送中文测试数据 |
| `test_ecommerce_english.py` | 异步 POST 英文跨境电商 AI 文本到 `/api/process_content`，验证精读模块 |
| `test_bilibili.py` | 向 `/api/process_bilibili` 发送 B 站链接，验证全链路 |
| `test_scrapling_bili.py` | 验证 Scrapling 从 B 站提取元数据的核心逻辑 |
| `.gitignore` | 忽略 cookies/、n8n_data/、qdrant_data/、.env 等 |

| `n8n_workflow_bili_daily.json` | n8n 工作流：定时获取关注+收藏 → 批量处理 → 日报 → 知识库 |

### `data_extractors/` (Python 服务)

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 应用入口，5 个 API 路由 + 启动事件 |
| `ai_processor.py` | AI 核心：AsyncOpenAI + 指数退避重试 + 语言自适应 Prompt（中文模块化提取 / 英文精读） |
| `obsidian_writer.py` | Markdown 生成器：YAML frontmatter + 模块化知识卡片 + 长难句精读 Blockquote |
| `feishu_sender.py` | 飞书推送：Markdown → 飞书交互卡片 + Webhook 发送 + HMAC-SHA256 签名 |
| `bili_extractor.py` | yt-dlp 音频下载：bestaudio → FFmpeg → mp3，BV 号提取，Cookie 防风控 |
| `bili_api.py` | B站 API 统一模块：Cookie 解析、WBI 签名、收藏夹 API、关注动态 API、去重持久化 |
| `bili_scraper.py` | Scrapling 快速元数据提取：视频信息/UP主/标签/互动数据/相关推荐，1-2s 无需 Cookie |
| `audio_transcriber.py` | ASR 转录：OpenAI 兼容 Whisper API，mp3 → 文本 |
| `vector_indexer.py` | 向量索引器：MarkdownHeaderTextSplitter 分块 → BGE-M3 Embedding → Qdrant `ecommerce_knowledge` 集合，含 `search_knowledge()` 检索方法 |
| `Dockerfile` | `python:3.10-slim` + FFmpeg + pip install |
| `requirements.txt` | fastapi, uvicorn, httpx, yt-dlp, openai, qdrant-client, langchain-text-splitters |
| `cookies.txt` | B 站 Netscape 格式 Cookie（不提交 Git） |

## API 端点

### `POST /api/process_content`
文本直达 AI 提取。入参：`{title, url, raw_text}`。中文走标准摘要，英文自动触发逐句精读。

### `POST /api/process_bilibili`
B 站全链路。入参：`{url[, use_scrapling: bool]}`。流程：Scrapling 元数据增强（可选，默认开启）→ 下载音频 → ASR 转录 → AI 提取 → Obsidian 入库 → 清理临时文件。当 `use_scrapling=true`，用视频标题作文件名、元数据拼接 AI 上下文、标签合并去重。Scrapling 失败时自动降级为纯转录模式。

### `POST /api/scrape_bilibili` (NEW)
B 站视频元数据快速提取。入参：`{url}`。1-2s 内返回视频标题、描述、互动数据（播放/点赞/收藏/评论等）、UP主信息、标签、相关视频推荐等全量结构化数据。无需 Cookie，不下载音频。

### `POST /api/search_knowledge`
语义检索知识库。入参：`{query, limit}`。返回 Top-K 文本块 + 溯源信息（文件名、URL、章节层级、相似度分数）。

### `POST /api/bilibili/favorites`
获取 B站收藏夹。入参：`{uid?, media_id?, page, page_size}`。media_id 为空时列出所有收藏夹文件夹，指定时返回视频列表（分页）。使用 WBI 签名 API（收藏夹页面为 SPA 客户端渲染，无法 Scrapling 抓取）。

### `POST /api/bilibili/following`
获取关注 UP 主最新视频动态。入参：`{page, page_size}`。使用 B站 Polymer Dynamic API + WBI 签名 + Cookie。

### `POST /api/bilibili/daily` (NEW)
一键日报端点。无需 n8n Code 节点编排，一次调用完成全链路：获取关注动态 → 获取收藏夹 → 去重 → 逐个转录+AI提炼 → 生成 Markdown 报告。入参: `?max_videos=10`。返回 `{report_title, report_text, processed, skipped, failed, details}`，report_text 可直接传 `/api/process_content` 保存。

### `POST /api/bilibili/batch`
批量处理 B站视频。入参：`{videos: [BV号或URL], use_scrapling, max_videos}`。流程：去重 → 逐个下载→转录→AI→入库，每个完成后标记已处理。入参 videos 支持完整 URL 或纯 BV 号。

### `POST /api/feishu/send` (NEW)
将日报 Markdown 推送为飞书交互卡片消息。入参：`{title, content}`。内容自动解析为统计/新增/失败/待处理卡片区块。需配置 `FEISHU_WEBHOOK_URL` 环境变量。

### `GET /health`
健康检查。返回 `{status, vector_db}`。

## 关键环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_API_KEY` | (必填) | 硅基流动 API Key |
| `AI_MODEL` | `deepseek-ai/DeepSeek-V3` | LLM 模型 |
| `ASR_BASE_URL` | `https://api.siliconflow.cn/v1` | ASR 端点 |
| `ASR_MODEL` | `TeleAI/TeleSpeechASR` | 语音转录模型 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 向量化模型 (1024d) |
| `QDRANT_URL` | `http://vector_db:6333` | Qdrant 地址 (Docker 内部 DNS) |
| `FEISHU_WEBHOOK_URL` | (可选) | 飞书自定义机器人 Webhook 地址 |
| `FEISHU_WEBHOOK_SECRET` | (可选) | 飞书机器人签名校验密钥 |

## 关键技术决策

### AsyncOpenAI + 指数退避
`ai_processor.py:_call_with_retry()` 捕获 `RateLimitError`/`APITimeoutError`/`InternalServerError`，按 1s→2s→4s 重试最多 3 次。不可恢复错误（401/403）立即抛出。

### `from __future__ import annotations`
因容器基础镜像为 `python:3.9-slim`（后升至 3.10），`str | None` 联合类型语法（PEP 604）需此导入兼容。涉及 `main.py`、`bili_extractor.py`。

### Markdown 结构感知分块
`vector_indexer.py` 使用 `MarkdownHeaderTextSplitter` 按 `#/##/###` 切分，保留标题层级元数据到 Qdrant payload，检索结果可溯源到具体章节。

### Scrapling + B 站元数据提取（`bili_scraper.py`）
使用 curl_cffi 引擎模拟 TLS 指纹抓取 B 站页面，解析 `window.__INITIAL_STATE__` JSON（括号计数器法精确定位 86KB+ JSON 对象边界），1-2 秒提取标题/统计/UP主/标签/相关视频。`asyncio.to_thread()` 包装同步 Fetcher.get() 避免阻塞异步事件循环。

**与 yt-dlp 的分工**：Scrapling 负责元数据（快），yt-dlp 负责音频内容（慢），两者互补。`/api/process_bilibili` 中 Scrapling 失败自动降级。

**已知问题**：Scrapling 的 PyPI 元数据未正确声明 `browserforge`、`curl_cffi` 为依赖，需在 `requirements.txt` 中显式添加。`playwright` 也需要但仅 StealthyFetcher 使用——我们只用 Fetcher 但 Scrapling 的模块导入链会加载它。

### 确定性 UUID 幂等索引
`uuid5(DNS, "filename:chunk_index")` 保证重复索引时覆盖而非重复写入。

### 双层临时文件清理
`/api/process_bilibili` 在正常路径和 `finally` 块各执行一次 `os.remove(mp3_path)`，确保异常时也不残留音频文件。

### Cookie 防风控
B 站 403 通过 Netscape 格式 Cookie 文件绕过。`bili_extractor.py` 接收 `cookiefile` 参数，`docker-compose.yml` 挂载 `./data_extractors/cookies.txt:/cookies/bilibili.txt`。

### qdrant-client 1.18 API 差异
`search()` 方法在 1.18 中已改为 `query_points()`（返回 `QueryResponse.points`）。`vector_indexer.py` 已适配。

## 常用命令

```powershell
# 启动全部服务
docker compose up -d

# 重建 python_api（代码 / 依赖变更后）
docker compose up --build -d python_api

# 不重建注入代码（Docker Hub 不可达时的变通方案）
docker cp data_extractors/bili_scraper.py python_api:/app/
docker cp data_extractors/main.py python_api:/app/
docker compose restart python_api

# 构建向量索引
docker exec -e QDRANT_URL=http://vector_db:6333 python_api python vector_indexer.py

# 运行各测试
python test_trigger.py                # n8n Webhook 管道
python test_ecommerce_english.py      # 英文精读验证
python test_bilibili.py               # B 站全链路
python data_extractors/bili_scraper.py  # Scrapling 元数据提取

# 健康检查
curl http://localhost:8000/health

# B 站快速元数据提取（1-2s，无需 Cookie）
curl -X POST http://localhost:8000/api/scrape_bilibili \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.bilibili.com/video/BV1ize4zgEir/"}'

# 知识检索
curl -X POST http://localhost:8000/api/search_knowledge \
  -H "Content-Type: application/json" \
  -d '{"query":"向量数据库在跨境电商中的应用"}'
```

## 已知问题

1. **Scrapling 缺失依赖**：`browserforge`、`curl_cffi` 未在 Scrapling 的 PyPI 元数据中声明，需在 `requirements.txt` 中显式添加。`playwright` 虽仅 StealthyFetcher 使用，但模块导入链会加载。`Dockerfile` build 时 `pip install -r requirements.txt` 可自动解决。

2. **Docker Hub 不可达**：国内网络环境下 `docker compose up --build` 可能因无法拉取基础镜像失败。变通方案：用 `docker cp` / 管道注入代码后 `restart`。
2. **Docker Desktop 端口丢失**：Windows 休眠后端口转发可能失效，`docker restart <container>` 可恢复。
3. **Cloudflare Tunnel URL 临时性**：`trycloudflare.com` 域名在容器重启后会分配新地址。

### WBI 签名 + 收藏夹 API
`bili_api.py` 中的 `BiliFavoritesFetcher` 最初尝试 Scrapling 页面抓取 `space.bilibili.com/{uid}/favlist`，但该页面为 SPA 客户端渲染，HTML 源码中不含 `__INITIAL_STATE__`（与视频页不同）。因此改用 WBI 签名 API:
- 文件夹列表: `GET /x/v3/fav/folder/created/list` + `collected/list`（需 `up_mid` 参数）
- 视频列表: `GET /x/v3/fav/resource/list`（需 `media_id` 参数 + 完整查询参数 `keyword/order/type/tid/platform`）

`BiliFollowingFetcher` 使用 Polymer Dynamic API (`/x/polymer/web-dynamic/v1/feed/all?type=video`)，同样需要 WBI 签名。

### Scrapling Fetcher API 变更 (v0.3+)
Scrapling v0.3+ 中 `Fetcher(headers=...)` 构造方式已弃用且无效。正确方式：在 `get()` 方法调用时通过 `headers` 参数传递。`bili_scraper.py` 使用无参构造（公开页面无需 Cookie），`bili_api.py` 已完全迁移到 httpx + WBI API 方案。

### n8n 工作流 (`n8n_workflow_bili_daily.json`)
4 节点极简工作流（零 Code 节点），适用于 n8n 2.x JS Task Runner 沙箱:

1. **Schedule Trigger** (cron: `0 2 * * *`, 每天凌晨2点)
2. **HTTP Request** → `POST /api/bilibili/daily?max_videos=10` (一键完成所有编排逻辑)
3. **HTTP Request** → `POST /api/process_content` (保存 Markdown 报告到 Obsidian)
4. **HTTP Request** → `POST /api/feishu/send` (推送日报卡片到飞书群)

编排逻辑（去重、合并、批量处理、日报生成）全部在 python_api 的 `/api/bilibili/daily` 端点内完成，n8n 只负责定时触发、结果保存和飞书推送。这避免了 n8n Code 节点的沙箱兼容性问题。

导入方式: n8n UI → Import from File → 选择 JSON 文件。导入后激活即可使用。
