"""检索模块 - 封装向量库检索功能，返回相关监管条文"""

from typing import Any, Optional, Protocol

# 向量库接口：由 src/vectorstore.py 实现
# 需实现 search(query: str, top_k: int) -> list[tuple[dict, float]]
# 返回的 metadata dict 应包含: text 或 article_text, 可选 article_id 或 id


class VectorStoreProtocol(Protocol):
    """向量库协议 - 定义检索接口"""

    def search(self, query: str, top_k: int = 5) -> list[tuple[dict, float]]:
        """检索与 query 最相似的文档，返回 (metadata, score) 列表"""
        ...


class Retriever:
    """监管条文检索器 - 封装向量库检索，过滤低相关度结果"""

    def __init__(
        self,
        vectorstore: VectorStoreProtocol,
        top_k: int = 5,
        score_threshold: float = 0.6,
    ):
        """
        Args:
            vectorstore: 向量库实例，需实现 search(query, top_k) 方法
            top_k: 返回的最相关条文数量
            score_threshold: 相似度阈值，低于此值的结果将被过滤
        """
        self.vectorstore = vectorstore
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, query: str, top_k: Optional[int] = None, api_key: Optional[str] = None) -> list[dict]:
        """
        检索与查询相关的监管条文。

        Args:
            query: 检索查询文本
            top_k: 返回数量，默认使用初始化时的 top_k
            api_key: 百炼 API 密钥，用于 embedding 查询（用户个人密钥）

        Returns:
            相关条文列表，每项包含:
            - article_id: 条文编号
            - article_text: 条文内容
            - relevance_score: 相似度 (0-1)
        """
        k = top_k if top_k is not None else self.top_k
        results = self.vectorstore.search(query, top_k=k, api_key=api_key)

        articles = []
        for i, (meta, score) in enumerate(results):
            if score < self.score_threshold:
                continue
            article_id = meta.get("article_id") or meta.get("id") or f"doc_{i+1}"
            article_text = meta.get("article_text") or meta.get("text") or ""
            articles.append({
                "article_id": str(article_id),
                "article_text": article_text,
                "relevance_score": round(float(score), 4),
            })
        return articles
