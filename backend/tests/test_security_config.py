import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.middleware import SecurityHeadersMiddleware

PROD = dict(
    env="production",
    jwt_secret="x" * 64,
    ADMIN_BOOTSTRAP_PASSWORD="Str0ng-Unique-Passw0rd",
    database_url="postgresql+asyncpg://nexus:s3cretpw@db:5432/nexus",
    api_cors_origins="https://chat.example.com,https://admin.example.com",
)


def s(**kw):
    return Settings(_env_file=None, **{**PROD, **kw})


def test_prod_baseline_ok_and_cookies_secure_by_default():
    cfg = s()
    assert cfg.cookie_secure_effective is True and cfg.cookie_samesite == "lax"


def test_dev_cookies_not_secure_by_default():
    assert Settings(_env_file=None, env="development").cookie_secure_effective is False


@pytest.mark.parametrize("env", ["development", "production"])
def test_wildcard_cors_rejected_everywhere(env):
    base = PROD if env == "production" else {"env": env}
    with pytest.raises(ValidationError, match="not allowed with credentials"):
        Settings(_env_file=None, **{**base, "api_cors_origins": "*"})
    with pytest.raises(ValidationError, match="not allowed with credentials"):
        Settings(_env_file=None, **{**base, "api_cors_origins": "https://a.example.com, *"})


def test_prod_requires_https_origins_and_secure_cookies():
    with pytest.raises(ValidationError, match="https"):
        s(api_cors_origins="http://chat.example.com")
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        s(cookie_secure=False)
    with pytest.raises(ValidationError, match="must be set"):
        s(api_cors_origins="")


def test_origin_must_be_bare():
    with pytest.raises(ValidationError, match="bare origin"):
        s(api_cors_origins="https://chat.example.com/app")
    assert s(api_cors_origins="https://chat.example.com/").cors_list == ["https://chat.example.com"]


def test_samesite_values():
    assert s(cookie_samesite="STRICT").cookie_samesite == "strict"
    with pytest.raises(ValidationError):
        s(cookie_samesite="bogus")
    with pytest.raises(ValidationError, match="requires secure"):
        Settings(_env_file=None, env="development", cookie_samesite="none")
    assert Settings(_env_file=None, env="development", cookie_samesite="none", cookie_secure=True)


def test_trusted_proxies_validated():
    assert len(s(trusted_proxies="10.0.0.0/8, 127.0.0.1").trusted_proxy_networks) == 2
    with pytest.raises(ValidationError, match="TRUSTED_PROXIES"):
        s(trusted_proxies="not-an-ip")


def test_session_cookie_attributes(monkeypatch):
    import app.security as sec

    monkeypatch.setattr(sec, "settings", s(cookie_samesite="strict"))
    resp = Response()
    sec.set_session_cookies(resp, "tok", "csrf", "chat")
    sec.clear_session(resp, "chat")
    cookies = [v.decode() for k, v in resp.raw_headers if k == b"set-cookie"]
    session, csrf, del_session, del_csrf = cookies
    for c in cookies:
        assert "Secure" in c and "SameSite=strict" in c and "Path=/" in c
    assert "HttpOnly" in session and "HttpOnly" not in csrf
    assert "Max-Age=0" in del_session and "Max-Age=0" in del_csrf


def _client(**kw):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, **kw)

    @app.get("/x")
    def x():
        return {"ok": 1}

    @app.get("/cached")
    def cached(response: Response):
        response.headers["Cache-Control"] = "max-age=5"
        return {}

    return TestClient(app)


def test_security_headers_present():
    r = _client(hsts=True).get("/x")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    assert r.headers["cache-control"] == "no-store"
    assert _client().get("/x").headers.get("strict-transport-security") is None
    assert _client().get("/cached").headers["cache-control"] == "max-age=5"


def test_main_wires_middleware_and_rejects_wildcard():
    import app.main as main

    assert any(m.cls is SecurityHeadersMiddleware for m in main.app.user_middleware)
    with pytest.raises(RuntimeError):
        main._validated_cors_origins(["*"], allow_credentials=True)
    r = TestClient(main.app).get("/health")
    assert r.status_code == 200 and r.headers["x-frame-options"] == "DENY"
