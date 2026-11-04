"""Whisper through faster-whisper (CTranslate2). MIT code and MIT weights."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voice_engine.stt.base import Transcript

# Whisper invents these on near-silence. They are never a real caller's sentence.
_HALLUCINATIONS = (
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subtitles by",
    "सब्सक्राइब",
    "धन्यवाद देखने",
)


def clean_transcript(text: str) -> str:
    cleaned = " ".join(text.split())
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in _HALLUCINATIONS):
        return ""
    return cleaned


class WhisperTranscriber:
    def __init__(
        self,
        model_dir: Path,
        threads: int = 4,
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 1,
    ) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            str(model_dir), device=device, compute_type=compute_type, cpu_threads=threads, num_workers=1
        )
        self._beam_size = beam_size

    def transcribe(self, audio: np.ndarray, language: str | None) -> Transcript:
        started = time.perf_counter()
        segments, info = self._model.transcribe(
            audio.astype(np.float32),
            language=language,
            beam_size=self._beam_size,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
        )
        parts = []
        no_speech = 0.0
        for segment in segments:
            parts.append(segment.text)
            no_speech = max(no_speech, segment.no_speech_prob)
        return Transcript(
            clean_transcript("".join(parts)),
            info.language,
            float(info.language_probability),
            float(no_speech),
            len(audio) / 16.0,
            (time.perf_counter() - started) * 1000,
        )


class PeriodicPartial:
    """Rough live text for languages with no streaming model: decode the audio so far, now and then."""

    def __init__(self, transcriber: WhisperTranscriber, language: str | None, every_ms: int = 900) -> None:
        self._transcriber = transcriber
        self._language = language
        self._every = every_ms * 16
        self._buffer: list[np.ndarray] = []
        self._samples = 0
        self._last_decoded = 0
        self._text = ""

    def accept(self, audio: np.ndarray) -> None:
        self._buffer.append(audio)
        self._samples += len(audio)

    def due(self) -> bool:
        return self._samples - self._last_decoded >= self._every

    def decode(self) -> str:
        """Heavy: call it from a worker thread, and skip it when the machine is busy."""
        self._last_decoded = self._samples
        self._text = self._transcriber.transcribe(np.concatenate(self._buffer), self._language).text
        return self._text

    def text(self) -> str:
        return self._text

    def reset(self) -> None:
        self._buffer = []
        self._samples = 0
        self._last_decoded = 0
        self._text = ""
