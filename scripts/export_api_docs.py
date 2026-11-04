"""Write docs/API.md from the routes the application really serves.

    python scripts/export_api_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.main import create_app  # noqa: E402

VOICE_SOCKET = """
## Voice WebSocket: `/ws/voice`

The browser opens this socket after `POST /api/conversations` has given it a conversation `id` and `token`.

The browser sends one JSON message first:

```json
{"type": "start", "id": "<conversation id>", "token": "<token>", "mode": "voice", "resume": false}
```

After that the browser sends binary frames of 16 kHz, mono, 16-bit PCM, 20 ms each, and these JSON messages:

| Message | Meaning |
| --- | --- |
| `{"type": "text", "text": "..."}` | A typed question. |
| `{"type": "interrupt"}` | The caller pressed Interrupt. |
| `{"type": "playback", "turn": 3, "played_ms": 1200, "finished": false}` | How much of the reply has reached the speaker. Sent every 250 ms. |
| `{"type": "audible", "turn": 3, "after_speech_end_ms": 2100}` | The moment the first sound of a reply was heard. |
| `{"type": "language", "language": "hi"}` | Change language. |
| `{"type": "voice", "voice": "hi-rohan"}` | Change voice. |
| `{"type": "mode", "mode": "text"}` | Change between voice and text. |
| `{"type": "end"}` | End the conversation. |

The server sends JSON messages and binary audio.

| Message | Meaning |
| --- | --- |
| `ready` | The session is ready. |
| `state` | `listening`, `thinking`, `speaking` and so on. |
| `level` | Speech probability for the waveform. |
| `speech_start`, `speech_end` | The caller began or stopped talking. |
| `partial` | Live words while the caller talks. |
| `final` | The finished transcript of the turn. |
| `agent_start`, `agent_text`, `sources`, `turn_end` | The reply, its sources and its timings. |
| `flush` | Stop playing the named turn now. |
| `escalation` | A person is needed. Has a severity. |
| `notice` | A safe approved reply replaced the model's text, with the reason. |
| `language`, `voice`, `mode` | The setting changed. |
| `error`, `ended` | The reason for a stop. |

Each binary audio frame has a 12-byte header of three little-endian 32-bit numbers (turn, chunk index, sample rate), then 16-bit PCM.

Close codes: `4401` bad token, `4403` not allowed, `4503` all lines busy.
"""


def main() -> None:
    schema = create_app(light=True).openapi()
    lines = [
        "# API",
        "",
        "Generated from the running application by `scripts/export_api_docs.py`.",
        "In development mode the same detail is at `/api/docs`.",
        "",
        "Admin routes need a logged-in user. Writing routes also need a role that allows the action.",
        "",
        "## HTTP routes",
        "",
        "| Method | Path | Purpose |",
        "| --- | --- | --- |",
    ]
    for path, methods in sorted(schema["paths"].items()):
        for method, detail in methods.items():
            summary = detail.get("summary", "").replace("|", "/")
            lines.append(f"| {method.upper()} | `{path}` | {summary} |")
    target = ROOT / "docs" / "API.md"
    target.write_text("\n".join(lines) + "\n" + VOICE_SOCKET, encoding="utf8")
    print("wrote", target, len(lines) - 11, "routes")


if __name__ == "__main__":
    main()
