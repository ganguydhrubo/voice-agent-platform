"""The voices the product offers. A voice is listed here only after it has been measured.

Two engines are used because each wins somewhere on this class of machine: Piper starts speaking in
a fraction of a second, and Kokoro sounds more natural and is more intelligible in Hindi. The
measurements behind each entry are in docs/13_PERFORMANCE.md and benchmarks/results/.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Voice:
    id: str
    language: str  # en, hi or bn
    label: str
    engine: str  # piper or kokoro
    model: str  # relative to models/tts
    speaker: int = 0
    espeak: str = ""  # Kokoro only: the espeak-ng language
    gender: str = "female"
    licence: str = ""


KOKORO = "kokoro-int8-multi-lang-v1_0"

VOICES: tuple[Voice, ...] = (
    Voice("en-alba", "en", "Alba (fast)", "piper", "piper/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
          licence="CC BY 4.0"),
    Voice("en-northern", "en", "Northern (fast)", "piper",
          "piper/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx",
          gender="male", licence="CC BY-SA 4.0"),
    Voice("en-emma", "en", "Emma (natural)", "kokoro", KOKORO, speaker=21, espeak="en-gb", licence="Apache-2.0"),
    Voice("hi-rohan", "hi", "Rohan (fast)", "piper", "piper/hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx",
          gender="male", licence="IITM IndicTTS"),
    Voice("hi-omega", "hi", "Omega (natural)", "kokoro", KOKORO, speaker=33, espeak="hi",
          gender="male", licence="Apache-2.0"),
    Voice("hi-alpha", "hi", "Alpha (natural)", "kokoro", KOKORO, speaker=31, espeak="hi", licence="Apache-2.0"),
    Voice("bn-google-a", "bn", "Bangla A (fast)", "piper", "piper/bn/bn_BD/google/medium/bn_BD-google-medium.onnx",
          speaker=14, licence="CC BY-SA 4.0"),
    Voice("bn-google-b", "bn", "Bangla B (fast)", "piper", "piper/bn/bn_BD/google/medium/bn_BD-google-medium.onnx",
          speaker=13, licence="CC BY-SA 4.0"),
)


def voice_by_id(voice_id: str) -> Voice | None:
    return next((voice for voice in VOICES if voice.id == voice_id), None)


def model_exists(voice: Voice, models_dir: Path) -> bool:
    path = models_dir / "tts" / voice.model
    return path.exists()


def voices_for(language: str, models_dir: Path) -> list[Voice]:
    return [voice for voice in VOICES if voice.language == language and model_exists(voice, models_dir)]


def default_voice(language: str, models_dir: Path) -> Voice | None:
    available = voices_for(language, models_dir)
    return available[0] if available else None
