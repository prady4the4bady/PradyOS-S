"""LLM provider abstraction — one switch for how smart the agents are.

Every LLM-backed plane (EVOLVE's proposer, the GUILD's worker, and future ones)
talks to a model through a single tiny interface, so the *whole* OS can be moved
from a small local model to a stronger one by changing configuration — never code.

  * **Defaults to local, free Ollama.** With no configuration, the agents run on a
    local model (zero API credits) — the project's standing constraint.
  * **Switchable to any stronger model** that speaks the OpenAI-compatible
    ``/v1/chat/completions`` API (OpenAI, Groq, Together, a local vLLM, etc.) by
    setting ``PRADYOS_LLM_*`` env vars. The Sovereign opts in to spend; nothing
    here ever sends data anywhere by default.

A provider is any object with a ``name`` attribute and a
``generate(prompt, *, system="") -> str`` method, so tests inject a fake and the
engines never touch the network.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from collections.abc import Mapping
from typing import Any

log = logging.getLogger("pradyos.llm")

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_LOCAL_MODEL = "qwen2.5-coder:7b"

# NVIDIA NIM — OpenAI-compatible hosted models (Llama-70B, Nemotron, …). The
# Sovereign opts in by supplying a key; the model is named in the request body.
_NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1"
_NVIDIA_DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"

# Friendly aliases → exact NIM model ids, so the Sovereign can switch the whole
# OS's brain with one short word (``PRADYOS_LLM_MODEL=minimax``). ``minimax`` maps
# to the multimodal MiniMax-M3 — the documented working fallback when other NIM
# models error. Any unknown value is passed through verbatim (a full model id).
_NVIDIA_MODEL_ALIASES: dict[str, str] = {
    "llama": "meta/llama-3.3-70b-instruct",
    "llama-70b": "meta/llama-3.3-70b-instruct",
    "nemotron": "nvidia/llama-3.1-nemotron-70b-instruct",
    "minimax": "minimaxai/minimax-m3",
    "minimax-m3": "minimaxai/minimax-m3",
}


def _resolve_model(name: str | None) -> str:
    """Map a friendly alias to its exact NIM model id (pass through unknowns)."""
    if not name:
        return _NVIDIA_DEFAULT_MODEL
    return _NVIDIA_MODEL_ALIASES.get(name.strip().lower(), name.strip())


class LLMError(RuntimeError):
    """Base class for LLM provider failures."""


class OllamaProvider:
    """A local Ollama model — zero API credits, the default. Never contacted at
    import time; if Ollama is down, :meth:`generate` raises and callers degrade."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = _DEFAULT_OLLAMA_URL,
        model: str = _DEFAULT_LOCAL_MODEL,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        full = f"{system}\n\n{prompt}" if system.strip() else prompt
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": full,
                "stream": False,
                "options": {"temperature": temperature},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()

    def info(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "base_url": self.base_url}


class OpenAICompatProvider:
    """Any OpenAI-compatible ``/chat/completions`` endpoint — the opt-in path to a
    stronger model. The Sovereign supplies ``base_url`` + ``model`` (+ optional
    ``api_key``); this is the only place a key is held and it is never logged."""

    name = "openai-compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: int = 120,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> None:
        if not (isinstance(base_url, str) and base_url.strip()):
            raise LLMError("OpenAICompatProvider needs a base_url")
        if not (isinstance(model, str) and model.strip()):
            raise LLMError("OpenAICompatProvider needs a model")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or None
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.top_p = top_p

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        messages: list[dict[str, str]] = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        # Optional generation controls (e.g. MiniMax-M3 / Nemotron tuning). Only
        # sent when configured, so the simple default request stays unchanged.
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            body["top_p"] = self.top_p
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, headers=headers
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            return ""
        return ((choices[0].get("message") or {}).get("content") or "").strip()

    def info(self) -> dict[str, Any]:
        # The API key is NEVER included.
        return {"provider": self.name, "model": self.model, "base_url": self.base_url}


def resolve_provider(env: Mapping[str, str] | None = None) -> Any:
    """Pick the LLM provider from configuration. **Defaults to local Ollama.**

    ``PRADYOS_LLM_PROVIDER``:
      * ``ollama`` (default) — local, free. ``PRADYOS_OLLAMA_URL``, ``PRADYOS_LLM_MODEL``.
      * ``nvidia`` / ``nim`` — NVIDIA NIM hosted models (Llama-70B, Nemotron, …).
        Needs ``PRADYOS_LLM_API_KEY``; ``PRADYOS_LLM_MODEL`` accepts a short alias
        (``llama`` / ``nemotron`` / ``minimax`` → MiniMax-M3, the working fallback)
        or a full model id (default llama-3.3-70b). ``PRADYOS_LLM_BASE_URL``
        (default NVIDIA's), ``PRADYOS_LLM_MAX_TOKENS`` and ``PRADYOS_LLM_TOP_P``
        are optional.
      * ``openai`` / ``openai-compat`` — any other OpenAI-compatible API. Requires
        ``PRADYOS_LLM_BASE_URL`` + ``PRADYOS_LLM_MODEL``; optional ``PRADYOS_LLM_API_KEY``.
      Misconfigured ⇒ falls back to local Ollama (never fails open).
    """
    env = env if env is not None else os.environ
    kind = (env.get("PRADYOS_LLM_PROVIDER") or "ollama").strip().lower()

    def _opt_int(key: str) -> int | None:
        try:
            return int(env[key]) if env.get(key) else None
        except (TypeError, ValueError):
            return None

    def _opt_float(key: str) -> float | None:
        try:
            return float(env[key]) if env.get(key) else None
        except (TypeError, ValueError):
            return None

    if kind in ("nvidia", "nim"):
        api_key = env.get("PRADYOS_LLM_API_KEY")
        if api_key:
            return OpenAICompatProvider(
                base_url=env.get("PRADYOS_LLM_BASE_URL", _NVIDIA_NIM_URL),
                model=_resolve_model(env.get("PRADYOS_LLM_MODEL")),
                api_key=api_key,
                max_tokens=_opt_int("PRADYOS_LLM_MAX_TOKENS"),
                top_p=_opt_float("PRADYOS_LLM_TOP_P"),
            )
        log.warning(
            "PRADYOS_LLM_PROVIDER=nvidia but PRADYOS_LLM_API_KEY missing; using local Ollama"
        )
    elif kind in ("openai", "openai-compat", "http"):
        base_url = env.get("PRADYOS_LLM_BASE_URL")
        model = env.get("PRADYOS_LLM_MODEL")
        if base_url and model:
            return OpenAICompatProvider(
                base_url=base_url,
                model=model,
                api_key=env.get("PRADYOS_LLM_API_KEY"),
                max_tokens=_opt_int("PRADYOS_LLM_MAX_TOKENS"),
                top_p=_opt_float("PRADYOS_LLM_TOP_P"),
            )
        log.warning(
            "PRADYOS_LLM_PROVIDER=%s but base_url/model missing; falling back to local Ollama",
            kind,
        )
    return OllamaProvider(
        base_url=env.get("PRADYOS_OLLAMA_URL", _DEFAULT_OLLAMA_URL),
        model=env.get("PRADYOS_LLM_MODEL", _DEFAULT_LOCAL_MODEL),
    )
