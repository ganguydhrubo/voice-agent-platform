"""Download the models named in models/manifests/catalogue.json into models/.

Nothing here needs an account or a paid service. Each item records its SHA-256 in
models/manifests/lock.json the first time it is fetched, and a later fetch that does not match
is refused, so a changed upstream file cannot slip in unnoticed.

    python scripts/fetch_models.py --list
    python scripts/fetch_models.py --profile cpu
    python scripts/fetch_models.py qwen3.5-0.8b-q4km silero-vad
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
CATALOGUE = MODELS / "manifests" / "catalogue.json"
LOCK = MODELS / "manifests" / "lock.json"

PROFILES = {
    # What the product runs on an ordinary computer: about 1.3 GB, chosen by measurement.
    "cpu": [
        "qwen3.5-0.8b-q4km",
        "zipformer-en-offline",
        "indicconformer-hi",
        "hindi-streaming-ctc",
        "bangla-zipformer-offline",
        "piper-en-alba",
        "piper-en-northern-male",
        "piper-hi-rohan",
        "piper-bn-google",
        "silero-vad",
        "multilingual-e5-small",
    ],
    # Optional: slower but more natural voices for English and Hindi. Adds about 0.2 GB.
    "natural-voices": ["kokoro-int8-multi-lang"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path, attempts: int = 8) -> None:
    """Fetch with resume, because large release files often stall on slow links."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "voice-agent-platform"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                mode = "ab" if offset and response.status == 206 else "wb"
                with partial.open(mode) as out:
                    while block := response.read(1 << 16):
                        out.write(block)
            partial.replace(dest)
            return
        except urllib.error.HTTPError as error:
            if error.code == 416:  # already complete
                partial.replace(dest)
                return
            if attempt == attempts or error.code in (401, 403, 404):
                raise
        except (OSError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(min(30, 2**attempt))


def hf_url(repo: str, file: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{quote(file)}"


def hf_files(repo: str, include: list[str] | None) -> list[str]:
    """Files of a public Hugging Face repo, optionally narrowed by glob patterns."""
    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=1"
    request = urllib.request.Request(url, headers={"User-Agent": "voice-agent-platform"})
    with urllib.request.urlopen(request, timeout=45) as response:
        entries = json.load(response)
    names = [entry["path"] for entry in entries if entry["type"] == "file"]
    names = [name for name in names if not name.startswith(".")]
    if include:
        names = [name for name in names if any(fnmatch.fnmatch(name, glob) for glob in include)]
    return names


def safe_extract_tar(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:*") as tar:
        tar.extractall(target, filter="data")


def safe_extract_zip(archive: Path, target: Path) -> None:
    root = target.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not (target / member.filename).resolve().is_relative_to(root):
                raise RuntimeError(f"Unsafe path in archive: {member.filename}")
        zipped.extractall(target)


def check_lock(lock: dict, key: str, digest: str) -> None:
    known = lock.get(key)
    if known and known != digest:
        raise RuntimeError(f"{key}: SHA-256 changed from {known} to {digest}. Refusing it.")
    lock[key] = digest


def fetch(item: dict, lock: dict) -> None:
    source = item["source"]
    target = MODELS / item["target"]
    target.mkdir(parents=True, exist_ok=True)
    marker = target / f".{item['id']}.done"
    kind = source["type"]
    if marker.exists():
        print(f"ok      {item['id']}")
        return
    print(f"fetch   {item['id']}", flush=True)
    if kind in ("hf_snapshot", "hf_file", "hf_files", "file"):
        if kind == "file":
            pairs = [(source["url"], target / source["name"])]
        elif kind == "hf_snapshot":
            files = hf_files(source["repo"], source.get("include"))
            pairs = [(hf_url(source["repo"], name), target / name) for name in files]
        else:
            files = source.get("files") or [source["file"]]
            pairs = [(hf_url(source["repo"], name), target / name) for name in files]
        with ThreadPoolExecutor(max_workers=8) as pool:  # espeak data is hundreds of small files
            list(pool.map(lambda pair: pair[1].exists() or download(*pair), pairs))
        for _, dest in pairs:
            if dest.stat().st_size >= 1 << 20:  # small text files are not worth pinning
                check_lock(lock, f"{item['id']}:{dest.name}", sha256(dest))
    elif kind in ("tar_bz2", "zip"):
        with tempfile.TemporaryDirectory() as tmp:
            name = source["url"].rsplit("/", 1)[-1]
            archive = Path(tmp) / name
            download(source["url"], archive)
            check_lock(lock, f"{item['id']}:{name}", sha256(archive))
            if kind == "zip":
                safe_extract_zip(archive, target)
            else:
                safe_extract_tar(archive, target)
    else:
        raise ValueError(f"Unknown source type: {kind}")
    marker.write_text("done\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("ids", nargs="*", help="catalogue ids to fetch")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="fetch a whole profile")
    parser.add_argument("--list", action="store_true", help="print the catalogue")
    args = parser.parse_args()

    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in catalogue["items"]}
    if args.list:
        for item in items.values():
            print(f"{item['id']:28} {item['kind']:10} {item['class']:20} {item['licence']}")
        return 0

    wanted = list(args.ids)
    if args.profile:
        wanted += PROFILES[args.profile]
        if args.profile == "cpu" and sys.platform == "win32":
            wanted.append("llama-server-win-cpu")
    unknown = [name for name in wanted if name not in items]
    if unknown or not wanted:
        parser.error(f"Choose ids from --list. Unknown: {unknown}")

    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    try:
        for name in dict.fromkeys(wanted):
            fetch(items[name], lock)
    finally:
        LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
