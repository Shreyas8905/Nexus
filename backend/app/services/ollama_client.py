from __future__ import annotations

import base64
from typing import AsyncIterator

import httpx

from app.config import get_settings

settings = get_settings()


class OllamaError(RuntimeError):
    pass


async def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            r = await client.post(
                f"{settings.ollama_url}/api/embeddings",
                json={"model": settings.ollama_embed_model, "prompt": text[:8000]},
            )
            if r.status_code >= 400:
                raise OllamaError(r.text)
            vectors.append(r.json()["embedding"])
    return vectors


async def generate(prompt: str, system: str, json_mode: bool = False) -> str:
    payload = {
        "model": settings.ollama_llm_model,
        "stream": False,
        "prompt": prompt,
        "system": system,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }
    if json_mode:
        payload["format"] = "json"
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        if r.status_code >= 400:
            raise OllamaError(r.text)
        return r.json().get("response", "")


async def generate_stream(prompt: str, system: str) -> AsyncIterator[str]:
    payload = {
        "model": settings.ollama_llm_model,
        "stream": True,
        "prompt": prompt,
        "system": system,
        "options": {"temperature": 0.2, "num_ctx": 4096},
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", f"{settings.ollama_url}/api/generate", json=payload) as r:
            async for line in r.aiter_lines():
                if not line:
                    continue
                import json

                data = json.loads(line)
                chunk = data.get("response") or ""
                if chunk:
                    yield chunk
                if data.get("done"):
                    break


async def caption_image(image_bytes: bytes) -> str:
    if not settings.enable_vision:
        return ""
    b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_vision_model,
                "stream": False,
                "prompt": "Describe this figure, chart, or image for a knowledge base. Include axes, trends, and labels if present.",
                "images": [b64],
            },
        )
        if r.status_code >= 400:
            return ""
        return r.json().get("response", "")
