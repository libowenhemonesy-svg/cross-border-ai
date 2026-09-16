"""单进程知识索引任务：页面可触发并查询进度。"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from knowledge_files import markdown_files


def create_index_router(get_indexer, vault_path):
    router = APIRouter()
    state = {"status": "idle", "chunks": None, "error": "", "finished_at": None}

    def list_documents():
        vault = Path(vault_path)
        files = markdown_files(vault)
        documents = []
        for path in files:
            stat = path.stat()
            documents.append({
                "path": path.relative_to(vault).as_posix(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            })
        return {"documents": documents, "total": len(documents)}

    @router.get("/api/knowledge/documents")
    async def documents():
        try:
            return await asyncio.to_thread(list_documents)
        except OSError as exc:
            raise HTTPException(503, "无法读取笔记列表，请检查目录权限后刷新") from exc

    async def run():
        try:
            indexer = await get_indexer()
            count = await asyncio.to_thread(indexer.index_vault, vault_path)
            state.update(status="succeeded", chunks=count)
        except Exception as exc:
            logging.getLogger(__name__).warning("索引失败，错误类型=%s", type(exc).__name__)
            state.update(status="failed", error="建立索引失败，请检查向量服务、模型配置、笔记目录权限及 UTF-8/Markdown 格式后重试。")
        finally:
            state["finished_at"] = datetime.now(timezone.utc).isoformat()

    @router.get("/api/knowledge/index")
    async def status():
        return dict(state)

    @router.post("/api/knowledge/index", status_code=202)
    async def start(background_tasks: BackgroundTasks):
        # 检查和标记之间没有 await，同一进程内不会重复调度。
        if state["status"] != "running":
            state.update(status="running", chunks=None, error="", finished_at=None)
            background_tasks.add_task(run)
        return dict(state)

    return router
