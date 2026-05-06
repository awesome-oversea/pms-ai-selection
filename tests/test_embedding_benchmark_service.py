from __future__ import annotations

from src.services.embedding_benchmark_service import EmbeddingBenchmarkService


class _FastEmbeddingService:
    provider_mode = "local-fast-test"

    def encode(self, texts, batch_size=256):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def encode_single(self, text):
        return [1.0, 0.0, 0.0, 0.0]


def test_embedding_benchmark_reaches_phase33_5000_qps_target():
    result = EmbeddingBenchmarkService(_FastEmbeddingService()).run_benchmark(
        sample_count=5000,
        batch_size=1000,
        target_qps=5000.0,
        latency_target_ms=50.0,
    )

    assert result["ready"] is True
    assert result["passed"] is True
    assert result["sample_count"] == 5000
    assert result["vector_count"] == 5000
    assert result["dimension"] == 4
    assert result["qps"] >= 5000.0
    assert result["qps_passed"] is True
    assert result["latency_passed"] is True
    assert result["provider_mode"] == "local-fast-test"
    assert result["resource_usage"]["resource_backend"] == "estimated-vector-footprint"
