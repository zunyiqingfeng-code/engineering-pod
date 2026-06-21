"""API auth: bearer token + short-lived signed tickets.

Two hardening choices worth copying:
  * Fail closed. If POD_TOKEN is unset the API refuses every request instead of
    silently running open — an unconfigured deploy is never an exposed deploy.
  * Constant-time comparison everywhere (hmac.compare_digest), so the token and
    ticket checks don't leak length/prefix through timing.

Tickets are HMAC-signed, expiring strings handed to endpoints that can only
carry auth in the URL (SSE streams, file downloads), so the long-lived token
never lands in a URL or a log line.
"""
import time
import hmac
import hashlib

from fastapi import Header, Query, HTTPException

from . import settings


def _bearer_ok(authorization):
    if not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization[7:], settings.TOKEN)


def make_ticket(ttl=120):
    exp = str(int(time.time()) + int(ttl))
    sig = hmac.new(settings.TOKEN.encode(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}", int(exp)


def _ticket_ok(ticket):
    if not ticket or "." not in ticket:
        return False
    payload, _, sig = ticket.rpartition(".")
    try:
        if int(payload) < int(time.time()):
            return False
    except ValueError:
        return False
    expected = hmac.new(settings.TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def auth(authorization: str = Header(default=""),
         token: str = Query(default=""),
         ticket: str = Query(default="")):
    if not settings.TOKEN:
        # Fail closed: no token configured => server is not ready to serve.
        raise HTTPException(503, "server not configured: set POD_TOKEN")
    if _bearer_ok(authorization):
        return
    if token and hmac.compare_digest(token, settings.TOKEN):
        return
    if ticket and _ticket_ok(ticket):
        return
    raise HTTPException(401, "unauthorized")
