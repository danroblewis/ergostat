"""Triage (SPEC §12r): a failed run kept as ``ergostat.run.failed`` about ``ergostat.failure/<block>-<signature>``, and
opened for repair only when its block runs a program of the project's and the code may be to blame; a run that ended
well but printed a traceback through the project's code kept as ``ergostat.run.swallowed``, which moves nothing."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
from pathlib import Path

from ..spec import runrecord
from . import BLOCKS, FAILURE, traces

TAIL = 8000
NOT_THE_CODE = ("stopped", "killed", "could not start", "signal")    # how a run ended that a change to its code is not for
OTHER = ("node", "java", "go")              # signed by how they ended until triage read their traces (superseded)


def clip(text: str) -> str:
    """The tail of a run's output from its last ``TAIL + 1`` characters: the last ``TAIL``, the first partial line
    dropped when they do not begin at the run's start (so no trace's header is there in part)."""
    if len(text) <= TAIL:
        return text
    return text[-TAIL:] if text[-TAIL - 1] == "\n" else text[-TAIL:].partition("\n")[2]


def scrub(p, text: str) -> str:
    """Secrets and the owner's denylist out (reports' rules, SPEC §12m); the model's names and paths kept."""
    from ..reports.scrub import Scrubber, denylist
    s = Scrubber(deny=denylist(getattr(p, "dir", None)))
    s._rules = [r for r in s._rules if r[0] in ("denylist", "secret")]
    return s.scrub(text)


def traceback_of(text: str, root: Path) -> dict | None:
    """The last traceback, of any language read (``traces.last``)."""
    return traces.last(text, root)


def signature(block: str, program: str | None, tb: dict | None, how: str = "") -> str:
    return hashlib.sha1(repr((block, program, tb["type"], tb["file"], tb["function"]) if tb else
                             (block, program, how)).encode()).hexdigest()[:8]


def current(p, spec, fid: str):
    """The failure as the record has it now; read only while ``held``."""
    from ..spec.items import one
    return one(p.events, spec, fid)


@contextlib.contextmanager
def held(p):
    """``repair/capture.lock``: held across each read of a failure, what is decided from it, and its write."""
    keep = Path(p.dir) / "repair"
    keep.mkdir(exist_ok=True)
    with open(keep / "capture.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        yield keep


def program_of(spec, b) -> str | None:
    """The project's file the block runs: the first word of its command that is a file under the model's folder."""
    root = spec.root.resolve()
    for w in str(b.params.get("run") or "").split():
        f = (spec.root / w).resolve()
        if not w.startswith("-") and f.is_file() and f.is_relative_to(root):
            return str(f.relative_to(root))
    return None


def guarded(p, b, cause: str | None) -> bool:
    """The repair loop's own runs, and runs a failure's events caused (a few steps up the cause chain), are never kept."""
    if b.name in BLOCKS:
        return True
    for _ in range(6):
        e = p.events.get(cause) if cause else None
        if e is None:
            return False
        if str(e.get("item") or "").startswith(FAILURE + "/") or e.get("source") in BLOCKS:
            return True
        cause = e.get("causedby")
    return False


def _fields(p, b, begun, data, name, sig, program, tb, stderr) -> dict:
    """What a failure keeps of a run: the fields the fixer and the impact report read."""
    if tb:
        tb["message"] = scrub(p, tb["message"])
    note = str(data.get("note") or "")
    return {"block": b.name, "run": begun["id"], "signature": sig, "program": program, "exit": data.get("exit"),
            "note": note, "error": f"{tb['type']}: {tb['message']}" if tb else note, "traceback": tb,
            "stderr": scrub(p, stderr[-TAIL:]), **({"log": data["log"]} if data.get("log") else {}),
            "input": f"file:repair/{name}.input", "model": data.get("model"), "item": data.get("item"),
            "read_only": b.params.get("read-only") is True, "count": 1, "first_seen": begun["time"],
            "began": begun["time"]}


def _row(type_: str, fid: str, begun: dict, data: dict) -> dict:
    return {"type": type_, "item": fid, "source": "ergostat", "causedby": begun["id"], "data": data}


def failed(p, spec, b, begun: dict, data: dict, stdin: str, stderr: str) -> dict | None:
    """Record the failed run on its failure, opened when it may be repaired; None when it is the loop's own.
    ``stderr``: the tail of the run's own log file (``data["log"]``), never the block's log, so no other run's lines;
    a daemon's run has only what it handed back that was not an event, usually nothing (SPEC §12r).
    Whether ``opened`` moves the failure is the fold's (``ItemKind.moves_from``), at the event's place in the record;
    what is decided here from a read (whether it is new, ``began``, which old failure it supersedes) is under ``held``."""
    if guarded(p, b, begun.get("causedby")):
        return None
    tb = traces.last(stderr, spec.root)
    program = program_of(spec, b) if b.type in ("program", "ai") else None
    code, note = data.get("exit"), str(data.get("note") or "")
    how = "signal" if runrecord.by_signal(code) else note.split(":")[0].split(" after")[0] or f"exited {code}"
    sig = signature(b.name, program, tb, how)
    name = f"{b.name}-{sig}"
    fid = f"{FAILURE}/{name}"
    d = _fields(p, b, begun, data, name, sig, program, tb, stderr)
    opens = program is not None and not how.startswith(NOT_THE_CODE)
    with held(p) as keep:
        (keep / f"{name}.input").write_text(scrub(p, stdin), encoding="utf-8")   # the latest input that failed
        it = current(p, spec, fid)
        if it is not None and it.state != "applied":
            d.pop("began")                                   # (when this run of failures began: the impact report's)
        rows = [_row("ergostat.run.failed", fid, begun, d)]
        if opens:
            rows.append(_row(f"{FAILURE}.opened", fid, begun, {"reopened": it is not None}))
        if tb and tb.get("language") in OTHER:               # its old item, signed by how it ended, if the same bug
            old = f"{FAILURE}/{b.name}-{signature(b.name, program, None, how)}"
            was = current(p, spec, old)
            again = was is not None and traces.last(str(was.fields.get("stderr") or ""), spec.root)
            if again and was.state not in ("superseded", "dismissed") and signature(b.name, program, again) == sig:
                rows.append(_row(f"{FAILURE}.superseded", old, begun, {"by": fid}))
        p.events.add_many(rows, new=True)
    return rows[0]


def swallowed(p, spec, b, begun: dict, tail: str, stdin: str = "") -> dict | None:
    """A run that ended well whose output's last trace goes through the project's code: ``ergostat.run.swallowed``
    about the failure that trace signs. A new one arrives ``noted`` with a failure's fields and is never opened; an
    existing one gets counts only, so no failure is moved, unleased or given another's traceback (SPEC §12r)."""
    if guarded(p, b, begun.get("causedby")):
        return None
    program = program_of(spec, b) if b.type in ("program", "ai") else None
    tb = traces.last(tail, spec.root) if program else None
    if not tb or not any(f["project"] for f in tb["frames"]):
        return None
    sig = signature(b.name, program, tb)
    name = f"{b.name}-{sig}"
    fid = f"{FAILURE}/{name}"
    with held(p) as keep:
        if current(p, spec, fid) is None:
            (keep / f"{name}.input").write_text(scrub(p, stdin), encoding="utf-8")
            d = {**_fields(p, b, begun, {"exit": 0}, name, sig, program, tb, tail), "count": 0, "swallowed": 1}
        else:
            d = {"swallowed": 1, "last_swallowed": begun["id"]}
        row = _row("ergostat.run.swallowed", fid, begun, d)
        p.events.add_many([row], new=True)
    return row
