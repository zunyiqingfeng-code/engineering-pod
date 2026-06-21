# Deployment boundaries

This repo is a reference shape, not a hardened hosted service. Treat deployment
as three separate boundaries: local demo, private server, and public internet.

## Local demo

Use this when you only want to test the API and console on one machine.

```bash
cd server
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example ../.env
# fill POD_TOKEN and backend commands
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `client/console.html`, set:

```text
base URL: http://127.0.0.1:8000
token:    POD_TOKEN from .env
```

This mode is for development only. It is not reachable from another device
unless you add networking around it.

## Private server

Use this when the goal is remote work from a phone or laptop.

Recommended shape:

```text
phone / laptop
  -> private network or VPN
  -> reverse proxy with TLS
  -> engineering-pod API on 127.0.0.1
  -> task workspaces under POD_BASE
```

Minimum rules:

- bind the app to localhost behind the reverse proxy;
- keep `POD_TOKEN` out of URLs and logs;
- use the ticket endpoint for SSE or download links;
- put `POD_BASE` on a disk with enough space for long jobs;
- run the backend commands as a low-privilege user;
- back up only the files you actually need, not every transient workspace.

## Public internet

Do not expose this reference app directly to the public internet.

Before public exposure, add at least:

- a real account system or single sign-on;
- rate limits;
- request size limits;
- per-task CPU, memory, and wall-time limits;
- worker isolation;
- audit logs;
- encrypted secret storage;
- a real job queue instead of the in-process thread runner.

The current implementation is deliberately small so the architecture is easy to
read. Production hardening should be explicit, not implied.

## Backend commands

Each backend is just a CLI command that reads the task prompt from stdin and
writes artifacts into the current working directory. That keeps the pod
independent of any one engine.

Example:

```text
POD_PRIMARY_CMD=my-agent --mode work
POD_CUSTOM_CMD=python ./tools/run_job.py
```

The server does not ship real credentials, real hosts, or a live engine config.
Keep those in your own environment or secret store.
