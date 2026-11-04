"""Compare text-to-speech candidates on this machine: speed, memory and whether words survive.

Intelligibility is measured by a round trip: speak a sentence, transcribe it with Whisper, and
score the text against what was said. This is a machine check. It does not replace a person
listening, and the report says so.

    python benchmarks/tts_candidates.py --threads 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SENTENCES = {
    "en": [
        "Visiting hours are from four to seven in the evening every day.",
        "Please bring a photo identity card and any earlier medical reports.",
        "The pharmacy is on the ground floor near the main entrance.",
        "Hello, how can I help you today?",
    ],
    "hi": [
        "मरीज़ों से मिलने का समय हर दिन शाम चार बजे से सात बजे तक है।",
        "अपना फोटो पहचान पत्र और पुरानी मेडिकल रिपोर्ट साथ लाएँ।",
        "फार्मेसी मुख्य द्वार के पास भूतल पर है।",
        "नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ?",
    ],
    "bn": [
        "রোগী দেখার সময় প্রতিদিন বিকেল চারটা থেকে সন্ধ্যা সাতটা পর্যন্ত।",
        "আপনার ফটো পরিচয়পত্র এবং পুরোনো মেডিকেল রিপোর্ট সঙ্গে আনুন।",
        "ফার্মেসি মূল প্রবেশপথের কাছে একতলায় আছে।",
        "নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    ],
}


def kokoro(lang: str, threads: int):
    import sherpa_onnx

    folder = ROOT / "models/tts/kokoro-int8-multi-lang-v1_0"
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(folder / "model.int8.onnx"),
                voices=str(folder / "voices.bin"),
                tokens=str(folder / "tokens.txt"),
                lexicon=f"{folder / 'lexicon-gb-en.txt'},{folder / 'lexicon-us-en.txt'}" if lang.startswith("en") else "",
                data_dir=str(folder / "espeak-ng-data"),
                lang=lang,
            ),
            num_threads=threads,
        ),
        max_num_sentences=1,
    )
    return sherpa_onnx.OfflineTts(config)


class EspeakKokoro:
    """Same call shape as sherpa's engine, so the loop below treats every candidate alike."""

    def __init__(self, language: str, threads: int) -> None:
        from voice_engine.tts.kokoro_espeak import KokoroEspeak

        self.engine = KokoroEspeak(ROOT / "models/tts/kokoro-int8-multi-lang-v1_0", threads)
        self.language = language

    def generate(self, text: str, sid: int, speed: float = 1.0):
        return self.engine.generate(text, sid, speed, self.language)


def vits(model: Path, tokens: Path, data_dir: Path, threads: int, lexicon: Path | None = None):
    import sherpa_onnx

    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model),
                tokens=str(tokens),
                data_dir=str(data_dir) if str(data_dir) != "." else "",
                lexicon=str(lexicon) if lexicon else "",
            ),
            num_threads=threads,
        ),
        max_num_sentences=1,
    )
    return sherpa_onnx.OfflineTts(config)


def piper(relative: str, threads: int):
    from voice_engine.tts.piper_espeak import PiperEspeak

    return PiperEspeak(ROOT / "models/tts/piper" / relative, threads)


def candidates(threads: int) -> list[dict]:
    coqui = ROOT / "models/tts/vits-coqui-bn-custom_female"
    return [
        {"name": "piper-en-cori", "language": "en", "load": lambda: piper("en/en_GB/cori/medium/en_GB-cori-medium.onnx", threads), "sid": 0},
        {"name": "piper-en-alba", "language": "en", "load": lambda: piper("en/en_GB/alba/medium/en_GB-alba-medium.onnx", threads), "sid": 0},
        {"name": "piper-en-northern-male", "language": "en", "load": lambda: piper("en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx", threads), "sid": 0},
        {"name": "kokoro-espeak-en-bf_emma", "language": "en", "load": lambda: EspeakKokoro("en-gb", threads), "sid": 21},
        {"name": "kokoro-espeak-hi-hf_alpha", "language": "hi", "load": lambda: EspeakKokoro("hi", threads), "sid": 31},
        {"name": "kokoro-espeak-hi-hf_beta", "language": "hi", "load": lambda: EspeakKokoro("hi", threads), "sid": 32},
        {"name": "kokoro-espeak-hi-hm_omega", "language": "hi", "load": lambda: EspeakKokoro("hi", threads), "sid": 33},
        {"name": "piper-hi-rohan", "language": "hi", "load": lambda: piper("hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx", threads), "sid": 0},
        {"name": "kokoro-espeak-bn-hf_alpha", "language": "bn", "load": lambda: EspeakKokoro("bn", threads), "sid": 31},
        {"name": "piper-bn-google-s0", "language": "bn", "load": lambda: piper("bn/bn_BD/google/medium/bn_BD-google-medium.onnx", threads), "sid": 0},
        {"name": "piper-bn-google-s4", "language": "bn", "load": lambda: piper("bn/bn_BD/google/medium/bn_BD-google-medium.onnx", threads), "sid": 4},
        {"name": "piper-bn-google-s15", "language": "bn", "load": lambda: piper("bn/bn_BD/google/medium/bn_BD-google-medium.onnx", threads), "sid": 15},
        {"name": "coqui-bn-female", "language": "bn", "load": lambda: vits(coqui / "model.onnx", coqui / "tokens.txt", Path(""), threads), "sid": 0, "needs": coqui / "model.onnx"},
    ]


def plain(text: str) -> str:
    """Compare words, not punctuation or capital letters."""
    kept = [c if c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M") else " " for c in text.lower()]
    return " ".join("".join(kept).split())


def resample_16k(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == 16000:
        return samples
    positions = np.linspace(0, len(samples) - 1, int(len(samples) * 16000 / rate))
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    import jiwer
    import soundfile

    from voice_engine.stt.conformer import ConformerTranscriber
    from voice_engine.stt.whisper import WhisperTranscriber

    judges: dict[str, object] = {}

    def judge(language: str):
        """The best measured recogniser for each language does the listening."""
        if language not in judges:
            judges[language] = (
                WhisperTranscriber(ROOT / "models/stt/faster-whisper-small", threads=4)
                if language == "en"
                else ConformerTranscriber(ROOT / f"models/stt/indicconformer-{language}", language, threads=4)
            )
        return judges[language]

    out_dir = ROOT / "benchmarks/results/tts_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    process = psutil.Process(os.getpid())
    results = []
    for candidate in candidates(args.threads):
        if args.only and args.only not in candidate["name"]:
            continue
        needs = candidate.get("needs")
        if needs is not None and not Path(needs).exists():
            print("skip (missing)", candidate["name"])
            continue
        before = process.memory_info().rss
        try:
            started = time.perf_counter()
            engine = candidate["load"]()
            load_s = time.perf_counter() - started
        except Exception as error:  # a candidate that will not load is itself a result
            print("FAILED", candidate["name"], error)
            results.append({"name": candidate["name"], "error": str(error)[:200]})
            continue
        language = candidate["language"]
        rtfs, first_ms, cers, heard = [], [], [], []
        for index, sentence in enumerate(SENTENCES[language]):
            started = time.perf_counter()
            try:
                audio = engine.generate(sentence, sid=candidate["sid"], speed=1.0)
            except Exception as error:
                print("FAILED", candidate["name"], str(error)[:200])
                continue
            took = time.perf_counter() - started
            samples = np.array(audio.samples, dtype=np.float32)
            if not len(samples):
                print("NO AUDIO", candidate["name"])
                continue
            seconds = len(samples) / audio.sample_rate if len(samples) else 0
            rtfs.append(took / seconds if seconds else 99)
            first_ms.append(took * 1000)
            soundfile.write(out_dir / f"{candidate['name']}_{index}.wav", samples, audio.sample_rate)
            if len(samples):
                text = judge(language).transcribe(resample_16k(samples, audio.sample_rate), language).text
                heard.append(text)
                cers.append(jiwer.cer(plain(sentence), plain(text) or " "))
        row = {
            "name": candidate["name"],
            "language": language,
            "load_s": round(load_s, 2),
            "rss_mb": round((process.memory_info().rss - before) / 1048576),
            "rtf_mean": round(float(np.mean(rtfs)), 3),
            "sentence_ms_mean": round(float(np.mean(first_ms))) if first_ms else None,
            "roundtrip_cer": round(float(np.mean(cers)), 3) if cers else None,
            "heard": heard[:2],
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        del engine
    target = ROOT / "benchmarks/results/tts_candidates.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    names = {row["name"] for row in results}
    results = [row for row in previous if row["name"] not in names] + results
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
