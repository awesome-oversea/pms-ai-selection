# RAG框架搭建方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D13-D15 RAG框架搭建
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. RAG框架架构](#2-rag框架架构)
- [3. 文档切片策略](#3-文档切片策略)
- [4. 混合检索实现](#4-混合检索实现)
- [5. Rerank精排集成](#5-rerank精排集成)
- [6. Prompt模板设计](#6-prompt模板设计)

---

## 1. 概述

### 1.1 设计目标

构建企业级RAG（检索增强生成）框架，实现文档处理、向量检索、混合检索和智能问答能力。

### 1.2 核心能力

| 能力 | 说明 | 目标指标 |
|------|------|---------|
| 文档处理 | 多格式解析与切片 | 支持10+格式 |
| 向量检索 | HNSW索引检索 | 延迟<50ms |
| 混合检索 | 向量+关键词融合 | MRR@10>0.7 |
| 精排重排 | Rerank模型 | 准确率提升20% |

---

## 2. RAG框架架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG框架架构                                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    文档处理层                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ 文档加载  │ │ 文档解析  │ │ 文档切片  │ │ 元数据提取│   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    向量化层                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Embedding│ │ 批量处理  │ │ 向量存储  │               │   │
│  │  │ 服务     │ │          │ │ (Qdrant) │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    检索层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ 向量检索  │ │ 关键词检索│ │ 混合融合  │ │ Rerank   │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    生成层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Prompt   │ │ LLM调用  │ │ 结果后处理│               │   │
│  │  │ 模板渲染 │ │          │ │          │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Document(BaseModel):
    doc_id: str
    content: str
    metadata: Dict[str, Any] = {}
    embedding: Optional[List[float]] = None
    created_at: datetime = datetime.now()

class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    metadata: Dict[str, Any] = {}
    embedding: Optional[List[float]] = None
    chunk_index: int = 0

class RetrievalResult(BaseModel):
    chunks: List[Chunk]
    scores: List[float]
    query: str
    total: int

class RAGResponse(BaseModel):
    answer: str
    sources: List[Chunk]
    confidence: float
    metadata: Dict[str, Any] = {}
```

---

## 3. 文档切片策略

### 3.1 切片器接口

```python
from abc import ABC, abstractmethod
from typing import List

class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: Document) -> List[Chunk]:
        pass

class ChunkerFactory:
    _chunkers = {}
    
    @classmethod
    def register(cls, name: str, chunker_class: type):
        cls._chunkers[name] = chunker_class
    
    @classmethod
    def create(cls, name: str, **kwargs) -> Chunker:
        return cls._chunkers[name](**kwargs)
```

### 3.2 递归字符切片器

```python
import re
from typing import List, Optional

class RecursiveCharacterChunker(Chunker):
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", "！", "？", " ", ""]
    
    def chunk(self, document: Document) -> List[Chunk]:
        chunks = []
        text = document.content
        
        chunks_text = self._split_text(text)
        
        for i, chunk_text in enumerate(chunks_text):
            chunk = Chunk(
                chunk_id=f"{document.doc_id}_chunk_{i}",
                doc_id=document.doc_id,
                content=chunk_text,
                metadata=document.metadata.copy(),
                chunk_index=i
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_text(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]
        
        for separator in self.separators:
            if separator in text:
                splits = text.split(separator)
                return self._merge_splits(splits, separator)
        
        return self._split_by_characters(text)
    
    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        merged = []
        current = ""
        
        for split in splits:
            if len(current) + len(split) + len(separator) <= self.chunk_size:
                current += separator + split if current else split
            else:
                if current:
                    merged.append(current)
                current = split
        
        if current:
            merged.append(current)
        
        return merged
    
    def _split_by_characters(self, text: str) -> List[str]:
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i:i + self.chunk_size]
            chunks.append(chunk)
        return chunks
```

### 3.3 语义边界切片器

```python
class SemanticChunker(Chunker):
    def __init__(
        self,
        embedding_service,
        similarity_threshold: float = 0.7,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000
    ):
        self.embedding_service = embedding_service
        self.similarity_threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
    
    async def chunk(self, document: Document) -> List[Chunk]:
        sentences = self._split_sentences(document.content)
        
        embeddings = await self.embedding_service.embed_batch(sentences)
        
        chunks = []
        current_chunk = [sentences[0]]
        current_embedding = embeddings[0]
        
        for i in range(1, len(sentences)):
            similarity = self._cosine_similarity(
                current_embedding,
                embeddings[i]
            )
            
            current_length = sum(len(s) for s in current_chunk)
            
            if similarity < self.similarity_threshold or current_length >= self.max_chunk_size:
                if current_length >= self.min_chunk_size:
                    chunks.append(self._create_chunk(
                        document,
                        current_chunk,
                        len(chunks)
                    ))
                    current_chunk = [sentences[i]]
                    current_embedding = embeddings[i]
                else:
                    current_chunk.append(sentences[i])
                    current_embedding = self._average_embedding(
                        [current_embedding, embeddings[i]]
                    )
            else:
                current_chunk.append(sentences[i])
                current_embedding = self._average_embedding(
                    [current_embedding, embeddings[i]]
                )
        
        if current_chunk:
            chunks.append(self._create_chunk(document, current_chunk, len(chunks)))
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        pattern = r'(?<=[。！？\n])'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        import numpy as np
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def _average_embedding(self, embeddings: List[List[float]]) -> List[float]:
        import numpy as np
        return np.mean(embeddings, axis=0).tolist()
    
    def _create_chunk(self, document: Document, sentences: List[str], index: int) -> Chunk:
        return Chunk(
            chunk_id=f"{document.doc_id}_chunk_{index}",
            doc_id=document.doc_id,
            content="".join(sentences),
            metadata=document.metadata.copy(),
            chunk_index=index
        )
```

---

## 4. 混合检索实现

### 4.1 检索器接口

```python
from abc import ABC, abstractmethod

class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict = None
    ) -> RetrievalResult:
        pass
```

### 4.2 向量检索器

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

class VectorRetriever(Retriever):
    def __init__(
        self,
        qdrant_client: QdrantClient,
        embedding_service,
        collection_name: str = "product_knowledge"
    ):
        self.client = qdrant_client
        self.embedding_service = embedding_service
        self.collection_name = collection_name
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict = None
    ) -> RetrievalResult:
        query_embedding = await self.embedding_service.embed(query)
        
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=value)
                    )
                )
            qdrant_filter = Filter(must=conditions)
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qdrant_filter
        )
        
        chunks = []
        scores = []
        
        for result in results:
            chunk = Chunk(
                chunk_id=str(result.id),
                doc_id=result.payload.get("doc_id", ""),
                content=result.payload.get("content", ""),
                metadata=result.payload.get("metadata", {})
            )
            chunks.append(chunk)
            scores.append(result.score)
        
        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            query=query,
            total=len(chunks)
        )
```

### 4.3 关键词检索器

```python
from elasticsearch import AsyncElasticsearch

class KeywordRetriever(Retriever):
    def __init__(
        self,
        es_client: AsyncElasticsearch,
        index_name: str = "product_knowledge"
    ):
        self.client = es_client
        self.index_name = index_name
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict = None
    ) -> RetrievalResult:
        must = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["content^2", "metadata.title"],
                    "type": "best_fields"
                }
            }
        ]
        
        if filters:
            for key, value in filters.items():
                must.append({
                    "term": {f"metadata.{key}": value}
                })
        
        response = await self.client.search(
            index=self.index_name,
            body={
                "query": {
                    "bool": {
                        "must": must
                    }
                },
                "size": top_k
            }
        )
        
        chunks = []
        scores = []
        
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            chunk = Chunk(
                chunk_id=hit["_id"],
                doc_id=source.get("doc_id", ""),
                content=source.get("content", ""),
                metadata=source.get("metadata", {})
            )
            chunks.append(chunk)
            scores.append(hit["_score"])
        
        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            query=query,
            total=len(chunks)
        )
```

### 4.4 RRF融合检索器

```python
class HybridRetriever(Retriever):
    def __init__(
        self,
        vector_retriever: VectorRetriever,
        keyword_retriever: KeywordRetriever,
        k: int = 60
    ):
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.k = k
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict = None
    ) -> RetrievalResult:
        vector_result, keyword_result = await asyncio.gather(
            self.vector_retriever.retrieve(query, top_k * 2, filters),
            self.keyword_retriever.retrieve(query, top_k * 2, filters)
        )
        
        rrf_scores = {}
        chunk_map = {}
        
        for rank, chunk in enumerate(vector_result.chunks):
            rrf_scores[chunk.chunk_id] = 1 / (self.k + rank + 1)
            chunk_map[chunk.chunk_id] = chunk
        
        for rank, chunk in enumerate(keyword_result.chunks):
            if chunk.chunk_id in rrf_scores:
                rrf_scores[chunk.chunk_id] += 1 / (self.k + rank + 1)
            else:
                rrf_scores[chunk.chunk_id] = 1 / (self.k + rank + 1)
                chunk_map[chunk.chunk_id] = chunk
        
        sorted_chunks = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        chunks = []
        scores = []
        
        for chunk_id, score in sorted_chunks:
            chunks.append(chunk_map[chunk_id])
            scores.append(score)
        
        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            query=query,
            total=len(chunks)
        )
```

---

## 5. Rerank精排集成

### 5.1 Rerank Pipeline

```python
class RerankPipeline:
    def __init__(
        self,
        rerank_service_url: str,
        top_k: int = 5
    ):
        self.rerank_url = rerank_service_url
        self.top_k = top_k
    
    async def rerank(
        self,
        query: str,
        result: RetrievalResult
    ) -> RetrievalResult:
        if not result.chunks:
            return result
        
        documents = [chunk.content for chunk in result.chunks]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.rerank_url}/v1/rerank",
                json={
                    "query": query,
                    "documents": documents,
                    "top_k": self.top_k
                }
            )
        
        rerank_result = response.json()
        
        reranked_chunks = []
        reranked_scores = []
        
        for item in rerank_result["results"]:
            original_chunk = result.chunks[item["index"]]
            reranked_chunks.append(original_chunk)
            reranked_scores.append(item["score"])
        
        return RetrievalResult(
            chunks=reranked_chunks,
            scores=reranked_scores,
            query=query,
            total=len(reranked_chunks)
        )
```

---

## 6. Prompt模板设计

### 6.1 Prompt模板管理

```python
from jinja2 import Template

class PromptTemplateManager:
    def __init__(self):
        self.templates = {
            "selection_analysis": Template("""你是一个跨境电商AI选品专家。基于以下检索到的信息，回答用户问题。

## 上下文信息
{% for chunk in context %}
### 来源 {{ loop.index }}
{{ chunk.content }}

{% endfor %}

## 用户问题
{{ query }}

## 回答要求
1. 基于上下文信息回答，不要编造内容
2. 如果信息不足，明确说明
3. 引用来源编号
4. 给出具体的数据和建议

## 回答
"""),

            "trend_prediction": Template("""你是一个跨境电商市场趋势分析专家。基于以下数据，预测市场趋势。

## 市场数据
{% for item in market_data %}
- {{ item.category }}: 销量 {{ item.sales }}, 增长率 {{ item.growth_rate }}%
{% endfor %}

## 分析要求
1. 识别增长趋势
2. 发现潜在机会
3. 预测未来3个月走势

## 分析结果
"""),

            "competitor_analysis": Template("""你是一个竞品分析专家。对比以下竞品信息。

## 主产品
{{ main_product }}

## 竞品列表
{% for competitor in competitors %}
### 竞品 {{ loop.index }}
- 名称: {{ competitor.name }}
- 价格: ${{ competitor.price }}
- 评分: {{ competitor.rating }}
- 销量: {{ competitor.sales }}
{% endfor %}

## 分析维度
1. 价格竞争力
2. 产品差异化
3. 市场定位
4. 改进建议

## 分析报告
""")
        }
    
    def render(self, template_name: str, **kwargs) -> str:
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        return template.render(**kwargs)
    
    def add_template(self, name: str, template_str: str):
        self.templates[name] = Template(template_str)
```

### 6.2 RAG服务封装

```python
class RAGService:
    def __init__(
        self,
        retriever: HybridRetriever,
        rerank_pipeline: RerankPipeline,
        llm_client,
        prompt_manager: PromptTemplateManager
    ):
        self.retriever = retriever
        self.rerank_pipeline = rerank_pipeline
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
    
    async def query(
        self,
        query: str,
        top_k: int = 5,
        use_rerank: bool = True,
        filters: Dict = None
    ) -> RAGResponse:
        retrieval_result = await self.retriever.retrieve(
            query,
            top_k=top_k * 2,
            filters=filters
        )
        
        if use_rerank:
            retrieval_result = await self.rerank_pipeline.rerank(
                query,
                retrieval_result
            )
        
        context = retrieval_result.chunks[:top_k]
        
        prompt = self.prompt_manager.render(
            "selection_analysis",
            context=context,
            query=query
        )
        
        llm_response = await self.llm_client.generate(prompt)
        
        confidence = self._calculate_confidence(
            retrieval_result.scores[:top_k]
        )
        
        return RAGResponse(
            answer=llm_response,
            sources=context,
            confidence=confidence,
            metadata={
                "query": query,
                "retrieval_scores": retrieval_result.scores[:top_k],
                "total_retrieved": retrieval_result.total
            }
        )
    
    def _calculate_confidence(self, scores: List[float]) -> float:
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
```

---

## 附录

### A. 验收检查清单

```markdown
## D13-D15 验收检查清单

### RAG框架
- [ ] LlamaIndex框架集成
- [ ] Qdrant Vector Store连接
- [ ] 基础检索流程跑通

### 文档切片
- [ ] 递归字符切片器可用
- [ ] 语义边界切片器可用
- [ ] 元数据保留正确

### 混合检索
- [ ] 向量检索正常
- [ ] 关键词检索正常
- [ ] RRF融合正确
- [ ] 检索延迟<100ms

### Rerank
- [ ] Rerank服务调用正常
- [ ] 排序准确率提升

### Prompt模板
- [ ] 选品分析模板
- [ ] 趋势预测模板
- [ ] 竞品分析模板
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
