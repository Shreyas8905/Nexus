# Running Nexus Locally (Without Docker)

This guide describes how to run the Nexus project natively on your system.

## Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Running Services**:
  - Qdrant: `localhost:6333`
  - Postgres: `localhost:5432`
  - Redis: `localhost:6379`
  - Ollama: `localhost:11434` (Required for embeddings)

## 1. Backend Setup

### Environment Variables
Create a `.env` file in the `backend/` directory:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/nexus_db

# Cache & Vector Store
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# LLM Configuration (Free Tier APIs)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_LLM_MODEL=llama-3.1-70b-versatile
GEMINI_API_KEY=your_gemini_api_key_here

# Ollama (Required for embeddings)
OLLAMA_URL=http://127.0.0.1:11434

# Security & Auth
JWT_SECRET=your-secure-secret
```

### Installation and Execution
1. **Install Dependencies**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
2. **Pull Embedding Model**:
   ```bash
   ollama pull nomic-embed-text
   ```
3. **Start API**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
4. **Start Worker** (In a NEW terminal window):
   ```bash
   cd backend
   python -m app.worker
   ```

## 2. Frontend Setup

### Chat Frontend
```bash
cd apps/chat
npm install
npm run dev
```
Available at: `http://localhost:3000`

### Admin Frontend
```bash
cd apps/admin
npm install
npm run dev
```
Available at: `http://localhost:3001`

## How it Works
- **API Proxying**: The frontends use Next.js `rewrites` to proxy all `/api` requests to the backend running at `http://localhost:8000`.
- **Hybrid LLM Strategy**: 
  - **Generation**: Handled by Groq API for speed and quality.
  - **Vision**: Handled by Google Gemini API.
  - **Embeddings**: Handled by local Ollama for stability and zero-cost.
