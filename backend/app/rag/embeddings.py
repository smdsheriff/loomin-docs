import logging
import os
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fallback model name used when the configured path doesn't exist on disk.
# sentence-transformers will auto-download from HuggingFace on first use.
_DEFAULT_HF_MODEL = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Singleton wrapper around the sentence-transformers embedding model.

    The model is loaded lazily on first call to ``embed`` so that import
    time stays fast and cold-start cost is paid only once.

    Loading strategy:
      1. Try the configured ``EMBEDDING_MODEL_PATH`` (may be a local directory
         pre-populated by ``sideload.sh`` for air-gapped deployments).
      2. If the path does not exist, fall back to the model *name* so that
         sentence-transformers downloads it automatically (requires internet).
    """

    _instance: Optional["EmbeddingService"] = None
    _model: Optional[SentenceTransformer] = None

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _resolve_model_path(self) -> str:
        """Return either a local directory or a HuggingFace model name."""
        path = settings.EMBEDDING_MODEL_PATH
        if os.path.isdir(path):
            logger.info("Using local embedding model at: %s", path)
            return path
        # Path doesn't exist — use the model name for auto-download
        name = os.path.basename(path) or _DEFAULT_HF_MODEL
        logger.info(
            "Local path %s not found. Downloading model '%s' from HuggingFace...",
            path, name,
        )
        return name

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            model_ref = self._resolve_model_path()
            try:
                self._model = SentenceTransformer(model_ref)
            except Exception as exc:
                # Provide a clear, actionable error for air-gapped deployments
                is_path = os.path.sep in model_ref or model_ref.startswith("/")
                if is_path:
                    msg = (
                        f"Failed to load embedding model from '{model_ref}'. "
                        f"The directory may be empty or corrupt. "
                        f"On air-gapped deployments, ensure 'sideload.sh' was run "
                        f"to populate the embedding-model volume before starting."
                    )
                else:
                    msg = (
                        f"Failed to download embedding model '{model_ref}'. "
                        f"This is expected on air-gapped VMs without internet. "
                        f"Run 'deploy/sideload.sh' on an internet-connected machine "
                        f"first, then transfer the package to the target VM."
                    )
                logger.error(msg)
                raise RuntimeError(msg) from exc
            logger.info(
                "Embedding model loaded successfully (dim=%d)", self.dimension
            )
        return self._model

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()  # type: ignore[return-value]

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts and return L2-normalized vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            numpy array of shape ``(len(texts), dimension)`` with unit-norm rows.
        """
        model = self._load_model()
        embeddings: np.ndarray = model.encode(
            texts, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True
        )
        return embeddings.astype(np.float32)


# Module-level convenience instance.
embedding_service = EmbeddingService()
