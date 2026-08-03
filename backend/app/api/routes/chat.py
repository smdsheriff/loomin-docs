import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.pii import sanitize
from app.core.tracing import RequestTrace
from app.models.database import ChatMessage, UploadedFile, async_session, get_session
from app.models.schemas import (
    ChatMessageResponse,
    ChatRequest,
    ImproveRequest,
    ImproveResponse,
    PersistMessageRequest,
    SummarizeRequest,
    SummarizeResponse,
)
from app.rag.prompting import SYSTEM_PROMPT, build_rag_prompt
from app.rag.retriever import retrieve_relevant_chunks
from app.services.ollama import ollama_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

# Prompt construction lives in app.rag.prompting so the legacy pipeline and the
# LangGraph pipeline share one source of truth. Aliased here to keep the module
# names used below unchanged.
_SYSTEM_PROMPT = SYSTEM_PROMPT
_build_rag_prompt = build_rag_prompt


@router.post("")
async def chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an SSE response with multi-turn conversation context + RAG."""
    trace = RequestTrace()
    model = body.model or settings.DEFAULT_MODEL
    trace.model = model

    # Sanitize user message
    sanitized_message, redactions = sanitize(body.message)

    # Persist user message
    user_msg = ChatMessage(
        document_id=body.document_id,
        role="user",
        content=body.message,
    )
    session.add(user_msg)
    await session.commit()

    # Fetch recent conversation history for multi-turn context
    history_stmt = (
        select(ChatMessage)
        .where(ChatMessage.document_id == body.document_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.MAX_CONVERSATION_HISTORY)
    )
    history_result = await session.execute(history_stmt)
    # Reverse to chronological order (query returns newest first)
    history_messages = list(reversed(history_result.scalars().all()))

    # Route through the LangGraph pipeline when enabled. Behavior and SSE framing
    # are identical to the legacy path below; the flag exists for safe rollout.
    if settings.USE_LANGGRAPH:
        return await _chat_via_graph(
            body, session, trace, sanitized_message, redactions, history_messages, model
        )

    # Retrieve relevant chunks via RAG
    with trace.trace_retrieval():
        chunks = await retrieve_relevant_chunks(
            sanitized_message, session, top_k=settings.MAX_CHUNKS_RETRIEVED
        )
    trace.chunks_retrieved = len(chunks)

    chunk_dicts = [c.model_dump() for c in chunks]

    # Sanitize retrieved chunks — uploaded files may contain PII
    for chunk in chunk_dicts:
        chunk["chunk_text"], _ = sanitize(chunk["chunk_text"])

    # Query uploaded file inventory
    file_list_stmt = select(UploadedFile.filename, UploadedFile.file_type, UploadedFile.chunk_count).order_by(UploadedFile.created_at.desc())
    file_list_result = await session.execute(file_list_stmt)
    available_files = [
        {"name": row[0], "type": row[1], "chunks": row[2]}
        for row in file_list_result.all()
    ]

    # Sanitize document content if provided
    sanitized_doc_content = None
    if body.document_content:
        sanitized_doc_content, _ = sanitize(body.document_content)

    # Build the current user message with RAG context
    current_prompt = _build_rag_prompt(
        sanitized_message, chunk_dicts, available_files, sanitized_doc_content
    )

    # Assemble multi-turn messages array for Ollama /api/chat
    ollama_messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]

    # Add conversation history (PII-sanitized, excluding the just-persisted user msg)
    for msg in history_messages[:-1]:  # exclude the last one (current user msg)
        sanitized_hist, _ = sanitize(msg.content)
        ollama_messages.append({"role": msg.role, "content": sanitized_hist})

    # Add current user message with RAG context
    ollama_messages.append({"role": "user", "content": current_prompt})

    async def event_stream():
        full_response: list[str] = []
        token_count = 0

        try:
            with trace.trace_generation():
                async for token in ollama_service.chat_stream(
                    messages=ollama_messages, model=model
                ):
                    full_response.append(token)
                    token_count += 1
                    event_data = json.dumps({"token": token})
                    yield f"data: {event_data}\n\n"
        except Exception as exc:
            logger.error("Stream generation failed: %s", exc)
            yield f"data: {json.dumps({'token': f'[Error: {exc}]'})}\n\n"

        trace.tokens_generated = token_count

        # Build citations from retrieved chunks
        citations = [
            {
                "source_file": c["source_file"],
                "chunk_index": c["chunk_index"],
                "score": c["score"],
                "text": c["chunk_text"][:200],
            }
            for c in chunk_dicts
        ]

        # Send final metadata event
        metadata = {
            **trace.to_dict(),
            "citations": citations,
            "pii_redactions": len(redactions),
        }
        yield f"data: {json.dumps({'done': True, 'metadata': metadata})}\n\n"

        # Persist assistant message with fresh session
        try:
            async with async_session() as persist_session:
                assistant_msg = ChatMessage(
                    document_id=body.document_id,
                    role="assistant",
                    content="".join(full_response),
                    metadata_json=json.dumps(metadata),
                )
                persist_session.add(assistant_msg)
                await persist_session.commit()
        except Exception as exc:
            logger.error("Failed to persist assistant message: %s", exc)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _chat_via_graph(
    body: ChatRequest,
    session: AsyncSession,
    trace: RequestTrace,
    sanitized_message: str,
    redactions: list,
    history_messages: list,
    model: str,
) -> StreamingResponse:
    """LangGraph-backed equivalent of ``chat``'s streaming body.

    Mirrors the legacy path's structure and error semantics:

    * Retrieval, inventory, and prompt assembly run **eagerly here** (via the
      prep graph) using the still-open request-scoped ``session``. A failure in
      this phase propagates as HTTP 500 with nothing persisted — identical to
      the legacy pipeline, which does retrieval before returning the stream.
    * Only token generation streams inside the response body. Assistant
      persistence uses a fresh ``async_session()`` because the request session
      is closed once ``StreamingResponse`` is returned.
    """
    # Lazy import so the (default) legacy path never requires langgraph.
    from app.rag.graph import prepare_chat_state, stream_generation

    # Sanitized prior turns, excluding the just-persisted current user message
    history_payload: list[dict[str, str]] = []
    for msg in history_messages[:-1]:
        sanitized_hist, _ = sanitize(msg.content)
        history_payload.append({"role": msg.role, "content": sanitized_hist})

    sanitized_doc_content = None
    if body.document_content:
        sanitized_doc_content, _ = sanitize(body.document_content)

    initial_state = {
        "user_message": sanitized_message,
        "document_id": body.document_id,
        "model": model,
        "document_content": sanitized_doc_content,
        "history": history_payload,
        "redactions": len(redactions),
        "session": session,
        "trace": trace,
    }

    # Eager prep — failures propagate as HTTP 500 (matches legacy), before any
    # streaming begins and before any assistant row is written.
    prepared_state = await prepare_chat_state(initial_state)

    async def event_stream():
        full_response = ""
        metadata: dict = {}

        async for event in stream_generation(prepared_state):
            if event["type"] == "token":
                yield f"data: {json.dumps({'token': event['token']})}\n\n"
            elif event["type"] == "final":
                metadata = event["metadata"]
                full_response = event["full_response"]
                yield f"data: {json.dumps({'done': True, 'metadata': metadata})}\n\n"

        # Persist assistant message with a fresh session (mirrors legacy path)
        try:
            async with async_session() as persist_session:
                assistant_msg = ChatMessage(
                    document_id=body.document_id,
                    role="assistant",
                    content=full_response,
                    metadata_json=json.dumps(metadata),
                )
                persist_session.add(assistant_msg)
                await persist_session.commit()
        except Exception as exc:
            logger.error("Failed to persist assistant message: %s", exc)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _get_rag_context_for_action(
    text: str,
    session: AsyncSession,
    trace: RequestTrace,
) -> tuple[str, list[dict]]:
    """Retrieve RAG context relevant to the selected text for summarize/improve."""
    sanitized_text, _ = sanitize(text)

    with trace.trace_retrieval():
        chunks = await retrieve_relevant_chunks(
            sanitized_text, session, top_k=settings.MAX_CHUNKS_RETRIEVED
        )
    trace.chunks_retrieved = len(chunks)

    chunk_dicts = [c.model_dump() for c in chunks]
    for chunk in chunk_dicts:
        chunk["chunk_text"], _ = sanitize(chunk["chunk_text"])

    # Build a compact context block from retrieved chunks
    if not chunk_dicts:
        return "", []

    context_parts: list[str] = []
    for i, chunk in enumerate(chunk_dicts, 1):
        source = chunk["source_file"]
        context_parts.append(f"[Source {i}: {source}]\n{chunk['chunk_text']}")
    context_block = "\n\n".join(context_parts)

    citations = [
        {
            "source_file": c["source_file"],
            "chunk_index": c["chunk_index"],
            "score": c["score"],
            "text": c["chunk_text"][:200],
        }
        for c in chunk_dicts
    ]

    return context_block, citations


@router.post("/summarize")
async def summarize(
    body: SummarizeRequest,
    session: AsyncSession = Depends(get_session),
) -> SummarizeResponse:
    """Summarize the provided text using the LLM, grounded in uploaded file context."""
    trace = RequestTrace()
    model = body.model or settings.DEFAULT_MODEL
    trace.model = model

    sanitized_text, _ = sanitize(body.text)

    # Retrieve relevant RAG context to ground the summary
    rag_context, citations = await _get_rag_context_for_action(body.text, session, trace)

    rag_section = ""
    if rag_context:
        rag_section = (
            "\n\nUse the following reference context from uploaded files to ensure "
            "factual accuracy. Cite sources using [Source N] if you use them:\n"
            f"--- REFERENCE CONTEXT ---\n{rag_context}\n--- END REFERENCE ---\n"
        )

    prompt = (
        "IMPORTANT: Return ONLY the summarized text. "
        "Do NOT include any preamble, introduction, explanation, or commentary like "
        "'Here is the summary' or 'Based on the provided text'. "
        "Just output the summary directly. Include [Source N] citations inline "
        "if you reference facts from the reference context.\n\n"
        "Summarize the following text concisely, preserving all key information:\n\n"
        f"{sanitized_text}"
        f"{rag_section}"
    )

    with trace.trace_generation():
        result = await ollama_service.generate(
            prompt=prompt,
            model=model,
            system_prompt=_SYSTEM_PROMPT,
        )

    if result.get("error"):
        raise HTTPException(status_code=502, detail=result.get("response", "Ollama error"))

    trace.tokens_generated = result.get("eval_count", 0)

    return SummarizeResponse(
        summary=result.get("response", ""),
        model=model,
        trace={**trace.to_dict(), "citations": citations},
    )


@router.post("/improve")
async def improve(
    body: ImproveRequest,
    session: AsyncSession = Depends(get_session),
) -> ImproveResponse:
    """Improve the provided text, grounded in uploaded file context."""
    trace = RequestTrace()
    model = body.model or settings.DEFAULT_MODEL
    trace.model = model

    sanitized_text, _ = sanitize(body.text)

    # Retrieve relevant RAG context to ground the improvement
    rag_context, citations = await _get_rag_context_for_action(body.text, session, trace)

    rag_section = ""
    if rag_context:
        rag_section = (
            "\n\nUse the following reference context from uploaded files to ensure "
            "factual accuracy. Cite sources using [Source N] if you use them:\n"
            f"--- REFERENCE CONTEXT ---\n{rag_context}\n--- END REFERENCE ---\n"
        )

    instruction = body.instruction or "Improve clarity, grammar, and style"
    prompt = (
        "IMPORTANT: Return ONLY the rewritten text. "
        "Do NOT include any preamble, introduction, explanation, or commentary like "
        "'Here is the improved version' or 'I have rewritten the text'. "
        "Just output the improved text directly. Include [Source N] citations inline "
        "if you reference facts from the reference context.\n\n"
        f"Instruction: {instruction}\n\n"
        f"Rewrite the following text accordingly:\n\n"
        f"{sanitized_text}"
        f"{rag_section}"
    )

    with trace.trace_generation():
        result = await ollama_service.generate(
            prompt=prompt,
            model=model,
            system_prompt=_SYSTEM_PROMPT,
        )

    if result.get("error"):
        raise HTTPException(status_code=502, detail=result.get("response", "Ollama error"))

    trace.tokens_generated = result.get("eval_count", 0)

    return ImproveResponse(
        improved_text=result.get("response", ""),
        model=model,
        trace={**trace.to_dict(), "citations": citations},
    )


@router.post("/message", response_model=ChatMessageResponse, status_code=201)
async def persist_message(
    body: PersistMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatMessageResponse:
    """Persist a single chat message (for summarize/improve system messages)."""
    msg = ChatMessage(
        document_id=body.document_id,
        role=body.role,
        content=body.content,
        metadata_json=body.metadata_json,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return ChatMessageResponse.model_validate(msg)


@router.get("/history")
async def chat_history(
    document_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageResponse]:
    """Return chat messages, optionally filtered by document_id."""
    stmt = select(ChatMessage).order_by(ChatMessage.created_at.asc())
    if document_id is not None:
        stmt = stmt.where(ChatMessage.document_id == document_id)

    result = await session.execute(stmt)
    messages = result.scalars().all()
    return [ChatMessageResponse.model_validate(m) for m in messages]
