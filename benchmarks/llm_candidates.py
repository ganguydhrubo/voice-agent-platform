"""Compare local language models on real grounded questions in three languages.

Each model is started in llama-server and asked the same questions with the same retrieved
passages. Time to first token, speed, memory and the words themselves are recorded, and the same
sentence checks that run in production decide whether each answer would have been spoken.

    python benchmarks/llm_candidates.py --models qwen3.5-0.8b-q4km qwen3.5-2b-q4km --threads 6
"""
from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_engine.config.loader import bundled_agent  # noqa: E402
from agent_engine.orchestration.prompt import build_messages  # noqa: E402
from agent_engine.orchestration.turn import AnswerEngine  # noqa: E402
from backend.db import Database  # noqa: E402
from knowledge_engine.embeddings.embedder import OnnxEmbedder  # noqa: E402
from knowledge_engine.service import KnowledgeService  # noqa: E402
from llm_engine.inference.llama_server import LlamaOptions, LlamaServer, find_binary  # noqa: E402
from llm_engine.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402

FILES = {
    "qwen3.5-0.8b-q4km": "Qwen3.5-0.8B-Q4_K_M.gguf",
    "qwen3.5-2b-q4km": "Qwen3.5-2B-Q4_K_M.gguf",
}

QUESTIONS = [
    ("en", "What are the visiting hours?", ["4", "7"]),
    ("en", "How many visitors can come at one time?", ["2", "two"]),
    ("en", "What are the OPD timings?", ["9", "5"]),
    ("en", "Where can I get medicine at night?", ["pharmacy", "Pharmacy"]),
    ("hi", "मरीज़ से मिलने का समय क्या है?", ["4", "7", "चार", "सात"]),
    ("hi", "ओपीडी कब खुलती है?", ["9", "सुबह"]),
    ("hi", "अपॉइंटमेंट कैसे लें?", ["040", "डेस्क"]),
    ("hi", "दवाई की दुकान कब खुली रहती है?", ["24"]),
    ("bn", "রোগী দেখার সময় কখন?", ["4", "7", "৪", "৭", "চার", "সাত"]),
    ("bn", "ওপিডি কখন খোলা থাকে?", ["9", "৯", "সকাল"]),
    ("bn", "অ্যাপয়েন্টমেন্ট কীভাবে নেব?", ["040", "ডেস্ক"]),
    ("bn", "ওষুধের দোকান কখন খোলা?", ["24", "২৪"]),
]


def process_mb(pid: int) -> float:
    return round(psutil.Process(pid).memory_info().rss / 1048576)


async def run(model: str, threads: int, ctx: int) -> dict:
    bundled = bundled_agent("healthcare")
    agent = bundled.config
    folder = Path(tempfile.mkdtemp(prefix="vap-llm-"))
    db = Database(folder / "bench.sqlite3")
    db.migrate()
    db.execute("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t', 'bench', 'Bench', '2026-11-04T00:00:00+00:00')")
    knowledge = KnowledgeService(db, OnnxEmbedder(ROOT / "models/embedding/multilingual-e5-small"))
    base = knowledge.create_base("t", "healthcare")
    for path in bundled.sample_files:
        knowledge.ingest_file("t", base["id"], path.name, path.read_bytes())

    options = LlamaOptions(ROOT / "models/llm" / FILES[model], "http://127.0.0.1:8099/v1", threads, 1, ctx, allow_low_memory=True)
    server = LlamaServer(options, find_binary(ROOT / "models"), folder)
    started = time.perf_counter()
    await server.start()
    atexit.register(server.stop)
    load_s = round(time.perf_counter() - started, 1)
    provider = OpenAICompatibleProvider(options.base_url)
    idle_mb = process_mb(server.pid)
    rows = []
    peak = idle_mb

    def search(query: str, language: str):
        return knowledge.search("t", [base["id"]], query, language)

    engine = AnswerEngine(provider, search, max_tokens=160)
    for language, question, expected in QUESTIONS:
        hits = search(question, language)
        messages = build_messages(agent, language, [], question, hits.hits)
        first = None
        tokens = 0
        begun = time.perf_counter()
        text = ""
        async for piece in provider.stream_chat(messages, 160, 0.2):
            first = first or time.perf_counter() - begun
            tokens += 1
            text += piece
        total = time.perf_counter() - begun
        peak = max(peak, process_mb(server.pid))
        spoken, dropped = [], []
        async for event in engine.answer(agent, language, [], question):
            if event.kind == "sentence":
                spoken.append(event.text)
            elif event.kind == "dropped":
                dropped.append([event.text, event.data.get("reason")])
        rows.append(
            {
                "language": language,
                "question": question,
                "ttft_ms": round((first or total) * 1000),
                "total_ms": round(total * 1000),
                "tokens_per_s": round(tokens / max(total - (first or 0), 0.01), 1),
                "confidence": hits.confidence,
                "raw": text,
                "spoken": " ".join(spoken),
                "dropped": dropped,
                "has_fact": any(item in " ".join(spoken) for item in expected),
            }
        )
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    await provider.close()
    server.stop()
    return {
        "model": model,
        "threads": threads,
        "ctx": ctx,
        "load_s": load_s,
        "idle_rss_mb": idle_mb,
        "peak_rss_mb": peak,
        "ttft_ms_median": round(statistics.median(row["ttft_ms"] for row in rows)),
        "tokens_per_s_median": statistics.median(row["tokens_per_s"] for row in rows),
        "facts_ok": f"{sum(row['has_fact'] for row in rows)}/{len(rows)}",
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=list(FILES))
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--ctx", type=int, default=4096)
    args = parser.parse_args()
    target = ROOT / "benchmarks/results/llm_candidates.json"
    results = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    for model in args.models:
        summary = asyncio.run(run(model, args.threads, args.ctx))
        print({key: value for key, value in summary.items() if key != "rows"}, flush=True)
        results.append(summary)
        target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
