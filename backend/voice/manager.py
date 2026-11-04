"""Admission control and load shedding.

The number of live conversations is capped by what the hardware plan measured, and free memory is
watched. Under pressure optional work goes first (live partial text), then new sessions are refused
with a clear message. Sessions already in progress are never dropped by this class.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import psutil

from backend import metrics

log = logging.getLogger("vap.manager")
GIB = 1024**3


@dataclass(frozen=True)
class Admission:
    allowed: bool
    reason: str = ""
    message: str = ""


class SessionManager:
    def __init__(self, max_sessions: int, min_free_ram_gb: float, stt_queue_limit: int = 8) -> None:
        self.max_sessions = max_sessions
        self.min_free_ram_gb = min_free_ram_gb
        self.stt_queue_limit = stt_queue_limit
        self.active = 0
        self.stt_waiting = 0
        self.tts_waiting = 0

    @staticmethod
    def free_ram_gb() -> float:
        return psutil.virtual_memory().available / GIB

    @property
    def degraded(self) -> bool:
        """True when optional work should be skipped."""
        return self.stt_waiting >= 2 or self.free_ram_gb() < self.min_free_ram_gb * 1.5

    def try_admit(self) -> Admission:
        if self.active >= self.max_sessions:
            metrics.REJECTED.labels("capacity").inc()
            return Admission(False, "capacity", "All our lines are busy. Please try again in a few minutes.")
        if self.free_ram_gb() < self.min_free_ram_gb:
            metrics.REJECTED.labels("memory").inc()
            return Admission(False, "memory", "The server is low on memory. Please try again in a few minutes.")
        if self.stt_waiting >= self.stt_queue_limit:
            metrics.REJECTED.labels("queue").inc()
            return Admission(False, "queue", "The server is busy. Please try again in a few minutes.")
        self.active += 1
        metrics.SESSIONS.set(self.active)
        return Admission(True)

    def release(self) -> None:
        self.active = max(0, self.active - 1)
        metrics.SESSIONS.set(self.active)

    def snapshot(self) -> dict:
        metrics.DEGRADED.set(1 if self.degraded else 0)
        return {
            "active_sessions": self.active,
            "max_sessions": self.max_sessions,
            "stt_waiting": self.stt_waiting,
            "tts_waiting": self.tts_waiting,
            "degraded": self.degraded,
            "free_ram_gb": round(self.free_ram_gb(), 2),
        }
