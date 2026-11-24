"""Feature flags: work that lands switched off (docs/DEVELOPMENT.md, Feature flags).

A flag is declared in ergostat/flags.json, ``{"NAME": {"on": false, "about": "what it gates"}}``; the code it gates
asks ``on("NAME")`` and the tests of that code carry ``@pytest.mark.flag("NAME")``, which skips them while the flag
is off (tests/conftest.py; unit tests only: on a test that drives a browser the marker stops the run). Declared
off is the default; the file ships empty, so nothing is gated. Turning a flag on (its ``on`` made true, or the
declaration of an off flag removed) is a change of its own: turned_on() names it, and the checks then run in full
(scripts/affected_tests.py: the whole unit suite; the merge queue: the browser files whatever its paths).

``ERGOSTAT_FLAGS=a,b`` turns the named declared flags on for one process (a test run of the flagged path, or the
build of the branch that declares them); it never declares one. An undeclared name raises UnknownFlag, so a typo is
never read as off or on; a declarations file that cannot be read or parsed reads every flag as off."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

FILE = Path(__file__).with_name("flags.json")
REL = "ergostat/flags.json"                            # FILE, as git names it in the repository
ENV = "ERGOSTAT_FLAGS"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class UnknownFlag(KeyError):
    """A flag asked for that flags.json does not declare."""


def parse(text: str) -> dict[str, bool]:
    """{name: on} from the declarations' text; ValueError saying what, for anything but the allowed form."""
    try:
        got = json.loads(text)
    except ValueError as e:
        raise ValueError(f"flags: not JSON: {e}") from None
    if not isinstance(got, dict):
        raise ValueError("flags: not an object of NAME: {on, about}")
    out = {}
    for name, d in got.items():
        if not NAME.match(name):
            raise ValueError(f"flags: bad name {name!r} (lower-case letters, digits and '-', at most 64)")
        if not isinstance(d, dict) or set(d) != {"on", "about"} or not isinstance(d["on"], bool) \
                or not isinstance(d["about"], str) or not d["about"].strip():
            raise ValueError(f"flags: {name} is not {{\"on\": true|false, \"about\": \"what it gates\"}}")
        out[name] = d["on"]
    return out


def asked() -> set[str]:
    """The names ERGOSTAT_FLAGS turns on for this process."""
    return {n.strip() for n in os.environ.get(ENV, "").split(",") if n.strip()}


def on(name: str, path: Path | None = None) -> bool:
    """Whether the declared flag ``name`` is on: declared on, or named in ERGOSTAT_FLAGS. Undeclared: UnknownFlag.
    A declarations file that cannot be read or parsed: off (the flagged path stays unreachable)."""
    try:
        flags = parse((path or FILE).read_text())
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    if name not in flags:
        raise UnknownFlag(name)
    return flags[name] or name in asked()


def turned_on(before: str | None, after: str | None) -> list[str]:
    """What a change from the declarations ``before`` to ``after`` (each its text, None: no file) turns on, each said
    as a reason: a flag on after and not on before, and an off flag whose declaration is gone (its guard with it, as a
    rule). An ``after`` that does not parse is a reason in itself (the worst case); a ``before`` that does not parse
    counts as no flag declared."""
    try:
        old = parse(before) if before is not None else {}
    except ValueError:
        old = {}
    try:
        new = parse(after) if after is not None else {}
    except ValueError as e:
        return [f"{REL} unreadable after the change ({e})"]
    return [f"flag {n} turned on" for n in sorted(new) if new[n] and old.get(n) is not True] + \
        [f"flag {n} removed while off" for n in sorted(old) if not old[n] and n not in new]


def at(repo: Path | str, rev: str) -> str | None:
    """flags.json's text at ``rev`` in ``repo`` (None: the tree has no such file). OSError when git cannot say."""
    try:
        ls = subprocess.run(["git", "-C", str(repo), "ls-tree", "--name-only", rev, "--", REL],
                            capture_output=True, text=True, timeout=60)
        if ls.returncode != 0:
            raise OSError(f"git ls-tree {rev}: {ls.stderr.strip()[:200]}")
        if not ls.stdout.strip():
            return None
        got = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{REL}"], capture_output=True, text=True,
                             timeout=60)
    except subprocess.TimeoutExpired as e:
        raise OSError(f"git timed out: {e}") from None
    if got.returncode != 0:
        raise OSError(f"git show {rev}:{REL}: {got.stderr.strip()[:200]}")
    return got.stdout


def turned_on_between(repo: Path | str, old: str, new: str = "HEAD") -> list[str]:
    """turned_on() from ``old`` to ``new`` in ``repo``; git unable to say is a reason (the worst case: run in full)."""
    try:
        return turned_on(at(repo, old), at(repo, new))
    except OSError as e:
        return [f"{REL} not read ({e})"]


def added_between(repo: Path | str, old: str, new: str = "HEAD") -> list[str]:
    """The flags ``new`` declares that ``old`` does not (the branch's own new flags); [] when either cannot be read."""
    try:
        before, after = at(repo, old), at(repo, new)
        old_names = set(parse(before)) if before is not None else set()
        return sorted(set(parse(after)) - old_names) if after is not None else []
    except (OSError, ValueError):
        return []
