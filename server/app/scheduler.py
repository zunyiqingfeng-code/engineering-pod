"""Cron-driven automation runner.

Give a task a 5-field cron schedule and a backend; a background scheduler fires
it on time, with no one watching the terminal. Long jobs run detached the same
way. This reconciles itself: every cycle it diffs the enabled automations
against live jobs and adds/updates/removes accordingly.
"""
import time
import uuid
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import settings, store, executor

TZ = ZoneInfo(settings.TZ)
LOG = logging.getLogger("pod.scheduler")


def _trigger(schedule):
    return CronTrigger.from_crontab(schedule, timezone=TZ)


def _next_ts(trigger):
    nxt = trigger.get_next_fire_time(None, datetime.now(TZ))
    return nxt.timestamp() if nxt else None


class AutomationRunner:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=TZ)
        self.fingerprints = {}

    def run_job(self, automation_id):
        item = store.get_automation(automation_id)
        if not item or not item.get("enabled"):
            return
        task_id = "tk_" + uuid.uuid4().hex[:12]
        store.create_task(task_id, item["prompt"], item["backend"])
        executor.enqueue(task_id)
        store.update_automation(automation_id, last_run_at=time.time())

    def reload(self):
        current = {}
        for item in store.list_automations():
            if not item.get("enabled"):
                continue
            try:
                trigger = _trigger(item["schedule"])
            except Exception:
                LOG.warning("invalid schedule for %s: %s", item["id"], item["schedule"])
                continue
            fp = (item["schedule"], item["prompt"], item["backend"])
            current[item["id"]] = fp
            if self.fingerprints.get(item["id"]) != fp:
                self.scheduler.add_job(self.run_job, trigger=trigger, id=item["id"],
                                       args=[item["id"]], replace_existing=True,
                                       max_instances=1, coalesce=True)
            store.update_automation(item["id"], next_run_at=_next_ts(trigger))
        for job_id in list(self.fingerprints):
            if job_id not in current and self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
        self.fingerprints = current

    def start_background(self):
        self.scheduler.start()

        def loop():
            while True:
                try:
                    self.reload()
                except Exception:
                    LOG.exception("reload failed")
                time.sleep(30)

        import threading
        threading.Thread(target=loop, daemon=True).start()
