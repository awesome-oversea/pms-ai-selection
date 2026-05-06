"""
BGE Embedding向量编码服务
==========================

提供文本向量化能力(D10-T032):
    - BAAI/bge-large-zh-v1.5 模型加载
    - 批量文本编码(支持长文本截断)
    - 向量归一化(L2 normalization)
    - REST API封装(目标5000 QPS)
    - 模型缓存与热更新

使用方式:
    from src.services.embedding import EmbeddingService

    svc = EmbeddingService()
    vectors = svc.encode(["产品描述文本", "另一个文本"])
"""

from typing import Optional

import numpy as np

from src.config.settings import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    BGE Embedding服务。

    封装sentence_transformers模型，提供:
        - 单条/批量文本编码
        - 自动归一化(cosine similarity优化)
        - 长度截断(避免OOM)

    Attributes:
        model_name: 模型标识符(如 BAAI/bge-large-zh-v1.5)
        max_length: 最大token序列长度
        dimension: 输出向量维度(1024 for bge-large-zh)
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str = "cpu",
    ):
        """
        初始化Embedding服务。

        Args:
            model_name: 模型名称(默认从配置读取)
            device: 推理设备(cpu/cuda/cuda:0)
        """
        settings = get_settings()
        self.model_name = model_name or settings.llm.embedding_model
        self.device = device
        self._model = None
        self._dimension: int | None = None
        self._provider_mode = "local-unknown"

    @property
    def model(self):
        """懒加载模型(首次调用时初始化)。"""
        if self._model is None:
            self._load_model()
        return self._model

    def _load_model(self):
        """加载sentence_transformers模型。"""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"🔄 加载Embedding模型: {self.model_name}")
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
            self._dimension = self._model.get_sentence_embedding_dimension()
            self._provider_mode = "local-real"
            logger.info(f"✅ Embedding模型已加载 (dim={self._dimension})")
        except ImportError:
            logger.warning("⚠️ sentence_transformers未安装，使用模拟模式")
            self._model = None
            self._dimension = 1024
            self._provider_mode = "local-mock"
        except Exception as exc:
            logger.warning(f"⚠️ Embedding模型加载失败，使用模拟模式: {exc}")
            self._model = None
            self._dimension = 1024
            self._provider_mode = "local-mock"

    @property
    def dimension(self) -> int:
        """获取输出向量维度。"""
        if self._dimension is None:
            return 1024
        return self._dimension

    @property
    def provider_mode(self) -> str:
        """返回当前 Embedding 运行模式。"""
        if self._provider_mode == "local-unknown":
            self._load_model()
        return self._provider_mode

    def encode(
        self,
        texts: list[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        max_length: int = 512,
    ) -> list[list[float]]:
        """
        编码文本列表为向量。

        Args:
            texts: 待编码文本列表
            batch_size: 批处理大小(影响显存占用)
            normalize_embeddings: 是否L2归一化(推荐True用于cosine相似度)
            max_length: 最大序列长度(超长文本截断)

        Returns:
            list[list[float]]: 向量列表，每个向量长度=dimension

        Raises:
            ValueError: texts为空列表时抛出
        """
        if not texts:
            raise ValueError("texts不能为空列表")

        truncated = [t[:max_length * 3] for t in texts]

        if self._model is not None:
            embeddings = self.model.encode(
                truncated,
                batch_size=batch_size,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False,
            )
            return embeddings.tolist()

        return self._mock_encode(truncated)

    def encode_single(
        self,
        text: str,
        normalize_embeddings: bool = True,
    ) -> list[float]:
        """
        编码单条文本。

        Args:
            text: 待编码文本
            normalize_embeddings: 是否归一化

        Returns:
            list[float]: 向量
        """
        result = self.encode([text], normalize_embeddings=normalize_embeddings)
        return result[0]

    def _mock_encode(self, texts: list[str]) -> list[list[float]]:
        """
        模拟编码(无模型时的降级方案)。

        使用文本hash生成伪随机向量，
        仅用于开发和测试环境。
        """
        import hashlib

        self._provider_mode = "local-mock"
        dim = self._dimension or 1024
        results = []

        for text in texts:
            hash_bytes = hashlib.sha256(text.encode()).digest()
            base_vector = np.frombuffer(hash_bytes, dtype=np.uint8).astype(np.float32) / 255.0

            if len(base_vector) < dim:
                repeats = (dim // len(base_vector)) + 1
                base_vector = np.tile(base_vector, repeats)[:dim]
            else:
                base_vector = base_vector[:dim]

            norm = np.linalg.norm(base_vector)
            if norm > 0:
                base_vector = base_vector / norm

            results.append(base_vector.tolist())

        return results


class EmbeddingProvider:
    """
    Embedding提供者抽象层。

    支持多种后端切换:
        - local: 本地sentence_transformers
        - triton: Triton推理服务器
        - openai: OpenAI兼容API(如vLLM embedding endpoint)
        """

    _instance: Optional["EmbeddingProvider"] = None

    def __init__(self, backend: str = "local"):
        self.backend = backend
        self._service: EmbeddingService | None = None

    @classmethod
    def get_instance(cls, backend: str = "local") -> "EmbeddingProvider":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls(backend=backend)
        return cls._instance

    @property
    def service(self) -> EmbeddingService:
        """获取底层EmbeddingService实例。"""
        if self._service is None:
            self._service = EmbeddingService()
        return self._service

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """异步接口: 编码文本列表。"""
        return self.service.encode(texts)

    async def embed_query(self, query: str) -> list[float]:
        """异步接口: 编码查询文本(用于检索)。"""
        return self.service.encode_single(query)

    @property
    def provider_mode(self) -> str:
        """公开当前 provider 运行模式。"""
        return self.service.provider_mode


def get_embedding_service() -> EmbeddingService:
    """获取全局EmbeddingService单例。"""
    return EmbeddingService()


def get_embedding_provider() -> EmbeddingProvider:
    """获取全局EmbeddingProvider单例。"""
    return EmbeddingProvider.get_instance()
