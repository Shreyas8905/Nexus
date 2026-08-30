from __future__ import annotations

import json
import re
from typing import Literal

from app.models import Role, Visibility
from app.services.ollama_client import generate

Decision = Literal["allow", "refuse"]

PII_INTENT = re.compile(
    r"\b("
    r"student\s+(record|marks|grade|result|phone|email|address|roll)|"
    r"roll\s*no|enrollment|"
    r"faculty\s+(phone|email|salary|address|personal)|"
    r"whose\s+marks|who\s+scored|"
    r"personal\s+detail"
    r")\b",
    re.I,
)
SAFE_GENERIC = re.compile(
    r"\b(policy|policies|achievement|awards?|curriculum|syllabus|admission|overview|statistics|aggregate)\b",
    re.I,
)

REFUSAL = (
    "I cannot share individual student records or faculty personal details "
    "(other than public achievements). Ask about general policies, aggregates, or published achievements instead."
)

OUTPUT_PII = [
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{10})\b"),
    re.compile(r"\broll\s*(?:no|number|#)?\s*[:\-]?\s*\w+\b", re.I),
]


def allowed_visibilities(role: Role) -> list[Visibility]:
    if role in (Role.admin, Role.internal):
        return [Visibility.generic, Visibility.internal, Visibility.restricted_pii]
    return [Visibility.generic]


async def input_guard(message: str, role: Role) -> tuple[Decision, str]:
    if role != Role.external:
        return "allow", ""
    if PII_INTENT.search(message) and not SAFE_GENERIC.search(message):
        return "refuse", REFUSAL
    system = (
        "You are a policy classifier for a university knowledge base. "
        "External users may only receive generic/public information. "
        "Refuse requests for individual student records or faculty personal details "
        "other than public achievements. Respond JSON {\"decision\":\"allow\"|\"refuse\",\"reason\":\"...\"}."
    )
    try:
        raw = await generate(message, system, json_mode=True)
        data = json.loads(raw)
        if str(data.get("decision", "")).lower() == "refuse":
            return "refuse", REFUSAL
    except Exception:
        if PII_INTENT.search(message):
            return "refuse", REFUSAL
    return "allow", ""


def scrub_output(text: str, role: Role) -> str:
    if role != Role.external:
        return text
    cleaned = text
    for pat in OUTPUT_PII:
        cleaned = pat.sub("[redacted]", cleaned)
    return cleaned
