"""Voice detection logic, the wire format and memory planning. No audio models needed."""
import numpy as np

from backend.hardware import LLM_CHOICES, choose_llm
from backend.voice.manager import SessionManager
from backend.voice.protocol import CHUNK_MS, HEADER, audio_frame, split_pcm
from voice_engine.stt.transducer import tidy
from voice_engine.tts.normalise import for_speech
from voice_engine.vad.silero import WINDOW_SAMPLES, UtteranceDetector, VadSettings


class ScriptedVad:
    """Returns a chosen speech probability for each 32 ms window."""

    def __init__(self, values):
        self.values = list(values)

    def probability(self, window):
        return self.values.pop(0) if self.values else 0.0

    def reset(self):
        pass


def feed(detector: UtteranceDetector, windows: int) -> list:
    events = []
    for _ in range(windows):
        events += detector.feed(np.zeros(WINDOW_SAMPLES, dtype=np.int16).tobytes())
    return events


def test_speech_then_silence_gives_one_utterance():
    detector = UtteranceDetector(ScriptedVad([0.9] * 20 + [0.0] * 20), VadSettings(end_silence_ms=320))
    assert [event.kind for event in feed(detector, 40)] == ["speech_start", "speech_end"]


def test_a_click_is_not_speech():
    detector = UtteranceDetector(ScriptedVad([0.9] * 2 + [0.0] * 30), VadSettings(end_silence_ms=320))
    assert feed(detector, 32) == []


def test_the_agent_echo_does_not_interrupt():
    detector = UtteranceDetector(ScriptedVad([0.6] * 30), VadSettings())
    detector.agent_speaking = True
    assert feed(detector, 30) == []


def test_real_speech_interrupts_the_agent():
    detector = UtteranceDetector(ScriptedVad([0.95] * 30), VadSettings(barge_in_ms=240))
    detector.agent_speaking = True
    assert "barge_in" in [event.kind for event in feed(detector, 30)]


def test_a_very_long_utterance_is_closed():
    detector = UtteranceDetector(ScriptedVad([0.9] * 400), VadSettings(max_utterance_ms=3200))
    assert "speech_end" in [event.kind for event in feed(detector, 300)]


def test_audio_frames_carry_their_turn():
    frame = audio_frame(7, 3, 22050, b"\x01\x02")
    assert HEADER.unpack(frame[:12]) == (7, 3, 22050)
    assert frame[12:] == b"\x01\x02"


def test_pcm_is_cut_into_short_chunks():
    rate = 16000
    chunks = split_pcm(b"\0\0" * rate, rate)
    assert len(chunks) == 1000 // CHUNK_MS
    assert sum(len(chunk) for chunk in chunks) == rate * 2


def test_admission_stops_at_the_limit():
    manager = SessionManager(max_sessions=1, min_free_ram_gb=0)
    assert manager.try_admit().allowed
    refused = manager.try_admit()
    assert not refused.allowed
    assert refused.reason == "capacity"
    manager.release()
    assert manager.try_admit().allowed


def test_admission_refuses_when_memory_is_short():
    manager = SessionManager(max_sessions=5, min_free_ram_gb=10_000)
    assert manager.try_admit().reason == "memory"


def test_english_capitals_become_a_sentence():
    assert tidy("WHERE IS THE PHARMACY", "en") == "Where is the pharmacy"
    assert tidy("I THINK I AM LATE", "en") == "I think I am late"
    assert tidy("ফার্মেসি কোথায়", "bn") == "ফার্মেসি কোথায়"


def test_the_model_choice_needs_enough_free_memory():
    assert choose_llm(4.0)[0] == LLM_CHOICES[0][0]
    assert choose_llm(0.2)[0] is None


def test_phone_digits_are_read_one_at_a_time():
    assert "1234" not in for_speech("Call 040 5550 1234.", "en")
    assert for_speech("Call 040 5550 1234.", "en").endswith("one two three four.")


def test_a_decimal_is_not_read_as_a_telephone_number():
    assert for_speech("The fee rose by 1234567.50 this year.", "en").count("zero") == 0
