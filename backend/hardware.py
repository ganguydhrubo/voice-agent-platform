"""Detect this machine and recommend an execution profile.

Profiles (see docs/05_ARCHITECTURE.md):
  A  CPU only: quantised models, one or two conversations at a time.
  B  One GPU: GPU speech and LLM, more parallel conversations.
  C  Dedicated server: many cores or several GPUs, model workers kept loaded.

The module only reads. It never loads a model and never assumes a GPU exists.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

GIB = 1024**3


@dataclass(frozen=True)
class Gpu:
    name: str
    vram_gb: float
    free_vram_gb: float
    vendor: str


@dataclass(frozen=True)
class HardwareReport:
    os: str
    os_version: str
    cpu_model: str
    physical_cores: int
    logical_cores: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    gpus: tuple[Gpu, ...] = field(default_factory=tuple)

    @property
    def usable_gpu(self) -> Gpu | None:
        """The largest GPU with its own memory. Integrated graphics do not count."""
        dedicated = [gpu for gpu in self.gpus if gpu.vram_gb >= 4]
        return max(dedicated, key=lambda gpu: gpu.vram_gb, default=None)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["usable_gpu"] = asdict(self.usable_gpu) if self.usable_gpu else None
        return data


def _run(command: list[str], timeout: float = 6.0) -> str:
    """Output of a command, or an empty string when it is missing or fails."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _cpu_model() -> str:
    system = platform.system()
    if system == "Windows":
        name = _run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
            timeout=12,
        ).strip()
        if name:
            return name.splitlines()[0].strip()
    if system == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    if system == "Darwin":
        name = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        if name:
            return name
    return platform.processor() or "Unknown CPU"


def parse_nvidia_smi(output: str) -> list[Gpu]:
    """Parse `nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`."""
    gpus: list[Gpu] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            total, free = float(parts[1]), float(parts[2])
        except ValueError:
            continue
        gpus.append(Gpu(parts[0], round(total / 1024, 1), round(free / 1024, 1), "nvidia"))
    return gpus


def _detect_gpus() -> list[Gpu]:
    if shutil.which("nvidia-smi"):
        found = parse_nvidia_smi(
            _run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ]
            )
        )
        if found:
            return found
    if platform.system() == "Windows":
        names = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
            ],
            timeout=12,
        )
        # Windows reports shared memory for integrated graphics, so it is not counted as VRAM.
        return [
            Gpu(name.strip(), 0.0, 0.0, "integrated")
            for name in names.splitlines()
            if name.strip()
        ]
    return []


def detect(data_dir: str | os.PathLike[str] = ".") -> HardwareReport:
    memory = psutil.virtual_memory()
    return HardwareReport(
        os=platform.system(),
        os_version=platform.version(),
        cpu_model=_cpu_model(),
        physical_cores=psutil.cpu_count(logical=False) or 1,
        logical_cores=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(memory.total / GIB, 1),
        ram_available_gb=round(memory.available / GIB, 1),
        disk_free_gb=round(shutil.disk_usage(data_dir).free / GIB, 1),
        gpus=tuple(_detect_gpus()),
    )


@dataclass(frozen=True)
class ProfilePlan:
    """What to run on this machine. Sizes are the models' measured resident memory in GiB."""

    profile: str
    label: str
    llm_model: str
    stt_final: str
    stt_threads: int
    llm_threads: int
    tts_threads: int
    stt_workers: int
    tts_workers: int
    llm_parallel: int
    max_sessions: int
    partial_transcripts: bool
    device: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


# Measured resident memory on the test laptop: see docs/13_PERFORMANCE.md.
# Largest first. Only models that passed the benchmark are listed: 0.8B peaked at 1.19 GB at ctx 2048.
LLM_CHOICES: tuple[tuple[str, float], ...] = (
    ("qwen3.5-0.8b-q4km", 1.2),
)
SPEECH_RESERVE_GB = 1.0  # VAD + embeddings + the recogniser and voice of the languages in use
HEADROOM_GB = 0.5


def choose_llm(available_gb: float, allowed: tuple[str, ...] | None = None) -> tuple[str | None, str]:
    """Largest LLM that fits, or None with the reason. Never picks one that cannot load."""
    budget = available_gb - SPEECH_RESERVE_GB - HEADROOM_GB
    for model, needed in LLM_CHOICES:
        if allowed is not None and model not in allowed:
            continue
        if needed <= budget:
            return model, f"{model} needs {needed} GB and {budget:.1f} GB is free for it."
    return None, f"Only {budget:.1f} GB is free for the LLM. The smallest model needs {LLM_CHOICES[-1][1]} GB."


def plan(report: HardwareReport) -> ProfilePlan:
    """Choose a profile from what was detected. Uses total RAM for the profile and free RAM for the model."""
    gpu = report.usable_gpu
    reasons: list[str] = []
    cores = report.physical_cores

    if gpu and (len([g for g in report.gpus if g.vram_gb >= 4]) > 1 or report.logical_cores >= 32):
        profile, label = "C", "Dedicated self-hosted server"
    elif gpu:
        profile, label = "B", "GPU-accelerated"
    elif report.logical_cores >= 32 and report.ram_total_gb >= 64:
        profile, label = "C", "Dedicated self-hosted server"
    else:
        profile, label = "A", "CPU only"
    reasons.append(
        f"{report.logical_cores} logical cores, {report.ram_total_gb} GB RAM, "
        + (f"{gpu.name} with {gpu.vram_gb} GB VRAM." if gpu else "no dedicated GPU.")
    )

    # Keep STT and LLM from fighting over the performance cores.
    stt_threads = min(4, max(2, cores // 2))
    llm_threads = max(2, cores - stt_threads - 1)
    tts_threads = max(1, min(2, cores // 4))

    llm_model, llm_reason = choose_llm(report.ram_available_gb)
    reasons.append(llm_reason)
    if llm_model is None:
        # Start on the smallest model only when it can still load; the server refuses otherwise.
        llm_model = LLM_CHOICES[-1][0]
        reasons.append("Low memory: starting with the smallest model and the server will check again.")

    if profile == "A":
        llm_parallel = 1
        max_sessions = 2 if report.logical_cores >= 12 else 1
        partial = report.logical_cores >= 8
        device = "cpu"
    elif profile == "B":
        llm_parallel = 4
        max_sessions = 10
        partial = True
        device = "cuda" if gpu and gpu.vendor == "nvidia" else "cpu"
    else:
        llm_parallel = 8
        max_sessions = 40
        partial = True
        device = "cuda" if gpu else "cpu"

    return ProfilePlan(
        profile=profile,
        label=label,
        llm_model=llm_model,
        stt_final="zipformer-en-offline, indicconformer-hi, bangla-zipformer",
        stt_threads=stt_threads,
        llm_threads=llm_threads,
        tts_threads=tts_threads,
        stt_workers=1 if profile == "A" else 2,
        tts_workers=1 if profile == "A" else 2,
        llm_parallel=llm_parallel,
        max_sessions=max_sessions,
        partial_transcripts=partial,
        device=device,
        reasons=tuple(reasons),
    )
