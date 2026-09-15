import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
from obsidian_writer import format_frontmatter
from vector_indexer import _parse_frontmatter


def test_metadata_round_trip_preserves_special_characters():
    source = "https://example.com/article?q=a---b#part"
    tags = ["广告: 优化", "#运营", "多行\n标签", "[选品]", "true"]
    text = format_frontmatter({"source_url": source, "tags": tags}) + "# 原文\n测试正文"
    metadata, body = _parse_frontmatter(text)
    assert metadata["source"] == source
    assert metadata["tags"] == tags
    assert body.strip() == "# 原文\n测试正文"


def test_quoted_source_is_decoded():
    metadata, body = _parse_frontmatter('---\nsource: "https://example.com/note"\n---\n正文')
    assert metadata["source"] == "https://example.com/note"
    assert body.strip() == "正文"


def test_empty_tags_are_a_list():
    text = format_frontmatter({"tags": []})
    assert yaml.safe_load(text.split("---")[1])["tags"] == []


@pytest.mark.parametrize("text", ["正文\n---\n末尾", "---不是元数据\n正文", "---\n没有结束标记"])
def test_plain_markdown_is_preserved(text):
    assert _parse_frontmatter(text) == ({}, text)


@pytest.mark.parametrize("header", ["tags: [", "- item", "source: [one, two]"])
def test_invalid_metadata_is_rejected(header):
    with pytest.raises(ValueError):
        _parse_frontmatter(f"---\n{header}\n---\n正文")
