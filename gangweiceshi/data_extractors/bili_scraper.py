"""
B 站信息采集器 — 基于 Scrapling 反检测引擎，1-2s 内提取视频页完整结构化元数据
无需 Cookie、无需下载音频，通过解析页面内嵌 __INITIAL_STATE__ JSON 实现

与 bili_extractor.py 的关系:
  - bili_extractor.py: yt-dlp 下载音频 → FFmpeg 转 mp3（慢，但能获取内容）
  - bili_scraper.py:  Scrapling 抓取页面 → 提取元数据（快，但只有元数据）
  两者互补，非替代。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import scrapling

from bili_extractor import extract_bv_id

logger = logging.getLogger(__name__)

# 北京时间
TZ = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════════════════════════════
#  数据模型
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class BiliVideoMeta:
    """B 站视频完整元数据"""
    bvid: str = ""
    title: str = ""
    description: str = ""
    cover_url: str = ""
    tags: list[dict] = field(default_factory=list)        # [{tag_id, tag_name}, ...]
    stat: dict = field(default_factory=dict)                # {view, dm, reply, favorite, coin, share, like}
    pubdate: str = ""                                       # ISO 8601 格式
    pubdate_ts: int = 0                                     # Unix 时间戳
    tname: str = ""                                         # 分区名称
    owner: dict = field(default_factory=dict)               # {mid, name}
    related_videos: list[dict] = field(default_factory=list)  # [{title, bvid, play_count, author}, ...]


@dataclass
class BiliUpInfo:
    """B 站 UP 主信息"""
    mid: int = 0
    name: str = ""
    fans: int = 0
    archive_count: int = 0
    sign: str = ""
    face_url: str = ""


# ═══════════════════════════════════════════════════════════════════════
#  主类
# ═══════════════════════════════════════════════════════════════════════


class BilibiliScraper:
    """Scrapling 驱动的 B 站数据提取器

    使用 curl_cffi 引擎模拟浏览器 TLS 指纹，绕过反爬机制。
    Fetcher 实例惰性初始化并复用，避免重复 TLS 握手开销。

    用法:
        scraper = BilibiliScraper()
        meta = scraper.extract_video_meta("https://www.bilibili.com/video/BV1xx411c7mD/")
        print(meta.title, meta.stat["view"])
    """

    def __init__(self):
        self._fetcher: scrapling.Fetcher | None = None

    def _get_fetcher(self) -> scrapling.Fetcher:
        """惰性初始化 Fetcher（curl_cffi 引擎，模拟 TLS 指纹）"""
        if self._fetcher is None:
            self._fetcher = scrapling.Fetcher()
            logger.info("Scrapling Fetcher（curl_cffi）已初始化")
        return self._fetcher

    # ------------------------------------------------------------------
    #  公开方法
    # ------------------------------------------------------------------

    def extract_video_meta(self, url: str, max_retries: int = 3) -> BiliVideoMeta:
        """从 B 站视频页提取完整元数据

        Args:
            url:         视频链接（bilibili.com/video/BV... 或 b23.tv 短链）
            max_retries: 网络请求最大重试次数

        Returns:
            BiliVideoMeta 对象，包含标题/描述/标签/互动数据/UP主/相关视频

        Raises:
            ValueError: 无效链接、视频不存在或数据提取失败
        """
        bv_id = extract_bv_id(url)
        if bv_id == "unknown":
            raise ValueError(f"无法从链接中提取 BV 号: {url}")

        # 1. 抓取页面
        page = self._fetch_with_retry(url, max_retries=max_retries)

        # 2. 从页面脚本中定位 __INITIAL_STATE__ JSON
        scripts = page.css("script::text").getall()
        initial_data = None
        for script in scripts:
            if "window.__INITIAL_STATE__" in script:
                try:
                    initial_data = self._extract_initial_state_json(script)
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"__INITIAL_STATE__ 解析失败，尝试下一个脚本: {e}")
                    continue

        if initial_data is None:
            raise ValueError(
                f"未能从页面中提取 __INITIAL_STATE__ 数据，"
                f"可能触发了反爬机制或页面结构已变更: {url}"
            )

        # 3. 映射为 BiliVideoMeta
        return self._parse_video_data(initial_data, bv_id)

    # ------------------------------------------------------------------
    #  网络请求 + 重试
    # ------------------------------------------------------------------

    def _fetch_with_retry(
        self, url: str, max_retries: int = 3
    ) -> scrapling.Response:
        """带指数退避的页面抓取

        可恢复错误: HTTP 429, HTTP 503, 连接超时
        不可恢复错误: HTTP 403, HTTP 404（立即抛出）
        """
        last_error = None
        fetcher = self._get_fetcher()

        for attempt in range(max_retries):
            try:
                response = fetcher.get(url)
                status = response.status

                if status == 200:
                    logger.info(f"页面抓取成功 ({url[:60]}...)")
                    return response
                elif status == 429:
                    last_error = RuntimeError(f"HTTP 429: 触发 B 站限流")
                elif status == 503:
                    last_error = RuntimeError(f"HTTP 503: B 站服务暂不可用")
                elif status == 404:
                    raise ValueError(f"视频不存在或已删除 (HTTP 404): {url}")
                elif status == 403:
                    raise RuntimeError(
                        f"访问被拒绝 (HTTP 403)，可能需要更换 IP: {url}"
                    )
                else:
                    last_error = RuntimeError(f"HTTP {status}")

            except (OSError, ConnectionError, TimeoutError) as e:
                last_error = e
            except (ValueError, RuntimeError):
                raise

            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"页面抓取失败 (尝试 {attempt+1}/{max_retries})，"
                    f"{wait}s 后重试: {last_error}"
                )
                time.sleep(wait)

        raise RuntimeError(f"页面抓取失败（已重试 {max_retries} 次）: {last_error}")

    # ------------------------------------------------------------------
    #  JSON 提取（括号计数器算法）
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_initial_state_json(script_text: str) -> dict:
        """从 JS 脚本文本中提取并解析 __INITIAL_STATE__ JSON 对象

        使用括号计数器精确匹配 JSON 对象边界，处理:
          - 字符串内转义（\\, \\"）
          - 嵌套 JSON 对象/数组
          - JSON 后紧跟其他 JS 语句（如 IIFE）

        Raises:
            ValueError: 未找到 __INITIAL_STATE__ 赋值语法
            json.JSONDecodeError: JSON 格式异常
        """
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*', script_text)
        if not match:
            raise ValueError("未找到 window.__INITIAL_STATE__ 赋值语句")

        json_start = match.end()
        if json_start >= len(script_text) or script_text[json_start] != "{":
            raise ValueError(
                f"__INITIAL_STATE__ 后不是 JSON 对象: "
                f"{script_text[json_start:json_start+20]}..."
            )

        depth = 0
        json_end = json_start
        in_string = False
        escape = False

        for i in range(json_start, len(script_text)):
            ch = script_text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not in_string:
                in_string = True
                continue
            if ch == '"' and in_string:
                in_string = False
                continue
            if not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        json_end = i + 1
                        break
            # 安全检查：JSON 不应超过 20MB
            if i - json_start > 20_000_000:
                break

        if json_end == json_start:
            raise ValueError("未能定位 JSON 对象结束位置")

        json_str = script_text[json_start:json_end]
        return json.loads(json_str)

    # ------------------------------------------------------------------
    #  数据映射
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_video_data(data: dict, bvid: str) -> BiliVideoMeta:
        """将 __INITIAL_STATE__ 原始字典映射为 BiliVideoMeta

        Args:
            data: 已解析的 __INITIAL_STATE__ JSON 字典
            bvid: BV 号（用于填充缺失的 bvid 字段）
        """
        video_data = data.get("videoData", {})
        up_data = data.get("upData", {})

        # ── 互动数据 ──
        raw_stat = video_data.get("stat", {})
        stat = {
            "view": raw_stat.get("view", 0),
            "dm": raw_stat.get("dm", 0),
            "reply": raw_stat.get("reply", 0),
            "favorite": raw_stat.get("favorite", 0),
            "coin": raw_stat.get("coin", 0),
            "share": raw_stat.get("share", 0),
            "like": raw_stat.get("like", 0),
        }

        # ── 发布时间（Unix 时间戳 → ISO 8601）──
        pubdate_ts = video_data.get("pubdate", 0)
        pubdate = ""
        if pubdate_ts:
            try:
                pubdate = datetime.fromtimestamp(pubdate_ts, tz=TZ).isoformat()
            except (OSError, ValueError):
                pubdate = str(pubdate_ts)

        # ── 标签 ──
        # B 站标签来源有两个：videoData.tag（旧格式）和 data.tags（新格式）
        tags = []
        raw_tags = video_data.get("tag", []) or data.get("tags", [])
        for t in raw_tags:
            if isinstance(t, dict):
                tags.append({
                    "tag_id": t.get("tag_id", ""),
                    "tag_name": t.get("tag_name", ""),
                })

        # ── UP 主 ──
        owner = video_data.get("owner", {})
        owner_info = {
            "mid": owner.get("mid", up_data.get("mid", 0)),
            "name": owner.get("name", up_data.get("name", "")),
        }

        # ── 相关视频 ──
        related = []
        for r in data.get("related", [])[:10]:
            if isinstance(r, dict):
                rstat = r.get("stat", {})
                related.append({
                    "bvid": r.get("bvid", ""),
                    "title": r.get("title", ""),
                    "play_count": rstat.get("view", 0),
                    "author": r.get("owner", {}).get("name", ""),
                    "cover": r.get("pic", ""),
                })

        return BiliVideoMeta(
            bvid=video_data.get("bvid", bvid),
            title=video_data.get("title", ""),
            description=video_data.get("desc", ""),
            cover_url=video_data.get("pic", ""),
            tags=tags,
            stat=stat,
            pubdate=pubdate,
            pubdate_ts=pubdate_ts,
            tname=video_data.get("tname", ""),
            owner=owner_info,
            related_videos=related,
        )


# ── CLI 入口：直接运行以验证功能 ──
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    scraper = BilibiliScraper()
    url = "https://www.bilibili.com/video/BV1ize4zgEir/"

    print(f"正在抓取: {url}\n")
    meta = scraper.extract_video_meta(url)

    print(f"── 基本信息 ──")
    print(f"BV号: {meta.bvid}")
    print(f"标题: {meta.title}")
    print(f"描述: {meta.description[:200]}...")
    print(f"分区: {meta.tname}")
    print(f"发布时间: {meta.pubdate}")

    print(f"\n── 互动数据 ──")
    for k, v in meta.stat.items():
        print(f"  {k}: {v}")

    print(f"\n── UP 主 ──")
    print(f"  UID: {meta.owner.get('mid')}")
    print(f"  名称: {meta.owner.get('name')}")

    print(f"\n── 标签 ({len(meta.tags)} 个) ──")
    for t in meta.tags:
        print(f"  #{t['tag_name']}")

    print(f"\n── 相关视频 Top 5 ──")
    for i, r in enumerate(meta.related_videos[:5], 1):
        print(f"  {i}. {r['title'][:60]}")
        print(f"     播放: {r['play_count']} | UP: {r['author']}")

    print("\n抓取成功！")
