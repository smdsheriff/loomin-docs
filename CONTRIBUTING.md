# Contributing to Loomin-Docs

Thanks for taking the time to contribute. Loomin-Docs is a small project, so almost any well-scoped improvement is welcome — bug fixes, documentation, and especially the missing test suite.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Ways to Contribute

- **Report a bug** — open an issue using the Bug Report template. Include your OS, Docker version, and the relevant container logs.
- **Suggest a feature** — open an issue using the Feature Request template. Explain the problem before the solution.
- **Improve documentation** — typos, unclear setup steps, and missing context all count. Docs-only PRs are always welcome.
- **Write code** — see [Roadmap](README.md#roadmap) in the README for the highest-impact areas. The test suite and frontend linting are the best starting points.

If you're planning a large change, open an issue first so we can agree on the approach before you spend time on it.

---

## Development Setup

### Option A — Docker (closest to production)

```bash
git clone https://github.com/smdsheriff/loomin-docs.git
cd loomin-docs/deploy
docker compose up --build
```

The app comes up on <http://localhost>. Rebuild after backend changes with `docker compose up --build backend`.

### Option B — Run services directly (fastest iteration)

You need an Ollama server running with at least one model pulled:

```bash
ollama serve &
ollama pull llama3.2:1b
```

**Backend:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env     # edit the paths for non-container use
uvicorn app.main:app --reload --port 8000
```

The defaults in `config.py` point at `/data`, which only exists inside the container. For local runs override them in `.env`:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./loomin.db
FAISS_INDEX_PATH=./.local/faiss_index
UPLOAD_DIR=./.local/uploads
OLLAMA_BASE_URL=http://localhost:11434
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000, proxies /api to :8000
```

---

## Project Layout

See [Project Structure](README.md#project-structure) in the README for the annotated tree, and [ARCHITECTURE.md](ARCHITECTURE.md) for data flows, the database schema, and the RAG pipeline. Reading ARCHITECTURE.md before touching `backend/app/rag/` or `backend/app/api/routes/chat.py` will save you time.

---

## Coding Conventions

### Python (backend)

- Target Python 3.11. Type-annotate function signatures; the codebase uses them consistently.
- Async all the way down — routes, database access (`aiosqlite`), and the Ollama client are async. Don't introduce blocking I/O into a request path.
- Keep module docstrings and the existing comment style. Section dividers like `# ── Routers ──` are used in `main.py`; match the local file's conventions rather than imposing new ones.
- Configuration belongs in `core/config.py` as a `Settings` field, never as a hard-coded literal in a route.
- Anything user-supplied that reaches the LLM must pass through `core/pii.py` sanitization.

We keep [ruff](https://docs.astral.sh/ruff/) clean in CI:

```bash
pip install ruff
ruff check backend/
```

### TypeScript / React (frontend)

- Functional components with hooks. No class components.
- Shared types live in `src/types/index.ts` — add to it rather than redeclaring shapes locally.
- All network calls go through `src/services/api.ts`; React state lives in `src/hooks/useApi.ts`. Don't call `fetch` from a component.
- Styling is TailwindCSS utility classes inline. There is no CSS-in-JS layer.
- Use the `@/` path alias for imports from `src/`.

The type checker must pass:

```bash
cd frontend
npm run build     # runs tsc && vite build
```

### Commits

Write in the imperative mood and explain *why* rather than restating the diff:

```
Add similarity-score threshold to retriever

Low-scoring chunks were being injected as context, which let the model
answer from noise. Filter below MIN_SIMILARITY_SCORE before prompt assembly.
```

Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `chore:`) are welcome but not required.

---

## Testing

**There is currently no automated test suite** — this is the project's biggest gap, and contributions here are especially valuable. If you're adding one:

- Backend: `pytest` with `pytest-asyncio` and `httpx.AsyncClient`. High-value targets are `core/pii.py` (regex correctness and offset tracking), `services/document.py` (chunking boundaries and overlap), and `rag/retriever.py` (threshold filtering and active-file scoping).
- Frontend: `vitest` plus `@testing-library/react`.

Put backend tests in `backend/tests/` and wire them into [.github/workflows/ci.yml](.github/workflows/ci.yml).

Until then, please verify changes manually and say what you tested in your PR description:

1. Start the stack and confirm all three services pass `make health`.
2. Create a document, type into it, and confirm auto-save plus a new entry in the History tab.
3. Upload a PDF, ask a question about it, and confirm the answer cites `[Source N]`.
4. Toggle that file off and confirm the assistant no longer uses it.
5. Select text and run Summarize; confirm Accept and Discard both behave.

---

## Pull Request Process

1. Fork the repository and branch from `main`. Use `feature/short-description`, `fix/short-description`, or `docs/short-description`.
2. Make your change. Keep the PR focused — one concern per pull request.
3. Confirm `ruff check backend/` and `npm run build` both pass.
4. Update the docs when behavior changes. A new environment variable belongs in `README.md`, `.env.example`, and `ARCHITECTURE.md`.
5. Fill in the PR template, including how you tested.
6. Open the PR against `main`. CI must be green before review.

Please don't commit build artifacts, `node_modules/`, virtualenvs, `.db` or `.faiss` files, or anything from `deploy/package/` — `.gitignore` covers these, but double-check `git status` before committing.

### Review

Expect a first response within a week. Reviews focus on correctness, whether the change fits the existing architecture, and doc accuracy. Small follow-up requests are normal and not a rejection.

---

## Reporting Security Issues

Do **not** open a public issue for a vulnerability. Follow the process in [SECURITY.md](SECURITY.md).

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers this project.
