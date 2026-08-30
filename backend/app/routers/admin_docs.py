from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models import DocStatus, Document, User, Visibility
from app.schemas import DocumentOut, VisibilityOverride
from app.services.audit import audit
from app.services.qdrant_store import delete_document
from app.services.queue import enqueue_ingest, invalidate_cache

router = APIRouter(prefix="/admin/documents", tags=["admin-docs"])
settings = get_settings()
ALLOWED = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
}


@router.get("", response_model=list[DocumentOut])
async def list_docs(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(rows.scalars())


@router.post("", response_model=DocumentOut)
async def upload(
    file: UploadFile = File(...),
    visibility: str | None = Form(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(413, "File too large")
    name = file.filename or "upload"
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        raise HTTPException(400, "Unsupported file type")
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    stored = Path(settings.upload_dir) / f"{uuid4()}{suffix}"
    stored.write_bytes(data)
    override = False
    vis = Visibility.internal
    if visibility in {v.value for v in Visibility}:
        vis = Visibility(visibility)
        override = True
    doc = Document(
        filename=name,
        content_type=file.content_type or "application/octet-stream",
        storage_path=str(stored),
        visibility=vis,
        visibility_override=override,
        status=DocStatus.queued,
        uploaded_by=admin.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    await enqueue_ingest(str(doc.id))
    await audit(db, "upload_document", admin.id, filename=name, document_id=str(doc.id))
    return doc


@router.patch("/{doc_id}/visibility", response_model=DocumentOut)
async def override_visibility(
    doc_id: str,
    body: VisibilityOverride,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    doc = await db.get(Document, UUID(doc_id))
    if not doc:
        raise HTTPException(404, "Not found")
    doc.visibility = body.visibility
    doc.visibility_override = True
    await db.commit()
    await db.refresh(doc)
    await enqueue_ingest(str(doc.id))
    await invalidate_cache()
    await audit(db, "override_visibility", admin.id, document_id=str(doc.id), visibility=body.visibility.value)
    return doc


@router.delete("/{doc_id}")
async def remove_doc(doc_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from uuid import UUID

    uid = UUID(doc_id)
    doc = await db.get(Document, uid)
    if not doc:
        raise HTTPException(404, "Not found")
    delete_document(uid)
    try:
        os.remove(doc.storage_path)
    except OSError:
        pass
    await db.delete(doc)
    await db.commit()
    await invalidate_cache()
    await audit(db, "delete_document", admin.id, filename=doc.filename, document_id=doc_id)
    return {"ok": True}
