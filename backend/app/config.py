"""
Application Configuration Module

This file provides fallback configuration defaults for local development.
For actual API endpoints, database credentials, and secret keys, all settings 
MUST be defined in the local `.env` file (see `.env.example`).
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory pointing to project root where .env resides
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_env: str = "development"

    # Core Secrets & Auth Defaults (Fallback placeholders; override in .env)
    jwt_secret: str = "placeholder-jwt-secret-override-in-env"
    cookie_secure: bool = False
    chat_cookie: str = "nexus_chat"
    admin_cookie: str = "nexus_admin"
    csrf_cookie: str = "nexus_csrf"

    # Admin Bootstrap Defaults
    admin_bootstrap_email: str = "admin@nexus.local"
    admin_bootstrap_password: str = "placeholder-admin-password-override-in-env"

    # CORS & Service Endpoints (Fallback URLs; override in .env for actual routing)
    chat_origin: str = "http://127.0.0.1:8080"
    admin_origin: str = "http://127.0.0.1:8081"
    api_cors_origins: str = "http://127.0.0.1:8080,http://127.0.0.1:8081"

    # Database & Vector Store Routes (Dummy connection paths; real paths load from .env)
    database_url: str = "postgresql+asyncpg://user:pass@127.0.0.1:5432/nexus_fallback"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "nexus_documents"

    # Ollama AI Model Services
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_vision_model: str = "llava:7b"
    enable_vision: bool = False
    embed_dim: int = 768

    # Upload Settings
    upload_dir: str = "./uploads"
    max_upload_mb: int = 50

    # Force Pydantic to read configuration directly from .env located at BASE_DIR
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    """Instantiates settings, forcing environmental resolution from .env file."""
    return Settings()