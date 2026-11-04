"""One conversational turn, from the caller's words to speakable sentences.

    guards -> retrieval -> LLM -> sentence split -> sentence check -> speech

The engine knows nothing about audio or sockets, so it can be tested with text alone. It yields
events; the session decides what to do with them and can stop at any point by closing the iterator.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from agent_engine.config.schema import AgentConfig
from agent_engine.orchestration.prompt import build_messages, choose_passages, context_block, leak_marker, system_prompt
from agent_engine.policies.guards import check_sentence, screen_turn, small_talk
from knowledge_engine.ingestion.chunker import detect_script_language
from knowledge_engine.retrieval.retriever import Retrieval
from llm_engine.providers.base import ChatMessage, LLMProvider, LLMUnavailable

log = logging.getLogger("vap.turn")

# Hard sentence ends. Commas only count once a clause is long enough to sound natural alone.
_SENTENCE_END = re.compile(r"([.!?।॥]+)(\s+|$)")
_CLAUSE_END = re.compile(r"([,;:–—])(\s+)")
FIRST_CLAUSE_CHARS = 28
_DECIMAL = re.compile(r"\d\.$")


@dataclass
class TurnEvent:
    kind: str  # retrieval, sentence, dropped, escalation, fallback, done
    text: str = ""
    data: dict = field(default_factory=dict)


class SentenceSplitter:
    """Collect tokens and release speakable pieces as soon as each one is complete."""

    def __init__(self) -> None:
        self._buffer = ""
        self._released = 0

    def push(self, token: str) -> list[str]:
        self._buffer += token
        pieces: list[str] = []
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if match and not _DECIMAL.search(self._buffer[: match.end(1)]):
                pieces.append(self._take(match.end()))
                continue
            clause = _CLAUSE_END.search(self._buffer)
            if clause and self._released == 0 and clause.end() >= FIRST_CLAUSE_CHARS:
                # Only the first clause is sent early: it is what shortens the wait for audio.
                pieces.append(self._take(clause.end()))
                continue
            return pieces

    def _take(self, end: int) -> str:
        piece, self._buffer = self._buffer[:end].strip(), self._buffer[end:]
        self._released += 1
        return piece

    def flush(self) -> list[str]:
        rest = self._buffer.strip()
        self._buffer = ""
        return [rest] if rest else []


SearchFn = Callable[[str, str], Retrieval]


# Words that point back at something said earlier.
_REFERRING = frozenset(
    "it its they them their that there this these those "
    "वह वो यह ये उस उसका उसकी उसके इस इसका इसकी इसके वहाँ वहां यहाँ यहां "
    "এটা এটি ওটা সেটা সেটি এর ওর ওটির এটির সেখানে ওখানে এখানে তার".split()
)


def is_follow_up(question: str) -> bool:
    words = re.findall("[\\w\u0900-\u097f\u0980-\u09ff]+", question.lower())
    return bool(_REFERRING.intersection(words))


def search_query(history: list[ChatMessage], question: str) -> str:
    """A question such as "what are its timings?" means little alone, so the last question goes with it."""
    if not is_follow_up(question):
        return question
    for message in reversed(history):
        if message.role == "user":
            return f"{message.content} {question}"
    return question


def merge_retrievals(first: Retrieval, second: Retrieval, limit: int = 3) -> Retrieval:
    """The best hit of `first`, then the hits of `second`, with no passage twice."""
    hits = list(first.hits[:1])
    known = {hit.chunk.id for hit in hits}
    hits += [hit for hit in second.hits if hit.chunk.id not in known]
    return Retrieval(hits[:limit], max(first.confidence, second.confidence))


class AnswerEngine:
    def __init__(self, llm: LLMProvider, search: SearchFn, max_tokens: int = 160, temperature: float = 0.1) -> None:
        self._llm = llm
        self._search = search
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def warm_up(self, agent: AgentConfig) -> None:
        """Put the agent's fixed prompt in the model's cache, so the first answer starts sooner."""
        messages = [ChatMessage("system", system_prompt(agent)), ChatMessage("user", "Hello.")]
        stream = self._llm.stream_chat(messages, 1, 0.0)
        try:
            async for _ in stream:
                break
        except LLMUnavailable:
            log.info("Warm-up skipped: the language model is not available.")
        finally:
            await stream.aclose()

    async def answer(
        self, agent: AgentConfig, language: str, history: list[ChatMessage], question: str
    ) -> AsyncIterator[TurnEvent]:
        decision = screen_turn(agent, question, language)
        if decision.kind != "allow":
            if decision.kind == "escalate":
                yield TurnEvent("escalation", decision.response, {"rule": decision.rule_id, "severity": decision.severity})
            else:
                yield TurnEvent("refused", decision.response, {"rule": decision.rule_id, "reason": decision.kind})
            yield TurnEvent("sentence", decision.response, {"fixed": True})
            yield TurnEvent("done", data={"kind": decision.kind})
            return

        started = time.perf_counter()
        query = search_query(history, question)
        topic = query.removesuffix(question).strip()
        previous = next((item.content for item in reversed(history) if item.role == "assistant"), "")
        retrieval = await asyncio.to_thread(self._search, query, language)
        if topic:
            # The thing "it" points at must be in reach, even if the new words pull elsewhere.
            earlier = await asyncio.to_thread(self._search, topic, language)
            retrieval = merge_retrievals(earlier, retrieval)
        yield TurnEvent(
            "retrieval",
            data={
                "confidence": retrieval.confidence,
                "sources": [hit.source() for hit, _ in choose_passages(retrieval.hits, query, topic)],
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

        no_answer = agent.no_answer.get(language) or agent.no_answer["en"]
        if not retrieval.hits or retrieval.confidence < agent.min_confidence:
            yield TurnEvent("sentence", small_talk(question, language) or no_answer, {"fixed": True})
            yield TurnEvent("done", data={"kind": "no_answer"})
            return

        context = context_block(retrieval.hits, query, topic)
        marker = leak_marker(agent)
        messages = build_messages(agent, language, history, question, retrieval.hits, query, topic)
        splitter = SentenceSplitter()
        spoken = 0
        dropped = 0
        ungrounded = False
        first_token_ms: float | None = None
        generation_started = time.perf_counter()
        stream = self._llm.stream_chat(messages, self._max_tokens, self._temperature)
        try:
            async for token in stream:
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - generation_started) * 1000, 1)
                    yield TurnEvent("first_token", data={"ms": first_token_ms})
                for piece in splitter.push(token):
                    result = self._check(piece, context, agent, marker, language, previous)
                    if result is None:
                        spoken += 1
                        yield TurnEvent("sentence", piece)
                    else:
                        dropped += 1
                        ungrounded = ungrounded or result == "not grounded"
                        yield TurnEvent("dropped", piece, {"reason": result})
            for piece in splitter.flush():
                result = self._check(piece, context, agent, marker, language, previous)
                if result is None:
                    spoken += 1
                    yield TurnEvent("sentence", piece)
                else:
                    dropped += 1
                    ungrounded = ungrounded or result == "not grounded"
                    yield TurnEvent("dropped", piece, {"reason": result})
        except LLMUnavailable as error:
            log.warning("LLM unavailable, reading the approved passage instead: %s", error)
            yield TurnEvent("fallback", data={"reason": "llm unavailable"})
            for piece in self._approved_passage(retrieval, language, query):
                spoken += 1
                yield TurnEvent("sentence", piece, {"fixed": True})
        finally:
            await stream.aclose()

        if spoken == 0:
            # Every sentence failed its check. Read approved text rather than say nothing. When the
            # model wandered off the documents, the passage may not answer either, so say so.
            passage = [] if ungrounded else self._approved_passage(retrieval, language, query)
            if passage:
                yield TurnEvent("fallback", data={"reason": "all sentences dropped"})
                for piece in passage:
                    yield TurnEvent("sentence", piece, {"fixed": True})
            else:
                yield TurnEvent("sentence", no_answer, {"fixed": True})
        yield TurnEvent("done", data={"kind": "answered", "dropped": dropped})

    @staticmethod
    def _check(piece: str, context: str, agent: AgentConfig, marker: str, language: str, previous: str = "") -> str | None:
        reason = check_sentence(piece, context, agent, marker)
        if reason:
            return reason
        if previous and piece.strip() == previous.strip():
            return "repeated the last answer"  # a small model can parrot history instead of answering
        script = detect_script_language(piece)
        if script and script != language and len(piece) > 12:
            return "wrong language"
        return None

    @staticmethod
    def _approved_passage(retrieval: Retrieval, language: str, query: str = "") -> list[str]:
        same_language = [hit for hit in retrieval.hits if hit.chunk.language == language]
        pieces = [sentence for _, sentences in choose_passages(same_language, query) for sentence in sentences]
        if len(pieces) == 1:  # a whole passage, when no words matched
            splitter = SentenceSplitter()
            pieces = splitter.push(pieces[0]) + splitter.flush()
        return pieces[:3]
