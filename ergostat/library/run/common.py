"""What the library's programs share: where their state is kept, the project's items, and how a line is said."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import time
from pathlib import Path

import yaml


def root() -> Path:
    return Path.cwd()


def state_dir() -> Path:
    """The project's state directory: given to blocks (``ERGOSTAT_STATE_DIR``); a sensor works it out the way the
    project does (its name and its folder), since it runs in the project's folder."""
    if os.environ.get("ERGOSTAT_STATE_DIR"):
        return Path(os.environ["ERGOSTAT_STATE_DIR"])
    from ...store import state_dir as sd
    main = root() / "ergostat.yaml"
    name = root().name
    try:
        data = yaml.safe_load(main.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict) and data.get("name"):
            name = str(data["name"])
    except (OSError, yaml.YAMLError):
        pass
    return sd(name, root())


def mine(instance: str) -> Path:
    d = state_dir() / "library" / instance
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextlib.contextmanager
def kept(instance: str, what: str):
    """A small JSON state, read and written back under a lock (a sensor and a block may share it)."""
    d = mine(instance)
    path = d / f"{what}.json"
    with open(d / f"{what}.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text()) if path.is_file() else {}
        except ValueError:
            data = {}
        yield data
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)


def say(obj: dict) -> None:
    print(json.dumps(obj, default=str), flush=True)


def note(text: str) -> None:
    """A line for the block's log (standard error), never read as an output."""
    print(text, file=sys.stderr, flush=True)


def project():
    """The project, opened from its folder: its compiled model and its record."""
    from ... import model as mdl
    from ...store import Project
    return Project(mdl.load(root()))


def items(p, kind: str, states: list[str] | None = None) -> list:
    from ...spec import items as its
    spec = p.model.spec
    if kind not in spec.items:
        raise SystemExit(f"no item kind {kind!r} in the model (kinds: {', '.join(k for k in spec.items if not k.startswith('ergostat.'))})")
    got = its.project(p.events, spec, kind)
    if states:
        got = [i for i in got if i.state in states]
    return sorted(got, key=lambda i: i.entered or i.first)


def block_input() -> dict:
    """What ergostat gave the block on standard input (empty when run by hand)."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        text = sys.stdin.read()
        return json.loads(text) if text.strip() else {}
    except ValueError:
        return {}


def now() -> float:
    return time.time()
