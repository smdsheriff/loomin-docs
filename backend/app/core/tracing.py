import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class RequestTrace:
    """Collects latency and throughput metrics for an AI request."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: str = ""
    chunks_retrieved: int = 0
    tokens_generated: int = 0

    _retrieval_start: float = 0.0
    _retrieval_end: float = 0.0
    _generation_start: float = 0.0
    _generation_end: float = 0.0

    @contextmanager
    def trace_retrieval(self) -> Generator[None, None, None]:
        """Context manager to time the retrieval phase."""
        self._retrieval_start = time.perf_counter()
        try:
            yield
        finally:
            self._retrieval_end = time.perf_counter()

    @contextmanager
    def trace_generation(self) -> Generator[None, None, None]:
        """Context manager to time the generation phase."""
        self._generation_start = time.perf_counter()
        try:
            yield
        finally:
            self._generation_end = time.perf_counter()

    @property
    def retrieval_time_ms(self) -> float:
        if self._retrieval_end == 0.0:
            return 0.0
        return round((self._retrieval_end - self._retrieval_start) * 1000, 1)

    @property
    def generation_time_ms(self) -> float:
        if self._generation_end == 0.0:
            return 0.0
        return round((self._generation_end - self._generation_start) * 1000, 1)

    @property
    def total_time_ms(self) -> float:
        return round(self.retrieval_time_ms + self.generation_time_ms, 1)

    @property
    def tokens_per_second(self) -> float:
        gen_seconds = self.generation_time_ms / 1000.0
        if gen_seconds <= 0:
            return 0.0
        return round(self.tokens_generated / gen_seconds, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "retrieval_time_ms": self.retrieval_time_ms,
            "generation_time_ms": self.generation_time_ms,
            "total_time_ms": self.total_time_ms,
            "tokens_generated": self.tokens_generated,
            "tokens_per_second": self.tokens_per_second,
            "model": self.model,
            "chunks_retrieved": self.chunks_retrieved,
        }
