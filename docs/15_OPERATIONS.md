# Operations

## Daily

| Task | Where |
| --- | --- |
| See health | System page, or `GET /api/ready` |
| See escalations | Escalations page. Check it often, because a person must act on each one |
| See speed | Latency page |
| See who changed what | Audit Log page |
| Add knowledge | Knowledge page. Test with its search box |
| Test an agent | Agents page, Test button |

## Monitoring

`/metrics` gives Prometheus data, from this machine only. With Docker, `docker-compose.monitoring.yml` starts Prometheus and Grafana with a ready dashboard: live conversations, turns per minute, refused calls, stage timings, queue depth, escalations and interruptions.

## Back-up

The whole state is in `data/platform.db`. The database uses WAL mode, so use SQLite's own back-up rather than copying the file while the server runs:

```bash
sqlite3 data/platform.db ".backup data/backup.db"
```

Models can be downloaded again, so they need no back-up. `.env` must be kept safe.

## Update

1. Back up.
2. Pull the new code.
3. Install packages, then rebuild the page.
4. Restart. New files in `backend/migrations/` run on start.
5. Open `/api/ready`, and make a test call.

## Change a model

Add it to `models/manifests/catalogue.json`, fetch it, then measure it before use: `benchmarks/stt_candidates.py`, `tts_candidates.py` or `llm_candidates.py`. Do not change a default on feel alone, because the Hindi and Bengali results here show how far a good reputation can mislead.

## Limits to change

| Setting | Effect |
| --- | --- |
| `VAP_MAX_SESSIONS` | Callers at one time. 0 means the hardware plan |
| `VAP_MIN_FREE_RAM_GB` | Refuse new work under this |
| `VAP_LLM_MAX_TOKENS` | Longest reply |
| `VAP_RATE_LIMIT_PER_MINUTE` | Requests per address |

## Retention

Set transcript days on the System page. Clean-up removes old transcripts. Audio is never stored.

## Incidents

| Sign | First step |
| --- | --- |
| `/api/ready` shows `llm: false` | Look at `data/llama-server.log` |
| Callers refused | Look at free memory and live sessions on the System page |
| Very slow replies | Look at the Latency page to see which stage grew. Close other apps |
| Wrong answers | Find the conversation, test the same question in Knowledge search, then fix the document |
| A wrong safety reply | Treat it as serious. Add a test to the agent, and fix the guard before going on |

Also see `TROUBLESHOOTING.md`.
