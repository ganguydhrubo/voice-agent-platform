"""Everything heavy and shared: database, models, worker pools and the LLM process.

One Runtime exists per server process. Sessions borrow from it and never own a model. Speech models
load on first use for a language, so memory stays low until a language is actually needed.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_engine.orchestration.turn import AnswerEngine
from backend.config import Settings
from backend.db import Database
from backend.hardware import HardwareReport, ProfilePlan, detect, plan
from backend.security import SlidingWindowLimiter
from backend.voice.manager import SessionManager
from knowledge_engine.embeddings.embedder import HashEmbedder, OnnxEmbedder
from knowledge_engine.service import KnowledgeService
from llm_engine.inference.llama_server import LlamaOptions, LlamaServer, ModelDoesNotFit, find_binary
from llm_engine.providers.base import LLMProvider, ScriptedProvider
from llm_engine.routing.router import MODEL_FILES, build_provider
from voice_engine.tts.engine import SpeechEngine
from voice_engine.tts.voices import default_voice
from voice_engine.vad.silero import SileroModel, VadSettings

log = logging.getLogger("vap.runtime")

LANGUAGES = ("en", "hi", "bn")
# The final recogniser for each language, chosen by measurement. See docs/13_PERFORMANCE.md.
FINAL_STT = {
    "en": ("zipformer", "zipformer-en-offline"),
    "hi": ("conformer", "indicconformer-hi"),
    "bn": ("zipformer", "bangla-zipformer"),
}
# English and Bengali decode in about 130 ms, so they re-decode for live text. Hindi's final model
# takes about a second, so a separate streaming model shows live words without delaying it.
STREAMING_HINDI = "hindi-streaming-ctc"


class Runtime:
    def __init__(self, settings: Settings, *, light: bool = False) -> None:
        """`light` runs without any model files, for tests: hashing embedder and no speech."""
        self.settings = settings
        self.light = light
        self.db = Database(settings.database_path)
        self.db.migrate()
        self.hardware: HardwareReport = detect(settings.data_dir)
        self.plan: ProfilePlan = plan(self.hardware)
        self.model_error = ""

        models = settings.models_dir
        embedding_dir = models / "embedding" / "multilingual-e5-small"
        self.embedder = HashEmbedder() if light or not embedding_dir.exists() else OnnxEmbedder(embedding_dir)
        self.knowledge = KnowledgeService(self.db, self.embedder)

        self.vad_model = None if light else SileroModel(models / "vad" / "silero_vad.onnx")
        self.vad_settings = VadSettings(
            threshold=settings.vad_threshold,
            min_speech_ms=settings.vad_min_speech_ms,
            barge_in_ms=settings.barge_in_min_speech_ms,
            end_silence_ms=settings.vad_end_silence_ms,
            max_utterance_ms=int(settings.max_utterance_seconds * 1000),
        )
        self.speech = SpeechEngine(models, threads=self.plan.tts_threads)
        self.stt_pool = ThreadPoolExecutor(max_workers=self.plan.stt_workers, thread_name_prefix="stt")
        self.tts_pool = ThreadPoolExecutor(max_workers=self.plan.tts_workers, thread_name_prefix="tts")
        self.sessions = SessionManager(settings.max_sessions or self.plan.max_sessions, settings.min_free_ram_gb)
        self.login_limiter = SlidingWindowLimiter(20, 60)
        self.api_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute, 60)

        self.llm: LLMProvider = ScriptedProvider() if light else build_provider(settings)
        self._llama: LlamaServer | None = None
        self._recognisers: dict[str, object] = {}
        self._partial_model = None
        self._load_lock = threading.Lock()

    def engine_for(self, tenant_id: str, kb_ids: list[str]) -> AnswerEngine:
        def search(query: str, language: str):
            return self.knowledge.search(tenant_id, kb_ids, query, language)

        return AnswerEngine(self.llm, search, max_tokens=self.settings.llm_max_tokens)

    async def start(self) -> None:
        if self.light or self.settings.llm_provider != "llama-server" or not self.settings.llm_manage_process:
            return
        name = self.settings.llm_model or self.plan.llm_model
        path = self.settings.models_dir / "llm" / MODEL_FILES.get(name, name)
        binary = find_binary(self.settings.models_dir)
        if not path.exists() or binary is None:
            self.model_error = f"The language model {path.name} or llama-server is missing. Run scripts/fetch_models.py."
            log.error(self.model_error)
            return
        options = LlamaOptions(
            path,
            self.settings.llm_base_url,
            self.plan.llm_threads,
            self.plan.llm_parallel,
            self.settings.llm_ctx_size,
            self.settings.llm_allow_low_memory,
        )
        self._llama = LlamaServer(options, binary, self.settings.data_dir)
        try:
            await self._llama.start()
        except (ModelDoesNotFit, RuntimeError, TimeoutError) as error:
            # The app still runs: approved passages are read without the LLM.
            self.model_error = str(error)
            log.error("LLM did not start: %s", error)
        await asyncio.to_thread(self.preload)

    async def stop(self) -> None:
        if self._llama:
            self._llama.stop()
        close = getattr(self.llm, "close", None)
        if close:
            await close()
        self.stt_pool.shutdown(wait=False, cancel_futures=True)
        self.tts_pool.shutdown(wait=False, cancel_futures=True)

    def recogniser(self, language: str):
        """Final speech-to-text for a language. Thread-safe; loads on first use."""
        with self._load_lock:
            found = self._recognisers.get(language)
            if found is not None:
                return found
            kind, name = FINAL_STT[language]
            path = self.settings.models_dir / "stt" / name
            if kind == "conformer":
                from voice_engine.stt.conformer import ConformerTranscriber

                found = ConformerTranscriber(path, language, threads=self.plan.stt_threads)
            else:
                from voice_engine.stt.transducer import OfflineZipformer

                tokens = path / "tokens.txt"
                folder = path / "int8" if (path / "int8").exists() else path
                found = OfflineZipformer(folder, language, threads=self.plan.stt_threads, tokens=tokens)
            self._recognisers[language] = found
            log.info("Loaded recogniser for %s: %s", language, name)
            return found

    def streaming_hindi(self):
        """Live Hindi words, when the model is present."""
        with self._load_lock:
            if self._partial_model is None:
                folder: Path = self.settings.models_dir / "stt" / STREAMING_HINDI
                if folder.exists():
                    from voice_engine.stt.zipformer import CtcStreamingModel

                    self._partial_model = CtcStreamingModel(folder, threads=1)
            return self._partial_model

    def preload(self) -> None:
        """Pay the loading cost at start-up, so nobody waits in silence for the first greeting."""
        if self.light:
            return
        self.recogniser("en")
        voices = [default_voice(language, self.settings.models_dir) for language in LANGUAGES]
        self.speech.preload([voice for voice in voices if voice])

    def loaded_models(self) -> dict:
        return {
            "recognisers": sorted(self._recognisers),
            "voices": self.speech.loaded_models,
            "llm_running": bool(self._llama and self._llama.running),
        }

    async def run_stt(self, function, *args):
        self.sessions.stt_waiting += 1
        try:
            return await asyncio.get_running_loop().run_in_executor(self.stt_pool, function, *args)
        finally:
            self.sessions.stt_waiting -= 1
