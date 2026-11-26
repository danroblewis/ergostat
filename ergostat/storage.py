"""Where the record is kept (SPEC §4b, ``storage:``): which backend holds the events, the VictoriaMetrics that
holds every reading (the only metrics store: each reading is a sample PromQL reads, ``victoria.py``), and when an
item's older events are rolled up into a snapshot (``rollup.py``). Every events backend has the same interface as
the SQLite one in ``store.py`` (``Events``), and one conformance suite holds every store to it
(``tests/test_store_conformance.py``).

    storage:
      events: segments                 # or sqlite; segments: compressed segments with an index (segments.py)
      measurements:
        url: http://127.0.0.1:8428     # the VictoriaMetrics (else ERGOSTAT_METRICS_URL, else this)
        run: victoria-metrics -storageDataPath ~/.ergostat/victoria-metrics-data -retentionPeriod 100y
                                       # optional: the command ergostat supervises (the daemon victoriametrics)
      rollup:
        after: 7d                      # an item's events older than this become one snapshot
        kinds: {session: 1d}           # per item kind
        every: 1h                      # how often the engine rolls up and forgets
      items:
        idle: 1d                       # an item with no event for this long is read from the item index, not kept folded in memory
      logs:
        block: 5MB                     # a block's log past this is cut to its last fifth, as a run's entry is added
        runs: 50                       # each block's own run files kept (logs/runs/<block>/), 1 to 1000, newest by seq
        run: 5MB                       # run.log past this is moved to run.log.1, at each start and every hour
        threads: 1MB                   # threads.txt (kill -USR1's stacks) past this is cut to its last fifth
        transcripts: 30d               # a transcript unchanged this long is forgotten by transcripts.json, never read again

The readings need a VictoriaMetrics answering (``brew install victoriametrics``, or ``run:``); none answering is
said, never covered by another store (NOTES.md, 2026-11-25)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .durations import DurationError, parse_duration

EVENT_BACKENDS = ("sqlite", "segments")
DEFAULT_EVENTS = "segments"
VM_URL = "http://127.0.0.1:8428"                  # VictoriaMetrics' own default address
URL_ENV = "ERGOSTAT_METRICS_URL"                  # the VictoriaMetrics a record without url: uses (before VM_URL)
ROLLUP_AFTER = 7 * 86400.0
EVERY = 3600.0
ITEM_IDLE = 86400.0
MB = 2**20
LOGS = {"block": 5 * MB, "runs": 50, "run": 5 * MB, "threads": MB, "transcripts": 30 * 86400.0}
RUNS_MOST = 1000                                   # (runs: a count of files, held to 1 to this)


@dataclass
class Storage:
    events: str = DEFAULT_EVENTS
    events_set: bool = False                       # the YAML named the events backend (else: an existing record decides)
    url: str | None = None                         # the VictoriaMetrics (None: metrics_url's default)
    run: str | None = None                         # the command ergostat supervises to run it (daemon victoriametrics)
    rollup_after: float | None = ROLLUP_AFTER      # None: never rolled up
    rollup_kinds: dict[str, float] = field(default_factory=dict)
    every: float = EVERY
    every_set: bool = False                        # the YAML said rollup: every: (unused under use: upkeep, a finding)
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
            problems.append("storage.measurements: a map (url:, run:)")
            me = {}
        for k in me:
            if k in ("raw", "tiers"):
                problems.append(f"storage.measurements.{k}: no longer: every reading is kept in VictoriaMetrics, for its "
                                "own -retentionPeriod (NOTES.md, 2026-11-25); remove it")
            elif k not in ("backend", "url", "run"):
                problems.append(f"storage.measurements: unknown key {k!r} (known: url, run)")
        b = me.get("backend", "victoriametrics")
        if b != "victoriametrics":
            problems.append(f"storage.measurements.backend: {b!r}: the readings are kept in VictoriaMetrics only "
                            "(NOTES.md, 2026-11-25); remove backend:")
        if me.get("url") is not None:
            s.url = str(me["url"])
        if "run" in me:
            if not isinstance(me["run"], str) or not me["run"].strip():
                problems.append("storage.measurements.run: the command that runs VictoriaMetrics")
            else:
                s.run = me["run"]
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
            s.every_set = True
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
        elif k == "runs":
            if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= RUNS_MOST:
                s.logs[k] = v
            else:
                problems.append(f"storage.logs.runs: a whole number of run files from 1 to {RUNS_MOST}, not {v!r}")
        else:
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB)\s*", str(v), re.I)
            if m:
                s.logs[k] = float(m.group(1)) * 1024 ** ("KMG".index(m.group(2)[0].upper()) + 1)
            else:
                problems.append(f"storage.logs.{k}: a size, as 500KB, 5MB or 1GB")
    if lg is not None and not isinstance(lg, dict):
        problems.append("storage.logs: a map (block:, runs:, run:, threads:, transcripts:)")
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


def answers(url: str, wait: float = 0.5) -> bool:
    """A VictoriaMetrics answering at ``url`` now (``/health``, within ``wait`` seconds)."""
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=wait) as r:
            return r.status == 200 and r.read(16).strip() == b"OK"
    except (OSError, ValueError):
        return False


def metrics_url(cfg: Storage | None) -> str:
    """The VictoriaMetrics this record's readings are in: ``url:``, else ``ERGOSTAT_METRICS_URL``, else VM_URL."""
    return ((cfg.url if cfg is not None else None) or os.environ.get(URL_ENV) or VM_URL).rstrip("/")


def in_default_home(directory: Path) -> bool:
    """A record under the default home, ``~/.ergostat``: an install's own."""
    try:
        return Path(directory).resolve().parent == (Path.home() / ".ergostat").resolve()
    except (OSError, RuntimeError):
        return False


def metrics_project(directory: Path) -> str:
    """The ``project`` label of a record's readings: its state key under the default home; under any other home (a
    script's, a demo's, a benchmark's, a test's throwaway ``ERGOSTAT_HOME``) the key and a digest of where that home
    is, so two homes sharing one VictoriaMetrics never read or delete each other's series."""
    d = Path(directory)
    if in_default_home(d):
        return d.name
    import hashlib
    try:
        where = str(d.resolve().parent)
    except (OSError, RuntimeError):
        where = str(d.parent)
    return f"{d.name}@{hashlib.sha256(where.encode()).hexdigest()[:10]}"


def not_answering(url: str) -> str:
    """What to do when no VictoriaMetrics answers at ``url``: every reading is kept there, and nothing else holds them."""
    return (f"no VictoriaMetrics answers at {url}, and ergostat keeps every reading there. Start one: "
            "brew install victoriametrics, then ergostat run (it starts one at the default address), or victoria-metrics -storageDataPath ~/.ergostat/victoria-metrics-data "
            "-retentionPeriod 100y (or brew services start victoriametrics); or have ergostat run it with "
            "storage: measurements: run: <that command> in the model; or point storage: measurements: url: (or "
            f"{URL_ENV}) at one that runs (docs/DASHBOARDS.md, VictoriaMetrics)")


BINARIES = ("victoria-metrics", "victoria-metrics-prod")   # Homebrew's name, then the release archive's
DATA = Path.home() / ".ergostat" / "victoria-metrics-data"


def start_local(cfg: Storage | None, wait: float = 15.0) -> str | None:
    """Start the VictoriaMetrics the readings are in, when it is ergostat's own: no ``url:`` and no ``run:`` in the model,
    no ``ERGOSTAT_METRICS_URL``, so the default local address. Started detached (it outlives the run: every ergostat
    command and every project on this machine reads it), its data in ``~/.ergostat/victoria-metrics-data`` and its log
    beside it. Returns None once it answers, else what is wrong (no binary, or it did not come up)."""
    import shutil
    import subprocess
    import time
    url = metrics_url(cfg)
    if answers(url):
        return None
    if (cfg is not None and (cfg.url or cfg.run)) or os.environ.get(URL_ENV) or url != VM_URL.rstrip("/"):
        return not_answering(url)                     # one the owner named: theirs to start, never ours
    exe = next((b for b in map(shutil.which, BINARIES) if b), None)
    if exe is None:
        return (f"no VictoriaMetrics answers at {url}, and none is installed for ergostat to start "
                "(ergostat keeps every reading there): brew install victoriametrics, then run this again")
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA.parent / "victoria-metrics.log", "ab") as log:
        subprocess.Popen([exe, f"-storageDataPath={DATA}", "-retentionPeriod=100y", f"-httpListenAddr={url.split('://', 1)[-1]}"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if answers(url):
            return None
        time.sleep(0.2)
    return (f"started VictoriaMetrics ({exe}) but it did not answer at {url} within {wait:g}s; "
            f"its log: {DATA.parent / 'victoria-metrics.log'}")


def open_measurements(cfg: Storage, directory: Path):
    from .victoria import Victoria
    return Victoria(metrics_url(cfg), directory, project=metrics_project(directory))
