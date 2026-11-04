"""Piper voices through onnxruntime, with espeak-ng phonemes.

sherpa-onnx 2.x has no espeak front end for VITS models, so a Piper voice is run directly: the
phoneme table and the scales come from the voice's own .onnx.json file.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voice_engine.tts.kokoro_espeak import phonemise


@dataclass
class PiperAudio:
    samples: np.ndarray
    sample_rate: int


class PiperEspeak:
    def __init__(self, model_path: Path, threads: int = 2) -> None:
        import onnxruntime as ort

        self.config = json.loads(model_path.with_suffix(".onnx.json").read_text(encoding="utf-8"))
        self.table: dict[str, list[int]] = self.config["phoneme_id_map"]
        self.rate = int(self.config["audio"]["sample_rate"])
        # phonemizer asks for a regional name where the voice file says plain "en".
        self.voice = {"en": "en-gb"}.get(self.config["espeak"]["voice"], self.config["espeak"]["voice"])
        inference = self.config.get("inference", {})
        self.noise = float(inference.get("noise_scale", 0.667))
        self.length = float(inference.get("length_scale", 1.0))
        self.noise_w = float(inference.get("noise_w", 0.8))
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def phoneme_ids(self, phonemes: str) -> list[int]:
        ids = list(self.table["^"]) + list(self.table["_"])
        for symbol in unicodedata.normalize("NFD", phonemes):
            found = self.table.get(symbol)
            if found:
                ids.extend(found)
                ids.extend(self.table["_"])
        ids.extend(self.table["$"])
        return ids

    def generate(self, text: str, sid: int = 0, speed: float = 1.0) -> PiperAudio:
        ids = self.phoneme_ids(phonemise(text, self.voice))
        inputs = {
            "input": np.array([ids], dtype=np.int64),
            "input_lengths": np.array([len(ids)], dtype=np.int64),
            "scales": np.array([self.noise, self.length / speed, self.noise_w], dtype=np.float32),
        }
        if "sid" in self.input_names:
            inputs["sid"] = np.array([sid], dtype=np.int64)
        audio = self.session.run(None, inputs)[0]
        return PiperAudio(np.asarray(audio, dtype=np.float32).ravel(), self.rate)
