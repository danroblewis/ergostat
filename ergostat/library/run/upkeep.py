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
    """``upkeep rollup`` (the record: roll-up, prune past keep, the archive's forgetting) and ``upkeep retain`` (the
    measurements into their tiers): the project opened from its folder, all the work under the compaction lock.
    One line on standard output: what it did (``{"out": "flow.rolled-up", "moved": ITEMS, ...}`` or
    ``{"out": "flow.measurements-forgotten", "moved": ROWS, ...}``; the other flows are measured by their stocks'
    falls), or the words ``busy: ...`` (exit 0, nothing done) when another holds the lock."""
    from ...durations import DurationError, parse_duration
    from ...store import Project
    ap = argparse.ArgumentParser(prog=f"upkeep {what}")
    ap.add_argument("--every", required=True)
    a = ap.parse_args(argv)
    try:
        every = parse_duration(a.every, "--every")
    except DurationError as e:
        print(f"upkeep {what}: {e}", file=sys.stderr)
        return 2
    if not EVERY[0] <= every <= EVERY[1]:
        print(f"upkeep {what}: --every is 1m to 1d (not {a.every})", file=sys.stderr)
        return 2
    from ... import model as mdl
    from ... import rollup
    p = Project(mdl.load(common.root()), common.state_dir(), note=False)
    with rollup.compaction(p) as held:
        if not held:                                 # (words, not JSON: the engine logs them, moves nothing)
            print(f"busy: another process holds {p.dir / rollup.LOCK}; nothing done", flush=True)
            return 0
        if what == "rollup":
            got = rollup.record(p)
            common.say({"out": "flow.rolled-up", "moved": got["rollup"]["items"], "events": got["rollup"]["events"],
                        "pruned": got["pruned"], "archive_forgot": got["archive_forgot"]})
        else:
            got = rollup.measurements(p) or {"rolled": 0, "forgot": 0}
            common.say({"out": "flow.measurements-forgotten", "moved": got["forgot"], "rolled": got["rolled"]})
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("rollup", "retain"):
        return _compactor(argv[1:], argv[0])
    if not argv or argv[0] != "tidy":
        print("usage: python -m ergostat.library.run upkeep tidy --keep N | rollup --every D | retain --every D",
              file=sys.stderr)
        return 2
    return tidy(argv[1:])
