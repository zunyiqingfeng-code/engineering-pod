"""Configuration, read entirely from environment / .env.

No secrets or real infrastructure values live in source. Copy .env.example to
.env and fill it in. See README "Configuration".
"""
import os

# Base data dir: sqlite db, task workspaces, delivered artifacts.
BASE = os.environ.get("POD_BASE", os.path.join(os.getcwd(), "pod-data"))
DB_PATH = os.path.join(BASE, "pod.db")
WORK_DIR = os.path.join(BASE, "workspaces")
ARTIFACT_DIR = os.path.join(BASE, "artifacts")

# Bearer token guarding the API. Empty => the server fails closed (refuses to
# start), so an unconfigured deployment is never left open. See auth.py.
TOKEN = os.environ.get("POD_TOKEN", "")

TZ = os.environ.get("POD_TZ", "UTC")

# Default backend id (must exist in backends.BACKENDS).
DEFAULT_BACKEND = os.environ.get("POD_DEFAULT_BACKEND", "primary")

# Names the delivery gate must never let leak into a deliverable (your real
# name, etc.). Comma-separated. Empty by default — set it in your own .env,
# do NOT hardcode a name here.
BLOCKED_NAMES = [n.strip() for n in os.environ.get("POD_BLOCKED_NAMES", "").split(",") if n.strip()]
