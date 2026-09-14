"""真实 FastAPI 路由与内容处理失败回归；不调用外部模型。"""
import asyncio
import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
from ai_processor import AIProcessor
from rag_graph import KnowledgeError


@pytest.mark.parametrize("result", [
    "{}", "[]", '{"summary":""}', "invalid json",
    '{"summary":"测试","modules":[{"title":{},"items":[]}]}',
    '{"summary":"测试","modules":[{"title":"测试","items":[{}]}]}',
    '{"summary":"测试","tags":[{}]}',
])
def test_invalid_extraction_is_an_error(result):
    processor = AIProcessor("test-only")
    processor._call_with_retry = AsyncMock(return_value=result)
    with pytest.raises(KnowledgeError):
        asyncio.run(processor.extract_async("测试输入"))


def test_no_key_does_not_call_provider():
    processor = AIProcessor("")
    processor._call_with_retry = AsyncMock()
    with pytest.raises(KnowledgeError, match="未配置"):
        asyncio.run(processor.extract_async("测试输入"))
    processor._call_with_retry.assert_not_awaited()


@pytest.fixture
def backend(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    module = importlib.import_module("main")
    monkeypatch.setattr(module, "VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(module, "API_KEY", "")
    monkeypatch.setattr(module, "vector_indexer", None)
    return module


def test_missing_key_api_is_503_and_writes_nothing(backend, tmp_path):
    with TestClient(backend.app) as client:
        response = client.post("/api/process_content", json={
            "title": "测试", "raw_text": "仅用于测试的输入",
        })
    assert response.status_code == 503
    assert list(tmp_path.glob("*.md")) == []


def test_extraction_failure_does_not_save_error_note(backend, monkeypatch, tmp_path):
    processor = AIProcessor("test-only")
    processor._call_with_retry = AsyncMock(side_effect=RuntimeError("private-provider-detail"))
    monkeypatch.setattr(backend, "processor", processor)
    client = TestClient(backend.app)
    response = client.post("/api/process_content", json={"title": "测试", "raw_text": "测试"})
    assert response.status_code == 502
    assert "private-provider-detail" not in response.text
    assert list(tmp_path.glob("*.md")) == []


def test_health_not_green_without_dependencies(backend):
    response = TestClient(backend.app).get("/health")
    assert response.json() == {
        "status": "degraded", "vector_db": "disconnected", "model_configured": False,
    }


def test_indexer_recovers_after_initial_connection_failure(backend, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-test-only")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("EMBEDDING_VECTOR_SIZE", "3")
    instance = Mock()
    factory = Mock(side_effect=[RuntimeError("offline"), instance])
    monkeypatch.setattr(backend, "VectorIndexer", factory)

    async def scenario():
        with pytest.raises(KnowledgeError):
            await backend.ensure_indexer()
        assert await backend.ensure_indexer() is instance
        assert await backend.ensure_indexer() is instance

    asyncio.run(scenario())
    assert factory.call_count == 2
    assert factory.call_args.kwargs["api_key"] == "embedding-test-only"
    assert factory.call_args.kwargs["base_url"] == "https://example.com/v1"
    assert factory.call_args.kwargs["vector_size"] == 3


def test_content_processor_accepts_custom_model_endpoint():
    processor = AIProcessor("test-only", base_url="https://example.com/v1")
    assert str(processor.client.base_url) == "https://example.com/v1/"


def test_search_dependency_failure_is_actionable(backend, monkeypatch):
    from unittest.mock import Mock
    indexer = Mock()
    indexer.search_knowledge.side_effect = RuntimeError("private-provider-detail")
    monkeypatch.setattr(backend, "ensure_indexer", AsyncMock(return_value=indexer))
    response = TestClient(backend.app).post("/api/search_knowledge", json={"query": "测试"})
    assert response.status_code == 503
    assert "重试" in response.json()["detail"]
    assert "private-provider-detail" not in response.text


def test_health_detects_disconnect_and_recovery(backend, monkeypatch):
    from unittest.mock import Mock
    indexer = Mock()
    indexer.qdrant.get_collection.side_effect = [RuntimeError("offline"), Mock()]
    monkeypatch.setattr(backend, "vector_indexer", indexer)
    monkeypatch.setattr(backend, "API_KEY", "test-only")
    client = TestClient(backend.app)
    assert client.get("/health").json()["vector_db"] == "disconnected"
    assert client.get("/health").json()["vector_db"] == "connected"


def test_requests_do_not_log_private_body(backend, caplog):
    caplog.set_level(logging.INFO)
    TestClient(backend.app).post("/api/process_content", json={
        "title": "测试", "raw_text": "PRIVATE_BODY_MUST_NOT_BE_LOGGED",
    })
    assert "PRIVATE_BODY_MUST_NOT_BE_LOGGED" not in caplog.text


def test_content_success_saves_source_and_original(backend, monkeypatch, tmp_path):
    processor = AIProcessor("test-only")
    processor._call_with_retry = AsyncMock(return_value='{"summary":"测试摘要","key_points":["测试要点"],"tags":["测试"]}')
    monkeypatch.setattr(backend, "processor", processor)
    response = TestClient(backend.app).post("/api/process_content", json={
        "title": "测试笔记", "raw_text": "测试用原始内容", "url": "https://example.com/source",
    })
    assert response.status_code == 200
    note = (tmp_path / "测试笔记.md").read_text(encoding="utf-8")
    assert "https://example.com/source" in note
    assert "测试用原始内容" in note
    assert response.json()["summary"] == "测试摘要"
