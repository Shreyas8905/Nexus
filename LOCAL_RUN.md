# Running Nexus Locally (Without Docker)

This guide describes how to run the Nexus project natively on your system.

## Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Running Services**:
  - Qdrant: `localhost:6333`
  - Postgres: `localhost:5432`
  - Redis: `localhost:6379`

## 1. Backend Setup

### Environment Variables
Create a `.env` file in the `backend/` directory:

```env
# Database
DATABASE_URL=postgresql+asyncpg://nexus:change-this-db-password@localhost:5432/nexus

# Cache & Vector Store
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# LLM Configuration (Free Tier APIs)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_LLM_MODEL=llama-3.1-70b-versatile
GEMINI_API_KEY=your_gemini_api_key_here

# Security & Auth
JWT_SECRET=your-secure-secret
```

### Installation and Execution
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 2. Frontend Setup

### Chat Frontend
```bash
cd apps/chat
npm install
npm run dev
```
The chat app will be available at `http://localhost:3000`.

### Admin Frontend
```bash
cd apps/admin
npm install
npm run dev
```
The admin app will be available at `http://localhost:3001`.

## How it Works
- **API Proxying**: The frontends use Next.js `rewrites` to proxy all `/api` requests to the backend running at `http://localhost:8000`.
- **LLM Provider**: Setting `LLM_PROVIDER=groq` in the backend `.env` switches the text generation to Groq API.
- **Embeddings & Vision**: These now use the Google Gemini API (`GEMINI_API_KEY`), removing the need for a local Ollama instance.
