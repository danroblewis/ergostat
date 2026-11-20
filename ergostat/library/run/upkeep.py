"""``use: upkeep``'s programs (SPEC §2a, *Upkeep*): ``upkeep tidy --keep N``, the index tidier, a block on the rule
rung. It works from the state directory alone (``common.state_dir``): it never opens the project, its model or an
index, only takes each index file's lock without waiting, and leaves to ``spec/itemindex._tidy`` whether a delete is
safe (no process holds the file, none changed it within ``TIDY_AGE``, checked again under the lock).

It prints one line, ``{"value": REMOVED, "removed": ..., "left": ..., "held": ..., "young": ...}``: the value, the files
removed, is what feeds ``out: flow.index-files-tidied``."""

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
    common.say({"value": got["removed"], **got})
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "tidy":
        print("usage: python -m ergostat.library.run upkeep tidy --keep N", file=sys.stderr)
        return 2
    return tidy(argv[1:])
