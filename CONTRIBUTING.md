# Contributing to Project Nexus

Thank you for your interest in contributing to Project Nexus! This project is a collaborative effort for the Department of AI & ML, DSCE.

## 🛠️ Developer Setup

### Backend Developers
The backend is built with FastAPI and focuses on the RAG pipeline.

#### Running the Backend
1. **Environment**: Use a Python 3.10+ virtual environment.
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   .venv\Scripts\activate     # Windows
   ```
2. **Install**: `pip install -r requirements.txt`
3. **Configure**: Copy `.env.example` to `.env` and fill in your API keys.
4. **Launch**: `uvicorn app.main:app --reload --port 8000`
5. **Worker**: Don't forget to run the worker in a separate terminal: `python -m app.worker`

#### Core Backend Areas
- `app/services/llm_client.py`: Where the LLM provider logic lives.
- `app/services/retrieve.py`: Logic for semantic search and reranking.
- `app/services/ingest.py`: The document processing pipeline.

---

### Frontend Developers
The frontends are built with Next.js (App Router).

#### Running the Frontends
1. **Install**: `npm install` in both `apps/chat` and `apps/admin`.
2. **Launch**: `npm run dev`
3. **Proxy**: Ensure the backend is running at `localhost:8000`. The `next.config.js` rewrites handle the `/api` proxying.

#### Core Frontend Areas
- `apps/chat/app/page.js`: The main chat interface and streaming logic.
- `apps/admin/app/page.js`: The document management and user control panel.

## 📜 Contribution Guidelines

### 1. Feature Requests
Please open an issue describing the feature and how it benefits the DSCE AI & ML department.

### 2. Code Standards
- **Python**: Follow PEP 8. Use type hints for all function signatures.
- **JavaScript**: Use functional React components and Tailwind CSS for styling.
- **Git**: Use descriptive commit messages (e.g., `feat: add groq support`, `fix: resolve embedding 404`).

### 3. Testing
Before submitting a PR:
- Verify that the `/health` endpoint returns `{"ok": True}`.
- Ensure that document ingestion completes without errors in the worker logs.
- Verify that citations are correctly rendered in the chat UI.

## 🤝 Support
For architectural questions, please refer to the `README.md` or contact the lead maintainers of the AI & ML Department.
