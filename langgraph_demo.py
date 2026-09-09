"""真实知识库问答：python langgraph_demo.py "你的问题"。"""
import argparse
import asyncio
import json

from my_agent.graph import app
from gangweiceshi.data_extractors.rag_graph import KnowledgeError


async def main():
    parser = argparse.ArgumentParser(description="LangGraph 知识库问答")
    parser.add_argument("question")
    args = parser.parse_args()
    try:
        result = await app.ainvoke({"question": args.question})
    except KnowledgeError as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
