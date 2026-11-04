"""Turn written text into text that reads aloud well.

Text-to-speech reads "040 5550 1234" as thousands and "₹2,000" as a symbol. Each language gets its
own rules here, so the model's written answer stays exact and only the spoken form changes.
"""
from __future__ import annotations

import re

DIGITS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "hi": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"],
    "bn": ["শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়"],
}
RUPEE = {"en": "rupees", "hi": "रुपये", "bn": "টাকা"}
PERCENT = {"en": "percent", "hi": "प्रतिशत", "bn": "শতাংশ"}
# Native digits are read the same way as ASCII digits once converted.
_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯", "01234567890123456789")

# Groups of digits with spaces or hyphens, or one long run: a telephone or reference number.
_PHONE = re.compile(r"(?<!\d)(?<!\d[.,])\+?\d[\d -]{5,}\d(?!\d)(?![.,]\d)")
_RUPEES = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)")
_RUPEES_WORD = re.compile(r"\b(?:Rs\.?|INR)\s?([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d)")
_CLOCK_EN = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s?(am|pm)\b", re.IGNORECASE)
_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")
_MARKUP = re.compile(r"[*_#`|<>\[\]{}]+")
_SPACES = re.compile(r"\s+")
# Short capitalised words that are read as words, not spelt out.
_NOT_ACRONYMS = {"AI", "OK", "NO", "IT"}


def _digits_aloud(match: re.Match, language: str) -> str:
    words = DIGITS[language]
    groups = re.split(r"[ -]+", match.group(0).replace("+", ""))
    spoken = [" ".join(words[int(digit)] for digit in group) for group in groups if group]
    return ", ".join(spoken)


def _clock(match: re.Match) -> str:
    hour, minutes, period = match.group(1), match.group(2), match.group(3).lower()
    middle = f" {minutes}" if minutes and minutes != "00" else ""
    return f"{hour}{middle} {' '.join(period).upper()}"


def _acronym(match: re.Match) -> str:
    word = match.group(0)
    return word if word in _NOT_ACRONYMS else " ".join(word)


def for_speech(text: str, language: str) -> str:
    cleaned = _MARKUP.sub(" ", text).translate(_NATIVE_DIGITS)
    cleaned = _RUPEES.sub(lambda m: f"{m.group(1)} {RUPEE[language]}", cleaned)
    cleaned = _RUPEES_WORD.sub(lambda m: f"{m.group(1)} {RUPEE[language]}", cleaned)
    cleaned = _PERCENT.sub(lambda m: f"{m.group(1)} {PERCENT[language]}", cleaned)
    cleaned = _THOUSANDS.sub("", cleaned)
    cleaned = _PHONE.sub(lambda m: _digits_aloud(m, language), cleaned)
    cleaned = _CLOCK_EN.sub(_clock, cleaned)
    cleaned = _ACRONYM.sub(_acronym, cleaned)
    return _SPACES.sub(" ", cleaned).strip()
