"""AI4Bharat IndicConformer through onnx-asr. MIT code and MIT weights.

Whisper small and base read Hindi and Bengali poorly on real recordings (see docs/13_PERFORMANCE.md),
and these language-specific models do far better. Decode time grows with the length of the audio.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voice_engine.stt.base import Transcript

PAD_SAMPLES = 4800  # 300 ms at 16 kHz


class ConformerTranscriber:
    def __init__(self, model_dir: Path, language: str, threads: int = 4) -> None:
        import onnx_asr
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._language = language
        self._model = onnx_asr.load_model(
            "nemo-conformer-ctc",
            str(model_dir),
            quantization="int8",
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> Transcript:
        started = time.perf_counter()
        # Measured on 40 human Hindi clips: detector-cut audio gives 31.5% word errors with no padding
        # and 9.8% with 300 ms. This model needs silence around the speech.
        padded = np.pad(audio.astype(np.float32), PAD_SAMPLES)
        text = self._model.recognize(padded, sample_rate=16000)
        return Transcript(
            " ".join(str(text).split()),
            self._language,
            1.0,
            0.0,
            len(audio) / 16.0,
            (time.perf_counter() - started) * 1000,
        )
