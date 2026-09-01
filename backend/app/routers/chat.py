from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Role, User
from app.schemas import ChatRequest
from app.security import cache_key
from app.services.audit import audit
from app.services.guardrails import REFUSAL, input_guard, scrub_output
from app.services.llm_client import generate_stream
from app.services.queue import get_cached, rate_limit, set_cached
from app.services.retrieve import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_INTERNAL = (
    "You are Nexus, an intranet knowledge assistant. Answer only from the provided context. "
    "If the context is insufficient, say you do not know. Cite sources by document title when relevant."
)
SYSTEM_EXTERNAL = (
    "You are Nexus, a public-facing campus assistant. Answer only from generic context. "
    "Never reveal individual student records, grades, contact details, or faculty personal data "
    "other than published achievements. If asked for those, refuse. Do not mention document filenames."
)


@router.post("/stream")
async def chat_stream(body: ChatRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role == Role.admin:
        raise HTTPException(403, "Admin uses the admin site, not chat")
    if await rate_limit(f"rl:chat:{user.id}", 40, 60):
        raise HTTPException(429, "Rate limit exceeded")

    decision, reason = await input_guard(body.message, user.role)
    user.query_count = (user.query_count or 0) + 1
    user.last_seen_at = datetime.now(timezone.utc)
    await db.commit()

    if decision == "refuse":
        await audit(db, "pii_refuse", user.id, message=body.message[:200])

        async def refused():
            yield f"data: {json.dumps({'type': 'token', 'text': reason})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'refused': True, 'citations': []})}\n\n"

        return StreamingResponse(refused(), media_type="text/event-stream")

    vis = "all" if user.role == Role.internal else "generic"
    key = cache_key(user.role.value, body.message, vis)
    cached = await get_cached(key)
    show_cite = user.role == Role.internal

    if cached:
        payload = json.loads(cached)

        async def from_cache():
            yield f"data: {json.dumps({'type': 'token', 'text': payload['answer']})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'refused': False, 'citations': payload.get('citations') if show_cite else []})}\n\n"

        return StreamingResponse(from_cache(), media_type="text/event-stream")

    context, citations = await retrieve(body.message, user.role)
    cite_payload = [c.model_dump(mode="json") for c in citations] if show_cite else []
    system = SYSTEM_INTERNAL if user.role == Role.internal else SYSTEM_EXTERNAL
    prompt = f"Context:\n{context or '(no matching documents)'}\n\nQuestion: {body.message}\nAnswer:"

    async def stream():
        parts: list[str] = []
        async for token in generate_stream(prompt, system):
            parts.append(token)
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        answer = scrub_output("".join(parts), user.role)
        await set_cached(key, json.dumps({"answer": answer, "citations": cite_payload}))
        yield f"data: {json.dumps({'type': 'done', 'refused': False, 'citations': cite_payload})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
