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


def test_shortened_note_removes_old_chunks(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    note = vault / "note.md"
    note.write_text("# 第一节\n" + "原始资料" * 30 + "\n# 第二节\n" + "过期内容" * 30, encoding="utf-8")
    assert instance.index_vault(str(vault)) == 2
    note.write_text("# 第一节\n" + "更新资料" * 30, encoding="utf-8")
    assert instance.index_vault(str(vault)) == 1
    results = instance.search_knowledge("资料", limit=10)
    assert len(results) == 1
    assert "更新资料" in results[0]["text"]


def test_failed_reindex_preserves_existing_knowledge(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    count = instance.index_vault(str(vault))
    monkeypatch.setattr(instance, "_embed", Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        instance.index_vault(str(vault))
    assert instance.qdrant.count(instance.collection_name).count == count


def test_missing_vault_is_not_success(indexer):
    instance, vault = indexer
    with pytest.raises(ValueError, match="目录不存在"):
        instance.index_vault(str(vault / "missing"))


def test_collection_dimension_mismatch_preserves_data(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    count = instance.index_vault(str(vault))
    with pytest.raises(ValueError, match="维度"):
        vector_indexer.VectorIndexer(api_key="test-only", vector_size=4)
    assert instance.qdrant.count(instance.collection_name).count == count


def test_nested_notes_with_same_name_have_distinct_sources(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    for folder in ("广告", "选品"):
        directory = vault / folder
        directory.mkdir()
        (directory / "note.md").write_text("# 笔记\n" + folder * 60, encoding="utf-8")
    assert instance.index_vault(str(vault)) == 3
    sources = {item["source_file"] for item in instance.search_knowledge("笔记", limit=10)}
    assert sources == {"note.md", "广告/note.md", "选品/note.md"}
    assert instance.index_vault(str(vault)) == 3
    assert instance.qdrant.count(instance.collection_name).count == 3


def test_hidden_folders_are_not_indexed(indexer, monkeypatch):
    instance, vault = indexer
    monkeypatch.setattr(instance, "_embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    hidden = vault / ".trash"
    hidden.mkdir()
    (hidden / "old.md").write_text("已丢弃的内容" * 40, encoding="utf-8")
    assert instance.index_vault(str(vault)) == 1
