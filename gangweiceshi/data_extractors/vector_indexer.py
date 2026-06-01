"""
向量索引器 — 遍历 Obsidian Vault .md 文件 → Markdown 结构感知分块 → Embedding → Qdrant
同时提供知识检索方法，供 main.py 的 /api/search_knowledge 调用
"""

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from langchain_text_splitters import MarkdownHeaderTextSplitter
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = logging.getLogger(__name__)

# ── Markdown 结构感知分块器（按标题层级切分） ──
HEADERS_TO_SPLIT = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

# 最小分块长度（字符数），过滤过短的无效片段
MIN_CHUNK_LENGTH = 50


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """从 Markdown 文本中解析 YAML frontmatter

    Returns:
        (metadata_dict, body_text) — metadata 包含 source/date/tags 等字段
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    frontmatter = parts[1]
    body = parts[2]

    metadata: dict = {}
    for line in frontmatter.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


class VectorIndexer:
    """Obsidian Vault ↔ Qdrant 向量知识库桥接器

    职责：
      1. index_vault()  — 遍历 .md 文件，分块 → 向量化 → 写入 Qdrant
      2. search_knowledge() — 查询向量化 → Qdrant 相似度检索 → 返回文本块
    """

    def __init__(
        self,
        qdrant_url: str = "http://vector_db:6333",
        api_key: str = "",
        base_url: str = "https://api.siliconflow.cn/v1",
        embedding_model: str = "BAAI/bge-m3",
        collection_name: str = "ecommerce_knowledge",
        vector_size: int = 1024,
    ):
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.embedding_model = embedding_model

        self.qdrant = QdrantClient(url=qdrant_url)
        self.openai = OpenAI(api_key=api_key, base_url=base_url)

        self.splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=HEADERS_TO_SPLIT,
            strip_headers=False,
        )

        self._ensure_collection()

    # ------------------------------------------------------------------
    #  集合管理
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        """确保 Qdrant 集合存在，不存在则创建"""
        collections = self.qdrant.get_collections()
        names = {c.name for c in collections.collections}

        if self.collection_name not in names:
            logger.info(
                f"创建 Qdrant 集合 '{self.collection_name}' "
                f"(维度={self.vector_size}, 距离=Cosine)"
            )
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )
        else:
            logger.info(f"集合 '{self.collection_name}' 已存在")

    def reset_collection(self) -> None:
        """删除并重建集合（全量重索引用）"""
        logger.warning(f"删除集合 '{self.collection_name}'...")
        self.qdrant.delete_collection(self.collection_name)
        self._ensure_collection()

    # ------------------------------------------------------------------
    #  Embedding
    # ------------------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容 Embedding API，批量向量化文本"""
        if not texts:
            return []

        response = self.openai.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        # 按输入顺序返回向量
        embeddings = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in embeddings]

    def _embed_single(self, text: str) -> list[float]:
        """单条文本向量化"""
        return self._embed([text])[0]

    # ------------------------------------------------------------------
    #  索引构建
    # ------------------------------------------------------------------

    def index_vault(self, vault_path: str = "/obsidian") -> int:
        """遍历 Vault 所有 .md 文件，分块 → 向量化 → 写入 Qdrant

        Args:
            vault_path: Obsidian Vault 目录路径

        Returns:
            成功索引的总 chunk 数
        """
        vault = Path(vault_path)
        if not vault.is_dir():
            logger.error(f"Vault 目录不存在: {vault_path}")
            return 0

        md_files = sorted(vault.glob("*.md"))
        if not md_files:
            logger.warning(f"Vault 中没有 .md 文件: {vault_path}")
            return 0

        logger.info(f"开始索引 {len(md_files)} 个 .md 文件...")

        total_chunks = 0
        all_points: list[PointStruct] = []

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"读取失败 {md_file.name}: {e}")
                continue

            if not content.strip():
                continue

            # 解析 frontmatter，分离元数据和正文
            metadata, body = _parse_frontmatter(content)
            source_url = metadata.get("source", "")

            # Markdown 结构感知分块
            try:
                docs = self.splitter.split_text(body)
            except Exception as e:
                logger.warning(f"分块失败 {md_file.name}: {e}")
                continue

            file_chunks = 0
            for i, doc in enumerate(docs):
                chunk_text = doc.page_content.strip()
                if len(chunk_text) < MIN_CHUNK_LENGTH:
                    continue

                # 生成确定性 UUID（文件名 + chunk 序号 → 幂等覆盖）
                point_id = str(uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"{md_file.name}:{i}",
                ))

                # 构建 payload（承载原文 + 溯源信息）
                payload = {
                    "source_file": md_file.name,
                    "source_url": source_url,
                    "chunk_index": i,
                    "text": chunk_text,
                }
                # 合并 Markdown 标题层级元数据
                payload.update(doc.metadata)

                all_points.append(PointStruct(
                    id=point_id,
                    vector=[],  # 临时占位，批量 embed 后填充
                    payload=payload,
                ))
                file_chunks += 1

            logger.info(f"  {md_file.name}: {file_chunks} 个有效 chunk")
            total_chunks += file_chunks

        if not all_points:
            logger.warning("没有可索引的有效 chunk")
            return 0

        # ── 批量向量化 ──
        batch_size = 20
        for batch_start in range(0, len(all_points), batch_size):
            batch = all_points[batch_start:batch_start + batch_size]
            texts = [p.payload["text"] for p in batch]  # type: ignore[index]

            try:
                vectors = self._embed(texts)
                for point, vector in zip(batch, vectors):
                    point.vector = vector  # type: ignore[assignment]
            except Exception as e:
                logger.error(
                    f"Embedding 批次 [{batch_start}:{batch_start+batch_size}] 失败: {e}"
                )
                # 跳过当前批次，继续下一批
                continue

        # 过滤掉向量填充失败的点
        valid_points = [p for p in all_points if p.vector]
        if not valid_points:
            logger.error("所有 embedding 均失败，无数据写入 Qdrant")
            return 0

        # ── 批量写入 Qdrant ──
        logger.info(f"写入 {len(valid_points)} 条向量到 Qdrant...")
        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=valid_points,
        )

        logger.info(f"索引完成: {total_chunks} chunks / {len(md_files)} 文件")
        return total_chunks

    # ------------------------------------------------------------------
    #  知识检索
    # ------------------------------------------------------------------

    def search_knowledge(
        self, query: str, limit: int = 3
    ) -> list[dict]:
        """语义检索：query 向量化 → Qdrant 相似度搜索 → 返回 Top-K 文本块

        Args:
            query: 用户查询字符串（中文或英文）
            limit: 返回的最大结果数

        Returns:
            [{text, source_file, source_url, score, h1, h2, h3}, ...]
        """
        query_vector = self._embed_single(query)

        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
        )

        output = []
        for r in response.points:
            p = r.payload or {}
            output.append({
                "text": p.get("text", ""),
                "source_file": p.get("source_file", ""),
                "source_url": p.get("source_url", ""),
                "score": round(r.score, 4),
                "h1": p.get("h1", ""),
                "h2": p.get("h2", ""),
                "h3": p.get("h3", ""),
            })

        return output


# ── CLI 入口：直接运行此脚本即可执行全量索引 ──
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    indexer = VectorIndexer(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("AI_API_KEY", ""),
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )

    vault = os.getenv("VAULT_PATH", "/obsidian")
    count = indexer.index_vault(vault_path=vault)
    print(f"\n索引完成，共写入 {count} 条向量。")
