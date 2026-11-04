"""Kokoro through onnxruntime, with espeak-ng phonemes for any language espeak-ng knows.

sherpa-onnx 2.x runs Kokoro from lexicons only, so it cannot speak Hindi or Bengali. This class
keeps one ONNX session and one voice table, and asks espeak-ng for phonemes.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 24000
MAX_TOKENS = 510
_espeak_lock = threading.Lock()  # espeak-ng keeps global state, so one call at a time


@dataclass
class KokoroAudio:
    samples: np.ndarray
    sample_rate: int = SAMPLE_RATE


def load_tokens(path: Path) -> dict[str, int]:
    table: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        # The space token is written as " 16", so the id is whatever follows the last space.
        symbol, _, number = line.rpartition(" ")
        table[symbol if symbol else " "] = int(number)
    return table


def phonemise(text: str, language: str) -> str:
    import espeakng_loader
    from phonemizer.backend import EspeakBackend
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    with _espeak_lock:
        EspeakWrapper.set_library(espeakng_loader.get_library_path())
        EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
        backend = _backends.get(language)
        if backend is None:
            backend = EspeakBackend(language, preserve_punctuation=True, with_stress=True, language_switch="remove-flags")
            _backends[language] = backend
        return backend.phonemize([text], strip=True)[0]


_backends: dict[str, object] = {}


class KokoroEspeak:
    def __init__(self, model_dir: Path, threads: int = 2) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_dir / "model.int8.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.tokens = load_tokens(model_dir / "tokens.txt")
        table = np.fromfile(model_dir / "voices.bin", dtype=np.float32)
        self.voices = table.reshape(-1, 510, 1, 256)

    def token_ids(self, phonemes: str) -> list[int]:
        return [self.tokens[p] for p in phonemes if p in self.tokens][:MAX_TOKENS]

    def generate(self, text: str, sid: int, speed: float = 1.0, language: str = "en-gb") -> KokoroAudio:
        ids = self.token_ids(phonemise(text, language))
        if not ids:
            return KokoroAudio(np.zeros(0, dtype=np.float32))
        style = self.voices[sid, min(len(ids), 509)]
        output = self.session.run(
            None,
            {
                "tokens": np.array([[0, *ids, 0]], dtype=np.int64),
                "style": style.astype(np.float32),
                "speed": np.array([speed], dtype=np.float32),
            },
        )
        return KokoroAudio(np.asarray(output[0], dtype=np.float32).ravel())
