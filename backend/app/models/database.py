import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from app.core.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_new_uuid)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    chat_messages = relationship(
        "ChatMessage", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    version_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    document = relationship("Document", back_populates="versions")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    document = relationship("Document", back_populates="chat_messages")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String, primary_key=True, default=_new_uuid)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # .pdf, .md, .txt
    file_path = Column(String, nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)  # Toggle file on/off for RAG
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    chunks = relationship(
        "FileChunk", back_populates="uploaded_file", cascade="all, delete-orphan"
    )


class FileChunk(Base):
    __tablename__ = "file_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(Integer, nullable=False)  # maps to FAISS index position

    uploaded_file = relationship("UploadedFile", back_populates="chunks")


def _run_migrations(conn) -> None:
    """Run lightweight schema migrations for SQLite.

    This is a *sync* callable invoked via ``conn.run_sync()``.
    SQLite does not support ALTER TABLE ADD COLUMN with constraints well,
    so we check if columns exist before attempting to add them.
    """
    import sqlalchemy as sa

    # Only run if the table already existed before create_all
    inspector_result = conn.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='uploaded_files'"
    ))
    if inspector_result.fetchone() is None:
        return  # Table was just created by create_all with all columns

    # Migration 1: Add is_active column to uploaded_files if missing
    result = conn.execute(sa.text("PRAGMA table_info(uploaded_files)"))
    columns = {row[1] for row in result}
    if "is_active" not in columns:
        conn.execute(sa.text(
            "ALTER TABLE uploaded_files ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
        ))


async def init_db() -> None:
    """Create all tables if they don't exist, then run migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """Dependency that yields an async database session."""
    async with async_session() as session:
        yield session  # type: ignore[misc]
