from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response, status

from app.config import get_settings
from app.models import Role
from app.schemas import TokenUser
from app.services.redis_client import ANSWER_NS

ph = PasswordHasher()
settings = get_settings()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_token(user: TokenUser, site: str) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "mcp": user.must_change_password,
        "site": site,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def cookie_name(site: str) -> str:
    return settings.admin_cookie if site == "admin" else settings.chat_cookie


SESSION_MAX_AGE = 12 * 3600


def _cookie_attrs() -> dict[str, Any]:
    # Secure/SameSite come from settings so set and delete always emit matching attributes
    # (browsers ignore a delete whose attributes don't match, and reject SameSite=None without Secure).
    return {"secure": settings.cookie_secure_effective, "samesite": settings.cookie_samesite, "path": "/"}


def set_session_cookies(response: Response, token: str, csrf: str, site: str) -> None:
    response.set_cookie(cookie_name(site), token, httponly=True, max_age=SESSION_MAX_AGE, **_cookie_attrs())
    # The CSRF token must stay readable by JS (double-submit pattern), hence not HttpOnly.
    response.set_cookie(settings.csrf_cookie, csrf, httponly=False, max_age=SESSION_MAX_AGE, **_cookie_attrs())


def clear_session(response: Response, site: str) -> None:
    response.delete_cookie(cookie_name(site), httponly=True, **_cookie_attrs())
    response.delete_cookie(settings.csrf_cookie, httponly=False, **_cookie_attrs())


def require_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie = request.cookies.get(settings.csrf_cookie, "")
    header = request.headers.get("X-CSRF-Token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def token_user_from_payload(payload: dict[str, Any]) -> TokenUser:
    return TokenUser(
        id=UUID(payload["sub"]),
        email=payload["email"],
        role=Role(payload["role"]),
        must_change_password=bool(payload.get("mcp")),
    )


def cache_key(role: str, message: str, vis: str, version: int) -> str:
    """Answer-cache key. ``version`` is the namespace version read *before* retrieval, so an
    answer computed across an invalidation is written to a dead namespace instead of going stale."""
    digest = hashlib.sha256(f"{role}|{vis}|{message.strip().lower()}".encode()).hexdigest()
    return f"{ANSWER_NS}:v{version}:{digest}"
