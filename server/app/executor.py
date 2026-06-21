"""Run a task on a backend, fail over when a line dies, then gate the output.

Flow:
  1. Resolve the failover order (preferred backend, then runnable fallbacks).
  2. Run each in turn: pipe the prompt in, stream stdout to the task log, in a
     per-task workspace directory. First clean exit wins; a missing binary or a
     non-zero exit falls through to the next line.
  3. Whatever landed in the workspace goes through the delivery gate
     (delivery_lint). A BLOCK finding means traces leaked — the task is marked
     `blocked` even though it "ran", because it is not deliverable.

The subprocess contract is intentionally generic: a backend is any CLI that
reads a prompt on stdin and works in cwd. Swap in your own agent CLI.
"""
import os
import subprocess
import threading

from . import settings, backends, store, delivery_lint


def _workspace(task_id):
    path = os.path.join(settings.WORK_DIR, task_id)
    os.makedirs(path, exist_ok=True)
    return path


def _run(task_id):
    task = store.get_task(task_id)
    if not task:
        return
    store.set_status(task_id, "running")
    order = backends.failover_order(task["backend"])
    if not order:
        store.append_event(task_id, "no runnable backend configured")
        store.set_status(task_id, "failed")
        return

    workdir = _workspace(task_id)
    ran_clean = False
    for bid in order:
        store.append_event(task_id, f"[backend:{bid}] starting")
        try:
            proc = subprocess.Popen(
                backends.BACKENDS[bid]["command"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, cwd=workdir,
                env=backends.build_env(bid), text=True,
            )
        except FileNotFoundError:
            store.append_event(task_id, f"[backend:{bid}] binary not found, failing over")
            continue
        try:
            proc.stdin.write(task["prompt"])
            proc.stdin.close()
            for line in proc.stdout:
                store.append_event(task_id, line.rstrip("\n"))
            rc = proc.wait()
        except Exception as exc:  # noqa: BLE001 - report and fail over
            store.append_event(task_id, f"[backend:{bid}] error: {exc}, failing over")
            continue
        if rc == 0:
            ran_clean = True
            break
        store.append_event(task_id, f"[backend:{bid}] exited {rc}, failing over")

    findings = delivery_lint.run(workdir)
    store.set_lint(task_id, findings)
    blocks = [f for f in findings if f[0] == "BLOCK"]

    if ran_clean and not blocks:
        store.set_status(task_id, "done")
    elif ran_clean and blocks:
        store.append_event(task_id, f"delivery gate held back {len(blocks)} trace(s)")
        store.set_status(task_id, "blocked")
    else:
        store.set_status(task_id, "failed")
    store.append_event(task_id, "[[END]]")


def enqueue(task_id):
    threading.Thread(target=_run, args=(task_id,), daemon=True).start()
