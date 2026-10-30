from __future__ import annotations

from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None

# Answer-cache namespace versioning.
#
# Cached answers live at ``nexus:ans:v{version}:{digest}``. Invalidation is a single INCR of
# ANSWER_VERSION_KEY: every key written under the previous version becomes unreachable at once
# (O(1), no KEYS/SCAN) and is reclaimed by its TTL rather than by an explicit delete.
ANSWER_NS = "nexus:ans"
ANSWER_VERSION_KEY = "nexus:ans:version"


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def get_answer_version() -> int:
    """Current answer-cache namespace version (0 if never bumped)."""
    raw = await get_redis().get(ANSWER_VERSION_KEY)
    return int(raw) if raw else 0


async def bump_answer_version() -> int:
    """Invalidate every cached answer in O(1) and return the new version."""
    return int(await get_redis().incr(ANSWER_VERSION_KEY))
