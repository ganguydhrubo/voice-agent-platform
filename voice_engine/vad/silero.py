"""Voice activity detection with Silero VAD (MIT), run directly on ONNX Runtime.

The model is shared; each conversation has its own recurrent state. `UtteranceDetector` turns the
per-window probabilities into start, end and barge-in events. While the agent is speaking the bar
is higher, because a leftover echo of its own voice must not count as the caller interrupting.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
WINDOW_SAMPLES = 512  # 32 ms, the size Silero expects at 16 kHz
WINDOW_MS = 32
CONTEXT_SAMPLES = 64


class SileroModel:
    def __init__(self, path: Path, threads: int = 1) -> None:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self._rate = np.array(SAMPLE_RATE, dtype=np.int64)

    def run(self, window: np.ndarray, state: np.ndarray) -> tuple[float, np.ndarray]:
        output, next_state = self._session.run(None, {"input": window, "state": state, "sr": self._rate})
        return float(output.reshape(-1)[0]), next_state


class VadStream:
    """Per-conversation state. Audio goes in as float32 windows of exactly 512 samples."""

    def __init__(self, model: SileroModel) -> None:
        self._model = model
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)

    def probability(self, window: np.ndarray) -> float:
        batch = window.reshape(1, -1).astype(np.float32)
        joined = np.concatenate([self._context, batch], axis=1)
        value, self._state = self._model.run(joined, self._state)
        self._context = joined[:, -CONTEXT_SAMPLES:]
        return value


@dataclass
class VadSettings:
    threshold: float = 0.5
    release: float = 0.35  # stays "in speech" until probability falls below this
    speaking_threshold: float = 0.8  # bar while the agent's voice is playing
    min_speech_ms: int = 160
    barge_in_ms: int = 240
    end_silence_ms: int = 450
    pre_roll_ms: int = 256
    max_utterance_ms: int = 20000


@dataclass
class VadEvent:
    kind: str  # speech_start, barge_in, speech_end
    audio: np.ndarray | None = None
    timing: dict = field(default_factory=dict)


class UtteranceDetector:
    """Feed it 16-bit PCM of any chunk size; it returns events as they happen."""

    def __init__(self, stream: VadStream, settings: VadSettings | None = None) -> None:
        self.settings = settings or VadSettings()
        self._stream = stream
        self._pending = np.zeros(0, dtype=np.float32)
        pre_roll = max(1, self.settings.pre_roll_ms // WINDOW_MS)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll)
        self._speech: list[np.ndarray] = []
        self._in_speech = False
        self._confirmed = False
        self._voiced_ms = 0
        self._silence_ms = 0
        self._barge_sent = False
        self.agent_speaking = False
        self.processed_ms = 0
        self.last_probability = 0.0

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def current_audio(self) -> np.ndarray:
        return np.concatenate(self._speech) if self._speech else np.zeros(0, dtype=np.float32)

    def feed(self, pcm: bytes) -> list[VadEvent]:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._pending = np.concatenate([self._pending, samples]) if self._pending.size else samples
        events: list[VadEvent] = []
        while self._pending.size >= WINDOW_SAMPLES:
            window, self._pending = self._pending[:WINDOW_SAMPLES], self._pending[WINDOW_SAMPLES:]
            self.processed_ms += WINDOW_MS
            events.extend(self._step(window))
        return events

    def _step(self, window: np.ndarray) -> list[VadEvent]:
        settings = self.settings
        probability = self._stream.probability(window)
        self.last_probability = probability
        start_bar = settings.speaking_threshold if self.agent_speaking else settings.threshold
        events: list[VadEvent] = []

        if not self._in_speech:
            self._pre_roll.append(window)
            if probability >= start_bar:
                self._in_speech = True
                self._confirmed = False
                self._barge_sent = False
                self._voiced_ms = WINDOW_MS
                self._silence_ms = 0
                self._speech = list(self._pre_roll)
            return events

        self._speech.append(window)
        if probability >= settings.release:
            self._voiced_ms += WINDOW_MS
            self._silence_ms = 0
        else:
            self._silence_ms += WINDOW_MS

        if not self._confirmed and self._voiced_ms >= settings.min_speech_ms:
            self._confirmed = True
            events.append(VadEvent("speech_start"))
        if self.agent_speaking and self._confirmed and not self._barge_sent and self._voiced_ms >= settings.barge_in_ms:
            self._barge_sent = True
            events.append(VadEvent("barge_in"))

        speech_ms = len(self._speech) * WINDOW_MS
        if self._silence_ms >= settings.end_silence_ms or speech_ms >= settings.max_utterance_ms:
            audio = self.current_audio()
            keep = self._confirmed
            forced = self._silence_ms < settings.end_silence_ms
            self._reset_segment()
            if keep:
                events.append(VadEvent("speech_end", audio, {"forced": forced, "speech_ms": speech_ms}))
        return events

    def _reset_segment(self) -> None:
        self._speech = []
        self._in_speech = False
        self._confirmed = False
        self._voiced_ms = 0
        self._silence_ms = 0
        self._pre_roll.clear()

    def reset(self) -> None:
        self._reset_segment()
        self._pending = np.zeros(0, dtype=np.float32)
        self._stream.reset()
