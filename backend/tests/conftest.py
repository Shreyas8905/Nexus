import os

# Must be set before app modules import (they read settings at import time).
os.environ.setdefault("ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nexus:pw@localhost:5432/nexus")
os.environ.setdefault("TRUSTED_PROXIES", "")

import fakeredis.aioredis
import pytest

import app.services.redis_client as redis_client


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "_redis", r)
    return r
