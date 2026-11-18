"""The remote API's tokens, one per consumer (SPEC §4c): made by ``ergostat remote token NAME``, printed once, and
kept only as their SHA-256 in ``<state>/remote-tokens.json``. With none, the API is off."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

FILE = "remote-tokens.json"


def _path(state: Path) -> Path:
    return Path(state) / FILE


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load(state: Path) -> dict[str, dict]:
    try:
        got = json.loads(_path(state).read_text())
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(state: Path, tokens: dict) -> None:
    f = _path(state)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(tokens, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


def issue(state: Path, name: str) -> str:
    """A new token for ``name`` (replacing its old one): returned once, kept only as its hash."""
    import time
    token = "erg_" + secrets.token_urlsafe(32)
    tokens = load(state)
    tokens[name] = {"sha256": _hash(token), "made": time.time()}
    _save(state, tokens)
    return token


def revoke(state: Path, name: str) -> bool:
    tokens = load(state)
    if name not in tokens:
        return False
    del tokens[name]
    _save(state, tokens)
    return True


def who(state: Path, token: str | None) -> str | None:
    """The consumer a presented token belongs to, or None; compared in constant time."""
    if not token:
        return None
    h = _hash(token)
    for name, row in load(state).items():
        if isinstance(row, dict) and hmac.compare_digest(str(row.get("sha256") or ""), h):
            return name
    return None
