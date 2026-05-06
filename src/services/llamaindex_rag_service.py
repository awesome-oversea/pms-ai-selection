from __future__ import annotations

import importlib.util
from time import perf_counter
from typing import Any

from src.rag.retriever import HybridRetriever


class LlamaIndexRAGService:
    def __init__(self) -> None:
        self.installed = importlib.util.find_spec("llama_index") is not None

    def build_status(self) -> dict[str, Any]:
        return {
            "framework": "llama-index",
            "installed": self.installed,
            "dependency": "llama-index>=0.12.0",
            "active_mode": "llama-index" if self.installed else "hybrid-compatible-fallback",
            "fallback": {
                "enabled": True,
                "engine": "src.rag.retriever.HybridRetriever",
                "reason": None if self.installed else "llama_index package not installed in current runtime",
            },
            "pipeline": {
                "document_loader": "llama_index.core.Document" if self.installed else "dict-documents",
                "index": "VectorStoreIndex" if self.installed else "HybridRetriever",
                "retriever": "as_retriever" if self.installed else "retrieve",
                "rerank_ready": True,
                "cache_ready": True,
            },
            "diagnostics": {
                "detection_method": "importlib.util.find_spec",
                "import_ready": self.installed,
                "fallback_reason": None if self.installed else "package 'llama_index' not installed",
                "compare_endpoint_ready": True,
            },
            "ready": True,
        }

    async def compare_with_hybrid(self, *, query: str, documents: list[dict[str, Any]], top_k: int = 5) -> dict[str, Any]:
        hybrid_started = perf_counter()
        hybrid_results = await self._run_hybrid(query=query, documents=documents, top_k=top_k)
        hybrid_latency_ms = round((perf_counter() - hybrid_started) * 1000, 3)
        llamaindex_started = perf_counter()
        llamaindex_results = await self._run_llamaindex(query=query, documents=documents, top_k=top_k) if self.installed else []
        llamaindex_latency_ms = round((perf_counter() - llamaindex_started) * 1000, 3) if self.installed else None
        active_results = llamaindex_results if llamaindex_results else hybrid_results
        overlap_ids = sorted({item.get("id") for item in llamaindex_results} & {item.get("id") for item in hybrid_results})
        return {
            "query": query,
            "top_k": top_k,
            "mode": "llama-index" if llamaindex_results else "hybrid-compatible-fallback",
            "llamaindex_installed": self.installed,
            "llamaindex_results": llamaindex_results,
            "hybrid_results": hybrid_results,
            "active_results": active_results,
            "metrics": {
                "document_count": len(documents),
                "hybrid_latency_ms": hybrid_latency_ms,
                "llamaindex_latency_ms": llamaindex_latency_ms,
                "active_engine": "llama-index" if llamaindex_results else "hybrid-compatible-fallback",
            },
            "comparison": {
                "llamaindex_count": len(llamaindex_results),
                "hybrid_count": len(hybrid_results),
                "overlap_ids": overlap_ids,
                "overlap_count": len(overlap_ids),
                "fallback_used": not bool(llamaindex_results),
            },
        }

    async def _run_hybrid(self, *, query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        retriever = HybridRetriever(
            fusion_top_k=top_k,
            cache_enabled=False,
            enable_qdrant_vector_search=False,
        )
        retriever.add_documents(documents)
        results = await retriever.retrieve(query, top_k=top_k)
        return [
            {
                "id": item.metadata.get("id") or item.metadata.get("document_id") or item.source or str(index),
                "content": item.content,
                "score": item.score,
                "source": item.source,
                "metadata": item.metadata,
                "rank": item.rank,
            }
            for index, item in enumerate(results, 1)
        ]

    async def _run_llamaindex(self, *, query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        try:
            from llama_index.core import Document, Settings, VectorStoreIndex
            from llama_index.core.embeddings import MockEmbedding

            Settings.embed_model = MockEmbedding(embed_dim=8)
            llama_docs = [Document(text=str(doc.get("content") or ""), metadata=doc.get("metadata") or {"id": doc.get("id")}) for doc in documents]
            index = VectorStoreIndex.from_documents(llama_docs)
            retriever = index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query)
            results: list[dict[str, Any]] = []
            for rank, node in enumerate(nodes[:top_k], 1):
                metadata = dict(getattr(node.node, "metadata", {}) or {})
                results.append(
                    {
                        "id": metadata.get("id") or metadata.get("document_id") or str(rank),
                        "content": getattr(node.node, "text", ""),
                        "score": float(getattr(node, "score", 0.0) or 0.0),
                        "source": metadata.get("source", "llama-index"),
                        "metadata": metadata,
                        "rank": rank,
                    }
                )
            return results
        except Exception:
            return []
