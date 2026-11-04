# Cost and capacity

## Cost

| Item | Cost |
| --- | --- |
| Software | ₹0. All open source |
| Models | ₹0 |
| Telephone or SIP | None needed |
| Speech, language or embedding API | None |
| Your hardware and electricity | Whatever you already pay |
| Public link by quick tunnel | ₹0 |
| Stable public address | Domain fee, and a server if you rent one |

No prices are given for rented servers, because they change and were not checked.

## Capacity: measured

On the test laptop, 10 cores and 16 threads, one LLM slot.

| Callers talking at one time | First audio p50 | First audio p95 | Note |
| --- | --- | --- | --- |
| 1 | 2,139 ms | 3,326 ms | 60 turns, with little free memory |
| 2 | 2,875 ms | 3,563 ms | 16 turns, each caller keeps talking with no pause. Harder than a real call |
| 3 | Refused | | Politely, with "All our lines are busy." |

## Capacity: calculated

**These are calculations, not measurements. Treat them as a plan to be tested.**

Assumptions:

1. One turn holds a language model slot for about 3 seconds. That is 0.85 s to the first token plus about 2 s for about 60 tokens at 32 tokens a second.
2. A caller takes one turn every 20 seconds: listening, thinking, speaking.
3. Keep a slot under 50% busy, or queues grow quickly.
4. One CPU slot uses 6 threads and about 1.2 GB.

So each CPU slot handles about 3 callers at a time (3 s ÷ 20 s = 15% each, and 50% ÷ 15% ≈ 3).

| Callers at one time | CPU slots | CPU threads | Memory | Machine | Work needed first |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 6, plus speech | 3 GB free | This laptop | None. Measured |
| 10 | 4 | About 30 | About 10 GB | One 32-thread server with 32 GB | Set `VAP_MAX_SESSIONS`, raise llama-server slots. Test it |
| 100 | 34 | About 240 | About 50 GB | About 8 such servers, or fewer with GPUs | **Not built:** shared database, shared sessions, a load balancer |
| 1,000 | 334 | About 2,400 | About 500 GB | GPUs make more sense. GPU speed not measured, so no number is given | Everything above, plus a queueing layer |
| 10,000 | 3,334 | About 24,000 | Terabytes | Not sensible on CPU, and this design has not been tested near it | A redesign. Not claimed |

## What breaks first, and when

| Point | Limit | Fix |
| --- | --- | --- |
| Language model | The first limit by far | More slots, GPU, or a smaller reply |
| Memory | About 2 callers on a busy 16 GB laptop | More memory |
| SQLite | One machine, one writer at a time | Move to PostgreSQL. Not built |
| WebSocket sessions | Tied to one process | Sticky routing and a shared store. Not built |
| Brute-force vector search | Thousands of chunks | A vector index. Not built |

## What is built to protect a busy server

1. `SessionManager` refuses new callers when places are full or free memory is low.
2. STT and TTS pools have a fixed size and a bounded queue.
3. The Prometheus gauges `vap_queue_depth`, `vap_active_sessions` and `vap_sessions_rejected_total` show pressure.
4. Under pressure, live words stop first and the session is marked degraded on the health page.

There is no claim of unlimited scale. On the tested hardware, this product is good for a demo, a small desk or a pilot.
