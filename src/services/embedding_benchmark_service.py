from __future__ import annotations

import statistics
import time
from typing import Any

from src.services.embedding import EmbeddingService


class EmbeddingBenchmarkService:
    def __init__(self, embedding_service: EmbeddingService | None = None) -> None:
        self.embedding_service = embedding_service or EmbeddingService()

    def run_benchmark(
        self,
        *,
        sample_count: int = 1000,
        batch_size: int = 256,
        text_prefix: str = "cross border product embedding benchmark",
        target_qps: float = 5000.0,
        latency_target_ms: float = 50.0,
    ) -> dict[str, Any]:
        sample_count = max(1, int(sample_count))
        batch_size = max(1, int(batch_size))
        texts = [f"{text_prefix} #{idx}" for idx in range(sample_count)]
        batches = [texts[idx : idx + batch_size] for idx in range(0, len(texts), batch_size)]

        start = time.perf_counter()
        vectors: list[list[float]] = []
        batch_latencies_ms: list[float] = []
        for batch in batches:
            batch_start = time.perf_counter()
            vectors.extend(self.embedding_service.encode(batch, batch_size=batch_size))
            batch_latencies_ms.append((time.perf_counter() - batch_start) * 1000)
        total_elapsed = max(time.perf_counter() - start, 1e-9)

        single_latencies_ms: list[float] = []
        for text in texts[: min(10, len(texts))]:
            single_start = time.perf_counter()
            self.embedding_service.encode_single(text)
            single_latencies_ms.append((time.perf_counter() - single_start) * 1000)
        single_p95_ms = max(single_latencies_ms) if len(single_latencies_ms) < 2 else statistics.quantiles(single_latencies_ms, n=20)[18]
        qps = sample_count / total_elapsed
        dimension = len(vectors[0]) if vectors else 0
        estimated_vector_memory_mb = len(vectors) * dimension * 4 / (1024 * 1024)
        return {
            "sample_count": sample_count,
            "batch_size": batch_size,
            "batch_count": len(batches),
            "vector_count": len(vectors),
            "dimension": dimension,
            "provider_mode": self.embedding_service.provider_mode,
            "elapsed_ms": round(total_elapsed * 1000, 3),
            "qps": round(qps, 2),
            "target_qps": target_qps,
            "qps_passed": qps >= target_qps,
            "single_p95_ms": round(single_p95_ms, 3),
            "latency_target_ms": latency_target_ms,
            "latency_passed": single_p95_ms < latency_target_ms,
            "batch_latency_ms": {
                "min": round(min(batch_latencies_ms), 3) if batch_latencies_ms else 0.0,
                "max": round(max(batch_latencies_ms), 3) if batch_latencies_ms else 0.0,
                "avg": round(sum(batch_latencies_ms) / max(len(batch_latencies_ms), 1), 3),
            },
            "resource_usage": {
                "estimated_vector_memory_mb": round(estimated_vector_memory_mb, 3),
                "resource_backend": "estimated-vector-footprint",
            },
            "ready": len(vectors) == sample_count,
            "passed": len(vectors) == sample_count and qps >= target_qps and single_p95_ms < latency_target_ms,
        }
