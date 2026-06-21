"""Multi-backend registry + failover ordering.

Each backend is just a CLI command that takes a prompt on stdin and drives an
autonomous coding/engineering agent (an OpenAI Codex-style CLI, for example).
The point of having several is fault tolerance: when one line is rate-limited,
flaky, or down, the executor transparently falls back to the next.

How to add your own engine: copy the "custom" entry, point `command` at your
CLI, set `provider`, and inject any per-backend env. Nothing here hardcodes a
specific vendor endpoint or key — those come from the environment.
"""
import os

# command is read from env so the repo ships no machine-specific binary names.
BACKENDS = {
    "primary": {
        "label": "Primary (OpenAI-compatible)",
        "command": [os.environ.get("POD_PRIMARY_CMD", "codex-primary")],
        "provider": "openai",
        "env": {},
    },
    "deepseek": {
        "label": "DeepSeek",
        "command": [os.environ.get("POD_DEEPSEEK_CMD", "codex-deepseek")],
        "provider": "deepseek",
        "env": {},
    },
    # Template slot — wire your own line here. Left disabled by default.
    "custom": {
        "label": "Custom backend (example)",
        "command": [os.environ.get("POD_CUSTOM_CMD", "")],
        "provider": "custom",
        "env": {},
    },
}


def is_runnable(backend_id):
    cfg = BACKENDS.get(backend_id)
    return bool(cfg and cfg["command"] and cfg["command"][0])


def failover_order(preferred):
    """Preferred backend first, then the other runnable ones as fallbacks."""
    order = []
    if is_runnable(preferred):
        order.append(preferred)
    for bid in BACKENDS:
        if bid != preferred and is_runnable(bid):
            order.append(bid)
    return order


def build_env(backend_id):
    """Process env for a backend run. Per-backend secrets are injected from the
    environment / your own secret store, never from this file."""
    cfg = BACKENDS[backend_id]
    env = dict(os.environ)
    env.update(cfg.get("env", {}))
    return env
