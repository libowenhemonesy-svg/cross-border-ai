from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import string
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class VideoInfo:
    bvid: str
    aid: int | None
    cid: int | None
    title: str
    author: str
    description: str
    pubdate: str | None
    tags: list[str]
    pages: list[dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a Bilibili video and save an Obsidian note."
    )
    parser.add_argument("--url", required=True, help="Bilibili video URL, e.g. https://www.bilibili.com/video/BV...")
    parser.add_argument("--cookie", required=True, help="Path to Netscape-format cookie.txt")
    parser.add_argument("--vault", required=True, help="Obsidian vault directory or output folder")
    parser.add_argument("--folder", default="Bilibili", help="Folder inside vault, default: Bilibili")
    return parser.parse_args()


def extract_bvid(url: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise ValueError("未能从链接中识别 BV 号，请确认输入的是 Bilibili 视频链接。")
    return match.group(1)


def load_cookie_jar(cookie_path: Path) -> http.cookiejar.MozillaCookieJar:
    if not cookie_path.exists():
        raise FileNotFoundError(f"cookie 文件不存在：{cookie_path}")
    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    jar.load(ignore_discard=True, ignore_expires=True)
    return jar


def fetch_text(url: str, cookie_jar: http.cookiejar.CookieJar, referer: str | None = None) -> str:
    scrapling_text = fetch_with_scrapling(url, cookie_jar, referer)
    if scrapling_text:
        return scrapling_text

    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with opener.open(request, timeout=30) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def fetch_with_scrapling(
    url: str,
    cookie_jar: http.cookiejar.CookieJar,
    referer: str | None = None,
) -> str | None:
    try:
        from scrapling.fetchers import Fetcher  # type: ignore
    except Exception:
        return None

    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    cookie_header = build_cookie_header(cookie_jar, url)
    if cookie_header:
        headers["Cookie"] = cookie_header
    try:
        page = Fetcher.get(url, headers=headers, timeout=30000)
    except Exception:
        return None
    text = getattr(page, "text", None)
    return text if isinstance(text, str) and text.strip() else None


def build_cookie_header(cookie_jar: http.cookiejar.CookieJar, url: str) -> str:
    hostname = urlparse(url).hostname or ""
    parts = []
    for cookie in cookie_jar:
        domain = cookie.domain.lstrip(".")
        if hostname.endswith(domain):
            parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts)


def extract_initial_state(html: str) -> dict[str, Any]:
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*\(function", html, re.S)
    if not match:
        match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});", html, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def parse_video_info(bvid: str, html: str, cookie_jar: http.cookiejar.CookieJar, referer: str) -> VideoInfo:
    state = extract_initial_state(html)
    video_data = state.get("videoData") or {}
    api_data = fetch_view_info(bvid, cookie_jar, referer)
    if api_data:
        video_data = {**api_data, **video_data}

    title = video_data.get("title") or extract_meta(html, "title") or bvid
    author = (video_data.get("owner") or {}).get("name") or ""
    description = video_data.get("desc") or extract_meta(html, "description") or ""
    aid = video_data.get("aid")
    pages = video_data.get("pages") or []
    cid = pages[0].get("cid") if pages else video_data.get("cid")
    pubdate = format_ts(video_data.get("pubdate"))

    if not pages:
        pages = fetch_pagelist(bvid, cookie_jar, referer)
        if pages and not cid:
            cid = pages[0].get("cid")

    tags = []
    for item in state.get("tags", []) or []:
        tag_name = item.get("tag_name") if isinstance(item, dict) else None
        if tag_name:
            tags.append(str(tag_name))

    return VideoInfo(
        bvid=bvid,
        aid=aid if isinstance(aid, int) else None,
        cid=cid if isinstance(cid, int) else None,
        title=clean_text(title),
        author=clean_text(author),
        description=clean_text(description),
        pubdate=pubdate,
        tags=tags,
        pages=pages,
    )


def fetch_view_info(bvid: str, cookie_jar: http.cookiejar.CookieJar, referer: str) -> dict[str, Any]:
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    try:
        payload = json.loads(fetch_text(url, cookie_jar, referer=referer))
    except Exception:
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def extract_meta(html: str, name: str) -> str | None:
    pattern = rf'<meta\s+name="{re.escape(name)}"\s+content="(.*?)"'
    match = re.search(pattern, html, re.S | re.I)
    if match:
        return html_unescape(match.group(1))
    if name == "title":
        title_match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if title_match:
            return html_unescape(title_match.group(1))
    return None


def fetch_pagelist(bvid: str, cookie_jar: http.cookiejar.CookieJar, referer: str) -> list[dict[str, Any]]:
    url = f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}&jsonp=jsonp"
    try:
        data = json.loads(fetch_text(url, cookie_jar, referer=referer))
    except Exception:
        return []
    pages = data.get("data")
    return pages if isinstance(pages, list) else []


def fetch_subtitle(video: VideoInfo, cookie_jar: http.cookiejar.CookieJar, referer: str) -> str:
    if not video.cid:
        return ""
    url = f"https://api.bilibili.com/x/player/v2?bvid={video.bvid}&cid={video.cid}"
    try:
        data = json.loads(fetch_text(url, cookie_jar, referer=referer))
    except Exception:
        return ""

    subtitles = (((data.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
    if not subtitles:
        return ""

    subtitle_url = subtitles[0].get("subtitle_url")
    if not subtitle_url:
        return ""
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url

    try:
        subtitle_data = json.loads(fetch_text(subtitle_url, cookie_jar, referer=referer))
    except Exception:
        return ""

    lines = []
    for item in subtitle_data.get("body", []) or []:
        content = clean_text(str(item.get("content", "")))
        if content:
            lines.append(content)
    return "\n".join(lines)


def summarize(text: str, fallback: str) -> str:
    source = clean_text(text or fallback)
    if not source:
        return "暂无可用正文，建议后续通过 Whisper 对音频进行转写后补全摘要。"
    sentences = split_sentences(source)
    if not sentences:
        return source[:220]
    return " ".join(sentences[:3])[:360]


def extract_keywords(text: str, base_tags: list[str], limit: int = 12) -> list[str]:
    keywords = [tag for tag in base_tags if tag]
    source = re.sub(r"https?://\S+", " ", text)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{2,}", source)
    stop_words = {
        "这个", "一个", "我们", "可以", "进行", "以及", "因为", "所以", "如果", "但是",
        "就是", "没有", "视频", "内容", "大家", "自己", "什么", "通过", "对于", "需要",
        "the", "and", "for", "with", "from", "this", "that",
    }
    counts = Counter(token for token in tokens if token.lower() not in stop_words)
    for word, _ in counts.most_common(limit * 2):
        if word not in keywords:
            keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords[:limit]


def build_markdown(video: VideoInfo, url: str, transcript: str) -> str:
    source_text = "\n".join([video.title, video.description, transcript])
    keywords = extract_keywords(source_text, video.tags)
    summary = summarize(transcript, video.description)
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    obsidian_tags = ["bilibili", "AI内容沉淀"] + keywords[:6]
    safe_tags = [to_obsidian_tag(tag) for tag in obsidian_tags if to_obsidian_tag(tag)]

    transcript_block = transcript.strip() or (
        "该视频未读取到平台字幕。生产版流程会进入音频下载与 Whisper 转写步骤；"
        "本 Demo 先保留该状态，便于展示异常分支和后续扩展点。"
    )
    pages_text = "\n".join(
        f"- P{index + 1}: {clean_text(str(page.get('part', '')))}"
        for index, page in enumerate(video.pages)
    ) or "- 单 P 视频或暂未读取到分 P 信息"

    return f"""---
title: "{yaml_escape(video.title)}"
source: "Bilibili"
url: "{yaml_escape(url)}"
bvid: "{video.bvid}"
author: "{yaml_escape(video.author)}"
published: "{video.pubdate or ''}"
created: "{created}"
tags: [{", ".join(f'"{tag}"' for tag in safe_tags)}]
---

# {video.title}

## 基本信息

- 来源平台：Bilibili
- 原始链接：{url}
- BV 号：{video.bvid}
- UP 主：{video.author or "未识别"}
- 发布时间：{video.pubdate or "未识别"}

## 自动摘要

{summary}

## 关键词 / 标签

{", ".join(keywords) if keywords else "暂无"}

## 分 P 信息

{pages_text}

## 原始简介

{video.description or "暂无简介"}

## 转文字结果

{transcript_block}

## 后续处理建议

- 将关键词同步为 Obsidian 标签，便于按主题聚合。
- 如果字幕为空，进入 Whisper 转写分支补全文本。
- 对摘要结果进行人工复核后，可沉淀到专题笔记或 MOC 页面。
"""


def save_note(markdown: str, vault: Path, folder: str, title: str) -> Path:
    output_dir = vault / folder
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(title) + ".md"
    path = output_dir / filename
    path.write_text(markdown, encoding="utf-8")
    return path


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text.replace("\n", " "))
    return [clean_text(part) for part in parts if clean_text(part)]


def format_ts(value: Any) -> str | None:
    if not isinstance(value, int):
        return None
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html_unescape(text)).strip()


def html_unescape(text: str) -> str:
    return (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
    )


def yaml_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_obsidian_tag(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"[^\w\u4e00-\u9fff/-]+", "", text)
    return text.strip("/").replace(" ", "")


def safe_filename(title: str) -> str:
    invalid = '<>:"/\\|?*'
    table = str.maketrans({char: "_" for char in invalid + string.whitespace})
    name = title.translate(table)
    name = re.sub(r"_+", "_", name).strip("._ ")
    return name[:80] or "bilibili_note"


def main() -> int:
    args = parse_args()
    bvid = extract_bvid(args.url)
    cookie_path = Path(args.cookie).expanduser()
    vault = Path(args.vault).expanduser()
    cookie_jar = load_cookie_jar(cookie_path)
    referer = f"https://www.bilibili.com/video/{bvid}"

    print(f"Fetching Bilibili video: {bvid}")
    html = fetch_text(referer, cookie_jar, referer="https://www.bilibili.com/")
    video = parse_video_info(bvid, html, cookie_jar, referer)
    transcript = fetch_subtitle(video, cookie_jar, referer)
    markdown = build_markdown(video, args.url, transcript)
    output_path = save_note(markdown, vault, args.folder, video.title)

    print(f"Saved Obsidian note: {output_path}")
    if not transcript:
        print("No platform subtitle found. The note includes a Whisper fallback placeholder.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
