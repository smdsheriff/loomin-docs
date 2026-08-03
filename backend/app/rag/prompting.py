"""Shared prompt construction for the RAG chat pipeline.

These helpers are the single source of truth for the assistant's system prompt
and the RAG prompt layout. Both the legacy inline pipeline (``api/routes/chat.py``)
and the LangGraph pipeline (``rag/graph.py``) import from here, so the two paths
are guaranteed to produce identical prompts.
"""

import re

SYSTEM_PROMPT = (
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


def build_rag_prompt(
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
        file_inventory = "Uploaded files available:\n" + "\n".join(file_lines) + "\n\n"

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
            "--- UPLOADED FILE CONTEXT ---\n"
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
