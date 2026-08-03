# Loomin-Docs

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/smdsheriff/loomin-docs/actions/workflows/ci.yml/badge.svg)](https://github.com/smdsheriff/loomin-docs/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/react-18-61dafb.svg)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A rich text editor with an integrated AI assistant sidebar, powered by local LLMs via [Ollama](https://ollama.com). Designed to run entirely self-contained — including on air-gapped RHEL 9 environments with no internet access.

Loomin-Docs pairs a TipTap editor with a Retrieval-Augmented Generation (RAG) pipeline. Upload documents (`.pdf`, `.md`, `.txt`) and ask context-aware questions answered by locally hosted language models. **No data ever leaves your network** — there are no third-party API calls, no telemetry, and no account system.

> **Why this exists.** Most AI writing tools require shipping your documents to someone else's servers. Loomin-Docs is for teams who can't do that: regulated industries, classified networks, or anyone who just wants their drafts to stay on their own hardware.

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Local Development (without Docker)](#local-development-without-docker)
- [Air-Gapped Deployment (RHEL 9)](#air-gapped-deployment-rhel-9)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Features

### Editor & Workspace
- **Rich Text Editor** — TipTap-based editor with Markdown input rules and a formatting toolbar (headings, bold, italic, underline, strikethrough, lists, code blocks, blockquotes), plus debounced auto-save.
- **Multi-Format Export** — Export the active document as `.txt`, `.md`, or `.html` from the header dropdown.
- **Document Versioning** — Every update writes a new version to SQLite. Browse, preview, and restore prior versions from the History tab.
- **Contextual Editing** — Select text, then choose Summarize or Improve from the floating bubble menu. Review the suggestion and Accept or Discard before it touches the document.
- **Resizable Sidebar** — Drag the divider to size the assistant panel between 320 and 600 px.

### AI Assistant Sidebar
- **Multi-Turn Chat** — Three-tab sidebar (Chat, Files, History). All panels stay mounted, so conversation state survives tab switches and model changes.
- **Dual-Context RAG** — Answers are grounded in *both* the current editor document and your uploaded files. FAISS similarity search with a configurable score threshold filters out weak matches instead of letting the model improvise.
- **RAG-Grounded Rewrites** — Summarize and Improve retrieve relevant file chunks and inject them as reference context, producing rewrites with inline `[Source N]` citations.
- **Clickable Citations** — Inline citation badges resolve `[Source N]` markers to their source file. Clicking one jumps to the Files tab and highlights that file.
- **Model Selector** — Switch between any models available in your Ollama instance (`llama3.2:1b` and `gemma3:1b` ship by default). Conversation history is preserved across switches.
- **Streaming Responses** — Tokens stream to the browser over Server-Sent Events.

### Asset Management
- **Document Upload** — Drag-and-drop or click to upload `.pdf`, `.md`, and `.txt` files (50 MB limit). Content is chunked (~375 words with 38-word overlap), embedded with `all-MiniLM-L6-v2`, and indexed in FAISS.
- **File Toggle** — Enable or disable individual files as RAG context without deleting them. Only active files contribute to answers.
- **Chunk Previews** — Expand any file to inspect exactly which text chunks were indexed.

### Observability & Privacy
- **Token Visualization** — Segmented bar showing document tokens, file-chunk tokens, and remaining context window, with percentages.
- **Latency Tracing** — Every AI response carries expandable metadata: `request_id`, retrieval time, generation time, total time, tokens/second, model name, and chunk count.
- **PII Sanitization** — SSNs, credit cards, emails, API keys, AWS keys, and phone numbers are masked at four interception points before any text reaches the LLM.

### Deployment
- **Fully Offline** — The whole stack runs on a single VM with no external dependencies at runtime.
- **Dual Compose Files** — `docker-compose.yml` builds from source for development; `docker-compose.prod.yml` is image-only for air-gapped targets.
- **Sideload Tooling** — `sideload.sh` bundles Docker RPMs, images, model weights, and embeddings into a single transferable archive; `setup.sh` bootstraps the target VM from it.

---

## Screenshots

> Screenshots are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to add them. Place images under `docs/images/` and reference them here.

---

## Technology Stack

| Component       | Technology                                    | Purpose                                        |
|-----------------|-----------------------------------------------|------------------------------------------------|
| Frontend        | React 18, TypeScript, TipTap, TailwindCSS     | Rich text editor and AI sidebar                |
| Reverse Proxy   | Nginx                                         | Static assets and API proxy (SSE-aware)        |
| Backend         | Python 3.11, FastAPI, SQLAlchemy (async)      | REST API, RAG pipeline, PII sanitization       |
| Database        | SQLite (via `aiosqlite`)                      | Documents, versions, chat history, file metadata |
| Vector Store    | FAISS (`IndexFlatIP`)                         | Cosine similarity search over document chunks  |
| Embedding Model | `all-MiniLM-L6-v2` (384-dim, L2-normalized)   | Text-to-vector embeddings                      |
| LLM Runtime     | Ollama (`llama3.2:1b`, `gemma3:1b` by default)| Local inference, no external API calls         |
| Orchestration   | Docker Compose                                | Three containers with health-check gating      |

---

## Quick Start

**Prerequisites:** Docker Engine with the Compose plugin. First boot pulls ~2 GB of model weights, so allow a few minutes.

```bash
git clone https://github.com/smdsheriff/loomin-docs.git
cd loomin-docs/deploy

docker compose up --build     # or: make build && make up
```

| Service        | URL                                              |
|----------------|--------------------------------------------------|
| Application    | <http://localhost>                               |
| API docs       | <http://localhost:8000/docs>                     |
| Ollama         | <http://localhost:11434>                         |

The Ollama entrypoint pulls `llama3.2:1b` and `gemma3:1b` on first boot and writes a readiness marker; the backend waits on that health check before starting.

```bash
make logs      # tail all service logs
make health    # HTTP status of all three services
make down      # stop the stack
make clean     # stop and destroy volumes (deletes all data)
```

Run `make help` in `deploy/` for the full target list.

### Hardware Expectations

| Resource | Minimum      | Recommended | Notes                                   |
|----------|--------------|-------------|-----------------------------------------|
| CPU      | 4 cores      | 8+ cores    | Inference is CPU-bound without a GPU    |
| RAM      | 8 GB         | 16+ GB      | Multiple models may be resident at once |
| Disk     | 20 GB        | 50+ GB      | Model weights plus document storage     |
| GPU      | Not required | NVIDIA GPU  | Substantially faster generation         |

---

## Local Development (without Docker)

Useful when iterating on the frontend or backend directly. You still need an Ollama server running somewhere.

**1. Start Ollama and pull a model:**

```bash
ollama serve &
ollama pull llama3.2:1b
```

**2. Backend:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env        # then edit paths for local (non-container) use
uvicorn app.main:app --reload --port 8000
```

By default the backend writes to `/data`, which suits containers but not a laptop. Override the paths in `.env`:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./loomin.db
FAISS_INDEX_PATH=./.local/faiss_index
UPLOAD_DIR=./.local/uploads
OLLAMA_BASE_URL=http://localhost:11434
```

**3. Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Vite serves on <http://localhost:3000> and already proxies `/api` to `http://localhost:8000` (see `vite.config.ts`). To point the frontend at a backend elsewhere, set `VITE_API_URL` instead.

---

## Air-Gapped Deployment (RHEL 9)

### Phase 1 — Build the offline package (internet required)

On a staging machine with Docker, Ollama, and Python 3:

```bash
cd deploy
bash sideload.sh          # or: make prepare-offline
```

This downloads Docker RPMs for RHEL 9, builds and exports every image as a `.tar`, pulls the Ollama model weights, fetches the `all-MiniLM-L6-v2` embedding model, copies the deployment scripts and `docker-compose.prod.yml`, and bundles it all into `loomin-docs-package.tar.gz` (roughly 15–25 GB).

### Phase 2 — Bootstrap the target VM

Transfer the archive to the air-gapped host, then:

```bash
tar -xzf loomin-docs-package.tar.gz
sudo bash package/setup.sh package/
```

The script installs Docker Engine from the bundled RPMs (`--disablerepo='*'`), loads every container image, populates the `embedding-model` and `ollama-data` volumes, brings up `docker-compose.prod.yml`, waits for health checks, and prints the access URLs.

`docker-compose.prod.yml` contains **no build directives** and declares its volumes as `external`, so no source code is required on the target host.

---

## Configuration

Every setting is an environment variable read by the backend's `Settings` class. See [.env.example](.env.example) for a copy-paste starting point.

| Variable                   | Default                                 | Description                                     |
|----------------------------|-----------------------------------------|-------------------------------------------------|
| `DATABASE_URL`             | `sqlite+aiosqlite:////data/loomin.db`   | SQLAlchemy async connection string              |
| `OLLAMA_BASE_URL`          | `http://ollama:11434`                   | Ollama server URL                               |
| `EMBEDDING_MODEL_PATH`     | `all-MiniLM-L6-v2`                      | Model name (downloaded) or local path (offline) |
| `FAISS_INDEX_PATH`         | `/data/faiss_index`                     | Where the FAISS index is persisted              |
| `UPLOAD_DIR`               | `/data/uploads`                         | Where uploaded source files are stored          |
| `DEFAULT_MODEL`            | `llama3.2:1b`                           | Model preselected in the dropdown               |
| `MAX_CHUNKS_RETRIEVED`     | `5`                                     | Top-K chunks per RAG query                      |
| `MIN_SIMILARITY_SCORE`     | `0.25`                                  | Minimum FAISS score for a chunk to be included  |
| `MAX_CONVERSATION_HISTORY` | `100`                                   | Messages carried into multi-turn context        |
| `USE_LANGGRAPH`            | `false`                                 | Route `/api/chat` through the LangGraph pipeline (see below) |

---

## Optional: LangGraph RAG Pipeline

`/api/chat` ships with two interchangeable implementations of the same RAG
pipeline, selected by the `USE_LANGGRAPH` flag:

- **Default (`false`)** — the original inline pipeline. `langgraph` is not
  imported at all on this path.
- **Enabled (`true`)** — the request is orchestrated by [LangGraph](https://langchain-ai.github.io/langgraph/):
  a **prep graph** (retrieve → file inventory → prompt assembly) runs to
  completion first, then a **generation graph** streams tokens. Both paths
  produce identical output, identical SSE framing, and identical error semantics
  (a retrieval failure returns HTTP 500 either way; a generation error streams an
  `[Error: …]` token — matching the original).

The graph exists as a foundation for retrieval-quality features — query
rewriting, cross-encoder reranking, document grading, self-correction loops —
which slot in as additional nodes. It reuses the project's own retriever,
embedder, and Ollama client, so no `langchain-ollama` dependency is added. See
[ARCHITECTURE.md](ARCHITECTURE.md#langgraph-rag-pipeline-optional) for the node
diagram.

Enable it per deployment (and flip back to `false` to roll back instantly — no
different image required):

```bash
# .env or the backend service environment
USE_LANGGRAPH=true
```

Air-gapped bundles built by `sideload.sh` already include `langgraph` (it is
baked into the backend image from `requirements.txt`); just rebuild the image so
the updated dependencies are captured.

Backend tests live in `backend/tests/` and run fully offline (Ollama and
retrieval are mocked):

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## API Reference

Interactive Swagger UI: <http://localhost:8000/docs>

| Method | Endpoint                       | Description                                 |
|--------|--------------------------------|---------------------------------------------|
| POST   | `/api/chat`                    | Multi-turn chat with RAG (SSE streaming)    |
| POST   | `/api/chat/summarize`          | RAG-grounded summarization of a selection   |
| POST   | `/api/chat/improve`            | RAG-grounded rewrite of a selection         |
| GET    | `/api/chat/history`            | Retrieve chat message history               |
| POST   | `/api/documents`               | Create a document                           |
| GET    | `/api/documents`               | List documents                              |
| PUT    | `/api/documents/{id}`          | Update a document (auto-creates a version)  |
| GET    | `/api/documents/{id}/versions` | List a document's version history           |
| POST   | `/api/files/upload`            | Upload and index a file for RAG             |
| GET    | `/api/files`                   | List uploaded files                         |
| PATCH  | `/api/files/{id}/toggle`       | Enable/disable a file as RAG context        |
| GET    | `/api/files/{id}/chunks`       | Inspect a file's indexed chunks             |
| DELETE | `/api/files/{id}`              | Delete a file and remove it from the index  |
| GET    | `/api/models`                  | List models available in Ollama             |
| POST   | `/api/tokens/count`            | Segmented token count (document + chunks)   |
| GET    | `/health`                      | Backend health check                        |

---

## Project Structure

```
loomin-docs/
├── frontend/                       # React + TypeScript SPA
│   ├── Dockerfile                  # Multi-stage: Node 20 builder → Nginx Alpine
│   ├── nginx.conf                  # SPA fallback + /api proxy (buffering off for SSE)
│   ├── public/favicon.svg
│   └── src/
│       ├── App.tsx                 # Root component: state, handlers, hook wiring
│       ├── components/
│       │   ├── Editor/
│       │   │   ├── Editor.tsx      # TipTap editor with BubbleMenu + imperative handles
│       │   │   └── Toolbar.tsx     # Formatting toolbar
│       │   ├── Layout.tsx          # Header: title, save status, word count, export
│       │   ├── Sidebar/
│       │   │   ├── Sidebar.tsx     # Three-tab container (Chat, Files, History)
│       │   │   ├── ChatPanel.tsx   # SSE streaming, citations, Accept/Discard
│       │   │   ├── FilesPanel.tsx  # Upload, toggle, chunk previews
│       │   │   ├── VersionPanel.tsx# Version browse / preview / restore
│       │   │   └── ModelSelector.tsx
│       │   └── TokenVisualization/
│       │       └── TokenBar.tsx    # Segmented context-window bar
│       ├── hooks/useApi.ts         # useDocuments, useChat, useFiles, useModels, useTokenCount
│       ├── services/api.ts         # HTTP client and SSE parser
│       └── types/index.ts          # Shared TypeScript interfaces
├── backend/                        # Python + FastAPI service
│   ├── Dockerfile                  # python:3.11-slim
│   ├── Modelfile                   # Ollama Modelfile documenting the system prompt
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # App factory: lifespan, CORS, routers, /health
│       ├── core/
│       │   ├── config.py           # Pydantic Settings
│       │   ├── pii.py              # PII sanitization (6 patterns, offset tracking)
│       │   └── tracing.py          # RequestTrace dataclass
│       ├── api/routes/
│       │   ├── chat.py             # Chat (SSE), summarize, improve
│       │   ├── documents.py        # CRUD with auto-versioning
│       │   ├── files.py            # Upload, toggle, chunks, delete
│       │   └── models.py           # Model list + segmented token count
│       ├── rag/
│       │   ├── embeddings.py       # sentence-transformers wrapper
│       │   ├── indexer.py          # FAISS IndexFlatIP (thread-safe, disk-persisted)
│       │   └── retriever.py        # Similarity search over active files
│       ├── services/
│       │   ├── ollama.py           # Async client (generate, chat_stream, list_models)
│       │   └── document.py         # PDF/MD/TXT parsing, chunking, token estimation
│       └── models/
│           ├── database.py         # SQLAlchemy models + lightweight migrations
│           └── schemas.py          # Pydantic request/response schemas
├── deploy/
│   ├── docker-compose.yml          # Development (builds from source)
│   ├── docker-compose.prod.yml     # Air-gapped production (image-only)
│   ├── ollama-entrypoint.sh        # Model preload + readiness marker
│   ├── setup.sh                    # RHEL 9 offline bootstrap
│   ├── sideload.sh                 # Offline package builder
│   └── Makefile                    # build / up / down / logs / health targets
├── ARCHITECTURE.md                 # System architecture and data flows
├── CONTRIBUTING.md                 # How to set up, build, and submit changes
├── SECURITY.md                     # Threat model and vulnerability reporting
├── CODE_OF_CONDUCT.md
└── LICENSE                         # MIT
```

---

## Roadmap

Loomin-Docs is a working single-user application. These are the areas where help is most valuable — see [CONTRIBUTING.md](CONTRIBUTING.md) and the issue tracker.

- [x] **LangGraph orchestration** — `/api/chat` can run through an explicit graph (opt-in via `USE_LANGGRAPH`), the foundation for the retrieval-quality nodes below.
- [~] **Automated test suite** — the backend now has a `pytest` suite (`backend/tests/`) covering the RAG graph, prompt building, and the chat route. Still wanted: PII/chunking unit tests and a frontend Vitest suite.
- [ ] **Query rewriting / reranking / document grading** — additional LangGraph nodes: a cross-encoder pass over FAISS candidates, an LLM relevance gate, and conversational query reformulation.
- [ ] **Real-time collaboration** — multi-user presence and CRDT-based co-editing over WebSockets. Nothing is implemented today; the app is single-user.
- [ ] **Authentication and multi-tenancy** — there is currently no auth layer and no per-user data isolation.
- [ ] **PostgreSQL + pgvector option** — as an alternative to SQLite plus a file-backed FAISS index.
- [ ] **Additional file formats** — `.docx`, `.html`, and `.csv` ingestion.
- [ ] **GPU deployment guide** — Compose overlay for NVIDIA runtime.
- [ ] **Frontend linting** — ESLint and Prettier config, wired into CI.

---

## Contributing

Contributions are very welcome — bug reports, docs, and code alike. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding conventions, and the pull request process. All participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

Good first issues: anything under [Roadmap](#roadmap), especially the test suite and frontend linting.

---

## Security

Loomin-Docs ships **without authentication** and binds its API to all interfaces. It is designed for trusted networks. Do not expose it directly to the public internet without putting your own authentication and TLS termination in front of it.

To report a vulnerability, please follow the process in [SECURITY.md](SECURITY.md) rather than opening a public issue.

---

## License

Released under the [MIT License](LICENSE). © 2026 Mohammed Sheriff.

Note that the models and dependencies Loomin-Docs orchestrates carry their own licenses — including Llama 3.2 (Llama Community License), Gemma (Gemma Terms of Use), and `all-MiniLM-L6-v2` (Apache 2.0). Review them before commercial deployment.

---

## Acknowledgements

Built on the work of [Ollama](https://ollama.com), [TipTap](https://tiptap.dev), [FastAPI](https://fastapi.tiangolo.com), [FAISS](https://faiss.ai), [sentence-transformers](https://sbert.net), [PyMuPDF](https://pymupdf.readthedocs.io), and [TailwindCSS](https://tailwindcss.com).
