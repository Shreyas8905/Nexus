"""LLM provider client (Groq, Ollama, Gemini).

Every external model call goes through this module, which provides:

* Structured logging: one JSON log line per attempt on the ``nexus.llm``
  logger with ``provider``, ``model``, ``latency_ms``, token counts and error
  type. Prompts, system prompts, completions and API keys are never logged.
* Explicit timeouts on every provider HTTP call (configured in ``config.py``).
* Error classification into typed ``LLMError`` subclasses (rate limit, timeout,
  context window, unavailable, auth, bad request).
* Retries with exponential backoff for transient errors, then fallback routing
  to the next model in the chain (Groq primary -> Groq fallback models ->
  local Ollama).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

import google.generativeai as genai
import groq
import httpx
from groq import AsyncGroq

from app.config import get_settings

settings = get_settings()
log = logging.getLogger("nexus.llm")

VISION_PROMPT = (
    "Describe this figure, chart, or image for a knowledge base. "
    "Include axes, trends, and labels if present."
)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class LLMError(RuntimeError):
    """Base error for every LLM failure. Existing callers keep catching this."""

    error_type = "unknown"
    retryable = False  # retry the same model after a backoff
    fallback = True  # moving on to the next model in the chain may help


class LLMRateLimitError(LLMError):
    error_type = "rate_limit"
    retryable = True


class LLMTimeoutError(LLMError):
    error_type = "timeout"
    retryable = True


class LLMUnavailableError(LLMError):
    error_type = "unavailable"
    retryable = True


class LLMContextLengthError(LLMError):
    error_type = "context_length"


class LLMAuthError(LLMError):
    error_type = "auth"


class LLMBadRequestError(LLMError):
    error_type = "bad_request"
    fallback = False  # the request itself is wrong; another model will not fix it


_CONTEXT_HINTS = (
    "context length",
    "context_length",
    "context window",
    "maximum context",
    "too many tokens",
)
_SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),  # Groq keys
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google keys
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key[\"'=:\s]+)[A-Za-z0-9._\-]{8,}"),
]


def _redact(text: str, limit: int = 300) -> str:
    """Strip anything that looks like a credential and cap the length."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text[:limit]


def _from_status(status: int, message: str) -> LLMError:
    if any(hint in message.lower() for hint in _CONTEXT_HINTS):
        return LLMContextLengthError(message)
    if status == 429:
        return LLMRateLimitError(message)
    if status in (401, 403):
        return LLMAuthError(message)
    if status in (408, 504):
        return LLMTimeoutError(message)
    if status >= 500 or status == 404:  # 404: model not pulled / decommissioned
        return LLMUnavailableError(message)
    return LLMBadRequestError(message)


def classify_error(exc: BaseException) -> LLMError:
    """Map provider/transport exceptions onto typed ``LLMError`` subclasses."""
    if isinstance(exc, LLMError):
        return exc
    message = _redact(str(exc) or type(exc).__name__)

    if any(hint in message.lower() for hint in _CONTEXT_HINTS):
        return LLMContextLengthError(message)
    if isinstance(exc, (groq.APITimeoutError, httpx.TimeoutException, asyncio.TimeoutError)):
        return LLMTimeoutError(message)
    if isinstance(exc, (groq.APIConnectionError, httpx.TransportError)):
        return LLMUnavailableError(message)
    if isinstance(exc, groq.APIStatusError):
        return _from_status(exc.status_code, message)
    return LLMError(message)


# --------------------------------------------------------------------------- #
# Logging / plumbing
# --------------------------------------------------------------------------- #
def _log_event(level: int, event: str, **context: Any) -> None:
    """Emit one structured (JSON) log line. Never pass prompts or keys here."""
    payload = {"event": event, **{k: v for k, v in context.items() if v is not None}}
    log.log(level, json.dumps(payload, default=str), extra={"llm": payload})


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.llm_timeout_seconds, connect=settings.llm_connect_timeout_seconds)


def _http_client() -> httpx.AsyncClient:
    """Single factory for outbound HTTP clients (patched in tests)."""
    return httpx.AsyncClient(timeout=_timeout())


def _groq_client() -> AsyncGroq:
    # Passing our own httpx client keeps the timeout explicit and avoids the
    # groq<0.13 + httpx>=0.28 "unexpected keyword argument 'proxies'" crash.
    # max_retries=0 because retries are handled (and logged) in this module.
    return AsyncGroq(
        api_key=settings.groq_api_key,
        timeout=_timeout(),
        max_retries=0,
        http_client=_http_client(),
    )


async def _sleep(seconds: float) -> None:  # patched in tests
    await asyncio.sleep(seconds)


def _backoff(attempt: int) -> float:
    return settings.llm_retry_backoff_seconds * (2 ** (attempt - 1))


@dataclass(frozen=True)
class Target:
    provider: str  # "groq" | "ollama" | "gemini"
    model: str


def _model_chain() -> list[Target]:
    """Ordered list of text models to try: primary first, then fallbacks."""
    chain: list[Target] = []
    if settings.llm_provider == "groq":
        if settings.groq_api_key:
            chain.append(Target("groq", settings.groq_llm_model))
            for model in settings.groq_fallback_model_list:
                if Target("groq", model) not in chain:
                    chain.append(Target("groq", model))
        else:
            _log_event(logging.WARNING, "llm.config", provider="groq", detail="GROQ_API_KEY not configured")
        if settings.llm_fallback_to_ollama or not chain:
            chain.append(Target("ollama", settings.ollama_llm_model))
    else:
        chain.append(Target("ollama", settings.ollama_llm_model))
    return chain


def _log_fallback(operation: str, current: Target, nxt: Target, err: LLMError) -> None:
    _log_event(
        logging.WARNING,
        "llm.fallback",
        operation=operation,
        from_provider=current.provider,
        from_model=current.model,
        to_provider=nxt.provider,
        to_model=nxt.model,
        error_type=err.error_type,
    )


async def _with_retries(
    target: Target,
    operation: str,
    call: Callable[[], Awaitable[tuple[Any, dict[str, Any]]]],
) -> Any:
    """Run ``call`` with exponential backoff on retryable errors."""
    attempts = settings.llm_max_retries + 1
    for attempt in range(1, attempts + 1):
        start = time.perf_counter()
        try:
            result, usage = await call()
        except Exception as exc:  # noqa: BLE001 - classified below
            err = classify_error(exc)
            will_retry = err.retryable and attempt < attempts
            _log_event(
                logging.WARNING,
                "llm.request.failed",
                operation=operation,
                provider=target.provider,
                model=target.model,
                attempt=attempt,
                latency_ms=_elapsed_ms(start),
                error_type=err.error_type,
                error=str(err),
                will_retry=will_retry,
            )
            if not will_retry:
                raise err from exc
            await _sleep(_backoff(attempt))
            continue
        _log_event(
            logging.INFO,
            "llm.request.completed",
            operation=operation,
            provider=target.provider,
            model=target.model,
            attempt=attempt,
            latency_ms=_elapsed_ms(start),
            **usage,
        )
        return result
    raise LLMError("retry loop exited unexpectedly")  # pragma: no cover


def _ollama_usage(data: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    total = None
    if prompt_tokens is not None or completion_tokens is not None:
        total = (prompt_tokens or 0) + (completion_tokens or 0)
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "tokens": total}


def _groq_usage(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "tokens": getattr(usage, "total_tokens", None),
    }


async def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code >= 400:
        body = (await r.aread()).decode(errors="replace")
        raise _from_status(r.status_code, _redact(body or f"HTTP {r.status_code}"))


def _raise_for_ollama_error(data: dict[str, Any]) -> None:
    if data.get("error"):
        raise _from_status(500, _redact(str(data["error"])))


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using local Ollama (retries on transient errors)."""
    target = Target("ollama", settings.ollama_embed_model)
    vectors: list[list[float]] = []
    async with _http_client() as client:
        for text in texts:

            async def call(text: str = text) -> tuple[list[float], dict[str, Any]]:
                r = await client.post(
                    f"{settings.ollama_url}/api/embeddings",
                    json={"model": target.model, "prompt": text[:8000]},
                )
                await _raise_for_status(r)
                data = r.json()
                _raise_for_ollama_error(data)
                return data["embedding"], {"input_chars": len(text)}

            try:
                vectors.append(await _with_retries(target, "embed", call))
            except LLMError as err:
                raise type(err)(
                    f"Local embedding failed: {err}. Ensure Ollama is running and model "
                    f"{target.model} is pulled."
                ) from err
    return vectors


# --------------------------------------------------------------------------- #
# Text generation
# --------------------------------------------------------------------------- #
async def _groq_generate(model: str, prompt: str, system: str, json_mode: bool) -> tuple[str, dict[str, Any]]:
    client = _groq_client()
    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"} if json_mode else None,
        )
        return completion.choices[0].message.content or "", _groq_usage(getattr(completion, "usage", None))
    finally:
        await client.close()


async def _ollama_generate(model: str, prompt: str, system: str, json_mode: bool) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "prompt": prompt,
        "system": system,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }
    if json_mode:
        payload["format"] = "json"
    async with _http_client() as client:
        r = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        await _raise_for_status(r)
        data = r.json()
        _raise_for_ollama_error(data)
        return data.get("response", ""), _ollama_usage(data)


async def generate(prompt: str, system: str, json_mode: bool = False) -> str:
    """Generate a completion, falling back along the model chain on failure."""
    chain = _model_chain()
    last_error: LLMError = LLMError("no LLM provider configured")
    for index, target in enumerate(chain):
        impl = _groq_generate if target.provider == "groq" else _ollama_generate

        async def call(target: Target = target, impl=impl) -> tuple[str, dict[str, Any]]:
            return await impl(target.model, prompt, system, json_mode)

        try:
            return await _with_retries(target, "generate", call)
        except LLMError as err:
            last_error = err
            if not err.fallback or index == len(chain) - 1:
                break
            _log_fallback("generate", target, chain[index + 1], err)
    _log_event(logging.ERROR, "llm.exhausted", operation="generate", error_type=last_error.error_type)
    raise last_error


async def _groq_stream(model: str, prompt: str, system: str) -> AsyncIterator[str]:
    client = _groq_client()
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0.2,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content
    finally:
        await client.close()


async def _ollama_stream(model: str, prompt: str, system: str) -> AsyncIterator[str]:
    payload = {
        "model": model,
        "stream": True,
        "prompt": prompt,
        "system": system,
        "options": {"temperature": 0.2, "num_ctx": 4096},
    }
    async with _http_client() as client:
        async with client.stream("POST", f"{settings.ollama_url}/api/generate", json=payload) as r:
            await _raise_for_status(r)
            async for line in r.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                _raise_for_ollama_error(data)
                chunk = data.get("response") or ""
                if chunk:
                    yield chunk
                if data.get("done"):
                    break


async def generate_stream(prompt: str, system: str) -> AsyncIterator[str]:
    """Stream tokens, with retry + fallback while no token has been sent yet.

    Once the first token has reached the caller the answer cannot be restarted
    on another model, so a mid-stream failure is logged and raised.
    """
    chain = _model_chain()
    last_error: LLMError = LLMError("no LLM provider configured")
    attempts = settings.llm_max_retries + 1
    for index, target in enumerate(chain):
        stream_impl = _groq_stream if target.provider == "groq" else _ollama_stream
        for attempt in range(1, attempts + 1):
            start = time.perf_counter()
            tokens = 0
            first_token_ms: int | None = None
            try:
                async for token in stream_impl(target.model, prompt, system):
                    if first_token_ms is None:
                        first_token_ms = _elapsed_ms(start)
                    tokens += 1
                    yield token
            except Exception as exc:  # noqa: BLE001 - classified below
                err = classify_error(exc)
                started = tokens > 0
                will_retry = err.retryable and not started and attempt < attempts
                _log_event(
                    logging.WARNING,
                    "llm.request.failed",
                    operation="stream",
                    provider=target.provider,
                    model=target.model,
                    attempt=attempt,
                    latency_ms=_elapsed_ms(start),
                    chunks=tokens,
                    error_type=err.error_type,
                    error=str(err),
                    mid_stream=started,
                    will_retry=will_retry,
                )
                if started:
                    raise err from exc
                last_error = err
                if will_retry:
                    await _sleep(_backoff(attempt))
                    continue
                break
            else:
                _log_event(
                    logging.INFO,
                    "llm.request.completed",
                    operation="stream",
                    provider=target.provider,
                    model=target.model,
                    attempt=attempt,
                    latency_ms=_elapsed_ms(start),
                    first_token_ms=first_token_ms,
                    chunks=tokens,
                )
                return
        if not last_error.fallback or index == len(chain) - 1:
            break
        _log_fallback("stream", target, chain[index + 1], last_error)
    _log_event(logging.ERROR, "llm.exhausted", operation="stream", error_type=last_error.error_type)
    raise last_error


# --------------------------------------------------------------------------- #
# Vision
# --------------------------------------------------------------------------- #
async def _gemini_caption(image_bytes: bytes) -> tuple[str, dict[str, Any]]:
    def _call() -> str:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_vision_model)
        response = model.generate_content(
            [VISION_PROMPT, {"mime_type": "image/png", "data": image_bytes}],
            request_options={"timeout": settings.llm_timeout_seconds},
        )
        return response.text or ""

    # The Gemini SDK is synchronous: run it off the event loop and bound it.
    text = await asyncio.wait_for(asyncio.to_thread(_call), timeout=settings.llm_timeout_seconds)
    return text, {"image_bytes": len(image_bytes)}


async def _ollama_caption(image_bytes: bytes) -> tuple[str, dict[str, Any]]:
    async with _http_client() as client:
        r = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_vision_model,
                "stream": False,
                "prompt": VISION_PROMPT,
                "images": [base64.b64encode(image_bytes).decode()],
            },
        )
        await _raise_for_status(r)
        data = r.json()
        _raise_for_ollama_error(data)
        return data.get("response", ""), {**_ollama_usage(data), "image_bytes": len(image_bytes)}


async def caption_image(image_bytes: bytes) -> str:
    """Caption an image: Gemini first (if configured), Ollama vision as fallback.

    Captions are best-effort enrichment for ingestion, so failures are logged
    and an empty string is returned instead of failing the whole document.
    """
    if not settings.enable_vision:
        return ""

    chain: list[tuple[Target, Callable[[], Awaitable[tuple[str, dict[str, Any]]]]]] = []
    if settings.gemini_api_key:
        chain.append((Target("gemini", settings.gemini_vision_model), lambda: _gemini_caption(image_bytes)))
    chain.append((Target("ollama", settings.ollama_vision_model), lambda: _ollama_caption(image_bytes)))

    for index, (target, call) in enumerate(chain):
        try:
            return await _with_retries(target, "caption", call)
        except LLMError as err:
            if index < len(chain) - 1:
                _log_fallback("caption", target, chain[index + 1][0], err)
    _log_event(logging.ERROR, "llm.exhausted", operation="caption", detail="returning empty caption")
    return ""
