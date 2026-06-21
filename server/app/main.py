"""FastAPI wiring: submit a task, stream it, schedule it.

Endpoints (all but /healthz require auth):
  POST   /tasks                 submit a prompt -> runs server-side, returns id
  GET    /tasks/{id}            status + delivery-gate findings
  GET    /tasks/{id}/events     SSE stream of the run (ticket auth)
  GET    /auth/ticket           mint a short-lived ticket for SSE/download URLs
  GET    /automations           list cron automations
  POST   /automations           create one (5-field cron + backend)
  DELETE /automations/{id}      remove one
  GET    /healthz               liveness + which backends are runnable
"""
import json
import time
import uuid

from fastapi import FastAPI, Depends, Body, HTTPException
from fastapi.responses import StreamingResponse

from . import settings, store, backends, executor
from .auth import auth, make_ticket
from .scheduler import AutomationRunner

app = FastAPI(title="engineering-pod (reference implementation)")
_runner = AutomationRunner()


@app.on_event("startup")
def _startup():
    store.init_db()
    _runner.start_background()


@app.get("/healthz")
def healthz():
    return {"ok": True, "backends": [b for b in backends.BACKENDS if backends.is_runnable(b)]}


@app.get("/auth/ticket", dependencies=[Depends(auth)])
def auth_ticket():
    ticket, exp = make_ticket()
    return {"ticket": ticket, "expires_at": exp}


@app.post("/tasks", dependencies=[Depends(auth)])
def submit_task(body: dict = Body(...)):
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    backend = body.get("backend") or settings.DEFAULT_BACKEND
    if backend not in backends.BACKENDS:
        raise HTTPException(400, f"unknown backend: {backend}")
    task_id = "tk_" + uuid.uuid4().hex[:12]
    store.create_task(task_id, prompt, backend)
    executor.enqueue(task_id)
    return {"id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}", dependencies=[Depends(auth)])
def get_task(task_id: str):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(404, "not found")
    task["lint"] = json.loads(task["lint"]) if task.get("lint") else []
    return task


@app.get("/tasks/{task_id}/events")
def task_events(task_id: str, _=Depends(auth)):
    if not store.get_task(task_id):
        raise HTTPException(404, "not found")

    def gen():
        seq, idle = 0, 0
        while True:
            rows = store.events_after(task_id, seq)
            for s, text in rows:
                seq = s
                if text == "[[END]]":
                    yield "event: end\ndata: done\n\n"
                    return
                yield f"data: {text}\n\n"
            if rows:
                idle = 0
            else:
                idle += 1
                if idle > 600:  # ~5 min idle -> close
                    return
                time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _validate_cron(schedule):
    if len(str(schedule or "").strip().split()) != 5:
        raise HTTPException(400, "schedule must be a 5-field cron expression")
    return str(schedule).strip()


@app.get("/automations", dependencies=[Depends(auth)])
def list_automations():
    return store.list_automations()


@app.post("/automations", dependencies=[Depends(auth)])
def create_automation(body: dict = Body(...)):
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    backend = body.get("backend") or settings.DEFAULT_BACKEND
    if backend not in backends.BACKENDS:
        raise HTTPException(400, f"unknown backend: {backend}")
    aid = "au_" + uuid.uuid4().hex[:12]
    store.create_automation({
        "id": aid, "title": body.get("title") or "automation",
        "prompt": prompt, "backend": backend,
        "schedule": _validate_cron(body.get("schedule")), "enabled": 1,
    })
    _runner.reload()
    return {"id": aid}


@app.delete("/automations/{aid}", dependencies=[Depends(auth)])
def delete_automation(aid: str):
    store.delete_automation(aid)
    _runner.reload()
    return {"ok": True}
