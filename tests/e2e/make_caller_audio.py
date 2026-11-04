"""One WAV per language that plays the caller's side of a conversation into a fake microphone."""
import sys
from pathlib import Path

import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks" / "data" / "journey"
OUT = ROOT / "benchmarks" / "data" / "journey"
GREETING_SECONDS = {"en": 7.0, "hi": 9.0, "bn": 10.0}
REPLY_SECONDS = {"en": 8.0, "hi": 9.0, "bn": 10.0}


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.int16)


def clip(language: str, index: int, gain: float = 1.0) -> np.ndarray:
    audio, _ = soundfile.read(SOURCE / f"{language}_{index}.wav", dtype="int16")
    return np.clip(audio.astype(np.int32) * gain, -32768, 32767).astype(np.int16)


for language in ("en", "hi", "bn"):
    reply = REPLY_SECONDS[language]
    parts = [
        silence(GREETING_SECONDS[language]),
        clip(language, 1),  # where is the pharmacy
        silence(reply),
        clip(language, 2),  # a follow-up that needs the last turn
        silence(reply),
        clip(language, 3),  # OPD timings
        silence(3.4),  # the agent is now speaking
        clip(language, 1, 1.5),  # the caller talks over it
        silence(reply),
    ]
    audio = np.concatenate(parts)
    soundfile.write(OUT / f"caller_{language}.wav", audio, 16000, subtype="PCM_16")
    print(language, round(len(audio) / 16000, 1), "seconds", file=sys.stderr)
