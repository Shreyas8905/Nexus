from __future__ import annotations

import asyncio
import logging

from app.db import engine, Base
from app.services.qdrant_store import ensure_collection
from app.services.queue import QUEUE_KEY
from app.services.redis_client import get_redis
from app.services.ingest import ingest_document

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nexus.worker")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_collection()
    r = get_redis()
    log.info("ingestion worker listening on %s", QUEUE_KEY)
    while True:
        item = await r.brpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        _, doc_id = item
        log.info("ingest %s", doc_id)
        try:
            await ingest_document(doc_id)
        except Exception:
            log.exception("failed ingest %s", doc_id)


if __name__ == "__main__":
    asyncio.run(main())
