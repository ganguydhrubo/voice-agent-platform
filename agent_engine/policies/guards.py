"""Checks that run outside the model. They decide; the LLM only ever fills in what they allow.

Order for every user turn:
  1. Escalation rules (an emergency wins over everything else).
  2. Restricted actions.
  3. Prompt-injection screen.
After generation, each sentence passes `check_sentence` before it can reach the speaker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent_engine.config.schema import AgentConfig, EscalationRule, RestrictedAction, normalise
from knowledge_engine.ingestion.chunker import detect_script_language
from knowledge_engine.text import fold


@dataclass(frozen=True)
class Decision:
    kind: str  # "escalate", "refuse", "injection" or "allow"
    response: str = ""
    rule_id: str = ""
    severity: str = ""


def _contains(text: str, phrase: str) -> bool:
    """Whole-phrase match. Hindi and Bengali inflect by suffix, so those match at word start."""
    target = normalise(phrase)
    if not target:
        return False
    if target.isascii():
        return f" {target} " in f" {text} "
    return f" {target}" in f" {text}"


def match_escalation(config: AgentConfig, text: str, language: str) -> EscalationRule | None:
    clean = normalise(text)
    # Rules in every language are checked: a caller may slip into English in an emergency.
    ordered = sorted(config.escalation_rules, key=lambda rule: rule.severity != "emergency")
    for rule in ordered:
        for phrases in rule.phrases.values():
            if any(_contains(clean, phrase) for phrase in phrases):
                return rule
    return None


def match_restricted(config: AgentConfig, text: str, language: str) -> RestrictedAction | None:
    clean = normalise(text)
    for action in config.restricted_actions:
        for phrases in action.phrases.values():
            if any(_contains(clean, phrase) for phrase in phrases):
                return action
    return None


_INJECTION = [
    r"ignore (all |any |the |your |my )*(previous |prior |above |earlier )?(instructions|rules|prompts?)",
    r"(disregard|forget) (all |any |the |your |my )*(previous |prior |above |earlier )?(instructions|rules|prompts?)",
    r"(reveal|show|print|repeat|tell me) (me )?(your|the) (system prompt|instructions|rules)",
    r"you are now (a|an|the) ",
    r"pretend (to be|you are)",
    r"developer mode",
    r"jailbreak",
    r"act as (a|an) (doctor|lawyer|admin|developer)",
    r"(पिछले|पहले के) (सभी )?(निर्देश|नियम).{0,20}(भूल|अनदेखा|नज़रअंदाज़|नजरअंदाज)",
    r"(আগের|পূর্বের) (সব |সকল )?(নির্দেশ|নিয়ম).{0,20}(ভুলে|উপেক্ষা)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION), re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


INJECTION_RESPONSE = {
    "en": "I can only help with questions about our services.",
    "hi": "यहाँ केवल हमारी सेवाओं से जुड़े सवालों में मदद मिल सकती है।",
    "bn": "আমি শুধু আমাদের পরিষেবা সংক্রান্ত প্রশ্নে সাহায্য করতে পারি।",
}


def screen_turn(config: AgentConfig, text: str, language: str) -> Decision:
    rule = match_escalation(config, text, language)
    if rule:
        return Decision("escalate", _pick(rule.response, language), rule.id, rule.severity)
    action = match_restricted(config, text, language)
    if action:
        return Decision("refuse", _pick(action.response, language), action.id)
    if looks_like_injection(text):
        return Decision("injection", INJECTION_RESPONSE.get(language, INJECTION_RESPONSE["en"]), "prompt-injection")
    return Decision("allow")


def _pick(texts: dict[str, str], language: str) -> str:
    return texts.get(language) or texts.get("en") or next(iter(texts.values()))


# Devanagari and Bengali digits count as digits too.
_NUMBER = re.compile(r"[0-9०-९০-৯][0-9०-९০-৯,.:/-]*")
_DIGIT_TABLE = {0x0966 + i: str(i) for i in range(10)} | {0x09E6 + i: str(i) for i in range(10)}


def _numbers(text: str) -> set[str]:
    found = set()
    for match in _NUMBER.findall(text):
        digits = re.sub(r"\D", "", match.translate(_DIGIT_TABLE))
        if digits:
            found.add(digits.lstrip("0") or "0")
    return found


def unsupported_numbers(sentence: str, context: str) -> set[str]:
    """Numbers in a generated sentence that the retrieved documents do not contain."""
    allowed = _numbers(context)
    return {number for number in _numbers(sentence) if number not in allowed and len(number) > 1}


_MEDICAL_CLAIMS = re.compile(
    r"\b(you (probably |likely |may |might )?have|you are suffering|take \d+ ?mg|i diagnose|your diagnosis)\b",
    re.IGNORECASE,
)


def check_sentence(sentence: str, context: str, config: AgentConfig, leak_marker: str) -> str | None:
    """None when the sentence may be spoken, otherwise the reason it was dropped."""
    if leak_marker and leak_marker in sentence:
        return "system prompt leak"
    if "system prompt" in sentence.lower():
        return "system prompt leak"
    if config.strict_numbers and unsupported_numbers(sentence, context):
        return "number not in approved documents"
    if any(rule.severity == "emergency" for rule in config.escalation_rules) and _MEDICAL_CLAIMS.search(sentence):
        return "medical claim"
    if config.strict_numbers and not grounded(sentence, context):
        return "not grounded"
    return None


MIN_GROUNDED_SHARE = 0.34


def grounded(sentence: str, context: str) -> bool:
    """At least a third of the sentence's words must come from the documents.

    A small model can answer fluently and wrongly. Its own wording of a real fact still overlaps the
    document well, while a made-up reply barely overlaps it at all. Replies in a different language
    from the document cannot be compared, so they pass.
    """
    if detect_script_language(sentence) != detect_script_language(context):
        return True
    words = re.findall(r"[\w\u0900-\u097f\u0980-\u09ff]+", fold(sentence))
    if len(words) < 3:
        return True
    source = fold(context)
    return sum(word in source for word in words) / len(words) >= MIN_GROUNDED_SHARE


_SMALL_TALK = {
    "greeting": (
        {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "namaste", "नमस्ते", "नमस्कार", "নমস্কার", "হ্যালো", "हैलो"},
        {"en": "Hello. How can I help you?", "hi": "नमस्ते। मैं आपकी क्या मदद कर सकती हूँ?", "bn": "নমস্কার। আমি আপনাকে কীভাবে সাহায্য করতে পারি?"},
    ),
    "thanks": (
        {"thanks", "thank you", "thank you very much", "ok thanks", "okay thank you", "धन्यवाद", "शुक्रिया", "ধন্যবাদ"},
        {"en": "You are welcome. Is there anything else I can help with?", "hi": "आपका स्वागत है। क्या मैं और कोई मदद कर सकती हूँ?", "bn": "আপনাকে স্বাগত। আর কিছু সাহায্য করতে পারি?"},
    ),
    "goodbye": (
        {"bye", "goodbye", "good bye", "bye bye", "अलविदा", "নমস্কার আসি", "বিদায়"},
        {"en": "Thank you for calling. Goodbye.", "hi": "संपर्क करने के लिए धन्यवाद। नमस्ते।", "bn": "যোগাযোগ করার জন্য ধন্যবাদ। নমস্কার।"},
    ),
}


def small_talk(question: str, language: str) -> str:
    """A polite reply when the whole message is a greeting, thanks or goodbye; otherwise nothing."""
    words = " ".join("".join(char if char.isalnum() or char.isspace() or ord(char) > 0x8ff else " " for char in question).lower().split())
    words = words.strip("।॥ ")
    for phrases, replies in _SMALL_TALK.values():
        if words in phrases:
            return replies.get(language, replies["en"])
    return ""
