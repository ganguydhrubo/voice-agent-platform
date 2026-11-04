"""Split sections into overlapping chunks at sentence ends, in Latin, Devanagari or Bengali text."""
from __future__ import annotations

import re
from dataclasses import dataclass

from knowledge_engine.ingestion.parsers import Section

_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s+|\n+")

# Text that addresses the assistant instead of the reader. Kept, but flagged and never trusted.
_INSTRUCTION_LIKE = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|rules)|"
    r"you are (now )?(an?|the) (ai|assistant|chatbot)|"
    r"system prompt|do not tell the user|disregard (your|the) instructions|"
    r"assistant:\s|<\|im_start\|>|\[inst\])",
    re.IGNORECASE,
)

_SCRIPT_RANGES = {"hi": (0x0900, 0x097F), "bn": (0x0980, 0x09FF)}


def detect_script_language(text: str) -> str:
    """Language by script. Bengali, Hindi or English; anything else in Latin script counts as English."""
    counts = {"hi": 0, "bn": 0, "en": 0}
    for char in text:
        code = ord(char)
        if 0x0900 <= code <= 0x097F:
            counts["hi"] += 1
        elif 0x0980 <= code <= 0x09FF:
            counts["bn"] += 1
        elif char.isascii() and char.isalpha():
            counts["en"] += 1
    best = max(counts, key=lambda language: counts[language])
    return best if counts[best] else ""


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    section: str
    language: str
    text: str
    flagged: bool


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part and part.strip()]


def chunk_sections(sections: list[Section], max_chars: int = 600, overlap_sentences: int = 1) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        sentences = split_sentences(section.text)
        current: list[str] = []
        size = 0
        index = 0
        while index < len(sentences):
            sentence = sentences[index]
            if len(sentence) > max_chars:  # one very long line: cut it on word boundaries
                pieces, line = [], ""
                for word in sentence.split(" "):
                    if len(line) + len(word) + 1 > max_chars and line:
                        pieces.append(line)
                        line = ""
                    line = f"{line} {word}".strip()
                if line:
                    pieces.append(line)
                sentences[index : index + 1] = pieces
                continue
            if size + len(sentence) > max_chars and current:
                chunks.append(_make(len(chunks), section.title, current))
                current = current[-overlap_sentences:] if overlap_sentences else []
                size = sum(len(item) for item in current)
                continue
            current.append(sentence)
            size += len(sentence) + 1
            index += 1
        if current:
            chunks.append(_make(len(chunks), section.title, current))
    return chunks


_PLAIN_TITLE = re.compile(r"^(Document|Page \d+|Row \d+|Table \d+)$")


def _make(ordinal: int, section: str, sentences: list[str]) -> Chunk:
    text = " ".join(sentences)
    # A real heading says what the passage is about, which helps both search and the model.
    if not _PLAIN_TITLE.match(section) and not text.startswith(section):
        text = f"{section}: {text}"
    return Chunk(ordinal, section, detect_script_language(text), text, bool(_INSTRUCTION_LIKE.search(text)))
