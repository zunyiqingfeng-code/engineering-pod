# engineering-pod

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A reference implementation of a personal "engineering pod": submit a task from
anywhere, a server-side autonomous coding agent does the work while you're away,
and a deterministic gate keeps anything machine-shaped out of what you deliver.

This is a clean, desensitized reference — not a mirror of any live system. It
exists to show the architecture you can build for yourself, not to be deployed
as-is. Bring your own engine, your own server, your own secrets.

## The idea

You send one line ("model this, run the simulation, write the report") from a
phone or laptop. It lands on a server that runs an autonomous coding-agent CLI
(an OpenAI Codex-style tool) with your real toolchain installed. It works in the
background — you can be asleep. You come back to artifacts you review and ship.

The machine carries the execution. You carry the judgment. The three pieces
below are what make that division of labour safe enough to ship client work on.

## Three pillars

### 1. Multi-backend failover (`app/backends.py`)
A production line can't hang on one model. Backends are independent CLI commands;
the executor tries your preferred one, then transparently fails over to the next
when a line is rate-limited, flaky, or down. Adding your own engine is one entry
in a registry — no vendor endpoint or key is hardcoded.

### 2. Zero-AI-trace delivery gate (`app/delivery_lint.py`)
Nothing you hand a client may carry a machine fingerprint: model names, "generated
by AI" footers, filler sign-offs, personal attributions, stray emoji, or the author
field hidden in Office metadata. The gate is deterministic code, not a prompt —
it doesn't depend on the model remembering to behave. It runs after every task and
stands alone as a pre-delivery scanner. The list of personal names to block is
configuration (`POD_BLOCKED_NAMES`); this repo ships none.

### 3. Cron automation (`app/scheduler.py`)
Give a task a 5-field cron schedule and it fires on time with no one watching.
Long jobs run detached. The runner reconciles itself each cycle against the
enabled automations.

## Architecture

```
  phone / laptop / browser
            │  one prompt (HTTPS, bearer token)
            ▼
   ┌──────────────────┐
   │  FastAPI  (main) │  auth: fail-closed token + HMAC tickets
   ├──────────────────┤
   │  executor        │──► backend A ─┐  failover
   │   └─ delivery_lint│    backend B ─┤  (app/backends.py)
   │  scheduler (cron)│    custom    ─┘
   │  store (sqlite)  │
   └──────────────────┘
            │  artifacts in a per-task workspace
            ▼
     you review → deliver
```

See [docs/architecture.md](docs/architecture.md) for the request/auth flow.

## Quickstart

```bash
cd server
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env
# set POD_TOKEN (required) and point POD_PRIMARY_CMD at your agent CLI
export $(grep -v '^#' ../.env | xargs)          # or use a dotenv loader

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Submit a task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H "Authorization: Bearer $POD_TOKEN" -H "Content-Type: application/json" \
  -d '{"prompt":"write a hello world script and save it as hello.py"}'
```

Or open `client/console.html` in a browser, set the base URL + token, and watch
the run stream live.

## Configuration

All config is environment-only (see `.env.example`). No secrets or infrastructure
values live in the source.

| Variable | Meaning |
| --- | --- |
| `POD_TOKEN` | Bearer token guarding the API. Required — server fails closed without it. |
| `POD_BASE` | Data dir (sqlite, workspaces, artifacts). |
| `POD_TZ` | IANA timezone for cron. |
| `POD_DEFAULT_BACKEND` | Default backend id. |
| `POD_PRIMARY_CMD` / `POD_DEEPSEEK_CMD` / `POD_CUSTOM_CMD` | Backend CLI commands. |
| `POD_BLOCKED_NAMES` | Names the delivery gate must block (comma-separated). |

## Security model

- Fail closed: with no `POD_TOKEN`, the API rejects every request rather than
  running open.
- Constant-time comparison (`hmac.compare_digest`) for token and ticket checks.
- Short-lived HMAC tickets for endpoints that can only carry auth in a URL (SSE,
  downloads), so the long-lived token never enters a URL or a log.
- The delivery gate is a backstop, not a vibe: deterministic, file-by-file.

This is a learning-grade reference. Review it against your own threat model
before putting real work behind it.

## What is intentionally not here

This is a template, not someone's running machine. It ships no real server
address, no credentials, no vendor-specific or gray-market relay wiring, and no
production frontend. The in-process queue stands in for a real Redis/RQ setup.
Wire your own engine, infrastructure, and secrets via the environment.

## License

MIT — see [LICENSE](LICENSE).
