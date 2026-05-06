"""
BGE Rerank重排序服务
===================

提供查询-文档相关性重排序能力(D11-T033):
    - bge-reranker-base 模型加载
    - 查询-文档对评分
    - Top-K结果筛选
    - 延迟目标<100ms

使用方式:
    from src.services.rerank import RerankService

    svc = RerankService()
    results = svc.rerank(query="无线耳机", docs=["产品A描述", "产品B描述"], top_k=5)
"""


from src.config.settings import get_settings
from src.core.logging import get_logger
from src.infrastructure.triton_client import TritonClient, TritonClientError

logger = get_logger(__name__)


class RerankService:
    """
    BGE Reranker重排序服务。

    基于Cross-Encoder架构，对query-doc对进行精细相关性评分，
    用于向量检索后的精排阶段(D11-T033)。

    Attributes:
        model_name: Reranker模型名称
        top_k: 默认返回Top-K数量
    """

    def __init__(
        self,
        model_name: str | None = None,
        top_k: int = 10,
        device: str = "cpu",
        prefer_triton: bool = True,
    ):
        settings = get_settings()
        self.model_name = model_name or settings.llm.rerank_model
        self.top_k = top_k
        self.device = device
        self._model = None
        self._triton_enabled = settings.llm.triton_enabled and prefer_triton
        self._triton_client = TritonClient(
            base_url=settings.llm.triton_endpoint,
            timeout_seconds=settings.llm.triton_timeout_seconds,
        ) if self._triton_enabled else None

    @property
    def model(self):
        """懒加载Reranker模型。"""
        if self._model is None:
            self._load_model()
        return self._model

    def _load_model(self):
        """加载CrossEncoder模型。"""
        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"🔄 加载Reranker模型: {self.model_name}")
            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("✅ Reranker模型已加载")
        except ImportError:
            logger.warning("⚠️ sentence_transformers未安装，使用模拟模式")
            self._model = None
        except Exception as exc:
            logger.warning(f"⚠️ Reranker模型加载失败，使用模拟模式: {type(exc).__name__}")
            self._model = None

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        return_scores: bool = True,
    ) -> list[dict]:
        """
        对文档列表按与查询的相关性重排序。

        Args:
            query: 用户查询文本
            documents: 候选文档文本列表
            top_k: 返回前K个结果(None=全部)
            return_scores: 是否返回相关性得分

        Returns:
            list[dict]: 排序后结果 [{"index", "score", "document"}, ...]
                按score降序排列

        Example:
            >>> svc.rerank("蓝牙耳机", ["AirPods Pro", "充电线", "Sony WH-1000XM5"], top_k=2)
            [{"index": 2, "score": 0.92, "document": "Sony WH-1000XM5"},
             {"index": 0, "score": 0.85, "document": "AirPods Pro"}]
        """
        if not documents:
            return []

        k = top_k or self.top_k
        k = min(k, len(documents))

        if self._triton_client is not None:
            try:
                results = self._triton_client.rerank_sync(query=query, documents=documents, top_k=k)
                if results:
                    return [
                        {
                            "index": int(item["index"]),
                            "score": float(item["score"]),
                            "document": documents[int(item["index"])] if "document" not in item else item["document"],
                        }
                        for item in results
                    ]
            except TritonClientError as e:
                logger.warning(f"⚠️ Triton rerank失败，回退本地/模拟模式: {e.error_code}")

        model = self.model
        if model is not None:
            pairs = [[query, doc] for doc in documents]
            scores = model.predict(pairs)

            scored = sorted(
                enumerate(scores),
                key=lambda x: x[1],
                reverse=True,
            )[:k]

            return [
                {
                    "index": idx,
                    "score": float(score),
                    "document": documents[idx],
                }
                for idx, score in scored
            ]

        return self._mock_rerank(query, documents, k)

    def score_documents_locally(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[dict]:
        """本地兼容评分逻辑，用于 Triton 不可用时的正式降级链路。"""
        import re

        def _terms(text: str) -> set[str]:
            normalized = text.lower()
            words = set(re.findall(r"[a-z0-9]+", normalized))
            chars = set(re.findall(r"[\u4e00-\u9fff]", normalized))
            bigrams = {normalized[index:index + 2] for index in range(max(len(normalized) - 1, 0)) if re.match(r"[\u4e00-\u9fff]{2}", normalized[index:index + 2])}
            return words | chars | bigrams

        query_terms = _terms(query)
        scored = []

        for idx, doc in enumerate(documents):
            doc_terms = _terms(doc)
            overlap = len(query_terms & doc_terms)
            score = overlap / max(len(query_terms), 1)
            scored.append({"index": idx, "score": score, "document": doc})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _mock_rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[dict]:
        """
        模拟重排序(无模型时的降级方案)。

        使用简单的关键词匹配度作为伪评分。
        """
        return self.score_documents_locally(query, documents, top_k)

    def score_pair(self, query: str, document: str) -> float:
        """
        计算单个query-doc对的相关性得分。

        Args:
            query: 查询文本
            document: 文档文本

        Returns:
            float: 相关性得分(通常0-1范围)
        """
        result = self.rerank(query, [document], top_k=1)
        return result[0]["score"] if result else 0.0


def get_rerank_service() -> RerankService:
    """获取全局RerankService单例。"""
    return RerankService()
