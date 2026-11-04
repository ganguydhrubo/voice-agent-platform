"""Build the speech test set from real human recordings.

Source: Mozilla Common Voice 17.0 test split (CC0), through the open mirror on Hugging Face.
Keeps well-voted clips only, converts them to 16 kHz mono WAV and writes a manifest for each
language. Clips stay out of Git; run this script again to rebuild the same set.

    python benchmarks/fetch_eval_audio.py --per-language 40
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
BASE = "https://huggingface.co/datasets/fsicoli/common_voice_17_0/resolve/main"
SHARDS = {"hi": "hi_test_0.tar", "bn": "bn_test_0.tar", "en": "en_test_0.tar"}


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "voice-agent-platform"})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:
        while block := response.read(1 << 20):
            out.write(block)


def best_clips(tsv: Path, count: int) -> dict[str, dict]:
    with tsv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))
    good = [row for row in rows if int(row["up_votes"] or 0) >= 2 and int(row["down_votes"] or 0) == 0]
    good.sort(key=lambda row: (-int(row["up_votes"]), row["path"]))
    return {row["path"]: row for row in good[: count * 3]}


def build(language: str, count: int) -> None:
    out_dir = DATA / language
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    with tempfile.TemporaryDirectory() as tmp:
        tsv = Path(tmp) / "test.tsv"
        download(f"{BASE}/transcript/{language}/test.tsv", tsv)
        wanted = best_clips(tsv, count)
        tar_path = Path(tmp) / SHARDS[language]
        download(f"{BASE}/audio/{language}/test/{SHARDS[language]}", tar_path)
        kept = []
        with tarfile.open(tar_path) as tar:
            for member in tar:
                name = Path(member.name).name
                row = wanted.get(name)
                if not row or not member.isfile():
                    continue
                source = Path(tmp) / name
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                source.write_bytes(handle.read())
                wav = out_dir / f"{Path(name).stem}.wav"
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-ac", "1", "-ar", "16000", str(wav)],
                    check=True,
                )
                kept.append({"audio": wav.name, "text": row["sentence"].strip(), "language": language})
                if len(kept) >= count:
                    break
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept), encoding="utf-8")
    print(f"{language}: {len(kept)} clips -> {manifest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-language", type=int, default=40)
    parser.add_argument("--languages", nargs="*", default=list(SHARDS))
    args = parser.parse_args()
    for language in args.languages:
        build(language, args.per_language)


if __name__ == "__main__":
    main()
