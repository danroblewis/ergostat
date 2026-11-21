"""ergostat's own upkeep, measured (SPEC §2a, *Upkeep*): ``ergostat.upkeep.index-files``, the live item-index files
under ``<state>/items``, and ``ergostat.upkeep.retired-index-files``, the retired ones (``spec/itemindex.files``).

A record kept nowhere on disk, or an items folder that cannot be listed, gives no reading (None, said on standard
error, the sensor's log), never 0: a goal held at "few files" is never met by a folder nobody could look in."""

from __future__ import annotations

import sys

from .spec import itemindex


def measure(p, name: str) -> float | None:
    d = itemindex.state_dir(p.events)
    if d is None:
        print(f"{name}: the record is kept nowhere on disk, so it has no index files to count", file=sys.stderr)
        return None
    try:
        live, retired = itemindex.files(d / "items")
    except OSError as e:
        print(f"{name}: {d / 'items'} cannot be listed ({type(e).__name__}: {e})", file=sys.stderr)
        return None
    return float(len(retired if name.endswith("retired-index-files") else live))
