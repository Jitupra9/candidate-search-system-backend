# Candidate Search System — Backend

AI-powered candidate search backend with RAG (Retrieval Augmented Generation), multi-provider LLM support, vector search, and background document processing.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Vector Store | ChromaDB |
| Embeddings | Ollama (nomic-embed-text) |
| Background Jobs | Celery + Redis |
| File Storage | AWS S3 (boto3) |
| Auth | JWT (python-jose) + bcrypt |
| LLM Providers | OpenAI, Anthropic, Groq, Ollama, Gemini |
| Rate Limiting | SlowAPI |

---

## Features

- JWT authentication (register / login / me)
- Upload candidate resumes from S3 — processed in background via Celery
- Multi-format document processing: PDF (plain + tabular), DOCX, CSV, XLSX, TXT
- Parent-child chunking — child chunks embedded in ChromaDB, parent content stored in metadata for full context injection
- 7 retrieval strategies: similarity, MMR, multi-query, contextual compression, self-query, hybrid BM25, ensemble
- Multi-provider LLM: switch between OpenAI / Anthropic / Groq / Ollama / Gemini per request
- Streaming SSE responses — token-by-token to frontend
- Rate limiting on auth endpoints

---

## Project Structure

```
candidate-search-system-backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic settings — reads from .env
│   │   ├── db.py              # Async SQLAlchemy engine + session
│   │   ├── security.py        # JWT create/verify, password hash
│   │   ├── chroma_client.py   # ChromaDB singleton client (one collection)
│   │   ├── middleware.py      # CORS + proxy headers
│   │   ├── exceptions.py      # Global exception handlers
│   │   └── limiter.py         # SlowAPI rate limiter
│   ├── llm/                   # ← All LLM concerns isolated here
│   │   ├── __init__.py        # Clean exports: complete, stream, list_models, prompts
│   │   ├── providers.py       # Provider client factories + PROVIDER_MODELS registry
│   │   ├── caller.py          # complete() and stream() — uses providers
│   │   └── prompts.py         # All prompts: system, few-shot, retriever prompts
│   ├── models/
│   │   ├── user.py            # User table
│   │   ├── candidates.py      # Candidate table
│   │   ├── documents.py       # Document table
│   │   └── chat_history.py    # Chat history table
│   ├── schemas/
│   │   ├── auth.py            # RegisterRequest, LoginRequest
│   │   ├── candidate.py       # CandidateCreate, CandidateOut
│   │   ├── chat_history.py    # ChatRequest, ChatResponse, SSE schemas
│   │   ├── document.py        # DocumentCreate, DocumentOut
│   │   └── response.py        # ApiResponse generic wrapper
│   ├── routes/
│   │   ├── auth.py            # POST /auth/register, /login, /me
│   │   ├── candidate.py       # POST /candidates/upload, GET, PATCH, DELETE
│   │   └── chat.py            # POST /chat/query, /chat/query/stream, GET /chat/models
│   ├── services/
│   │   ├── auth_service.py    # register_user, login_user, get_me
│   │   ├── candidate_service.py  # upload → dispatch Celery task
│   │   ├── DocumentLoader.py  # Multi-format loader (PDF/DOCX/CSV/XLSX/TXT)
│   │   ├── text_spliter.py    # Parent-child chunking strategy
│   │   ├── Embadding.py       # EmbeddingService — Ollama nomic-embed-text
│   │   ├── s3_processor.py    # S3 download with temp file context manager
│   │   ├── rag_service.py     # All 7 retrieval strategies
│   │   ├── llm_service.py     # Thin wrapper re-exporting from app/llm
│   │   └── chat_servie.py     # RAG orchestrator — retrieve → prompt → LLM
│   └── workers/
│       ├── celery_app.py      # Celery app setup (Redis broker)
│       └── candidate_tasks.py # process_candidate_resume task
├── migrations/                # Alembic migration versions
├── .env                       # Local environment variables (never commit)
├── .env.example               # Template for environment variables
├── alembic.ini                # Alembic config
├── main.py                    # FastAPI app factory
├── run.py                     # Uvicorn dev server entry point
└── requirements.txt           # All dependencies
```

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (for Celery broker + result backend)
- ChromaDB server
- Ollama (for embeddings)
- AWS S3 bucket (for resume storage)

---

## Installation

### 1. Clone the repository

```bash
git clone <repository_url>
cd candidate-search-system-backend
```

### 2. Create virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in all values:

```bash
copy .env.example .env
```

```env
# App
APP_NAME=Candidate Search System
APP_ENV=development
DEBUG=False
SECRET_KEY=your_secret_key
FRONTEND_URL=http://localhost:3000

# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ai

# Redis
REDIS_URL=redis://localhost:6379

# JWT
JWT_SECRET_KEY=your_jwt_secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES=120
JWT_REFRESH_TOKEN_EXPIRES=720

# AWS S3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET=your-bucket-name
MAX_FILE_SIZE_MB=50

# LLM Providers (add only the ones you use)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# Default LLM
# development
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.2
# production (uncomment and replace above)
# DEFAULT_PROVIDER=groq
# DEFAULT_MODEL=llama-3.3-70b-versatile

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8000

# Email (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password
```

---

## Database Setup

### 1. Create the database

```sql
CREATE DATABASE ai;
```

### 2. Apply migrations

```bash
alembic upgrade head
```

### 3. Create a new migration after model changes

```bash
alembic revision --autogenerate -m "describe_your_change"
alembic upgrade head
```

| Command | Description |
|---|---|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic upgrade +1` | Apply next migration only |
| `alembic downgrade -1` | Revert last migration |
| `alembic history` | Show migration history |
| `alembic current` | Show current applied version |

---

## Running the Application

### Start all required services first

**ChromaDB:**
```bash
chroma run --host localhost --port 8000
```

**Ollama (embeddings):**
```bash
ollama serve
ollama pull nomic-embed-text
```

**Redis:**
```bash
# Windows
redis-server

# Linux/Mac
redis-server /etc/redis/redis.conf
```

**Celery worker (background jobs):**
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

### Start the API server

```bash
python run.py
```

Server runs at: `http://localhost:8000`

Interactive API docs: `http://localhost:8000/docs`

---

## API Reference

All protected endpoints require:
```http
Authorization: Bearer <access_token>
```

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, returns access + refresh tokens |
| GET | `/api/v1/auth/me` | Get current user info |

**Register:**
```json
POST /api/v1/auth/register
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepassword"
}
```

**Login:**
```json
POST /api/v1/auth/login
{
  "email": "john@example.com",
  "password": "securepassword"
}
```

---

### Candidates

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/candidates/upload` | Upload resume URL — triggers background processing |
| GET | `/api/v1/candidates/` | List all candidates |
| GET | `/api/v1/candidates/{id}` | Get candidate by ID |
| PATCH | `/api/v1/candidates/{id}` | Update candidate |
| DELETE | `/api/v1/candidates/{id}` | Delete candidate |

**Upload candidate resume:**
```json
POST /api/v1/candidates/upload
{
  "resume_file_url": "https://your-bucket.s3.amazonaws.com/resumes/john.pdf",
  "uploaded_by": "user-uuid"
}
```

Response:
```json
{
  "ok": true,
  "message": "Resume processing started",
  "data": {
    "task_id": "abc-123",
    "status": "processing"
  }
}
```

The Celery worker will:
1. Download file from S3
2. Detect file type and load document
3. Split into parent-child chunks
4. Embed child chunks with Ollama
5. Store in ChromaDB with parent content in metadata

---

### Chat

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/chat/query/stream` | SSE streaming response |
| GET  | `/api/v1/chat/models`        | List all available providers and models |

**Request body:**
```json
{
  "query": "Find Python developers with 5+ years experience in Bangalore",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.7,
  "strategy": "hybrid_bm25",
  "k": 5,
  "filters": null,
  "ensemble_weights": null
}
```

**Retrieval strategies:**

| Strategy | Description |
|---|---|
| `pipeline` | **Recommended** — multi-query → similarity pool → MMR → contextual compression |
| `similarity` | Top-k cosine similarity — fast, single query |
| `mmr` | Max Marginal Relevance — diverse, reduces redundancy |
| `multi_query` | LLM generates 3 query variants, merges results |
| `contextual` | LLM trims irrelevant parts from passages |
| `self_query` | LLM extracts metadata filters from natural language |
| `hybrid_bm25` | BM25 keyword + dense vector RRF fusion |
| `ensemble` | Weighted merge of similarity + MMR |

**Available providers and models:**

| Provider | Models |
|---|---|
| `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo` |
| `anthropic` | `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307` |
| `groq` | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768`, `gemma2-9b-it` |
| `ollama` | `llama3.2`, `mistral`, `phi3` |
| `gemini` | `gemini-1.5-pro`, `gemini-1.5-flash` |

---

### Streaming SSE Protocol

`POST /api/v1/chat/query/stream` returns Server-Sent Events:

```
data: {"type": "start",   "chat_id": "uuid", "query": "...", "provider": "openai", "model": "gpt-4o-mini", "strategy": "similarity"}

data: {"type": "chunk",   "content": "Python"}
data: {"type": "chunk",   "content": " developers"}
data: {"type": "chunk",   "content": " found:"}
... (one event per token)

data: {"type": "sources", "source_chunks": [...], "sources_count": 5}

data: {"type": "done",    "chat_id": "uuid"}

data: {"type": "error",   "message": "..."}  ← only on failure
```

**Frontend consumption:**
```javascript
const res = await fetch('/api/v1/chat/query/stream', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

const reader = res.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  const lines = decoder.decode(value).split('\n\n')
  for (const line of lines) {
    if (!line.startsWith('data:')) continue
    const event = JSON.parse(line.replace('data: ', ''))
    if (event.type === 'start')   initChatBubble(event.chat_id)
    if (event.type === 'chunk')   appendToken(event.content)
    if (event.type === 'sources') renderSources(event.source_chunks)
    if (event.type === 'done')    markComplete()
  }
}
```

---

## Document Processing

Supported file types uploaded via S3:

| Format | Loader | Notes |
|---|---|---|
| `.pdf` | pdfplumber + PyMuPDF | Auto-detects tables, falls back to plain text |
| `.docx` | python-docx | Extracts paragraphs grouped by headings + tables |
| `.doc` | python-docx | Same as docx |
| `.csv` | pandas | Each row becomes a searchable document |
| `.xlsx` | pandas | All sheets processed, each row is a document |
| `.xls` | pandas | Same as xlsx |
| `.txt` | built-in | Split on double newlines into paragraphs |

---

## Customization Guide

The `app/llm/` module is the single place to make any LLM-related changes:

| What you want to change | File to edit |
|---|---|
| Add a new LLM provider | `app/llm/providers.py` — add client factory + entry in `PROVIDER_MODELS` |
| Add a model to existing provider | `app/llm/providers.py` — add to `PROVIDER_MODELS` dict only |
| Change system prompt or tone | `app/llm/prompts.py` — edit `SYSTEM_PROMPT` |
| Change few-shot examples | `app/llm/prompts.py` — edit `FEW_SHOT_EXAMPLES` |
| Change multi-query retriever prompt | `app/llm/prompts.py` — edit `MULTI_QUERY_PROMPT` |
| Change contextual compression prompt | `app/llm/prompts.py` — edit `CONTEXTUAL_COMPRESSION_PROMPT` |
| Change self-query metadata prompt | `app/llm/prompts.py` — edit `SELF_QUERY_PROMPT` |
| Change how LLM is called | `app/llm/caller.py` |

---

## Parent-Child Chunking

```
Document page/section
        │
        ▼
  Parent chunk (1000 chars)  ← stored in child metadata as parent_content
        │
   ┌────┴────┐
   ▼         ▼
 Child 1   Child 2   (200 chars each)  ← embedded + stored in ChromaDB
```

- Search finds the small child chunk quickly (precise vector match)
- `parent_content` is stored inside the child chunk's metadata — no second collection, no extra DB call
- Full parent text is injected into LLM context window
- Single ChromaDB collection: `candidate_chunks`

---

## Troubleshooting

**ChromaDB connection refused**
```bash
# Make sure ChromaDB server is running
chroma run --host localhost --port 8000
```

**Ollama embedding fails**
```bash
# Make sure Ollama is running and model is pulled
ollama serve
ollama pull nomic-embed-text
```

**Celery task not running**
```bash
# Check Redis is running
redis-cli ping   # should return PONG

# Start worker
celery -A app.workers.celery_app worker --loglevel=info

# Monitor tasks
celery -A app.workers.celery_app flower
```

**Database connection error**
```bash
# Verify PostgreSQL is running and DATABASE_URL is correct
psql -h localhost -U postgres -d ai
```

**Migration conflicts**
```bash
# Reset and reapply (development only)
alembic downgrade base
alembic upgrade head
```

**JWT token expired**
- Access token expires after `JWT_ACCESS_TOKEN_EXPIRES` minutes (default: 120)
- Re-login to get a new token
