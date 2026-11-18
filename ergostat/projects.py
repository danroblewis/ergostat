"""Every project on this machine that ergostat has seen: its record's folder in the home holds
``repo.json`` (the repository's path). Read only."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from .store import home

# A project's row is worked out again when its model's files or whether it runs change, and
# otherwise when it is older than this: each one is a model loaded (a second or so) and a snapshot
# of its record, and the page's header asks for the list while it is open.
RUNNING_FRESH = 60.0
STOPPED_FRESH = 600.0
_ROWS: dict = {}                 # state folder: (key, row, files, when)
_ONE_AT_A_TIME = threading.Lock()


def _times(files) -> tuple:
    out = []
    for f in files:
        try:
            out.append(f.stat().st_mtime_ns)
        except OSError:
            out.append(None)
    return tuple(out)


def _row(d: Path, note: dict, pid: int | None) -> tuple[dict, list]:
    from . import model as mdl
    from . import state as st
    from .runner import web_url
    from .store import Project
    try:
        m = mdl.load(Path(note["repo"]))
    except Exception as e:                       # a repository moved or its model broken: say so, don't stop
        return {"name": d.name, "repo": None, "error": f"{type(e).__name__}: {e}"}, []
    p = Project(m, d)
    snap = st.snapshot(p)
    loops = {n: lp["status"] for n, lp in snap["loops"].items()}
    files = list(getattr(m, "files", None) or ([m.path] if m.path else []))
    return {"name": m.name, "repo": note["repo"], "running": bool(pid), "web": web_url(p) if pid else None,
            "loops": len(loops), "off": sorted(n for n, s in loops.items() if s in ("off", "open")),
            "unknown": sorted(n for n, s in loops.items() if s == "unknown"),
            "attention": len([a for a in st.attention(snap, bool(pid), m) if a["level"] != "hint"])}, files


def known(fresh: bool = False) -> list[dict]:
    """Each project: name, repository, whether it runs, its page, and its loops' statuses. Rows are
    kept between calls (see ``RUNNING_FRESH``); ``fresh`` works every one out again."""
    from .runner import running_pid
    with _ONE_AT_A_TIME:                         # however many ask at once, the work is done once
        out, now, seen = [], time.monotonic(), set()
        for f in sorted(home().glob("*/repo.json")):
            d = f.parent
            seen.add(d)
            try:
                text = f.read_text()
                note = json.loads(text)
            except (OSError, ValueError) as e:
                out.append({"name": d.name, "repo": None, "error": f"{type(e).__name__}: {e}"})
                continue
            pid = running_pid(SimpleNamespace(dir=d), wait=False)
            was = _ROWS.get(d)
            key = (text, pid, _times(was[2]) if was else None)
            if not fresh and was and was[0] == key and now - was[3] < (RUNNING_FRESH if pid else STOPPED_FRESH):
                out.append(was[1])
                continue
            row, files = _row(d, note, pid)
            _ROWS[d] = ((text, pid, _times(files)), row, files, now)
            out.append(row)
        for d in [x for x in _ROWS if x not in seen]:      # forgotten (ergostat reset): let go of it
            del _ROWS[d]
        return out
