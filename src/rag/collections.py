from __future__ import annotations

DEFAULT_QDRANT_COLLECTION_NAME = "product_knowledge"
LOCAL_KNOWLEDGE_QDRANT_COLLECTION_NAME = "product_knowledge_local"


def resolve_qdrant_collection_name(
    configured_name: str | None,
    *,
    use_local_knowledge: bool = False,
) -> str:
    normalized = (configured_name or "").strip()
    if normalized:
        return normalized
    if use_local_knowledge:
        return LOCAL_KNOWLEDGE_QDRANT_COLLECTION_NAME
    return DEFAULT_QDRANT_COLLECTION_NAME
