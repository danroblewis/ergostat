"""Where a sensor's ``run:`` runs (SPEC §2a, *Untrusted libraries*): on the owner's shell only when compile proved it the
owner's or ergostat's (``verdict``, an allowlist); every other run only through ``ergostat.sandbox``, with no hosts, no
environment, only its template's folder readable, a work folder of its own, at most ``CEILING`` seconds and at most
``MOST`` at once. No sandbox here: it does not run."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

from ..spec.load import Where
from .expand import SECTION_OF, Via

OWNER, SANDBOX = "owner", "sandbox"
CEILING = 120.0         # seconds: the longest a sandboxed run may take, whatever the model says
MOST = 4                # sandboxed runs at once, of the whole process
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
UNKNOWN = "0-unknown"   # the work folder of a run whose instance can't be told (no instance's name starts with a digit)
_LOCK = threading.Lock()
_held = [0]


def verdict(uses, where, of, name: str) -> str:
    """OWNER for a run in the model's own files, a trusted chain's, or one R1, R2 passed (trust.owner_runs); SANDBOX
    for anything else: no ``where``, another kind of it, a missing use, or a check that raises (lesson-3)."""
    try:
        if type(where) is Where:
            return OWNER
        if type(where) is not Via:
            return SANDBOX
        u = (uses or {}).get(where.instance)
        if not isinstance(u, dict):
            return SANDBOX
        if u.get("untrusted") is False:
            return OWNER
        return OWNER if f"{SECTION_OF[of.kind]}.{of.name}.{name}" in (u.get("owner_runs") or ()) else SANDBOX
    except Exception:   # noqa: BLE001
        return SANDBOX


def sandboxed(s) -> bool:
    return bool(s.run) and s.run_in != OWNER


def _room() -> bool:
    return _held[0] < MOST


class Slot:
    keep = False        # set when the run escaped: its slot is never given back


@contextmanager
def _slot():
    """A slot, or None when ``MOST`` are taken: checked and taken under one lock (lesson-1)."""
    with _LOCK:
        got = Slot() if _room() else None
        if got is not None:
            _held[0] += 1
    try:
        yield got
    finally:
        if got is not None and not got.keep:
            with _LOCK:
                _held[0] -= 1


def _digest(path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (OSError, TypeError, ValueError):
        return "unreadable"


def chain(uses, inst: str) -> list:
    """The instance and every one above it: its template, the file and the file's digest."""
    out, at = [], inst
    while at is not None and len(out) < 16 and at not in [x[0] for x in out]:
        u = (uses or {}).get(at)
        u = u if isinstance(u, dict) else {}
        out.append([at, u.get("template"), u.get("path"), _digest(u.get("path"))])
        at = u.get("above")
    return out


def work_folder(uses, state, inst: str) -> Path:
    """``<state>/library-work/<inst>``, emptied when the chain of templates that made the instance changed. The marker
    saying which chain made it is kept beside the folder, never in it, where the run could forge it."""
    if not NAME.fullmatch(inst):
        raise ValueError(f"not a work folder's name: {inst!r}")
    root = Path(state) / "library-work"
    work, marker = root / inst, root / f"{inst}.made"
    want = json.dumps(chain(uses, inst))
    root.mkdir(parents=True, exist_ok=True)
    try:
        had = marker.read_text()
    except OSError:
        had = None
    if had != want:
        if work.is_symlink() or work.is_file():
            work.unlink()
        elif work.exists():
            shutil.rmtree(work)
        marker.write_text(want)
    work.mkdir(exist_ok=True)
    return work


def read(spec, s, state) -> tuple[str | None, str]:
    """Run a sensor's ``run:`` sandboxed: its output, or None and why not (nothing ran, or it failed)."""
    from .. import sandbox
    inst = getattr(s.where, "instance", None) if type(s.where) is Via else None
    u = (spec.uses or {}).get(inst) if inst else None
    folder = Path(u["path"]).parent if isinstance(u, dict) and u.get("path") else None
    try:
        work = work_folder(spec.uses, state, inst if inst and NAME.fullmatch(inst) else UNKNOWN)
    except (OSError, ValueError) as e:
        return None, f"not run: its sandbox's work folder: {e}"
    policy = sandbox.Policy(work=work, read=[str(folder)] if folder else [], hosts={}, env={})
    try:
        timeout = float(s.timeout) if 0 < float(s.timeout) <= CEILING else CEILING
    except (TypeError, ValueError):
        timeout = CEILING
    with _slot() as slot:
        if slot is None:
            return None, f"not run: {MOST} sandboxed runs are already under way"
        try:
            r = sandbox.run(["/bin/sh", "-c", s.run], policy, timeout=timeout, cwd=work)
        except sandbox.Unavailable as e:
            return None, f"not run: {e}"
        slot.keep = bool(r.escaped)
    if r.timed_out:
        return None, f"no answer within {timeout:g}s (sandboxed)"
    if r.exit != 0:
        return None, f"exited {r.exit} (sandboxed): {(r.stderr or r.stdout).strip()[:200]}"
    return r.stdout, ""
