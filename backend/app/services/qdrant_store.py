from __future__ import annotations

from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from qdrant_client.http.models import PointStruct

from app.config import get_settings
from app.models import Visibility

settings = get_settings()
_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, timeout=30)
    return _client


def ensure_collection() -> None:
    c = client()
    names = [x.name for x in c.get_collections().collections]
    if settings.qdrant_collection in names:
        return
    c.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qm.VectorParams(size=settings.embed_dim, distance=qm.Distance.COSINE),
    )
    c.create_payload_index(
        settings.qdrant_collection,
        field_name="visibility",
        field_schema=qm.PayloadSchemaType.KEYWORD,
    )
    c.create_payload_index(
        settings.qdrant_collection,
        field_name="document_id",
        field_schema=qm.PayloadSchemaType.KEYWORD,
    )


def upsert_chunks(
    ids: list[str],
    vectors: list[list[float]],
    payloads: list[dict],
) -> None:
    ensure_collection()
    points = [
        PointStruct(id=pid, vector=vec, payload=pl)
        for pid, vec, pl in zip(ids, vectors, payloads)
    ]
    client().upsert(collection_name=settings.qdrant_collection, points=points)


def delete_document(document_id: UUID) -> None:
    ensure_collection()
    client().delete(
        collection_name=settings.qdrant_collection,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=str(document_id)))]
            )
        ),
    )


def search(vector: list[float], allowed: list[Visibility], limit: int = 40) -> list[qm.ScoredPoint]:
    ensure_collection()
    return client().search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=limit,
        query_filter=qm.Filter(
            must=[
                qm.FieldCondition(
                    key="visibility",
                    match=qm.MatchAny(any=[v.value for v in allowed]),
                )
            ]
        ),
        with_payload=True,
    )
