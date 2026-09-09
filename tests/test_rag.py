"""使用显式注入的测试替身验证真实 LangGraph 执行与 HTTP 错误边界。"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
import rag_graph
from rag_api import create_rag_router
from rag_graph import KnowledgeError, build_graph

SOURCE = {"text": "测试提供的原文", "source_file": "note.md", "source_url": "", "score": 0.8}


def client_for(retrieve, generate):
    app = FastAPI()
    app.include_router(create_rag_router(build_graph(retrieve, generate)))
    return TestClient(app)


def test_answer_and_sources():
    retrieve = AsyncMock(return_value=[SOURCE])
    generate = AsyncMock(return_value={"supported": True, "answer": "测试模型回答", "citation_ids": [1]})
    with client_for(retrieve, generate) as client:
        response = client.post("/api/ask_knowledge", json={"question": " 测试问题 "})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["sources"] == [dict(SOURCE, id=1)]
    assert response.json()["citation_ids"] == [1]
    retrieve.assert_awaited_once_with("测试问题")


def test_no_data_never_calls_model():
    generate = AsyncMock()
    with client_for(AsyncMock(return_value=[]), generate) as client:
        response = client.post("/api/ask_knowledge", json={"question": "问题"})
    assert response.json()["status"] == "no_data"
    generate.assert_not_awaited()


@pytest.mark.parametrize("question", ["", " ", "x" * 8001])
def test_invalid_question(question):
    retrieve = AsyncMock()
    with client_for(retrieve, AsyncMock()) as client:
        assert client.post("/api/ask_knowledge", json={"question": question}).status_code == 422
    retrieve.assert_not_awaited()


@pytest.mark.parametrize("result", [
    {"supported": True, "answer": "答案", "citation_ids": [99]},
    {"supported": True, "answer": "答案", "citation_ids": []},
    {"supported": True, "answer": "", "citation_ids": [1]},
    {"supported": True, "answer": "答案", "citation_ids": [True]},
    {"supported": False, "answer": "不足", "citation_ids": [1]},
])
def test_invalid_model_answer_rejected(result):
    with client_for(AsyncMock(return_value=[SOURCE]), AsyncMock(return_value=result)) as client:
        assert client.post("/api/ask_knowledge", json={"question": "问题"}).status_code == 502


def test_insufficient_context():
    result = {"supported": False, "answer": "资料没有相关信息", "citation_ids": []}
    with client_for(AsyncMock(return_value=[SOURCE]), AsyncMock(return_value=result)) as client:
        response = client.post("/api/ask_knowledge", json={"question": "问题"})
    assert response.json()["status"] == "insufficient_context"


def test_retrieval_unavailable():
    with client_for(AsyncMock(side_effect=KnowledgeError("检索不可用", 503)), AsyncMock()) as client:
        assert client.post("/api/ask_knowledge", json={"question": "问题"}).status_code == 503


def test_missing_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with pytest.raises(KnowledgeError, match="未配置"):
        asyncio.run(rag_graph.generate_answer("问题", [SOURCE]))


@pytest.mark.parametrize("status, payload", [
    (200, {"choices": [{"message": {"content": '{"supported":true,"answer":"回答","citation_ids":[1]}'}}]}),
    (401, {"error": "secret-from-provider"}),
    (200, {"choices": [{"message": {"content": "not json"}}]}),
])
def test_model_transport(monkeypatch, status, payload):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    monkeypatch.setenv("AI_BASE_URL", "https://model.test/v1")
    original = httpx.AsyncClient

    def respond(request):
        assert str(request.url) == "https://model.test/v1/chat/completions"
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        rag_graph.httpx, "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    if status == 200 and payload["choices"][0]["message"]["content"].startswith("{"):
        assert asyncio.run(rag_graph.generate_answer("问题", [SOURCE]))["citation_ids"] == [1]
    else:
        with pytest.raises(KnowledgeError) as caught:
            asyncio.run(rag_graph.generate_answer("问题", [SOURCE]))
        assert "secret-from-provider" not in str(caught.value)


def test_requests_do_not_share_state():
    retrieve = AsyncMock(side_effect=[[SOURCE], []])
    generate = AsyncMock(return_value={"supported": True, "answer": "答案", "citation_ids": [1]})
    with client_for(retrieve, generate) as client:
        client.post("/api/ask_knowledge", json={"question": "一"})
        second = client.post("/api/ask_knowledge", json={"question": "二"}).json()
    assert second["sources"] == []
    assert second["citation_ids"] == []
    assert second["status"] == "no_data"
