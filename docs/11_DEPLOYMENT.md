# Deployment

## A. Local setup on Windows, macOS or Linux

Needs Python 3.12 and Bun or Node.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/fetch_models.py --profile cpu
cd frontend && bun install && bun run build && cd ..
cp .env.example .env
```

On macOS and Linux use `.venv/bin/python`. On Linux and macOS the catalogue has a Windows llama-server, so build or download llama-server for your system, and set `VAP_LLM_BASE_URL` to it with `VAP_LLM_MANAGE_PROCESS=false`.

Open `.env` and set your own owner Email ID and password. Then:

```bash
.venv/Scripts/python scripts/serve.py
```

Open http://localhost:8000. The first start seeds 16 agents and takes up to a minute. A local address may use the microphone without HTTPS.

After a change to agent files or sample knowledge, delete `data/` to seed again. This also removes conversations and users, so never do it on a live system.

## B. Public link from your own computer, for free

The microphone needs HTTPS. A Cloudflare quick tunnel gives HTTPS without an account.

1. Download cloudflared from https://github.com/cloudflare/cloudflared/releases into `models/runtime/`.
2. Start the tunnel, and read the `trycloudflare.com` address it prints:

```bash
models/runtime/cloudflared.exe tunnel --url http://localhost:8000
```

3. Put these in `.env` and start the server:

```
VAP_ENVIRONMENT=production
VAP_TRUST_PROXY=true
VAP_PUBLIC_ORIGIN=https://the-address-it-printed.trycloudflare.com
```

| Limit | Detail |
| --- | --- |
| Uptime | Only while the computer is on and both programs run |
| Address | Changes on every tunnel start |
| Callers | 2 at a time on the test laptop |
| Promise | None from Cloudflare. Quick tunnels are meant for testing |

## C. Always on

| Option | Cost | Notes |
| --- | --- | --- |
| Own always-on computer with a named Cloudflare tunnel | Free tunnel, your electricity and a domain | Stable address. Needs a Cloudflare account and a domain |
| Hugging Face Spaces | Free tier | Docs say 16 GB, 2 CPUs, sleeps when idle. Forum reports show new accounts may get no quota. Two CPUs would be slow. WebSocket support not confirmed. **Not tested** |
| A rented server | Paid | Needs at least the profile A hardware. Paid, so it is your choice |

The product needs 3 GB of free memory and 8 or more logical cores to answer in about 2 seconds, so most free hosting will be slow even when it works.

## D. Docker

```bash
python scripts/fetch_models.py --profile cpu
cp .env.example .env
docker compose up --build
```

Add HTTPS with Caddy on a server with a real domain:

```bash
DOMAIN=voice.example.com docker compose --profile https up -d
```

Add monitoring:

```bash
GRAFANA_PASSWORD=your-own-password docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

**Docker builds were not tested.** Docker Desktop would not start on the test laptop, so these files have only had a configuration check. Expect to fix small problems on first use.

## E. A server without Docker, with nginx

`infrastructure/nginx/voice-agent.conf` proxies HTTPS and WebSocket traffic to port 8000. Keep the long socket timeouts, or calls will drop. Run the server under systemd or a similar service manager.

## Environment settings

`.env.example` lists all of them.
