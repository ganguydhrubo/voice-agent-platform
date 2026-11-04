"""A real client for a running server: speaks the same WebSocket protocol as the browser."""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass, field

import numpy as np
import websockets

BASE = "http://localhost:8000"


def start_conversation(agent: str, language: str, mode: str = "voice", voice: str = "") -> dict:
    body = json.dumps({"agent": agent, "language": language, "mode": mode, "voice": voice}).encode()
    request = urllib.request.Request(
        f"{BASE}/api/public/conversations",
        data=body,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


@dataclass
class Turn:
    number: int = 0
    heard: str = ""
    reply: list[str] = field(default_factory=list)
    sources: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    outcome: str = ""
    audio_ms: float = 0.0
    first_audio_at: float | None = None
    audio_frames: int = 0

    @property
    def text(self) -> str:
        return " ".join(self.reply)


class Client:
    def __init__(self, conversation: dict, mode: str = "voice") -> None:
        self.conversation = conversation
        self.mode = mode
        self.events: list[dict] = []
        self.turns: dict[int, Turn] = {}
        self.audio_turns: set[int] = set()
        self.socket = None
        self._reader = None
        self.partial: list[str] = []
        self.flushed: list[int] = []

    async def __aenter__(self) -> Client:
        self.socket = await websockets.connect(
            BASE.replace("http", "ws") + "/ws/voice", origin=BASE, max_size=1 << 22
        )
        await self.socket.send(
            json.dumps({"type": "start", "id": self.conversation["id"], "token": self.conversation["token"], "mode": self.mode})
        )
        self._reader = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *_) -> None:
        if self._reader:
            self._reader.cancel()
        await self.socket.close()

    def turn(self, number: int) -> Turn:
        return self.turns.setdefault(number, Turn(number))

    async def _read(self) -> None:
        async for raw in self.socket:
            if isinstance(raw, bytes):
                number = int.from_bytes(raw[:4], "little")
                turn = self.turn(number)
                turn.audio_frames += 1
                if turn.first_audio_at is None:
                    turn.first_audio_at = time.perf_counter()
                continue
            event = json.loads(raw)
            event["_at"] = time.perf_counter()
            self.events.append(event)
            kind = event["type"]
            if kind == "partial":
                self.partial.append(event["text"])
            elif kind == "final":
                self.turn(event["turn"]).heard = event["text"]
            elif kind == "agent_text":
                self.turn(event["turn"]).reply.append(event["text"])
            elif kind == "sources":
                self.turn(event["turn"]).sources = event["sources"]
            elif kind == "flush":
                self.flushed.append(event["turn"])
            elif kind == "turn_end":
                turn = self.turn(event["turn"])
                turn.outcome = event.get("outcome", "")
                turn.timings = event.get("timings", {})
                turn.audio_ms = event.get("audio_ms", 0.0)

    async def wait_for(self, kind: str, count: int = 1, timeout: float = 60, since: int = 0) -> dict:
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            found = [event for event in self.events[since:] if event["type"] == kind]
            if len(found) >= count:
                return found[count - 1]
            await asyncio.sleep(0.02)
        raise TimeoutError(f"{kind} not seen. Last events: {[e['type'] for e in self.events[-12:]]}")

    async def ask_text(self, text: str, timeout: float = 90) -> Turn:
        mark = len(self.events)
        await self.socket.send(json.dumps({"type": "text", "text": text}))
        event = await self.wait_for("turn_end", since=mark, timeout=timeout)
        return self.turn(event["turn"])

    async def send_json(self, payload: dict) -> None:
        await self.socket.send(json.dumps(payload))

    async def speak(self, pcm: np.ndarray, trailing_silence_ms: int = 900, real_time: bool = True) -> None:
        """Send 16 kHz int16 audio in 20 ms frames, at the pace a microphone would."""
        frame = 320
        tail = np.zeros(int(16 * trailing_silence_ms), dtype=np.int16)
        data = np.concatenate([pcm, tail])
        next_at = time.perf_counter()
        for start in range(0, len(data), frame):
            await self.socket.send(data[start : start + frame].tobytes())
            next_at += 0.02
            if real_time:
                delay = next_at - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
