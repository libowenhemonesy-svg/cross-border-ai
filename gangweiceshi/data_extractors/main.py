"""
FastAPI Web 服务 — 内容提取 / 向量检索 / Bilibili 音频转录全链路
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from ai_processor import AIProcessor
from audio_transcriber import transcribe_audio
from bili_extractor import download_bili_audio
from bili_api import (
    BiliFavoritesFetcher,
    BiliFollowingFetcher,
    filter_new_videos,
    is_processed,
    mark_processed,
    get_processed_stats,
    get_uid_from_cookies,
)
from bili_scraper import BilibiliScraper
from feishu_sender import send_daily_report as send_feishu_report
from wechat_extractor import WechatExtractor, WechatArticle
from wechat_tracker import WechatTracker, TrackedAccount
from obsidian_writer import write_to_vault, sanitize_filename
from vector_indexer import VectorIndexer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Content Processor", version="3.0")

# ── 常量 ──
TZ = timezone(timedelta(hours=8))
VAULT_PATH = "/obsidian"
QDRANT_URL = os.getenv("QDRANT_URL", "http://vector_db:6333")
API_KEY = os.getenv("AI_API_KEY", "your-api-key-here")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# ASR 配置（可替换为任意 OpenAI 兼容 Whisper 端点）
ASR_BASE_URL = os.getenv("ASR_BASE_URL", "https://api.siliconflow.cn/v1")
ASR_MODEL = os.getenv("ASR_MODEL", "TeleAI/TeleSpeechASR")

# ── 全局处理器实例 ──
processor = AIProcessor(
    api_key=API_KEY,
    model=os.getenv("AI_MODEL", "deepseek-ai/DeepSeek-V3"),
)

vector_indexer: VectorIndexer | None = None
bili_scraper: BilibiliScraper | None = None
wechat_extractor: WechatExtractor | None = None
wechat_tracker: WechatTracker | None = None


@app.on_event("startup")
async def startup_event():
    """启动时连接 Qdrant 向量数据库 + 初始化 Scrapling"""
    global vector_indexer, bili_scraper, wechat_extractor, wechat_tracker
    try:
        vector_indexer = VectorIndexer(
            qdrant_url=QDRANT_URL,
            api_key=API_KEY,
            embedding_model=EMBEDDING_MODEL,
        )
        logger.info(f"向量索引器已连接 → {QDRANT_URL}")
    except Exception as e:
        logger.error(f"向量索引器初始化失败（Qdrant 可能未就绪）: {e}")
        logger.error("知识检索 API 将不可用，其他功能正常")

    try:
        bili_scraper = BilibiliScraper()
        logger.info("BilibiliScraper (Scrapling) 已初始化")
    except Exception as e:
        logger.error(f"Scrapling 初始化失败: {e}")
        logger.error("/api/scrape_bilibili 将不可用，其他 B 站功能不受影响")

    try:
        wechat_extractor = WechatExtractor()
        logger.info("WechatExtractor (Scrapling) 已初始化")
    except Exception as e:
        logger.error(f"WechatExtractor 初始化失败: {e}")
        logger.error("/api/process_wechat 将不可用")

    try:
        wechat_tracker = WechatTracker(vault_path=VAULT_PATH)
        logger.info(f"WechatTracker 已初始化（追踪 {len(wechat_tracker.get_accounts())} 个账号）")
    except Exception as e:
        logger.error(f"WechatTracker 初始化失败: {e}")
        logger.error("/api/wechat/daily 将不可用")


# ── 请求日志中间件 ──


@app.middleware("http")
async def log_request_body(request: Request, call_next):
    body = await request.body()
    logger.info(f"[{request.method} {request.url.path}] body={body.decode()[:500]}")
    return await call_next(request)


# ═══════════════════════════════════════════════════════════════════
#  API 模型
# ═══════════════════════════════════════════════════════════════════


class ProcessRequest(BaseModel):
    title: str
    url: str = ""
    raw_text: str


class ProcessResponse(BaseModel):
    status: str
    filepath: str
    summary: str
    key_points: list[str]
    modules: list[dict] = []   # v4.0 模块化知识卡片
    tags: list[str]


class SearchRequest(BaseModel):
    query: str
    limit: int = 3


class SearchResultItem(BaseModel):
    text: str
    source_file: str
    source_url: str
    score: float
    h1: str = ""
    h2: str = ""
    h3: str = ""


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class BiliProcessRequest(BaseModel):
    url: str
    use_scrapling: bool = True  # 默认启用 Scrapling 元数据增强


class BiliProcessResponse(BaseModel):
    status: str
    filepath: str
    summary: str
    key_points: list[str]
    modules: list[dict] = []   # v4.0 模块化知识卡片
    tags: list[str]
    transcript_preview: str = ""  # 转录文本前 200 字预览
    video_title: str = ""         # Scrapling 获取的视频标题
    video_stat: dict = {}         # Scrapling 获取的互动数据


class ScrapeBiliRequest(BaseModel):
    url: str
    save_to_vault: bool = False  # 是否同时保存为 Obsidian .md 笔记


class ScrapeBiliResponse(BaseModel):
    status: str
    bvid: str
    title: str
    description: str
    cover_url: str
    tags: list[dict]
    stat: dict
    pubdate: str
    tname: str
    owner: dict
    related_videos: list[dict]
    filepath: str = ""  # save_to_vault=True 时返回保存路径


# ── B站 自动化端点模型 ──


class BiliFavoritesRequest(BaseModel):
    uid: int = 0
    media_id: int | None = None  # None=列出所有收藏夹文件夹, 指定值=获取该文件夹视频
    page: int = 1
    page_size: int = 20


class BiliFavoritesResponse(BaseModel):
    status: str
    folders: list[dict] = []   # media_id=None 时返回
    videos: list[dict] = []    # media_id 指定时返回
    total: int = 0
    has_more: bool = False
    page: int = 1


class BiliFollowingRequest(BaseModel):
    page: int = 1
    page_size: int = 20


class BiliFollowingResponse(BaseModel):
    status: str
    videos: list[dict] = []
    total: int = 0
    has_more: bool = False
    page: int = 1


class BiliBatchRequest(BaseModel):
    videos: list[str]  # BV 号或完整 URL 列表
    use_scrapling: bool = True
    max_videos: int = 10


class BiliBatchResult(BaseModel):
    bvid: str
    title: str = ""
    status: str = ""  # "ok" | "failed" | "skipped"
    filepath: str = ""
    error: str = ""
    summary: str = ""     # AI 核心摘要
    modules: list[dict] = []  # 知识模块


class BiliBatchResponse(BaseModel):
    status: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[BiliBatchResult] = []


class BiliDailyResponse(BaseModel):
    """一键日报响应: 获取关注+收藏 → 去重 → 批量处理 → 生成报告"""
    status: str
    report_title: str = ""
    report_text: str = ""
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    details: list[BiliBatchResult] = []


class FeishuSendRequest(BaseModel):
    """飞书推送请求"""
    title: str
    content: str      # Markdown 格式的报告正文


class FeishuSendResponse(BaseModel):
    """飞书推送响应"""
    status: str
    message: str = ""


class WechatQueueRequest(BaseModel):
    """手动添加微信文章到处理队列"""
    url: str


class WechatQueueResponse(BaseModel):
    """队列操作响应"""
    status: str
    message: str = ""
    url: str = ""


class WechatProcessRequest(BaseModel):
    """微信公众号文章处理请求"""
    url: str


class WechatProcessResponse(BaseModel):
    """微信公众号文章处理响应"""
    status: str
    filepath: str
    title: str
    author: str = ""
    publish_time: str = ""
    summary: str
    key_points: list[str]
    modules: list[dict]
    tags: list[str]
    image_count: int = 0


class WechatTrackRequest(BaseModel):
    """添加微信公众号追踪请求"""
    url: str  # 该公众号的任意一篇历史文章链接


class WechatTrackResponse(BaseModel):
    """添加追踪响应"""
    status: str
    biz: str = ""
    name: str = ""
    message: str = ""


class WechatDailyResponse(BaseModel):
    """微信公众号日报响应"""
    status: str
    report_title: str = ""
    report_text: str = ""
    processed: int = 0
    discovered: int = 0
    details: list[dict] = []


class UnifiedDailyResponse(BaseModel):
    """全平台统一日报响应: B站 + 微信 合并报告"""
    status: str
    report_title: str = ""
    report_text: str = ""
    bili_processed: int = 0
    wechat_processed: int = 0
    wechat_discovered: int = 0
    new_items: list[dict] = []  # 飞书卡片用: [{title, summary, link, source}]


# ═══════════════════════════════════════════════════════════════════
#  内容处理 API
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/process_content", response_model=ProcessResponse)
async def process_content(req: ProcessRequest):
    if not req.raw_text or not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text 不能为空")

    # 1. AI 提取（异步，含指数退避重试 + 英文自动精读）
    extracted = await processor.extract_async(req.raw_text, source_url=req.url)

    # 2. 写入 Obsidian Vault
    data = asdict(extracted)
    filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=req.title)

    return ProcessResponse(
        status="ok",
        filepath=filepath,
        summary=extracted.summary,
        key_points=extracted.key_points,
        modules=extracted.modules,
        tags=extracted.tags,
    )


# ═══════════════════════════════════════════════════════════════════
#  B 站快速信息采集 API（Scrapling，无需 Cookie）
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/scrape_bilibili", response_model=ScrapeBiliResponse)
async def scrape_bilibili(req: ScrapeBiliRequest):
    """从 B 站视频页快速提取元数据（1-2s，无需 Cookie）

    通过 Scrapling 反检测引擎抓取页面，解析内嵌 __INITIAL_STATE__ JSON，
    获取标题、描述、标签、互动数据、UP主信息、相关视频推荐等结构化元数据。

    与 /api/process_bilibili 的区别:
      - 本端点: 纯元数据，1-2s 返回，适合快速查看/搜索
      - process_bilibili: 音频→转录→AI 提炼，45-100s，适合深度学习
    """
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    if bili_scraper is None:
        raise HTTPException(
            status_code=503,
            detail="B 站采集器未就绪，请检查 Scrapling 是否正常安装",
        )

    try:
        meta = await asyncio.to_thread(
            bili_scraper.extract_video_meta, req.url.strip()
        )

        # 可选：将元数据写入 Obsidian 知识库
        filepath = ""
        if req.save_to_vault:
            tag_names = ", ".join(t.get("tag_name", "") for t in meta.tags)
            scraped_text = (
                f"【视频标题】{meta.title}\n"
                f"【UP主】{meta.owner.get('name', '')}\n"
                f"【视频简介】{meta.description}\n"
                f"【标签】{tag_names}\n"
                f"【发布时间】{meta.pubdate}\n"
                f"【播放量】{meta.stat.get('view', 0)} | "
                f"点赞 {meta.stat.get('like', 0)} | "
                f"收藏 {meta.stat.get('favorite', 0)}\n"
            )
            # 添加相关视频
            if meta.related_videos:
                scraped_text += "\n【相关视频推荐】\n"
                for r in meta.related_videos[:5]:
                    scraped_text += f"- {r['title']} (播放:{r['play_count']} UP:{r['author']})\n"

            # 用元数据调用 AI 提炼
            extracted = await processor.extract_async(
                scraped_text,
                source_url=req.url.strip(),
            )
            # 合并标签
            scraper_tags = [t.get("tag_name", "") for t in meta.tags]
            merged = set(scraper_tags + extracted.tags)
            extracted.tags = list(merged)[:10]

            filename = sanitize_filename(meta.title) if meta.title else meta.bvid
            data = asdict(extracted)
            filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=filename)
            logger.info(f"[Scrape] 已保存到 Obsidian: {filepath}")

        return ScrapeBiliResponse(
            status="ok",
            bvid=meta.bvid,
            title=meta.title,
            description=meta.description,
            cover_url=meta.cover_url,
            tags=meta.tags,
            stat=meta.stat,
            pubdate=meta.pubdate,
            tname=meta.tname,
            owner=meta.owner,
            related_videos=meta.related_videos,
            filepath=filepath,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[Scrape] 未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"采集失败: {e}")


# ═══════════════════════════════════════════════════════════════════
#  Bilibili 音频转录全链路 API
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/process_bilibili", response_model=BiliProcessResponse)
async def process_bilibili(req: BiliProcessRequest):
    """B 站视频 → [元数据增强] → 音频 → 转录 → AI 语义处理 → Obsidian 知识库

    全链路流程（严格顺序）：
      ① [可选] Scrapling 预取视频元数据（标题、标签、描述，1-2s）
      ② yt-dlp + FFmpeg 下载最佳音频流 → mp3
      ③ OpenAI 兼容 Whisper API 转录 → 长文本
      ④ 拼接元数据上下文 + 转录文本 → AI 语义提炼
      ⑤ 写入 Obsidian Vault（Markdown + YAML Frontmatter）
      ⑥ 清理 /tmp 临时音频文件

    当 use_scrapling=True（默认）且 Scrapling 成功时:
      - 文件名使用视频标题（而非 BV 号）
      - AI 上下文包含标题+描述+标签，提炼质量更高
      - 标签来自 Scrapling + AI 双重来源，合并去重

    当 use_scrapling=False 或 Scrapling 失败时:
      - 降级为纯转录模式（与旧版行为一致）
    """
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    mp3_path: str | None = None

    # ── ① [可选] Scrapling 元数据预取 ──
    video_meta = None
    if req.use_scrapling and bili_scraper is not None:
        try:
            video_meta = await asyncio.to_thread(
                bili_scraper.extract_video_meta, req.url.strip()
            )
            logger.info(f"[Bili] Scrapling 元数据获取成功: {video_meta.title}")
        except Exception as e:
            logger.warning(f"[Bili] Scrapling 元数据获取失败，降级为纯转录模式: {e}")

    try:
        # ── ② 下载 B 站音频 ──
        logger.info(f"[Bili] 开始处理: {req.url}")
        mp3_path = download_bili_audio(
            url=req.url.strip(),
            cookiefile="/cookies/bilibili.txt",
        )

        # ── ③ ASR 转录 ──
        transcript_text = transcribe_audio(
            file_path=mp3_path,
            api_key=API_KEY,
            base_url=ASR_BASE_URL,
            model=ASR_MODEL,
        )

        if not transcript_text or not transcript_text.strip():
            raise HTTPException(
                status_code=422, detail="转录结果为空，音频可能无有效语音内容"
            )

        logger.info(f"[Bili] 转录成功: {len(transcript_text)} 字符")

        # ── ④ 构建增强 AI 输入（元数据 + 转录文本）──
        from bili_extractor import extract_bv_id
        bv_id = extract_bv_id(req.url.strip())

        if video_meta:
            # 用视频标题作为文件名
            title = sanitize_filename(video_meta.title) if video_meta.title else f"B站视频_{bv_id}"
            # 构建增强上下文：标题 → 描述 → 标签 → 转录
            tag_names = ", ".join(t.get("tag_name", "") for t in video_meta.tags)
            enriched_text = (
                f"【视频标题】{video_meta.title}\n"
                f"【UP主】{video_meta.owner.get('name', '')}\n"
                f"【视频简介】{video_meta.description}\n"
                f"【原始标签】{tag_names}\n"
                f"【播放量】{video_meta.stat.get('view', 0)}\n"
                f"---\n"
                f"{transcript_text}"
            )
        else:
            title = f"B站视频_{bv_id}"
            enriched_text = transcript_text

        # ── ⑤ AI 语义处理 ──
        extracted = await processor.extract_async(
            enriched_text,
            source_url=req.url.strip(),
        )

        # 合并标签：Scrapling 标签 + AI 标签，去重
        if video_meta:
            scraper_tags = [t.get("tag_name", "") for t in video_meta.tags]
            merged = set(scraper_tags + extracted.tags)
            extracted.tags = list(merged)[:10]

        # ── ⑥ 写入 Obsidian Vault ──
        data = asdict(extracted)
        filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=title)

        # ── ⑦ 清理临时音频文件 ──
        if mp3_path and os.path.isfile(mp3_path):
            os.remove(mp3_path)
            logger.info(f"[Bili] 已清理临时文件: {mp3_path}")
            mp3_path = None

        transcript_preview = transcript_text[:200]

        logger.info(f"[Bili] 全链路完成 → {filepath}")
        return BiliProcessResponse(
            status="ok",
            filepath=filepath,
            summary=extracted.summary,
            key_points=extracted.key_points,
            modules=extracted.modules,
            tags=extracted.tags,
            transcript_preview=transcript_preview,
            video_title=video_meta.title if video_meta else "",
            video_stat=video_meta.stat if video_meta else {},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bili] 全链路失败: {e}")
        raise HTTPException(status_code=500, detail=f"Bilibili 处理失败: {e}")

    finally:
        # 兜底清理：确保无论成功与否都删除临时 mp3
        if mp3_path and os.path.isfile(mp3_path):
            os.remove(mp3_path)
            logger.info(f"[Bili] 异常流程清理: {mp3_path}")


# ── 微信公众号处理端点 ──


def _build_wechat_ai_input(article: WechatArticle) -> str:
    """将微信文章元数据拼接为 AI 增强输入"""
    parts = []
    if article.title:
        parts.append(f"【文章标题】{article.title}")
    if article.author:
        parts.append(f"【公众号】{article.author}")
    if article.publish_time:
        parts.append(f"【发布时间】{article.publish_time}")
    if parts:
        parts.append("---")
    parts.append(article.content_text)
    return "\n".join(parts)


@app.post("/api/process_wechat", response_model=WechatProcessResponse)
async def process_wechat(req: WechatProcessRequest):
    """微信公众号文章 → 内容提取 → AI 语义处理 → Obsidian 知识库

    三步走流程：
      1. Scrapling 反检测引擎抓取页面 → 解析标题/公众号/正文/图片
      2. 拼接元数据 + 正文 → AI 语义提炼（模块化知识卡片）
      3. 写入 Obsidian Vault（Markdown + YAML Frontmatter）
    """
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    if wechat_extractor is None:
        raise HTTPException(
            status_code=503,
            detail="微信提取器未就绪，请检查 Scrapling 是否正常安装",
        )

    try:
        # ① 抓取 + 解析（同步方法，asyncio.to_thread 包装避免阻塞事件循环）
        article = await asyncio.to_thread(
            wechat_extractor.extract, req.url.strip()
        )

        # ② 构建 AI 输入
        enriched_text = _build_wechat_ai_input(article)

        # ③ AI 语义处理
        extracted = await processor.extract_async(
            enriched_text,
            source_url=req.url.strip(),
        )

        # ④ 追加来源标签
        source_tags = ["微信公众号"]
        if article.author:
            source_tags.append(f"来源:{article.author}")
        merged = set(source_tags + extracted.tags)
        extracted.tags = list(merged)[:10]

        # ⑤ 写入 Obsidian
        if article.title:
            filename = sanitize_filename(article.title)
        else:
            filename = f"微信文章_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}"

        data = asdict(extracted)
        filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=filename)

        logger.info(f"[Wechat] 全链路完成 → {filepath}")

        return WechatProcessResponse(
            status="ok",
            filepath=filepath,
            title=article.title,
            author=article.author,
            publish_time=article.publish_time,
            summary=extracted.summary,
            key_points=extracted.key_points,
            modules=extracted.modules,
            tags=extracted.tags,
            image_count=len(article.images),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[Wechat] 未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"微信文章处理失败: {e}")


# ── 微信文章手动队列 API ──


@app.post("/api/wechat/queue", response_model=WechatQueueResponse)
async def wechat_queue(req: WechatQueueRequest):
    """手动添加微信公众号文章到处理队列

    将文章 URL 加入待处理队列，下次 /api/unified_daily 或
    /api/wechat/daily 运行时自动处理并推送飞书。
    """
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    if wechat_tracker is None:
        raise HTTPException(status_code=503, detail="微信追踪器未就绪")

    ok, msg = wechat_tracker.queue_article(req.url.strip())
    return WechatQueueResponse(
        status="ok" if ok else "skipped",
        message=msg,
        url=req.url.strip(),
    )


@app.get("/api/wechat/queue", response_model=dict)
async def wechat_queue_list():
    """查看当前队列中的文章 URL"""
    if wechat_tracker is None:
        raise HTTPException(status_code=503, detail="微信追踪器未就绪")

    return {
        "count": len(wechat_tracker._queue),
        "urls": wechat_tracker.get_queue(),
    }


# ── 微信公众号追踪 API ──


@app.post("/api/wechat/track", response_model=WechatTrackResponse)
async def wechat_track(req: WechatTrackRequest):
    """添加一个微信公众号到追踪列表

    提供该公众号的任意一篇历史文章链接，系统自动提取账号信息并开始追踪。
    后续 /api/wechat/daily 会自动发现该号的新文章。
    """
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    if wechat_tracker is None:
        raise HTTPException(status_code=503, detail="微信追踪器未就绪")

    try:
        acc = wechat_tracker.add_account(req.url.strip())
        return WechatTrackResponse(
            status="ok",
            biz=acc.biz,
            name=acc.name,
            message=f"已开始追踪「{acc.name or acc.biz}」",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[WechatTrack] 错误: {e}")
        raise HTTPException(status_code=500, detail=f"添加追踪失败: {e}")


@app.get("/api/wechat/accounts")
async def wechat_accounts():
    """列出当前所有追踪的微信公众号"""
    if wechat_tracker is None:
        raise HTTPException(status_code=503, detail="微信追踪器未就绪")

    accounts = wechat_tracker.get_accounts()
    return {
        "count": len(accounts),
        "accounts": [
            {"biz": a.biz, "name": a.name, "article_count": a.article_count, "added_at": a.added_at}
            for a in accounts
        ],
    }


@app.post("/api/wechat/daily", response_model=WechatDailyResponse)
async def wechat_daily(max_articles: int = 10):
    """一键日报端点：发现追踪账号的新文章 → AI 提炼 → 生成 Markdown 报告"""
    try:
        report_title, report_text, processed, discovered, _ = await _run_wechat_daily(max_articles)
        return WechatDailyResponse(
            status="ok",
            report_title=report_title,
            report_text=report_text,
            processed=processed,
            discovered=discovered,
            details=[],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"[WechatDaily] 失败: {e}")
        raise HTTPException(status_code=500, detail=f"日报生成失败: {e}")


# ── 内部辅助：单视频全链路处理（供 /api/bilibili/batch 复用）──


# ── 内部辅助：单视频全链路处理（供 /api/bilibili/batch 复用）──


async def _process_single_bili_video(
    url: str, use_scrapling: bool = True
) -> dict:
    """处理单个 B站视频：Scrapling 元数据 + 音频下载 → ASR 转录 → AI 提炼 → Obsidian 入库"""
    from bili_extractor import extract_bv_id

    bv_id = extract_bv_id(url)
    video_link = f"https://www.bilibili.com/video/{bv_id}/"
    result = {"bvid": bv_id, "title": "", "status": "failed", "filepath": "", "error": "", "summary": "", "modules": [], "link": video_link}

    # ① Scrapling 元数据提取
    video_meta = None
    if use_scrapling and bili_scraper is not None:
        try:
            video_meta = await asyncio.to_thread(
                bili_scraper.extract_video_meta, url
            )
        except Exception as e:
            logger.warning(f"[Batch] Scrapling 失败: {e}")
            result["error"] = f"Scrapling 失败: {e}"
            return result

    if video_meta is None:
        result["error"] = "无法获取视频元数据"
        return result

    title = sanitize_filename(video_meta.title) if video_meta.title else f"B站视频_{bv_id}"
    result["title"] = title
    mp3_path = f"/tmp/{bv_id}.mp3"

    try:
        # ② 下载音频（yt-dlp → mp3），带 Cookie 防风控
        logger.info(f"[Batch] 开始下载音频: {bv_id}")
        dl_result = await asyncio.to_thread(
            download_bili_audio, url, output_dir="/tmp",
            cookiefile="/cookies/bilibili.txt" if os.path.isfile("/cookies/bilibili.txt") else None,
        )
        if dl_result and os.path.isfile(dl_result):
            mp3_path = dl_result  # 使用 download_bili_audio 返回的实际路径
        elif not os.path.isfile(mp3_path):
            mp3_path = ""
            logger.warning(f"[Batch] 音频下载失败，降级为纯元数据模式: {bv_id}")
    except Exception as e:
        mp3_path = ""
        logger.warning(f"[Batch] 音频下载异常，降级为纯元数据模式: {e}")

    try:
        # ③ 构建 AI 输入
        tag_names = ", ".join(t.get("tag_name", "") for t in video_meta.tags)
        parts = [
            f"【视频标题】{video_meta.title}",
            f"【视频链接】{video_link}",
            f"【UP主】{video_meta.owner.get('name', '')}",
            f"【视频简介】{video_meta.description}",
            f"【原始标签】{tag_names}",
            f"【播放量】{video_meta.stat.get('view', 0)} | "
            f"点赞: {video_meta.stat.get('like', 0)} | "
            f"收藏: {video_meta.stat.get('favorite', 0)}",
        ]

        # ④ ASR 转录
        transcript = ""
        if mp3_path:
            try:
                logger.info(f"[Batch] 开始 ASR 转录: {bv_id}")
                transcript = await asyncio.to_thread(
                    transcribe_audio, mp3_path,
                    api_key=API_KEY, base_url=ASR_BASE_URL, model=ASR_MODEL,
                )
                if transcript and transcript.strip():
                    parts.append(f"\n--- 以下为视频语音转录文本 ---\n{transcript}")
                    logger.info(f"[Batch] ASR 转录成功: {bv_id} ({len(transcript)} 字)")
            except Exception as e:
                logger.warning(f"[Batch] ASR 转录失败，继续使用元数据: {e}")

        enriched_text = "\n".join(parts)

        # ⑤ AI 语义处理
        extracted = await processor.extract_async(enriched_text, source_url=video_link)

        scraper_tags = [t.get("tag_name", "") for t in video_meta.tags]
        merged = set(scraper_tags + extracted.tags)
        extracted.tags = list(merged)[:10]

        # ⑥ 写入 Obsidian Vault（含转录原文）
        data = asdict(extracted)
        data["full_text"] = transcript  # 触发 obsidian_writer 的「原文实录」章节
        filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=title)
        result["filepath"] = filepath
        result["status"] = "ok"
        result["summary"] = extracted.summary
        result["modules"] = extracted.modules

    except Exception as e:
        logger.error(f"[Batch] 处理失败 {bv_id}: {e}")
        result["error"] = str(e)[:200]
    finally:
        # ⑦ 清理临时 mp3
        if mp3_path and os.path.isfile(mp3_path):
            try:
                os.remove(mp3_path)
            except Exception:
                pass

    return result


# ═══════════════════════════════════════════════════════════════════
#  B站 自动化端点 (n8n 工作流驱动)
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/bilibili/favorites", response_model=BiliFavoritesResponse)
async def bilibili_favorites(req: BiliFavoritesRequest):
    """获取 B站收藏夹内容

    - media_id 为空时: 列出所有公开收藏夹文件夹
    - media_id 指定时: 返回该收藏夹内的视频列表（分页）

    需要有效的 Cookie (cookies.txt) 才能访问用户专属收藏夹数据。
    """
    fetcher = BiliFavoritesFetcher()
    uid = req.uid if req.uid > 0 else get_uid_from_cookies()

    if uid == 0:
        raise HTTPException(
            status_code=400,
            detail="无法获取用户 UID，请在请求中提供 uid 或确保 cookies.txt 有效",
        )

    try:
        if req.media_id is None:
            folders = await fetcher.list_folders(uid)
            return BiliFavoritesResponse(
                status="ok",
                folders=[{
                    "media_id": f.media_id,
                    "title": f.title,
                    "media_count": f.media_count,
                } for f in folders],
            )
        else:
            result = await fetcher.get_folder_videos(
                uid, req.media_id, req.page, req.page_size,
            )
            return BiliFavoritesResponse(
                status="ok",
                videos=[asdict(v) for v in result.items],
                total=result.total,
                has_more=result.has_more,
                page=result.page,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[Favorites] 未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取收藏夹失败: {e}")


@app.post("/api/bilibili/following", response_model=BiliFollowingResponse)
async def bilibili_following(req: BiliFollowingRequest):
    """获取关注 UP 主的最新视频动态

    通过 B站 Polymer Dynamic API (WBI 签名 + Cookie) 获取已登录用户的
    关注列表中的最新视频投稿。需要有效的 Cookie (cookies.txt)。
    """
    fetcher = BiliFollowingFetcher()

    try:
        result = await fetcher.get_following_feed(
            page=req.page, page_size=req.page_size,
        )
        return BiliFollowingResponse(
            status="ok",
            videos=[asdict(v) for v in result.items],
            total=result.total,
            has_more=result.has_more,
            page=result.page,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[Following] 未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取关注动态失败: {e}")


@app.post("/api/bilibili/batch", response_model=BiliBatchResponse)
async def bilibili_batch(req: BiliBatchRequest):
    """批量处理 B站视频：去重 → 下载 → 转录 → AI 提炼 → Obsidian 入库

    入参 videos 可以是完整 URL 或纯 BV 号，自动规范化。
    每个视频处理完成后立即标记已处理，避免重复。
    max_videos 限制单次批量处理的上限（默认 10）。
    """
    from bili_extractor import extract_bv_id

    if not req.videos:
        raise HTTPException(status_code=400, detail="videos 列表不能为空")

    # ① 规范化：提取 BV 号并构建完整 URL
    normalized: list[tuple[str, str]] = []  # [(bv_id, full_url)]
    for v in req.videos:
        bv_id = extract_bv_id(v.strip())
        if bv_id:
            full_url = f"https://www.bilibili.com/video/{bv_id}/"
            normalized.append((bv_id, full_url))

    if not normalized:
        raise HTTPException(status_code=400, detail="未找到有效的 BV 号")

    # ② 去重过滤
    new_videos = []
    skipped_bvids = []
    for bv_id, full_url in normalized:
        if is_processed(bv_id):
            skipped_bvids.append(bv_id)
        else:
            new_videos.append((bv_id, full_url))

    # ③ 限制数量
    limit = min(req.max_videos, 20)
    to_process = new_videos[:limit]
    skipped_bvids.extend([bv for bv, _ in new_videos[limit:]])

    logger.info(
        f"[Batch] 共 {len(normalized)} 个视频, "
        f"已处理跳过 {len(skipped_bvids)}, 待处理 {len(to_process)}"
    )

    # ④ 逐个处理
    results: list[BiliBatchResult] = []

    # 先记录跳过的
    for bv_id in skipped_bvids:
        results.append(BiliBatchResult(bvid=bv_id, status="skipped"))

    # 逐个处理新视频
    for bv_id, full_url in to_process:
        logger.info(f"[Batch] 开始处理: {bv_id}")
        r = await _process_single_bili_video(full_url, req.use_scrapling)

        if r["status"] == "ok":
            mark_processed(bv_id, r.get("title", ""), "ok")

        results.append(BiliBatchResult(
            bvid=bv_id,
            title=r.get("title", ""),
            status=r["status"],
            filepath=r.get("filepath", ""),
            error=r.get("error", ""),
            summary=r.get("summary", ""),
            modules=r.get("modules", []),
        ))

    processed = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")

    logger.info(
        f"[Batch] 完成: processed={processed}, failed={failed}, skipped={skipped}"
    )

    return BiliBatchResponse(
        status="ok",
        processed=processed,
        skipped=skipped,
        failed=failed,
        results=results,
    )


def _matches_keywords(title: str, keywords: str) -> bool:
    """检查标题是否匹配任意关键词（不区分大小写）"""
    if not keywords or not keywords.strip():
        return True  # 无过滤条件 = 全部通过
    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return True
    title_lower = title.lower()
    return any(kw in title_lower for kw in kw_list)


# ── 日报核心逻辑（供统一日报端点复用）──

async def _run_bilibili_daily(
    max_videos: int = 10,
    filter_keywords: str = "",
) -> tuple[str, str, int, list[dict]]:  # (title, text, processed, [{title,summary,link,tags}])
    """B站日报核心逻辑，返回报告标题、正文、处理数、新增条目列表"""
    from bili_extractor import extract_bv_id

    has_filter = bool(filter_keywords and filter_keywords.strip())
    all_bvs: list[str] = []
    all_videos_info: list[dict] = []
    filtered_count = 0

    try:
        following = BiliFollowingFetcher()
        following_result = await following.get_following_feed(page=1, page_size=20)
        for v in following_result.items:
            if not v.bvid or is_processed(v.bvid):
                continue
            if not _matches_keywords(v.title, filter_keywords):
                filtered_count += 1
                continue
            all_bvs.append(v.bvid)
            all_videos_info.append({"bvid": v.bvid, "title": v.title, "author": v.author_name})
        logger.info(f"[Daily] 关注动态: {len(following_result.items)} 条, 过滤 {filtered_count} 条, 新视频 {len(all_bvs)} 条")
    except Exception as e:
        logger.warning(f"[Daily] 获取关注动态失败 (不阻断): {e}")

    try:
        uid = get_uid_from_cookies()
        if uid > 0:
            fav_fetcher = BiliFavoritesFetcher()
            folders = await fav_fetcher.list_folders(uid)
            for folder in folders[:3]:
                try:
                    fv_result = await fav_fetcher.get_folder_videos(
                        uid, folder.media_id, page=1, page_size=20,
                    )
                    for v in fv_result.items:
                        if not v.bvid or v.bvid in all_bvs or is_processed(v.bvid):
                            continue
                        if not _matches_keywords(v.title, filter_keywords):
                            filtered_count += 1
                            continue
                        all_bvs.append(v.bvid)
                        all_videos_info.append({
                            "bvid": v.bvid, "title": v.title,
                            "author": v.author_name, "folder": folder.title,
                        })
                except Exception as fe:
                    logger.warning(f"[Daily] 获取收藏夹 {folder.title} 失败: {fe}")
            logger.info(f"[Daily] 收藏夹: 累计 {len(all_bvs)} 个新视频")
    except Exception as e:
        logger.warning(f"[Daily] 收藏夹获取失败 (不阻断): {e}")

    all_bvs = list(dict.fromkeys(all_bvs))
    limit = min(max_videos, 20)
    to_process = all_bvs[:limit]

    logger.info(f"[Daily] 去重后: {len(all_bvs)} 个, 限处理 {len(to_process)} 个")

    details: list[BiliBatchResult] = []
    processed = 0

    for bv_id in to_process:
        full_url = f"https://www.bilibili.com/video/{bv_id}/"
        r = await _process_single_bili_video(full_url, use_scrapling=True)
        if r["status"] == "ok":
            mark_processed(bv_id, r.get("title", ""), "ok")
            processed += 1
        details.append(BiliBatchResult(
            bvid=bv_id,
            title=r.get("title", ""),
            status=r["status"],
            filepath=r.get("filepath", ""),
            error=r.get("error", ""),
            summary=r.get("summary", ""),
            modules=r.get("modules", []),
        ))

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    filter_info = f"\n- 关键词过滤: \"{filter_keywords}\" 过滤掉 {filtered_count} 条" if has_filter else ""
    lines = [
        f"## 📺 B站",
        f"> {today}",
        "",
        f"- 新发现视频: {len(all_bvs)} 个{filter_info}",
        f"- 已处理: {processed} 篇",
        "",
    ]

    ok_items_data: list[dict] = []
    ok_items = [d for d in details if d.status == "ok"]
    if ok_items:
        lines.append("### 新增沉淀")
        for d in ok_items:
            title = d.title or d.bvid
            bv_link = f"https://www.bilibili.com/video/{d.bvid}/"
            # 从 modules 中提取所有标签
            item_tags: list[str] = []
            lines.append(f"- **{title}**")
            lines.append(f"  🔗 {bv_link}")
            if d.summary:
                lines.append(f"  💡 {d.summary}")
            if d.modules:
                for m in d.modules:
                    m_title = m.get("title", "")
                    m_items = m.get("items", [])
                    if m_title:
                        item_tags.append(m_title)
                    if m_items:
                        preview = "；".join(m_items[:3])
                        if len(m_items) > 3:
                            preview += f" ...共{len(m_items)}条"
                        lines.append(f"  · {m_title}: {preview}")
            ok_items_data.append({
                "title": title,
                "summary": d.summary or "",
                "link": bv_link,
                "tags": item_tags,
                "modules": [{"title": m.get("title", ""), "items": m.get("items", [])} for m in (d.modules or [])],
            })
        lines.append("")

    skipped_bvs = all_bvs[limit:]
    if skipped_bvs:
        lines.append(f"#### 待处理 ({len(skipped_bvs)} 个)")
        for bv in skipped_bvs[:8]:
            info = next((x for x in all_videos_info if x["bvid"] == bv), {})
            lines.append(f"- [{info.get('title', bv)}](https://www.bilibili.com/video/{bv}/)")
        if len(skipped_bvs) > 8:
            lines.append(f"- ...还有 {len(skipped_bvs) - 8} 个")
        lines.append("")

    report_text = "\n".join(lines)
    report_title = f"每日B站知识沉淀日报_{today}"

    logger.info(f"[Daily] 完成: processed={processed}")
    return report_title, report_text, processed, ok_items_data


async def _run_wechat_daily(
    max_articles: int = 10,
) -> tuple[str, str, int, int, list[dict]]:  # (title, text, processed, discovered, [{title,summary,link,tags}])
    """微信日报核心逻辑，返回报告标题、正文、处理数、发现数、新增条目列表"""
    if wechat_tracker is None or wechat_extractor is None:
        raise RuntimeError("微信服务未就绪")

    discovered = wechat_tracker.discover_new_articles(max_per_account=max_articles)
    logger.info(f"[WechatDaily] 发现 {len(discovered)} 篇新文章")

    details: list[dict] = []
    processed = 0

    for art in discovered[:max_articles]:
        result = {
            "url": art.url, "title": "", "status": "failed",
            "filepath": "", "summary": "", "modules": [], "error": "", "author": "",
        }
        try:
            article = await asyncio.to_thread(wechat_extractor.extract, art.url)
            result["title"] = article.title
            result["author"] = article.author
            enriched_text = _build_wechat_ai_input(article)
            extracted = await processor.extract_async(enriched_text, source_url=art.url)
            source_tags = ["微信公众号"]
            if article.author:
                source_tags.append(f"来源:{article.author}")
            merged = set(source_tags + extracted.tags)
            extracted.tags = list(merged)[:10]
            filename = sanitize_filename(article.title) if article.title else f"微信文章_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}"
            data = asdict(extracted)
            filepath = write_to_vault(data, vault_path=VAULT_PATH, filename=filename)
            wechat_tracker.mark_processed(art.url, art.biz)
            processed += 1
            result["status"] = "ok"
            result["filepath"] = filepath
            result["summary"] = extracted.summary
            result["modules"] = extracted.modules
        except Exception as e:
            logger.warning(f"[WechatDaily] 处理失败 {art.url[:60]}: {e}")
            result["error"] = str(e)[:200]
        details.append(result)

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    ok_items = [d for d in details if d["status"] == "ok"]
    lines = [
        f"## 📱 微信公众号",
        f"> {today}",
        "",
        f"- 追踪账号: {len(wechat_tracker.get_accounts())} 个",
        f"- 发现新文章: {len(discovered)} 篇",
        f"- 处理成功: {processed} 篇",
        "",
    ]

    ok_items_data: list[dict] = []
    if ok_items:
        lines.append("### 新增沉淀")
        for d in ok_items:
            title = d.get("title", "") or d.get("url", "")
            link = d.get("url", "")
            item_tags: list[str] = []
            lines.append(f"- **{title}**")
            lines.append(f"  🔗 {link}")
            if d.get("author"):
                lines.append(f"  📛 {d['author']}")
            if d.get("summary"):
                lines.append(f"  💡 {d['summary']}")
            if d.get("modules"):
                for m in d["modules"]:
                    m_title = m.get("title", "")
                    m_items = m.get("items", [])
                    if m_title:
                        item_tags.append(m_title)
                    if m_items:
                        preview = "；".join(m_items[:3])
                        if len(m_items) > 3:
                            preview += f" ...共{len(m_items)}条"
                        lines.append(f"  · {m_title}: {preview}")
            ok_items_data.append({
                "title": title,
                "summary": d.get("summary", ""),
                "link": link,
                "tags": item_tags,
                "modules": [{"title": m.get("title", ""), "items": m.get("items", [])} for m in (d.get("modules") or [])],
            })
        lines.append("")

    report_text = "\n".join(lines)
    report_title = f"每日微信公众号知识沉淀日报_{today}"

    logger.info(f"[WechatDaily] 完成: processed={processed}")
    return report_title, report_text, processed, len(discovered), ok_items_data


@app.post("/api/bilibili/daily", response_model=BiliDailyResponse)
async def bilibili_daily(
    max_videos: int = 10,
    filter_keywords: str = "",
):
    """一键日报: 获取关注动态 → 去重 → 批量转录 → 生成 Markdown 报告"""
    report_title, report_text, processed, _ = await _run_bilibili_daily(max_videos, filter_keywords)
    return BiliDailyResponse(
        status="ok",
        report_title=report_title,
        report_text=report_text,
        processed=processed,
        skipped=0,
        failed=0,
        details=[],
    )


# ═══════════════════════════════════════════════════════════════════
#  全平台统一日报 API（B站 + 微信，一个端点搞定）
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/unified_daily", response_model=UnifiedDailyResponse)
async def unified_daily(
    max_videos: int = 10,
    max_articles: int = 2,
    filter_keywords: str = "亚马逊,跨境电商,选品,FBA,卖家,Listing,运营,跨境,电商,广告",
):
    """全平台统一日报: B站 + 微信公众号 合并为一份日报

    并行获取 B站和微信日报，合并 Markdown 报告文本，
    生成统一的飞书卡片数据。n8n 只需调用这一个端点即可。

    参数:
      max_videos:       B站最多处理视频数 (默认 10)
      max_articles:     微信最多处理文章数 (默认 10)
      filter_keywords:  B站标题关键词过滤，逗号分隔。默认过滤跨境电商相关
    """
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    bili_title = bili_text = wechat_title = wechat_text = ""
    bili_count = wechat_count = wechat_found = 0
    all_new_items: list[dict] = []

    # 并行执行 B站 + 微信日报（B站端内带关键词过滤）
    bili_task = _run_bilibili_daily(max_videos, filter_keywords)
    wechat_task = _run_wechat_daily(max_articles) if (wechat_tracker and wechat_extractor) else None

    results = await asyncio.gather(bili_task, wechat_task, return_exceptions=True)

    # 解析 B站结果
    if isinstance(results[0], Exception):
        logger.warning(f"[UnifiedDaily] B站日报失败: {results[0]}")
        bili_text = "## 📺 B站\n> 今日暂无可处理内容\n"
    else:
        bili_title, bili_text, bili_count, bili_items = results[0]
        for item in bili_items:
            item["source"] = "B站"
            all_new_items.append(item)

    # 解析微信结果
    if results[1] is None:
        wechat_text = "## 📱 微信公众号\n> 微信服务未就绪，已跳过\n"
    elif isinstance(results[1], Exception):
        logger.warning(f"[UnifiedDaily] 微信日报失败: {results[1]}")
        wechat_text = "## 📱 微信公众号\n> 暂无可处理内容\n"
    else:
        wechat_title, wechat_text, wechat_count, wechat_found, wechat_items = results[1]
        for item in wechat_items:
            item["source"] = "微信"
            all_new_items.append(item)

    # ── 按主题归类 ──
    tag_groups: dict[str, list[dict]] = {}  # tag → articles
    for item in all_new_items:
        for tag in item.get("tags", []):
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append(item)

    # 合并为统一日报
    total_processed = bili_count + wechat_count
    source_summary_parts = [f"B站 {bili_count} 篇"]
    if wechat_count > 0 or wechat_found > 0:
        source_summary_parts.append(f"微信 {wechat_count} 篇")
    source_summary = " + ".join(source_summary_parts)

    lines = [
        f"# 跨境知识日报",
        f"> {today} 自动生成 · {source_summary}",
        "",
        f"## 统计",
        f"- B站处理: {bili_count} 篇",
        f"- 微信处理: {wechat_count} 篇（发现 {wechat_found} 篇）",
        f"- 合计入库: {total_processed} 篇",
        "",
    ]

    # ── 按知识领域归类（3条以上才建组，其余归入"综合"）──
    if tag_groups:
        lines.append("## 按主题归类")
        # 按文章数排序，只展示 ≥2篇 的主题
        active_groups = [(tag, arts) for tag, arts in tag_groups.items() if len(arts) >= 2]
        active_groups.sort(key=lambda x: -len(x[1]))
        orphan_items: list[dict] = []

        if active_groups:
            grouped_titles: set[str] = set()
            for tag, arts in active_groups:
                lines.append(f"### {tag}（{len(arts)} 篇）")
                for a in arts:
                    src_tag = "📺" if a["source"] == "B站" else "📱"
                    lines.append(f"- **{a['title']}** {src_tag}")
                    if a.get("link"):
                        lines.append(f"  🔗 {a['link']}")
                    if a.get("summary"):
                        lines.append(f"  💡 {a['summary']}")
                    if a.get("modules"):
                        for m in a["modules"]:
                            m_title = m.get("title", "")
                            m_items = m.get("items", [])
                            if m_items:
                                preview = "；".join(m_items[:3])
                                if len(m_items) > 3:
                                    preview += f" ...共{len(m_items)}条"
                                lines.append(f"  · {m_title}: {preview}")
                    if a.get("tags"):
                        lines.append(f"  🏷️ {' · '.join(a['tags'])}")
                    grouped_titles.add(a["title"])
                lines.append("")

            # 没有被任何活跃主题收录的文章 → 归入"综合"
            orphan_items = [a for a in all_new_items if a["title"] not in grouped_titles]
            if orphan_items:
                lines.append(f"### 综合（{len(orphan_items)} 篇）")
                for a in orphan_items:
                    src_tag = "📺" if a["source"] == "B站" else "📱"
                    lines.append(f"- **{a['title']}** {src_tag}")
                    if a.get("link"):
                        lines.append(f"  🔗 {a['link']}")
                    if a.get("summary"):
                        lines.append(f"  💡 {a['summary']}")
                    if a.get("modules"):
                        for m in a["modules"]:
                            m_title = m.get("title", "")
                            m_items = m.get("items", [])
                            if m_items:
                                preview = "；".join(m_items[:3])
                                if len(m_items) > 3:
                                    preview += f" ...共{len(m_items)}条"
                                lines.append(f"  · {m_title}: {preview}")
                    if a.get("tags"):
                        lines.append(f"  🏷️ {' · '.join(a['tags'])}")
                lines.append("")
        else:
            # 没有高频主题时直接列出
            lines.append("*今日各篇主题分散，按时间线呈现如下：*")
            lines.append("")
            for item in all_new_items[:16]:
                src_tag = "📺" if item["source"] == "B站" else "📱"
                lines.append(f"- **{item['title']}** {src_tag}")
                if item.get("link"):
                    lines.append(f"  🔗 {item['link']}")
                if item.get("summary"):
                    lines.append(f"  💡 {item['summary']}")
                if item.get("modules"):
                    for m in item["modules"]:
                        m_title = m.get("title", "")
                        m_items = m.get("items", [])
                        if m_items:
                            preview = "；".join(m_items[:3])
                            if len(m_items) > 3:
                                preview += f" ...共{len(m_items)}条"
                            lines.append(f"  · {m_title}: {preview}")
                if item.get("tags"):
                    lines.append(f"  🏷️ {' · '.join(item['tags'])}")

    if not tag_groups and all_new_items:
        lines.append("## 新增沉淀内容")
        for item in all_new_items[:16]:
            src_tag = "📺" if item["source"] == "B站" else "📱"
            lines.append(f"- **{item['title']}** {src_tag}")
            if item.get("link"):
                lines.append(f"  🔗 {item['link']}")
            if item.get("summary"):
                lines.append(f"  💡 {item['summary']}")
        if len(all_new_items) > 16:
            lines.append(f"*...还有 {len(all_new_items) - 16} 篇*")
        lines.append("")

    report_text = "\n".join(lines)
    report_text += "\n\n---\n\n" + bili_text + "\n\n---\n\n" + wechat_text

    report_title = f"跨境知识日报_{today}"

    logger.info(f"[UnifiedDaily] 完成: B站{bili_count} + 微信{wechat_count} = {total_processed}")

    return UnifiedDailyResponse(
        status="ok",
        report_title=report_title,
        report_text=report_text,
        bili_processed=bili_count,
        wechat_processed=wechat_count,
        wechat_discovered=wechat_found,
        new_items=all_new_items[:16],
    )


# ═══════════════════════════════════════════════════════════════════
#  飞书推送 API
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/feishu/send", response_model=FeishuSendResponse)
async def feishu_send(req: FeishuSendRequest):
    """将日报 Markdown 推送为飞书卡片消息

    需配置环境变量 FEISHU_WEBHOOK_URL（飞书自定义机器人 Webhook 地址）。
    如机器人开启安全设置，还需配置 FEISHU_WEBHOOK_SECRET（签名校验密钥）。
    """
    if not req.title or not req.content:
        raise HTTPException(status_code=400, detail="title 和 content 不能为空")

    ok, msg = await send_feishu_report(
        title=req.title,
        markdown_text=req.content,
    )

    if not ok:
        logger.warning(f"飞书推送失败: {msg}")

    return FeishuSendResponse(
        status="ok" if ok else "error",
        message=msg,
    )


# ═══════════════════════════════════════════════════════════════════
#  知识检索 API
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/search_knowledge", response_model=SearchResponse)
async def search_knowledge(req: SearchRequest):
    """语义检索 Obsidian 知识库

    1. 将用户查询向量化（BGE-M3 Embedding）
    2. 在 Qdrant 'ecommerce_knowledge' 集合中执行 Cosine 相似度搜索
    3. 返回匹配度最高的文本块及其溯源信息
    """
    if vector_indexer is None:
        raise HTTPException(
            status_code=503,
            detail="向量索引器未就绪，请确认 Qdrant 服务已启动",
        )

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    # 同步 Qdrant 调用用 to_thread 包裹，避免阻塞事件循环
    results = await asyncio.to_thread(
        vector_indexer.search_knowledge,
        query=req.query.strip(),
        limit=min(req.limit, 10),
    )

    return SearchResponse(
        query=req.query.strip(),
        results=[SearchResultItem(**r) for r in results],
        total=len(results),
    )


# ═══════════════════════════════════════════════════════════════════
#  健康检查
# ═══════════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "vector_db": "connected" if vector_indexer is not None else "disconnected",
    }
