import logging
import os
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Chunking constants — "tokens" are approximated as words * 1.33.
_TARGET_CHUNK_WORDS = 375   # ~500 tokens
_OVERLAP_WORDS = 38         # ~50 tokens


# ── File Parsing ────────────────────────────────────────────────────────────

def parse_pdf(file_path: str) -> str:
    """Extract text from a PDF using multiple PyMuPDF strategies.

    Tries plain text extraction first, then falls back to extracting
    from text blocks and dictionaries for scanned/image-heavy PDFs.
    """
    doc = fitz.open(file_path)
    pages: list[str] = []

    for page in doc:
        # Strategy 1: standard text extraction
        text = page.get_text("text")
        if text and text.strip():
            pages.append(text.strip())
            continue

        # Strategy 2: extract from text blocks (handles some layouts better)
        blocks = page.get_text("blocks")
        if blocks:
            block_texts = [
                b[4].strip() for b in blocks
                if isinstance(b[4], str) and b[4].strip()
            ]
            if block_texts:
                pages.append("\n".join(block_texts))
                continue

        # Strategy 3: raw dict extraction (last resort for embedded text)
        raw = page.get_text("rawdict")
        if raw and "blocks" in raw:
            raw_texts: list[str] = []
            for block in raw["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            t = span.get("text", "").strip()
                            if t:
                                raw_texts.append(t)
            if raw_texts:
                pages.append(" ".join(raw_texts))

    doc.close()
    return "\n\n".join(pages)


def parse_text_file(file_path: str) -> str:
    """Read a plain text or markdown file."""
    path = Path(file_path)
    return path.read_text(encoding="utf-8", errors="replace")


def parse_file(file_path: str, file_type: str) -> str:
    """Dispatch to the appropriate parser based on file extension.

    Args:
        file_path: Absolute path to the file on disk.
        file_type: The file extension, e.g. ``.pdf``, ``.md``, ``.txt``.

    Returns:
        The extracted text content of the file.
    """
    file_type = file_type.lower()
    if file_type == ".pdf":
        return parse_pdf(file_path)
    if file_type in {".md", ".txt"}:
        return parse_text_file(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


# ── Text Chunking ───────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    target_words: int = _TARGET_CHUNK_WORDS,
    overlap_words: int = _OVERLAP_WORDS,
) -> list[str]:
    """Split text into overlapping chunks of approximately ``target_words``.

    Args:
        text: The full document text.
        target_words: Target number of words per chunk (~500 tokens).
        overlap_words: Number of words to overlap between consecutive chunks
            (~50 tokens).

    Returns:
        A list of text chunks.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + target_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap_words

    return chunks


# ── Token estimation ────────────────────────────────────────────────────────

# Approximate context windows for common Ollama models.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "loomin": 131072,
    "llama3": 8192,
    "llama3:8b": 8192,
    "llama3:70b": 8192,
    "llama3.2": 131072,
    "llama3.2:1b": 131072,
    "llama3.2:3b": 131072,
    "llama2": 4096,
    "llama2:13b": 4096,
    "mistral": 32768,
    "mistral:7b-instruct-q4_0": 32768,
    "mixtral": 32768,
    "codellama": 16384,
    "gemma": 8192,
    "gemma2": 8192,
    "gemma3": 8192,
    "gemma3:1b": 8192,
    "phi3": 4096,
    "qwen2": 32768,
}

DEFAULT_CONTEXT_WINDOW = 8192


def estimate_tokens(text: str) -> int:
    """Estimate token count using a hybrid heuristic.

    Uses max(char_based, word_based) for robustness across text types:
    - English prose: ~4 chars/token (GPT/Llama tokenizers)
    - Code/technical: ~3.5 chars/token (more symbols → shorter tokens)
    - Word-based: ~1.3 words/token (cross-check)
    """
    if not text:
        return 0
    char_count = len(text)
    word_count = len(text.split())
    char_estimate = char_count // 4
    word_estimate = round(word_count * 1.3)
    return max(char_estimate, word_estimate)


def get_context_window(model: Optional[str] = None) -> int:
    """Return the context window size for a given model name."""
    if model is None:
        return DEFAULT_CONTEXT_WINDOW
    # Try exact match first, then prefix match
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    base_model = model.split(":")[0]
    return MODEL_CONTEXT_WINDOWS.get(base_model, DEFAULT_CONTEXT_WINDOW)
