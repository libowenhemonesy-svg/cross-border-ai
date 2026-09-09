"""独立路由工厂，便于在不启动采集服务的情况下验证问答 API。"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rag_graph import KnowledgeError


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


class AskResponse(BaseModel):
    status: Literal["answered", "insufficient_context", "no_data"]
    answer: str
    citation_ids: list[int]
    sources: list[dict]


def create_rag_router(graph) -> APIRouter:
    router = APIRouter()

    @router.post("/api/ask_knowledge", response_model=AskResponse)
    async def ask_knowledge(req: AskRequest):
        try:
            result = await graph.ainvoke({"question": req.question})
        except KnowledgeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return AskResponse(**{key: result[key] for key in AskResponse.model_fields})

    return router
