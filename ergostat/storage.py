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
      items:
        idle: 1d                       # an item with no event for this long is read from the item index, not kept folded in memory
      logs:
        block: 5MB                     # a block's log past this is cut to its last fifth, at its next run
        run: 5MB                       # run.log past this is moved to run.log.1, at each start and every hour
        threads: 1MB                   # threads.txt (kill -USR1's stacks) past this is cut to its last fifth
        transcripts: 30d               # a transcript unchanged this long is forgotten by transcripts.json, never read again

The defaults run on a laptop with no services."""

from __future__ import annotations

import os
import re
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
ITEM_IDLE = 86400.0
MB = 2**20
LOGS = {"block": 5 * MB, "run": 5 * MB, "threads": MB, "transcripts": 30 * 86400.0}


@dataclass
class Storage:
    events: str = DEFAULT_EVENTS
    events_set: bool = False                       # the YAML named the events backend (else: an existing record decides)
    measurements: str = "sqlite"
    url: str | None = None                         # victoriametrics
    raw: float | None = RAW
    tiers: tuple[tuple[float, float], ...] = TIERS
    rollup_after: float | None = ROLLUP_AFTER      # None: never rolled up
    rollup_kinds: dict[str, float] = field(default_factory=dict)
    every: float = EVERY
    item_idle: float = ITEM_IDLE                   # an open item untouched this long is not kept folded in memory
    logs: dict[str, float] = field(default_factory=lambda: dict(LOGS))   # the caps on the logs (bytes; transcripts: s)

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
        if k not in ("events", "measurements", "rollup", "items", "logs"):
            problems.append(f"storage: unknown key {k!r} (known: events, measurements, rollup, items, logs)")
    ev = raw.get("events")
    if isinstance(ev, dict):
        ev = ev.get("backend")
    if ev is not None:
        if ev not in EVENT_BACKENDS:
            problems.append(f"storage.events: {ev!r} is not a backend ({', '.join(EVENT_BACKENDS)})")
        else:
            s.events = ev
            s.events_set = True
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
    it = raw.get("items")
    if it is not None:
        if not isinstance(it, dict):
            problems.append("storage.items: a map (idle:)")
            it = {}
        for k in it:
            if k != "idle":
                problems.append(f"storage.items: unknown key {k!r} (known: idle)")
        if "idle" in it:
            s.item_idle = _dur(it["idle"], "storage.items.idle", problems) or ITEM_IDLE
    lg = raw.get("logs")
    for k, v in (lg.items() if isinstance(lg, dict) else ()):
        if k not in LOGS:
            problems.append(f"storage.logs: unknown key {k!r} (known: {', '.join(LOGS)})")
        elif k == "transcripts":
            s.logs[k] = _dur(v, "storage.logs.transcripts", problems) or LOGS[k]
        else:
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB)\s*", str(v), re.I)
            if m:
                s.logs[k] = float(m.group(1)) * 1024 ** ("KMG".index(m.group(2)[0].upper()) + 1)
            else:
                problems.append(f"storage.logs.{k}: a size, as 500KB, 5MB or 1GB")
    if lg is not None and not isinstance(lg, dict):
        problems.append("storage.logs: a map (block:, run:, threads:, transcripts:)")
    return s


def trim(path: Path, most: float) -> None:
    """A log past ``most`` bytes cut to its last fifth, from a line's start."""
    try:
        if path.stat().st_size > most:
            with open(path, "rb") as f:
                f.seek(-int(most // 5), 2)
                tail = f.read()
            path.write_bytes(tail[tail.find(b"\n") + 1:])
    except OSError:
        pass


def rotate(path: Path, most: float) -> None:
    """A log past ``most`` bytes copied to ``<name>.1`` (the one before replaced) and emptied in place, so whatever
    has it open for appending writes on into the fresh one."""
    try:
        if path.stat().st_size > most:
            import shutil
            shutil.copyfile(path, path.with_name(path.name + ".1"))
            os.truncate(path, 0)
    except OSError:
        pass


def events_backend(cfg: Storage, directory: Path) -> str:
    """The events backend: the one the YAML names; else a record made before the segmented log was the default
    (an ``events.db``) stays where it is, so upgrading never hides a project's history; else the default."""
    if not cfg.events_set and (Path(directory) / "events.db").exists():
        return "sqlite"
    return cfg.events


def open_events(cfg: Storage, directory: Path):
    if events_backend(cfg, directory) == "segments":
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
