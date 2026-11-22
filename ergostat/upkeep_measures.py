"""ergostat's own upkeep, measured (SPEC §2a, *Upkeep*): ``ergostat.upkeep.index-files``, the live item-index files
under ``<state>/items``, and ``ergostat.upkeep.retired-index-files``, the retired ones (``spec/itemindex.files``);
``rollup-due`` (``rollup.compact``'s dry run), ``events-past-keep`` (what pruning would forget) and ``measurements-due``.

A record kept nowhere on disk, an items folder that cannot be listed, or a store that cannot count what is due (an
events store without ``prunable``, VictoriaMetrics) gives no reading (None, said on standard error), never 0."""

from __future__ import annotations

import sys
import time

from .spec import itemindex


def _none(name: str, why: str) -> None:
    print(f"{name}: {why}, so there is no reading", file=sys.stderr)


def record(p, name: str) -> float | None:
    now = time.time()
    if name.endswith("rollup-due"):
        from .rollup import compact
        return float(compact(p, now, cap=p.model.keep, dry=True)["items"])
    if name.endswith("events-past-keep"):
        if not hasattr(p.events, "prunable"):
            return _none(name, f"the events store ({type(p.events).__name__}) cannot count the events past keep")
        return float(p.events.prunable(now - p.model.keep))
    if not hasattr(p.measurements, "due"):
        return _none(name, f"the measurements store ({type(p.measurements).__name__}) keeps its own retention")
    return float(p.measurements.due(now))


def measure(p, name: str) -> float | None:
    if not name.endswith("index-files"):
        return record(p, name)
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
