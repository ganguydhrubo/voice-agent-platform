"""Streaming Zipformer through sherpa-onnx, for true word-by-word partial text."""
from __future__ import annotations

from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


def _find(folder: Path, pattern: str) -> str:
    matches = sorted(folder.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"{pattern} not found in {folder}")
    return str(matches[0])


class ZipformerModel:
    def __init__(self, folder: Path, threads: int = 2) -> None:
        import sherpa_onnx

        encoder = sorted(folder.glob("encoder*int8*.onnx")) or sorted(folder.glob("encoder*.onnx"))
        joiner = sorted(folder.glob("joiner*int8*.onnx")) or sorted(folder.glob("joiner*.onnx"))
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(folder / "tokens.txt"),
            encoder=str(encoder[0]),
            decoder=_find(folder, "decoder*.onnx"),
            joiner=str(joiner[0]),
            num_threads=threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
        )

    def stream(self) -> ZipformerPartial:
        return ZipformerPartial(self._recognizer)


class CtcStreamingModel:
    """Streaming Zipformer2 CTC, a single ONNX file with no decoder or joiner."""

    def __init__(self, folder: Path, threads: int = 2) -> None:
        import sherpa_onnx

        self._recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
            tokens=str(folder / "tokens.txt"),
            model=str(folder / "encoder.int8.onnx"),
            num_threads=threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
        )

    def stream(self) -> ZipformerPartial:
        return ZipformerPartial(self._recognizer)


class ZipformerPartial:
    def __init__(self, recognizer) -> None:
        self._recognizer = recognizer
        self._stream = recognizer.create_stream()

    def accept(self, audio: np.ndarray) -> None:
        self._stream.accept_waveform(SAMPLE_RATE, audio)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

    def text(self) -> str:
        return self._recognizer.get_result(self._stream).strip()

    def reset(self) -> None:
        self._recognizer.reset(self._stream)


class StreamingFinal:
    """Feed a whole utterance through the streaming model, for measuring its accuracy."""

    def __init__(self, folder: Path, language: str, threads: int = 2) -> None:
        self._model = CtcStreamingModel(folder, threads) if language == "hi" else ZipformerModel(folder, threads)
        self._language = language

    def transcribe(self, audio: np.ndarray, language: str | None = None):
        import time

        from voice_engine.stt.base import Transcript

        started = time.perf_counter()
        partial = self._model.stream()
        partial.accept(audio.astype(np.float32))
        partial.accept(np.zeros(int(SAMPLE_RATE * 0.5), dtype=np.float32))
        return Transcript(
            partial.text().lower(), self._language, 1.0, 0.0, len(audio) / 16.0, (time.perf_counter() - started) * 1000
        )
