from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field, model_validator
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
    cookie_secure: bool = False
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

    @model_validator(mode="after")
    def validate_secure_non_dev_config(self) -> Settings:
        if self.env.lower() == "development":
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
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
