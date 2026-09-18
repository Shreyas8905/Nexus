from __future__ import annotations

from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def get_cache_version() -> int:
    r = get_redis()
    ver = await r.get("nexus:ans:version")
    return int(ver) if ver else 1


async def increment_cache_version() -> int:
    r = get_redis()
    return await r.incr("nexus:ans:version")
