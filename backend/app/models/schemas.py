from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Chat ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    document_id: Optional[str] = None
    model: Optional[str] = None
    document_content: Optional[str] = None  # Current editor content for contextual RAG


class PersistMessageRequest(BaseModel):
    """Persist a single chat message (for system/action messages not sent via /api/chat)."""
    role: str  # "user" or "assistant"
    content: str
    document_id: Optional[str] = None
    metadata_json: Optional[str] = None


class SummarizeRequest(BaseModel):
    text: str
    model: Optional[str] = None


class ImproveRequest(BaseModel):
    text: str
    instruction: Optional[str] = None
    model: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: int
    document_id: Optional[str] = None
    role: str
    content: str
    metadata_json: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SummarizeResponse(BaseModel):
    summary: str
    model: str
    trace: dict[str, Any] = {}


class ImproveResponse(BaseModel):
    improved_text: str
    model: str
    trace: dict[str, Any] = {}


# ── Documents ───────────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    content: str = ""


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    id: int
    document_id: str
    content: str
    version_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Files ───────────────────────────────────────────────────────────────────

class UploadedFileResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    chunk_count: int
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class FileToggleRequest(BaseModel):
    is_active: bool


class FileChunkResponse(BaseModel):
    chunk_index: int
    content: str

    model_config = {"from_attributes": True}


class FileDeleteResponse(BaseModel):
    detail: str


# ── Models ──────────────────────────────────────────────────────────────────

class OllamaModel(BaseModel):
    name: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None


class ModelsResponse(BaseModel):
    models: list[OllamaModel]


class TokenCountRequest(BaseModel):
    text: str
    model: Optional[str] = None
    active_file_ids: Optional[list[str]] = None  # IDs of active files for chunk token calc


class TokenCountResponse(BaseModel):
    tokens: int
    percentage: float
    model: str
    context_window: int
    doc_tokens: int = 0
    chunk_tokens: int = 0
    free_tokens: int = 0


# ── RAG retrieval result ────────────────────────────────────────────────────

class RetrievedChunk(BaseModel):
    chunk_text: str
    source_file: str
    chunk_index: int
    score: float


# ── Health ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
