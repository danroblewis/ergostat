"""The last good model, for the command line while the YAML is broken (SPEC §9.1). The engine keeps the model it
takes whole, as one snapshot of every file its loading read (``spec/files.py``): each file's bytes stored once by
their hash in ``<state>/good/objects/``, and ``good/manifest.json`` naming them. A command that only reads loads that
snapshot alone, read-only, never running anything; a command that acts refuses, naming the YAML's errors."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

DIR, MANIFEST, OBJECTS = "good", "manifest.json", "objects"
READS = {None, "status", "item", "event", "lease", "loop", "system", "explain", "findings", "residual", "fit", "claims",
         "messages", "agent", "block", "inbox", "stock", "flow", "valve", "sensor", "controller", "disturbance"}
ACTS = ("add", "redrive", "renew", "nack", "check", "about", "reopen", "now", "done", "approve", "deny", "stop",
        "restart", "check_warm", "opened", "read", "forget_above", "forget_below", "decided", "requests", "invest", "reset",
        "revoke")
# a topic that mostly acts, with subcommands (its ``what``) that only read: only those run on the last good model
READ_WHAT = {"remote": ("proposals",)}
# the read topics' other flags, each one that only reads (tests/test_cli_fallback.py holds every flag to one list or
# the other); what decides is the record, which the fallback opens refusing every write
READ_FLAGS = ("n", "kind", "state", "history", "type", "item", "source", "follow", "runs", "data", "patch", "set_", "by",
              "to", "why", "after", "no_count", "all", "around", "depth", "list", "wiring", "blocks", "open", "note",
              "command", "stats", "search")
WRITES = ("add", "add_many", "prune", "replace", "forget", "roll", "drop", "flush")


class ReadOnlyRecord(Exception):
    """A command on the last good model tried to write to the record."""


class _ReadOnly:
    """A store that answers reads and refuses every write (the fallback's events and measurements)."""

    def __init__(self, store):
        self._store = store

    def __getattr__(self, name):
        if name in WRITES:
            raise ReadOnlyRecord(f"{name}: the record is read-only while the model is the last good one")
        return getattr(self._store, name)


def reads(args) -> bool:
    """Whether this command only reads: a topic that reads (or one of ``READ_WHAT``'s subcommands), with none of its
    acting flags."""
    topic = getattr(args, "topic", None)
    return (topic in READS or getattr(args, "what", None) in READ_WHAT.get(topic, ())) and \
        not any(getattr(args, a, None) not in (None, False) for a in ACTS)


def _load(kept: dict, fetch):
    from . import model as mdl
    from .spec import files
    with files.replay(kept, fetch):
        return mdl.load_main(Path(kept["main"]))


def keep(project) -> str | None:
    """The model ``project`` runs, kept as its snapshot when it reads back from that alone; else why not (the snapshot
    before stays)."""
    m = project.model
    r = getattr(m, "reads", None)
    if r is None or r.replay:
        return None
    blobs = {hashlib.sha256(b).hexdigest(): b for b in r.files.values() if b is not None}
    kept = {"main": str(m.path.resolve()), "taken": time.time(), "dirs": r.dirs, "globs": r.globs,
            "library": os.environ.get("ERGOSTAT_LIBRARY") or "",
            "files": {p: (hashlib.sha256(b).hexdigest() if b is not None else None) for p, b in r.files.items()}}
    try:
        _load(kept, blobs.get)
    except Exception as e:                                # (a read noted wrong: never kept to fail later)
        return f"{type(e).__name__}: {e}"
    good = project.dir / DIR
    try:
        (good / OBJECTS).mkdir(parents=True, exist_ok=True)
        for h, b in blobs.items():
            if not (good / OBJECTS / h).is_file():
                tmp = good / OBJECTS / f"{h}.{os.getpid()}.tmp"
                tmp.write_bytes(b)
                os.replace(tmp, good / OBJECTS / h)
        try:                                            # the snapshot before: its objects kept one generation more,
            was = set(json.loads((good / MANIFEST).read_text())["files"].values())   # for a command reading it now
        except (OSError, ValueError, KeyError, AttributeError):
            was = set()
        tmp = good / f"{MANIFEST}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(kept))
        os.replace(tmp, good / MANIFEST)
        for f in [*good.iterdir(), *(good / OBJECTS).iterdir()]:   # only what keep writes: objects, and its .tmp files
            if len(f.name) == 64 and f.name not in blobs and f.name not in was or \
                    f.name.endswith(".tmp") and time.time() - f.stat().st_mtime > 3600:
                f.unlink(missing_ok=True)
    except OSError as e:
        return f"{good}: {e}"
    return None


def fallback(here: Path, err: Exception):
    """A Project on the last good model of the repository at or above ``here``, said in one line on standard error;
    None when none is kept or it does not read back whole."""
    from . import model as mdl
    from .projects import state_of
    from .store import Project
    main = mdl.find(here)
    d = state_of(main) if main is not None else None
    if d is None or not (d / DIR / MANIFEST).is_file():
        return None
    objects = d / DIR / OBJECTS

    def fetch(h: str) -> bytes | None:
        try:
            return (objects / h).read_bytes()
        except OSError:
            return None
    kept: dict = {}
    try:
        kept = json.loads((d / DIR / MANIFEST).read_text())
        if Path(kept["main"]) != main.resolve():
            return None
        m = _load(kept, fetch)
    except Exception as e:
        lib = os.environ.get("ERGOSTAT_LIBRARY") or ""
        note = f"; ERGOSTAT_LIBRARY is {lib!r} here, {kept.get('library', '')!r} when it was kept" \
            if kept and lib != kept.get("library", "") else ""
        print(f"ergostat: the last good model could not be read back ({e}{note})", file=sys.stderr)
        return None
    lines = [x.strip() for x in str(err).splitlines()[1:] if x.strip()] or [str(err)]
    more = f", and {len(lines) - 1} more" if len(lines) > 1 else ""
    when = time.strftime("%H:%M", time.localtime(kept["taken"]))
    print(f"ergostat: {main.name} has errors ({lines[0]}{more}); using the last good model, taken {when} "
          f"(ergostat check shows them)", file=sys.stderr)
    p = Project(m, d, note=False)
    p.events, p.measurements = _ReadOnly(p.events), _ReadOnly(p.measurements)
    return p
