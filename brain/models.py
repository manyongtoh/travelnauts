"""Which language model the agents use.

  sandbox          the deterministic stand-in in sandbox_model.py: no network, same inputs give the
                   same outputs, good for testing the flow and the screens. The writing is template based.
  ollama:<model>   a local model through Ollama, e.g. ollama:gemma4 (the pilot's choice for writing)
  openai:<model>   any OpenAI compatible endpoint at BRAIN_MODEL_BASE_URL (Azure AI Foundry, vLLM, ...)
"""
from __future__ import annotations

import os

from .config import get_settings

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def build_model(name: str | None = None):
    s = get_settings()
    name = name or s.model
    if name == "sandbox":
        from .sandbox_model import sandbox_model
        return sandbox_model()
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    if name.startswith("ollama:"):
        base = os.getenv("BRAIN_MODEL_BASE_URL", "http://localhost:11434/v1")
        return OpenAIChatModel(name.split(":", 1)[1], provider=OpenAIProvider(base_url=base, api_key="ollama"))
    if name.startswith("openai:"):
        return OpenAIChatModel(name.split(":", 1)[1], provider=OpenAIProvider(base_url=s.model_base_url, api_key=s.model_api_key))
    raise ValueError(f"Unknown BRAIN_MODEL {name!r}")
