"""Where the record is kept (SPEC §4b, ``storage:``): which backend holds the events and which the
measurements, how long raw readings are kept and the tiers they are rolled up into, and when an
item's older events are rolled up into a snapshot (``rollup.py``). Every backend has the same
interface as the SQLite ones in ``store.py`` (``Events``, ``Measurements``), and one conformance
suite holds them all to it (``tests/test_store_conformance.py``).

    storage:
      events: segments                 # or sqlite; segments: compressed segments with an index (segments.py)
      measurements:
        backend: sqlite                # or victoriametrics (url: http://127.0.0.1:8428)
        raw: 2d                        # raw readings kept this long
        tiers: {1m: 14d, 10m: 90d, 1h: 2y}   # then buckets of each width, each kept this long
      rollup:
        after: 7d                      # an item's events older than this become one snapshot
        kinds: {session: 1d}           # per item kind
        every: 1h                      # how often the engine rolls up and forgets

The defaults run on a laptop with no services."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .durations import DurationError, parse_duration

EVENT_BACKENDS = ("sqlite", "segments")
MEASUREMENT_BACKENDS = ("sqlite", "victoriametrics")
DEFAULT_EVENTS = "segments"
RAW = 2 * 86400.0
TIERS = ((60.0, 14 * 86400.0), (600.0, 90 * 86400.0), (3600.0, 730 * 86400.0))
ROLLUP_AFTER = 7 * 86400.0
EVERY = 3600.0


@dataclass
class Storage:
    events: str = DEFAULT_EVENTS
    measurements: str = "sqlite"
    url: str | None = None                         # victoriametrics
    raw: float | None = RAW
    tiers: tuple[tuple[float, float], ...] = TIERS
    rollup_after: float | None = ROLLUP_AFTER      # None: never rolled up
    rollup_kinds: dict[str, float] = field(default_factory=dict)
    every: float = EVERY

    def horizon(self, kind: str | None) -> float | None:
        """How old an item's events are before they are rolled up: its kind's, else the default."""
        return self.rollup_kinds.get(kind or "", self.rollup_after)


def _dur(v, what: str, problems: list[str]) -> float | None:
    if v in (None, "never", False):
        return None
    try:
        return parse_duration(v, what)
    except DurationError as e:
        problems.append(str(e))
        return None


def parse(raw, problems: list[str]) -> Storage:
    """``storage:`` as written; what is wrong goes in ``problems`` and its default is kept."""
    s = Storage()
    if raw is None:
        return s
    if not isinstance(raw, dict):
        problems.append("storage: a map (events:, measurements:, rollup:)")
        return s
    for k in raw:
        if k not in ("events", "measurements", "rollup"):
            problems.append(f"storage: unknown key {k!r} (known: events, measurements, rollup)")
    ev = raw.get("events")
    if isinstance(ev, dict):
        ev = ev.get("backend")
    if ev is not None:
        if ev not in EVENT_BACKENDS:
            problems.append(f"storage.events: {ev!r} is not a backend ({', '.join(EVENT_BACKENDS)})")
        else:
            s.events = ev
    me = raw.get("measurements")
    if isinstance(me, str):
        me = {"backend": me}
    if me is not None:
        if not isinstance(me, dict):
            problems.append("storage.measurements: a backend's name, or a map (backend:, url:, raw:, tiers:)")
            me = {}
        for k in me:
            if k not in ("backend", "url", "raw", "tiers"):
                problems.append(f"storage.measurements: unknown key {k!r} (known: backend, url, raw, tiers)")
        b = me.get("backend", "sqlite")
        if b not in MEASUREMENT_BACKENDS:
            problems.append(f"storage.measurements.backend: {b!r} is not a backend ({', '.join(MEASUREMENT_BACKENDS)})")
        else:
            s.measurements = b
        if b == "victoriametrics":
            s.url = str(me.get("url") or "http://127.0.0.1:8428")
        if "raw" in me:
            s.raw = _dur(me["raw"], "storage.measurements.raw", problems)
        if "tiers" in me:
            t = me["tiers"]
            if t in (None, False, {}, []):
                s.tiers = ()
            elif not isinstance(t, dict):
                problems.append("storage.measurements.tiers: a map of bucket width to how long it is kept ({1m: 14d})")
            else:
                got = [(_dur(e, "storage.measurements.tiers", problems), _dur(k, "storage.measurements.tiers", problems))
                       for e, k in t.items()]
                if all(e and k for e, k in got):
                    s.tiers = tuple(sorted(got))        # type: ignore[arg-type]
                    if any(b % a for (a, _), (b, _) in zip(s.tiers, s.tiers[1:], strict=False)):
                        problems.append("storage.measurements.tiers: each bucket width a multiple of the one before (1m, 10m, 1h)")
    ro = raw.get("rollup")
    if ro is not None:
        if not isinstance(ro, dict):
            ro = {"after": ro}
        for k in ro:
            if k not in ("after", "kinds", "every"):
                problems.append(f"storage.rollup: unknown key {k!r} (known: after, kinds, every)")
        if "after" in ro:
            s.rollup_after = _dur(ro["after"], "storage.rollup.after", problems)
        for kind, v in (ro.get("kinds") or {}).items():
            got = _dur(v, f"storage.rollup.kinds.{kind}", problems)
            s.rollup_kinds[str(kind)] = got          # type: ignore[assignment]
        if "every" in ro:
            s.every = _dur(ro["every"], "storage.rollup.every", problems) or EVERY
    return s


def open_events(cfg: Storage, directory: Path):
    if cfg.events == "segments":
        from .segments import Segments
        return Segments(directory)
    from .store import Events
    return Events(directory)


def open_measurements(cfg: Storage, directory: Path):
    if cfg.measurements == "victoriametrics":
        from .victoria import Victoria
        return Victoria(cfg.url or "http://127.0.0.1:8428", directory, raw=cfg.raw, tiers=list(cfg.tiers))
    from .store import Measurements
    return Measurements(directory, raw=cfg.raw, tiers=list(cfg.tiers))
