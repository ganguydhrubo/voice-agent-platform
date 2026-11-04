"""The one interface the rest of the app knows. Swapping the LLM never touches agent code."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMUnavailable(RuntimeError):
    """The model cannot answer right now. The caller falls back to approved text."""


class LLMProvider(Protocol):
    name: str

    def stream_chat(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        """Yield text as it is generated. Closing the iterator must stop generation."""
        ...

    async def healthy(self) -> bool: ...


class ScriptedProvider:
    """Replies from a list. Used by tests so they run without a model."""

    name = "scripted"

    def __init__(self, replies: list[str] | None = None, delay: float = 0.0) -> None:
        self.replies = list(replies or [])
        self.delay = delay
        self.calls: list[list[ChatMessage]] = []
        self.cancelled = 0

    async def stream_chat(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        import asyncio

        self.calls.append(messages)
        reply = self.replies.pop(0) if self.replies else "Sample answer."
        try:
            for word in reply.split(" "):
                if self.delay:
                    await asyncio.sleep(self.delay)
                yield word + " "
        except (asyncio.CancelledError, GeneratorExit):
            self.cancelled += 1
            raise

    async def healthy(self) -> bool:
        return True
