"""LangGraph orchestration of the RAG chat pipeline.

This is a faithful re-expression of the inline pipeline in
``app/api/routes/chat.py`` as an explicit graph. It deliberately does **not**
change behavior: given the same inputs it produces the same prompt, the same
token stream, and the same trace metadata. The graph exists so future
capabilities (query rewriting, reranking, document grading, self-correction
loops) can be added as nodes and conditional edges without rewriting the
request handler.

Design notes
------------
* **No LangChain model wrapper.** The generate node calls the project's own
  ``ollama_service`` directly, so no ``langchain-ollama`` dependency is pulled
  in and the existing connection/timeout handling is reused verbatim.
* **Streaming.** The generate node emits tokens through LangGraph's custom
  stream channel (``get_stream_writer``). The caller consumes them with
  ``graph.astream(..., stream_mode=["custom", "values"])`` — ``custom`` carries
  per-token dicts, ``values`` carries state snapshots whose last value holds the
  final citations/metadata.
* **Request-scoped objects in state.** The live SQLAlchemy session and the
  ``RequestTrace`` are passed through graph state. This is safe because the
  graph is compiled without a checkpointer, so state is an in-memory dict that
  is never serialized.
"""

import logging
from typing import Any, AsyncGenerator, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter
from sqlalchemy import select

from app.core.config import settings
from app.core.pii import sanitize
from app.models.database import UploadedFile
from app.rag.prompting import SYSTEM_PROMPT, build_rag_prompt
from app.rag.retriever import retrieve_relevant_chunks
from app.services.ollama import ollama_service

logger = logging.getLogger(__name__)


class ChatGraphState(TypedDict, total=False):
    """State channels for the chat graph.

    Inputs are populated by the caller before invocation; the remaining fields
    are filled in by the nodes as the graph runs.
    """

    # ── Inputs (set by caller) ───────────────────────────────────────────
    user_message: str            # PII-sanitized user query
    document_id: Optional[str]
    model: str
    document_content: Optional[str]  # PII-sanitized editor content, or None
    history: list[dict]          # prior turns, PII-sanitized, excludes current msg
    redactions: int              # count of PII redactions in the user message
    session: Any                 # AsyncSession (request-scoped, not serialized)
    trace: Any                   # RequestTrace (carried through, not serialized)

    # ── Working state (set by nodes) ─────────────────────────────────────
    chunks: list[dict]           # retrieved + sanitized RAG chunks
    available_files: list[dict]  # uploaded file inventory
    current_prompt: str          # the RAG-assembled user turn
    messages: list[dict]         # full messages array sent to Ollama

    # ── Outputs (set by generate node) ───────────────────────────────────
    full_response: str
    citations: list[dict]
    metadata: dict


async def _retrieve_node(state: ChatGraphState) -> dict:
    """Embed the query, search FAISS, and PII-sanitize the retrieved chunks."""
    trace = state["trace"]
    session = state["session"]

    with trace.trace_retrieval():
        chunks = await retrieve_relevant_chunks(
            state["user_message"], session, top_k=settings.MAX_CHUNKS_RETRIEVED
        )
    trace.chunks_retrieved = len(chunks)

    chunk_dicts = [c.model_dump() for c in chunks]
    # Uploaded files may contain PII — sanitize before it reaches the model
    for chunk in chunk_dicts:
        chunk["chunk_text"], _ = sanitize(chunk["chunk_text"])

    return {"chunks": chunk_dicts}


async def _inventory_node(state: ChatGraphState) -> dict:
    """Load the uploaded-file inventory so the model knows what exists."""
    session = state["session"]
    stmt = select(
        UploadedFile.filename, UploadedFile.file_type, UploadedFile.chunk_count
    ).order_by(UploadedFile.created_at.desc())
    result = await session.execute(stmt)
    available_files = [
        {"name": row[0], "type": row[1], "chunks": row[2]} for row in result.all()
    ]
    return {"available_files": available_files}


def _build_prompt_node(state: ChatGraphState) -> dict:
    """Assemble the RAG prompt and the full messages array for Ollama."""
    current_prompt = build_rag_prompt(
        state["user_message"],
        state["chunks"],
        state["available_files"],
        state.get("document_content"),
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(state.get("history", []))
    messages.append({"role": "user", "content": current_prompt})

    return {"current_prompt": current_prompt, "messages": messages}


async def _generate_node(state: ChatGraphState, writer: StreamWriter) -> dict:
    """Stream tokens from Ollama, then assemble citations and trace metadata.

    ``writer`` is injected by LangGraph (declared as a ``StreamWriter``
    parameter); calling it routes items to the ``custom`` stream channel that
    the caller consumes via ``astream(stream_mode="custom")``.
    """
    trace = state["trace"]
    model = state["model"]

    full_response: list[str] = []
    token_count = 0

    try:
        with trace.trace_generation():
            async for token in ollama_service.chat_stream(
                messages=state["messages"], model=model
            ):
                full_response.append(token)
                token_count += 1
                writer({"token": token})
    except Exception as exc:  # noqa: BLE001 — mirror legacy: surface as an error token
        logger.error("Stream generation failed: %s", exc)
        writer({"token": f"[Error: {exc}]"})

    trace.tokens_generated = token_count

    citations = [
        {
            "source_file": c["source_file"],
            "chunk_index": c["chunk_index"],
            "score": c["score"],
            "text": c["chunk_text"][:200],
        }
        for c in state["chunks"]
    ]

    metadata = {
        **trace.to_dict(),
        "citations": citations,
        "pii_redactions": state.get("redactions", 0),
    }

    return {
        "full_response": "".join(full_response),
        "citations": citations,
        "metadata": metadata,
    }


def build_prep_graph() -> StateGraph:
    """Construct the preparation graph: retrieve → inventory → build_prompt.

    This runs to completion *before* streaming begins, so a failure here (e.g. a
    missing FAISS index) propagates as an exception — matching the legacy path,
    which performs retrieval in the request handler body and returns HTTP 500 on
    error rather than swallowing it into a 200 stream.

    New retrieval-quality nodes (query rewrite, rerank, document grading) slot in
    between ``retrieve`` and ``build_prompt`` here.
    """
    graph = StateGraph(ChatGraphState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("inventory", _inventory_node)
    graph.add_node("build_prompt", _build_prompt_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "inventory")
    graph.add_edge("inventory", "build_prompt")
    graph.add_edge("build_prompt", END)
    return graph


def build_generation_graph() -> StateGraph:
    """Construct the generation graph: a single streaming ``generate`` node."""
    graph = StateGraph(ChatGraphState)
    graph.add_node("generate", _generate_node)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    return graph


# Compile once at import; both compiled graphs are stateless and reusable.
prep_graph = build_prep_graph().compile()
generation_graph = build_generation_graph().compile()


async def prepare_chat_state(initial_state: ChatGraphState) -> dict:
    """Run retrieval, inventory, and prompt assembly eagerly.

    Returns the merged state (including the assembled ``messages``). Raises if
    any prep step fails — the caller runs this while the request-scoped DB
    session is still open, so exceptions surface as HTTP 500 exactly as in the
    legacy pipeline (no partial SSE stream, no persisted assistant row).
    """
    return await prep_graph.ainvoke(initial_state)


async def stream_generation(
    state: ChatGraphState,
) -> AsyncGenerator[dict, None]:
    """Stream generation from prepared state and yield normalized events.

    Yields:
      * ``{"type": "token", "token": "<piece>"}`` for each generated token
      * ``{"type": "final", "metadata": {...}, "full_response": "<text>"}`` once,
        after generation completes (even if generation raised — the generate
        node catches errors and still produces full metadata).
    """
    final_state: dict = {}

    async for mode, chunk in generation_graph.astream(
        state, stream_mode=["custom", "values"]
    ):
        if mode == "custom":
            # chunk is the dict passed to writer(), e.g. {"token": "..."}
            token = chunk.get("token")
            if token is not None:
                yield {"type": "token", "token": token}
        elif mode == "values":
            # state snapshot after each node; keep the latest
            final_state = chunk

    yield {
        "type": "final",
        "metadata": final_state.get("metadata", {}),
        "full_response": final_state.get("full_response", ""),
    }
