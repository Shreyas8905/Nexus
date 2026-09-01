# Docker Deployment Guide (Fully Local)

This guide provides instructions for deploying Project Nexus as a completely self-hosted, on-premise system. In this configuration, all AI capabilities (Chat, Embeddings, and Vision) are handled locally by Ollama, removing all dependencies on external cloud APIs.

## Architecture Overview
The system is deployed as a set of microservices:
- `api`: FastAPI backend handling requests.
- `worker`: Background process for document ingestion and embedding.
- `postgres`: Relational database for users and document metadata.
- `redis`: Message queue for ingestion tasks and session caching.
- `qdrant`: Vector database for semantic search.
- `ollama`: Local LLM engine for ALL AI tasks.
- `chat`: Next.js user interface.
- `admin`: Next.js administrative control plane.
- `caddy`: Reverse proxy and API gateway.

## Deployment Steps

### 1. Environment Configuration
Create a `.env` file in the root directory. For a fully local deployment, use the following settings:

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

# LLM Configuration (Fully Local)
LLM_PROVIDER=ollama
OLLAMA_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_VISION_MODEL=llava:7b

# Security
JWT_SECRET=your_long_random_secret
```

### 2. Launching the Stack

### GPU Deployment (Recommended)
For production-grade performance, use the GPU override file. This requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed on the host.

Run the following command to start the services with GPU acceleration:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### CPU Deployment (Fallback)
If no NVIDIA GPU is available, you can run the system in CPU-only mode (note: generation will be significantly slower):

```bash
docker compose up -d
```

### 3. Initializing Local Models
The `ollama` container starts without any models. You must pull the required models manually for the system to function. Run these commands in your terminal:

**For Embeddings (Required for Ingestion):**
```bash
docker exec -it nexus-ollama-1 ollama pull nomic-embed-text
```

**For Chat Generation (Required for Chat):**
```bash
docker exec -it nexus-ollama-1 ollama pull qwen2.5:7b-instruct-q4_K_M
```

**For Vision (Optional):**
```bash
docker exec -it nexus-ollama-1 ollama pull llava:7b
```

## Accessing the Application
Once the stack is healthy and models are pulled, the services are available via the Caddy proxy:
- **Chat Interface**: `http://localhost:8080`
- **Admin Panel**: `http://localhost:8081`

## Production Hardening
For production environments, it is recommended to:
1. **Volume Backups**: Regularly backup the `postgres_data` and `qdrant_data` volumes.
2. **Hardware Acceleration**: To improve performance, ensure the Docker host has an NVIDIA GPU and that the `ollama` container is configured to use it (via `--gpus all` or the NVIDIA Container Toolkit).
3. **HTTPS**: Configure Caddy with a real domain and SSL certificates.
4. **Network Isolation**: Keep the `nexus_internal` network internal and only expose Caddy to the public.
