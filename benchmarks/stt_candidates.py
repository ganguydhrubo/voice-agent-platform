"""Word and character error rates for speech-to-text candidates on real human recordings.

The clips are Common Voice 17.0 test recordings (CC0), fetched by fetch_eval_audio.py.

    python benchmarks/stt_candidates.py --models faster-whisper-base faster-whisper-small
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def plain(text: str) -> str:
    kept = [c if c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M") else " " for c in text.lower()]
    return " ".join("".join(kept).split())


def script_share(text: str, language: str) -> float:
    """How much of the text is in the script the language is written in."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    ranges = {"hi": (0x0900, 0x097F), "bn": (0x0980, 0x09FF), "en": (0x0041, 0x024F)}
    low, high = ranges[language]
    return sum(low <= ord(c) <= high for c in letters) / len(letters)


def load_clips(language: str, limit: int) -> list[dict]:
    folder = ROOT / "benchmarks/data" / language
    rows = [json.loads(line) for line in (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return rows[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["faster-whisper-base", "faster-whisper-small"])
    parser.add_argument("--languages", nargs="+", default=["en", "hi", "bn"])
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--beam", type=int, default=1)
    args = parser.parse_args()

    import jiwer
    import soundfile

    from voice_engine.stt.whisper import WhisperTranscriber

    process = psutil.Process(os.getpid())
    results = []
    for name in args.models:
        before = process.memory_info().rss
        languages = args.languages
        if name.startswith("indicconformer"):
            from voice_engine.stt.conformer import ConformerTranscriber

            languages = [name.rsplit("-", 1)[1]]
            model = ConformerTranscriber(ROOT / "models/stt" / name, languages[0], threads=args.threads)
        elif name.startswith("sherpa-onnx-streaming-zipformer") or name == "zipformer-en-streaming-large":
            from voice_engine.stt.zipformer import StreamingFinal

            languages = ["en"]
            model = StreamingFinal(ROOT / "models/stt" / name, "en", threads=args.threads)
        elif name == "hindi-streaming-ctc":
            from voice_engine.stt.zipformer import StreamingFinal

            languages = ["hi"]
            model = StreamingFinal(ROOT / "models/stt" / name, "hi", threads=args.threads)
        elif name == "zipformer-en-offline":
            from voice_engine.stt.transducer import OfflineZipformer

            languages = ["en"]
            model = OfflineZipformer(ROOT / "models/stt" / name, "en", threads=args.threads)
        elif name == "bangla-zipformer":
            from voice_engine.stt.transducer import OfflineZipformer

            languages = ["bn"]
            folder = ROOT / "models/stt/bangla-zipformer"
            model = OfflineZipformer(folder / "int8", "bn", threads=args.threads, tokens=folder / "tokens.txt")
        else:
            model = WhisperTranscriber(ROOT / "models/stt" / name, threads=args.threads, beam_size=args.beam)
        for language in languages:
            references, hypotheses, decode_ms, audio_ms, script = [], [], [], [], []
            for clip in load_clips(language, args.limit):
                path = Path(clip["audio"])
                path = path if path.is_absolute() else ROOT / "benchmarks/data" / language / path.name
                audio, rate = soundfile.read(path, dtype="float32")
                assert rate == 16000
                out = model.transcribe(audio, language)
                references.append(plain(clip["text"]))
                hypotheses.append(plain(out.text) or " ")
                decode_ms.append(out.decode_ms)
                audio_ms.append(out.audio_ms)
                script.append(script_share(out.text, language))
            row = {
                "model": name,
                "language": language,
                "clips": len(references),
                "wer": round(jiwer.wer(references, hypotheses), 3),
                "cer": round(jiwer.cer(references, hypotheses), 3),
                "rtf": round(sum(decode_ms) / sum(audio_ms), 3),
                "decode_p50_ms": round(float(np.percentile(decode_ms, 50))),
                "decode_p95_ms": round(float(np.percentile(decode_ms, 95))),
                "right_script": round(float(np.mean(script)), 3),
                "rss_mb": round((process.memory_info().rss - before) / 1048576),
                "beam": args.beam,
                "threads": args.threads,
                "sample": list(zip(references[:2], hypotheses[:2])),
            }
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        del model
    target = ROOT / "benchmarks/results/stt_candidates.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    target.write_text(json.dumps(previous + results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
