import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import FileChunk, UploadedFile, get_session
from app.models.schemas import (
    ModelsResponse,
    OllamaModel,
    TokenCountRequest,
    TokenCountResponse,
)
from app.services.document import estimate_tokens, get_context_window
from app.services.ollama import ollama_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """Proxy to Ollama GET /api/tags and return available models."""
    data = await ollama_service.list_models()
    raw_models = data.get("models", [])
    models = []
    for m in raw_models:
        models.append(
            OllamaModel(
                name=m.get("name", "unknown"),
                size=m.get("size"),
                modified_at=m.get("modified_at"),
                digest=m.get("digest"),
            )
        )
    return ModelsResponse(models=models)


@router.post("/tokens/count", response_model=TokenCountResponse)
async def token_count(
    body: TokenCountRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenCountResponse:
    """Estimate token count for document text and active file chunks,
    returning a segmented breakdown of context window usage."""
    resolved_model = body.model or settings.DEFAULT_MODEL
    doc_tokens = estimate_tokens(body.text)
    ctx_window = get_context_window(resolved_model)

    # Calculate chunk tokens from active files
    chunk_tokens = 0
    try:
        if body.active_file_ids:
            stmt = (
                select(func.coalesce(func.sum(func.length(FileChunk.content)), 0))
                .join(UploadedFile, FileChunk.file_id == UploadedFile.id)
                .where(UploadedFile.id.in_(body.active_file_ids))
                .where(UploadedFile.is_active == True)  # noqa: E712
            )
        else:
            stmt = (
                select(func.coalesce(func.sum(func.length(FileChunk.content)), 0))
                .join(UploadedFile, FileChunk.file_id == UploadedFile.id)
                .where(UploadedFile.is_active == True)  # noqa: E712
            )
        result = await session.execute(stmt)
        total_chars = result.scalar() or 0
        chunk_tokens = total_chars // 4
    except Exception:
        # If file tables have schema issues, degrade gracefully
        chunk_tokens = 0

    total_tokens = doc_tokens + chunk_tokens
    free_tokens = max(0, ctx_window - total_tokens)
    percentage = round((total_tokens / ctx_window) * 100, 2) if ctx_window > 0 else 0.0

    return TokenCountResponse(
        tokens=total_tokens,
        percentage=percentage,
        model=resolved_model,
        context_window=ctx_window,
        doc_tokens=doc_tokens,
        chunk_tokens=chunk_tokens,
        free_tokens=free_tokens,
    )
