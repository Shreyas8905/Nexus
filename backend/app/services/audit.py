from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def audit(db: AsyncSession, action: str, actor_id: UUID | None = None, **detail) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, detail=detail or None))
    await db.commit()
