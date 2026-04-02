# Loomin-Docs

A real-time collaborative text editor with an integrated AI assistant sidebar, powered by local LLMs via Ollama. Designed to run entirely self-contained on air-gapped RHEL 9 environments with no internet access.

Loomin-Docs combines rich text editing with a Retrieval-Augmented Generation (RAG) pipeline, enabling users to upload documents (.pdf, .md, .txt) and ask context-aware questions answered by locally hosted language models. All data stays on-premises -- nothing leaves the network.

## Features

### Editor & Workspace
- **Rich Text Editor** -- TipTap-based editor with Markdown support, formatting toolbar (headings, bold, italic, underline, lists, code blocks, blockquotes), and real-time auto-save.
- **Multi-Format Export** -- Export documents as `.txt`, `.md` (Markdown), or `.html` with formatting preserved via dropdown menu.
- **Document Versioning** -- Every edit is auto-saved with version history in SQLite. Browse, preview, and restore previous versions from the History tab in the sidebar.
- **Contextual Editing** -- Select text in the editor, click Summarize or Improve via the floating bubble menu. Review the AI's suggestion, then Accept or Discard before it modifies the document.

### AI Assistant Sidebar
- **AI Chat Assistant** -- Persistent three-tab sidebar (Chat, Files, History) with multi-turn conversation context preserved across tab switches and model changes.
- **RAG Pipeline** -- FAISS vector search with similarity threshold filtering ensures answers are grounded in both the active document content AND uploaded files, not hallucinations.
- **Contextual RAG** -- Chat responses use dual context: the current editor document (up to 2000 chars, HTML-stripped) plus uploaded file chunks retrieved via FAISS similarity search.
- **RAG-Grounded Rewrites** -- Summarize and Improve operations retrieve relevant file chunks and inject them as reference context, producing factually grounded rewrites with inline `[Source N]` citations.
- **Clickable Citations** -- AI responses include inline citation badges that resolve `[Source N]` markers to source files. Clicking navigates to the Files tab and highlights the referenced file.
- **Model Selector** -- Toggle between multiple local models (`llama3.2:1b`, `gemma3:1b`, `llama3.2:1b`) via Ollama API. Conversation history is preserved when switching.

### Asset Management (Files Tab)
- **Document Upload** -- Upload `.pdf`, `.md`, and `.txt` files (drag-and-drop or click). Content is automatically chunked, embedded with all-MiniLM-L6-v2, and indexed in FAISS.
- **File Toggle** -- Enable/disable individual files from RAG context via toggle switch without deleting them. Only active files contribute to AI responses.
- **Chunk Previews** -- Expand any file to view its indexed text chunks inline with chunk index and content preview.

### Observability
- **Token Visualization** -- Segmented progress bar showing three components: document tokens (blue), file chunk tokens (amber), and free context window (gray), with percentage labels.
- **Latency Tracing** -- Every AI response includes expandable metadata: `request_id`, retrieval time, generation time, total time, tokens/second, model name, and chunk count.
- **PII Sanitization** -- Sensitive data (SSN, credit cards, emails, API keys, AWS keys, phone numbers) is masked at four interception points before reaching the LLM.

### Collaboration & Deployment
- **Real-Time Presence** -- WebSocket-based collaboration awareness: connected users appear as colored avatar circles in the header bar with live join/leave updates.
- **Custom Modelfile** -- Ollama Modelfile with RAG-grounded 7-rule system prompt is auto-loaded via `ollama create loomin` at container startup.
- **Air-Gap Ready** -- The entire stack runs offline on a single RHEL 9 VM with no external dependencies. Dual Docker Compose files for development (with build) and production (image-only).

## Technology Stack

| Component         | Technology                        | Purpose                                    |
|-------------------|-----------------------------------|--------------------------------------------|
| Frontend          | React 18, TypeScript, TipTap, TailwindCSS | Rich text editor, AI sidebar, presence UI |
| Reverse Proxy     | Nginx                             | Static assets, API proxy, WebSocket proxy  |
| Backend           | Python 3.11, FastAPI, SQLAlchemy  | REST API, WebSocket, RAG pipeline, PII     |
| Database          | SQLite (via aiosqlite)            | Document versions, chat history, file metadata |
| Vector Store      | FAISS (IndexFlatIP)               | Cosine similarity search over document chunks |
| Embedding Model   | all-MiniLM-L6-v2 (384-dim)       | Text-to-vector embeddings (L2-normalized)  |
| LLM               | llama3.2:1b, gemma3:1b, llama3.2:1b (via Ollama) | Multi-model inference |
| Orchestration     | Docker Compose                    | Three-container management with health checks |
| Target OS         | RHEL 9 (air-gapped)              | Production deployment                      |

## Project Structure

```
loomin-docs/
├── frontend/                       # React + TypeScript application
│   ├── Dockerfile                  # Multi-stage: Node builder -> Nginx Alpine
│   ├── nginx.conf                  # Reverse proxy + WebSocket proxy + timeouts
│   ├── public/
│   │   └── favicon.svg             # Blue document icon favicon
│   ├── src/
│   │   ├── App.tsx                 # Root component: state, handlers, hook wiring
│   │   ├── components/
│   │   │   ├── Editor/
│   │   │   │   ├── Editor.tsx      # TipTap editor with BubbleMenu + replaceSelection
│   │   │   │   └── Toolbar.tsx     # Formatting toolbar (H1-H3, bold, lists, code)
│   │   │   ├── Layout.tsx          # Header bar: title, presence, export, shortcuts
│   │   │   ├── Sidebar/
│   │   │   │   ├── Sidebar.tsx     # Three-tab container (Chat, Files, History)
│   │   │   │   ├── ChatPanel.tsx   # AI chat: SSE streaming, citations, actions
│   │   │   │   ├── FilesPanel.tsx  # File upload, toggle, chunk preview
│   │   │   │   ├── VersionPanel.tsx # Version history: browse, preview, restore
│   │   │   │   └── ModelSelector.tsx # Ollama model dropdown
│   │   │   └── TokenVisualization/
│   │   │       └── TokenBar.tsx    # Segmented context window bar (doc/files/free)
│   │   ├── hooks/
│   │   │   ├── useApi.ts           # React hooks: useDocuments, useChat, useFiles, useModels, useTokenCount
│   │   │   └── usePresence.ts      # WebSocket presence hook (users, cursor tracking)
│   │   ├── services/
│   │   │   └── api.ts              # HTTP client, SSE parser, file/toggle/chunk APIs
│   │   └── types/
│   │       └── index.ts            # TypeScript interfaces (15+ types)
│   └── package.json
├── backend/                        # Python + FastAPI application
│   ├── Dockerfile                  # Python 3.11 slim
│   ├── Modelfile                   # Ollama system prompt (7 rules, temp 0.7, top_p 0.9)
│   ├── requirements.txt            # FastAPI, SQLAlchemy, FAISS, sentence-transformers, etc.
│   └── app/
│       ├── main.py                 # FastAPI app: lifespan, CORS, router registration
│       ├── core/
│       │   ├── config.py           # Pydantic Settings (9 env-configurable params)
│       │   ├── pii.py              # PII sanitization (6 regex patterns, offset tracking)
│       │   └── tracing.py          # RequestTrace dataclass (request_id, timing, throughput)
│       ├── api/routes/
│       │   ├── chat.py             # Chat (SSE streaming), summarize, improve + RAG grounding
│       │   ├── collaboration.py    # WebSocket presence (PresenceManager, cursor tracking)
│       │   ├── documents.py        # CRUD with auto-versioning on every update
│       │   ├── files.py            # Upload, toggle, chunk preview, delete endpoints
│       │   └── models.py           # Ollama model list + segmented token count
│       ├── rag/
│       │   ├── embeddings.py       # Sentence-transformers with air-gapped error handling
│       │   ├── indexer.py          # FAISS IndexFlatIP (thread-safe, disk-persisted)
│       │   └── retriever.py        # Similarity search filtered by is_active files
│       ├── services/
│       │   ├── ollama.py           # Async HTTP client (generate, chat_stream, list_models)
│       │   └── document.py         # PDF/MD/TXT parsing, chunking, hybrid token estimation
│       └── models/
│           ├── database.py         # SQLAlchemy models (5 tables) + lightweight migrations
│           └── schemas.py          # Pydantic request/response schemas (20+ models)
├── deploy/                         # Deployment infrastructure
│   ├── docker-compose.yml          # Development (with build directives + Modelfile mount)
│   ├── docker-compose.prod.yml     # Air-gapped production (image-only, no build)
│   ├── ollama-entrypoint.sh        # Model preloading + ollama create + readiness marker
│   ├── setup.sh                    # Air-gapped RHEL 9 bootstrap (RPMs, images, volumes)
│   ├── sideload.sh                 # Offline package builder (~15-25 GB archive)
│   └── Makefile                    # Convenience targets (build, up, down, logs, health)
├── tests/
│   └── verify_rag.py              # RAG faithfulness test (9 cases, SSE-aware, scoring)
├── README.md                      # This file
└── ARCHITECTURE.md                # Detailed system architecture and data flows
```

## Quick Start (Development)

Prerequisites: Docker Engine with the Compose plugin.

```bash
cd loomin-docs/deploy

# Build and start all services
docker compose up --build

# Or using Make
make build && make up
```

The application will be available at [http://localhost](http://localhost). The API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

The Ollama entrypoint automatically pulls `llama3.2:1b`, `gemma3:1b`, and `llama3.2:1b` on first boot, then creates the custom `loomin` model from the bundled Modelfile.

```bash
# View logs
make logs

# Stop the stack
make down
```

## Air-Gapped Deployment (RHEL 9)

### Phase 1: Prepare the Offline Package (Internet Required)

Run this on a machine with internet access, Docker, Ollama, and Python 3:

```bash
cd deploy
bash sideload.sh
```

This will:
1. Download Docker RPMs for RHEL 9
2. Build and export all Docker images as `.tar` files (`loomin-frontend`, `loomin-backend`, `ollama/ollama`)
3. Pull Ollama model weights (llama3.2:1b, gemma3:1b, llama3.2:1b)
4. Download the `all-MiniLM-L6-v2` embedding model
5. Copy deployment scripts, Modelfile, and `docker-compose.prod.yml`
6. Bundle everything into `loomin-docs-package.tar.gz`

### Phase 2: Deploy on the Air-Gapped VM

Transfer `loomin-docs-package.tar.gz` to the target RHEL 9 VM (e.g., via USB), then:

```bash
tar -xzf loomin-docs-package.tar.gz
sudo bash package/setup.sh package/
```

The setup script will:
1. Install Docker Engine from bundled RPMs (with `--disablerepo='*'`)
2. Load all container images from `.tar` files
3. Populate Docker volumes (embedding model + Ollama model blobs)
4. Start the stack using `docker-compose.prod.yml` (no build directives)
5. Wait for all services to pass health checks (including `ollama create loomin`)
6. Print access URLs

The production compose file (`docker-compose.prod.yml`) has **no build directives** -- it uses only pre-loaded images, so no source code is needed on the target VM.

## API Documentation

Visit [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger documentation.

### Key Endpoints

| Method | Endpoint                       | Description                            |
|--------|--------------------------------|----------------------------------------|
| POST   | `/api/chat`                    | Multi-turn AI chat with RAG (SSE streaming) |
| POST   | `/api/chat/summarize`          | RAG-grounded text summarization        |
| POST   | `/api/chat/improve`            | RAG-grounded text improvement          |
| GET    | `/api/chat/history`            | Retrieve chat message history          |
| POST   | `/api/documents`               | Create a document                      |
| GET    | `/api/documents`               | List documents                         |
| PUT    | `/api/documents/{id}`          | Update document (auto-versions)        |
| GET    | `/api/documents/{id}/versions` | List document version history          |
| POST   | `/api/files/upload`            | Upload and index a file for RAG        |
| GET    | `/api/files`                   | List uploaded files                    |
| PATCH  | `/api/files/{id}/toggle`       | Enable/disable file for RAG context    |
| GET    | `/api/files/{id}/chunks`       | View indexed chunks for a file         |
| DELETE | `/api/files/{id}`              | Remove a file and its index            |
| GET    | `/api/models`                  | List available Ollama models           |
| POST   | `/api/tokens/count`            | Segmented token count (doc + chunks)   |
| WS     | `/ws/collaborate/{doc_id}`     | Real-time presence WebSocket           |
| GET    | `/health`                      | Backend health check                   |

## Configuration

All settings are environment-configurable via the backend's `Settings` class:

| Variable                   | Default                 | Description                          |
|----------------------------|-------------------------|--------------------------------------|
| `DATABASE_URL`             | `sqlite+aiosqlite:////data/loomin.db` | SQLite connection string |
| `OLLAMA_BASE_URL`          | `http://ollama:11434`   | Ollama server URL                    |
| `EMBEDDING_MODEL_PATH`     | `all-MiniLM-L6-v2`     | Path or name of embedding model      |
| `DEFAULT_MODEL`            | `llama3.2:1b`           | Default Ollama model for chat        |
| `MAX_CHUNKS_RETRIEVED`     | `5`                     | Top-K chunks for RAG retrieval       |
| `MIN_SIMILARITY_SCORE`     | `0.25`                  | Minimum FAISS score to include chunk |
| `MAX_CONVERSATION_HISTORY` | `100`                    | Messages to include in multi-turn context |

## Service Health Check

```bash
make health
```

Reports HTTP status of frontend (:80), backend (:8000), and Ollama (:11434).
