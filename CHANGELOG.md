# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Optional LangGraph RAG pipeline** (`app/rag/graph.py`), behind the `USE_LANGGRAPH` flag (default `false`). When enabled, `/api/chat` routes through an explicit graph — a prep graph (retrieve → inventory → build prompt) that runs eagerly, then a streaming generation graph — while producing output, SSE framing, and error semantics identical to the original inline pipeline. The graph reuses the project's own retriever, embedder, and Ollama client (no `langchain-ollama` dependency) and is the foundation for future retrieval-quality nodes (query rewrite, reranking, document grading). Backward compatible: with the flag off, `langgraph` is not imported and the original code path is unchanged.
- First backend test suite (`backend/tests/`): prompt-parity, graph-unit (streaming, citations, message assembly, generation-error handling), a backward-compat guard that retrieval failures still raise (HTTP 500, not a degraded 200 stream), and route-level SSE tests covering both the legacy and LangGraph paths.
- `backend/requirements-dev.txt` and `backend/pytest.ini` for the test toolchain.
- MIT `LICENSE`.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), and `SECURITY.md` with a documented threat model.
- `.env.example` covering every supported setting.
- GitHub issue templates, pull request template, and Dependabot configuration.
- Continuous integration: `ruff` lint, `pytest`, and bytecode compilation for the backend, TypeScript build for the frontend, and Docker image builds.
- `.editorconfig`.

### Changed
- Group Dependabot updates by ecosystem and library family (TipTap, React, build tooling) so routine bumps arrive as a handful of pull requests instead of one per dependency. The first unguarded run opened 17 at once. Major bumps stay ungrouped so breaking changes are reviewed individually.
- Rewrote `README.md` for an open-source audience: badges, table of contents, local development instructions without Docker, hardware expectations, roadmap, and license notes for bundled models.
- Corrected `README.md` and `ARCHITECTURE.md` to describe only what the code actually implements (see Removed).

### Fixed
- Duplicate `llama3.2:1b` entry in the documented model list; the shipped models are `llama3.2:1b` and `gemma3:1b`.
- `deploy/Makefile` no longer exposes a `test-rag` target pointing at a `tests/verify_rag.py` that does not exist in the repository.

### Removed
- Documentation claims for features that were never implemented. Real-time WebSocket collaboration presence (`/ws/collaborate/{doc_id}`, `PresenceManager`, `usePresence.ts`, presence avatars, the Nginx `/ws/*` proxy) is not in the codebase, and the Ollama entrypoint deliberately does not run `ollama create loomin` — the system prompt is applied at the API level in `chat.py` for all models instead. These are now tracked under Roadmap rather than described as shipped.

## [1.0.0]

### Added
- TipTap rich text editor with a formatting toolbar, auto-save, and `.txt` / `.md` / `.html` export.
- Document versioning with browse, preview, and restore from the History tab.
- Three-tab AI sidebar (Chat, Files, History) with multi-turn conversation and SSE token streaming.
- Dual-context RAG over the active document and uploaded files, backed by FAISS `IndexFlatIP` and `all-MiniLM-L6-v2` embeddings.
- RAG-grounded Summarize and Improve with `[Source N]` citations and an Accept/Discard review step.
- File upload for `.pdf`, `.md`, and `.txt` with chunk previews and per-file toggling of RAG inclusion.
- Ollama model selector with conversation history preserved across model switches.
- Segmented token visualization and per-response latency tracing.
- Regex-based PII sanitization at four interception points before text reaches the LLM.
- Docker Compose orchestration with health-check gating, plus `sideload.sh` and `setup.sh` for air-gapped RHEL 9 deployment.

[Unreleased]: https://github.com/smdsheriff/loomin-docs/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/smdsheriff/loomin-docs/releases/tag/v1.0.0
