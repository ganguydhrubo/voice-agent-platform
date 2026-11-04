# Architecture

```
 Browser                                      Server (one Python process plus llama-server)
 ┌───────────────────────────┐   HTTPS/WSS    ┌──────────────────────────────────────────────┐
 │ React page                │ ─────────────► │ FastAPI: pages, REST, /ws/voice              │
 │ AudioWorklet 16 kHz PCM   │ ◄───────────── │ VoiceSession per caller                      │
 │ AudioPlayer, schedules    │  audio, events │  ├ Silero VAD, turn detection                │
 │ chunks, flushes on stop   │                │  ├ Speech to text, by language               │
 └───────────────────────────┘                │  ├ Guards before the model                   │
                                              │  ├ Retrieval, SQLite FTS5 + vectors          │
                                              │  ├ llama-server, streaming                   │
                                              │  ├ Checks on every sentence                  │
                                              │  └ Piper voice, sentence by sentence         │
                                              │ SessionManager: places, memory, degradation  │
                                              │ SQLite (WAL): tenants, agents, documents,    │
                                              │ conversations, audit log, turn metrics       │
                                              └──────────────────────────────────────────────┘
```

## Parts

| Folder | Job |
| --- | --- |
| `frontend/` | React, TypeScript, Vite. Built to static files that FastAPI serves. |
| `backend/` | App start-up, REST, WebSocket session, login, roles, limits, hardware plan, metrics. |
| `voice_engine/` | VAD, speech to text, text to speech, text clean-up for speech. |
| `llm_engine/` | llama-server start and stop, streaming, provider interface. |
| `agent_engine/` | Agent files, prompts, guards, the answer flow for one turn. |
| `knowledge_engine/` | Parsing, chunking, embedding, storing, searching. |
| `models/manifests/` | Which models exist, and their checksums. |
| `infrastructure/` | Docker, Caddy, nginx, Prometheus, Grafana. |
| `tests/` | Unit, integration, live, browser and benchmark tests. |

## Main decisions

1. **The server decides when speech ends.** Silero runs on the server, so a browser cannot skip the higher bar used while the agent talks.
2. **Sentence-sized streaming.** The model streams text. Each finished sentence passes the checks, then goes to the voice. A bad sentence never reaches the speaker.
3. **Guards sit outside the model.** Emergency, restricted topics and prompt injection are caught by plain code before the model sees the question. The model is not trusted to refuse.
4. **The approved text is the fallback.** If the model strays, the caller hears a sentence taken straight from the document. If no document fits, the caller hears the agent's fixed no-answer line.
5. **Bounded work.** STT and TTS each run in small worker pools with a limit. When the pool is full, callers are told, rather than waiting without end.
6. **SQLite for now.** One file, no server to run, and FTS5 for word search. It suits one machine. More than one server needs a shared database, which is not built. See `12_COST_ANALYSIS.md`.
7. **No model in the page.** The browser only captures and plays audio, so a phone can use it.

## One turn

1. Browser sends 20 ms audio frames over the WebSocket.
2. VAD finds the end of speech after 450 ms of silence.
3. Recogniser produces the final text.
4. Guards check it. An emergency goes straight to the emergency reply and an escalation record.
5. Retriever finds the best passages. Confidence under 0.62 gives the no-answer line and no model call.
6. Prompt is built with the passages and the short history.
7. Model streams. Sentences are checked.
8. Piper makes audio. Frames go to the browser in 200 ms chunks.
9. Browser plays them and reports progress.
10. Timings, transcript and any escalation are stored. Audio is not.

Interruptions: see `06_VOICE_PIPELINE.md`.
