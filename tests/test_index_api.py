import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
from index_api import create_index_router


def test_index_status_and_retry():
    indexer = Mock()
    indexer.index_vault.side_effect = [RuntimeError("private-key"), 3]
    app = FastAPI()
    app.include_router(create_index_router(AsyncMock(return_value=indexer), "/test-vault"))
    with TestClient(app) as client:
        assert client.get("/api/knowledge/index").json()["status"] == "idle"
        assert client.post("/api/knowledge/index").status_code == 202
        failed = client.get("/api/knowledge/index").json()
        assert failed["status"] == "failed"
        assert "private-key" not in failed["error"]
        client.post("/api/knowledge/index")
        result = client.get("/api/knowledge/index").json()
        assert result["status"] == "succeeded"
        assert result["chunks"] == 3
        assert result["error"] == ""
        assert result["finished_at"]


def test_duplicate_requests_schedule_one_task():
    from starlette.background import BackgroundTasks

    async def scenario():
        router = create_index_router(AsyncMock(), "/test-vault")
        start = next(route.endpoint for route in router.routes if "POST" in route.methods)
        first, second = BackgroundTasks(), BackgroundTasks()
        results = await asyncio.gather(start(first), start(second))
        assert all(result["status"] == "running" for result in results)
        assert len(first.tasks) + len(second.tasks) == 1

    asyncio.run(scenario())
