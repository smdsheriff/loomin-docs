import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Document, DocumentVersion, get_session
from app.models.schemas import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
    DocumentVersionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(
    body: DocumentCreate,
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """Create a new document and auto-save as version 1."""
    doc = Document(title=body.title, content=body.content)
    session.add(doc)
    await session.flush()  # populate doc.id

    version = DocumentVersion(
        document_id=doc.id,
        content=doc.content,
        version_number=1,
    )
    session.add(version)
    await session.commit()
    await session.refresh(doc)

    return DocumentResponse.model_validate(doc)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    session: AsyncSession = Depends(get_session),
) -> list[DocumentResponse]:
    """List all documents ordered by most recently updated."""
    stmt = select(Document).order_by(Document.updated_at.desc())
    result = await session.execute(stmt)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """Get a single document by ID."""
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    body: DocumentUpdate,
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """Update a document and auto-create a new version."""
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if body.title is not None:
        doc.title = body.title
    if body.content is not None:
        doc.content = body.content

    doc.updated_at = datetime.now(timezone.utc)

    # Determine next version number
    stmt = (
        select(func.coalesce(func.max(DocumentVersion.version_number), 0))
        .where(DocumentVersion.document_id == document_id)
    )
    result = await session.execute(stmt)
    max_version: int = result.scalar_one()

    version = DocumentVersion(
        document_id=document_id,
        content=doc.content,
        version_number=max_version + 1,
    )
    session.add(version)
    await session.commit()
    await session.refresh(doc)

    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
async def list_versions(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[DocumentVersionResponse]:
    """List all versions for a document, newest first."""
    # Verify document exists
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    result = await session.execute(stmt)
    versions = result.scalars().all()
    return [DocumentVersionResponse.model_validate(v) for v in versions]
