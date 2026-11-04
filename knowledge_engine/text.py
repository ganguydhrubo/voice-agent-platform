"""Spelling-tolerant text for search.

Speech recognisers spell loan words freely: Hindi "pharmacy" can arrive as फ़ॉारमेसी while the
document says फार्मेसी. Both fold to the same search form, so the words still match. The folded form
is used only for matching. People and the language model always see the original text.
"""
from __future__ import annotations

import re
import unicodedata

_MARKS = str.maketrans(
    {
        "़": None,  # Devanagari nukta
        "्": None,  # Devanagari virama
        "়": None,  # Bengali nukta
        "্": None,  # Bengali virama
        "ॉ": "ा",  # candra o sign to aa sign
        "ॅ": "े",  # candra e sign to e sign
        "ऑ": "आ",  # candra O to AA
        "ऍ": "ए",  # candra E to E
        "ं": None,  # anusvara
        "ँ": None,  # candrabindu
        "ঁ": None,  # Bengali candrabindu
    }
)
_REPEATED_SIGN = re.compile("([ा-ौা-ৌ])\\1+")


def fold(text: str) -> str:
    """Lower-case and drop the marks that vary between spellings of one word."""
    folded = unicodedata.normalize("NFD", text).lower().translate(_MARKS)
    return unicodedata.normalize("NFC", _REPEATED_SIGN.sub(r"\1", folded))
