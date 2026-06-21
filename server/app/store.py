"""Minimal SQLite store for tasks, their streamed output, and automations.

Production uses Redis + a real queue; this in-process version keeps the
reference implementation self-contained and runnable with nothing but Python.
"""
import os
import json
import time
import sqlite3
import threading

from . import settings

_lock = threading.Lock()


def _conn():
    os.makedirs(settings.BASE, exist_ok=True)
    c = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks(
              id TEXT PRIMARY KEY, prompt TEXT, backend TEXT, status TEXT,
              lint TEXT, created_at REAL);
            CREATE TABLE IF NOT EXISTS task_events(
              task_id TEXT, seq INTEGER, text TEXT);
            CREATE TABLE IF NOT EXISTS automations(
              id TEXT PRIMARY KEY, title TEXT, prompt TEXT, backend TEXT,
              schedule TEXT, enabled INTEGER, created_at REAL,
              last_run_at REAL, next_run_at REAL);
            """
        )


# --- tasks ---

def create_task(task_id, prompt, backend):
    with _lock, _conn() as c:
        c.execute("INSERT INTO tasks(id,prompt,backend,status,lint,created_at) VALUES(?,?,?,?,?,?)",
                  (task_id, prompt, backend, "queued", None, time.time()))


def get_task(task_id):
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def set_status(task_id, status):
    with _lock, _conn() as c:
        c.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))


def set_lint(task_id, findings):
    payload = json.dumps([{"severity": s, "kind": k, "file": p, "line": ln, "match": m}
                          for s, k, p, ln, m in findings], ensure_ascii=False)
    with _lock, _conn() as c:
        c.execute("UPDATE tasks SET lint=? WHERE id=?", (payload, task_id))


def append_event(task_id, text):
    with _lock, _conn() as c:
        seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=?",
                        (task_id,)).fetchone()[0]
        c.execute("INSERT INTO task_events(task_id,seq,text) VALUES(?,?,?)", (task_id, seq, text))


def events_after(task_id, after_seq):
    with _lock, _conn() as c:
        rows = c.execute("SELECT seq,text FROM task_events WHERE task_id=? AND seq>? ORDER BY seq",
                         (task_id, after_seq)).fetchall()
        return [(r["seq"], r["text"]) for r in rows]


# --- automations ---

def create_automation(a):
    with _lock, _conn() as c:
        c.execute("""INSERT INTO automations(id,title,prompt,backend,schedule,enabled,created_at)
                     VALUES(?,?,?,?,?,?,?)""",
                  (a["id"], a["title"], a["prompt"], a["backend"], a["schedule"],
                   int(a.get("enabled", 1)), time.time()))


def list_automations():
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM automations").fetchall()]


def get_automation(aid):
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM automations WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None


def update_automation(aid, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE automations SET {cols} WHERE id=?", (*fields.values(), aid))


def delete_automation(aid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM automations WHERE id=?", (aid,))
