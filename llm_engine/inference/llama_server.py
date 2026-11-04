"""Start, watch and stop a local llama-server process.

Before loading anything it compares the model's size with free memory, so a model that does not
fit fails with a clear message instead of pushing the machine into swap.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psutil

log = logging.getLogger("vap.llm")
GIB = 1024**3


class ModelDoesNotFit(RuntimeError):
    pass


@dataclass(frozen=True)
class LlamaOptions:
    model_path: Path
    base_url: str
    threads: int
    parallel: int
    ctx_size: int
    # On for a laptop whose other apps can give up memory. Windows then trims them, which is slower
    # for those apps but safe, so this is a deliberate choice and is never the default.
    allow_low_memory: bool = False


def estimated_load_gib(model_path: Path, ctx_size: int, parallel: int) -> float:
    """File size plus working buffers. Checked against measured use in docs/13_PERFORMANCE.md."""
    file_gib = model_path.stat().st_size / GIB
    return round(file_gib * 1.05 + 0.00006 * ctx_size * parallel + 0.15, 2)


def find_binary(models_dir: Path) -> str | None:
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    bundled = models_dir / "runtime" / "llama-server" / name
    if bundled.exists():
        return str(bundled)
    return shutil.which("llama-server")


class LlamaServer:
    def __init__(self, options: LlamaOptions, binary: str, log_dir: Path) -> None:
        self._options = options
        self._binary = binary
        self._log_path = log_dir / "llama-server.log"
        self._process: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    def check_memory(self) -> None:
        needed = estimated_load_gib(self._options.model_path, self._options.ctx_size, self._options.parallel)
        free = psutil.virtual_memory().available / GIB
        if needed > free and self._options.allow_low_memory:
            log.warning("Only %.1f GB is free and about %s GB is needed. Continuing as configured.", free, needed)
        elif needed > free:
            raise ModelDoesNotFit(
                f"{self._options.model_path.name} needs about {needed} GB and only {free:.1f} GB is free."
            )

    async def start(self, timeout: float = 180.0) -> None:
        self.check_memory()
        address = urlparse(self._options.base_url)
        command = [
            self._binary,
            "--model", str(self._options.model_path),
            "--host", address.hostname or "127.0.0.1",
            "--port", str(address.port or 8081),
            "--threads", str(self._options.threads),
            "--threads-http", "2",
            "--parallel", str(self._options.parallel),
            "--ctx-size", str(self._options.ctx_size * self._options.parallel),
            "--batch-size", "256",
            "--cache-reuse", "64",
            "--jinja",
            "--reasoning", "off",
            "--no-webui",
        ]  # fmt: skip
        log_file = self._log_path.open("ab")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(
            command, stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags, env=os.environ.copy()
        )
        log_file.close()
        deadline = asyncio.get_running_loop().time() + timeout
        root = self._options.base_url.removesuffix("/v1").rstrip("/")
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self._process.poll() is not None:
                    raise RuntimeError(f"llama-server exited early. See {self._log_path}.")
                try:
                    response = await client.get(f"{root}/health")
                    if response.status_code == 200:
                        log.info("llama-server ready, pid %s", self._process.pid)
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.25)
        self.stop()
        raise TimeoutError("llama-server did not become ready in time.")

    def stop(self) -> None:
        if not self._process:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
