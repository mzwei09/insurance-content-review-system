"""FAISS 向量库模块 - 使用 Dashscope text-embedding-v2 与 FAISS 存储监管条文"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_DIMENSION = 1536
DEFAULT_EMBEDDING_MODEL = "text-embedding-v2"
MAX_RETRIES = 3


def _get_embeddings(
    texts: list[str],
    model: str = DEFAULT_EMBEDDING_MODEL,
    api_key: Optional[str] = None,
) -> list[list[float]]:
    """
    调用 Dashscope TextEmbedding API 获取向量。
    失败时重试 3 次。
    """
    try:
        from dashscope import TextEmbedding
    except ImportError:
        raise ImportError("请安装 dashscope: pip install dashscope")

    key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not key or key == "your-api-key-here":
        raise ValueError(
            "请配置 DASHSCOPE_API_KEY：在 config.yaml 的 api.dashscope_api_key 或环境变量中设置"
        )

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = TextEmbedding.call(
                model=model,
                input=texts,
                api_key=key,
            )
            if resp.status_code == 200:
                return [item["embedding"] for item in resp.output["embeddings"]]
            last_error = RuntimeError(f"API 返回 {resp.status_code}: {getattr(resp, 'message', resp)}")
        except Exception as e:
            last_error = e
            logger.warning("Embedding API 第 %d 次调用失败: %s", attempt, e)

    raise last_error


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2 归一化，使 IndexFlatIP 内积等价于余弦相似度"""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    return vectors / norms


class VectorStore:
    """
    基于 FAISS 的向量存储，支持条文元数据。
    使用 IndexFlatIP（内积），向量需 L2 归一化。
    """

    def __init__(
        self,
        dimension: int = DEFAULT_DIMENSION,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        storage_path: Optional[str] = None,
        index_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        api_key: Optional[str] = None,
        use_ip: bool = True,
    ):
        if faiss is None:
            raise ImportError("请安装 faiss-cpu: pip install faiss-cpu")

        self.dimension = dimension
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.use_ip = use_ip

        # 兼容 index_path/metadata_path 与 storage_path 两种配置
        if index_path and metadata_path:
            self.index_path = Path(index_path)
            self.metadata_path = Path(metadata_path)
            self.storage_path = self.index_path.parent
        else:
            self.storage_path = Path(storage_path or "data/vectorstore")
            self.storage_path.mkdir(parents=True, exist_ok=True)
            self.index_path = self.storage_path / "faiss.index"
            self.metadata_path = self.storage_path / "metadata.json"

        self.index: Optional[faiss.Index] = None
        self.metadata: list[dict[str, Any]] = []

    def _create_index(self) -> "faiss.Index":
        if self.use_ip:
            return faiss.IndexFlatIP(self.dimension)
        return faiss.IndexFlatL2(self.dimension)

    def add_articles(
        self,
        articles: list[dict[str, Any]],
        batch_size: int = 10,
    ) -> tuple[int, int]:
        """
        将条文列表向量化并加入索引。
        articles: [{"article_id": "...", "content": "...", "document": "..."}, ...]

        Returns:
            (成功数, 失败数)
        """
        if not articles:
            return 0, 0

        success_count = 0
        fail_count = 0

        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            texts = []
            valid_indices = []

            for j, art in enumerate(batch):
                content = art.get("content", "").strip()
                if not content:
                    logger.warning("条文内容为空，跳过: %s", art.get("article_id"))
                    fail_count += 1
                    continue
                texts.append(content)
                valid_indices.append(j)

            if not texts:
                continue

            try:
                embeddings = _get_embeddings(
                    texts,
                    model=self.embedding_model,
                    api_key=self.api_key,
                )
            except Exception as e:
                logger.error("向量化失败: %s", e)
                fail_count += len(batch)
                continue

            vectors = np.array(embeddings, dtype=np.float32)
            if self.use_ip:
                vectors = _normalize_vectors(vectors)

            if self.index is None:
                self.index = self._create_index()

            self.index.add(vectors)

            for j in valid_indices:
                art = batch[j]
                content = art.get("content", "")
                meta = {
                    "article_id": art.get("article_id", ""),
                    "document": art.get("document", ""),
                    "content": content[:500],
                    "article_text": content,  # 完整内容供检索返回
                    "text": content,  # 兼容 retriever
                }
                self.metadata.append(meta)
                success_count += 1

        return success_count, fail_count

    def save(self) -> None:
        """持久化索引和元数据"""
        if self.index is None:
            logger.warning("索引为空，跳过保存")
            return

        self.storage_path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logger.info("向量库已保存至 %s", self.storage_path)

    def load(self) -> bool:
        """从磁盘加载索引和元数据"""
        if not self.index_path.exists():
            logger.warning("索引文件不存在: %s", self.index_path)
            return False

        try:
            self.index = faiss.read_index(str(self.index_path))
            if self.metadata_path.exists():
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            logger.info("向量库已加载，共 %d 条", len(self.metadata))
            return True
        except Exception as e:
            logger.error("加载向量库失败: %s", e)
            return False

    def search(
        self,
        query: str,
        top_k: int = 5,
        api_key: Optional[str] = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """
        检索最相似的条文。

        Args:
            query: 查询文本
            top_k: 返回数量
            api_key: 百炼 API 密钥，若提供则优先使用（用户个人密钥）

        Returns:
            [(metadata, score), ...]，score 为相似度（0~1 或距离）
        """
        if self.index is None:
            return []

        key = api_key or self.api_key
        try:
            query_embeddings = _get_embeddings(
                [query],
                model=self.embedding_model,
                api_key=key,
            )
        except Exception as e:
            logger.error("查询向量化失败: %s", e)
            return []

        vectors = np.array(query_embeddings, dtype=np.float32)
        if self.use_ip:
            vectors = _normalize_vectors(vectors)

        k = min(top_k, self.index.ntotal) if self.index.ntotal > 0 else 0
        if k <= 0:
            return []

        scores, indices = self.index.search(vectors, k)
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            meta = self.metadata[idx]
            raw_score = float(scores[0][i])
            if self.use_ip:
                # 内积已归一化，范围约 [-1, 1]，转为 [0, 1]
                score = (raw_score + 1) / 2
            else:
                score = 1.0 / (1.0 + raw_score)
            results.append((meta, score))

        return results
