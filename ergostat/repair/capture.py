"""Triage (SPEC §12r): a failed run kept as ``ergostat.run.failed`` about ``ergostat.failure/<block>-<signature>``, and
opened for repair only when its block runs a program of the project's and the code may be to blame."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..spec import runrecord
from . import BLOCKS, FAILURE

TAIL = 8000
FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>.+)$')
LIBRARY = ("site-packages", "/lib/python", "<frozen", "<string>")
NOT_THE_CODE = ("stopped", "killed", "could not start", "signal")    # how a run ended that a change to its code is not for


def scrub(p, text: str) -> str:
    """Secrets and the owner's denylist out (reports' rules, SPEC §12m); the model's names and paths kept."""
    from ..reports.scrub import Scrubber, denylist
    s = Scrubber(deny=denylist(getattr(p, "dir", None)))
    s._rules = [r for r in s._rules if r[0] in ("denylist", "secret")]
    return s.scrub(text)


def traceback_of(text: str, root: Path) -> dict | None:
    """The last Python traceback: its exception's type and message, and its innermost frame in the project's code."""
    lines = text.splitlines()
    starts = [i for i, s in enumerate(lines) if s.startswith("Traceback (most recent call last)")]
    if not starts:
        return None
    frames, kind, msg = [], None, ""
    for s in lines[starts[-1] + 1:]:
        if m := FRAME.match(s):
            f = Path(m["file"]).resolve()
            f = str(f.relative_to(root.resolve())) if f.is_relative_to(root.resolve()) else m["file"]
            frames.insert(0, {"file": f, "line": int(m["line"]), "function": m["function"]})
        elif s.strip() and not s[:1].isspace():
            kind, _, msg = s.strip().partition(": ")
            break
    if not kind or not frames:
        return None
    return {"type": kind, "message": msg, **next((f for f in frames if not any(x in f["file"] for x in LIBRARY)),
                                                 frames[0])}


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


def failed(p, spec, b, begun: dict, data: dict, stdin: str, stderr: str) -> dict | None:
    """Record the failed run on its failure, opened when it may be repaired; None when it is the loop's own."""
    if guarded(p, b, begun.get("causedby")):
        return None
    from ..spec.items import one
    tb = traceback_of(stderr, spec.root)
    program = program_of(spec, b) if b.type in ("program", "ai") else None
    code, note = data.get("exit"), str(data.get("note") or "")
    how = "signal" if runrecord.by_signal(code) else note.split(":")[0].split(" after")[0] or f"exited {code}"
    sig = hashlib.sha1(repr((b.name, program, tb["type"], tb["file"], tb["function"]) if tb else
                            (b.name, program, how)).encode()).hexdigest()[:8]
    name = f"{b.name}-{sig}"
    fid = f"{FAILURE}/{name}"
    keep = Path(p.dir) / "repair"
    keep.mkdir(exist_ok=True)
    (keep / f"{name}.input").write_text(scrub(p, stdin), encoding="utf-8")   # the latest input that failed
    if tb:
        tb["message"] = scrub(p, tb["message"])
    d = {"block": b.name, "run": begun["id"], "signature": sig, "program": program, "exit": code, "note": note,
         "error": f"{tb['type']}: {tb['message']}" if tb else note, "traceback": tb,
         "stderr": scrub(p, stderr[-TAIL:]), "input": f"file:repair/{name}.input", "model": data.get("model"),
         "item": data.get("item"), "read_only": b.params.get("read-only") is True, "count": 1,
         "first_seen": begun["time"], "began": begun["time"]}
    it = one(p.events, spec, fid)
    if it is not None and it.state != "applied":
        d.pop("began")                                       # (when this run of failures began: the impact report's)
    opens = program is not None and not how.startswith(NOT_THE_CODE) and (it is None or it.state in ("noted", "applied"))
    rows = [{"type": "ergostat.run.failed", "item": fid, "source": "ergostat", "causedby": begun["id"], "data": d}]
    if opens:
        rows.append({"type": f"{FAILURE}.opened", "item": fid, "source": "ergostat", "causedby": begun["id"],
                     "data": {"reopened": it is not None}})
    p.events.add_many(rows, new=True)
    return rows[0]
