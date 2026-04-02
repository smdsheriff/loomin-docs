import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import FileChunk, UploadedFile, get_session
from app.models.schemas import FileChunkResponse, FileDeleteResponse, FileToggleRequest, UploadedFileResponse
from app.rag.embeddings import embedding_service
from app.rag.indexer import faiss_indexer
from app.services.document import chunk_text, parse_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])

_ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}


@router.post("/upload", response_model=UploadedFileResponse, status_code=201)
async def upload_file(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> UploadedFileResponse:
    """Upload a file, parse it, chunk it, embed chunks, and index them."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Check for duplicate filename — warn user if already uploaded
    dup_stmt = select(UploadedFile).where(UploadedFile.filename == file.filename)
    dup_result = await session.execute(dup_stmt)
    existing = dup_result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"File '{file.filename}' already uploaded (id: {existing.id}, {existing.chunk_count} chunks). Delete it first to re-upload.",
        )

    # Save file to disk
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{ext}"
    file_path = upload_dir / safe_filename

    content_bytes = await file.read()

    # Server-side size limit (50 MB) — defense in depth
    max_size = 50 * 1024 * 1024
    if len(content_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content_bytes) / (1024*1024):.1f} MB). Maximum is 50 MB.",
        )

    file_path.write_bytes(content_bytes)

    # Parse file content
    try:
        text = parse_file(str(file_path), ext)
    except Exception as exc:
        # Clean up the file on parse failure
        file_path.unlink(missing_ok=True)
        logger.error("Failed to parse uploaded file %s: %s", file.filename, exc)
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")

    if not text.strip():
        file_path.unlink(missing_ok=True)
        detail = "File contains no extractable text."
        if ext == ".pdf":
            detail += " The PDF may be scanned/image-based. Only text-based PDFs are supported."
        raise HTTPException(status_code=422, detail=detail)

    # Chunk the text
    chunks = chunk_text(text)
    if not chunks:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="File produced no text chunks")

    # Embed all chunks
    embeddings = embedding_service.embed(chunks)

    # Add to FAISS index
    embedding_ids = faiss_indexer.add_documents(chunks, embeddings)

    # Persist to database
    uploaded_file = UploadedFile(
        id=file_id,
        filename=file.filename,
        file_type=ext,
        file_path=str(file_path),
        chunk_count=len(chunks),
    )
    session.add(uploaded_file)

    for idx, (chunk_content, eid) in enumerate(zip(chunks, embedding_ids)):
        db_chunk = FileChunk(
            file_id=file_id,
            chunk_index=idx,
            content=chunk_content,
            embedding_id=eid,
        )
        session.add(db_chunk)

    await session.commit()
    await session.refresh(uploaded_file)

    # Save FAISS index to disk
    faiss_indexer.save()

    logger.info(
        "Uploaded file %s: %d chunks indexed", file.filename, len(chunks)
    )
    return UploadedFileResponse.model_validate(uploaded_file)


@router.get("", response_model=list[UploadedFileResponse])
async def list_files(
    session: AsyncSession = Depends(get_session),
) -> list[UploadedFileResponse]:
    """List all uploaded files."""
    stmt = select(UploadedFile).order_by(UploadedFile.created_at.desc())
    result = await session.execute(stmt)
    files = result.scalars().all()
    return [UploadedFileResponse.model_validate(f) for f in files]


@router.patch("/{file_id}/toggle", response_model=UploadedFileResponse)
async def toggle_file(
    file_id: str,
    body: FileToggleRequest,
    session: AsyncSession = Depends(get_session),
) -> UploadedFileResponse:
    """Toggle a file on/off for RAG context inclusion."""
    uploaded_file = await session.get(UploadedFile, file_id)
    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    uploaded_file.is_active = body.is_active
    await session.commit()
    await session.refresh(uploaded_file)

    state = "enabled" if body.is_active else "disabled"
    logger.info("File %s (%s) %s for RAG", uploaded_file.filename, file_id, state)
    return UploadedFileResponse.model_validate(uploaded_file)


@router.get("/{file_id}/chunks", response_model=list[FileChunkResponse])
async def get_file_chunks(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[FileChunkResponse]:
    """Return all chunks for a given file, ordered by chunk index."""
    uploaded_file = await session.get(UploadedFile, file_id)
    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    stmt = (
        select(FileChunk)
        .where(FileChunk.file_id == file_id)
        .order_by(FileChunk.chunk_index.asc())
    )
    result = await session.execute(stmt)
    chunks = result.scalars().all()
    return [FileChunkResponse.model_validate(c) for c in chunks]


@router.delete("/{file_id}", response_model=FileDeleteResponse)
async def delete_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> FileDeleteResponse:
    """Delete an uploaded file, its chunks from the DB, and remove from FAISS."""
    uploaded_file = await session.get(UploadedFile, file_id)
    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Get embedding ids to remove from FAISS
    stmt = select(FileChunk.embedding_id).where(FileChunk.file_id == file_id)
    result = await session.execute(stmt)
    embedding_ids = [row[0] for row in result.all()]

    # Remove from FAISS (logical removal)
    if embedding_ids:
        faiss_indexer.remove_documents(embedding_ids)
        faiss_indexer.save()

    # Delete the physical file
    file_path = Path(uploaded_file.file_path)
    file_path.unlink(missing_ok=True)

    # Delete from database (cascades to file_chunks)
    await session.delete(uploaded_file)
    await session.commit()

    logger.info("Deleted file %s (%s)", uploaded_file.filename, file_id)
    return FileDeleteResponse(detail=f"File '{uploaded_file.filename}' deleted successfully")
