from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.db import Base, engine, SessionLocal
from app.models import Role, User
from app.routers import admin_docs, admin_users, auth, chat
from app.security import hash_password
from app.services.qdrant_store import ensure_collection

settings = get_settings()


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Nexus-Site"],
)

app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(admin_docs.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"ok": True}
