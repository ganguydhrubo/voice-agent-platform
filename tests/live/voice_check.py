"""The whole voice path against the running server: real audio frames in, real audio frames out.

    python tests/live/voice_check.py journey      asks follow-up questions in each language
    python tests/live/voice_check.py human        sends human Common Voice clips
    python tests/live/voice_check.py barge        interrupts the agent while it speaks
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf8")
from tests.live.client import Client, start_conversation  # noqa: E402

DATA = ROOT / "benchmarks" / "data"


def read(path: Path) -> np.ndarray:
    audio, rate = soundfile.read(path, dtype="int16")
    assert rate == 16000, path
    return audio


async def spoken_turn(client: Client, path: Path) -> dict:
    mark = len(client.events)
    audio = read(path)
    started = time.perf_counter()
    await client.speak(audio)
    end = await client.wait_for("speech_end", since=mark, timeout=30)
    final = await client.wait_for("final", since=mark, timeout=30)
    if not final["text"]:
        return {"turn": client.turn(final["turn"]), "first_audio_ms": None, "sent_s": time.perf_counter() - started}
    done = await client.wait_for("turn_end", since=mark, timeout=60)
    turn = client.turn(done["turn"])
    first = (turn.first_audio_at - end["_at"]) * 1000 if turn.first_audio_at else None
    await client.send_json({"type": "playback", "turn": done["turn"], "played_ms": turn.audio_ms, "finished": True})
    return {
        "turn": turn,
        "first_audio_ms": first,
        "sent_s": time.perf_counter() - started,
    }


async def journey() -> None:
    for language in ("en", "hi", "bn"):
        conversation = start_conversation("healthcare", language)
        async with Client(conversation) as client:
            await client.wait_for("turn_end", timeout=40)
            greet = client.turn(1)
            print(f"\n== {language}: greeting {greet.text!r}, audio frames {greet.audio_frames}")
            await client.send_json({"type": "playback", "turn": 1, "played_ms": greet.audio_ms, "finished": True})
            for index in (1, 2, 3):
                result = await spoken_turn(client, DATA / "journey" / f"{language}_{index}.wav")
                turn = result["turn"]
                print(f"  heard : {turn.heard}")
                print(f"  reply : {turn.text}")
                print(f"  first audio {result['first_audio_ms']:.0f} ms after speech end, frames {turn.audio_frames}, {turn.outcome}, {turn.timings}")


async def human() -> None:
    labels = {}
    for language in ("en", "hi", "bn"):
        for line in (DATA / language / "manifest.jsonl").read_text(encoding="utf8").splitlines():
            row = json.loads(line)
            labels[row["audio"].removesuffix(".wav")] = row["text"]
    for language in ("en", "hi", "bn"):
        files = sorted((DATA / language).glob("*.wav"))[:3]
        conversation = start_conversation("healthcare", language)
        async with Client(conversation) as client:
            await client.wait_for("turn_end", timeout=40)
            await client.send_json({"type": "playback", "turn": 1, "played_ms": client.turn(1).audio_ms, "finished": True})
            for path in files:
                result = await spoken_turn(client, path)
                turn = result["turn"]
                print(f"[{language}] {path.name}\n  said : {labels.get(path.stem, '?')}\n  heard: {turn.heard}\n  reply: {turn.text[:100]}\n  {result['first_audio_ms']} ms {turn.outcome}")


async def barge() -> None:
    conversation = start_conversation("healthcare", "en")
    async with Client(conversation) as client:
        await client.wait_for("turn_end", timeout=40)
        await client.send_json({"type": "playback", "turn": 1, "played_ms": client.turn(1).audio_ms, "finished": True})
        audio = read(DATA / "journey" / "en_3.wav")
        mark = len(client.events)
        await client.speak(audio)
        start = await client.wait_for("agent_start", since=mark, timeout=30)
        answering = start["turn"]
        print(f"agent speaking on turn {answering}")
        await asyncio.sleep(0.3)
        await client.send_json({"type": "playback", "turn": answering, "played_ms": 300})
        mark = len(client.events)
        began = time.perf_counter()
        # A louder interruption over the agent's own speech, as a caller would talk over it.
        loud = np.clip(read(DATA / "journey" / "en_1.wav").astype(np.int32) * 2, -32768, 32767).astype(np.int16)
        frames_before = client.turn(answering).audio_frames
        await client.speak(loud)
        flush = await client.wait_for("flush", since=mark, timeout=10)
        print(f"flushed turn {flush['turn']} reason {flush['reason']} {(flush['_at'] - began) * 1000:.0f} ms after talking began")
        done = await client.wait_for("turn_end", since=mark, timeout=40)
        turn = client.turn(done["turn"])
        print(f"old turn frames {frames_before} -> {client.turn(answering).audio_frames}")
        print(f"new turn heard: {turn.heard}\nreply: {turn.text}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "journey"
    asyncio.run({"journey": journey, "human": human, "barge": barge}[what]())
