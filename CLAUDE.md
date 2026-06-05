# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

跨境电商 AI 智能助手，核心功能：B站视频/微信公众号文章抓取 → AI 语义提炼 → Obsidian 知识库写入 → Qdrant 向量索引 → 飞书日报推送。通过 n8n 工作流定时触发。

## 仓库结构

- `gangweiceshi/` — 核心子项目，包含 Python 后端、React 前端、Docker 编排、n8n 工作流
- `gangweiceshi/data_extractors/` — FastAPI 后端，所有数据处理逻辑
- `gangweiceshi/frontend/` — React + TypeScript + Vite 前端控制台
- `my_agent/` — LangGraph Agent 模块（独立）
- `amazon-ai-product-analyzer/` — Chrome 插件（Amazon 选品分析）
- `亚马逊/` — Obsidian 知识库文档（16+ 篇亚马逊运营文档）
- `gangweiceshi2/` — 岗位测试 Demo（独立）

## 常用命令

### Docker 部署（推荐）

```powershell
cd gangweiceshi
docker compose up -d                          # 启动全部 5 个服务
docker compose up --build -d python_api       # 代码变更后重建后端
docker compose down                            # 停止全部
```

### 本地开发

```powershell
# Python 后端
pip install -r gangweiceshi/data_extractors/requirements.txt
cd gangweiceshi/data_extractors
uvicorn main:app --host 0.0.0.0 --port 8000

# 前端
cd gangweiceshi/frontend
npm install
npm run dev                                    # Vite 开发服务器，端口 3000
npm run build                                  # 生产构建
```

### 测试

测试文件位于 `gangweiceshi/` 根目录，均为脚本式测试（非 pytest）：

```powershell
cd gangweiceshi
python test_bilibili.py                        # B站全链路测试（下载→转录→AI→入库）
python test_scrapling_bili.py                  # Scrapling 元数据提取测试
python test_ecommerce_english.py               # 英文逐句精读测试
python test_trigger.py                         # n8n Webhook 触发测试
python debug_wechat.py                         # 微信公众号调试
```

### 向量索引

```powershell
docker exec -e QDRANT_URL=http://vector_db:6333 python_api python vector_indexer.py
```

### LangGraph Agent

```powershell
langgraph serve                                # 基于 langgraph.json 配置启动
```

## 架构要点

### 数据流

```
内容源 → 数据提取器 → AI 处理器 → Obsidian 写入器 → 向量索引器
                     ↓
                 飞书推送器 ← 日报生成
```

### 后端模块职责（`gangweiceshi/data_extractors/`）

| 模块 | 职责 |
|------|------|
| `main.py` | FastAPI 入口，15+ API 路由，启动时初始化 Qdrant/Scrapling/微信服务 |
| `ai_processor.py` | AI 核心：AsyncOpenAI 调用，中英文双语 Prompt（中文知识卡片/英文逐句精读），指数退避重试 |
| `bili_scraper.py` | Scrapling 快速元数据（1-2s），curl_cffi 模拟 TLS 指纹，解析 `__INITIAL_STATE__` JSON |
| `bili_extractor.py` | yt-dlp 音频下载 → FFmpeg 转 mp3，需 Cookie 防风控 |
| `bili_api.py` | B站 WBI 签名、收藏夹/关注动态 API、Cookie 解析、去重持久化（`.bili_processed.json`） |
| `audio_transcriber.py` | ASR 转录，调用硅基流动 Whisper API |
| `wechat_extractor.py` | 微信文章提取，httpx + UA 伪装，内置 3s 频率控制 |
| `wechat_tracker.py` | 公众号追踪管理，持久化到 `.wechat_tracked/processed/queue.json` |
| `obsidian_writer.py` | Markdown 生成，YAML Frontmatter + 知识卡片 + 逐句精读 |
| `vector_indexer.py` | BGE-M3 Embedding → Qdrant，确定性 UUID 幂等写入 |
| `feishu_sender.py` | 飞书 Webhook 推送，HMAC-SHA256 签名，交互卡片格式 |

### 前端架构（`gangweiceshi/frontend/`）

React 18 + TypeScript + Vite 6 + Tailwind CSS 3。单页应用，5 个视图面板：Dashboard、BilibiliPanel、WechatPanel、DailyPanel、SearchPanel。通过 nginx 反向代理 `/api/` 到 `python_api:8000`。

### Docker 服务（`gangweiceshi/docker-compose.yml`）

| 服务 | 端口 | 说明 |
|------|------|------|
| `frontend` | 3000:80 | nginx 静态文件 + 反向代理 |
| `n8n` | 5678:5678 | 工作流编排 |
| `python_api` | 8000:8000 | FastAPI 后端 |
| `vector_db` | 6333 | Qdrant 向量数据库 |
| `cloudflare_tunnel` | — | Cloudflare Tunnel 外网访问 |

## 关键环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_API_KEY` | (必填) | 硅基流动 / OpenAI 兼容 API Key |
| `AI_MODEL` | `deepseek-ai/DeepSeek-V3` | LLM 模型 |
| `ASR_BASE_URL` | `https://api.siliconflow.cn/v1` | ASR 端点 |
| `ASR_MODEL` | `TeleAI/TeleSpeechASR` | 语音转录模型 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 向量化模型 (1024 维) |
| `QDRANT_URL` | `http://vector_db:6333` | Qdrant 地址 |
| `FEISHU_WEBHOOK_URL` | (可选) | 飞书 Webhook |
| `FEISHU_WEBHOOK_SECRET` | (可选) | 飞书签名校验密钥 |
| `VAULT_PATH` | `/obsidian` | Obsidian Vault 挂载路径 |

## 已知技术债务

1. **wechat_extractor.py div 扫描**：HTML 标签不规范时 while 循环会扫描整个页面（数十万字符），是性能瓶颈
2. **bili_scraper.py 线程安全**：Fetcher 单例通过 `asyncio.to_thread()` 并发调用，curl_cffi session 可能非线程安全
3. **bili_api.py WBI 密钥无重试**：Cookie 过期时级联失败，每次请求等 15s 超时
4. **ai_processor.py asyncio.run()**：同步包装器在异步上下文中会崩溃，当前未触发但存在维护风险
5. **批量处理超时**：B站日报顺序处理 10-20 个视频（每个 45-100s），逼近 n8n 900s 超时

## 服务访问地址

- 前端控制台：`http://localhost:3000`
- n8n 工作流：`http://localhost:5678`
- Python API：`http://localhost:8000`
- Qdrant Dashboard：`http://localhost:6333/dashboard`
- 健康检查：`GET http://localhost:8000/health`
