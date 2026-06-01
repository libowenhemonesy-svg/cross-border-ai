"""
Obsidian 写入器 — 生成带 YAML Frontmatter 的 Markdown 并保存到本地 Vault
支持中英双语精读格式，含逐句对齐翻译与词汇标注
"""

import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 北京时间
TZ = timezone(timedelta(hours=8))


def sanitize_filename(title: str) -> str:
    """将标题转为安全的文件名（替换 Windows/macOS 非法字符）"""
    safe = re.sub(r'[\\/:*?"<>|]', "-", title)
    return safe.strip()[:120]


def format_frontmatter(data: dict) -> str:
    """生成 Obsidian 兼容的 YAML Frontmatter

    输入 data 字典预期包含：
      - summary:       str  标题/摘要
      - key_points:    list 核心观点
      - tags:          list 分类标签
      - source_url:    str  原文链接（可选）
      - close_reading: list 逐句精读数据（可选）
    """
    now = datetime.now(TZ).strftime("%Y-%m-%d")

    tags = data.get("tags", [])
    tags_yaml = "\n  - ".join(tags)
    if tags_yaml:
        tags_yaml = "\n  - " + tags_yaml

    source = data.get("source_url", "")
    source_line = f"\nsource: {source}" if source else ""

    return f"""---
date: {now}
tags:{tags_yaml}{source_line}
---

"""


def _format_vocabulary(vocab_list: list[dict]) -> str:
    """将词汇标注列表渲染为 Markdown 列表行"""
    if not vocab_list:
        return ""
    lines = []
    for v in vocab_list:
        term = v.get("term", "")
        annotation = v.get("annotation", "")
        if term and annotation:
            lines.append(f"> - **{term}**：{annotation}")
        elif term:
            lines.append(f"> - **{term}**")
    return "\n".join(lines)


def format_modules(modules: list[dict]) -> str:
    """渲染「模块化知识卡片」章节 (v4.0)

    每个模块以二级标题呈现，条目以有序列表排列。
    模块标题使用对应图标前缀，提升视觉辨识度。
    """
    if not modules:
        return ""

    MODULE_ICONS = {
        "可操作方法": "📋",
        "数据参考": "📊",
        "避坑指南": "⚠️",
        "行业洞察": "🔍",
        "工具资源": "🛠",
        "案例拆解": "📖",
    }

    parts = ["## 知识模块\n"]
    for m in modules:
        title = m.get("title", "其他")
        items = m.get("items", [])
        if not items:
            continue
        icon = MODULE_ICONS.get(title, "📌")
        parts.append(f"### {icon} {title}\n")
        for i, item in enumerate(items, 1):
            parts.append(f"{i}. {item}")
        parts.append("")
    return "\n".join(parts)


def format_close_reading(entries: list[dict]) -> str:
    """渲染「核心长难句精读」章节

    每条精读条目以 Markdown Blockquote 呈现，包含：
      - 英文原句
      - 中文对齐翻译
      - 商业/技术词汇标注

    输出示例：
    > **原文**
    > English sentence...
    > **译文**
    > 中文翻译...
    > **词汇标注**
    > - **RAG**：检索增强生成...
    """
    if not entries:
        return ""

    parts = ["## 核心长难句精读\n"]

    for i, entry in enumerate(entries, 1):
        original = entry.get("original", "").strip()
        translation = entry.get("translation", "").strip()
        vocabulary = entry.get("vocabulary", [])

        if not original and not translation:
            continue

        block_lines = [f"> **原文**"]

        # 原文可能含多行，每行都加 blockquote 前缀
        for line in original.split("\n"):
            block_lines.append(f"> {line.strip()}")

        block_lines.append("> ")
        block_lines.append(f"> **译文**")
        for line in translation.split("\n"):
            block_lines.append(f"> {line.strip()}")

        # 词汇标注
        vocab_block = _format_vocabulary(vocabulary)
        if vocab_block:
            block_lines.append("> ")
            block_lines.append(f"> **词汇标注**")
            block_lines.append(vocab_block)

        parts.append("\n".join(block_lines))
        parts.append("")  # 条目间空行

    return "\n".join(parts)


def format_full_text(text: str) -> str:
    """渲染「原文实录」章节 — 保留原始转录/输入文本供溯源和复习"""
    if not text or not text.strip():
        return ""
    char_count = len(text)
    return f"""---

## 原文实录

> 以下为原始转录文本，由 AI 自动生成，共 {char_count} 字。保留完整内容以便溯源和深度复习。

{text}
"""


def format_body(data: dict) -> str:
    """生成 Markdown 正文"""
    summary = data.get("summary", "")
    modules = data.get("modules", [])
    key_points = data.get("key_points", [])
    source_url = data.get("source_url", "")
    full_text = data.get("full_text", "")
    close_reading = data.get("close_reading", [])

    parts = [f"# {summary}\n"] if summary else []

    # v4.0 模块化知识卡片（优先）
    if modules:
        parts.append(format_modules(modules))
    elif key_points:
        # 降级：旧格式平铺观点
        parts.append("## 核心观点\n")
        for i, point in enumerate(key_points, 1):
            parts.append(f"{i}. {point}")
        parts.append("")

    # 逐句精读章节（英文内容专用）
    if close_reading:
        parts.append(format_close_reading(close_reading))

    if source_url:
        parts.append(f"> 原文链接: {source_url}\n")

    # 原始全文实录（用于溯源与深度复习）
    if full_text:
        parts.append(format_full_text(full_text))

    return "\n".join(parts)


def write_to_vault(data: dict, vault_path: str = None, filename: str = None) -> str:
    """将 AI 提取的数据写入 Obsidian Vault .md 文件

    Args:
        data: AI 提取结果字典，含 summary / key_points / tags / source_url / close_reading
        vault_path: Obsidian Vault 路径，默认 ../obsidian_vault
        filename:  输出文件名（不含扩展名），默认取 summary 前 80 字符

    Returns:
        写入的 .md 文件绝对路径
    """
    if vault_path is None:
        vault_path = str(Path(__file__).resolve().parent.parent / "obsidian_vault")

    os.makedirs(vault_path, exist_ok=True)

    if filename is None:
        summary = data.get("summary", "").strip()
        filename = summary[:80] if summary else datetime.now(TZ).strftime("note_%Y%m%d_%H%M%S")

    filename = sanitize_filename(filename)
    filepath = os.path.join(vault_path, f"{filename}.md")

    content = format_frontmatter(data) + format_body(data)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return os.path.abspath(filepath)
