from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import List, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine.url import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    # Database - Defaults to localhost for local dev, overridden by .env or ENV vars in Docker
    database_url: str = "******localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    ollama_url: str = "http://localhost:11434"

    jwt_secret: str = "dev-only-change-me"
    # None -> derive from ENV (Secure everywhere except development).
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    chat_cookie: str = "nexus_chat"
    admin_cookie: str = "nexus_admin"
    csrf_cookie: str = "nexus_csrf"

    admin_bootstrap_email: str = "admin@nexus.local"
    admin_bootstrap_password: str = Field(
        default="ChangeMeNow!",
        validation_alias=AliasChoices("ADMIN_BOOTSTRAP_PASSWORD", "ADMIN_PASSWORD"),
    )

    chat_origin: str = "http://localhost:8080"
    admin_origin: str = "http://localhost:8081"
    api_cors_origins: str = "http://localhost:8080,http://localhost:8081"

    # Comma-separated IPs/CIDRs of reverse proxies allowed to set X-Forwarded-For / X-Real-IP.
    # Empty (default) means forwarded headers are never trusted.
    trusted_proxies: str = ""

    llm_provider: str = "ollama"
    groq_api_key: str | None = None
    groq_llm_model: str = "llama-3.1-70b-versatile"
    gemini_api_key: str | None = None

    ollama_llm_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_vision_model: str = "llava:7b"
    enable_vision: bool = False
    embed_dim: int = 768
    qdrant_collection: str = "nexus_chunks"
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 50

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("trusted_proxies")
    @classmethod
    def _validate_trusted_proxies(cls, value: str) -> str:
        for entry in value.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXIES contains an invalid IP/CIDR: {entry!r}") from exc
        return value

    @property
    def is_development(self) -> bool:
        return self.env.strip().lower() == "development"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else not self.is_development

    @model_validator(mode="after")
    def validate_cookie_and_cors_config(self) -> Settings:
        # Credentials (cookies) are always shared cross-origin, so a wildcard origin is never valid.
        if "*" in self.cors_list:
            raise ValueError("API_CORS_ORIGINS must list explicit origins; '*' is not allowed with credentials")
        for origin in self.cors_list:
            parts = urlsplit(origin)
            if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/") or parts.query or parts.fragment:
                raise ValueError(f"API_CORS_ORIGINS entry must be a bare origin like https://host: {origin!r}")

        if self.cookie_samesite == "none" and not self.cookie_secure_effective:
            raise ValueError("COOKIE_SAMESITE=none requires secure cookies (COOKIE_SECURE=true)")

        if not self.is_development:
            if not self.cookie_secure_effective:
                raise ValueError("COOKIE_SECURE must not be disabled outside development")
            if not self.cors_list:
                raise ValueError("API_CORS_ORIGINS must be set outside development")
            insecure = [o for o in self.cors_list if urlsplit(o).scheme != "https"]
            if insecure:
                raise ValueError(f"API_CORS_ORIGINS must use https outside development: {insecure}")
        return self

    @model_validator(mode="after")
    def validate_secure_non_dev_config(self) -> Settings:
        if self.is_development:
            return self

        insecure_values = {
            "",
            "secret",
            "admin",
            "password",
            "change_me",
            "change-me",
            "changeme",
            "dev-only-change-me",
            "replace-with-64-char-random-string",
            "changemenow!",
            "change-this-db-password",
        }

        if self.jwt_secret.strip().lower() in insecure_values:
            raise ValueError("JWT_SECRET must be explicitly set to a secure value outside development")

        if self.admin_bootstrap_password.strip().lower() in insecure_values:
            raise ValueError("ADMIN_PASSWORD/ADMIN_BOOTSTRAP_PASSWORD must be secure outside development")

        try:
            db_url = make_url(self.database_url)
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL outside development") from exc
        db_password = (db_url.password or "").strip().lower()
        if (
            self.database_url == Settings.model_fields["database_url"].default
            or not db_url.username
            or not db_url.password
            or db_password in insecure_values
        ):
            raise ValueError("DATABASE_URL must include non-default credentials outside development")

        return self

    @property
    def cors_list(self) -> List[str]:
        return [o.strip().rstrip("/") for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        return tuple(
            ipaddress.ip_network(e.strip(), strict=False) for e in self.trusted_proxies.split(",") if e.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
