"""
微信公众号文章提取模块 — 抓取 mp.weixin.qq.com 文章并解析为结构化数据

使用方式:
  extractor = WechatExtractor()
  article = extractor.extract("https://mp.weixin.qq.com/s/xxxxx")
  print(article.title, article.author, len(article.content_text))

通过 httpx + 微信 UA 伪装绕过"请在微信中打开"拦截，无需 Cookie 或登录。
"""

from __future__ import annotations

import html as html_module
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# 微信内置浏览器 User-Agent（绕过"请在微信中打开"拦截）
WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 12; SM-G9960) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/108.0.5359.128 "
    "Mobile Safari/537.36 MicroMessenger/8.0.42.2744(0x28002A3B) "
    "WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64"
)

MIN_REQUEST_INTERVAL = 3.0  # 最小请求间隔（秒），保证 ≤20 次/分钟


@dataclass
class WechatArticle:
    """微信公众号文章结构化数据"""
    title: str = ""
    author: str = ""           # 公众号名称
    publish_time: str = ""     # 发布时间文本，如 "2025-06-15 10:30"
    content_text: str = ""     # 正文纯文本（供 AI 处理）
    images: list[str] = field(default_factory=list)  # data-src 真实图片 URL
    source_url: str = ""


class WechatExtractor:
    """微信公众号文章抓取器

    使用 httpx + 微信 User-Agent 伪装访问文章页面，
    解析 HTML 提取标题/作者/正文/图片。

    内置频率控制（≥3s 间隔）防止触发微信反爬。
    """

    def __init__(self):
        self._last_request_time: float = 0.0

    def _rate_limit(self) -> None:
        """频率控制：保证两次请求间隔 >= 3 秒"""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------
    #  公开方法
    # ------------------------------------------------------------------

    def extract(self, url: str, max_retries: int = 3) -> WechatArticle:
        """抓取并解析微信公众号文章

        Args:
            url:         文章链接 (mp.weixin.qq.com/s/...)
            max_retries: 网络请求最大重试次数

        Returns:
            WechatArticle 对象，包含标题/作者/正文/图片

        Raises:
            ValueError: 无效链接、文章不存在或内容为空
            RuntimeError: 网络请求失败或触发反爬
        """
        if not self._is_valid_wechat_url(url):
            raise ValueError(f"不是有效的微信公众号文章链接: {url}")

        # ① 限流 + 抓取
        self._rate_limit()
        html = self._fetch_page(url, max_retries=max_retries)

        # ② 验证页面
        self._validate_page(html, url)

        # ③ 提取各字段
        title = self._extract_title(html)
        author = self._extract_author(html)
        publish_time = self._extract_publish_time(html)
        content_text, images = self._extract_content(html)

        article = WechatArticle(
            title=title,
            author=author,
            publish_time=publish_time,
            content_text=content_text,
            images=images,
            source_url=url,
        )

        # ④ 质量检查
        if not article.title and not article.content_text.strip():
            raise ValueError("未能提取到有效内容，页面可能为空或结构已变更")

        logger.info(
            f"WechatExtractor 解析完成: title={article.title[:40]}..., "
            f"author={article.author}, content_len={len(article.content_text)}, "
            f"images={len(article.images)}"
        )
        return article

    # ------------------------------------------------------------------
    #  URL 校验
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_wechat_url(url: str) -> bool:
        return bool(re.match(r'https?://mp\.weixin\.qq\.com/s/', url))

    # ------------------------------------------------------------------
    #  网络请求 + 重试
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str, max_retries: int = 3) -> str:
        """带指数退避的页面抓取，返回 HTML 文本"""
        last_error = None

        for attempt in range(max_retries):
            try:
                with httpx.Client(
                    timeout=30, follow_redirects=True,
                    headers={"User-Agent": WECHAT_UA},
                ) as client:
                    resp = client.get(url)
                    status = resp.status_code

                if status == 200:
                    text = resp.text
                    if text and len(text) > 100:
                        logger.info(f"微信文章抓取成功 ({len(text)} 字节)")
                        return text
                    else:
                        last_error = RuntimeError("响应体为空或过短")
                elif status == 429:
                    last_error = RuntimeError("HTTP 429: 触发微信限流")
                elif status == 404:
                    raise ValueError("文章不存在或已被删除")
                elif status == 403:
                    raise RuntimeError("访问被拒绝 (HTTP 403)")
                else:
                    last_error = RuntimeError(f"HTTP {status}")

            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as e:
                last_error = e
            except (ValueError, RuntimeError):
                raise

            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"微信文章抓取失败 (尝试 {attempt+1}/{max_retries})，"
                    f"{wait}s 后重试: {last_error}"
                )
                time.sleep(wait)

        raise RuntimeError(f"页面抓取失败（已重试 {max_retries} 次）: {last_error}")

    # ------------------------------------------------------------------
    #  页面验证
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_page(html: str, url: str) -> None:
        """检查页面是否包含文章正文（排除"请在微信中打开"等占位页）"""
        if "#js_content" not in html and "rich_media_content" not in html:
            raise ValueError(
                "页面不包含文章正文，可能需要关注公众号、文章已删除、"
                "或触发了微信环境验证"
            )

    # ------------------------------------------------------------------
    #  字段提取
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_title(html: str) -> str:
        """提取文章标题，多层回退：
        1. CSS: #activity-name
        2. regex: <h1 class="rich_media_title">
        3. meta: og:title
        """
        m = re.search(r'<h1[^>]*id="?activity-name"?[^>]*>(.*?)</h1>', html, re.DOTALL)
        if m:
            title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if title:
                return html_module.unescape(title)

        m = re.search(
            r'<h1[^>]*class="?rich_media_title"?[^>]*>(.*?)</h1>',
            html, re.DOTALL,
        )
        if m:
            title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if title:
                return html_module.unescape(title)

        m = re.search(
            r'<meta[^>]*property="?og:title"?[^>]*content="?([^"]+)"?',
            html,
        )
        if m:
            return html_module.unescape(m.group(1).strip())

        return ""

    @staticmethod
    def _extract_author(html: str) -> str:
        """提取公众号名称，多层回退：
        1. CSS: #js_name
        2. CSS: a.rich_media_meta_nickname
        3. regex: profile_nickname
        """
        m = re.search(r'<[^>]*id="?js_name"?[^>]*>(.*?)</', html, re.DOTALL)
        if m:
            author = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if author:
                return html_module.unescape(author)

        m = re.search(
            r'<a[^>]*class="?rich_media_meta_nickname"?[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )
        if m:
            author = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if author:
                return html_module.unescape(author)

        m = re.search(r'nickname\s*=\s*"([^"]+)"', html)
        if m:
            return html_module.unescape(m.group(1).strip())

        return ""

    @staticmethod
    def _extract_publish_time(html: str) -> str:
        """提取发布时间，多层回退：
        1. JS 变量: create_time（页面渲染前已嵌入，最可靠）
        2. JS 变量: publish_time
        3. HTML: em#publish_time（JS 动态填充，通常为空）
        """
        m = re.search(r"create_time\s*:\s*'([^']+)'", html)
        if m:
            return m.group(1).strip()

        m = re.search(r'var\s+publish_time\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1).strip()

        m = re.search(r'<em[^>]*id="?publish_time"?[^>]*>(.*?)</em>', html, re.DOTALL)
        if m:
            result = html_module.unescape(m.group(1).strip())
            if result:
                return result
        return ""

    @staticmethod
    def _extract_content(html: str) -> tuple[str, list[str]]:
        """从 #js_content 中提取正文纯文本和图片 URL 列表

        处理流程：
        1. 定位 #js_content div 的 HTML 片段
        2. 提取所有 data-src 图片 URL
        3. 将 <img> 替换为 [图片: alt] 文本标注
        4. 处理换行和块级元素
        5. 去除所有 HTML 标签
        6. HTML 实体解码 + 空白规范化

        Returns:
            (content_text, images_list)
        """
        # ── ① 定位 #js_content 区块（用 div 计数器匹配闭合标签）──
        start_match = re.search(
            r'<div[^>]*id="?js_content"?[^>]*>',
            html,
        )
        if not start_match:
            start_match = re.search(
                r'<div[^>]*class="?rich_media_content"?[^>]*>',
                html,
            )
        if not start_match:
            return "", []

        start_pos = start_match.end()  # 内容起始位置（div 开标签之后）
        # 从 div 开标签处开始计数嵌套深度
        scan_pos = start_match.start()
        depth = 0
        end_pos = -1

        # 在原始 html 中扫描，跳过字符串内容避免误匹配
        i = scan_pos
        while i < len(html):
            if html[i:i+4].lower() == '<div':
                # 确认是真正的 div 标签开头（后面是空格、> 或属性）
                next_char = html[i+4] if i+4 < len(html) else ''
                if next_char in (' ', '>', '\n', '\t'):
                    depth += 1
                    i += 4
                    continue
            if html[i:i+6].lower() == '</div>':
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
                i += 6
                continue
            i += 1

        if end_pos < 0:
            return "", []

        raw_html = html[start_pos:end_pos]

        # ── ② 提取图片 data-src ──
        images: list[str] = []
        seen: set[str] = set()

        def _replace_img(m: re.Match) -> str:
            img_tag = m.group(0)
            src_m = re.search(r'data-src="([^"]+)"', img_tag)
            if not src_m:
                src_m = re.search(r'src="([^"]+)"', img_tag)
            img_url = src_m.group(1) if src_m else ""

            alt_m = re.search(r'alt="([^"]*)"', img_tag)
            alt_text = alt_m.group(1) if alt_m else ""

            if img_url and img_url not in seen:
                images.append(img_url)
                seen.add(img_url)

            if alt_text:
                return f"\n[图片: {alt_text}]\n"
            return "\n[图片]\n"

        raw_html = re.sub(r'<img\b[^>]*/?>', _replace_img, raw_html, flags=re.I)

        # ── ③ 替换换行标签 ──
        raw_html = re.sub(r'<br\s*/?>', '\n', raw_html, flags=re.I)

        # ── ④ 删除 script/style 标签 ──
        raw_html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', raw_html, flags=re.I | re.DOTALL)

        # ── ⑤ 块级元素前后插入换行 ──
        block_tags = r'(div|p|h[1-6]|section|article|blockquote|li|tr|ul|ol|table|figure|figcaption|pre)'
        raw_html = re.sub(rf'<{block_tags}\b[^>]*>', '\n', raw_html, flags=re.I)
        raw_html = re.sub(rf'</{block_tags}>', '\n', raw_html, flags=re.I)

        # ── ⑥ 去除所有剩余 HTML 标签 ──
        text = re.sub(r'<[^>]+>', '', raw_html)

        # ── ⑦ HTML 实体解码 ──
        text = html_module.unescape(text)

        # ── ⑧ 空白规范化 ──
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'^\s+', '', text, flags=re.M)
        text = re.sub(r'\s+$', '', text, flags=re.M)

        lines = [l for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        return text, images
