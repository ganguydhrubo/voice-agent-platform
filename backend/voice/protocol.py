"""The voice WebSocket's wire format.

Binary frames from the browser are raw 16-bit, 16 kHz mono PCM.
Binary frames from the server are a 12-byte header followed by 16-bit mono PCM at the stated rate:

    uint32 turn    the turn this audio belongs to, so stale audio can be recognised
    uint32 index   the chunk's position in the turn
    uint32 rate    samples per second

All other messages are JSON text with a `type` field.
"""
from __future__ import annotations

import struct

HEADER = struct.Struct("<III")
CHUNK_MS = 200  # short chunks mean a barge-in has little audio left to flush
MAX_AUDIO_FRAME_BYTES = 64_000  # about 2 seconds; anything larger is not a microphone
MAX_TEXT_FRAME_BYTES = 4_000


def audio_frame(turn: int, index: int, rate: int, pcm: bytes) -> bytes:
    return HEADER.pack(turn, index, rate) + pcm


def split_pcm(pcm: bytes, rate: int) -> list[bytes]:
    size = int(rate * CHUNK_MS / 1000) * 2
    return [pcm[start : start + size] for start in range(0, len(pcm), size)]
