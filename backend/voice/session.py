"""One live conversation over a WebSocket.

    microphone frames -> VAD -> speech-to-text -> AnswerEngine -> text-to-speech -> audio frames

At most one turn runs at a time. When the caller interrupts, the turn number moves on: the running
task is cancelled, which closes the LLM stream, and any audio still queued for the old turn is
dropped by the sender, so stale audio cannot reach the speaker. The answer kept in memory is cut
back to what the caller actually heard, so the next reply does not assume they heard the rest.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import numpy as np
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from agent_engine.config.schema import LANGUAGE_NAMES, AgentConfig
from agent_engine.orchestration.turn import TurnEvent
from backend import metrics
from backend.db import new_id, now_iso
from backend.metrics import Stopwatch, TurnTimings
from backend.runtime import Runtime
from backend.voice.protocol import MAX_AUDIO_FRAME_BYTES, MAX_TEXT_FRAME_BYTES, audio_frame, split_pcm
from knowledge_engine.ingestion.chunker import detect_script_language
from llm_engine.providers.base import ChatMessage
from voice_engine.stt.whisper import PeriodicPartial
from voice_engine.tts.engine import to_pcm16, trim_silence
from voice_engine.tts.voices import Voice, default_voice, voice_by_id, voices_for
from voice_engine.vad.silero import UtteranceDetector, VadStream

log = logging.getLogger("vap.session")

IDLE_LIMIT_SECONDS = 600
MAX_SESSION_SECONDS = 1800
PARTIAL_EVERY_MS = 600
SEND_QUEUE_LIMIT = 600
BARGE_GRACE_MS = 400  # the speaker's output delay: audio this recent may not have been heard


@dataclass
class SpokenPart:
    text: str
    start_ms: float
    audio_ms: float


@dataclass
class ConversationContext:
    id: str
    tenant_id: str
    agent_id: str
    agent: AgentConfig
    kb_ids: list[str]
    keep_history: bool
    language: str
    voice_id: str
    mode: str = "voice"


@dataclass
class ActiveAnswer:
    turn: int
    message_id: str | None = None
    parts: list[SpokenPart] = field(default_factory=list)
    audio_ms: float = 0.0
    finished: bool = False
    any_audio: bool = False


class VoiceSession:
    def __init__(
        self, websocket: WebSocket, runtime: Runtime, context: ConversationContext, resuming: bool = False
    ) -> None:
        self.ws = websocket
        self.runtime = runtime
        self.context = context
        self.language = context.language
        self.voice: Voice | None = voice_by_id(context.voice_id) or default_voice(self.language, runtime.settings.models_dir)
        self.speak_replies = context.mode == "voice"
        self.detector = (
            UtteranceDetector(VadStream(runtime.vad_model), runtime.vad_settings) if runtime.vad_model else None
        )
        self.history: list[ChatMessage] = []
        self._out: asyncio.Queue = asyncio.Queue(maxsize=SEND_QUEUE_LIMIT)
        self._turn = 0
        self._task: asyncio.Task | None = None
        self._answer: ActiveAnswer | None = None
        self._played_ms = 0.0
        self._speech_end_at: float | None = None
        self._carry = ""  # words of a turn cancelled before any reply was heard
        self._pending_timings: TurnTimings | None = None
        self._last_activity = time.monotonic()
        self._started = time.monotonic()
        self._speaking_timer: asyncio.TimerHandle | None = None
        self._partial_stream = None
        self._partial_decoder: PeriodicPartial | None = None
        self._partial_running = False
        self._closed = False
        self._state = ""
        self._resuming = resuming
        self._end_reason = "disconnected"

    # ---- sending -------------------------------------------------------------------------

    async def _send_json(self, payload: dict) -> None:
        if self._closed:
            return
        try:
            self._out.put_nowait(("json", 0, payload))
        except asyncio.QueueFull:
            log.warning("Send queue full; closing a slow client.")
            await self._close(1013)

    async def _send_audio(self, turn: int, frame: bytes) -> None:
        # Waiting here is the backpressure: a slow client slows its own synthesis, nobody else's.
        await self._out.put(("audio", turn, frame))

    async def _send_loop(self) -> None:
        while True:
            kind, turn, payload = await self._out.get()
            if kind == "stop":
                return
            if kind == "audio" and turn != self._turn:
                continue  # audio of an interrupted turn
            try:
                if kind == "audio":
                    await self.ws.send_bytes(payload)
                else:
                    await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
            except (WebSocketDisconnect, RuntimeError):
                return

    async def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            await self._send_json({"type": "state", "state": state})

    # ---- lifecycle -----------------------------------------------------------------------

    async def run(self) -> None:
        sender = asyncio.create_task(self._send_loop())
        watchdog = asyncio.create_task(self._watchdog())
        warm = asyncio.create_task(self._warm_up())
        try:
            await self._send_json(
                {
                    "type": "ready",
                    "conversation_id": self.context.id,
                    "language": self.language,
                    "voice": self.voice.id if self.voice else None,
                    "sample_rate": 16000,
                    "degraded": self.runtime.sessions.degraded,
                }
            )
            await self._greet()
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                self._last_activity = time.monotonic()
                if message.get("bytes") is not None:
                    await self._on_audio(message["bytes"])
                elif message.get("text") is not None:
                    if await self._on_control(message["text"]):
                        break
        except WebSocketDisconnect:
            pass
        finally:
            await self._finish()
            watchdog.cancel()
            warm.cancel()
            self._out.put_nowait(("stop", 0, None)) if not self._out.full() else sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    async def _warm_up(self) -> None:
        engine = self.runtime.engine_for(self.context.tenant_id, self.context.kb_ids)
        await engine.warm_up(self.context.agent)
        if self.speak_replies and self.detector:
            # Load the recogniser now, so the caller's first sentence does not pay for it.
            await asyncio.get_running_loop().run_in_executor(None, self.runtime.recogniser, self.language)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = time.monotonic()
            if now - self._last_activity > IDLE_LIMIT_SECONDS or now - self._started > MAX_SESSION_SECONDS:
                self._end_reason = "time limit"
                await self._send_json({"type": "ended", "reason": "time limit"})
                await self._close(1000)
                return

    async def _close(self, code: int) -> None:
        self._closed = True
        if self.ws.client_state == WebSocketState.CONNECTED:
            try:
                await self.ws.close(code)
            except RuntimeError:
                pass

    async def _finish(self) -> None:
        self._closed = True
        self._bump_turn()
        await self._cancel_task()
        self._persist_timings()
        # A dropped connection may come back. Only the caller or the time limit closes a conversation.
        self.runtime.db.execute(
            "UPDATE conversations SET ended_at = ?, end_reason = ? WHERE id = ? AND ended_at IS NULL",
            (now_iso(), self._end_reason, self.context.id),
        )

    async def _cancel_task(self) -> None:
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _bump_turn(self) -> int:
        self._turn += 1
        return self._turn

    # ---- input ---------------------------------------------------------------------------

    async def _on_control(self, raw: str) -> bool:
        """Return True when the conversation should end."""
        if len(raw) > MAX_TEXT_FRAME_BYTES:
            await self._send_error("too_long", "That message is too long.")
            return False
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return False
        kind = message.get("type") if isinstance(message, dict) else None
        if kind == "text":
            text = str(message.get("text", "")).strip()
            if text:
                await self._interrupt("text")
                self._language_from_text(text)
                self._start_turn(text=text)
        elif kind == "interrupt":
            await self._interrupt("button")
        elif kind == "playback":
            await self._on_playback(message)
        elif kind == "audible":
            self._on_audible(message)
        elif kind == "language":
            await self._switch_language(str(message.get("language", "")))
        elif kind == "voice":
            await self._switch_voice(str(message.get("voice", "")))
        elif kind == "mode":
            self.speak_replies = message.get("mode") == "voice"
            await self._send_json({"type": "mode", "mode": "voice" if self.speak_replies else "text"})
        elif kind == "end":
            self._end_reason = "caller"
            await self._send_json({"type": "ended", "reason": "caller"})
            return True
        return False

    async def _on_audio(self, pcm: bytes) -> None:
        if self.detector is None or not self.speak_replies or len(pcm) > MAX_AUDIO_FRAME_BYTES or len(pcm) % 2:
            return
        was_speaking = self.detector.in_speech
        events = self.detector.feed(pcm)
        for event in events:
            await self._on_vad(event)
        if self.detector.in_speech or was_speaking:
            await self._feed_partial(pcm)
        if events or int(self.detector.processed_ms) % 96 == 0:
            await self._send_json({"type": "level", "p": round(self.detector.last_probability, 2)})

    async def _on_vad(self, event) -> None:
        if event.kind == "speech_start":
            await self._send_json({"type": "speech_start"})
            if self._answer_is_pending():
                await self._cancel_before_reply()
            await self._set_state("listening")
        elif event.kind == "barge_in":
            await self._interrupt("speech")
        elif event.kind == "speech_end":
            self._speech_end_at = time.perf_counter()
            self._reset_partial()
            turn = self._bump_turn()
            await self._send_json({"type": "speech_end", "turn": turn})
            self._task = asyncio.create_task(self._run_turn(turn, audio=event.audio, timing=event.timing))

    def _answer_is_pending(self) -> bool:
        """A reply is being prepared and the caller has not heard any of it."""
        return bool(self._task and not self._task.done() and not (self._answer and self._answer.any_audio))

    async def _cancel_before_reply(self) -> None:
        """The caller kept talking: drop the half-made reply and join the two utterances."""
        self._bump_turn()
        await self._cancel_task()

    async def _interrupt(self, reason: str) -> None:
        answer = self._answer
        busy = bool(self._task and not self._task.done())
        audible = bool(answer and answer.any_audio and self.detector and self.detector.agent_speaking)
        if not busy and not audible:
            return
        old_turn = self._turn
        self._bump_turn()
        await self._cancel_task()
        self._set_agent_speaking(False)
        metrics.BARGE_INS.inc()
        if self._pending_timings:
            self._pending_timings.interrupted = True
        await self._send_json({"type": "flush", "turn": old_turn, "reason": reason})
        if answer:
            self._keep_what_was_heard(answer)
        await self._set_state("listening")

    def _keep_what_was_heard(self, answer: ActiveAnswer) -> None:
        heard_until = max(self._played_ms - BARGE_GRACE_MS, 0)
        heard = [part.text for part in answer.parts if part.start_ms <= heard_until or not self.speak_replies]
        text = " ".join(heard)
        # Drop the assistant entry for this answer, then keep only what the caller heard.
        if self.history and self.history[-1].role == "assistant":
            self.history.pop()
        if text:
            self.history.append(ChatMessage("assistant", text))
        if answer.message_id:
            self.runtime.db.execute(
                "UPDATE messages SET interrupted = 1, text = ? WHERE id = ?",
                (text or "(interrupted before any words were heard)", answer.message_id),
            )
        self._answer = None

    async def _on_playback(self, message: dict) -> None:
        if message.get("turn") != self._current_answer_turn():
            return
        played = message.get("played_ms")
        if isinstance(played, int | float):
            self._played_ms = float(played)
        if message.get("finished"):
            self._set_agent_speaking(False)
            if self._task is None or self._task.done():
                await self._set_state("listening")

    def _current_answer_turn(self) -> int | None:
        return self._answer.turn if self._answer else None

    def _on_audible(self, message: dict) -> None:
        delay = message.get("after_speech_end_ms")
        timings = self._pending_timings
        if timings and message.get("turn") == timings.turn and isinstance(delay, int | float):
            timings.first_audible_ms = round(float(delay), 1)
            self._persist_timings()

    def _set_agent_speaking(self, speaking: bool) -> None:
        if self.detector:
            self.detector.agent_speaking = speaking
        if self._speaking_timer:
            self._speaking_timer.cancel()
            self._speaking_timer = None

    def _expect_speech_end(self, seconds: float) -> None:
        """The browser normally reports when playback ends; this covers a report that never comes."""
        if self._speaking_timer:
            self._speaking_timer.cancel()
        loop = asyncio.get_running_loop()
        self._speaking_timer = loop.call_later(seconds + 1.5, self._set_agent_speaking, False)

    # ---- partial transcripts -------------------------------------------------------------

    def _reset_partial(self) -> None:
        self._partial_stream = None
        self._partial_decoder = None

    async def _feed_partial(self, pcm: bytes) -> None:
        if not self.runtime.plan.partial_transcripts or self.runtime.sessions.degraded:
            return
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if self.language == "hi":
            await self._partial_streaming(audio)
        else:
            await self._partial_periodic(audio)

    async def _partial_streaming(self, audio: np.ndarray) -> None:
        if self._partial_stream is None:
            model = self.runtime.streaming_hindi()
            if model is None:
                return
            self._partial_stream = model.stream()
            self._partial_buffer: list[np.ndarray] = []
        self._partial_buffer.append(audio)
        if self._partial_running:
            return
        self._partial_running = True
        stream = self._partial_stream

        async def work() -> None:
            try:
                chunk = np.concatenate(self._partial_buffer)
                self._partial_buffer = []
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, stream.accept, chunk)
                if stream is self._partial_stream:
                    text = stream.text()
                    if text:
                        await self._send_json({"type": "partial", "text": text})
            finally:
                self._partial_running = False

        asyncio.create_task(work())

    async def _partial_periodic(self, audio: np.ndarray) -> None:
        if self._partial_decoder is None:
            self._partial_decoder = PeriodicPartial(self.runtime.recogniser(self.language), self.language, PARTIAL_EVERY_MS)
        partial = self._partial_decoder
        partial.accept(audio)
        if self._partial_running or not partial.due():
            return
        self._partial_running = True

        async def work() -> None:
            try:
                text = await self.runtime.run_stt(partial.decode)
                if partial is self._partial_decoder and text:
                    await self._send_json({"type": "partial", "text": text})
            finally:
                self._partial_running = False

        asyncio.create_task(work())

    # ---- language and voice --------------------------------------------------------------

    def _language_from_text(self, text: str) -> None:
        """Typed text shows its language by its script, which is reliable."""
        found = detect_script_language(text)
        if found in ("hi", "bn") and found != self.language and found in self.context.agent.languages:
            self._apply_language(found)

    def _apply_language(self, language: str) -> None:
        self.language = language
        current = self.voice.language if self.voice else ""
        if current != language:
            self.voice = default_voice(language, self.runtime.settings.models_dir)
        self._reset_partial()

    async def _switch_language(self, language: str) -> None:
        if language not in self.context.agent.languages or language == self.language:
            return
        await self._interrupt("language")
        self._apply_language(language)
        self.runtime.db.execute(
            "UPDATE conversations SET language = ?, voice = ? WHERE id = ?",
            (language, self.voice.id if self.voice else "", self.context.id),
        )
        await self._send_json(
            {"type": "language", "language": language, "voice": self.voice.id if self.voice else None}
        )

    async def _switch_voice(self, voice_id: str) -> None:
        voice = voice_by_id(voice_id)
        allowed = voices_for(self.language, self.runtime.settings.models_dir)
        if voice and voice in allowed:
            self.voice = voice
            await self._send_json({"type": "voice", "voice": voice.id})

    # ---- turns ---------------------------------------------------------------------------

    def _start_turn(self, text: str) -> None:
        turn = self._bump_turn()
        self._speech_end_at = time.perf_counter()
        self._task = asyncio.create_task(self._run_turn(turn, text=text))

    def _restore_history(self) -> None:
        """After a dropped connection, the conversation carries on from what was stored."""
        keep = self.context.agent.memory.keep_turns * 2
        rows = self.runtime.db.all(
            "SELECT role, text FROM messages WHERE conversation_id = ? AND tenant_id = ?"
            " ORDER BY created_at DESC LIMIT ?",
            (self.context.id, self.context.tenant_id, keep),
        )
        self.history = [ChatMessage(row["role"], row["text"]) for row in reversed(rows)]

    async def _greet(self) -> None:
        if self._resuming:
            self._restore_history()
        greeting = self.context.agent.greeting.get(self.language) or ""
        if self._resuming or not greeting:
            await self._set_state("listening")
            return
        turn = self._bump_turn()
        self._task = asyncio.create_task(self._run_fixed(turn, greeting))

    async def _run_fixed(self, turn: int, text: str) -> None:
        answer = self._begin_answer(turn)
        await self._send_json({"type": "agent_start", "turn": turn})
        await self._send_json({"type": "agent_text", "turn": turn, "text": text})
        if self.speak_replies:
            await self._set_state("speaking")
            await self._speak(answer, text, None, None)
        answer.finished = True
        answer.message_id = self._store_message("assistant", text, self.language)
        self.history.append(ChatMessage("assistant", text))
        await self._send_json({"type": "turn_end", "turn": turn, "audio_ms": answer.audio_ms})
        if not self.speak_replies:
            await self._set_state("listening")

    def _begin_answer(self, turn: int) -> ActiveAnswer:
        self._played_ms = 0.0
        self._answer = ActiveAnswer(turn)
        return self._answer

    async def _run_turn(
        self, turn: int, audio: np.ndarray | None = None, text: str | None = None, timing: dict | None = None
    ) -> None:
        self._persist_timings()
        timings = TurnTimings(turn=turn, language=self.language)
        self._pending_timings = timings
        clock = Stopwatch()
        try:
            await self._set_state("thinking")
            if audio is not None:
                timings.speech_ms = (timing or {}).get("speech_ms")
                recogniser = await asyncio.get_running_loop().run_in_executor(
                    None, self.runtime.recogniser, self.language
                )
                transcript = await self.runtime.run_stt(recogniser.transcribe, audio, self.language)
                timings.stt_final_ms = clock.ms()
                text = transcript.text
                if not text.strip():
                    await self._send_json({"type": "final", "turn": turn, "text": ""})
                    await self._set_state("listening")
                    return
            question = f"{self._carry} {text}".strip()
            self._carry = question
            await self._send_json({"type": "final", "turn": turn, "text": question, "language": self.language})
            await self._reply(turn, question, timings, clock)
        except asyncio.CancelledError:
            timings.outcome = "cancelled"
            raise
        except Exception:
            log.exception("Turn failed.")
            await self._send_error("turn_failed", "Something went wrong. Please try again.")
            await self._set_state("listening")
        finally:
            if timings.total_ms is None:
                timings.total_ms = clock.ms()

    async def _reply(self, turn: int, question: str, timings: TurnTimings, clock: Stopwatch) -> None:
        agent = self.context.agent
        language = self.language
        answer = self._begin_answer(turn)
        engine = self.runtime.engine_for(self.context.tenant_id, self.context.kb_ids)
        speech_queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        speaker = asyncio.create_task(self._speak_queue(answer, speech_queue, timings, clock))
        written: list[str] = []
        sources: list[dict] = []
        confidence: float | None = None
        outcome = "answered"
        try:
            async for event in engine.answer(agent, language, list(self.history), question):
                kind = event.kind
                if kind == "retrieval":
                    timings.retrieval_ms = event.data.get("ms")
                    sources = event.data.get("sources", [])
                    confidence = event.data.get("confidence")
                    await self._send_json({"type": "sources", "turn": turn, "sources": sources, "confidence": confidence})
                elif kind == "first_token":
                    timings.llm_first_token_ms = event.data.get("ms")
                elif kind == "sentence":
                    written.append(event.text)
                    await self._send_json({"type": "agent_text", "turn": turn, "text": event.text})
                    await speech_queue.put(event.text)
                elif kind == "escalation":
                    self._escalate(event)
                    await self._send_json({"type": "escalation", "severity": event.data.get("severity")})
                elif kind == "refused":
                    outcome = "refused"
                elif kind == "fallback":
                    await self._send_json({"type": "notice", "code": "approved_text", "reason": event.data.get("reason")})
                elif kind == "dropped":
                    log.info("Dropped a sentence: %s", event.data.get("reason"))
                elif kind == "done":
                    outcome = event.data.get("kind", outcome)
            await speech_queue.put(None)
            await speaker
        except BaseException:
            speaker.cancel()
            raise

        # The caller's words stay as one turn even when two utterances were joined.
        self._carry = ""
        self.history.append(ChatMessage("user", question))
        full_text = " ".join(written)
        self.history.append(ChatMessage("assistant", full_text))
        self._store_message("user", question, language)
        answer.message_id = self._store_message("assistant", full_text, language, sources, confidence)
        answer.finished = True
        timings.outcome = outcome
        timings.total_ms = clock.ms()
        metrics.TURNS.labels(language, outcome).inc()
        await self._send_json(
            {"type": "turn_end", "turn": turn, "audio_ms": answer.audio_ms, "outcome": outcome, "timings": timings.to_dict()}
        )
        if not self.speak_replies or not answer.any_audio:
            await self._set_state("listening")

    async def _speak_queue(self, answer: ActiveAnswer, queue: asyncio.Queue, timings: TurnTimings, clock: Stopwatch) -> None:
        while True:
            text = await queue.get()
            if text is None:
                return
            if self.speak_replies:
                await self._speak(answer, text, timings, clock)
            else:
                answer.parts.append(SpokenPart(text, 0.0, 0.0))

    async def _speak(
        self, answer: ActiveAnswer, text: str, timings: TurnTimings | None, clock: Stopwatch | None
    ) -> None:
        if self.voice is None:
            await self._send_error("no_voice", "No voice is installed for this language. Text replies still work.")
            return
        loop = asyncio.get_running_loop()
        self.runtime.sessions.tts_waiting += 1
        try:
            samples, rate = await loop.run_in_executor(self.runtime.tts_pool, self.runtime.speech.synthesise, text, self.voice)
        finally:
            self.runtime.sessions.tts_waiting -= 1
        if answer.turn != self._turn:
            return
        samples = trim_silence(samples, rate)
        duration_ms = len(samples) * 1000 / rate
        if timings and clock and timings.tts_first_audio_ms is None:
            timings.tts_first_audio_ms = clock.ms()
        answer.parts.append(SpokenPart(text, answer.audio_ms, duration_ms))
        # Set for every sentence: playback can run dry between two sentences and report "finished".
        self._set_agent_speaking(True)
        if not answer.any_audio:
            answer.any_audio = True
            await self._set_state("speaking")
            await self._send_json({"type": "agent_start", "turn": answer.turn})
            if timings and clock:
                timings.first_audio_sent_ms = clock.ms()
        index = len(answer.parts) * 1000
        for chunk in split_pcm(to_pcm16(samples), rate):
            await self._send_audio(answer.turn, audio_frame(answer.turn, index, rate, chunk))
            index += 1
        answer.audio_ms += duration_ms
        self._expect_speech_end(answer.audio_ms / 1000)

    # ---- records -------------------------------------------------------------------------

    def _store_message(
        self, role: str, text: str, language: str, sources: list | None = None, confidence: float | None = None
    ) -> str | None:
        if not self.context.keep_history or not self.context.agent.memory.store_transcripts:
            return None
        message_id = new_id()
        self.runtime.db.execute(
            "INSERT INTO messages (id, conversation_id, tenant_id, role, text, language, sources, confidence, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                self.context.id,
                self.context.tenant_id,
                role,
                text,
                language,
                json.dumps(sources or [], ensure_ascii=False),
                confidence,
                now_iso(),
            ),
        )
        return message_id

    def _escalate(self, event: TurnEvent) -> None:
        severity = event.data.get("severity") or "human"
        metrics.ESCALATIONS.labels(severity).inc()
        self.runtime.db.execute(
            "INSERT INTO escalations (id, tenant_id, conversation_id, agent_id, rule, severity, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                self.context.tenant_id,
                self.context.id,
                self.context.agent_id,
                event.data.get("rule", ""),
                severity,
                now_iso(),
            ),
        )

    def _persist_timings(self) -> None:
        timings, self._pending_timings = self._pending_timings, None
        if not timings or not timings.outcome:
            return
        timings.observe()
        self.runtime.db.execute(
            "INSERT INTO turn_metrics (tenant_id, language, metrics, created_at) VALUES (?, ?, ?, ?)",
            (self.context.tenant_id, timings.language, json.dumps(timings.to_dict()), now_iso()),
        )

    async def _send_error(self, code: str, message: str) -> None:
        await self._send_json({"type": "error", "code": code, "message": message})


def language_label(language: str) -> str:
    return LANGUAGE_NAMES.get(language, language)
