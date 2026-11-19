"""Taking a changed model while ergostat runs (SPEC §9.1), safe while someone, or an agent, is still editing it.

- **Settled** (``Settled``): a change is taken only once the model's files have stayed the same for ``SETTLE``
  seconds (``ERGOSTAT_RELOAD_SETTLE``, 1.5 by default): a burst of writes is one change, and a file read half
  written (truncated, then completed) is never taken.
- **Checked** (``load_checked``): a model that does not load, has errors, or whose main file is empty is never
  taken. The last good one keeps running, and what is wrong is written to ``<state>/reload.json`` (``write_state``),
  where ``ergostat status``, the page's header and the log say it, until the files are fixed.
- **Once** for the same files: files refused are not read again until they change.

The run (``cli/running.py``) and the page (``web/server.py``, ``Live``) each follow the model this way."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import model as mdl

SETTLE = float(os.environ.get("ERGOSTAT_RELOAD_SETTLE") or 1.5)   # seconds the files must stay the same
SLOW = 2.0                   # a change that takes longer than this to take is logged with where the time went
STATE = "reload.json"


class Settled:
    """A model's files followed: ``due()`` is the stamp of files that changed and have since stayed the same for
    ``settle`` seconds, once; None otherwise. ``took(model, stamp)`` and ``refused(stamp)`` say what became of it."""

    def __init__(self, model, settle: float | None = None):
        self.model = model
        self.settle = SETTLE if settle is None else settle
        self.taken = mdl.stamp(model)                  # the files as last taken (or refused)
        self.seen = self.taken                          # the files as last seen, and since when
        self.since = time.monotonic()

    def due(self):
        now = mdl.stamp(self.model)
        if now != self.seen:
            self.seen, self.since = now, time.monotonic()
        if now == self.taken:
            return None
        if time.monotonic() - self.since < self.settle and self.quiet() < self.settle:
            return None
        return now

    def quiet(self) -> float:
        """Seconds since the model's files, or the folders holding them, were last written."""
        files = list(getattr(self.model, "files", None) or ([self.model.path] if self.model.path else []))
        newest = 0.0
        for f in files + list({Path(f).parent for f in files}):
            try:
                newest = max(newest, os.stat(f).st_mtime)
            except OSError:
                return 0.0                                  # (one gone: being replaced, as an editor saves)
        return time.time() - newest

    def took(self, model, stamp=None) -> None:
        """``model`` taken, read from the files as they were at ``stamp``: changed again while it was read, it is
        read again once they settle."""
        before, self.model = self.model, model
        self.taken = self.seen = mdl.stamp(model)
        if stamp is not None and mdl.stamp(before) != stamp:
            self.taken = None

    def refused(self, stamp) -> None:
        self.taken = stamp


def load_checked(model) -> tuple[object | None, list[str]]:
    """The model at ``model``'s place, read again: (the model, []) when it may run, else (None, its errors, each
    ``file:line: what``)."""
    root = model.path.parent if model.path else Path.cwd()
    main = model.path
    try:
        if main is not None and main.exists() and not main.read_text(encoding="utf-8").strip():
            return None, [f"{main.name}:1: the file is empty"]
    except OSError as e:
        return None, [f"{main.name}: {e}"]
    try:
        fresh = mdl.load(root)
    except mdl.ModelError as e:
        lines = [x.strip() for x in str(e).splitlines()[1:] if x.strip()] or [str(e)]
        return None, lines
    except Exception as e:                              # (a file vanished between two reads, a duration...)
        return None, [f"{mdl.file_name(model)}: {type(e).__name__}: {e}"]
    errors = [msg for lv, msg in mdl.check(fresh, warnings=False) if lv == "error"]
    return (None, errors) if errors else (fresh, [])


def where(errors: list[str]) -> str:
    """``file:line`` of the first error, as the banner says it."""
    m = re.match(r"([^\s:]+(?::\d+)?)", errors[0]) if errors else None
    return m.group(1) if m else "the model"


def banner(errors: list[str]) -> str:
    n = len(errors)
    more = f", and {n - 1} more" if n > 1 else ""
    return f"the edited model has errors ({where(errors)}{more}); still running the last good version"


def write_state(state_dir: Path, errors: list[str] | None, version: str | None = None) -> None:
    """What the last change to the files came to: its errors (the last good version still running), or none."""
    path = Path(state_dir) / STATE
    try:
        if not errors:
            path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"errors": errors, "since": time.time(), "running": version,
                                   "banner": banner(errors)}))
        os.replace(tmp, path)
    except OSError:
        pass


def read_state(state_dir: Path) -> dict | None:
    try:
        got = json.loads((Path(state_dir) / STATE).read_text())
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("errors") else None
