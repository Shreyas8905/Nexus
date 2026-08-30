$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env from .env.example — change JWT_SECRET and passwords before production."
}
docker compose up -d --build
Write-Host "Pulling local models (first run is slow)..."
docker compose exec -T ollama ollama pull nomic-embed-text
docker compose exec -T ollama ollama pull qwen2.5:7b-instruct-q4_K_M
Write-Host "Chat:  http://localhost:8080"
Write-Host "Admin: http://localhost:8081"
