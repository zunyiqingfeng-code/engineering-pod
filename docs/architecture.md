# Architecture

A small, honest map of how a prompt becomes a reviewed deliverable.

## Request / auth flow

```
client                      FastAPI (app/main.py)            executor / scheduler
  │                                │                                  │
  │ POST /tasks  (Bearer token)    │                                  │
  ├───────────────────────────────►│ auth() — fail closed if no token │
  │                                │ store.create_task()              │
  │                                │ executor.enqueue() ──────────────►│ run in a thread
  │ ◄────────── { id }             │                                  │
  │                                │                                  │ try backend A
  │ GET /auth/ticket               │                                  │  → fail over to B
  │ ◄────────── { ticket }         │   HMAC, short-lived              │  → custom slot
  │                                │                                  │
  │ GET /tasks/{id}/events?ticket= │                                  │ stream stdout
  ├───────────────────────────────►│ SSE: replay store events ◄───────┤ store.append_event()
  │ ◄═══════════ live log ═════════│                                  │
  │                                │                                  │ delivery_lint.run()
  │ GET /tasks/{id}                │                                  │ store.set_status()
  │ ◄───── status + lint findings  │                                  │
```

The bearer token authenticates normal requests. Endpoints that can only carry
auth in the URL — Server-Sent Events, file downloads — take a short-lived
HMAC-signed ticket instead, so the long-lived token never lands in a URL or a
server log. Both checks use constant-time comparison.

## Why a delivery gate, not a prompt

A model can be told "don't leave traces" and still leave them — it forgets on a
long task, or paraphrases its way around the instruction. The gate
(`app/delivery_lint.py`) is deterministic code that runs *after* the work, over
the actual files. A `BLOCK` finding marks a task `blocked` even though it ran:
it produced output, but the output is not deliverable. That distinction —
"ran" vs "deliverable" — is the whole point.

## Failover, concretely

`app/backends.py` holds a registry of backends, each a CLI command. The executor
asks for a failover order (preferred first, then every other runnable backend),
and walks it: a missing binary or a non-zero exit drops to the next line, a clean
exit wins. Which backend leads is a human decision (cost vs. difficulty), set per
task; the failover itself is automatic.

## From reference to production

This implementation keeps everything in one process so it runs with nothing but
Python. A real deployment typically swaps:

- the in-process thread queue for Redis + a job queue (workers, retries, backpressure),
- sqlite for a managed database,
- the single host for a reverse proxy terminating TLS in front of the API,
- the `console.html` demo for a real desktop/mobile client over the same API.

None of those change the shape above — they harden it.
