from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, require_admin, _site_from_request
from app.models import Role, User
from app.schemas import (
    ChangePasswordRequest,
    ExternalStartRequest,
    LoginRequest,
    MeResponse,
    TokenUser,
    UserOut,
)
from app.security import (
    clear_session,
    create_token,
    hash_password,
    new_csrf,
    set_session_cookies,
    verify_password,
)
from app.services.audit import audit
from app.services.queue import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_site(request: Request, intended: str) -> str:
    detected = _site_from_request(request)
    if intended == "admin":
        return "admin"
    return detected


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if await rate_limit(f"rl:login:{request.client.host if request.client else 'x'}", 20, 60):
        raise HTTPException(429, "Too many login attempts")
    site = _cookie_site(request, "auto")
    result = await db.execute(select(User).where(User.email == str(body.email).lower()))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    if site == "admin" and user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    if site == "chat" and user.role == Role.admin:
        raise HTTPException(403, "Use the admin site to sign in as admin")
    if user.role == Role.external:
        raise HTTPException(400, "External users start with email only")
    user.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    csrf = new_csrf()
    token = create_token(
        TokenUser(id=user.id, email=user.email, role=user.role, must_change_password=user.must_change_password),
        site,
    )
    set_session_cookies(response, token, csrf, site)
    await audit(db, "login", user.id, site=site)
    return {"user": UserOut.model_validate(user), "csrf": csrf}


@router.post("/admin/login")
async def admin_login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    request.state.force_site = "admin"
    if await rate_limit(f"rl:adminlogin:{request.client.host if request.client else 'x'}", 20, 60):
        raise HTTPException(429, "Too many login attempts")
    result = await db.execute(select(User).where(User.email == str(body.email).lower()))
    user = result.scalar_one_or_none()
    if (
        not user
        or user.role != Role.admin
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    user.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    csrf = new_csrf()
    token = create_token(
        TokenUser(id=user.id, email=user.email, role=user.role, must_change_password=user.must_change_password),
        "admin",
    )
    set_session_cookies(response, token, csrf, "admin")
    await audit(db, "login", user.id, site="admin")
    return {"user": UserOut.model_validate(user), "csrf": csrf}


@router.post("/external")
async def external_start(body: ExternalStartRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if await rate_limit(f"rl:ext:{request.client.host if request.client else 'x'}", 30, 60):
        raise HTTPException(429, "Too many requests")
    email = str(body.email).lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and user.role != Role.external:
        raise HTTPException(400, "This email belongs to an internal account")
    if not user:
        user = User(email=email, role=Role.external, password_hash=None, is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.is_active:
        raise HTTPException(403, "Access revoked")
    user.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    csrf = new_csrf()
    token = create_token(TokenUser(id=user.id, email=user.email, role=user.role), "chat")
    set_session_cookies(response, token, csrf, "chat")
    await audit(db, "external_start", user.id)
    return {"user": UserOut.model_validate(user), "csrf": csrf}


@router.post("/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user)):
    site = _site_from_request(request)
    if user.role == Role.admin:
        site = "admin"
    clear_session(response, site)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(request: Request, user: User = Depends(get_current_user)):
    csrf = request.cookies.get("nexus_csrf") or new_csrf()
    site = "admin" if user.role == Role.admin else "chat"
    return MeResponse(user=UserOut.model_validate(user), csrf=csrf, site=site)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()
    return {"ok": True}
