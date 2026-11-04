"""Settings, read from the environment or .env. Defaults run the whole stack locally with no key."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAP_", env_file=ROOT / ".env", extra="ignore")

    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    public_origin: str = "http://localhost:8000"
    data_dir: Path = ROOT / "data"
    models_dir: Path = ROOT / "models"

    # First owner account. Created once, on first start, when both are set.
    admin_email: str = ""
    admin_password: str = ""

    # Local LLM. Any OpenAI-compatible server works, so changing model or runtime is configuration.
    llm_provider: str = "llama-server"
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = ""
    llm_model: str = ""  # empty = chosen from the hardware plan
    llm_manage_process: bool = True  # start and stop llama-server ourselves
    llm_ctx_size: int = 2048
    llm_max_tokens: int = 160
    llm_allow_low_memory: bool = False  # load even when free memory looks too low; see docs/15_OPERATIONS.md

    # Speech
    max_utterance_seconds: float = 20.0
    vad_threshold: float = 0.5
    vad_end_silence_ms: int = 450
    vad_min_speech_ms: int = 160
    barge_in_min_speech_ms: int = 240

    # Limits
    max_sessions: int = 0  # 0 = from the hardware plan
    max_upload_mb: int = 25
    rate_limit_per_minute: int = 120
    login_attempts_before_lock: int = 5
    login_lock_minutes: int = 15
    session_hours: int = 12
    remember_days: int = 30

    # Refuse new work when free memory falls under this.
    min_free_ram_gb: float = Field(default=0.3, ge=0)

    # /metrics answers only on this machine unless this is set behind a private network.
    metrics_open: bool = False

    # Behind a tunnel or reverse proxy every request seems to come from 127.0.0.1. Turn this on there,
    # so rate limits and audit logs see the caller's address. Leave it off when the server faces
    # callers directly, because anyone can forge these headers.
    trust_proxy: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "platform.db"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
