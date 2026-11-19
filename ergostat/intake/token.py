"""Who may push (``envelope``, ``hooks``): a request from this machine, or from an address ``intake: allow:`` names,
carrying the local token: ``<state>/intake.token``, made the first time it is asked for, readable by its owner only.

The token is carried in any of the ways a sender can: ``Authorization: Bearer TOKEN``, ``X-Ergostat-Token: TOKEN``,
``?token=TOKEN`` (a webhook that cannot set headers), or as the secret of an HMAC-SHA256 of the body, the way GitHub
(``X-Hub-Signature-256: sha256=HEX``; Jira's webhooks with a secret sign the same way) and PagerDuty
(``X-PagerDuty-Signature: v1=HEX[,v1=HEX]``) sign what they send."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
from pathlib import Path

NAME = "intake.token"


def path(state: Path) -> Path:
    return Path(state) / NAME


def token(state: Path) -> str:
    """The token, made (owner-only) when there is none yet."""
    f = path(state)
    try:
        got = f.read_text().strip()
        if got:
            return got
    except FileNotFoundError:
        pass
    new = secrets.token_urlsafe(32)
    try:
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:                                # another process made it first: theirs
        return f.read_text().strip()
    with os.fdopen(fd, "w") as w:
        w.write(new + "\n")
    return new


def _sig(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def carried(secret: str, headers, query: dict, body: bytes) -> bool:
    """Whether the request carries the token (in any of the ways above)."""
    def same(x: str | None) -> bool:
        return bool(x) and secrets.compare_digest(x.strip(), secret)
    auth = headers.get("Authorization") or ""
    if auth.lower().startswith("bearer ") and same(auth[7:]):
        return True
    if same(headers.get("X-Ergostat-Token")) or same((query.get("token") or [""])[0]):
        return True
    want = _sig(secret, body)
    for h in ("X-Hub-Signature-256", "X-Hub-Signature"):
        v = headers.get(h) or ""
        if v.startswith("sha256=") and secrets.compare_digest(v[7:].strip(), want):
            return True
    for part in (headers.get("X-PagerDuty-Signature") or "").split(","):
        part = part.strip()
        if part.startswith("v1=") and secrets.compare_digest(part[3:], want):
            return True
    return False


def allowed(address: str, allow: list[str]) -> bool:
    """Whether a push may come from this address: this machine always, else a network ``intake: allow:`` names."""
    try:
        a = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if a.is_loopback or (getattr(a, "ipv4_mapped", None) and a.ipv4_mapped.is_loopback):
        return True
    for net in allow:
        try:
            if a in ipaddress.ip_network(net, strict=False):
                return True
        except ValueError:
            continue
    return False
