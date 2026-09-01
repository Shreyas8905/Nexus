# Docker Deployment Guide

This guide provides instructions for deploying Project Nexus using Docker Compose. This is the recommended method for on-premise production deployment.

## Architecture Overview
The system is deployed as a set of microservices:
- `api`: FastAPI backend handling requests.
- `worker`: Background process for document ingestion and embedding.
- `postgres`: Relational database for users and document metadata.
- `redis`: Message queue for ingestion tasks and session caching.
- `qdrant`: Vector database for semantic search.
- `ollama`: Local LLM engine for embeddings and vision.
- `chat`: Next.js user interface.
- `admin`: Next.js administrative control plane.
- `caddy`: Reverse proxy and API gateway.

## Deployment Steps

### 1. Environment Configuration
Create a `.env` file in the root directory:

```env
# Database
POSTGRES_USER=nexus
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=nexus

# Backend
DATABASE_URL=postgresql+asyncpg://nexus:your_secure_password@postgres:5432/nexus
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
OLLAMA_URL=http://ollama:11434

# LLM Settings
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_LLM_MODEL=llama-3.1-70b-versatile
GEMINI_API_KEY=your_gemini_api_key

# Security
JWT_SECRET=your_long_random_secret
```

### 2. Launching the Stack
Run the following command to start all services in the background:

```bash
docker compose up -d
```

### 3. Initializing the Embedding Model
The `ollama` container starts empty. You must pull the required embedding model:

```bash
docker exec -it nexus-ollama-1 ollama pull nomic-embed-text
```

## Accessing the Application
Once the stack is healthy, the services are available via the Caddy proxy:
- **Chat Interface**: `http://localhost:8080`
- **Admin Panel**: `http://localhost:8081`

## Production Hardening
For production environments, it is recommended to:
1. **Volume Backups**: Regularly backup the `postgres_data` and `qdrant_data` volumes.
2. **Resource Limits**: Set CPU and Memory limits in `docker-compose.yml` to prevent the LLM worker from consuming all host resources.
3. **HTTPS**: Configure Caddy with a real domain and SSL certificates (Caddy handles Auto-HTTPS automatically if a public domain is provided).
4. **Network Isolation**: Keep the `nexus_internal` network internal and only expose Caddy to the public.
