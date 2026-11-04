"""Put the agent on a public HTTPS link from this computer, for free. Needs no account.

    python scripts/go_live.py

It opens a Cloudflare quick tunnel, starts the agent with the settings a public address needs, and
prints the link. The link works while this window stays open and the computer stays on, and it
changes on every start. Press Ctrl+C to stop both.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8000
LINK = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_tunnel() -> str:
    for name in ("cloudflared.exe", "cloudflared"):
        local = ROOT / "models" / "runtime" / name
        if local.exists():
            return str(local)
    found = shutil.which("cloudflared")
    if found:
        return found
    raise SystemExit("cloudflared was not found. Put it in models/runtime. See docs/11_DEPLOYMENT.md.")


def open_tunnel(program: str) -> tuple[subprocess.Popen, str]:
    tunnel = subprocess.Popen(
        [program, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf8",
        errors="replace",
    )
    found: list[str] = []

    def read() -> None:
        for line in tunnel.stdout:
            match = LINK.search(line)
            if match and not found:
                found.append(match.group(0))

    threading.Thread(target=read, daemon=True).start()
    deadline = time.time() + 40
    while not found:
        if tunnel.poll() is not None or time.time() > deadline:
            tunnel.terminate()
            raise SystemExit("The tunnel did not open. Check the internet connection and try again.")
        time.sleep(0.2)
    return tunnel, found[0]


def wait_until_ready() -> bool:
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ready", timeout=3) as reply:
                if b'"llm":true' in reply.read():
                    return True
        except OSError:
            pass
        time.sleep(2)
    return False


def main() -> None:
    tunnel, link = open_tunnel(find_tunnel())
    settings = dict(
        os.environ,
        VAP_ENVIRONMENT="production",
        VAP_TRUST_PROXY="true",
        VAP_PUBLIC_ORIGIN=link,
    )
    server = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "serve.py")], cwd=ROOT, env=settings)
    try:
        if not wait_until_ready():
            raise SystemExit("The agent did not start in time. Read the messages above.")
        print(f"\nThe agent is live at:\n\n    {link}\n", flush=True)
        print("Keep this window open and the computer on. Press Ctrl+C to stop.\n", flush=True)
        while server.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        print("Stopped: the agent or the tunnel has closed.")
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.terminate()
        tunnel.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
