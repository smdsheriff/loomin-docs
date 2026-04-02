import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, documents, files, models
from app.models.database import init_db
from app.models.schemas import HealthResponse
from app.rag.indexer import faiss_indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler — runs on startup and shutdown."""
    # ── Startup ─────────────────────────────────────────────────────────
    logger.info("Initializing database tables...")
    await init_db()
    logger.info("Database ready.")

    logger.info("Loading FAISS index...")
    faiss_indexer.load()
    logger.info("FAISS index ready (%d vectors).", faiss_indexer.total_vectors)

    yield

    # ── Shutdown ────────────────────────────────────────────────────────
    logger.info("Saving FAISS index before shutdown...")
    faiss_indexer.save()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Loomin-Docs",
    description="Collaborative text editor backend with AI assistant (RAG, summarization, document manipulation).",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(files.router)
app.include_router(models.router)


# ── Health check ────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    return HealthResponse()
