# Troubleshooting

## Starting

| Problem | Fix |
| --- | --- |
| `Model file not found` | Run `python scripts/fetch_models.py --profile cpu` |
| Language model refuses to load: not enough memory | Close other apps. On a busy 16 GB laptop set `VAP_LLM_ALLOW_LOW_MEMORY=true` |
| Blank page | Build the page: `cd frontend && bun run build` |
| Port 8000 in use | Set `VAP_PORT`, or stop the other program |
| Log In fails on the first day | The owner comes from `.env` on first start only. Change it there and delete `data/`, if nothing is stored yet |
| Cannot use a new agent file | Agent files load once. Add it in the Agents page, or delete `data/` on a test system |

## Microphone

| Problem | Fix |
| --- | --- |
| "Microphone access is blocked" | Select the lock icon in the address bar and allow the microphone |
| "This page needs HTTPS" | Use `localhost` or an HTTPS link |
| "No microphone was found" | Plug one in, or use text mode |
| Agent stops talking by itself | Its voice is reaching the microphone. Use headphones, or lower the volume |
| Words not heard | Move nearer to the microphone. A noisy room hurts accuracy |

## Conversation

| Problem | Fix |
| --- | --- |
| "All our lines are busy" | Every place is taken. Wait, or raise `VAP_MAX_SESSIONS` if the machine can cope |
| Slow first reply | Other apps are using memory or CPU |
| "I do not have this information" often | The document lacks the answer, or the wording differs. Test in Knowledge search |
| Hindi or Bengali text looks wrong in logs | Your terminal needs UTF-8. Set `PYTHONIOENCODING=utf8` |
| Reply stops at once | Noise counted as an interruption. Lower the volume or use headphones |

## Public link

| Problem | Fix |
| --- | --- |
| The link stopped working | The tunnel stopped, or its address changed. Start it again and update `VAP_PUBLIC_ORIGIN` |
| Page opens, call fails | `VAP_PUBLIC_ORIGIN` does not match the link. Restart after changing it |
| All callers look like one person | Set `VAP_TRUST_PROXY=true` |

## Tests

| Problem | Fix |
| --- | --- |
| Live tests fail at once | They need the server running |
| Browser test says 429 | The request limit is working. The test waits between passes for this reason |
| `No module named playwright` | `pip install playwright`, then `python -m playwright install chromium` |

## Docker

Docker builds have not been tested. On Windows, if Docker Desktop will not start, check that virtualisation is on and WSL 2 works.
