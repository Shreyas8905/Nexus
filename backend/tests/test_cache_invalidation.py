import inspect

import app.services.queue as queue
import app.services.redis_client as redis_client
from app.security import cache_key
from app.services.queue import get_cached, invalidate_cache, set_cached
from app.services.redis_client import get_answer_version


def test_no_keyspace_scans_remain():
    src = inspect.getsource(queue) + inspect.getsource(redis_client)
    for banned in ("scan_iter", ".scan(", ".keys(", "nexus:ans:*"):
        assert banned not in src


def test_key_is_namespaced_by_version():
    assert cache_key("internal", "Hi", "all", 3).startswith("nexus:ans:v3:")
    assert cache_key("internal", " hi ", "all", 3) == cache_key("internal", "Hi", "all", 3)
    assert cache_key("internal", "hi", "all", 3) != cache_key("internal", "hi", "all", 4)
    assert cache_key("internal", "hi", "all", 1) != cache_key("external", "hi", "generic", 1)


async def test_invalidate_makes_old_entries_unreachable(fake_redis):
    v0 = await get_answer_version()
    assert v0 == 0
    await set_cached(cache_key("internal", "q", "all", v0), "answer")
    assert await get_cached(cache_key("internal", "q", "all", v0)) == "answer"

    await invalidate_cache()

    v1 = await get_answer_version()
    assert v1 == v0 + 1
    assert await get_cached(cache_key("internal", "q", "all", v1)) is None


async def test_invalidation_cost_is_constant_in_keyspace(fake_redis):
    for i in range(2000):
        await fake_redis.set(f"nexus:ans:v0:{i}", "x", ex=3600)
    calls = []
    original = fake_redis.execute_command

    async def spy(*args, **kw):
        calls.append(args[0])
        return await original(*args, **kw)

    fake_redis.execute_command = spy
    await invalidate_cache()
    assert [c.upper() for c in calls] in (["INCR"], ["INCRBY"])  # redis-py sends INCRBY


async def test_inflight_answer_across_invalidation_never_served(fake_redis):
    key = cache_key("internal", "q", "all", await get_answer_version())  # taken before retrieval
    await invalidate_cache()  # admin changes a doc while the answer is generating
    await set_cached(key, "stale")  # generation finishes and writes under the old version
    fresh = cache_key("internal", "q", "all", await get_answer_version())
    assert await get_cached(fresh) is None
