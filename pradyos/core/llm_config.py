"""Runtime LLM provider configuration — switch providers without restart.

Stores the active provider config in a JSON file (``var/state/llm_config.json``)
so it survives restarts. Call ``reconfigure()`` to hot-swap the LLM provider
all agents share. If no config file exists, falls back to environment variables.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from pradyos.core.llm import OpenAICompatProvider, OllamaProvider, resolve_provider

log = logging.getLogger("pradyos.llm_config")

_STATE_DIR = Path(os.environ.get("PRADYOS_STATE_PATH", str(Path(__file__).resolve().parent.parent.parent / "var" / "state")))
_CONFIG_PATH = _STATE_DIR / "llm_config.json"

_lock = Lock()
_provider = None


def _get_provider() -> Any:
    global _provider
    with _lock:
        if _provider is not None:
            return _provider
        _provider = _load_or_resolve()
        return _provider


def _load_or_resolve() -> Any:
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            kind = data.get("provider", "ollama")
            if kind in ("nvidia", "nim", "openai", "openai-compat"):
                return OpenAICompatProvider(
                    base_url=data["base_url"],
                    model=data["model"],
                    api_key=data.get("api_key") or None,
                    max_tokens=data.get("max_tokens"),
                    top_p=data.get("top_p"),
                )
        except Exception as exc:
            log.warning("Failed to load saved LLM config: %s; falling back to env", exc)
    return resolve_provider()


def get() -> Any:
    return _get_provider()


def current_config() -> dict[str, Any]:
    p = _get_provider()
    info = p.info() if hasattr(p, "info") else {"provider": getattr(p, "name", "unknown")}
    if _CONFIG_PATH.exists():
        try:
            saved = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            info["configured"] = {k: v for k, v in saved.items() if k != "api_key"}
            info["has_api_key"] = bool(saved.get("api_key"))
        except Exception:
            pass
    else:
        info["configured"] = {"from_env": True}
        info["has_api_key"] = bool(os.environ.get("PRADYOS_LLM_API_KEY"))
    return info


def reconfigure(
    provider: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    global _provider
    kind = provider.strip().lower()

    if kind in ("ollama",):
        new = OllamaProvider(
            base_url=base_url or os.environ.get("PRADYOS_OLLAMA_URL", "http://localhost:11434"),
            model=model or os.environ.get("PRADYOS_LLM_MODEL", "qwen2.5-coder:7b"),
        )
        config = {"provider": "ollama", "base_url": new.base_url, "model": new.model}
    elif kind in ("nvidia", "nim"):
        default_url = "https://integrate.api.nvidia.com/v1"
        default_model = "meta/llama-3.3-70b-instruct"
        b_url = base_url or default_url
        mdl = model or default_model
        if not api_key:
            return {"error": "API key required for NVIDIA provider"}
        new = OpenAICompatProvider(base_url=b_url, model=mdl, api_key=api_key, max_tokens=max_tokens, top_p=top_p)
        config = {"provider": "nvidia", "base_url": b_url, "model": mdl}
        if api_key:
            config["api_key"] = api_key
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        if top_p is not None:
            config["top_p"] = top_p
    elif kind in ("openai", "openai-compat"):
        if not base_url or not model:
            return {"error": "base_url and model required for OpenAI-compatible provider"}
        new = OpenAICompatProvider(base_url=base_url, model=model, api_key=api_key or None, max_tokens=max_tokens, top_p=top_p)
        config = {"provider": "openai-compat", "base_url": base_url, "model": model}
        if api_key:
            config["api_key"] = api_key
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        if top_p is not None:
            config["top_p"] = top_p
    else:
        return {"error": f"Unknown provider: {kind}"}

    with _lock:
        _provider = new

    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    result = {k: v for k, v in config.items() if k != "api_key"}
    result["has_api_key"] = bool(config.get("api_key"))
    result["status"] = "configured"
    return result
