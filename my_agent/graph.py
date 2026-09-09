"""LangGraph Studio 入口，复用后端问答图并通过 HTTP 检索已有知识库。"""
import os

import httpx

from gangweiceshi.data_extractors.rag_graph import KnowledgeError, build_graph


async def retrieve_knowledge(question: str) -> list[dict]:
    base_url = os.getenv("KNOWLEDGE_API_URL", "http://localhost:8000").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/api/search_knowledge",
                json={"query": question, "limit": 4},
            )
            response.raise_for_status()
            results = response.json()["results"]
            if not isinstance(results, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("text"), str)
                for item in results
            ):
                raise ValueError("Invalid search results")
            return results
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise KnowledgeError("知识检索调用失败，请检查后端和向量索引", 503) from exc


app = build_graph(retrieve_knowledge)
