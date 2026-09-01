from __future__ import annotations

from rank_bm25 import BM25Okapi
from uuid import UUID

from app.models import Role, Visibility
from app.schemas import Citation
from app.services.guardrails import allowed_visibilities
from app.services.llm_client import embed_texts
from app.services.qdrant_store import search


def _lexical_rerank(query: str, hits: list) -> list:
    if not hits:
        return []
    corpus = [(h.payload or {}).get("text") or "" for h in hits]
    tokenized = [c.lower().split() for c in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(zip(hits, scores), key=lambda x: (x[1], x[0].score), reverse=True)
    return [h for h, _ in ranked]


async def retrieve(query: str, role: Role, k: int = 8) -> tuple[str, list[Citation]]:
    allowed = allowed_visibilities(role)
    qvec = (await embed_texts([query]))[0]
    dense = search(qvec, allowed, limit=40)
    reranked = _lexical_rerank(query, dense)[:k]
    citations: list[Citation] = []
    context_parts: list[str] = []
    for h in reranked:
        payload = h.payload or {}
        parent = payload.get("parent_text") or payload.get("text") or ""
        title = payload.get("filename") or "document"
        snippet = (payload.get("text") or "")[:400]
        context_parts.append(f"[{title} p={payload.get('page')} sheet={payload.get('sheet')}]\n{parent[:1800]}")
        citations.append(
            Citation(
                document_id=UUID(payload["document_id"]),
                title=title,
                page=payload.get("page"),
                sheet=payload.get("sheet"),
                snippet=snippet,
                content_kind=payload.get("content_kind") or "text",
            )
        )
    return "\n\n---\n\n".join(context_parts), citations
