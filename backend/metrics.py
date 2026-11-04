"""Prometheus metrics, and the timing record for one conversational turn.

Every stage is measured on the server except `first_audible_ms`, which the browser reports when the
first sample actually plays. Together they give the numbers in docs/13_PERFORMANCE.md.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from prometheus_client import Counter, Gauge, Histogram

BUCKETS_MS = (50, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 4000, 6000, 8000, 12000, 20000)

SESSIONS = Gauge("vap_active_sessions", "Voice sessions connected now")
REJECTED = Counter("vap_sessions_rejected_total", "Sessions refused by admission control", ["reason"])
TURNS = Counter("vap_turns_total", "Finished turns", ["language", "outcome"])
BARGE_INS = Counter("vap_barge_ins_total", "Interruptions by the caller")
ESCALATIONS = Counter("vap_escalations_total", "Escalations raised", ["severity"])
STAGE_MS = Histogram("vap_stage_ms", "Time spent in each pipeline stage", ["stage", "language"], buckets=BUCKETS_MS)
QUEUE_DEPTH = Gauge("vap_queue_depth", "Jobs waiting for a worker", ["pool"])
DEGRADED = Gauge("vap_degraded", "1 when the server has shed optional work")


@dataclass
class TurnTimings:
    """Milliseconds. A stage that did not run stays None."""

    turn: int = 0
    language: str = ""
    speech_ms: float | None = None
    stt_final_ms: float | None = None
    retrieval_ms: float | None = None
    llm_first_token_ms: float | None = None
    tts_first_audio_ms: float | None = None
    first_audio_sent_ms: float | None = None
    first_audible_ms: float | None = None
    total_ms: float | None = None
    outcome: str = ""
    interrupted: bool = False

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def observe(self) -> None:
        for stage in (
            "stt_final_ms",
            "retrieval_ms",
            "llm_first_token_ms",
            "tts_first_audio_ms",
            "first_audio_sent_ms",
            "first_audible_ms",
            "total_ms",
        ):
            value = getattr(self, stage)
            if value is not None:
                STAGE_MS.labels(stage.removesuffix("_ms"), self.language).observe(value)


class Stopwatch:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)
