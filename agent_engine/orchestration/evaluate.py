"""Run an agent's evaluation tests through the real turn engine."""
from __future__ import annotations

from agent_engine.config.schema import AgentConfig
from agent_engine.orchestration.turn import AnswerEngine


async def run_one(engine: AnswerEngine, agent: AgentConfig, test) -> dict:
    spoken: list[str] = []
    outcome = "answered"
    async for event in engine.answer(agent, test.language, [], test.question):
        if event.kind == "sentence":
            spoken.append(event.text)
        elif event.kind == "escalation":
            outcome = "escalated"
        elif event.kind == "refused":
            outcome = "refused"
        elif event.kind == "done" and event.data.get("kind") == "no_answer":
            outcome = "no_answer"
    reply = " ".join(spoken)
    lowered = reply.lower()
    failures = []
    if outcome != test.expect:
        failures.append(f"Expected {test.expect}, got {outcome}.")
    failures += [f"Missing: {item}." for item in test.must_include if item.lower() not in lowered]
    failures += [f"Should not say: {item}." for item in test.must_exclude if item.lower() in lowered]
    return {
        "id": test.id,
        "language": test.language,
        "question": test.question,
        "expected": test.expect,
        "outcome": outcome,
        "reply": reply,
        "passed": not failures,
        "failures": failures,
    }


async def run_agent_tests(engine: AnswerEngine, agent: AgentConfig) -> dict:
    results = [await run_one(engine, agent, test) for test in agent.evaluation_tests]
    passed = sum(1 for result in results if result["passed"])
    return {"passed": passed, "total": len(results), "results": results}
