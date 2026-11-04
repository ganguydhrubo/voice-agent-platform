"""Compare all 16 speakers of the Bengali Piper voice.

The recogniser the live agent uses for Bengali does the listening, so a low error here means the
words came out clearly enough for a machine. It says nothing about how pleasant a voice sounds.
Run from the project folder: python benchmarks/bn_speaker_scan.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import jiwer
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf8")

from benchmarks.tts_candidates import SENTENCES, plain, resample_16k
from voice_engine.stt.transducer import OfflineZipformer
from voice_engine.tts.piper_espeak import PiperEspeak

MODEL = ROOT / "models/tts/piper/bn/bn_BD/google/medium/bn_BD-google-medium.onnx"
EXTRA = [
    "আউটডোর সোমবার থেকে শনিবার সকাল নয়টা থেকে বিকেল পাঁচটা পর্যন্ত খোলা থাকে।",
    "জরুরি বিভাগ চব্বিশ ঘণ্টা খোলা থাকে।",
    "অ্যাপয়েন্টমেন্টের জন্য অভ্যর্থনায় যোগাযোগ করুন।",
]


def main() -> None:
    speakers = json.loads(MODEL.with_suffix(".onnx.json").read_text(encoding="utf8"))["num_speakers"]
    voice = PiperEspeak(MODEL, 2)
    folder = ROOT / "models/stt/bangla-zipformer"
    judge = OfflineZipformer(folder / "int8", "bn", threads=4, tokens=folder / "tokens.txt")
    sentences = [*SENTENCES["bn"], *EXTRA]
    results = []
    for speaker in range(speakers):
        cers, rtfs = [], []
        for sentence in sentences:
            started = time.perf_counter()
            audio = voice.generate(sentence, sid=speaker, speed=1.0)
            took = time.perf_counter() - started
            samples = np.array(audio.samples, dtype=np.float32)
            rtfs.append(took / (len(samples) / audio.sample_rate))
            heard = judge.transcribe(resample_16k(samples, audio.sample_rate), "bn").text
            cers.append(jiwer.cer(plain(sentence), plain(heard) or "x"))
        row = {"speaker": speaker, "cer": round(float(np.mean(cers)), 3), "worst": round(float(np.max(cers)), 3), "rtf": round(float(np.mean(rtfs)), 3)}
        results.append(row)
        print(row, flush=True)
    results.sort(key=lambda row: row["cer"])
    out = ROOT / "benchmarks/results/bn_speaker_scan.json"
    out.write_text(json.dumps({"sentences": len(sentences), "judge": "bangla-zipformer", "results": results}, indent=1), encoding="utf8")
    print("best", results[:4])


if __name__ == "__main__":
    main()
