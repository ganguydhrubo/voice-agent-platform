"""Word error rate through the live path: voice detector first, then the recogniser.

The clips are the same human Common Voice recordings as stt_candidates.py. The difference from that
benchmark is that here each clip is cut by the detector exactly as a live conversation would be,
so this shows what a caller gets, including any damage done by cutting at the wrong moment.

    python benchmarks/live_path_stt.py --end-silence 450 700 --limit 40
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jiwer
import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.stdout.reconfigure(encoding="utf8")

from stt_candidates import load_clips, plain  # noqa: E402

from voice_engine.vad.silero import SileroModel, UtteranceDetector, VadSettings, VadStream  # noqa: E402

MODELS = {"en": "zipformer-en-offline", "hi": "indicconformer-hi", "bn": "bangla-zipformer"}


def recogniser(language: str, threads: int):
    folder = ROOT / "models" / "stt" / MODELS[language]
    if language == "hi":
        from voice_engine.stt.conformer import ConformerTranscriber

        return ConformerTranscriber(folder, language, threads=threads)
    from voice_engine.stt.transducer import OfflineZipformer

    inner = folder / "int8" if (folder / "int8").exists() else folder
    return OfflineZipformer(inner, language, threads=threads, tokens=folder / "tokens.txt")


def segments(detector: UtteranceDetector, audio: np.ndarray) -> list[np.ndarray]:
    found = []
    tail = np.zeros(16 * 1500, dtype=np.int16)
    data = np.concatenate([audio, tail])
    for start in range(0, len(data), 320):
        for event in detector.feed(data[start : start + 320].tobytes()):
            if event.kind == "speech_end":
                found.append(event.audio)
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-silence", type=int, nargs="+", default=[450])
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--languages", nargs="+", default=["en", "hi", "bn"])
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    vad = SileroModel(ROOT / "models" / "vad" / "silero_vad.onnx")
    rows = []
    for language in args.languages:
        model = recogniser(language, args.threads)
        clips = load_clips(language, args.limit)
        audios = []
        for clip in clips:
            audio, rate = soundfile.read(ROOT / "benchmarks" / "data" / language / clip["audio"], dtype="int16")
            assert rate == 16000
            audios.append(audio)
        references = [plain(clip["text"]) for clip in clips]

        whole = [plain(model.transcribe(audio.astype(np.float32) / 32768.0, language).text) for audio in audios]
        baseline = jiwer.wer(references, whole)
        print(f"{language}: whole clip, no detector WER {baseline:.3f}", flush=True)
        for silence in args.end_silence:
            settings = VadSettings(threshold=args.threshold, end_silence_ms=silence)
            texts, pieces = [], []
            for audio in audios:
                parts = segments(UtteranceDetector(VadStream(vad), settings), audio)
                pieces.append(len(parts))
                texts.append(plain(" ".join(model.transcribe(part, language).text for part in parts)))
            pairs = [(reference, text) for reference, text in zip(references, texts, strict=True)]
            wer = jiwer.wer([pair[0] for pair in pairs], [pair[1] or " " for pair in pairs])
            first_only = sum(1 for count in pieces if count > 1)
            print(f"   end silence {silence} ms: WER {wer:.3f}, clips cut in two or more {first_only}/{len(clips)}, none found {pieces.count(0)}", flush=True)
            rows.append({"language": language, "end_silence_ms": silence, "wer": round(wer, 3), "whole_clip_wer": round(baseline, 3), "split_clips": first_only, "clips": len(clips)})
    out = ROOT / "benchmarks" / "results" / "live_path_stt.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
