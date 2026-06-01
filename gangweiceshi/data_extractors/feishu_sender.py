"""
飞书消息推送模块 — 将日报 Markdown 转换为飞书卡片消息并通过 Webhook 发送

使用方式:
  1. 在飞书群聊中 → 设置 → 群机器人 → 添加自定义机器人
  2. 复制 Webhook URL，设置为环境变量 FEISHU_WEBHOOK_URL
  3. 调用 send_daily_report(title, markdown_text) 即可推送到飞书群

飞书自定义机器人 Webhook 文档: https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))

# 飞书卡片颜色常量
COLOR_GREEN = "green"
COLOR_BLUE = "blue"
COLOR_RED = "red"
COLOR_YELLOW = "yellow"


def _sign(secret: str, timestamp: str) -> str:
    """飞书安全设置：HMAC-SHA256 签名（如果机器人配置了签名校验）"""
    string_to_sign = f"{timestamp}\n{secret}"
    return hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def markdown_to_feishu_card(title: str, markdown_text: str) -> dict[str, Any]:
    """将日报 Markdown 转换为飞书「交互卡片」格式

    卡片结构（适配统一日报格式）:
      ┌──────────────────────────────────┐
      │  📊 跨境知识日报_2026-05-27       │  ← 蓝色标题栏
      ├──────────────────────────────────┤
      │  📈 B站 3篇 + 微信 2篇 = 5篇     │
      ├──────────────────────────────────┤
      │  🏷️ 选品策略（3篇）               │
      │  · 标题1 📺 — AI摘要...           │
      │  · 标题2 📱 — AI摘要...           │
      ├──────────────────────────────────┤
      │  🏷️ FBA运营（2篇）               │
      │  · 标题3 📺 — AI摘要...           │
      ├──────────────────────────────────┤
      │  📝 待处理 (5个)                 │
      │  · 标题4 · 标题5 ...             │
      └──────────────────────────────────┘
    """
    sections = _parse_report_sections(markdown_text)

    elements: list[dict] = []

    # ── 统计区 ──
    if sections.get("stats"):
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**📈 {sections['stats']}**"},
        })
        elements.append({"tag": "hr"})

    # ── 按主题归类（重点区块）──
    topic_groups = sections.get("topic_groups", [])
    if topic_groups:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "**📚 今日知识主题**"},
        })
        for group in topic_groups[:8]:
            name = group["name"]
            count = group["count"]
            items = group["items"]
            lines = [f"**🏷️ {name}（{count}篇）**"]
            for item in items[:6]:
                src = item.get("source_icon", "")
                t = item["title"]
                s = item.get("summary", "")
                if len(s) > 60:
                    s = s[:60] + "..."
                if s:
                    lines.append(f"· {t} {src} — {s}")
                else:
                    lines.append(f"· {t} {src}")
                # 展示模块详情（每模块截断到 30 字）
                mods = item.get("modules", [])
                if mods:
                    mod_previews = []
                    for mod in mods[:4]:
                        mod_text = mod.lstrip("· ").strip()
                        if len(mod_text) > 40:
                            mod_text = mod_text[:40] + "..."
                        mod_previews.append(mod_text)
                    if mod_previews:
                        lines.append(f"  ↳ {' | '.join(mod_previews)}")
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(lines)},
            })

        total_items = sum(g["count"] for g in topic_groups)
        shown_items = sum(min(len(g["items"]), 6) for g in topic_groups[:8])
        if shown_items < total_items:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"*…还有 {total_items - shown_items} 篇，完整报告见 Obsidian 知识库*"},
            })
        elements.append({"tag": "hr"})

    # ── 回退：无主题归类时用旧版"新增沉淀"格式 ──
    if not topic_groups:
        new_items = sections.get("new_items", [])
        if new_items:
            content = "**✅ 新增沉淀内容**\n" + "\n".join(f"· {item}" for item in new_items[:12])
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            })
            if len(new_items) > 12:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"*...还有 {len(new_items) - 12} 篇*"},
                })
            elements.append({"tag": "hr"})

    # ── 待处理 ──
    pending_items = sections.get("pending_items", [])
    if pending_items:
        pending_title = sections.get("pending_title", "待处理")
        # 压缩待处理为一行，节省卡片空间
        item_preview = " · ".join(pending_items[:10])
        if len(pending_items) > 10:
            item_preview += f" ...共{len(pending_items)}个"
        content = f"**📝 {pending_title}**\n{item_preview}"
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": content},
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": f"🤖 自动生成 · {datetime.now(TZ).strftime('%m-%d %H:%M')} · 完整报告见 Obsidian",
        }],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 {title}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def _parse_report_sections(md: str) -> dict:
    """解析日报 Markdown，提取各板块内容

    支持两种日报格式：
    1. 统一日报：## 统计 + ## 按主题归类（含 ### 子段）+ #### 待处理
    2. 旧版日报：## 统计 + ## 新增沉淀内容 + ## 待处理
    """
    result: dict[str, Any] = {
        "stats": "",
        "topic_groups": [],    # [{name, count, items: [{title, source_icon, summary, tags}]}]
        "new_items": [],       # 回退用：旧版格式的纯文本条目
        "pending_items": [],
        "pending_title": "待处理",
    }

    # ── ① 统计 ──
    stats_match = re.search(r'## 统计\n(.*?)(?=\n## |\Z)', md, re.DOTALL)
    if stats_match:
        lines = stats_match.group(1).strip().split("\n")
        stats_lines = [l.strip("- ").strip() for l in lines if l.strip().startswith("-")]
        result["stats"] = " | ".join(stats_lines)

    # ── ② 按主题归类（统一日报新格式）──
    topic_match = re.search(r'## 按主题归类\n(.*?)(?=\n---|\n## [^#]|\Z)', md, re.DOTALL)
    if topic_match:
        topic_block = topic_match.group(1)
        # 按 ### 分割各主题子段
        subsections = re.split(r'\n(?=### )', topic_block.strip())
        for sub in subsections:
            sub = sub.strip()
            if not sub:
                continue
            # 第一行: ### 主题名（N篇）
            header_match = re.match(r'### (.+?)（(\d+)\s*篇）', sub)
            if not header_match:
                continue
            group_name = header_match.group(1).strip()
            group_count = int(header_match.group(2))
            group_items: list[dict] = []

            # 解析条目: 每个条目以 "- **标题**" 开头，后续行是 💡/🔗/🏷️
            body = sub[header_match.end():]
            entries = re.split(r'\n(?=-\s\*\*)', body.strip())
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                lines = entry.split("\n")
                # 第一行: - **标题** 📺 或 - **标题** 📱
                first = lines[0]
                title_match = re.match(r'-\s\*\*(.+?)\*\*\s*([📺📱])?', first)
                if not title_match:
                    continue
                item_title = title_match.group(1).strip()
                source_icon = title_match.group(2) or ""
                item_summary = ""
                item_tags: list[str] = []
                item_link = ""
                item_modules: list[str] = []  # 模块详情

                for line in lines[1:]:
                    stripped = line.strip()
                    if stripped.startswith("💡"):
                        item_summary = stripped[2:].strip()
                    elif stripped.startswith("🔗"):
                        item_link = stripped[2:].strip()
                    elif stripped.startswith("🏷️"):
                        tags_text = stripped[2:].strip()
                        item_tags = [t.strip() for t in tags_text.split("·") if t.strip()]
                    elif stripped.startswith("·") and ":" in stripped:
                        item_modules.append(stripped)

                group_items.append({
                    "title": item_title,
                    "source_icon": source_icon,
                    "summary": item_summary,
                    "tags": item_tags,
                    "link": item_link,
                    "modules": item_modules,
                })

            if group_items:
                result["topic_groups"].append({
                    "name": group_name,
                    "count": group_count,
                    "items": group_items,
                })

        # 回退：无 ### 子段 → 分散格式，直接提取条目到 new_items
        if not result["topic_groups"] and topic_block.strip():
            # 跳过说明行（如 *今日各篇主题分散...*）
            body = topic_block.strip()
            body = re.sub(r'^\*[^\n]+\*\s*\n+', '', body)
            entries = re.split(r'\n(?=-\s\*\*)', body)
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                lines = entry.split("\n")
                title_match = re.match(r'-\s\*\*(.+?)\*\*', lines[0])
                if not title_match:
                    continue
                title = title_match.group(1)
                parts = [title]
                # 提取摘要和模块作为补充信息
                for line in lines[1:]:
                    stripped = line.strip()
                    if stripped.startswith("💡"):
                        parts.append(stripped)
                    elif stripped.startswith("·") and ":" in stripped:
                        parts.append(stripped)
                result["new_items"].append(" — ".join(parts) if len(parts) > 1 else title)

    # ── ③ 新增沉淀内容（旧版格式回退）──
    new_match = re.search(r'## 新增沉淀内容\n(.*?)(?=\n## |\Z)', md, re.DOTALL)
    if new_match:
        block = new_match.group(1)
        old_items = re.findall(r'- \[(.*?)\]', block)
        if old_items:
            result["new_items"] = old_items
        else:
            entries = re.split(r'\n(?=-\s\*\*)', block.strip())
            for entry in entries:
                lines = entry.strip().split("\n")
                if not lines:
                    continue
                title_match = re.match(r'-\s\*\*(.+?)\*\*', lines[0])
                if not title_match:
                    continue
                title = title_match.group(1)
                details = []
                for line in lines[1:]:
                    stripped = line.strip()
                    if stripped.startswith("💡"):
                        details.append(stripped)
                    elif stripped.startswith("·"):
                        details.append(stripped)
                if details:
                    result["new_items"].append(f"{title} — {' '.join(details)}")
                else:
                    result["new_items"].append(title)

    # ── ④ 待处理 ──
    # 优先匹配四级标题格式: #### 待处理 (N个)
    pend4_match = re.search(r'#### 待处理.*?\n(.*?)(?=\n##|\n###|\Z)', md, re.DOTALL)
    if pend4_match:
        title_match = re.search(r'#### (待处理.*)', md)
        if title_match:
            result["pending_title"] = title_match.group(1)
        items = re.findall(r'- \[(.*?)\]', pend4_match.group(1))
        if not items:
            items = re.findall(r'- (.*?)(?:\n|$)', pend4_match.group(1))
        result["pending_items"] = [i.strip() for i in items if i.strip()]
    else:
        # 回退二级标题格式
        pend_match = re.search(r'## 待处理.*\n(.*?)(?=\n## |\Z)', md, re.DOTALL)
        if pend_match:
            title_match = re.search(r'## (待处理.*)', md)
            if title_match:
                result["pending_title"] = title_match.group(1)
            items = re.findall(r'- (.*?)(?:\n|$)', pend_match.group(1))
            result["pending_items"] = [i.strip() for i in items if i.strip()]

    return result


async def send_via_webhook(
    webhook_url: str,
    payload: dict,
    secret: str | None = None,
    timeout: int = 30,
) -> tuple[bool, str]:
    """通过飞书 Webhook 发送消息

    Args:
        webhook_url: 飞书机器人 Webhook 地址
        payload: 消息体
        secret: 签名校验密钥（机器人安全设置）
        timeout: 请求超时（秒）

    Returns:
        (是否成功, 错误信息)
    """
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = _sign(secret, ts)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(webhook_url, json=payload)
            data = resp.json()

            if data.get("code") == 0:
                logger.info(f"飞书推送成功 → StatusCode={data.get('StatusCode', 0)}")
                return True, ""
            else:
                err = f"飞书 API 错误: code={data.get('code')}, msg={data.get('msg')}"
                logger.error(err)
                return False, err
    except httpx.TimeoutException:
        return False, "飞书 Webhook 请求超时"
    except Exception as e:
        return False, str(e)


async def send_daily_report(
    title: str,
    markdown_text: str,
    webhook_url: str | None = None,
    secret: str | None = None,
) -> tuple[bool, str]:
    """发送日报到飞书群

    Args:
        title: 日报标题
        markdown_text: 日报 Markdown 正文
        webhook_url: 覆盖环境变量的 Webhook URL
        secret: 覆盖环境变量的签名密钥

    Returns:
        (是否成功, 消息)
    """
    url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
    sec = secret or os.getenv("FEISHU_WEBHOOK_SECRET", "").strip() or None

    if not url:
        return False, "未配置 FEISHU_WEBHOOK_URL 环境变量"

    card = markdown_to_feishu_card(title, markdown_text)
    ok, err = await send_via_webhook(url, card, sec)

    if ok:
        return True, "日报已推送到飞书"
    return False, f"飞书推送失败: {err}"
