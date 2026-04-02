import json
import logging
from typing import Any, AsyncGenerator, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)


class OllamaService:
    """Async HTTP client for the Ollama REST API."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    # ── Non-streaming generation ────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a generate request to Ollama and return the full response.

        Returns:
            A dict with at least ``response`` and ``model`` keys.
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate", json=payload
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self._base_url)
            return {
                "response": "Error: Unable to connect to the Ollama service. Please ensure it is running.",
                "model": model,
                "error": True,
            }
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama returned HTTP %s: %s", exc.response.status_code, exc.response.text)
            return {
                "response": f"Error: Ollama returned status {exc.response.status_code}.",
                "model": model,
                "error": True,
            }

    # ── Streaming generation ────────────────────────────────────────────

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama as an async generator.

        Yields individual response tokens (strings).
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/generate", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            return
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self._base_url)
            yield "Error: Unable to connect to the Ollama service."
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error during stream: %s", exc)
            yield f"Error: Ollama returned status {exc.response.status_code}."

    # ── Multi-turn chat streaming (Ollama /api/chat) ─────────────────────

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str,
    ) -> AsyncGenerator[str, None]:
        """Stream a multi-turn chat response from Ollama /api/chat.

        Args:
            messages: List of ``{"role": "system|user|assistant", "content": "..."}``
            model: Ollama model name.

        Yields individual response tokens.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/chat", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        # /api/chat format: {"message": {"role": "assistant", "content": "token"}}
                        msg = data.get("message", {})
                        token = msg.get("content", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            return
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self._base_url)
            yield "Error: Unable to connect to the Ollama service."
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error during chat stream: %s", exc)
            yield f"Error: Ollama returned status {exc.response.status_code}."

    # ── List models ─────────────────────────────────────────────────────

    async def list_models(self) -> dict[str, Any]:
        """Fetch available models from Ollama GET /api/tags."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self._base_url)
            return {"models": []}
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP %s when listing models", exc.response.status_code)
            return {"models": []}


# Module-level convenience instance.
ollama_service = OllamaService()
