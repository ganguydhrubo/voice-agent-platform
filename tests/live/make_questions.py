"""Spoken test questions as 16 kHz WAV files.

These are machine voices, because no public recording asks these exact questions. They test the
journey end to end. Human speech is covered by the Common Voice clips in voice_check.py.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from voice_engine.tts.engine import SpeechEngine  # noqa: E402
from voice_engine.tts.voices import voice_by_id  # noqa: E402

OUT = ROOT / "benchmarks" / "data" / "journey"
QUESTIONS = {
    "en": ("en-northern", ["Where is the pharmacy?", "What are its timings?", "What are the OPD timings?"]),
    "hi": ("hi-rohan", ["फार्मेसी कहाँ है?", "वह कितने बजे खुलती है?", "ओपीडी का समय क्या है?"]),
    "bn": ("bn-google-b", ["ফার্মেসি কোথায়?", "এটা কখন খোলে?", "ওপিডির সময় কী?"]),
}


def to_16k(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == 16000:
        return samples
    count = int(len(samples) * 16000 / rate)
    return np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    engine = SpeechEngine(ROOT / "models", threads=2)
    for language, (voice_id, lines) in QUESTIONS.items():
        voice = voice_by_id(voice_id)
        for index, line in enumerate(lines, start=1):
            samples, rate = engine.synthesise(line, voice)
            path = OUT / f"{language}_{index}.wav"
            soundfile.write(path, to_16k(samples, rate), 16000, subtype="PCM_16")
            print(path.name, line)


if __name__ == "__main__":
    main()
