# Loomin-Docs Architecture

This document describes the system architecture, data flows, component responsibilities, security considerations, and performance characteristics of Loomin-Docs.

## System Overview

Loomin-Docs is a three-container application orchestrated by Docker Compose. All containers communicate over an internal bridge network (`loomin-net`). The only externally exposed port in production is port 80 (Nginx), which serves the frontend, proxies API requests to the backend, and upgrades WebSocket connections for real-time collaboration.

```mermaid
graph TB
    subgraph "External"
        User["User Browser"]
    end

    subgraph "Docker Host (RHEL 9 VM)"
        subgraph "loomin-net (bridge network)"
            FE["Frontend Container<br/>Nginx :80"]
            BE["Backend Container<br/>FastAPI :8000"]
            OL["Ollama Container<br/>Ollama Server :11434"]
        end

        subgraph "Docker Volumes"
            V1["backend-data<br/>/data"]
            V2["embedding-model<br/>/models"]
            V3["ollama-data<br/>/root/.ollama"]
        end
    end

    User -->|"HTTP :80"| FE
    User <-->|"WebSocket /ws/*"| FE
    FE -->|"Reverse Proxy<br/>/api/* -> :8000"| BE
    FE <-->|"WebSocket Proxy<br/>/ws/* -> :8000"| BE
    BE -->|"Multi-turn /api/chat<br/>+ /api/generate"| OL

    BE --- V1
    BE --- V2
    OL --- V3

    subgraph "backend-data volume"
        DB["SQLite<br/>loomin.db"]
        FI["FAISS Index<br/>faiss_index/"]
        UL["Uploads<br/>uploads/"]
    end

    V1 --- DB
    V1 --- FI
    V1 --- UL
```

## Component Details

### Frontend (Nginx + React)

- **Image**: `loomin-frontend:latest` (multi-stage: Node 20 builder -> Nginx Alpine)
- **Responsibilities**:
  - Serve the compiled React SPA (TipTap editor, AI sidebar, file manager)
  - Reverse-proxy all `/api/*` requests to the backend on port 8000
  - WebSocket proxy for `/ws/*` with 24h timeout for real-time collaboration
  - Handle file uploads up to 100 MB (`client_max_body_size 100M`)
  - Proxy timeouts: 600s read/send for long LLM inference
- **Port**: 80 (exposed to host)
- **Key Frontend Components**:
  - `Editor/Editor.tsx` -- TipTap rich text editor with BubbleMenu (Summarize/Improve), `replaceSelection` and `setContent` imperative handles
  - `Editor/Toolbar.tsx` -- Formatting toolbar: H1-H3, bold, italic, underline, strikethrough, code, lists, blockquotes
  - `Sidebar/Sidebar.tsx` -- Three-tab container (Chat, Files, History) with all panels mounted for state preservation
  - `Sidebar/ChatPanel.tsx` -- Multi-turn AI chat with SSE streaming, typing indicator, citation badges, action trace badges, Accept/Discard flow
  - `Sidebar/FilesPanel.tsx` -- File upload (drag-and-drop), toggle on/off, chunk previews, delete with highlighting
  - `Sidebar/VersionPanel.tsx` -- Version history browser with preview, restore, time-ago display
  - `Sidebar/ModelSelector.tsx` -- Dropdown toggling between Ollama models with size display
  - `TokenVisualization/TokenBar.tsx` -- Segmented context window bar (blue=doc, amber=files, gray=free)
  - `Layout.tsx` -- Header bar with editable title, save status, presence avatars, word count, export dropdown, keyboard shortcuts
- **Hooks**:
  - `useApi.ts` -- `useDocuments`, `useChat`, `useFiles`, `useModels`, `useTokenCount` with debounced API calls
  - `usePresence.ts` -- WebSocket hook for real-time user presence per document

### Backend (FastAPI)

- **Image**: `loomin-backend:latest` (Python 3.11 slim)
- **Responsibilities**:
  - RESTful API for chat, documents, files, models, and token counting
  - WebSocket endpoint for real-time collaboration presence (`/ws/collaborate/{document_id}`)
  - Multi-turn conversation: fetches recent history from SQLite, assembles messages array
  - Dual-context RAG pipeline: query embedding -> FAISS search (threshold >= 0.25) -> context injection from BOTH active editor content AND uploaded file chunks
  - RAG-grounded Summarize/Improve: retrieves relevant file chunks for contextual rewrites with inline citations
  - PII sanitization on user input, RAG chunks, document content, AND conversation history (4 interception points)
  - Latency tracing on every AI response (`request_id`, `retrieval_time_ms`, `generation_time_ms`, `tokens_per_second`)
  - Document versioning: auto-creates new version on every update, browsable via API
  - File management: parse -> chunk -> embed -> FAISS index -> SQLite, with toggle on/off for RAG inclusion
  - Lightweight SQLite migrations for backward-compatible schema changes
- **Port**: 8000
- **Volumes**:
  - `backend-data:/data` -- SQLite database, FAISS index, uploaded files
  - `embedding-model:/models` -- Sentence-transformer model files
- **Health Check**: `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"`
- **Configuration** (all env-configurable):
  - `DATABASE_URL` -- SQLite connection string
  - `OLLAMA_BASE_URL` -- Ollama container URL
  - `EMBEDDING_MODEL_PATH` -- Path to embedding model (explicit error if missing in air-gapped mode)
  - `DEFAULT_MODEL` -- Default Ollama model (`llama3.2:1b`)
  - `MAX_CHUNKS_RETRIEVED` -- Top-K chunks for RAG (default: 5)
  - `MIN_SIMILARITY_SCORE` -- Minimum FAISS score threshold (default: 0.25)
  - `MAX_CONVERSATION_HISTORY` -- Messages in multi-turn context (default: 100)

### Ollama (LLM Server)

- **Image**: `ollama/ollama:latest`
- **Responsibilities**:
  - Serve multiple language models (llama3.2:1b, gemma3:1b, llama3.2:1b)
  - Provide `/api/chat` (multi-turn) and `/api/generate` (single-shot) inference APIs
  - Auto-pull models on first boot via `ollama-entrypoint.sh`
  - Create custom `loomin` model from mounted Modelfile (`ollama create loomin -f /Modelfile`)
  - Graceful fallback in air-gapped mode (pre-loaded models from volume)
- **Port**: 11434
- **Volumes**:
  - `ollama-data:/root/.ollama` -- Model weights, manifests
  - `Modelfile:/Modelfile` -- Custom model definition (mounted read-only)
- **Health Check**: `test -f /tmp/.ollama-models-ready` (marker created after all models loaded + custom model created)
- **Entrypoint**: Custom `ollama-entrypoint.sh` starts server, pulls/verifies models, runs `ollama create`, creates readiness marker

## Database Schema (5 Tables)

```mermaid
erDiagram
    Document ||--o{ DocumentVersion : "has versions"
    Document ||--o{ ChatMessage : "has messages"
    UploadedFile ||--o{ FileChunk : "has chunks"

    Document {
        string id PK "UUID"
        string title
        text content "HTML from TipTap"
        datetime created_at
        datetime updated_at
    }

    DocumentVersion {
        int id PK "auto-increment"
        string document_id FK
        text content "HTML snapshot"
        int version_number
        datetime created_at
    }

    ChatMessage {
        int id PK "auto-increment"
        string document_id FK "nullable"
        string role "user or assistant"
        text content
        text metadata_json "trace + citations"
        datetime created_at
    }

    UploadedFile {
        string id PK "UUID"
        string filename
        string file_type ".pdf .md .txt"
        string file_path
        int chunk_count
        boolean is_active "toggle for RAG"
        datetime created_at
    }

    FileChunk {
        int id PK "auto-increment"
        string file_id FK
        int chunk_index
        text content
        int embedding_id "FAISS row mapping"
    }
```

### Schema Migrations

The application uses lightweight SQLite-specific migrations (no Alembic dependency). On startup, `init_db()` creates tables via `metadata.create_all`, then runs `_run_migrations()` which uses `PRAGMA table_info` to detect missing columns and adds them via `ALTER TABLE`. This ensures backward compatibility when upgrading an existing database (e.g., adding the `is_active` column to `uploaded_files`).

## Dual Deployment Strategy

| Aspect | Development (Internet) | Air-Gapped (RHEL 9) |
|--------|----------------------|---------------------|
| Compose file | `docker-compose.yml` (with `build:` directives) | `docker-compose.prod.yml` (image-only, no build) |
| Images | Built from source via `docker compose up --build` | Pre-loaded from `.tar` via `docker load -i` |
| Ollama models | Pulled from registry on first boot | Pre-loaded in `ollama-data` volume by `setup.sh` |
| Custom model | Created via `ollama create loomin -f /Modelfile` | Same -- Modelfile mounted from package |
| Embedding model | Auto-downloaded from HuggingFace if missing | Pre-loaded in `embedding-model` volume by `setup.sh` |
| Docker RPMs | Already installed | Installed from bundled RPMs by `setup.sh` |

## Data Flow Diagrams

### Multi-Turn Chat with RAG (Dual Context)

```mermaid
sequenceDiagram
    participant U as User Browser
    participant FE as Nginx (Frontend)
    participant BE as FastAPI (Backend)
    participant DB as SQLite
    participant EMB as Embedding Model
    participant FX as FAISS Index
    participant OL as Ollama (LLM)

    U->>FE: POST /api/chat {message, document_id, model, document_content}
    FE->>BE: Proxy to :8000/api/chat

    Note over BE: 1. Sanitize user input (PII)
    Note over BE: 2. Sanitize document_content (PII)
    BE->>DB: Persist user message
    BE->>DB: Fetch last N conversation messages
    DB-->>BE: Chat history (up to MAX_CONVERSATION_HISTORY)

    BE->>EMB: Encode query to vector
    EMB-->>BE: Query embedding [384-dim]

    BE->>FX: Similarity search (top-k=5, threshold >= 0.25, active files only)
    FX-->>BE: Ranked chunks with scores

    Note over BE: 3. Sanitize RAG chunks (PII)
    Note over BE: 4. Sanitize history messages (PII)
    Note over BE: 5. Build prompt:<br/>[file inventory + doc context + file chunks + question]

    BE->>OL: POST /api/chat {model, messages[], stream: true}
    OL-->>BE: Streamed tokens (SSE)

    BE-->>FE: SSE: {token: "..."} ... {done: true, metadata: {citations, trace}}
    FE-->>U: Display streaming response with inline citation badges

    BE->>DB: Persist assistant response + metadata_json
```

### Document Upload and Indexing

```mermaid
sequenceDiagram
    participant U as User Browser
    participant FE as Nginx (Frontend)
    participant BE as FastAPI (Backend)
    participant FS as File Storage
    participant EMB as Embedding Model
    participant FX as FAISS Index
    participant DB as SQLite

    U->>FE: POST /api/files/upload (multipart)
    FE->>BE: Proxy (client_max_body_size: 100M)

    Note over BE: 1. Validate type (.pdf/.md/.txt) + size (50MB)
    Note over BE: 2. Check for duplicate filename (409 if exists)

    BE->>FS: Save to /data/uploads/{uuid}.ext
    Note over BE: 3. Parse file (PyMuPDF 3-strategy for PDF, UTF-8 for text)
    Note over BE: 4. Chunk text (375 words target, 38-word overlap)

    loop For each chunk
        BE->>EMB: Encode chunk to vector (L2-normalized)
        EMB-->>BE: Chunk embedding [384-dim]
        BE->>FX: Add to FAISS IndexFlatIP
        BE->>DB: Store FileChunk (file_id, chunk_index, content, embedding_id)
    end

    BE->>FX: Save index to disk
    BE->>DB: Create UploadedFile record (is_active=true)
    BE-->>FE: {id, filename, file_type, chunk_count, is_active}
    FE-->>U: Upload success + file appears in Files tab with toggle
```

### Contextual Editing (Summarize / Improve) with RAG Grounding

```mermaid
sequenceDiagram
    participant U as User Browser
    participant FE as Nginx (Frontend)
    participant BE as FastAPI (Backend)
    participant EMB as Embedding Model
    participant FX as FAISS Index
    participant OL as Ollama (LLM)

    U->>U: Select text in editor
    U->>FE: Click "Summarize" or "Improve" (BubbleMenu or sidebar)

    FE->>BE: POST /api/chat/summarize {text, model}
    Note over BE: 1. Sanitize selected text (PII)

    BE->>EMB: Encode selected text to vector
    EMB-->>BE: Query embedding [384-dim]
    BE->>FX: Search for relevant file chunks (active files only)
    FX-->>BE: Ranked reference chunks

    Note over BE: 2. Build prompt with reference context + citation instructions
    BE->>OL: POST /api/generate {prompt, model, system}
    OL-->>BE: Full response (non-streaming)

    BE-->>FE: {summary, model, trace: {citations, timing}}
    FE->>FE: Show suggestion in chat with Accept/Discard buttons
    FE->>FE: Display citation badges from trace.citations
    U->>FE: Click "Apply to document"
    FE->>FE: Replace selected text in TipTap editor
    FE-->>U: Document updated + confirmation message
```

### Real-Time Collaboration Presence

```mermaid
sequenceDiagram
    participant A as User A
    participant FE as Nginx
    participant BE as FastAPI (PresenceManager)
    participant B as User B

    A->>FE: WebSocket /ws/collaborate/{doc_id}
    FE->>BE: Upgrade connection
    BE-->>A: {type: "presence_state", your_id, your_color, users: [A]}

    B->>FE: WebSocket /ws/collaborate/{doc_id}
    FE->>BE: Upgrade connection
    BE-->>B: {type: "presence_state", your_id, your_color, users: [A, B]}
    BE-->>A: {type: "user_joined", user: B, users: [A, B]}

    A->>BE: {type: "cursor_move", pos: 42}
    BE-->>B: {type: "cursor_update", user_id: A, cursor_pos: 42}

    B->>BE: Connection closed
    BE-->>A: {type: "user_left", user_id: B, users: [A]}
```

## Security Considerations

### PII Sanitization Flow

PII sanitization is applied at **four points** in the pipeline:

```mermaid
flowchart LR
    A["User Message"] --> B["sanitize()"]
    C["RAG Chunks"] --> D["sanitize()"]
    E["Chat History"] --> F["sanitize()"]
    G["Document Content"] --> H["sanitize()"]
    B --> I["Build Messages Array"]
    D --> I
    F --> I
    H --> I
    I --> J["Ollama /api/chat"]
    J --> K["LLM Response"]
    K --> L["User (via SSE)"]
```

**Detected PII patterns (6 types):**

| Pattern           | Example                     | Replacement           |
|-------------------|-----------------------------|-----------------------|
| SSN               | `123-45-6789`               | `[SSN-REDACTED]`      |
| Credit Card       | `4111-1111-1111-1111`       | `[CC-REDACTED]`       |
| AWS Key           | `AKIA1234567890ABCDEF`      | `[AWS-KEY-REDACTED]`  |
| API Key           | `sk-abc123...`              | `[API-KEY-REDACTED]`  |
| Email             | `user@example.com`          | `[EMAIL-REDACTED]`    |
| Phone             | `(503) 555-0142`            | `[PHONE-REDACTED]`    |

### RAG Faithfulness Enforcement (3 layers)

```
Layer 1: RETRIEVAL FILTERING
  FAISS search -> only chunks with score >= 0.25 pass
  Only chunks from is_active=true files are returned

Layer 2: PROMPT ENGINEERING
  With context:    "Answer using ONLY the context above (current document and/or uploaded files)"
  Without context: "No files uploaded / no relevant content found -- do NOT answer from training"
  Summarize/Improve: "Use reference context to ensure factual accuracy. Cite [Source N]"

Layer 3: SYSTEM PROMPT (7 rules, always active)
  Rule 1: ONLY use provided context (document content + uploaded files)
  Rule 2: NEVER use training knowledge for factual questions
  Rule 3: Cite [Source N] when referencing uploaded files
  Rule 4: Use CURRENT DOCUMENT section for document questions
  Rule 5: Say "I don't have information" if not in context
  Rule 6: Tell user to upload files or write content if no context
  Rule 7: Be concise, helpful, and professional
```

### Network Isolation

- Docker bridge network (`loomin-net`) is internal only
- In air-gapped environment, the host has no outbound internet
- Ports 8000 and 11434 can be restricted to `127.0.0.1` in production
- WebSocket connections proxied through Nginx (no direct backend exposure)

## Token Estimation

Token counts are estimated using a hybrid heuristic for robustness across text types:

```
estimate = max(char_count / 4, word_count * 1.3)
```

- **Character-based** (`char_count / 4`): Standard for English prose with GPT/Llama tokenizers (~4 chars per token)
- **Word-based** (`word_count * 1.3`): Cross-check for shorter texts where character count underestimates
- The segmented token bar breaks down: **document tokens** (from editor content) + **file chunk tokens** (from active uploaded files) + **free tokens** (remaining context window)

Context window sizes are resolved from a built-in model lookup table with prefix matching (e.g., `llama3.2:1b` -> 131072 tokens).

## Performance Characteristics

| Operation                  | Expected Latency       | Bottleneck                    |
|----------------------------|------------------------|-------------------------------|
| Document upload (1 MB)     | 2-5 seconds            | Text extraction + embedding   |
| FAISS similarity search    | < 50 ms                | In-memory vector search       |
| Embedding a query          | 20-100 ms              | CPU-bound model inference     |
| LLM response (first token) | 1-5 seconds           | Model loading / prompt eval   |
| LLM response (streaming)  | 10-60 seconds total    | Token generation speed        |
| WebSocket presence event   | < 10 ms                | In-memory broadcast           |
| Version history fetch      | < 50 ms                | SQLite query                  |

### Resource Requirements

| Resource | Minimum     | Recommended  | Notes                                |
|----------|-------------|--------------|--------------------------------------|
| CPU      | 4 cores     | 8+ cores     | LLM inference is CPU-intensive       |
| RAM      | 8 GB        | 16+ GB       | Multiple models loaded concurrently  |
| Disk     | 20 GB       | 50+ GB       | Model weights + document storage     |
| GPU      | Not required | NVIDIA GPU  | Dramatically improves LLM speed      |

## Volume Layout

```
backend-data (/data)
├── loomin.db                    # SQLite (documents, versions, chat, files, chunks)
├── faiss_index/
│   └── index.faiss              # Serialized FAISS IndexFlatIP
└── uploads/
    ├── {uuid}.pdf
    ├── {uuid}.md
    └── {uuid}.txt

embedding-model (/models)
└── all-MiniLM-L6-v2/           # Sentence-transformers model
    ├── config.json
    ├── tokenizer.json
    ├── model.safetensors
    └── ...

ollama-data (/root/.ollama)
└── models/
    ├── blobs/                   # Model weight files (SHA256)
    └── manifests/               # Model metadata
        └── registry.ollama.ai/
            └── library/
                ├── llama3.2/
                ├── gemma3/
                └── gemma3/
```

## Modelfile

The custom `loomin` model is created automatically at container startup via `ollama create loomin -f /Modelfile`. The Modelfile is mounted from `backend/Modelfile` into the Ollama container.

```
FROM llama3.2:1b
SYSTEM """7-rule RAG faithfulness prompt..."""
PARAMETER temperature 0.7
PARAMETER top_p 0.9
```

The same system prompt is also injected at the API level in `chat.py` for all models (not just `loomin`), ensuring consistent behavior regardless of which model the user selects.

## Nginx Proxy Configuration

```
/           -> Static React SPA (try_files with SPA fallback)
/api/*      -> Backend :8000 (HTTP 1.1, buffering off, 600s timeout)
/ws/*       -> Backend :8000 (WebSocket upgrade, 86400s timeout)
```

- `client_max_body_size 100M` for file uploads
- WebSocket proxy uses `Connection: "upgrade"` header with 24-hour idle timeout
- API proxy disables buffering and caching for SSE streaming compatibility
