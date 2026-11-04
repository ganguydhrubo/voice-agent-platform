"""Speak text with any catalogued voice.

Models load once, on first use or at start-up. A Kokoro session is shared by all its voices, and a
Piper model file is shared by its speakers, so offering many voices does not multiply memory.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from voice_engine.tts.kokoro_espeak import KokoroEspeak
from voice_engine.tts.normalise import for_speech
from voice_engine.tts.piper_espeak import PiperEspeak
from voice_engine.tts.voices import Voice

log = logging.getLogger("vap.tts")


class SpeechEngine:
    def __init__(self, models_dir: Path, threads: int = 2) -> None:
        self._dir = models_dir / "tts"
        self._threads = threads
        self._loaded: dict[str, object] = {}
        self._lock = threading.Lock()

    def _engine(self, voice: Voice):
        key = voice.model
        with self._lock:
            engine = self._loaded.get(key)
            if engine is None:
                log.info("Loading voice model %s", key)
                path = self._dir / voice.model
                engine = KokoroEspeak(path, self._threads) if voice.engine == "kokoro" else PiperEspeak(path, self._threads)
                self._loaded[key] = engine
            return engine

    def preload(self, voices: list[Voice]) -> None:
        for voice in voices:
            self.synthesise("Hello.", voice, speak_language=False)

    def synthesise(self, text: str, voice: Voice, speed: float = 1.0, speak_language: bool = True) -> tuple[np.ndarray, int]:
        """Return mono float samples and their rate. Text is normalised for the voice's language."""
        spoken = for_speech(text, voice.language) if speak_language else text
        engine = self._engine(voice)
        if voice.engine == "kokoro":
            audio = engine.generate(spoken, voice.speaker, speed, voice.espeak)
        else:
            audio = engine.generate(spoken, voice.speaker, speed)
        return audio.samples, audio.sample_rate

    @property
    def loaded_models(self) -> list[str]:
        return list(self._loaded)


def to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def trim_silence(samples: np.ndarray, rate: int, threshold: float = 0.004, keep_ms: int = 40) -> np.ndarray:
    """Remove leading silence so that first-audio latency is not spent on nothing."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if not len(loud):
        return samples
    keep = int(rate * keep_ms / 1000)
    return samples[max(int(loud[0]) - keep, 0) : min(int(loud[-1]) + keep * 3, len(samples))]
