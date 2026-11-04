"""Offline Zipformer transducer through sherpa-onnx."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voice_engine.stt.base import Transcript


def _first(folder: Path, part: str) -> str:
    return str(sorted(folder.glob(f"{part}*.onnx"))[0])


def tidy(text: str, language: str) -> str:
    """The English model writes in capitals. Sentence case reads better on screen."""
    if language != "en" or text != text.upper():
        return text
    sentence = text.lower().capitalize()
    return f" {sentence} ".replace(" i ", " I ").replace(" i'", " I'").strip()


class OfflineZipformer:
    def __init__(self, folder: Path, language: str, threads: int = 4, tokens: Path | None = None) -> None:
        import sherpa_onnx

        self._language = language
        self._recogniser = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=_first(folder, "encoder"),
            decoder=_first(folder, "decoder"),
            joiner=_first(folder, "joiner"),
            tokens=str(tokens or folder / "tokens.txt"),
            num_threads=threads,
            decoding_method="greedy_search",
        )

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> Transcript:
        started = time.perf_counter()
        stream = self._recogniser.create_stream()
        stream.accept_waveform(16000, audio.astype(np.float32))
        self._recogniser.decode_stream(stream)
        return Transcript(
            tidy(" ".join(stream.result.text.split()), self._language),
            self._language,
            1.0,
            0.0,
            len(audio) / 16.0,
            (time.perf_counter() - started) * 1000,
        )
