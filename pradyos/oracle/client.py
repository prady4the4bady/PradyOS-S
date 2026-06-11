"""Ollama HTTP client for ORACLE.

Connects to a local Ollama server (default: http://localhost:11434) via
TCP/HTTP — no subprocess, no AF_UNIX sockets, Windows-safe.

Uses httpx for both sync and async operation. ORACLE always uses the
async path; the sync path is available for shell utilities.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger("pradyos.oracle.client")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OllamaError(Exception):
    """Raised when Ollama returns a non-2xx status or a malformed response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:1.5b-base"
DEFAULT_TIMEOUT = 120.0  # seconds — LLM calls can be slow on CPU


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP API.

    Supports:
        generate()   — /api/generate   (single completion)
        chat()       — /api/chat        (message history)
        stream_chat()— /api/chat streaming
        list_models()— /api/tags
        is_alive()   — HEAD / to test connectivity
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def is_alive(self) -> bool:
        """Return True if Ollama is reachable, False otherwise."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as cli:
                r = await cli.get(self.base_url + "/")
                return r.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        raw: bool = False,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Single-turn completion. Returns the full response text."""
        import httpx

        payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **(options or {}),
            },
        }
        if system:
            payload["system"] = system
        if raw:
            payload["raw"] = True

        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            try:
                r = await cli.post(self.base_url + "/api/generate", json=payload)
            except httpx.ConnectError as e:
                raise OllamaError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e

        if r.status_code != 200:
            raise OllamaError(r.text[:500], status_code=r.status_code)

        try:
            data = r.json()
        except Exception as e:
            raise OllamaError(f"Malformed JSON from Ollama: {e}") from e

        return str(data.get("response", ""))

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Multi-turn chat. Returns the assistant's response text."""
        import httpx

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **(options or {}),
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            try:
                r = await cli.post(self.base_url + "/api/chat", json=payload)
            except httpx.ConnectError as e:
                raise OllamaError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e

        if r.status_code != 200:
            raise OllamaError(r.text[:500], status_code=r.status_code)

        try:
            data = r.json()
        except Exception as e:
            raise OllamaError(f"Malformed JSON from Ollama: {e}") from e

        return str(data.get("message", {}).get("content", ""))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Streaming chat — yields text tokens as they arrive."""
        import httpx

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            try:
                async with cli.stream("POST", self.base_url + "/api/chat", json=payload) as r:
                    if r.status_code != 200:
                        raise OllamaError(await r.aread() or b"error", status_code=r.status_code)
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
            except httpx.ConnectError as e:
                raise OllamaError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e

    async def list_models(self) -> list[str]:
        """Return the list of locally available model names."""
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as cli:
            try:
                r = await cli.get(self.base_url + "/api/tags")
            except httpx.ConnectError:
                return []

        if r.status_code != 200:
            return []

        try:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------
    # Sync helpers (CLI / test utilities)
    # ------------------------------------------------------------------

    def generate_sync(self, prompt: str, **kwargs: Any) -> str:
        """Blocking wrapper around ``generate`` for non-async contexts."""
        import asyncio

        return asyncio.run(self.generate(prompt, **kwargs))
