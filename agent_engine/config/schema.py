"""The shape of an industry agent. Everything a business changes lives here, not in code."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["en", "hi", "bn"]
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "hi": "Hindi", "bn": "Bengali"}

TOOL_NAMES = ("knowledge_search", "escalate_to_human", "record_callback_request")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EscalationRule(Strict):
    """A deterministic rule. It runs before the LLM, so the model cannot talk its way past it."""

    id: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    severity: Literal["emergency", "human"]
    # Lower-case phrases, per language. Matching ignores case and punctuation.
    phrases: dict[Language, list[str]]
    # Spoken instead of any model output. Required in every language the agent offers.
    response: dict[Language, str]

    @field_validator("phrases")
    @classmethod
    def phrases_not_empty(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if not any(value.values()):
            raise ValueError("Add at least one phrase.")
        return {lang: [phrase.strip().lower() for phrase in items if phrase.strip()] for lang, items in value.items()}


class RestrictedAction(Strict):
    """Something the agent must refuse, such as a diagnosis or legal advice."""

    id: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    phrases: dict[Language, list[str]]
    response: dict[Language, str]


class MemorySettings(Strict):
    keep_turns: int = Field(default=6, ge=0, le=20)
    store_transcripts: bool = True


class EvaluationTest(Strict):
    """A scripted check. `expect` is one of: answered, refused, escalated, no_answer."""

    id: str
    language: Language
    question: str = Field(min_length=2, max_length=300)
    expect: Literal["answered", "refused", "escalated", "no_answer"]
    must_include: list[str] = Field(default_factory=list)
    must_exclude: list[str] = Field(default_factory=list)


class AgentConfig(Strict):
    slug: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    industry: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=60)
    role: str = Field(min_length=2, max_length=120)
    organisation: str = Field(min_length=2, max_length=120)
    personality: str = Field(min_length=2, max_length=400)
    system_instructions: str = Field(min_length=2, max_length=2000)
    languages: list[Language] = Field(min_length=1)
    greeting: dict[Language, str]
    no_answer: dict[Language, str]
    knowledge_bases: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=lambda: ["knowledge_search", "escalate_to_human"])
    restricted_actions: list[RestrictedAction] = Field(default_factory=list)
    business_policies: list[str] = Field(default_factory=list)
    escalation_rules: list[EscalationRule] = Field(default_factory=list)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    strict_numbers: bool = True
    min_confidence: float = Field(default=0.62, ge=0, le=1)
    evaluation_tests: list[EvaluationTest] = Field(default_factory=list)

    @field_validator("allowed_tools")
    @classmethod
    def known_tools(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(TOOL_NAMES))
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}.")
        return value

    def missing_translations(self) -> list[str]:
        """Every fixed sentence must exist in every offered language."""
        problems: list[str] = []
        for language in self.languages:
            for field_name, texts in (("greeting", self.greeting), ("no_answer", self.no_answer)):
                if not texts.get(language):
                    problems.append(f"{field_name}: {LANGUAGE_NAMES[language]} is missing.")
            for rule in [*self.escalation_rules, *self.restricted_actions]:
                if not rule.response.get(language):
                    problems.append(f"{rule.id}: {LANGUAGE_NAMES[language]} response is missing.")
        return problems


_PUNCTUATION = re.compile(r"[\s।॥.,!?;:'\"()\[\]{}\-]+")


def normalise(text: str) -> str:
    """Lower-case, single-spaced text without punctuation, including the Hindi and Bengali danda."""
    return _PUNCTUATION.sub(" ", text.lower()).strip()
