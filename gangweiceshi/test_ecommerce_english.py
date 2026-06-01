"""
测试脚本 — 异步发送英文跨境电商 AI 技术文本到 python_api
验证「逐句对齐精读」模块的端到端效果
"""

import asyncio
import httpx

API_URL = "http://localhost:8000/api/process_content"

# 约 600 词高密度英文测试数据，聚焦 RAG + LangGraph + 向量数据库在跨境电商中的落地
PAYLOAD = {
    "title": "RAG-LangGraph Multi-Agent Architecture for Cross-Border E-Commerce Intelligence",
    "url": "https://example.com/rag-langgraph-ecommerce-2026",
    "raw_text": (
        "The rapid evolution of artificial intelligence has ushered in a new paradigm "
        "for cross-border e-commerce operations, where Retrieval-Augmented Generation (RAG) "
        "combined with LangGraph-based multi-agent orchestration is fundamentally transforming "
        "how sellers approach product selection, listing optimization, and advertising automation. "

        "At the core of this transformation lies the vector database, which serves as the "
        "long-term memory backbone for RAG systems. By encoding product catalogs, customer "
        "reviews, and market trend reports into high-dimensional embedding vectors stored in "
        "specialized databases such as Milvus, Pinecone, or Weaviate, e-commerce platforms "
        "can perform semantic similarity searches that go far beyond traditional keyword matching. "
        "When a seller queries 'emerging home fitness trends among European millennials,' the "
        "vector database retrieves semantically relevant documents even when exact keyword "
        "overlap is minimal, enabling the RAG pipeline to ground its generation in factual, "
        "contextually appropriate market intelligence rather than hallucinated data. "

        "LangGraph elevates this architecture by introducing stateful, graph-based multi-agent "
        "workflows. Unlike simple linear RAG chains that retrieve documents and generate text "
        "in a single pass, LangGraph enables the construction of cyclic computational graphs "
        "where specialized AI agents—each responsible for a distinct function such as market "
        "research, competitor analysis, regulatory compliance checking, and content localization"
        "—can collaborate, delegate tasks, and iteratively refine outputs. "

        "Consider a concrete cross-border e-commerce use case: an American seller aiming to "
        "expand into the Japanese market. The LangGraph orchestration layer spawns a Market "
        "Research Agent that queries vector databases containing historical sales data and "
        "social media sentiment from Japanese consumers. Simultaneously, a Compliance Agent "
        "cross-references the proposed product against Japan's Pharmaceutical and Medical "
        "Device Act (PMD Act) and Consumer Product Safety Act databases. The insights from "
        "both agents are then routed to a Listing Optimization Agent, which employs a "
        "fine-tuned large language model to generate Japanese-language product titles, bullet "
        "points, and A+ content that not only comply with local regulations but also resonate "
        "with Japanese consumer psychology—incorporating culturally appropriate honorific "
        "language and addressing specific pain points identified through semantic analysis "
        "of Rakuten and Amazon Japan reviews. "

        "In the advertising domain, the multi-agent system achieves real-time bid optimization "
        "through a feedback loop architecture. A Bidding Strategy Agent monitors cost-per-click "
        "and conversion rate data streamed from Amazon Advertising API, while a Creative "
        "Optimization Agent continuously A/B tests ad copy and hero images. When the vector "
        "database detects an emerging consumer trend—for instance, a surge in semantic "
        "embeddings related to 'sustainable packaging'—the system autonomously adjusts "
        "bidding weights toward relevant long-tail keywords and triggers the generation of "
        "new ad creatives highlighting eco-friendly product attributes. "

        "The technical implementation of such a system requires careful consideration of "
        "embedding model selection and retrieval strategies. While OpenAI's text-embedding-3-large "
        "offers strong out-of-the-box performance for English content, multilingual e-commerce "
        "scenarios often benefit from fine-tuned bilingual embedding models such as BGE-M3, "
        "which supports over 100 languages and achieves superior cross-lingual retrieval "
        "accuracy. The chunking strategy is equally critical: product descriptions benefit "
        "from smaller chunk sizes of 256-512 tokens with high overlap to preserve attribute-level "
        "semantic fidelity, whereas market trend reports can be chunked at 1024-2048 tokens "
        "to capture broader thematic patterns. Hybrid search combining dense vector retrieval "
        "with sparse BM25 keyword matching has been empirically shown to improve recall by "
        "18-23% in cross-border e-commerce RAG pipelines compared to dense-only approaches. "

        "Looking ahead, the convergence of RAG, LangGraph, and vector database technologies "
        "is poised to democratize access to sophisticated cross-border e-commerce intelligence. "
        "Small and medium-sized sellers who previously lacked the resources to conduct "
        "multilingual market research, navigate complex international compliance landscapes, "
        "and optimize advertising campaigns across disparate platforms will increasingly "
        "rely on these AI-native workflows to compete with enterprise-scale incumbents on "
        "a more level playing field."
    ),
}


async def main():
    print(f"向 {API_URL} 发送英文测试数据...")
    print(f"标题: {PAYLOAD['title']}")
    print(f"正文字数: {len(PAYLOAD['raw_text'].split())} 词 / {len(PAYLOAD['raw_text'])} 字符")
    print()

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(API_URL, json=PAYLOAD)
            print(f"HTTP {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                print(f"状态:    {data.get('status')}")
                print(f"输出文件: {data.get('filepath')}")
                print(f"摘要:    {data.get('summary')}")
                print(f"核心观点: {data.get('key_points')}")
                print(f"标签:    {data.get('tags')}")
                print()
                print("─" * 60)
                print(f"生成 .md 文件: {data.get('filepath')}")
                print("请在 Obsidian 中打开查看「核心长难句精读」章节的排版效果。")
            else:
                print("响应内容:", resp.text[:500])

        except httpx.ConnectError:
            print("连接失败 — 请确认 python_api 容器是否正在运行 (docker compose up -d)")
        except Exception as e:
            print(f"请求异常: {e}")


if __name__ == "__main__":
    asyncio.run(main())
