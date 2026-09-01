from __future__ import annotations

import base64
import json
from typing import AsyncIterator

import httpx
from groq import AsyncGroq
import google.generativeai as genai

from app.config import get_settings

settings = get_settings()

class LLMError(RuntimeError):
    pass

async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings using local Ollama.
    This is the stable fallback as API embeddings can be regional/unstable.
    """
    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            try:
                r = await client.post(
                    f"{settings.ollama_url}/api/embeddings",
                    json={"model": settings.ollama_embed_model, "prompt": text[:8000]},
                )
                if r.status_code >= 400:
                    raise LLMError(f"Ollama embedding error: {r.text}")
                vectors.append(r.json()["embedding"])
            except Exception as e:
                raise LLMError(f"Local embedding failed: {str(e)}. Ensure Ollama is running and model {settings.ollama_embed_model} is pulled.")
    return vectors

async def generate(prompt: str, system: str, json_mode: bool = False) -> str:
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise LLMError("Groq API key is not configured")

        client = AsyncGroq(api_key=settings.groq_api_key)
        try:
            chat_completion = await client.chat.completions.create(
                model=settings.groq_llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"} if json_mode else None,
            )
            return chat_completion.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(str(e))
        finally:
            await client.close()
    else:
        # Ollama implementation
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
                raise LLMError(r.text)
            return r.json().get("response", "")

async def generate_stream(prompt: str, system: str) -> AsyncIterator[str]:
    print(f"DEBUG: Starting generate_stream with provider: {settings.llm_provider}")
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise LLMError("Groq API key is not configured")

        print(f"DEBUG: Calling Groq API with model: {settings.groq_llm_model}")
        client = AsyncGroq(api_key=settings.groq_api_key)
        try:
            stream = await client.chat.completions.create(
                model=settings.groq_llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    print(f"DEBUG: Received token: {content}", end="")
                    yield content
            print("\nDEBUG: Stream completed successfully")
        except Exception as e:
            print(f"DEBUG: Groq Stream Error: {str(e)}")
            raise LLMError(str(e))
        finally:
            await client.close()
    else:
        # Ollama implementation
        print(f"DEBUG: Calling Ollama API with model: {settings.ollama_llm_model}")
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
                    data = json.loads(line)
                    chunk = data.get("response") or ""
                    if chunk:
                        print(f"DEBUG: Received token: {chunk}", end="")
                        yield chunk
                    if data.get("done"):
                        break
        print("\nDEBUG: Ollama Stream completed successfully")

async def caption_image(image_bytes: bytes) -> str:
    if not settings.enable_vision:
        return ""

    if not settings.gemini_api_key:
        # Fallback to Ollama if Gemini is not available but vision is enabled
        try:
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
        except Exception:
            return ""

    # Use Gemini for vision
    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Create a Gemini image part
        image_part = {
            "mime_type": "image/png", # Assuming png as most common, usually handled by the source
            "data": image_bytes
        }

        response = model.generate_content([
            "Describe this figure, chart, or image for a knowledge base. Include axes, trends, and labels if present.",
            image_part
        ])
        return response.text or ""
    except Exception:
        return ""
