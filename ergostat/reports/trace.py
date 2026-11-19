"""An exception, as a report shows it: its traceback with ergostat's and Python's frames kept (their code is public),
every other frame reduced to where it was, and its message left to the scrubber; and its stack signature, the same
for the same bug wherever and however often it happens."""

from __future__ import annotations

import hashlib
import traceback
from pathlib import Path

from .scrub import PACKAGE_ROOT, Piece, original_rel, path_rule, python_rel

PACKAGE = PACKAGE_ROOT / "ergostat"


def _ours(filename: str) -> str | None:
    """A frame's file as the report says it, when it is public: ``ergostat/...`` or ``python3.N/...``."""
    try:
        if Path(filename).resolve().is_relative_to(PACKAGE):
            return original_rel(str(Path(filename).resolve()))
    except (OSError, ValueError):
        pass
    if path_rule(filename) == "python-path":
        return python_rel(filename)
    return None


PUBLIC_MODULES = ("builtins", "ergostat", "sqlite3", "json", "yaml", "re", "subprocess", "urllib", "http", "socket", "os",
                  "concurrent", "asyncio", "threading", "queue", "shlex", "tomllib")


def pieces(exc: BaseException) -> list[Piece]:
    """The traceback, most recent call last, causes first, as pieces: (text, kept as it is)."""
    out: list[Piece] = []
    chain: list[BaseException] = []
    e: BaseException | None = exc
    while e is not None and len(chain) < 5 and e not in chain:
        chain.append(e)
        e = e.__cause__ or (e.__context__ if not e.__suppress_context__ else None)
    for i, x in enumerate(reversed(chain)):
        if i:
            out.append(("\nThe above exception led to the following:\n\n", True))
        out.append(("Traceback (most recent call last):\n", True))
        for f in traceback.extract_tb(x.__traceback__):
            mine = _ours(f.filename)
            if mine is not None:
                out.append((f'  File "{mine}", line {f.lineno}, in {f.name}\n', True))
                if f.line:
                    out.append((f"    {f.line.strip()}\n", True))
            else:
                out += [('  File "', True), (f.filename, False), (f'", line {f.lineno}, in ', True), (f.name, False), ("\n", True)]
        t = type(x)
        out.append((t.__qualname__, t.__module__.split(".")[0] in PUBLIC_MODULES))
        out += [(": ", True), (str(x), False), ("\n", True)]
    return out


def signature(exc: BaseException) -> str:
    """The exception's type and the frames in ergostat (file and function, not line: a line moves with any edit); the
    whole stack's files and functions when none is ergostat's."""
    frames = traceback.extract_tb(exc.__traceback__)
    mine = [(original_rel(str(Path(f.filename).resolve())), f.name) for f in frames
            if _ours(f.filename) and _ours(f.filename).startswith("ergostat/")]
    if not mine:
        mine = [(Path(f.filename).name, f.name) for f in frames]
    key = repr((type(exc).__module__, type(exc).__qualname__, mine))
    return hashlib.sha1(key.encode()).hexdigest()


def where(exc: BaseException) -> str:
    """The innermost frame in ergostat, for a title: ``spec/engine.py in _evaluate``."""
    for f in reversed(traceback.extract_tb(exc.__traceback__)):
        mine = _ours(f.filename)
        if mine and mine.startswith("ergostat/"):
            return f"{mine.removeprefix('ergostat/')} in {f.name}"
    return "outside ergostat's own code"
