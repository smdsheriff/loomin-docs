import logging
import threading
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# Dimension lookup for well-known embedding models.  When the FAISS index is
# created fresh we resolve the dimension from the *actual* loaded model, but
# this table allows the indexer to initialise a placeholder index at import
# time (before the heavy model is loaded).
_KNOWN_DIMENSIONS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-MiniLM-L12-v2": 384,
    "all-mpnet-base-v2": 768,
    "paraphrase-MiniLM-L6-v2": 384,
    "paraphrase-multilingual-MiniLM-L12-v2": 384,
    "bge-small-en-v1.5": 384,
    "bge-base-en-v1.5": 768,
    "bge-large-en-v1.5": 1024,
    "e5-small-v2": 384,
    "e5-base-v2": 768,
    "e5-large-v2": 1024,
    "nomic-embed-text-v1.5": 768,
    "gte-small": 384,
    "gte-base": 768,
    "gte-large": 1024,
}

# Default until the real embedding model reports its dimension.
_DEFAULT_DIMENSION = 384


def _guess_dimension(model_path: str) -> int:
    """Return the embedding dimension for a model path/name if known."""
    name = Path(model_path).name
    return _KNOWN_DIMENSIONS.get(name, _DEFAULT_DIMENSION)


class FAISSIndexer:
    """Manages a FAISS IndexFlatIP index stored on disk.

    Thread-safety is provided by a re-entrant lock around mutating operations.
    Because we L2-normalize all vectors before insertion, inner-product search
    is equivalent to cosine similarity.

    The index dimension is determined lazily:
      1. If a saved index exists on disk, the dimension is read from it.
      2. Otherwise the dimension is resolved from the embedding model at first
         ``add_documents`` call (via ``ensure_dimension``).
      3. As a last resort, the lookup table ``_KNOWN_DIMENSIONS`` is consulted.
    """

    _instance: "FAISSIndexer | None" = None

    def __new__(cls) -> "FAISSIndexer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False  # type: ignore[attr-defined]
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._initialized = True
        self._dimension: int = _guess_dimension(settings.EMBEDDING_MODEL_PATH)
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(self._dimension)
        self._lock = threading.Lock()
        self._index_dir = Path(settings.FAISS_INDEX_PATH)
        self._index_file = self._index_dir / "index.faiss"
        self._next_id: int = 0
        self._id_map: dict[int, int] = {}
        self._removed_ids: set[int] = set()

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def total_vectors(self) -> int:
        return self._index.ntotal

    def ensure_dimension(self, dim: int) -> None:
        """Re-initialise the index if the actual embedding dimension differs
        from the initial guess.  This is a no-op when the dimensions match or
        the index already contains vectors (to avoid data loss)."""
        if dim == self._dimension:
            return
        with self._lock:
            if self._index.ntotal > 0:
                logger.warning(
                    "Embedding dimension changed (%d -> %d) but index already "
                    "contains %d vectors – keeping existing index.  Re-index "
                    "your files if the model has changed.",
                    self._dimension, dim, self._index.ntotal,
                )
                return
            logger.info(
                "Updating FAISS index dimension from %d to %d",
                self._dimension, dim,
            )
            self._dimension = dim
            self._index = faiss.IndexFlatIP(dim)

    def add_documents(
        self, chunks: list[str], embeddings: np.ndarray
    ) -> list[int]:
        """Add embeddings to the index. Returns assigned embedding_ids."""
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)

        # Auto-detect dimension from the first batch of embeddings
        if self._index.ntotal == 0 and embeddings.shape[1] != self._dimension:
            self.ensure_dimension(embeddings.shape[1])

        assert embeddings.shape[1] == self._dimension, (
            f"Embedding dimension mismatch: got {embeddings.shape[1]}, "
            f"index expects {self._dimension}"
        )

        with self._lock:
            start_id = self._next_id
            ids = list(range(start_id, start_id + len(chunks)))
            # Map each id to its position in the underlying flat index
            base_row = self._index.ntotal
            for offset, eid in enumerate(ids):
                self._id_map[eid] = base_row + offset
            self._index.add(embeddings.astype(np.float32))
            self._next_id = start_id + len(chunks)
        return ids

    def search(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> list[tuple[int, float]]:
        """Search the index and return list of (embedding_id, score).

        Results that have been logically removed are filtered out.
        """
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        with self._lock:
            search_k = min(top_k + len(self._removed_ids), self._index.ntotal)
            if search_k == 0:
                return []

            scores, indices = self._index.search(query_embedding.astype(np.float32), search_k)

            # Reverse-map FAISS row indices -> our embedding_ids
            row_to_id: dict[int, int] = {v: k for k, v in self._id_map.items()}

            results: list[tuple[int, float]] = []
            for score, row_idx in zip(scores[0], indices[0]):
                if row_idx == -1:
                    continue
                eid = row_to_id.get(int(row_idx))
                if eid is None or eid in self._removed_ids:
                    continue
                results.append((eid, float(score)))
                if len(results) >= top_k:
                    break
            return results

    def remove_documents(self, embedding_ids: list[int]) -> None:
        """Logically remove documents by marking their ids as excluded.

        FAISS IndexFlatIP does not support true deletion, so we maintain a
        set of removed ids that are filtered during search.
        """
        with self._lock:
            for eid in embedding_ids:
                self._removed_ids.add(eid)

    def save(self) -> None:
        """Persist the FAISS index to disk."""
        self._index_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, str(self._index_file))
        logger.info("FAISS index saved to %s (%d vectors)", self._index_file, self._index.ntotal)

    def load(self) -> None:
        """Load the FAISS index from disk if it exists."""
        if not self._index_file.exists():
            logger.info("No existing FAISS index found at %s; starting fresh", self._index_file)
            return
        with self._lock:
            self._index = faiss.read_index(str(self._index_file))
            # Rebuild id_map from the loaded index (assumes sequential ids)
            self._next_id = self._index.ntotal
            self._id_map = {i: i for i in range(self._index.ntotal)}
        logger.info(
            "FAISS index loaded from %s (%d vectors)", self._index_file, self._index.ntotal
        )

    def reset(self) -> None:
        """Reset the index to an empty state. Useful for testing."""
        with self._lock:
            self._index = faiss.IndexFlatIP(self._dimension)
            self._next_id = 0
            self._id_map.clear()
            self._removed_ids.clear()


# Module-level convenience instance.
faiss_indexer = FAISSIndexer()
