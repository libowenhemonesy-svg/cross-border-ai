"""本地 Qdrant + 真实 Markdown 分块，Embedding 仅使用显式测试替身。"""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
import vector_indexer


@pytest.fixture
def indexer(monkeypatch, tmp_path):
    database = QdrantClient(":memory:")
    monkeypatch.setattr(vector_indexer, "QdrantClient", lambda **kwargs: database)
    instance = vector_indexer.VectorIndexer(api_key="test-only", vector_size=3)
    (tmp_path / "note.md").write_text(
        "---\nsource: https://example.com/note\n---\n# 测试笔记\n"
        + "这段原文只用于本地集成测试，不是运营建议，也不作为产品的演示答案。" * 5,
        encoding="utf-8",
    )
    yield instance, tmp_path
    database.close()


def test_index_and_retrieve_preserve_source(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    count = instance.index_vault(str(vault))
    assert count > 0
    result = instance.search_knowledge("测试", limit=1)
    assert result[0]["source_file"] == "note.md"
    assert result[0]["source_url"] == "https://example.com/note"
    assert "本地集成测试" in result[0]["text"]
    assert instance.index_vault(str(vault)) == count
    assert instance.qdrant.count(instance.collection_name).count == count


@pytest.mark.parametrize("vectors", [[], [[1.0, 0.0]]])
def test_invalid_vectors_never_write(indexer, monkeypatch, vectors):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: vectors)
    with pytest.raises(RuntimeError, match="本次索引未写入"):
        instance.index_vault(str(vault))
    assert instance.qdrant.count(instance.collection_name).count == 0


def test_provider_failure_not_reported_as_success(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", Mock(side_effect=RuntimeError("test-provider-error")))
    with pytest.raises(RuntimeError, match="向量化失败"):
        instance.index_vault(str(vault))
    assert instance.qdrant.count(instance.collection_name).count == 0
