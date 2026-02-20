from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
QDRANT_PATH = DATA_DIR / "qdrant"
COLLECTION_NAME = "rules_embeddings"
EMBEDDING_DIM = 1536

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is not None:
        return _client

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(QDRANT_PATH))

    collections = {item.name for item in client.get_collections().collections}
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(
                size=EMBEDDING_DIM,
                distance=qmodels.Distance.COSINE,
            ),
        )

    _client = client
    return client


def find_duplicate_rule(vector: list[float], threshold: float = 0.88) -> tuple[str | None, float | None]:
    client = _get_client()
    hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        limit=1,
        score_threshold=threshold,
    )
    if not hits:
        return None, None

    top = hits[0]
    score = float(top.score) if top.score is not None else None
    payload_rule_id = None
    if isinstance(top.payload, dict):
        payload_rule_id = top.payload.get("rule_id")
    return str(payload_rule_id or top.id), score


def upsert_rule_vector(
    rule_id: str,
    vector: list[float],
    yaml_text: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = _get_client()
    payload = {"yaml": yaml_text, "rule_id": rule_id}
    if metadata:
        payload.update(metadata)

    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"rule:{rule_id}"))

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            qmodels.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )


def search_rule_vectors(
    vector: list[float],
    limit: int = 8,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    client = _get_client()
    kwargs: dict[str, Any] = {
        "collection_name": COLLECTION_NAME,
        "query_vector": vector,
        "limit": max(1, min(limit, 20)),
    }
    if score_threshold is not None:
        kwargs["score_threshold"] = float(score_threshold)

    hits = client.search(**kwargs)
    results: list[dict[str, Any]] = []
    for hit in hits:
        payload = hit.payload if isinstance(hit.payload, dict) else {}
        results.append(
            {
                "id": str(payload.get("rule_id") or hit.id),
                "score": float(hit.score) if hit.score is not None else 0.0,
                "payload": payload,
            }
        )
    return results
