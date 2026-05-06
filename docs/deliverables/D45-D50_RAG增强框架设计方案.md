# RAG增强框架设计方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D45-D50 RAG增强框架与知识库管理
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. RAG架构设计](#2-rag架构设计)
- [3. 文档处理管道](#3-文档处理管道)
- [4. 向量检索引擎](#4-向量检索引擎)
- [5. 混合检索策略](#5-混合检索策略)
- [6. 知识库管理](#6-知识库管理)
- [7. API接口设计](#7-api接口设计)

---

## 1. 概述

### 1.1 设计目标

构建企业级RAG（Retrieval-Augmented Generation）框架，为AI选品决策提供知识增强能力。

### 1.2 核心能力

| 能力 | 说明 | 目标指标 |
|------|------|---------|
| 文档处理 | 多格式文档解析与切分 | 支持10+格式 |
| 向量检索 | 高效语义检索 | 召回率≥95% |
| 混合检索 | 向量+关键词融合 | 效果提升20% |
| 知识管理 | 知识库版本管理 | 增量更新 |

---

## 2. RAG架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG Framework                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Document Processing                    │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ Loader   │ │ Parser   │ │ Chunker  │ │ Enricher │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Embedding Service                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Text     │ │ Image    │ │ Multi    │               │   │
│  │  │ Embedder │ │ Embedder │ │ Modal    │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Retrieval Engine                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ Vector   │ │ Keyword  │ │ Hybrid   │ │ Reranker │   │   │
│  │  │ Search   │ │ Search   │ │ Search   │ │          │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Generation Service                     │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Context  │ │ Prompt   │ │ LLM      │               │   │
│  │  │ Builder  │ │ Template │ │ Client   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心类设计

```python
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel

class Document(BaseModel):
    doc_id: str
    content: str
    metadata: dict[str, Any]
    chunks: list["Chunk"] = []

class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any]

class RAGResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    confidence: float
    retrieval_time: float
    generation_time: float

class RAGPipeline:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        retriever: Retriever,
        generator: Generator
    ):
        self.loader = loader
        self.chunker = chunker
        self.embedder = embedder
        self.retriever = retriever
        self.generator = generator
    
    async def index(self, file_path: str) -> int:
        doc = await self.loader.load(file_path)
        chunks = self.chunker.chunk(doc)
        
        for chunk in chunks:
            chunk.embedding = await self.embedder.embed(chunk.content)
        
        await self.retriever.index(chunks)
        return len(chunks)
    
    async def query(self, question: str, top_k: int = 5) -> RAGResponse:
        import time
        start_time = time.time()
        
        query_embedding = await self.embedder.embed(question)
        chunks = await self.retriever.retrieve(query_embedding, top_k)
        
        retrieval_time = time.time() - start_time
        
        context = self._build_context(chunks)
        answer = await self.generator.generate(question, context)
        
        generation_time = time.time() - start_time - retrieval_time
        
        return RAGResponse(
            answer=answer,
            sources=[{"content": c.content, "metadata": c.metadata} for c in chunks],
            confidence=self._calculate_confidence(chunks),
            retrieval_time=retrieval_time,
            generation_time=generation_time
        )
```

---

## 3. 文档处理管道

### 3.1 文档加载器

```python
class DocumentLoader(ABC):
    @abstractmethod
    async def load(self, source: str) -> Document:
        pass

class PDFLoader(DocumentLoader):
    async def load(self, source: str) -> Document:
        import fitz
        
        doc = fitz.open(source)
        content = ""
        for page in doc:
            content += page.get_text()
        
        return Document(
            doc_id=str(uuid.uuid4()),
            content=content,
            metadata={"source": source, "type": "pdf", "pages": len(doc)}
        )

class MarkdownLoader(DocumentLoader):
    async def load(self, source: str) -> Document:
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
        
        return Document(
            doc_id=str(uuid.uuid4()),
            content=content,
            metadata={"source": source, "type": "markdown"}
        )

class WebPageLoader(DocumentLoader):
    async def load(self, url: str) -> Document:
        import aiohttp
        from bs4 import BeautifulSoup
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                html = await response.text()
        
        soup = BeautifulSoup(html, "html.parser")
        content = soup.get_text(separator="\n", strip=True)
        
        return Document(
            doc_id=str(uuid.uuid4()),
            content=content,
            metadata={"source": url, "type": "webpage"}
        )
```

### 3.2 文档切分器

```python
class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: Document) -> list[Chunk]:
        pass

class RecursiveCharacterChunker(Chunker):
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", ".", " "]
    
    def chunk(self, document: Document) -> list[Chunk]:
        chunks = []
        content = document.content
        
        for separator in self.separators:
            if separator in content:
                splits = content.split(separator)
                current_chunk = ""
                
                for split in splits:
                    if len(current_chunk) + len(split) <= self.chunk_size:
                        current_chunk += split + separator
                    else:
                        if current_chunk:
                            chunks.append(self._create_chunk(
                                document, current_chunk.strip(), len(chunks)
                            ))
                        current_chunk = split + separator
                
                if current_chunk:
                    chunks.append(self._create_chunk(
                        document, current_chunk.strip(), len(chunks)
                    ))
                
                break
        
        return chunks
    
    def _create_chunk(self, doc: Document, content: str, index: int) -> Chunk:
        return Chunk(
            chunk_id=f"{doc.doc_id}_chunk_{index}",
            doc_id=doc.doc_id,
            content=content,
            metadata={**doc.metadata, "chunk_index": index}
        )

class SemanticChunker(Chunker):
    def __init__(self, embedder: Embedder, similarity_threshold: float = 0.8):
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
    
    async def chunk(self, document: Document) -> list[Chunk]:
        sentences = self._split_sentences(document.content)
        embeddings = await self.embedder.embed_batch(sentences)
        
        chunks = []
        current_chunk_sentences = [sentences[0]]
        current_embedding = embeddings[0]
        
        for i in range(1, len(sentences)):
            similarity = self._cosine_similarity(current_embedding, embeddings[i])
            
            if similarity >= self.similarity_threshold:
                current_chunk_sentences.append(sentences[i])
                current_embedding = self._average_embedding(
                    embeddings[:i+1]
                )
            else:
                chunks.append(self._create_chunk(
                    document, " ".join(current_chunk_sentences), len(chunks)
                ))
                current_chunk_sentences = [sentences[i]]
                current_embedding = embeddings[i]
        
        if current_chunk_sentences:
            chunks.append(self._create_chunk(
                document, " ".join(current_chunk_sentences), len(chunks)
            ))
        
        return chunks
```

---

## 4. 向量检索引擎

### 4.1 Qdrant集成

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class QdrantRetriever:
    def __init__(self, collection_name: str, embedding_dim: int = 1536):
        self.client = QdrantClient(host="localhost", port=6333)
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        
        self._ensure_collection()
    
    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        if self.collection_name not in [c.name for c in collections]:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE
                )
            )
    
    async def index(self, chunks: list[Chunk]):
        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=chunk.embedding,
                payload={
                    "content": chunk.content,
                    "doc_id": chunk.doc_id,
                    "metadata": chunk.metadata
                }
            )
            for chunk in chunks if chunk.embedding
        ]
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
    
    async def retrieve(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_conditions: dict = None
    ) -> list[Chunk]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        query_filter = None
        if filter_conditions:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            query_filter = Filter(must=conditions)
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=query_filter
        )
        
        chunks = []
        for result in results:
            chunks.append(Chunk(
                chunk_id=str(result.id),
                doc_id=result.payload.get("doc_id"),
                content=result.payload.get("content"),
                embedding=result.vector,
                metadata=result.payload.get("metadata", {})
            ))
        
        return chunks
```

---

## 5. 混合检索策略

### 5.1 向量+关键词融合

```python
from enum import Enum

class FusionStrategy(str, Enum):
    RRF = "reciprocal_rank_fusion"
    WEIGHTED = "weighted_sum"
    SCORE_BASED = "score_based"

class HybridRetriever:
    def __init__(
        self,
        vector_retriever: QdrantRetriever,
        keyword_retriever: ElasticsearchRetriever,
        strategy: FusionStrategy = FusionStrategy.RRF
    ):
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.strategy = strategy
    
    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 5
    ) -> list[Chunk]:
        vector_results = await self.vector_retriever.retrieve(
            query_embedding, top_k * 2
        )
        
        keyword_results = await self.keyword_retriever.retrieve(
            query, top_k * 2
        )
        
        if self.strategy == FusionStrategy.RRF:
            return self._rrf_fusion(vector_results, keyword_results, top_k)
        elif self.strategy == FusionStrategy.WEIGHTED:
            return self._weighted_fusion(vector_results, keyword_results, top_k)
        else:
            return self._score_based_fusion(vector_results, keyword_results, top_k)
    
    def _rrf_fusion(
        self,
        vector_results: list[Chunk],
        keyword_results: list[Chunk],
        top_k: int,
        k: int = 60
    ) -> list[Chunk]:
        scores = {}
        chunk_map = {}
        
        for i, chunk in enumerate(vector_results):
            chunk_map[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1 / (k + i + 1)
        
        for i, chunk in enumerate(keyword_results):
            chunk_map[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1 / (k + i + 1)
        
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        return [chunk_map[cid] for cid in sorted_ids[:top_k]]
    
    def _weighted_fusion(
        self,
        vector_results: list[Chunk],
        keyword_results: list[Chunk],
        top_k: int,
        vector_weight: float = 0.6
    ) -> list[Chunk]:
        scores = {}
        chunk_map = {}
        
        for chunk in vector_results:
            chunk_map[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + vector_weight
        
        for chunk in keyword_results:
            chunk_map[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + (1 - vector_weight)
        
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        return [chunk_map[cid] for cid in sorted_ids[:top_k]]
```

### 5.2 Reranker

```python
class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)
    
    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int = 5
    ) -> list[Chunk]:
        pairs = [(query, chunk.content) for chunk in chunks]
        scores = self.model.predict(pairs)
        
        scored_chunks = list(zip(chunks, scores))
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        return [chunk for chunk, score in scored_chunks[:top_k]]
```

---

## 6. 知识库管理

### 6.1 知识库模型

```python
from datetime import datetime

class KnowledgeBase(BaseModel):
    kb_id: str
    name: str
    description: str
    collection_name: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime
    status: str = "active"

class KnowledgeBaseManager:
    def __init__(self, db: Database, retriever: QdrantRetriever):
        self.db = db
        self.retriever = retriever
    
    async def create_kb(self, name: str, description: str = "") -> KnowledgeBase:
        kb_id = str(uuid.uuid4())
        collection_name = f"kb_{kb_id.replace('-', '_')}"
        
        kb = KnowledgeBase(
            kb_id=kb_id,
            name=name,
            description=description,
            collection_name=collection_name,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        await self.db.insert("knowledge_bases", kb.dict())
        return kb
    
    async def add_document(self, kb_id: str, document: Document) -> int:
        kb = await self.get_kb(kb_id)
        
        chunker = RecursiveCharacterChunker()
        chunks = chunker.chunk(document)
        
        embedder = get_embedder()
        for chunk in chunks:
            chunk.embedding = await embedder.embed(chunk.content)
        
        await self.retriever.index(chunks)
        
        await self.db.update(
            "knowledge_bases",
            {"kb_id": kb_id},
            {
                "document_count": kb.document_count + 1,
                "chunk_count": kb.chunk_count + len(chunks),
                "updated_at": datetime.now().isoformat()
            }
        )
        
        return len(chunks)
    
    async def delete_document(self, kb_id: str, doc_id: str) -> bool:
        await self.retriever.delete_by_doc_id(doc_id)
        return True
```

---

## 7. API接口设计

```python
from fastapi import APIRouter, UploadFile, File

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

@router.post("/knowledge-bases")
async def create_knowledge_base(kb: KnowledgeBaseCreate):
    manager = get_kb_manager()
    result = await manager.create_kb(kb.name, kb.description)
    return result

@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    manager = get_kb_manager()
    
    content = await file.read()
    doc = await parse_document(file.filename, content)
    
    chunk_count = await manager.add_document(kb_id, doc)
    
    return {"status": "success", "chunks": chunk_count}

@router.post("/knowledge-bases/{kb_id}/query")
async def query_knowledge_base(kb_id: str, query: QueryRequest):
    pipeline = get_rag_pipeline(kb_id)
    result = await pipeline.query(query.question, query.top_k)
    return result

@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    manager = get_kb_manager()
    success = await manager.delete_document(kb_id, doc_id)
    return {"success": success}
```

---

## 附录

### A. 配置示例

```yaml
rag:
  embedding:
    model: "BAAI/bge-large-zh"
    dimension: 1024
    batch_size: 32
  
  chunking:
    strategy: "recursive"
    chunk_size: 1000
    chunk_overlap: 200
  
  retrieval:
    top_k: 5
    reranker: "BAAI/bge-reranker-base"
  
  qdrant:
    host: "localhost"
    port: 6333
    grpc_port: 6334
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
