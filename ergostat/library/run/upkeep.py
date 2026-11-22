"""``use: upkeep``'s programs (SPEC §2a, *Upkeep*): ``upkeep tidy --keep N``, the index tidier, a block on the rule
rung. It works from the state directory alone (``common.state_dir``): it never opens the project, its model or an
index, only takes each index file's lock without waiting, and leaves to ``spec/itemindex._tidy`` whether a delete is
safe (no process holds the file, none changed it within ``TIDY_AGE``, checked again under the lock).

It prints one line per flow it moves: ``{"out": "flow.index-files-tidied", "moved": LIVE, "left": ..., "held": ...,
"young": ...}`` (the live files removed) and ``{"out": "flow.retired-index-files-removed", "moved": RETIRED}``."""

from __future__ import annotations

import argparse
import sys

from ...spec import itemindex
from . import common


def tidy(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="upkeep tidy")
    ap.add_argument("--keep", type=int, required=True)
    a = ap.parse_args(argv)
    if not 1 <= a.keep <= itemindex.MOST_FILES:
        print(f"upkeep tidy: --keep is 1 to {itemindex.MOST_FILES} (not {a.keep})", file=sys.stderr)
        return 2
    d = common.state_dir() / "items"
    try:
        if not d.is_dir():
            raise FileNotFoundError(f"no folder {d}")
        got = itemindex._tidy(d, a.keep)
    except OSError as e:                              # nothing could be looked at: never a clean result
        print(f"upkeep tidy: the index files cannot be listed ({type(e).__name__}: {e})", file=sys.stderr)
        return 1
    common.say({"out": "flow.index-files-tidied", "moved": got["removed"],
                **{k: got[k] for k in ("left", "held", "young")}})
    common.say({"out": "flow.retired-index-files-removed", "moved": got["retired"]})
    return 0


EVERY = (60.0, 86400.0)        # rollup-every and retain-every: 1m to 1d (the template holds them there too)


def _compactor(argv: list[str], what: str) -> int:
    """``upkeep rollup`` (roll-up, prune past keep, the archive's forgetting) and ``upkeep retain`` (the measurements
    into their tiers), under the compaction lock. One line: JSON moving ``flow.rolled-up`` (items; ``--flow
    events-forgotten``: events pruned) or ``flow.measurements-forgotten``, or ``busy: ...`` (exit 0) when the lock is held."""
    from ...durations import DurationError, parse_duration
    from ...store import Project
    ap = argparse.ArgumentParser(prog=f"upkeep {what}")
    ap.add_argument("--every", required=True)
    ap.add_argument("--flow", choices=["rolled-up", "events-forgotten"], default="rolled-up")
    a = ap.parse_args(argv)
    try:
        if not EVERY[0] <= parse_duration(a.every, "--every") <= EVERY[1]:
            raise DurationError(f"--every is 1m to 1d (not {a.every})")
    except DurationError as e:
        print(f"upkeep {what}: {e}", file=sys.stderr)
        return 2
    from ... import model, rollup
    p = Project(model.load(common.root()), common.state_dir(), note=False)
    with rollup.compaction(p) as held:
        if not held:                                 # (words, not JSON: the engine logs them, moves nothing)
            print(f"busy: another process holds {p.dir / rollup.LOCK}; nothing done", flush=True)
            return 0
        if what == "rollup":                         # the same work for either block; its line moves the block's flow
            got = rollup.record(p)
            moved = got["pruned"] if a.flow == "events-forgotten" else got["rollup"]["items"]
            common.say({"out": f"flow.{a.flow}", "moved": moved, "items": got["rollup"]["items"], "events": got["rollup"]["events"],
                        "pruned": got["pruned"], "archive_forgot": got["archive_forgot"]})
        else:
            got = rollup.measurements(p) or {"rolled": 0, "forgot": 0}
            common.say({"out": "flow.measurements-forgotten", "moved": got["forgot"], "rolled": got["rolled"]})
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("rollup", "retain"):
        return _compactor(argv[1:], argv[0])
    if not argv or argv[0] != "tidy":
        print("usage: python -m ergostat.library.run upkeep tidy --keep N | rollup --every D | retain --every D", file=sys.stderr)
        return 2
    return tidy(argv[1:])
