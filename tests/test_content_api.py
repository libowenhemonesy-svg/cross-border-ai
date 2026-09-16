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


@pytest.mark.parametrize("tracker_ready, extractor_ready", [(False, False), (True, False), (False, True)])
def test_daily_skips_unavailable_wechat(backend, monkeypatch, tracker_ready, extractor_ready):
    monkeypatch.setattr(backend, "wechat_tracker", object() if tracker_ready else None)
    monkeypatch.setattr(backend, "wechat_extractor", object() if extractor_ready else None)
    bili = AsyncMock(return_value=(backend.BiliDailyResponse(status="ok", report_text="测试正文"), []))
    wechat = AsyncMock()
    monkeypatch.setattr(backend, "_run_bilibili_daily", bili)
    monkeypatch.setattr(backend, "_run_wechat_daily", wechat)
    response = TestClient(backend.app).post("/api/unified_daily")
    assert response.status_code == 200
    assert "微信服务未就绪，已跳过" in response.json()["report_text"]
    assert response.json()["status"] == "partial"
    assert "测试正文" in response.json()["report_text"]
    bili.assert_awaited_once()
    wechat.assert_not_awaited()


def test_daily_runs_both_available_sources(backend, monkeypatch):
    monkeypatch.setattr(backend, "wechat_tracker", object())
    monkeypatch.setattr(backend, "wechat_extractor", object())
    bili = AsyncMock(return_value=(backend.BiliDailyResponse(status="ok", report_text="B站正文"), []))
    wechat = AsyncMock(return_value=("测试微信日报", "微信正文", 0, 0, []))
    monkeypatch.setattr(backend, "_run_bilibili_daily", bili)
    monkeypatch.setattr(backend, "_run_wechat_daily", wechat)
    response = TestClient(backend.app).post("/api/unified_daily")
    assert response.status_code == 200
    assert "B站正文" in response.json()["report_text"]
    assert "微信正文" in response.json()["report_text"]
    assert response.json()["status"] == "ok"
    bili.assert_awaited_once()
    wechat.assert_awaited_once()


@pytest.mark.parametrize("bili_failed,wechat_failed,expected", [
    (True, False, "partial"), (False, True, "partial"), (True, True, "failed"),
])
def test_daily_reports_platform_failure(backend, monkeypatch, caplog,
                                       bili_failed, wechat_failed, expected):
    monkeypatch.setattr(backend, "wechat_tracker", object())
    monkeypatch.setattr(backend, "wechat_extractor", object())
    monkeypatch.setattr(backend, "_run_bilibili_daily", AsyncMock(
        side_effect=RuntimeError("PRIVATE_PROVIDER_ERROR") if bili_failed else None,
        return_value=(backend.BiliDailyResponse(status="ok", report_text="B站成功内容", processed=1), []),
    ))
    monkeypatch.setattr(backend, "_run_wechat_daily", AsyncMock(
        side_effect=RuntimeError("PRIVATE_PROVIDER_ERROR") if wechat_failed else None,
        return_value=("微信", "微信成功内容", 1, 1, []),
    ))
    response = TestClient(backend.app).post("/api/unified_daily")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == expected
    assert "日报生成失败" in data["report_text"]
    assert "暂无可处理内容" not in data["report_text"]
    assert "PRIVATE_PROVIDER_ERROR" not in response.text + caplog.text
    if not bili_failed:
        assert "B站成功内容" in data["report_text"]
    if not wechat_failed:
        assert "微信成功内容" in data["report_text"]


def test_daily_failed_when_only_available_platform_fails(backend, monkeypatch):
    monkeypatch.setattr(backend, "wechat_tracker", None)
    monkeypatch.setattr(backend, "wechat_extractor", None)
    monkeypatch.setattr(backend, "_run_bilibili_daily", AsyncMock(side_effect=RuntimeError("offline")))
    response = TestClient(backend.app).post("/api/unified_daily")
    assert response.json()["status"] == "failed"
    assert "微信服务未就绪，已跳过" in response.json()["report_text"]


@pytest.mark.parametrize("favorites_available", [False, True])
def test_bili_discovery_failure_is_visible(backend, monkeypatch, caplog, favorites_available):
    from unittest.mock import Mock
    following = Mock()
    following.get_following_feed = AsyncMock(side_effect=RuntimeError("PRIVATE_DISCOVERY_ERROR"))
    favorites = Mock()
    favorites.list_folders = AsyncMock(return_value=[])
    monkeypatch.setattr(backend, "BiliFollowingFetcher", lambda: following)
    monkeypatch.setattr(backend, "BiliFavoritesFetcher", lambda: favorites)
    monkeypatch.setattr(backend, "get_uid_from_cookies", lambda: 1 if favorites_available else 0)
    if favorites_available:
        report, _ = asyncio.run(backend._run_bilibili_daily())
        assert "关注动态读取失败" in report.report_text
        assert "本次结果不完整" in report.report_text
        assert report.processed == 0
        assert report.status == "partial"
    else:
        with pytest.raises(KnowledgeError, match="内容发现失败"):
            asyncio.run(backend._run_bilibili_daily())
    assert "PRIVATE_DISCOVERY_ERROR" not in caplog.text


def test_bili_empty_feed_is_not_failure(backend, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    following = Mock()
    following.get_following_feed = AsyncMock(return_value=SimpleNamespace(items=[]))
    monkeypatch.setattr(backend, "BiliFollowingFetcher", lambda: following)
    monkeypatch.setattr(backend, "get_uid_from_cookies", lambda: 0)
    report, items = asyncio.run(backend._run_bilibili_daily())
    assert "采集异常" not in report.report_text
    assert report.processed == 0
    assert items == []


@pytest.mark.parametrize("statuses,expected", [(["ok", "failed", "skipped"], "partial"), (["failed"], "failed")])
def test_bili_daily_returns_real_counts(backend, monkeypatch, statuses, expected):
    from types import SimpleNamespace
    from unittest.mock import Mock
    following = Mock()
    following.get_following_feed = AsyncMock(return_value=SimpleNamespace(items=[
        SimpleNamespace(bvid=f"BV{i}", title="测试视频", author_name="测试")
        for i in range(len(statuses))
    ]))
    monkeypatch.setattr(backend, "BiliFollowingFetcher", lambda: following)
    monkeypatch.setattr(backend, "get_uid_from_cookies", lambda: 0)
    monkeypatch.setattr(backend, "is_processed", lambda _: False)
    mark = Mock()
    monkeypatch.setattr(backend, "mark_processed", mark)
    monkeypatch.setattr(backend, "_process_single_bili_video", AsyncMock(side_effect=[
        {"status": status, "title": "测试视频", "error": "PRIVATE_ERROR" if status == "failed" else ""}
        for status in statuses
    ]))
    response = TestClient(backend.app).post("/api/bilibili/daily")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == expected
    assert result["processed"] == statuses.count("ok")
    assert result["failed"] == statuses.count("failed")
    assert result["skipped"] == statuses.count("skipped")
    assert [item["status"] for item in result["details"]] == statuses
    assert mark.call_count == statuses.count("ok")
    assert "处理失败: 1 个" in result["report_text"]
    assert "PRIVATE_ERROR" not in response.text


@pytest.mark.parametrize("bili_status,wechat_ready,expected", [
    ("partial", False, "partial"), ("partial", True, "partial"),
    ("failed", False, "failed"), ("failed", True, "partial"),
])
def test_unified_daily_preserves_bili_failure_status(backend, monkeypatch,
                                                    bili_status, wechat_ready, expected):
    monkeypatch.setattr(backend, "wechat_tracker", object() if wechat_ready else None)
    monkeypatch.setattr(backend, "wechat_extractor", object() if wechat_ready else None)
    monkeypatch.setattr(backend, "_run_bilibili_daily", AsyncMock(return_value=(
        backend.BiliDailyResponse(status=bili_status, failed=1), [],
    )))
    monkeypatch.setattr(backend, "_run_wechat_daily", AsyncMock(return_value=("微信", "正文", 0, 0, [])))
    response = TestClient(backend.app).post("/api/unified_daily")
    assert response.json()["status"] == expected
