"""Unit tests for app.services.llm_client (no network: all providers mocked)."""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import groq
import httpx
import pytest

from app.services import llm_client
from app.services.llm_client import (
    LLMAuthError,
    LLMBadRequestError,
    LLMContextLengthError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    classify_error,
)

FAKE_KEY = "gsk_" + "A1b2C3d4" * 6
SECRET_PROMPT = "what is the grade of student 1DS23AI999"
REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


# --------------------------------------------------------------------------- #
# Fixtures / fakes
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    s = llm_client.settings
    monkeypatch.setattr(s, "llm_provider", "ollama")
    monkeypatch.setattr(s, "groq_api_key", None)
    monkeypatch.setattr(s, "groq_llm_model", "primary-70b")
    monkeypatch.setattr(s, "groq_fallback_models", "backup-8b")
    monkeypatch.setattr(s, "llm_fallback_to_ollama", True)
    monkeypatch.setattr(s, "ollama_llm_model", "qwen-local")
    monkeypatch.setattr(s, "ollama_embed_model", "embed-local")
    monkeypatch.setattr(s, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(s, "llm_max_retries", 2)
    monkeypatch.setattr(s, "llm_retry_backoff_seconds", 0.5)
    monkeypatch.setattr(s, "llm_timeout_seconds", 30.0)
    monkeypatch.setattr(s, "llm_connect_timeout_seconds", 5.0)
    monkeypatch.setattr(s, "enable_vision", True)
    monkeypatch.setattr(s, "gemini_api_key", None)
    return s


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(llm_client, "_sleep", fake_sleep)
    return calls


@pytest.fixture
def ollama(monkeypatch):
    """Route all httpx traffic through a scripted MockTransport."""
    state = SimpleNamespace(handler=None, requests=[])

    def dispatch(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        return state.handler(request)

    monkeypatch.setattr(
        llm_client, "_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(dispatch))
    )
    return state


def groq_error(cls, status: int, message: str = "boom"):
    return cls(message, response=httpx.Response(status, request=REQ), body=None)


def completion(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )


class FakeGroq:
    """Stands in for AsyncGroq; ``script`` maps model -> list of outcomes."""

    def __init__(self, script: dict[str, list]):
        self.script = script
        self.calls: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, model, stream=False, **_):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if stream:
            return self._stream(outcome)
        return completion(outcome)

    async def _stream(self, parts):
        for part in parts:
            if isinstance(part, BaseException):
                raise part
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])

    async def close(self):
        pass


@pytest.fixture
def use_groq(monkeypatch, _settings):
    def install(script: dict[str, list]) -> FakeGroq:
        fake = FakeGroq(script)
        monkeypatch.setattr(_settings, "llm_provider", "groq")
        monkeypatch.setattr(_settings, "groq_api_key", FAKE_KEY)
        monkeypatch.setattr(llm_client, "_groq_client", lambda: fake)
        return fake

    return install


def events(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "nexus.llm"]


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.DEBUG, logger="nexus.llm")


# --------------------------------------------------------------------------- #
# Acceptance criterion 1: no print() in llm_client.py
# --------------------------------------------------------------------------- #
def test_no_print_calls_in_llm_client():
    source = Path(llm_client.__file__).read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
    ]
    assert calls == []


# --------------------------------------------------------------------------- #
# Acceptance criterion 2: structured context, no secrets / prompts
# --------------------------------------------------------------------------- #
async def test_success_logs_structured_context(ollama, caplog):
    ollama.handler = lambda req: httpx.Response(
        200, json={"response": "hello", "prompt_eval_count": 20, "eval_count": 5}
    )

    assert await llm_client.generate(SECRET_PROMPT, "system rules") == "hello"

    [event] = events(caplog)
    assert event["event"] == "llm.request.completed"
    assert event["provider"] == "ollama"
    assert event["model"] == "qwen-local"
    assert event["tokens"] == 25
    assert isinstance(event["latency_ms"], int)
    assert caplog.records[0].llm["model"] == "qwen-local"  # also available as a record attribute


async def test_logs_never_contain_prompt_or_api_key(use_groq, ollama, sleeps, caplog):
    use_groq({
        "primary-70b": [groq_error(groq.AuthenticationError, 401, f"Invalid API Key {FAKE_KEY}")],
    })
    ollama.handler = lambda req: httpx.Response(200, json={"response": "ok"})

    await llm_client.generate(SECRET_PROMPT, "system rules")

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in log_text
    assert "[REDACTED]" in log_text
    assert SECRET_PROMPT not in log_text
    assert "system rules" not in log_text


# --------------------------------------------------------------------------- #
# Acceptance criterion 3: timeout + error fallback paths
# --------------------------------------------------------------------------- #
async def test_rate_limit_is_retried_with_exponential_backoff(use_groq, sleeps, caplog):
    fake = use_groq({
        "primary-70b": [
            groq_error(groq.RateLimitError, 429),
            groq_error(groq.RateLimitError, 429),
            "answer",
        ]
    })

    assert await llm_client.generate("q", "s") == "answer"
    assert fake.calls == ["primary-70b"] * 3
    assert sleeps == [0.5, 1.0]
    done = events(caplog)[-1]
    assert done["event"] == "llm.request.completed" and done["attempt"] == 3 and done["tokens"] == 18


async def test_timeout_exhausts_retries_then_falls_back_to_next_groq_model(use_groq, sleeps, caplog):
    fake = use_groq({
        "primary-70b": [groq.APITimeoutError(request=REQ)] * 3,
        "backup-8b": ["from backup"],
    })

    assert await llm_client.generate("q", "s") == "from backup"
    assert fake.calls == ["primary-70b"] * 3 + ["backup-8b"]
    fallback = next(e for e in events(caplog) if e["event"] == "llm.fallback")
    assert fallback["from_model"] == "primary-70b"
    assert fallback["to_model"] == "backup-8b"
    assert fallback["error_type"] == "timeout"


async def test_httpx_timeout_on_ollama_is_retried(ollama, sleeps):
    outcomes = [httpx.ReadTimeout("slow", request=REQ), httpx.Response(200, json={"response": "late"})]

    def handler(req):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    ollama.handler = handler
    assert await llm_client.generate("q", "s") == "late"
    assert sleeps == [0.5]


async def test_auth_error_skips_retries_and_routes_to_ollama(use_groq, ollama, sleeps):
    fake = use_groq({
        "primary-70b": [groq_error(groq.AuthenticationError, 401)],
        "backup-8b": [groq_error(groq.AuthenticationError, 401)],
    })
    ollama.handler = lambda req: httpx.Response(200, json={"response": "local"})

    assert await llm_client.generate("q", "s") == "local"
    assert fake.calls == ["primary-70b", "backup-8b"]
    assert sleeps == []


async def test_context_window_error_falls_back_without_retry(use_groq, sleeps):
    fake = use_groq({
        "primary-70b": [groq_error(groq.BadRequestError, 400, "Please reduce the length: context_length_exceeded")],
        "backup-8b": ["short answer"],
    })

    assert await llm_client.generate("q", "s") == "short answer"
    assert fake.calls == ["primary-70b", "backup-8b"]
    assert sleeps == []


async def test_bad_request_is_not_retried_or_routed(use_groq, ollama, sleeps):
    fake = use_groq({"primary-70b": [groq_error(groq.BadRequestError, 400, "invalid response_format")]})
    ollama.handler = lambda req: pytest.fail("should not fall back on a malformed request")

    with pytest.raises(LLMBadRequestError):
        await llm_client.generate("q", "s")
    assert fake.calls == ["primary-70b"]


async def test_all_providers_failing_raises_typed_error(use_groq, ollama, sleeps, caplog):
    use_groq({
        "primary-70b": [groq_error(groq.InternalServerError, 503)] * 3,
        "backup-8b": [groq_error(groq.InternalServerError, 503)] * 3,
    })
    ollama.handler = lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused", request=req))

    with pytest.raises(LLMUnavailableError) as info:
        await llm_client.generate("q", "s")
    assert isinstance(info.value, LLMError)  # existing `except LLMError` callers still work
    assert events(caplog)[-1]["event"] == "llm.exhausted"


async def test_missing_groq_key_routes_straight_to_ollama(ollama, _settings, monkeypatch):
    monkeypatch.setattr(_settings, "llm_provider", "groq")
    ollama.handler = lambda req: httpx.Response(200, json={"response": "local"})
    assert await llm_client.generate("q", "s") == "local"


async def test_fallback_to_ollama_can_be_disabled(use_groq, ollama, sleeps, _settings, monkeypatch):
    monkeypatch.setattr(_settings, "llm_fallback_to_ollama", False)
    use_groq({
        "primary-70b": [groq_error(groq.AuthenticationError, 401)],
        "backup-8b": [groq_error(groq.AuthenticationError, 401)],
    })
    ollama.handler = lambda req: pytest.fail("ollama fallback is disabled")
    with pytest.raises(LLMAuthError):
        await llm_client.generate("q", "s")


# --------------------------------------------------------------------------- #
# Streaming
# --------------------------------------------------------------------------- #
async def collect(stream) -> list[str]:
    return [token async for token in stream]


async def test_stream_falls_back_before_first_token(use_groq, sleeps, caplog):
    use_groq({
        "primary-70b": [groq_error(groq.RateLimitError, 429)] * 3,
        "backup-8b": [["Hel", "lo"]],
    })

    assert await collect(llm_client.generate_stream("q", "s")) == ["Hel", "lo"]
    done = events(caplog)[-1]
    assert done["event"] == "llm.request.completed" and done["model"] == "backup-8b" and done["chunks"] == 2


async def test_stream_failure_after_tokens_is_raised_not_rerouted(use_groq, sleeps, caplog):
    fake = use_groq({
        "primary-70b": [["partial", groq.APIConnectionError(request=REQ)]],
        "backup-8b": [["should not be used"]],
    })

    received: list[str] = []
    with pytest.raises(LLMUnavailableError):
        async for token in llm_client.generate_stream("q", "s"):
            received.append(token)

    assert received == ["partial"]
    assert fake.calls == ["primary-70b"]
    failed = next(e for e in events(caplog) if e["event"] == "llm.request.failed")
    assert failed["mid_stream"] is True


async def test_ollama_stream_error_status_is_classified(ollama, sleeps):
    ollama.handler = lambda req: httpx.Response(404, json={"error": "model 'qwen-local' not found"})
    with pytest.raises(LLMUnavailableError):
        await collect(llm_client.generate_stream("q", "s"))


async def test_ollama_stream_success(ollama, caplog):
    body = "\n".join(
        json.dumps(x)
        for x in [{"response": "a"}, {"response": "b"}, {"response": "", "done": True}]
    )
    ollama.handler = lambda req: httpx.Response(200, content=body.encode())
    assert await collect(llm_client.generate_stream("q", "s")) == ["a", "b"]
    assert events(caplog)[-1]["first_token_ms"] is not None


# --------------------------------------------------------------------------- #
# Embeddings and vision
# --------------------------------------------------------------------------- #
async def test_embed_retries_transient_connection_errors(ollama, sleeps):
    outcomes = [httpx.ConnectError("refused", request=REQ), httpx.Response(200, json={"embedding": [0.1, 0.2]})]

    def handler(req):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    ollama.handler = handler
    assert await llm_client.embed_texts(["chunk"]) == [[0.1, 0.2]]
    assert sleeps == [0.5]


async def test_embed_missing_model_raises_helpful_error(ollama, sleeps):
    ollama.handler = lambda req: httpx.Response(400, json={"error": "bad input"})
    with pytest.raises(LLMBadRequestError, match="Ensure Ollama is running"):
        await llm_client.embed_texts(["chunk"])


async def test_caption_falls_back_from_gemini_to_ollama(ollama, sleeps, _settings, monkeypatch):
    monkeypatch.setattr(_settings, "gemini_api_key", "AIza" + "x" * 30)

    async def broken_gemini(_bytes):
        raise TimeoutError("gemini deadline exceeded")

    monkeypatch.setattr(llm_client, "_gemini_caption", broken_gemini)
    ollama.handler = lambda req: httpx.Response(200, json={"response": "a bar chart"})

    assert await llm_client.caption_image(b"\x89PNG") == "a bar chart"


async def test_caption_returns_empty_when_every_provider_fails(ollama, sleeps, caplog):
    ollama.handler = lambda req: httpx.Response(500, text="down")
    assert await llm_client.caption_image(b"\x89PNG") == ""
    assert events(caplog)[-1]["event"] == "llm.exhausted"


# --------------------------------------------------------------------------- #
# Timeouts and classification
# --------------------------------------------------------------------------- #
def test_http_clients_use_configured_timeouts():
    client = llm_client._http_client()
    assert client.timeout.read == 30.0 and client.timeout.connect == 5.0


def test_groq_client_builds_with_pinned_httpx(_settings, monkeypatch):
    # Regression: groq==0.11 + httpx==0.28 crashed with "unexpected keyword 'proxies'".
    monkeypatch.setattr(_settings, "groq_api_key", FAKE_KEY)
    client = llm_client._groq_client()
    assert client.max_retries == 0
    assert client.timeout.read == 30.0 and client.timeout.connect == 5.0


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (groq_error(groq.RateLimitError, 429), LLMRateLimitError),
        (groq.APITimeoutError(request=REQ), LLMTimeoutError),
        (groq.APIConnectionError(request=REQ), LLMUnavailableError),
        (groq_error(groq.InternalServerError, 503), LLMUnavailableError),
        (groq_error(groq.AuthenticationError, 401), LLMAuthError),
        (groq_error(groq.BadRequestError, 400, "maximum context length is 8192 tokens"), LLMContextLengthError),
        (groq_error(groq.BadRequestError, 400), LLMBadRequestError),
        (httpx.ReadTimeout("t", request=REQ), LLMTimeoutError),
        (httpx.ConnectError("c", request=REQ), LLMUnavailableError),
        (ValueError("weird"), LLMError),
    ],
)
def test_classify_error(exc, expected):
    assert type(classify_error(exc)) is expected
