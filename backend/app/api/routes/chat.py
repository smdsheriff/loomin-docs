import json
import logging
import re
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
from app.rag.retriever import retrieve_relevant_chunks
from app.services.ollama import ollama_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

_SYSTEM_PROMPT = (
    "You are Loomin, an intelligent document assistant. "
    "You MUST follow these rules strictly:\n"
    "1. ONLY answer questions using the provided context (current document content and/or uploaded files).\n"
    "2. NEVER use your training knowledge to answer factual questions about documents.\n"
    "3. Always cite your sources using [Source N] notation when referencing uploaded files.\n"
    "4. When the user asks about their current document, use the CURRENT DOCUMENT section.\n"
    "5. If the provided context does not contain the answer, clearly state: "
    "'Based on the available documents, I don't have information about that.'\n"
    "6. If no context is provided, tell the user to upload relevant files or write content in the editor first.\n"
    "7. Be concise, helpful, and professional."
)


def _build_rag_prompt(
    user_message: str,
    context_chunks: list[dict],
    available_files: list[dict] | None = None,
    document_content: str | None = None,
) -> str:
    """Build a prompt that injects retrieved context before the user question.

    Context is assembled from two sources:
    1. The current document editor content (the text the user is working on)
    2. Uploaded files chunks retrieved via FAISS similarity search
    """
    # Build file inventory so the model knows what files the user has uploaded
    file_inventory = ""
    if available_files:
        file_lines = [f"  - {f['name']} ({f['type']}, {f['chunks']} chunks)" for f in available_files]
        file_inventory = f"Uploaded files available:\n" + "\n".join(file_lines) + "\n\n"

    # Build document editor context section
    doc_context = ""
    if document_content and document_content.strip():
        # Strip HTML tags for plain-text context
        plain_text = re.sub(r"<[^>]+>", " ", document_content)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        if plain_text:
            # Limit to ~2000 chars to avoid overwhelming the context window
            truncated = plain_text[:2000]
            if len(plain_text) > 2000:
                truncated += "... [truncated]"
            doc_context = (
                f"--- CURRENT DOCUMENT ---\n{truncated}\n--- END DOCUMENT ---\n\n"
            )

    has_any_context = bool(context_chunks) or bool(doc_context)

    if not has_any_context:
        if not available_files:
            return (
                "The user has not uploaded any files yet and the document is empty. "
                "Do NOT answer from your own knowledge. Instead, tell the user to "
                "upload .pdf, .md, or .txt files first for accurate answers.\n\n"
                f"Question: {user_message}"
            )
        return (
            f"{file_inventory}"
            "No relevant content was found in the uploaded files for this question. "
            "Do NOT answer from your own knowledge. Tell the user that the uploaded "
            "files do not contain information about their question.\n\n"
            f"Question: {user_message}"
        )

    # Build uploaded file chunks section
    file_context = ""
    if context_chunks:
        context_parts: list[str] = []
        for i, chunk in enumerate(context_chunks, 1):
            source = chunk["source_file"]
            idx = chunk["chunk_index"]
            text = chunk["chunk_text"]
            context_parts.append(f"[Source {i}: {source} (chunk {idx})]\n{text}")
        file_context = (
            f"--- UPLOADED FILE CONTEXT ---\n"
            + "\n\n".join(context_parts)
            + "\n--- END UPLOADED FILE CONTEXT ---\n\n"
        )

    return (
        f"{file_inventory}"
        f"{doc_context}"
        f"{file_context}"
        f"Answer the question using ONLY the context above (current document and/or uploaded files). "
        f"If the answer is not in the context, say you don't have that information. "
        f"Cite sources using [Source N] notation when referencing uploaded files.\n\n"
        f"Question: {user_message}"
    )


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
