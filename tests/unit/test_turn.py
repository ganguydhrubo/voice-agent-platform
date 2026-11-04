"""The answer engine, with a scripted model so these are exact and fast."""
import pytest

from agent_engine.config.loader import bundled_agent
from agent_engine.orchestration.prompt import build_messages, choose_passages, system_prompt
from agent_engine.orchestration.turn import AnswerEngine, SentenceSplitter, is_follow_up, search_query
from knowledge_engine.retrieval.retriever import Hit, Retrieval
from knowledge_engine.vector_store.sqlite_store import StoredChunk
from llm_engine.providers.base import ChatMessage, LLMUnavailable, ScriptedProvider

AGENT = bundled_agent("healthcare").config
PHARMACY = "Departments: The laboratory is on the ground floor. The pharmacy is near the main entrance and is open 24 hours a day."
VISITING = "Visiting hours: Visiting hours are from 4 pm to 7 pm every day."


def hit(text: str, language: str = "en", section: str = "Document", cosine: float = 0.9) -> Hit:
    chunk = StoredChunk(text[:12], "doc", "kb", "guide.md", section, language, text, False)
    return Hit(chunk, 0.9, cosine, 1.0)


def search_returning(*texts: str, confidence: float = 0.9):
    return lambda query, language: Retrieval([hit(text) for text in texts], confidence)


async def collect(engine: AnswerEngine, question: str, language: str = "en", history=None) -> list:
    return [event async for event in engine.answer(AGENT, language, history or [], question)]


def spoken(events) -> str:
    return " ".join(event.text for event in events if event.kind == "sentence")


async def test_a_grounded_answer_is_spoken():
    engine = AnswerEngine(ScriptedProvider(["The pharmacy is near the main entrance."]), search_returning(PHARMACY))
    events = await collect(engine, "Where is the pharmacy?")
    assert spoken(events) == "The pharmacy is near the main entrance."
    assert [event for event in events if event.kind == "retrieval"][0].data["sources"]


async def test_low_confidence_says_it_does_not_know_and_never_calls_the_model():
    provider = ScriptedProvider(["Paris flights cost 500 euros."])
    engine = AnswerEngine(provider, search_returning(PHARMACY, confidence=0.3))
    events = await collect(engine, "What is the price of a flight to Paris?")
    assert spoken(events) == AGENT.no_answer["en"]
    assert provider.calls == []


async def test_an_emergency_never_reaches_the_model():
    provider = ScriptedProvider()
    engine = AnswerEngine(provider, search_returning(PHARMACY))
    events = await collect(engine, "My mother has chest pain")
    assert any(event.kind == "escalation" for event in events)
    assert provider.calls == []


async def test_an_invented_number_is_replaced_by_the_approved_text():
    engine = AnswerEngine(ScriptedProvider(["The pharmacy closes at 11 pm."]), search_returning(PHARMACY))
    events = await collect(engine, "When does the pharmacy close?")
    assert "11" not in spoken(events)
    assert "24 hours" in spoken(events)


async def test_a_reply_that_wanders_off_the_documents_becomes_no_answer():
    engine = AnswerEngine(ScriptedProvider(["Bananas grow quickly during warm summers everywhere."]), search_returning(PHARMACY))
    assert spoken(await collect(engine, "Where is the pharmacy?")) == AGENT.no_answer["en"]


async def test_repeating_the_last_answer_is_not_an_answer():
    last = "The pharmacy is near the main entrance."
    engine = AnswerEngine(ScriptedProvider([last]), search_returning(PHARMACY))
    history = [ChatMessage("user", "Where is the pharmacy?"), ChatMessage("assistant", last)]
    assert "24 hours" in spoken(await collect(engine, "When does it open?", history=history))


async def test_a_model_outage_reads_the_approved_text():
    class Broken(ScriptedProvider):
        async def stream_chat(self, messages, max_tokens, temperature):
            raise LLMUnavailable("down")
            yield ""

    engine = AnswerEngine(Broken(), search_returning(PHARMACY))
    events = await collect(engine, "Where is the pharmacy?")
    assert any(event.kind == "fallback" for event in events)
    assert "pharmacy" in spoken(events)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What are its timings?", True),
        ("वह कितने बजे खुलती है", True),
        ("এটা কখন খোলে", True),
        ("Where is the pharmacy?", False),
        ("ফার্মেসি কোথায়", False),
    ],
)
def test_follow_ups_are_recognised(question, expected):
    assert is_follow_up(question) is expected


def test_a_follow_up_searches_with_the_last_question():
    history = [ChatMessage("user", "Where is the pharmacy?"), ChatMessage("assistant", "Near the door.")]
    assert search_query(history, "When does it open?") == "Where is the pharmacy? When does it open?"
    assert search_query(history, "Where is billing?") == "Where is billing?"


def test_only_the_relevant_sentences_reach_the_model():
    chosen = choose_passages([hit(PHARMACY), hit(VISITING)], "Where is the pharmacy?")
    text = " ".join(sentence for _, sentences in chosen for sentence in sentences)
    assert "pharmacy" in text
    assert "laboratory" not in text
    assert "Visiting" not in text


def test_with_no_shared_words_the_closest_passage_is_used_whole():
    chosen = choose_passages([hit(PHARMACY), hit(VISITING)], "zzz qqq")
    assert chosen[0][1] == [PHARMACY]


def test_the_system_prompt_does_not_change_with_language():
    question = build_messages(AGENT, "bn", [], "ফার্মেসি কোথায়?", [hit(PHARMACY)])
    assert question[0].content == system_prompt(AGENT)
    assert "Reply in Bengali only." in question[-1].content
    assert "DOCUMENTS" in question[-1].content


def test_the_splitter_releases_the_first_clause_early():
    splitter = SentenceSplitter()
    pieces = []
    for token in "The hospital opens at nine in the morning, and it closes at five. Thanks.".split(" "):
        pieces += splitter.push(token + " ")
    pieces += splitter.flush()
    assert len(pieces) >= 2
    assert pieces[-1].endswith(".")


@pytest.mark.parametrize("text", ["यह पहला वाक्य है। यह दूसरा है।", "এটি প্রথম বাক্য। এটি দ্বিতীয়।"])
def test_the_splitter_knows_the_danda(text):
    splitter = SentenceSplitter()
    assert len(splitter.push(text) + splitter.flush()) == 2


def test_the_splitter_does_not_cut_a_decimal():
    splitter = SentenceSplitter()
    assert splitter.push("The fee is 2.50 today") == []
