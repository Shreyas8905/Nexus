from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import Chunk, DocStatus, Document
from app.services.chunking import chunk_blocks
from app.services.classify import classify_blocks
from app.services.ollama_client import embed_texts
from app.services.parse import parse_file
from app.services.qdrant_store import delete_document, upsert_chunks


async def _set_progress(db: AsyncSession, doc: Document, step: str, pct: int, status: DocStatus | None = None) -> None:
    doc.progress_step = step
    doc.progress_pct = pct
    if status:
        doc.status = status
    await db.commit()


async def ingest_document(document_id: str) -> None:
    async with SessionLocal() as db:
        doc = await db.get(Document, UUID(document_id))
        if not doc:
            return
        try:
            delete_document(doc.id)
            await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            await db.commit()
            await _set_progress(db, doc, "parsing", 10, DocStatus.parsing)
            blocks = await parse_file(doc.storage_path, doc.content_type, doc.filename)
            if not doc.visibility_override:
                doc.visibility = classify_blocks(blocks, doc.filename)
            await _set_progress(db, doc, "chunking", 40)
            drafts = chunk_blocks(blocks)
            await _set_progress(db, doc, "embedding", 55, DocStatus.embedding)
            vectors: list[list[float]] = []
            batch = 8
            for i in range(0, len(drafts), batch):
                vectors.extend(await embed_texts([d.text for d in drafts[i : i + batch]]))
                await _set_progress(db, doc, "embedding", min(90, 55 + int(35 * (i + batch) / max(len(drafts), 1))))
            ids: list[str] = []
            payloads: list[dict] = []
            for draft, vec in zip(drafts, vectors):
                chunk = Chunk(
                    document_id=doc.id,
                    text=draft.text,
                    page=draft.page,
                    sheet=draft.sheet,
                    content_kind=draft.kind,
                    visibility=doc.visibility,
                )
                db.add(chunk)
                await db.flush()
                ids.append(str(chunk.id))
                payloads.append(
                    {
                        "document_id": str(doc.id),
                        "filename": doc.filename,
                        "text": draft.text,
                        "parent_text": draft.parent_text,
                        "page": draft.page,
                        "sheet": draft.sheet,
                        "content_kind": draft.kind,
                        "visibility": doc.visibility.value,
                    }
                )
            if ids:
                upsert_chunks(ids, vectors, payloads)
            doc.chunk_count = len(ids)
            await _set_progress(db, doc, "ready", 100, DocStatus.ready)
        except Exception as exc:
            doc.status = DocStatus.failed
            doc.progress_step = "failed"
            doc.error = str(exc)[:2000]
            await db.commit()
