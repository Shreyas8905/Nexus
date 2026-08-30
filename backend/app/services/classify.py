from __future__ import annotations

import re

from app.models import Visibility
from app.services.parse import ParsedBlock

EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{3,5}[-.\s]?){2,4}\d{2,4}\b")
ROLL = re.compile(r"\b(?:roll|reg(?:istration)?|enrollment|student\s*id)[^\n]{0,40}\d{3,}\b", re.I)
GRADE = re.compile(r"\b(?:gpa|cgpa|marks?|percentage|grade)\b", re.I)
PII_SHEETS = re.compile(r"result|marks|attendance|salary|personal|student", re.I)


def classify_blocks(blocks: list[ParsedBlock], filename: str) -> Visibility:
    blob = filename + "\n" + "\n".join(b.text for b in blocks[:80])
    pii_hits = 0
    if EMAIL.search(blob):
        pii_hits += 2
    if PHONE.search(blob):
        pii_hits += 1
    if ROLL.search(blob):
        pii_hits += 3
    if GRADE.search(blob) and (ROLL.search(blob) or "student" in blob.lower()):
        pii_hits += 3
    if any(PII_SHEETS.search(b.sheet or "") for b in blocks):
        pii_hits += 2
    if PII_SHEETS.search(filename):
        pii_hits += 2
    if pii_hits >= 4:
        return Visibility.restricted_pii
    if pii_hits >= 1:
        return Visibility.internal
    return Visibility.generic
