from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.db import Base, engine, SessionLocal
from app.middleware import SecurityHeadersMiddleware
from app.models import Role, User
from app.routers import admin_docs, admin_users, auth, chat
from app.security import hash_password
from app.services.qdrant_store import ensure_collection

settings = get_settings()
log = logging.getLogger("nexus.api")
if not settings.is_development and not settings.trusted_proxies.strip():
    log.warning(
        "TRUSTED_PROXIES is empty: X-Forwarded-For/X-Real-IP are ignored, so behind a reverse proxy "
        "all clients share the proxy's IP for rate limiting and audit logs"
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        existing = await db.execute(select(User).where(User.role == Role.admin))
        if existing.scalar_one_or_none() is None:
            db.add(
                User(
                    email=settings.admin_bootstrap_email.lower(),
                    password_hash=hash_password(settings.admin_bootstrap_password),
                    role=Role.admin,
                    is_active=True,
                    must_change_password=True,
                )
            )
            await db.commit()
    ensure_collection()
    yield


app = FastAPI(title="Nexus API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def _validated_cors_origins(origins: list[str], allow_credentials: bool) -> list[str]:
    """Browsers refuse `*` with credentials and Starlette would otherwise echo any Origin back."""
    if allow_credentials and "*" in origins:
        raise RuntimeError("CORS: wildcard origins are not allowed when credentials are allowed")
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_validated_cors_origins(settings.cors_list, allow_credentials=True),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Nexus-Site"],
)
# Added last => outermost, so CORS preflight and error responses carry the headers too.
app.add_middleware(SecurityHeadersMiddleware, hsts=not settings.is_development)

# Create a master router for all API endpoints to support /api prefix
api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_docs.router)
api_router.include_router(chat.router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"ok": True}
