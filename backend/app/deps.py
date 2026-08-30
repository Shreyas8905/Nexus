from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Role, User
from app.schemas import TokenUser
from app.security import cookie_name, decode_token, require_csrf, token_user_from_payload

settings = get_settings()


def _site_from_request(request: Request) -> str:
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if settings.admin_origin in origin or request.headers.get("X-Nexus-Site") == "admin":
        return "admin"
    host = request.headers.get("host", "")
    if "8081" in host:
        return "admin"
    return "chat"


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    require_csrf(request)
    site = _site_from_request(request)
    token = request.cookies.get(cookie_name(site))
    if not token:
        # admin cookie might be used if host detection failed
        token = request.cookies.get(settings.admin_cookie) or request.cookies.get(settings.chat_cookie)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    user = await db.get(User, token_user_from_payload(payload).id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    return user


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


def require_roles(*roles: Role):
    async def _inner(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _inner


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
