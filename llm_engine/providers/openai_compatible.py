"""Any server that speaks the OpenAI chat format: llama.cpp, Ollama, vLLM or SGLang.

The default target is a local llama-server, so no key and no outside service is involved. A hosted
endpoint can be set in configuration as an optional adapter; nothing in the app requires one.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from llm_engine.providers.base import ChatMessage, LLMUnavailable


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str = "local", api_key: str = "", timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            headers=headers, timeout=httpx.Timeout(timeout, connect=3.0), limits=httpx.Limits(max_keepalive_connections=8)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def stream_chat(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        body = {
            "model": self._model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "cache_prompt": True,  # llama-server reuses the shared prompt prefix between turns
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            # Leaving the context closes the socket, and llama-server stops generating.
            async with self._client.stream("POST", f"{self._base_url}/chat/completions", json=body) as response:
                if response.status_code != 200:
                    detail = (await response.aread()).decode("utf-8", "replace")[:200]
                    raise LLMUnavailable(f"LLM returned {response.status_code}: {detail}")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        return
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text
        except httpx.HTTPError as error:
            raise LLMUnavailable(f"LLM request failed: {error}") from error

    async def healthy(self) -> bool:
        root = self._base_url.removesuffix("/v1")
        try:
            response = await self._client.get(f"{root}/health", timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200
