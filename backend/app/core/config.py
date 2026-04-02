from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    DATABASE_URL: str = "sqlite+aiosqlite:////data/loomin.db"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    EMBEDDING_MODEL_PATH: str = "all-MiniLM-L6-v2"
    FAISS_INDEX_PATH: str = "/data/faiss_index"
    UPLOAD_DIR: str = "/data/uploads"
    DEFAULT_MODEL: str = "llama3.2:1b"
    MAX_CHUNKS_RETRIEVED: int = 5
    MIN_SIMILARITY_SCORE: float = 0.25
    MAX_CONVERSATION_HISTORY: int = 100

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
