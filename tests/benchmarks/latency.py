"""End-to-end latency through the real voice path, with p50, p95 and p99 per stage.

Audio goes in over the WebSocket at real-time speed and the timer stops when the first audio frame
of the reply arrives. The running server must be idle, or the numbers mean little.

    python tests/benchmarks/latency.py --turns 20                  one caller, 20 turns per language
    python tests/benchmarks/latency.py --turns 8 --concurrent 2    two callers at the same time
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf8")
from tests.live.client import Client, start_conversation  # noqa: E402

DATA = ROOT / "benchmarks" / "data" / "journey"
OUT = ROOT / "benchmarks" / "results"


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * share
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 1),
        "p50": round(percentile(values, 0.5), 1),
        "p95": round(percentile(values, 0.95), 1),
        "p99": round(percentile(values, 0.99), 1),
        "max": round(max(values), 1),
    }


async def caller(language: str, turns: int, rows: list[dict]) -> None:
    conversation = start_conversation("healthcare", language)
    questions = [soundfile.read(DATA / f"{language}_{index}.wav", dtype="int16")[0] for index in (1, 3)]
    async with Client(conversation) as client:
        await client.wait_for("turn_end", timeout=60)
        await client.send_json({"type": "playback", "turn": 1, "played_ms": client.turn(1).audio_ms, "finished": True})
        for number in range(turns):
            audio: np.ndarray = questions[number % len(questions)]
            mark = len(client.events)
            await client.speak(audio, trailing_silence_ms=700)
            end = await client.wait_for("speech_end", since=mark, timeout=30)
            done = await client.wait_for("turn_end", since=mark, timeout=60)
            turn = client.turn(done["turn"])
            first = (turn.first_audio_at - end["_at"]) * 1000 if turn.first_audio_at else None
            await client.send_json({"type": "playback", "turn": done["turn"], "played_ms": turn.audio_ms, "finished": True})
            rows.append({"language": language, "first_audio_ms": first, **turn.timings})
            print(f"{language} {number + 1}/{turns}: {first and round(first)} ms", flush=True)
            await asyncio.sleep(0.3)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--concurrent", type=int, default=1)
    args = parser.parse_args()
    rows: list[dict] = []
    started = time.perf_counter()
    if args.concurrent == 1:
        for language in ("en", "hi", "bn"):
            await caller(language, args.turns, rows)
    else:
        languages = ["en", "hi", "bn"]
        await asyncio.gather(*[caller(languages[index % 3], args.turns, rows) for index in range(args.concurrent)])
    report: dict = {
        "concurrent": args.concurrent,
        "turns": len(rows),
        "seconds": round(time.perf_counter() - started),
        "machine": {"logical_cores": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1)},
        "stages": {},
    }
    stages = ("first_audio_ms", "stt_final_ms", "retrieval_ms", "llm_first_token_ms", "tts_first_audio_ms", "total_ms")
    for language in ("en", "hi", "bn", "all"):
        chosen = [row for row in rows if language in (row["language"], "all")]
        report["stages"][language] = {
            stage: summary([row[stage] for row in chosen if isinstance(row.get(stage), int | float)]) for stage in stages
        }
    name = f"latency_{args.concurrent}_caller.json"
    (OUT / name).write_text(json.dumps(report, indent=1), encoding="utf8")
    print(json.dumps(report["stages"]["all"]["first_audio_ms"]))
    for language in ("en", "hi", "bn"):
        print(language, report["stages"][language].get("first_audio_ms"))


if __name__ == "__main__":
    asyncio.run(main())
