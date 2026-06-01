"""
B站 API 与收藏夹数据获取模块 — 为 n8n 自动化提供内容源

核心能力:
  1. Netscape 格式 Cookie 解析 → HTTP Cookie 头
  2. WBI 签名 (B站 /x/ 命名空间 API 强制要求的轻量鉴权)
  3. 收藏夹视频列表获取 (Scrapling 页面抓取 → __INITIAL_STATE__ 解析)
  4. 关注 UP 主视频动态获取 (API + WBI 签名)
  5. 去重持久化 (/obsidian/.bili_processed.json)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))
COOKIE_FILE = "/cookies/bilibili.txt"
VAULT_PATH = os.environ.get("VAULT_PATH", "/obsidian")
PROCESSED_FILE = os.path.join(VAULT_PATH, ".bili_processed.json")

# WBI 签名固定置换表 (长度 64)
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 44, 52, 34,
]


# ═══════════════════════════════════════════════════════════════════════
#  Cookie 解析
# ═══════════════════════════════════════════════════════════════════════


def parse_cookies_netscape(filepath: str = COOKIE_FILE) -> dict[str, str]:
    """解析 Netscape 格式 Cookie 文件，返回 {name: value} 字典

    文件格式: domain  flag  path  secure  expiry  name  value
    跳过注释行 (#) 和空行。
    """
    cookies: dict[str, str] = {}
    if not os.path.isfile(filepath):
        logger.warning(f"Cookie 文件不存在: {filepath}")
        return cookies

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name, value = parts[5], parts[6]
                cookies[name] = value

    logger.info(f"解析到 {len(cookies)} 个 Cookie: {list(cookies.keys())}")
    return cookies


def build_cookie_header(cookies: dict[str, str]) -> str:
    """将 Cookie 字典序列化为 HTTP Cookie 请求头值"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def get_uid_from_cookies(cookies: dict[str, str] | None = None) -> int:
    """从 Cookie 中提取 DedeUserID (B站用户 UID)"""
    if cookies is None:
        cookies = parse_cookies_netscape()
    uid_str = cookies.get("DedeUserID", "0")
    try:
        return int(uid_str)
    except ValueError:
        return 0


# ═══════════════════════════════════════════════════════════════════════
#  WBI 签名
# ═══════════════════════════════════════════════════════════════════════


def get_mixin_key(orig: str) -> str:
    """对 img_key + sub_key 拼接串应用 WBI 置换表，取前 32 字符"""
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB if i < len(orig))[:32]


async def fetch_wbi_keys(cookies: dict[str, str]) -> tuple[str, str]:
    """通过 nav API 获取 WBI 混合密钥 (img_key, sub_key)"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = {
        "Cookie": build_cookie_header(cookies),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        data = resp.json()
        wbi = data.get("data", {}).get("wbi_img", {})
        img_url = wbi.get("img_url", "")
        sub_url = wbi.get("sub_url", "")
        if not img_url or not sub_url:
            raise ValueError(f"无法获取 WBI 密钥: {data}")

        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        logger.info(f"WBI 密钥已获取: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")
        return img_key, sub_key


def sign_params(params: dict[str, str], img_key: str, sub_key: str) -> dict[str, str]:
    """为请求参数追加 WBI 签名 (wts + w_rid)"""
    mixin_key = get_mixin_key(img_key + sub_key)
    params["wts"] = str(int(time.time()))
    # 按 key 字母序排序 → URL 编码 → 追加 mixin_key → MD5
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    query = urllib.parse.urlencode(sorted_params)
    # B站要求特殊字符大写编码
    query = query.replace("%2C", "%2c").replace("%3A", "%3a")  # normalize casing
    to_hash = query + mixin_key
    w_rid = hashlib.md5(to_hash.encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


# ═══════════════════════════════════════════════════════════════════════
#  数据模型
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class BiliVideoItem:
    """列表中的单个视频条目 (精简版)"""
    bvid: str = ""
    title: str = ""
    cover_url: str = ""
    author_name: str = ""
    author_mid: int = 0
    play_count: int = 0
    duration: str = ""
    pubdate_ts: int = 0
    video_url: str = ""

    def __post_init__(self):
        if self.bvid and not self.video_url:
            self.video_url = f"https://www.bilibili.com/video/{self.bvid}/"


@dataclass
class BiliFavFolder:
    """收藏夹文件夹信息"""
    media_id: int = 0
    title: str = ""
    media_count: int = 0


@dataclass
class BiliListResult:
    """列表查询结果"""
    items: list[BiliVideoItem] = field(default_factory=list)
    total: int = 0
    has_more: bool = False
    page: int = 1


# ═══════════════════════════════════════════════════════════════════════
#  收藏夹获取器 (WBI 签名 API)
# ═══════════════════════════════════════════════════════════════════════


class BiliFavoritesFetcher:
    """通过 B站 WBI 签名 API 获取收藏夹数据

    收藏夹页面 (space.bilibili.com/{uid}/favlist) 为 SPA 客户端渲染，
    HTML 源码中不含 __INITIAL_STATE__，因此改用以下 API:
      - 文件夹列表: GET /x/v3/fav/folder/created/list + collected/list
      - 视频列表:   GET /x/v3/fav/resource/list?media_id=...
    所有 /x/ 命名空间 API 均需 WBI 签名。
    """

    def __init__(self, cookiefile: str = COOKIE_FILE):
        self._cookies = parse_cookies_netscape(cookiefile)
        self._img_key: str | None = None
        self._sub_key: str | None = None
        self._cookie_header = build_cookie_header(self._cookies)
        self._headers = {
            "Cookie": self._cookie_header,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }

    async def _ensure_wbi_keys(self):
        if self._img_key and self._sub_key:
            return
        self._img_key, self._sub_key = await fetch_wbi_keys(self._cookies)

    async def list_folders(self, uid: int) -> list[BiliFavFolder]:
        """获取用户所有收藏夹文件夹（创建的 + 收藏的）"""
        await self._ensure_wbi_keys()

        folders: list[BiliFavFolder] = []
        async with httpx.AsyncClient(timeout=15) as client:
            # 创建的收藏夹
            params = sign_params(
                {"up_mid": str(uid), "pn": "1", "ps": "50", "platform": "web"},
                self._img_key, self._sub_key,
            )
            url = f"https://api.bilibili.com/x/v3/fav/folder/created/list?{urllib.parse.urlencode(params)}"
            resp = await client.get(url, headers=self._headers)
            data = resp.json()
            if data.get("code") == 0 and data.get("data"):
                for f in data["data"].get("list", []):
                    folders.append(BiliFavFolder(
                        media_id=f.get("id", 0),
                        title=f.get("title", "默认收藏夹"),
                        media_count=f.get("media_count", 0),
                    ))

            # 收藏的收藏夹
            params2 = sign_params(
                {"up_mid": str(uid), "pn": "1", "ps": "50", "platform": "web"},
                self._img_key, self._sub_key,
            )
            url2 = f"https://api.bilibili.com/x/v3/fav/folder/collected/list?{urllib.parse.urlencode(params2)}"
            resp2 = await client.get(url2, headers=self._headers)
            data2 = resp2.json()
            if data2.get("code") == 0 and data2.get("data"):
                for f in data2["data"].get("list", []):
                    folders.append(BiliFavFolder(
                        media_id=f.get("id", 0),
                        title=f.get("title", ""),
                        media_count=f.get("media_count", 0),
                    ))

        logger.info(f"获取到 {len(folders)} 个收藏夹文件夹")
        return folders

    async def get_folder_videos(
        self, uid: int, media_id: int = 0,
        page: int = 1, page_size: int = 20,
    ) -> BiliListResult:
        """获取指定收藏夹的视频列表 (分页)"""
        await self._ensure_wbi_keys()

        params = sign_params({
            "media_id": str(media_id),
            "pn": str(page),
            "ps": str(page_size),
            "keyword": "",
            "order": "mtime",
            "type": "0",
            "tid": "0",
            "platform": "web",
        }, self._img_key, self._sub_key)

        url = f"https://api.bilibili.com/x/v3/fav/resource/list?{urllib.parse.urlencode(params)}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers)
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"收藏夹 API 错误: code={data.get('code')}, {data.get('message')}")

        result_data = data.get("data") or {}
        medias = result_data.get("medias", [])
        info = result_data.get("info", {})
        total = info.get("media_count", len(medias))
        has_more = result_data.get("has_more", False)

        items = []
        for m in medias:
            items.append(BiliVideoItem(
                bvid=m.get("bvid", ""),
                title=m.get("title", ""),
                cover_url=m.get("cover", ""),
                author_name=m.get("upper", {}).get("name", ""),
                author_mid=m.get("upper", {}).get("mid", 0),
                play_count=m.get("cnt_info", {}).get("play", 0),
                duration=str(m.get("duration", "")),
                pubdate_ts=m.get("pubtime", 0),
            ))

        logger.info(f"收藏夹 media_id={media_id}: {len(items)}/{total} 条视频")
        return BiliListResult(
            items=items, total=total, has_more=has_more, page=page,
        )


# ═══════════════════════════════════════════════════════════════════════
#  关注动态获取器 (API + WBI 签名)
# ═══════════════════════════════════════════════════════════════════════


class BiliFollowingFetcher:
    """通过 B站 Polymer Dynamic API 获取已登录用户的关注 UP 主最新视频

    API: GET https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?type=video
    需要: Cookie (SESSDATA) + WBI 签名
    """

    def __init__(self, cookiefile: str = COOKIE_FILE):
        self._cookies = parse_cookies_netscape(cookiefile)
        self._img_key: str | None = None
        self._sub_key: str | None = None

    async def _ensure_wbi_keys(self):
        """获取或刷新 WBI 密钥"""
        if self._img_key and self._sub_key:
            return
        self._img_key, self._sub_key = await fetch_wbi_keys(self._cookies)

    async def get_following_feed(
        self, page: int = 1, page_size: int = 20
    ) -> BiliListResult:
        """获取关注 UP 主的最新视频动态"""
        await self._ensure_wbi_keys()

        params = sign_params(
            {"type": "video", "pn": str(page), "ps": str(page_size)},
            self._img_key, self._sub_key,
        )

        url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?{urllib.parse.urlencode(params)}"
        headers = {
            "Cookie": build_cookie_header(self._cookies),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"关注动态 API 错误: code={data.get('code')}, {data.get('message')}")

        items_data = data.get("data", {}).get("items", [])
        items = []
        for item in items_data:
            try:
                archive = item.get("modules", {}).get("module_dynamic", {}).get("major", {}).get("archive", {})
                if not archive:
                    continue
                items.append(BiliVideoItem(
                    bvid=archive.get("bvid", ""),
                    title=archive.get("title", ""),
                    cover_url=archive.get("cover", ""),
                    author_name=item.get("modules", {}).get("module_author", {}).get("name", ""),
                    author_mid=item.get("modules", {}).get("module_author", {}).get("mid", 0),
                    play_count=archive.get("stat", {}).get("play", 0),
                    duration=archive.get("duration_text", ""),
                    pubdate_ts=archive.get("pubdate", 0),
                ))
            except (KeyError, TypeError, AttributeError) as e:
                logger.warning(f"解析动态条目失败: {e}")
                continue

        logger.info(f"关注动态: {len(items)} 条视频 (page {page})")
        return BiliListResult(
            items=items,
            total=len(items),
            has_more=len(items) >= page_size,
            page=page,
        )


# ═══════════════════════════════════════════════════════════════════════
#  去重
# ═══════════════════════════════════════════════════════════════════════


def _load_processed() -> dict:
    """加载已处理视频记录"""
    if not os.path.isfile(PROCESSED_FILE):
        return {}
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_processed(data: dict):
    """持久化已处理视频记录"""
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_processed(bvid: str) -> bool:
    """检查 BV 号是否已处理"""
    return bvid in _load_processed()


def mark_processed(bvid: str, title: str = "", status: str = "ok"):
    """标记 BV 号为已处理"""
    data = _load_processed()
    data[bvid] = {
        "title": title,
        "processed_at": datetime.now(TZ).isoformat(),
        "status": status,
    }
    _save_processed(data)
    logger.info(f"已标记处理: {bvid} ({title[:40] if title else ''})")


def filter_new_videos(items: list[BiliVideoItem]) -> list[BiliVideoItem]:
    """过滤出未处理的新视频"""
    data = _load_processed()
    new_items = [it for it in items if it.bvid not in data]
    logger.info(f"去重: {len(items)} → {len(new_items)} 个新视频")
    return new_items


def get_processed_stats() -> dict:
    """获取去重统计信息"""
    data = _load_processed()
    ok_count = sum(1 for v in data.values() if v.get("status") == "ok")
    return {
        "total_processed": len(data),
        "success_count": ok_count,
        "latest": max((v.get("processed_at", "") for v in data.values()), default=""),
    }
