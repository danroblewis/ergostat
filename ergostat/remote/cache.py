"""A remote's model kept in the state folder (SPEC §4c): ``<state>/remotes/NAME/model.json`` (what it served, with
its version) and ``status.json`` (when it was last asked, whether it answered, why not, when to ask again). The
model file is one of the model's files: when a refresh writes a new version, the model reloads. Asking again is
conditional (``If-None-Match``), so an unchanged model costs a 304; a remote that fails is asked less often, twice
the period after each failure up to ten periods."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import client

MODEL, STATUS = "model.json", "status.json"
BACKOFF_MOST = 10
TIMEOUT = 3.0


def folder(project: str, root: Path, remote: str) -> Path:
    from ..store import state_dir
    d = state_dir(project, root) / "remotes" / remote
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(f: Path) -> dict | None:
    try:
        got = json.loads(f.read_text())
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def _write(f: Path, data: dict) -> None:
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, sort_keys=True))
    tmp.replace(f)


def model(d: Path) -> dict | None:
    return _read(d / MODEL)


def status(d: Path) -> dict:
    return _read(d / STATUS) or {}


def refresh(d: Path, url: str, token_file: str | None, root: Path, every: float, force: bool = False,
            timeout: float = TIMEOUT) -> dict:
    """Ask the remote for its model when it is time (or ``force``), and keep what it said: the status after."""
    now = time.time()
    st = status(d)
    if not force and now < float(st.get("next") or 0):
        return st
    have = model(d)
    token, why = client.token_of(token_file, root)
    if token is None:
        code, body, why_ = 0, None, why
    else:
        code, body, _, why_ = client.get(url, "model", token, etag=(have or {}).get("version"), timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("version"):
        if not have or have.get("version") != body["version"]:
            _write(d / MODEL, {**body, "fetched": now, "url": url})
        new = {"checked": now, "ok": True, "why": "", "version": body["version"], "fails": 0, "next": now + every,
               "answered": now, "failing_since": None}
    elif code == 304 and have:
        new = {"checked": now, "ok": True, "why": "", "version": have.get("version"), "fails": 0, "next": now + every,
               "answered": now, "failing_since": None}
    else:
        fails = int(st.get("fails") or 0) + 1
        new = {"checked": now, "ok": False, "why": why_ or f"{code}: no model in the answer", "fails": fails,
               "failing_since": st.get("failing_since") if not st.get("ok", True) and st.get("failing_since") else now,
               "next": now + every * min(BACKOFF_MOST, 2 ** (fails - 1))}
    st = {**status(d), **new}                      # (what readings noted meanwhile is kept)
    _write(d / STATUS, st)
    return st


def note(d: Path, ok: bool, why: str = "", version: str | None = None) -> None:
    """What a reading learnt of the remote (it answered, or not), kept beside the model's status, so the page says how
    old its readings are without asking again."""
    st = status(d)
    now = time.time()
    if ok:
        st.update(read=now, read_ok=True, read_why="", **({"seen_version": version} if version else {}))
    else:
        st.update(read_ok=False, read_why=why, read_failing_since=st.get("read_failing_since") if st.get("read_ok") is False
                  else now)
    _write(d / STATUS, st)
