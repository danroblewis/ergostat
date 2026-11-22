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
    p = Project(m, d, note=False)                # read only: another project's note is its own to write
    snap = st.snapshot(p)
    g = st.goals_off(snap, names=True)
    files = list(getattr(m, "files", None) or ([m.path] if m.path else []))
    return {"name": m.name, "repo": note["repo"], "running": bool(pid), "web": web_url(p) if pid else None,
            "loops": len(snap["loops"]), "off": sorted(g["system"] + g["open"]), "unknown": g["unknown"],
            "upkeep_off": sorted(n for v in g["own"].values() for n in v),
            "goals_off": g["system"],            # the header's first figure: the system's goals off, upkeep apart
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


def orphans() -> list[dict]:
    """The folders under the home whose ``repo.json`` names a repository that is gone (its parent folder is there and
    it is not: a drive or share not mounted is not gone), and no engine runs in: each with that repository and its
    size. Only these are ever deleted (``ergostat compact --projects --yes``); a folder without a readable
    ``repo.json``, or a symlink, is never among them."""
    from .runner import running_pid
    out = []
    for f in sorted(home().glob("*/repo.json")):
        try:
            repo = Path(json.loads(f.read_text())["repo"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        d = f.parent
        if d.is_symlink() or repo.exists() or not repo.parent.is_dir() or running_pid(SimpleNamespace(dir=d), wait=False):
            continue
        size = sum(x.stat().st_size for x in d.rglob("*") if x.is_file() and not x.is_symlink())
        out.append({"dir": str(d), "repo": str(repo), "bytes": size})
    return out


def forget(found: list[dict]) -> list[str]:
    """Each folder ``orphans`` found deleted, when it is still one (checked again): the folders that are gone."""
    import shutil
    again = {x["dir"] for x in orphans()}
    gone = []
    for x in found:
        d = Path(x["dir"])
        if x["dir"] in again and not d.is_symlink() and d.parent.resolve() == home().resolve():
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                gone.append(x["dir"])
    return gone


def state_of(main: Path) -> Path | None:
    """The state folder of the repository whose main file is ``main``, found without loading the model: by the name the
    file says, else by the ``repo.json`` that names the repository."""
    import json

    from .calls.client import state_of as by_name
    root = main.parent.resolve()
    d = by_name(root)
    if d is not None:
        return d
    for note in home().glob("*/repo.json"):
        try:
            if Path(json.loads(note.read_text())["repo"]).resolve() == root:
                return note.parent
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None
