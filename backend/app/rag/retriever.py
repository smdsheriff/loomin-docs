import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import FileChunk, UploadedFile
from app.models.schemas import RetrievedChunk
from app.rag.embeddings import embedding_service
from app.rag.indexer import faiss_indexer

logger = logging.getLogger(__name__)


async def retrieve_relevant_chunks(
    query: str,
    session: AsyncSession,
    top_k: int = 5,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Embed the query, search FAISS, and join with the database to return
    chunk text and source file information.

    Args:
        query: The user's natural-language query.
        session: An active async SQLAlchemy session.
        top_k: Maximum number of chunks to return.

    Returns:
        A list of ``RetrievedChunk`` objects sorted by descending score.
    """
    if faiss_indexer.total_vectors == 0:
        return []

    # 1. Embed the query
    query_vector = embedding_service.embed([query])

    # 2. Search FAISS
    results = faiss_indexer.search(query_vector, top_k=top_k)
    if not results:
        return []

    # Filter out low-confidence results to prevent hallucination from weak matches
    from app.core.config import settings
    threshold = min_score if min_score is not None else settings.MIN_SIMILARITY_SCORE
    results = [(eid, score) for eid, score in results if score >= threshold]
    if not results:
        logger.info("All retrieved chunks below similarity threshold (%.2f)", threshold)
        return []

    embedding_ids = [eid for eid, _ in results]
    score_map = {eid: score for eid, score in results}

    # 3. Fetch matching chunks from the database (only from active files)
    stmt = (
        select(FileChunk, UploadedFile.filename)
        .join(UploadedFile, FileChunk.file_id == UploadedFile.id)
        .where(FileChunk.embedding_id.in_(embedding_ids))
        .where(UploadedFile.is_active == True)  # noqa: E712 — SQLAlchemy requires ==
    )
    result = await session.execute(stmt)
    rows = result.all()

    # 4. Build response, preserving the ranking order from FAISS
    chunk_lookup: dict[int, tuple[FileChunk, str]] = {}
    for chunk, filename in rows:
        chunk_lookup[chunk.embedding_id] = (chunk, filename)

    retrieved: list[RetrievedChunk] = []
    for eid in embedding_ids:
        pair = chunk_lookup.get(eid)
        if pair is None:
            continue
        chunk, filename = pair
        retrieved.append(
            RetrievedChunk(
                chunk_text=chunk.content,
                source_file=filename,
                chunk_index=chunk.chunk_index,
                score=score_map[eid],
            )
        )

    return retrieved
