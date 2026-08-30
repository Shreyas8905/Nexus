#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — change JWT_SECRET and passwords before production."
fi
docker compose up -d --build
echo "Pulling local models (first run is slow)..."
docker compose exec -T ollama ollama pull "${OLLAMA_EMBED_MODEL:-nomic-embed-text}" || true
docker compose exec -T ollama ollama pull "${OLLAMA_LLM_MODEL:-qwen2.5:7b-instruct-q4_K_M}" || true
echo "Chat:  http://localhost:8080"
echo "Admin: http://localhost:8081"
