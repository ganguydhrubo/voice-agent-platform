# Test report

Run on 4 November 2026 on the final code, on the laptop described in `13_PERFORMANCE.md`.

## Summary

| Suite | Tool | Result |
| --- | --- | --- |
| Python unit and integration | pytest | **109 passed**, 0 failed |
| Page unit tests | Vitest | **19 passed**, 0 failed |
| Lint | ruff | Clean |
| Type check | tsc | Clean |
| Agent evaluation, all 16 agents, real model | `tests/live/run_evaluations.py` | **55 of 55** |
| Retrieval, 3 languages | `tests/benchmarks/rag_eval.py` | **22 of 22** top result |
| Browser journey, real Chromium, 3 languages | `tests/e2e/journey.py` | **3 of 3**, zero console errors |
| Every page, 4 widths, light and dark | `tests/e2e/admin.py` | **16 pages, 8 passes**, zero faults |
| Interruption over a real socket | `tests/live/voice_check.py barge` | Pass |
| Third caller when full | `tests/live/capacity_check.py` | Refused politely, then served |
| Docker Compose file check | `docker compose config` | Pass, both files |

## Coverage against the brief

| Area | How it is tested | Limit |
| --- | --- | --- |
| Microphone | Chromium with a fake device playing recordings | **No real microphone or room** |
| Audio capture | Same run: AudioWorklet in a real browser | |
| Detector | `test_voice_logic.py`, `live_path_stt.py` | |
| Speech to text | 40 human clips per language, per candidate | Common Voice clips only |
| Text to speech | Round trip by recogniser | **No human listening** |
| Language model | Facts test and the 55 evaluations | |
| Streaming | Real socket, browser journey | |
| Interruptions | Real socket, browser journey, Vitest for stale frames | One recording |
| Context | Follow-ups in all journeys, `followup_check.py` | |
| Knowledge search | `rag_eval.py`, integration tests | One sample set |
| Three languages | All of the above | Spoken language detection not offered |
| Healthcare safety | `test_guards.py`, evaluations | Sample facts |
| Login and roles | `test_auth_and_roles.py` | |
| Tenant isolation | `test_knowledge_and_tenants.py` | |
| Network failure | `test_a_dropped_connection_can_resume_without_a_second_greeting` | Clean drop only. No slow or lossy network test |
| Callers at one time | 2 callers, 16 turns; third refused | Two callers only |
| Running out of resources | Admission tests, hardware plan tests | Memory pressure was not forced on purpose |
| Public link | Real test over the tunnel: see below | |
| Docker image build | **Not run** | Docker Desktop would not start |

## Real bugs these tests caught

| Bug | Found by | Fix |
| --- | --- | --- |
| Talk page crashed in new Chrome: `window.scrollTo` returned a Promise and React treated it as clean-up | Browser journey | Added braces |
| Human Hindi garbled on the live path: WER 0.315 against 0.105 for whole clips | `live_path_stt.py` | 300 ms padding |
| "Ignore your previous instructions" got through the injection check | `test_guards.py` | Wider pattern |
| Telephone number at the end of a sentence kept its last group as a number | `test_voice_logic.py` | Better pattern |
| Late audio frame could restart speech after an interruption | Code reading, then Vitest | `flushedTurn` guard |
| System page wider than the screen; words broke mid-word in tables | `tests/e2e/admin.py` and screenshots | CSS and better formatting |
| Random Hindi sentence received an unrelated answer | Human clip test | More stop words |
| `docker compose up` would have failed without a Grafana password | `docker compose config` | Monitoring in its own file |
| Off-topic questions were answered | Evaluations | Cut-off of 0.62 from measured data |

## Known defects still open

1. Two unanswerable test questions pass the retrieval cut-off. See `08_RAG.md`.
2. Bengali wording from the small model can be awkward.
3. Machine-voice test questions were misheard at times ("What are its tidings"). The answers were still right, but a real caller may not always be so lucky.
4. Password reset needs an admin to read the server console, as there is no email service.

## How to run

```bash
.venv/Scripts/python -m pytest tests/unit tests/integration -q
cd frontend && bun run test && cd ..
.venv/Scripts/python scripts/serve.py
```

With the server running, in another window:

```bash
python tests/live/run_evaluations.py
python tests/benchmarks/rag_eval.py
python tests/e2e/make_caller_audio.py
python tests/e2e/journey.py en hi bn
python tests/e2e/admin.py
python tests/live/capacity_check.py
```
