"""Tests for the pluggable LLM provider — routing + prompt assembly, no network."""

from __future__ import annotations

import pytest

from pradyos.core.llm import (
    LLMError,
    OllamaProvider,
    OpenAICompatProvider,
    resolve_provider,
)
from pradyos.evolve import LLMProposer
from pradyos.guild import LLMGuildWorker, Role


class _FakeProvider:
    name = "fake"

    def __init__(self, out: str = "") -> None:
        self.out = out
        self.seen: list[str] = []

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        self.seen.append(prompt)
        return self.out


# ── resolve_provider: defaults to local, opt-in to stronger ────────────────────


def test_resolve_default_is_local_ollama():
    p = resolve_provider({})
    assert p.name == "ollama" and p.model == "qwen2.5-coder:7b"


def test_resolve_local_model_override():
    p = resolve_provider({"PRADYOS_LLM_MODEL": "llama3:70b"})
    assert p.name == "ollama" and p.model == "llama3:70b"


def test_resolve_openai_compatible_provider():
    p = resolve_provider(
        {
            "PRADYOS_LLM_PROVIDER": "openai",
            "PRADYOS_LLM_BASE_URL": "https://api.example.com/v1",
            "PRADYOS_LLM_MODEL": "gpt-strong",
            "PRADYOS_LLM_API_KEY": "sk-secret",
        }
    )
    assert p.name == "openai-compat" and p.model == "gpt-strong"
    # The API key must NEVER appear in info().
    assert "sk-secret" not in str(p.info())


def test_resolve_openai_misconfigured_falls_back_to_local():
    # provider=openai but no base_url/model → never fail open; use local.
    p = resolve_provider({"PRADYOS_LLM_PROVIDER": "openai"})
    assert p.name == "ollama"


def test_resolve_nvidia_nim_with_key():
    p = resolve_provider({"PRADYOS_LLM_PROVIDER": "nvidia", "PRADYOS_LLM_API_KEY": "nvapi-x"})
    assert p.name == "openai-compat"
    assert p.base_url == "https://integrate.api.nvidia.com/v1"  # NVIDIA default
    assert p.model == "meta/llama-3.3-70b-instruct"  # default model
    assert "nvapi-x" not in str(p.info())  # key never exposed


def test_resolve_nvidia_model_override():
    p = resolve_provider(
        {
            "PRADYOS_LLM_PROVIDER": "nim",
            "PRADYOS_LLM_API_KEY": "nvapi-x",
            "PRADYOS_LLM_MODEL": "nvidia/llama-3.1-nemotron-70b-instruct",
        }
    )
    assert p.model == "nvidia/llama-3.1-nemotron-70b-instruct"


def test_resolve_nvidia_without_key_falls_back_to_local():
    # NVIDIA needs a key; without one, never fail open → local.
    p = resolve_provider({"PRADYOS_LLM_PROVIDER": "nvidia"})
    assert p.name == "ollama"


def test_openai_provider_requires_base_url_and_model():
    with pytest.raises(LLMError):
        OpenAICompatProvider(base_url="", model="x")
    with pytest.raises(LLMError):
        OpenAICompatProvider(base_url="https://x", model="")


def test_ollama_info_shape():
    info = OllamaProvider(model="m").info()
    assert info["provider"] == "ollama" and info["model"] == "m" and "base_url" in info


# ── proposer / worker build prompts and use the provider ───────────────────────


def test_llm_proposer_strips_fences_and_uses_provider():
    fake = _FakeProvider("```python\nx = 1\n```")
    out = LLMProposer(fake)("BEFORE_SRC", "harden error handling")
    assert out == "x = 1\n"
    assert "harden error handling" in fake.seen[0] and "BEFORE_SRC" in fake.seen[0]


def test_llm_guild_worker_uses_provider_with_role_context():
    fake = _FakeProvider("my contribution")
    role = Role("planner", "strategy", "plan it")
    out = LLMGuildWorker(fake)(role, "ship a CLI", [{"role": "x", "content": "prior"}])
    assert out == "my contribution"
    assert "planner" in fake.seen[0] and "ship a CLI" in fake.seen[0] and "prior" in fake.seen[0]


def test_ollama_subclasses_are_llm_backed():
    # Back-compat: OllamaProposer/OllamaGuildWorker still construct (Ollama default).
    from pradyos.evolve import OllamaProposer
    from pradyos.guild import OllamaGuildWorker

    assert isinstance(OllamaProposer(), LLMProposer)
    assert isinstance(OllamaGuildWorker(), LLMGuildWorker)
