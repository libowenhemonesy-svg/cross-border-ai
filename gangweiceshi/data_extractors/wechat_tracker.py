"""
微信公众号账号追踪模块 — 管理追踪账号列表 + 发现新文章

存储: /obsidian/.wechat_tracked.json（追踪账号配置）
     /obsidian/.wechat_processed.json（已处理文章去重，复用 B站模式）

使用方式:
  tracker = WechatTracker(vault_path="/obsidian")
  tracker.add_account("https://mp.weixin.qq.com/s/xxxxx")  # 从文章链接添加追踪
  new_articles = tracker.discover_new_articles()            # 发现所有追踪号的新文章
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))

WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 12; SM-G9960) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/108.0.5359.128 "
    "Mobile Safari/537.36 MicroMessenger/8.0.42.2744(0x28002A3B) "
    "WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64"
)


@dataclass
class TrackedAccount:
    """追踪的微信公众号"""
    biz: str                # 账号唯一标识（base64）
    name: str = ""          # 公众号名称
    article_count: int = 0  # 已处理文章数
    added_at: str = ""      # 添加时间


@dataclass
class DiscoveredArticle:
    """发现的文章"""
    url: str
    biz: str
    title: str = ""
    is_new: bool = True


class WechatTracker:
    """微信公众号追踪器

    维护追踪账号列表，通过"种子文章交叉链接"方式发现新文章。
    """

    def __init__(self, vault_path: str = "/obsidian"):
        self.vault_path = vault_path
        self._tracked_file = os.path.join(vault_path, ".wechat_tracked.json")
        self._processed_file = os.path.join(vault_path, ".wechat_processed.json")
        self._queue_file = os.path.join(vault_path, ".wechat_queue.json")
        self._accounts: dict[str, TrackedAccount] = {}
        self._processed: dict[str, str] = {}  # url → biz 映射
        self._queue: list[str] = []            # 手动加入的文章 URL 队列
        self._load()

    # ------------------------------------------------------------------
    #  持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """加载追踪配置和已处理列表"""
        # 加载追踪账号
        try:
            if os.path.isfile(self._tracked_file):
                with open(self._tracked_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("accounts", []):
                    acc = TrackedAccount(**item)
                    self._accounts[acc.biz] = acc
                logger.info(
                    f"WechatTracker: 加载 {len(self._accounts)} 个追踪账号"
                )
        except Exception as e:
            logger.warning(f"加载追踪配置失败: {e}")

        # 加载已处理列表
        try:
            if os.path.isfile(self._processed_file):
                with open(self._processed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                urls_data = data.get("urls", {})
                if isinstance(urls_data, list):
                    # 迁移旧格式（纯 URL 列表 → URL→biz 映射）
                    self._processed = {u: "" for u in urls_data}
                else:
                    self._processed = urls_data
                logger.info(f"WechatTracker: {len(self._processed)} 篇已处理")
        except Exception as e:
            logger.warning(f"加载已处理列表失败: {e}")

        # 加载手动队列
        try:
            if os.path.isfile(self._queue_file):
                with open(self._queue_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._queue = data.get("urls", [])
                logger.info(f"WechatTracker: 加载 {len(self._queue)} 个手动队列URL")
        except Exception as e:
            logger.warning(f"加载手动队列失败: {e}")

    def _save_queue(self) -> None:
        """持久化手动队列"""
        os.makedirs(self.vault_path, exist_ok=True)
        with open(self._queue_file, "w", encoding="utf-8") as f:
            json.dump({
                "urls": self._queue,
                "updated_at": datetime.now(TZ).isoformat(),
            }, f, ensure_ascii=False, indent=2)

    def _save(self) -> None:
        """持久化追踪配置和已处理列表"""
        os.makedirs(self.vault_path, exist_ok=True)

        data = {
            "updated_at": datetime.now(TZ).isoformat(),
            "accounts": [
                {
                    "biz": a.biz,
                    "name": a.name,
                    "article_count": a.article_count,
                    "added_at": a.added_at,
                }
                for a in self._accounts.values()
            ],
        }
        with open(self._tracked_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        proc_data = {"urls": self._processed}
        with open(self._processed_file, "w", encoding="utf-8") as f:
            json.dump(proc_data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    #  账号管理
    # ------------------------------------------------------------------

    def add_account(self, article_url: str) -> TrackedAccount:
        """从一篇文章链接提取账号信息并加入追踪列表

        Args:
            article_url: 公众号文章链接

        Returns:
            TrackedAccount 对象

        Raises:
            ValueError: 无法提取 biz ID
        """
        biz, name = self._extract_account_info(article_url)

        if biz in self._accounts:
            logger.info(f"账号已在追踪列表中: {name or biz}")
            # 仍然将这篇新文章作为种子存储
            if article_url not in self._processed:
                self._processed[article_url] = biz
                self._accounts[biz].article_count += 1
                self._save()
            return self._accounts[biz]

        acc = TrackedAccount(
            biz=biz,
            name=name,
            article_count=1,
            added_at=datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        )
        self._accounts[biz] = acc
        # 将添加时用的文章 URL 直接作为种子
        self._processed[article_url] = biz
        self._save()
        logger.info(f"WechatTracker: 新增追踪账号 → {name or biz}（初始种子已存储）")
        return acc

    def remove_account(self, biz: str) -> bool:
        """移除追踪账号"""
        if biz in self._accounts:
            del self._accounts[biz]
            self._save()
            return True
        return False

    def get_accounts(self) -> list[TrackedAccount]:
        """获取所有追踪账号"""
        return list(self._accounts.values())

    def queue_article(self, url: str) -> tuple[bool, str]:
        """手动添加文章 URL 到处理队列（下次日报运行时自动处理）

        Args:
            url: 微信公众号文章链接

        Returns:
            (是否成功加入队列, 状态消息)
        """
        if url in self._processed:
            return False, "该文章已处理过"
        if url in self._queue:
            return False, "该文章已在队列中"
        self._queue.append(url)
        self._save_queue()
        logger.info(f"文章已加入手动队列: {url[:60]}")
        return True, "文章已加入处理队列，将在下次日报运行时处理"

    def get_queue(self) -> list[str]:
        """获取当前队列中的 URL 列表"""
        return list(self._queue)

    # ------------------------------------------------------------------
    #  文章发现
    # ------------------------------------------------------------------

    def discover_new_articles(
        self, max_per_account: int = 5
    ) -> list[DiscoveredArticle]:
        """从所有追踪账号发现新文章

        对每个账号，用最新已知文章作为种子，提取页内其他文章链接。
        同时优先处理手动队列中的 URL。

        Args:
            max_per_account: 每个账号最多返回的文章数

        Returns:
            新文章列表（已去重、已过滤已处理）
        """
        discovered: list[DiscoveredArticle] = []
        seen: set[str] = set()

        # ── ① 优先处理手动队列 ──
        queue_urls = list(self._queue)
        self._queue = []
        self._save_queue()

        for url in queue_urls:
            if url in self._processed:
                logger.info(f"队列URL已处理过，跳过: {url[:60]}")
                continue
            if url in seen:
                continue
            seen.add(url)
            # 尝试提取 biz（失败也不影响处理）
            try:
                biz, name = self._extract_account_info(url)
            except Exception:
                biz, name = "", ""
            discovered.append(DiscoveredArticle(url=url, biz=biz))
            logger.info(f"从手动队列发现: {url[:60]}" + (f" ({name})" if name else ""))

        # ── ② 交叉链接发现 ──

        for biz, acc in self._accounts.items():
            try:
                # 找到该账号最近的一篇已处理文章作为种子
                seed_url = self._find_seed_url(biz)
                if not seed_url:
                    logger.warning(f"账号 {acc.name or biz} 无种子文章，跳过")
                    continue

                # 从种子文章中提取同号文章链接
                links = self._fetch_article_links(seed_url)
                logger.info(
                    f"账号 {acc.name or biz}: 从种子文章发现 {len(links)} 个链接"
                )

                count = 0
                for link in links:
                    if count >= max_per_account:
                        break
                    if link in seen or link in self._processed:
                        continue
                    seen.add(link)

                    art = DiscoveredArticle(url=link, biz=biz)
                    discovered.append(art)
                    count += 1

            except Exception as e:
                logger.warning(f"发现账号 {acc.name or biz} 文章失败: {e}")
                continue

        logger.info(
            f"WechatTracker: 共发现 {len(discovered)} 篇新文章"
        )
        return discovered

    def mark_processed(self, url: str, biz: str = "") -> None:
        """标记文章已处理"""
        self._processed[url] = biz
        self._save()

    def is_processed(self, url: str) -> bool:
        """检查文章是否已处理"""
        return url in self._processed

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _find_seed_url(self, biz: str) -> str | None:
        """找到指定账号最近一篇已处理文章作为种子"""
        for url, url_biz in self._processed.items():
            if url_biz == biz:
                return url
        return None

    def _fetch_article_links(self, article_url: str) -> list[str]:
        """从文章页提取所有微信文章链接（排除自身和外部链接）"""
        try:
            with httpx.Client(
                timeout=30, follow_redirects=True,
                headers={"User-Agent": WECHAT_UA},
            ) as client:
                resp = client.get(article_url)
                if resp.status_code != 200:
                    logger.warning(f"种子文章获取失败 HTTP {resp.status_code}: {article_url[:60]}")
                    return []

                html = resp.text
                # 找所有 mp.weixin.qq.com/s/ 链接
                links = re.findall(
                    r'https?://mp\.weixin\.qq\.com/s/([^"#\s&\x27<>]+)',
                    html,
                )
                # 还原完整 URL + 去重 + 过滤自身
                full_links = []
                seen: set[str] = set()
                current_sn = self._extract_sn(article_url)

                for path in links:
                    url = f"https://mp.weixin.qq.com/s/{path}"
                    if url in seen:
                        continue
                    # 过滤当前文章自身
                    sn = self._extract_sn(url)
                    if sn and sn == current_sn:
                        continue
                    seen.add(url)
                    full_links.append(url)

                return full_links
        except Exception as e:
            logger.warning(f"获取文章链接失败: {e}")
            return []

    @staticmethod
    def _extract_sn(url: str) -> str:
        """从微信文章 URL 中提取 sn 参数"""
        m = re.search(r'/s/([^?&#]+)', url)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_account_info(url: str) -> tuple[str, str]:
        """从文章页提取 biz ID 和公众号名称

        Returns:
            (biz_id, account_name)
        """
        with httpx.Client(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": WECHAT_UA},
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise ValueError(f"文章获取失败 HTTP {resp.status_code}")

            html = resp.text

            # 提取 biz ID
            m = re.search(r'var\s+biz\s*=\s*"([^"]+)"', html)
            if not m:
                m = re.search(r'biz\s*:\s*"([^"]+)"', html)
            if not m:
                raise ValueError("无法从文章中提取 biz ID")
            biz = m.group(1)

            # 提取公众号名称
            name = ""
            m = re.search(r'<[^>]*id="?js_name"?[^>]*>(.*?)</', html, re.DOTALL)
            if m:
                name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if not name:
                m = re.search(r'nickname\s*=\s*"([^"]+)"', html)
                if m:
                    name = m.group(1).strip()

            return biz, name
