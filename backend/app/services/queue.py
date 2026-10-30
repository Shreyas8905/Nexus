from __future__ import annotations

from app.services.redis_client import bump_answer_version, get_redis

QUEUE_KEY = "nexus:ingest"


async def enqueue_ingest(document_id: str) -> None:
    await get_redis().lpush(QUEUE_KEY, document_id)


async def get_cached(key: str) -> str | None:
    return await get_redis().get(key)


async def set_cached(key: str, value: str, ttl: int = 3600) -> None:
    await get_redis().set(key, value, ex=ttl)


async def invalidate_cache() -> None:
    """Drop all cached answers by bumping the namespace version (O(1), no keyspace scan)."""
    await bump_answer_version()


async def rate_limit(key: str, limit: int, window: int) -> bool:
    r = get_redis()
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, window)
    return n > limit
