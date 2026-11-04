"""Pick the LLM provider from configuration. Changing model or runtime never changes agent code."""
from __future__ import annotations

from llm_engine.providers.base import LLMProvider
from llm_engine.providers.openai_compatible import OpenAICompatibleProvider

MODEL_FILES = {
    "qwen3.5-0.8b-q4km": "Qwen3.5-0.8B-Q4_K_M.gguf",
    "qwen3.5-2b-q4km": "Qwen3.5-2B-Q4_K_M.gguf",
}
# Every one of these speaks the OpenAI chat format, so one adapter serves them all.
OPENAI_COMPATIBLE = {"llama-server", "ollama", "vllm", "sglang", "openai-compatible"}


def build_provider(settings) -> LLMProvider:
    if settings.llm_provider not in OPENAI_COMPATIBLE:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}.")
    model = settings.llm_model or "local"
    return OpenAICompatibleProvider(settings.llm_base_url, model=model, api_key=settings.llm_api_key)
