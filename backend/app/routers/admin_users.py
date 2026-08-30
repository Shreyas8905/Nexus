from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models import Role, User
from app.schemas import CreateInternalUserRequest, ResetPasswordRequest, UserOut
from app.security import hash_password
from app.services.audit import audit

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/internal", response_model=list[UserOut])
async def list_internal(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(User).where(User.role == Role.internal).order_by(User.created_at.desc()))
    return list(rows.scalars())


@router.get("/external", response_model=list[UserOut])
async def list_external(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(User).where(User.role == Role.external).order_by(User.created_at.desc()))
    return list(rows.scalars())


@router.post("/internal", response_model=UserOut)
async def create_internal(body: CreateInternalUserRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    email = str(body.email).lower()
    exists = await db.execute(select(User).where(User.email == email))
    if exists.scalar_one_or_none():
        raise HTTPException(409, "Email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=Role.internal,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await audit(db, "create_internal_user", admin.id, email=email)
    return user


@router.post("/{user_id}/disable")
async def disable_user(user_id: UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user or user.role == Role.admin:
        raise HTTPException(404, "User not found")
    user.is_active = False
    await db.commit()
    await audit(db, "disable_user", admin.id, email=user.email)
    return {"ok": True}


@router.post("/{user_id}/enable")
async def enable_user(user_id: UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = True
    await db.commit()
    return {"ok": True}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: UUID,
    body: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.role != Role.internal:
        raise HTTPException(404, "Internal user not found")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    await db.commit()
    await audit(db, "reset_password", admin.id, email=user.email)
    return {"ok": True}
