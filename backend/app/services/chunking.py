from __future__ import annotations

from dataclasses import dataclass

from app.services.parse import ParsedBlock


@dataclass
class ChunkDraft:
    text: str
    parent_text: str
    page: int | None
    sheet: str | None
    kind: str


def _split_words(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    out: list[str] = []
    i = 0
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        i += max(size - overlap, 1)
    return out


def chunk_blocks(blocks: list[ParsedBlock]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for block in blocks:
        parent = block.text.strip()
        if not parent:
            continue
        if block.kind == "table":
            children = _split_words(parent, 180, 30) or [parent]
        else:
            children = _split_words(parent, 220, 40) or [parent]
        for child in children:
            drafts.append(
                ChunkDraft(
                    text=child,
                    parent_text=parent[:4000],
                    page=block.page,
                    sheet=block.sheet,
                    kind=block.kind,
                )
            )
    return drafts
