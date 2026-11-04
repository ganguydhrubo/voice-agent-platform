"""Speech-to-text interfaces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    language_confidence: float
    no_speech: float
    audio_ms: float
    decode_ms: float


class FinalTranscriber(Protocol):
    """Accurate text for a finished utterance."""

    def transcribe(self, audio: np.ndarray, language: str | None) -> Transcript: ...


class PartialStream(Protocol):
    """Rough text that grows while the caller is still speaking."""

    def accept(self, audio: np.ndarray) -> None: ...

    def text(self) -> str: ...

    def reset(self) -> None: ...
