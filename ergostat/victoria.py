"""The measurements: every reading is kept in VictoriaMetrics (SPEC §4b, ``storage: measurements: {url: ...}``), the
only metrics store (NOTES.md, 2026-11-25), read and written over its HTTP API (standard library only).

Every reading is a sample named for its series, with the series' bounded labels (``promql_name``, from the model:
promnames.py): a part's sensor under the part's own name (``gaps_approved``), a run's ``ergostat_run_<measure>{block}``,
a valve's ``ergostat_valve_position{valve}``, ..., each with ``project="<state key>"`` and ``series="<series>"`` too,
so ergostat's own series are queried by PromQL
like any other source's (the built-in ``ergostat`` data source, ergostat/datasources). Writes: ``/api/v1/import``
(JSON lines, millisecond timestamps, out of order allowed), then ``/internal/force_flush`` so what
was written is read at once. Raw reads: ``/api/v1/export``. Buckets: MetricsQL over
``/api/v1/query_range`` (``avg_over_time``, ``last_over_time``, ``tlast_over_time``, ...), computed by the
server, so a month of readings never leaves it one by one. Retention is the server's own
(``-retentionPeriod``); VictoriaMetrics compresses what it keeps, and the open-source server has no
downsampling: old spans are bucketed when they are asked for. A reading
set aside (``forget``) is kept in ``measurements.forgotten.json`` in the state directory, and the ledger of
backfilled readings (``backfill``) in ``measurements.backfilled.db`` beside it. No server answering is said, with
how to start one (``storage.not_answering``), never covered by another store."""

from __future__ import annotations

import atexit
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import weakref
from pathlib import Path

from .promnames import Names, item_labels, names_for

OLD_METRIC = "ergostat_reading"   # every series' one name before its labels (still read: ``_sel``)
FOREVER = "100y"                  # (every reading: VictoriaMetrics keeps at most 100 years)
EPS = 0.001                       # a bucket is (start, end]: queried a millisecond early, so it is [start, end)


class VictoriaError(RuntimeError):
    pass


_WAITING: weakref.WeakSet = weakref.WeakSet()    # the stores with readings waiting to be sent (sent at exit too)
_PEERS: dict[tuple[str, str], weakref.WeakSet] = {}   # (server, project) → this process's stores of it (``_wrote``)
_PEERS_LOCK = threading.Lock()


def _at_exit() -> None:
    for v in list(_WAITING):
        v._last()


atexit.register(_at_exit)


def _ms(t: float | None) -> float | None:
    """A time as the server keeps it, to the nearest millisecond (``_import``): a span's bounds are read this way, so a
    reading written at exactly a bound is in the span."""
    return None if t is None else round(float(t) * 1000) / 1000


def _q(s: str) -> str:
    return json.dumps(s)


def promql_name(series: str, names: Names | None = None) -> dict[str, str]:
    """A series' metric name and labels (without ``project`` and ``series``), as the model ``names`` them
    (promnames.py). Each label's value is a part, sensor, block or measure the model declares, so the labels are
    bounded by the model: nothing generated (an item's id, a run's) is ever a label, which is the event log's."""
    return (names or Names()).labels(series)


def _newer(x: tuple[float, float], old: tuple[float, float] | None) -> bool:
    """Whether reading ``x`` stands for its series over ``old``: the later; of two at one time, the greater, as
    VictoriaMetrics' own deduplication keeps (it holds both, in no order a reader can rely on)."""
    return old is None or x[0] > old[0] or (x[0] == old[0] and x[1] > old[1])


def _refused(e: OSError) -> bool:
    """A connection no server took (refused, reset, no route): not one that was too slow."""
    why = getattr(e, "reason", e)
    return isinstance(why, OSError) and not isinstance(why, TimeoutError) and not isinstance(e, TimeoutError)


class Victoria:
    name = "victoriametrics"

    RAW = 2 * 86400.0             # a long span's readings older than this are bucketed (``range``), the recent read whole
    WIDTHS = (60.0, 600.0, 3600.0, 86400.0)   # the buckets a long span is read in: the finest within RAW_MOST
    FULL = 300.0                  # seconds between ``newest``'s reads of every series (between them: the recent ones)
    LATE = 3600.0                 # how far before its last read ``newest`` looks again: another process's reading
                                  # older than this, written since, is seen at the next full read

    def __init__(self, url: str, directory: Path, project: str | None = None):
        self.base = url.rstrip("/")
        self.dir = directory
        self.project = project or directory.name
        self._pending: list[tuple[str, float, float]] = []    # written here, not yet sent: sent within FLUSH
        self._lock = threading.Lock()
        self._sending = threading.Lock()                     # held while readings taken from _pending are sent
        self._flusher: threading.Thread | None = None
        self.spec_of = lambda: None   # the model whose names a reading is written under (Project sets it)
        self._newest: dict[str, tuple[float, float]] | None = None   # series → its newest reading (``newest``)
        self._newest_read = (0.0, 0.0)                     # (when every series' was last read, when the recent were)
        self._newest_lock = threading.Lock()
        self._log: list[str] = []                          # the series whose newest changed, in turn (``changes``)
        self._log_at = (0, 0)                              # (its epoch: read afresh, the changes dropped before it)
        self._writes = 0                                   # imports and deletions by this process (``version``)
        self._deleted = False                              # readings deleted here: ``newest`` reads every series again
        with _PEERS_LOCK:
            _PEERS.setdefault((self.base, self.project), weakref.WeakSet()).add(self)
        from .store import LEDGER, _Conns
        self._ledger = _Conns(directory / "measurements.backfilled.db", LEDGER)   # beside measurements.forgotten.json

    FLUSH = 0.5                   # seconds a reading waits before it is sent (one import for many)

    def flush(self) -> None:
        """Send what is pending, now (every read does first: what was written here is read here), after what another
        thread is sending already."""
        with self._sending:
            with self._lock:
                rows, self._pending = self._pending, []
            if rows:
                try:
                    self._import(rows)
                except VictoriaError:
                    with self._lock:                   # the server away: kept, and sent with the next
                        self._pending[:0] = rows
                    raise

    def _later(self) -> None:
        """Sends what is pending every ``FLUSH``, and ends once nothing is (the next ``add`` starts another): a store
        written once holds no thread."""
        while True:
            time.sleep(self.FLUSH)
            try:
                self.flush()
            except VictoriaError:
                pass                                       # kept (flush put them back) for the next try
            with self._lock:
                if not self._pending:
                    self._flusher = None
                    return

    # ---- the API

    def _req(self, path: str, params: dict | None = None, body: bytes | None = None) -> bytes:
        url = self.base + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST" if body is not None else "GET"),
                                        timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise VictoriaError(f"VictoriaMetrics at {self.base}{path}: {e.code} {e.read()[:300]!r}") from None
        except OSError as e:
            if _refused(e):
                from .storage import not_answering
                raise VictoriaError(f"{not_answering(self.base)} ({e})") from e
            raise VictoriaError(f"VictoriaMetrics at {self.base}: {e}") from e

    def check(self) -> None:
        """``VictoriaError``, saying how to start one, when no VictoriaMetrics answers here (``/health``)."""
        from .storage import answers, not_answering
        if not answers(self.base, wait=2.0):
            raise VictoriaError(not_answering(self.base))

    def labels(self, series: str) -> dict[str, str]:
        """The name and labels ``series`` is written under now, by the model as it is (``promql_name``)."""
        return names_for(self.spec_of()).labels(series)

    def _sel(self, series: str | None = None, name: str = ".+") -> str:
        """Every name of this project's (or one series'): a record written under an earlier name (OLD_METRIC, the old
        generic ``ergostat_sensor``, a part renamed in the model) is read too."""
        return "{" + f'__name__=~"{name}",project={_q(self.project)}' + (f",series={_q(series)}" if series else "") + "}"

    def _own(self) -> str:
        """This project's series (with a ``series`` label): not the item metrics written under labels of their own."""
        return self._sel()[:-1] + ',series!=""}'

    def put(self, rows: list[tuple[dict, float, float]]) -> None:
        """Samples under labels of their own (``itemmetrics.py``: a name and its labels, no ``series``; an item kind's
        under its own name, ``promnames.item_labels``), with this project's ``project``, imported at once; a server
        away raises ``VictoriaError``."""
        groups: dict[tuple, dict] = {}
        for labels, t, v in ((item_labels(lb), t, v) for lb, t, v in rows):
            g = groups.setdefault(tuple(sorted(labels.items())), {"metric": {**labels, "project": self.project},
                                                                    "values": [], "timestamps": []})
            g["values"].append(float(v))
            g["timestamps"].append(round(float(t) * 1000))
        got = list(groups.values())
        for i in range(0, len(got), 2000):
            self._req("/api/v1/import", body="".join(json.dumps(g) + "\n" for g in got[i:i + 2000]).encode())
        self._req("/internal/force_flush")

    def _import(self, rows: list[tuple[str, float, float]]) -> None:
        groups: dict[str, dict] = {}
        for s, t, v in rows:
            g = groups.setdefault(s, {"metric": {**self.labels(s), "project": self.project, "series": s},
                                      "values": [], "timestamps": []})
            g["values"].append(float(v))
            g["timestamps"].append(round(float(t) * 1000))
        self._req("/api/v1/import", body="".join(json.dumps(g) + "\n" for g in groups.values()).encode())
        self._req("/internal/force_flush")
        last: dict[str, tuple[float, float]] = {}
        for s, t, v in rows:                               # (each series' latest sent: ``_newer``)
            x = (round(float(t) * 1000) / 1000, float(v))
            if _newer(x, last.get(s)):
                last[s] = x
        self._wrote(last)

    def _peers(self) -> list[Victoria]:
        with _PEERS_LOCK:
            return list(_PEERS.get((self.base, self.project), ()))

    def _wrote(self, last: dict[str, tuple[float, float]] | None) -> None:
        """Readings sent (``last``: each series' latest), or deleted (None), by this process: every store of this project
        here knows at once (``newest``, ``version``), whichever sent them."""
        for v in self._peers():
            with v._newest_lock:
                v._writes += 1
                if last is None:
                    v._deleted = True
                    continue
                got = v._newest
                if got is None:
                    continue
                for s, x in last.items():
                    old = got.get(s)
                    if _newer(x, old):
                        got = dict(got) if got is v._newest else got   # (a dict handed out is never changed)
                        got[s] = x
                        v._log.append(s)
                v._newest = got

    def _rows(self, sel: str, start: float | None = None, end: float | None = None) -> list[tuple[dict, list]]:
        """Each series the selector matches, as exported: its labels and its readings ``(time, value)``."""
        params: dict = {"match[]": sel}
        if start is not None:
            params["start"] = f"{start:.3f}"
        # (an end unsaid is the server's a moment ago, which leaves out what was just written)
        params["end"] = f"{end if end is not None else time.time() + 2 * 86400:.3f}"
        return [(r["metric"], [(t / 1000, float(v)) for t, v in zip(r["timestamps"], r["values"], strict=True)])
                for line in self._req("/api/v1/export", params).decode().splitlines() if line.strip()
                for r in [json.loads(line)]]

    def _export(self, series: str | None, start: float | None = None, end: float | None = None,
                sel: str | None = None) -> dict[str, list]:
        out: dict[str, list] = {}
        for metric, pts in self._rows(sel or self._sel(series), start, end):
            out.setdefault(metric.get("series", ""), []).extend(pts)
        for s, pts in out.items():                     # (of readings at one time, the greater: ``_newer``)
            pts.sort()
            out[s] = [p for i, p in enumerate(pts) if i + 1 == len(pts) or pts[i + 1][0] != p[0]]
        return out

    def _query(self, q: str, at: float) -> list[tuple[dict, float]]:
        d = json.loads(self._req("/api/v1/query", {"query": q, "time": f"{at:.3f}", "nocache": "1", "latency_offset": "1ms"}))
        if d.get("status") != "success":
            raise VictoriaError(d.get("error", "query failed"))
        return [(r["metric"], float(r["value"][1])) for r in d["data"]["result"]]

    def _range(self, q: str, start: float, end: float, step: float) -> dict[float, float]:
        """``q`` at ``start`` and each ``step`` after it to ``end``: the step is sent in whole milliseconds, so the end is
        moved to the last point's (never a point lost to the rounding), a moment past it."""
        k = max(0, int((end - start) / step + 1e-6))
        step = max(round(step, 3), 0.001)
        end = start + k * step + 0.0005
        ahead = end - (time.time() - 0.005)
        if 0 < ahead < 0.05:              # (the server answers no point past its now: one a moment ahead, waited for)
            time.sleep(ahead)
        d = json.loads(self._req("/api/v1/query_range", {"query": q, "start": f"{start:.3f}", "end": f"{end:.3f}",
                                                          "step": f"{step:.3f}s", "nocache": "1", "latency_offset": "1ms"}))
        if d.get("status") != "success":
            raise VictoriaError(d.get("error", "query failed"))
        out: dict[float, float] = {}
        for r in d["data"]["result"]:     # (one series under two names, an old and the model's: their spans apart)
            for t, v in r["values"]:
                out.setdefault(float(t), float(v))
        return out

    # ---- writing

    def _sync_reads(self) -> None:
        """What this process wrote to this project, sent before it is read (by any of its stores here)."""
        for v in self._peers():
            if v._pending or v._sending.locked():    # (one being sent by the flushing thread: waited for)
                v.flush()

    def add(self, series: str, value: float, at: float | None = None) -> None:
        """A reading, sent with the others written within ``FLUSH`` (the engine writes one at a time,
        and one import and flush each would hold it back)."""
        with self._lock:
            self._pending.append((series, at if at is not None else time.time(), float(value)))
            if self._flusher is None:
                self._flusher = threading.Thread(target=self._later, name="ergostat-victoria-flush", daemon=True)
                self._flusher.start()
                _WAITING.add(self)

    def _last(self) -> None:
        try:
            self.flush()
        except VictoriaError:
            pass

    def add_many(self, rows: list[tuple[str, float, float]]) -> None:
        self.flush()
        for i in range(0, len(rows), 200_000):
            self._import(rows[i:i + 200_000])

    def backfill(self, series: str, rows: list[tuple[float, float]], src: str | None = None, replace: bool = False) -> dict:
        """Past readings not backfilled before, sent while the ledger is held; a refused import rolls the ledger back.
        ``replace``: what is in their span set aside first (``_replace``)."""
        from .store import ledger_write
        return ledger_write(self._ledger, series, rows, src, lambda c, rows: self.add_many(rows),
                            self._replace if replace else None)

    def _replace(self, c, series: str, lo: float, hi: float, rows: list[tuple[str, float, float]], why: str) -> int:
        """The server deletes only whole series: under the compaction lock, the series read out, its readings in
        ``[lo, hi]`` set aside (``measurements.forgotten.json``, with ``why``), and the rest with ``rows`` written back."""
        import fcntl

        from .rollup import LOCK
        self._sync_reads()
        lo, hi = _ms(lo), _ms(hi)
        with open(self.dir / LOCK, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)                 # (let go when the file is closed)
            pts = self._export(series, 0).get(series) or []
            out = [p for p in pts if lo <= p[0] <= hi]
            self._delete(self._sel(series))
            self._import([(series, t, v) for t, v in pts if not lo <= t <= hi] + rows)
            self._aside(series, out, why)
        return len(out)

    def _delete(self, sel: str) -> None:
        self._req("/api/v1/admin/tsdb/delete_series", {"match[]": sel}, body=b"")
        self._wrote(None)

    def _aside(self, series: str, pts: list[tuple[float, float]], why: str | None = None) -> None:
        note = self.dir / "measurements.forgotten.json"
        old = json.loads(note.read_text()) if note.exists() else []
        note.write_text(json.dumps(old + [{"series": series, "time": t, "value": v, "forgotten_at": time.time(), "why": why}
                                          for t, v in pts]))

    def backfills(self, series: str) -> list[dict]:
        from .store import ledger_read
        return ledger_read(self._ledger, series)

    # ---- reading

    def latest(self, series: str, before: float | None = None) -> tuple[float, float] | None:
        self._sync_reads()
        before = before if before is not None else time.time() + 86400
        for back in (3600, 86400, 30 * 86400, None):
            pts = self._export(series, None if back is None else before - back, before).get(series) or []
            if pts:
                return pts[-1]
        return None

    def newest(self) -> dict[str, tuple[float, float]]:
        """Every series' newest reading, ``(time, value)``: what ``latest(series)`` answers, for every series at once
        (docs/proposals/scale.md, #3). Kept in memory: what this process sends is merged in as it is sent (``_wrote``);
        every ``FULL`` seconds, and after this process deleted readings, every series is read again; between, the
        series with a reading in the ``LATE`` before the last read and since (another process's) are merged in. The
        engine reads every sensor once a pass: two queries, not one per sensor. The dict is the store's own: read it,
        never change it."""
        self._sync_reads()
        with self._newest_lock:
            now = time.time()
            at = now + 86400.0                            # (a reading a little ahead of this clock is read too)
            got, (full_at, recent_at) = self._newest, self._newest_read
            if got is None or self._deleted or now - full_at > self.FULL:
                fresh = self._latest_all(FOREVER, at)
                for s, x in (got or {}).items() if not self._deleted else ():
                    if s in fresh and fresh[s][0] == x[0] and _newer(x, fresh[s]):
                        fresh[s] = x                       # (of one time, the greater, whichever the server answered)
                if got is None or self._deleted:
                    self._log, self._log_at = [], (self._log_at[0] + 1, 0)
                else:
                    self._log += [s for s, x in fresh.items() if got.get(s) != x]
                got, self._deleted, self._newest_read = fresh, False, (now, now)
            else:
                window = at - recent_at + self.LATE
                for s, x in self._latest_all(f"{window:.3f}s", at).items():
                    old = got.get(s)
                    if _newer(x, old):
                        got = dict(got) if got is self._newest else got   # (a dict handed out is never changed)
                        got[s] = x
                        self._log.append(s)
                self._newest_read = (full_at, now)
            if len(self._log) > 100_000:                  # (a reader that far behind reads everything again)
                self._log_at = (self._log_at[0], self._log_at[1] + len(self._log))
                self._log = []
            self._newest = got
            return got

    def _latest_all(self, window: str, at: float) -> dict[str, tuple[float, float]]:
        """Each series' newest reading in ``window`` before ``at``, ``(time, value)``; of one series under two names,
        the later."""
        sel, out = self._own(), {}
        key = lambda m: tuple(sorted(m.items()))   # noqa: E731
        when = {key(m): t for m, t in self._query(f"tlast_over_time({sel}[{window}]) keep_metric_names", at)}
        for m, v in self._query(f"last_over_time({sel}[{window}]) keep_metric_names", at):
            t = when.get(key(m))
            if t is not None and _newer((t, v), out.get(m["series"])):
                out[m["series"]] = (t, v)
        return out

    def changes(self, since: tuple | None) -> tuple[dict[str, tuple[float, float]], set[str] | None, tuple]:
        """``newest()``, the series whose newest reading changed since ``since`` (a mark an earlier call returned;
        None when that cannot be said: the first call, or every series read afresh since), and the mark for the next
        call. The engine's pass reads only what changed (docs/proposals/scale.md, #1)."""
        got = self.newest()
        with self._newest_lock:
            (epoch, base), n = self._log_at, len(self._log)
            mark = (epoch, base + n)
            if since is None or since[0] != epoch or since[1] < base:
                return got, None, mark
            return got, set(self._log[since[1] - base:]), mark

    def version(self) -> tuple:
        """What changes when a reading is written or set aside: by this process, and every series' newest reading
        (another process's reading past the newest moves it; one it writes into the past does not)."""
        got = self.newest()
        return (self._writes, len(got), hash(frozenset(got.items())))

    RAW_MOST = 20_000             # readings of one series read one by one, at most; more are bucketed

    def range(self, series: str, since: float, until: float | None = None, last: int | None = None) -> list[tuple[float, float]]:
        """The readings, one by one when there are few (or for the recent ``RAW``); otherwise, before
        that, each bucket of the finest of ``WIDTHS`` that keeps them to ``RAW_MOST`` as its last reading."""
        self._sync_reads()
        until = until if until is not None else time.time() + 1
        since, until = _ms(since), _ms(until)
        if last:
            got: list[tuple[float, float]] = []
            for back in (3600, 86400, 30 * 86400, None):
                lo = since if back is None else max(since, until - back)
                got = [p for p in self._export(series, lo, until).get(series) or [] if since <= p[0] <= until]
                if len(got) >= last or lo == since:
                    break
            return got[-last:]
        if self.count(series, since, until) <= self.RAW_MOST:
            return [p for p in self._export(series, since, until).get(series) or [] if since <= p[0] <= until]
        cut = max(since, time.time() - self.RAW)
        out: list[tuple[float, float]] = []
        if cut > since:
            e = next((e for e in self.WIDTHS if (min(cut, until) - since) / e <= self.RAW_MOST), self.WIDTHS[-1])
            sel = self._sel(series)
            vals = self._range(f"last_over_time({sel}[{e:g}s])", since + e - EPS, min(cut, until), e)
            ts = self._range(f"tlast_over_time({sel}[{e:g}s])", since + e - EPS, min(cut, until), e)
            out = sorted((ts[t], v) for t, v in vals.items() if t in ts and since <= ts[t] < cut)
        if until >= cut:
            out += [p for p in self._export(series, cut, until).get(series) or [] if cut <= p[0] <= until]
        return out

    def ranges(self, series: list[str], since: float, until: float) -> dict[str, list[tuple[float, float]]]:
        """``range(s, since, until)`` of each of ``series``, read together (one export for many), every reading one by
        one; a series with none in the span is there, empty."""
        self._sync_reads()
        since, until = _ms(since), _ms(until)
        out: dict[str, list] = {s: [] for s in series}
        names = sorted(out)
        for i in range(0, len(names), 100):
            group = "|".join(re.escape(s) for s in names[i:i + 100])
            sel = "{" + f'__name__=~".+",project={_q(self.project)},series=~{_q(group)}' + "}"
            for s, pts in self._export(None, since, until, sel=sel).items():
                if s in out:
                    out[s] = [p for p in pts if since <= p[0] <= until]
        return out

    def count(self, series: str | None = None, since: float | None = None, until: float | None = None) -> int:
        self._sync_reads()
        until = until if until is not None else time.time() + 86400
        span = f"{max(1.0, until - since) + EPS:.3f}s" if since is not None else FOREVER
        got = self._query(f"sum(count_over_time({self._sel(series) if series else self._own()}[{span}]))", until)
        return int(got[0][1]) if got else 0

    def bucketed(self, series: str, since: float, until: float, n: int) -> list[tuple[int, float, float, float]]:
        """The readings in ``n`` equal buckets over ``[since, until]``: ``(bucket, mean, the last reading's time, its
        value)`` for each that has a reading (one at ``until`` in the last). Few readings: worked out from them; many:
        by the server, each bucket a window."""
        self._sync_reads()
        since, until = _ms(since), _ms(until)
        w = max((until - since) / max(n, 1), 0.001)        # (a bucket of a millisecond at least: the server's finest)
        if self.count(series, since, until) <= self.RAW_MOST:
            acc: dict[int, list] = {}
            for t, v in self._export(series, since, until).get(series) or []:
                if since <= t <= until:
                    a = acc.setdefault(min(max(int((t - since) / w), 0), n - 1), [0.0, 0, t, v])
                    a[0], a[1] = a[0] + v, a[1] + 1
                    if t >= a[2]:
                        a[2], a[3] = t, v
            return [(b, a[0] / a[1], a[2], a[3]) for b, a in sorted(acc.items())]
        sel, win = self._sel(series), f"{w:.3f}s"
        start, end = since + w - EPS, since + n * w - EPS
        mean = self._range(f"avg_over_time({sel}[{win}])", start, end, w)
        last = self._range(f"last_over_time({sel}[{win}])", start, end, w)
        when = self._range(f"tlast_over_time({sel}[{win}])", start, end, w)
        out = []
        for t, m in sorted(mean.items()):
            b = min(n - 1, max(0, round((t + EPS - since) / w) - 1))
            if t in last and t in when:
                out.append((b, m, when[t], last[t]))
        return out

    def rollups(self, series: str, since: float, until: float, start: float, step: float, n: int) -> list[tuple]:
        """A chart's buckets of ``step`` seconds from ``start``, over ``[since, until]``: ``(bucket, count, sum, min,
        max, the last reading)`` for each that has a reading (one before ``start`` counted in the first, one past the
        last bucket in the last). Few readings: worked out from them; many: by the server, each bucket a window."""
        self._sync_reads()
        since, until = _ms(since), _ms(until)
        acc: dict[int, list] = {}
        if self.count(series, since, until) <= self.RAW_MOST:
            for t, v in self._export(series, since, until).get(series) or []:
                if not since <= t <= until:
                    continue
                b = max(min(int((t - start) // step), n - 1), 0)
                a = acc.get(b)
                if a is None:
                    acc[b] = [1, v, v, v, t, v]
                    continue
                a[0], a[1], a[2], a[3] = a[0] + 1, a[1] + v, min(a[2], v), max(a[3], v)
                if t >= a[4]:
                    a[4], a[5] = t, v
            return [(b, a[0], a[1], a[2], a[3], a[5]) for b, a in sorted(acc.items())]
        sel, win, fs = self._sel(series), f"{step:.3f}s", ("count", "sum", "min", "max", "last")
        got = {f: self._range(f"{f}_over_time({sel}[{win}])", start + step - EPS, start + n * step - EPS, step) for f in fs}
        for t, k in sorted(got["count"].items()):
            if k and all(t in got[f] for f in fs):
                b = min(n - 1, max(0, round((t + EPS - start) / step) - 1))
                acc[b] = [int(k), *(got[f][t] for f in fs[1:])]
        return [(b, *a) for b, a in sorted(acc.items())]

    def sampled(self, series: str, since: float, until: float | None = None, points: int = 600) -> list[tuple[float, float]]:
        until = until if until is not None else time.time() + 1
        if self.count(series, since, until) <= points * 2:
            return self.range(series, since, until)
        first, last = self.first(series, since, until), self.latest(series, until)
        mid = [(t, mean) for _, mean, t, _ in self.bucketed(series, since, until, points) if first[0] < t < last[0]]
        return [first, *mid, last]

    def first(self, series: str, since: float, until: float) -> tuple[float, float] | None:
        self._sync_reads()
        since, until = _ms(since), _ms(until)
        step = 3600.0
        lo = since
        while lo <= until:
            hi = min(until, lo + step)
            pts = self._export(series, lo, hi).get(series) or []
            pts = [p for p in pts if since <= p[0] <= until]
            if pts:
                return pts[0]
            lo, step = hi + 0.001, step * 8
        return None

    def series(self) -> list[dict]:
        self._sync_reads()
        sel = self._own()
        n = {m["series"]: v for m, v in self._query(f"sum by (series) (count_over_time({sel}[{FOREVER}]))", time.time() + 86400)}
        last = {m["series"]: v for m, v in self._query(f"max by (series) (tlast_over_time({sel}[{FOREVER}]))", time.time() + 86400)}
        # (one series under two names, an old and the model's: the value is the one read last, by its time; on a tie,
        # the one under the name it is written under now)
        key = lambda m: tuple(sorted(m.items()))   # noqa: E731
        when = {key(m): t for m, t in self._query(f"tlast_over_time({sel}[{FOREVER}]) keep_metric_names", time.time() + 86400)}
        val: dict[str, tuple] = {}
        for m, v in self._query(f"last_over_time({sel}[{FOREVER}]) keep_metric_names", time.time() + 86400):
            rank = (when.get(key(m), float("-inf")), m.get("__name__") == self.labels(m["series"])["__name__"])
            if m["series"] not in val or rank > val[m["series"]][0]:
                val[m["series"]] = (rank, v)
        return [{"series": s, "n": int(n[s]), "last": last.get(s), "value": val.get(s, (0, None))[1]} for s in sorted(n)]

    def first_time(self) -> float | None:
        self._sync_reads()
        got = self._query(f"min(tfirst_over_time({self._own()}[{FOREVER}]))", time.time() + 86400)
        return got[0][1] if got else None

    # ---- setting aside, keeping

    def forget(self, series: str, above: float | None = None, below: float | None = None) -> list[tuple[float, float]]:
        """Readings above ``above`` or below ``below`` set aside: the series written again without them
        (VictoriaMetrics deletes whole series), what went kept beside the state."""
        self._sync_reads()
        if above is None and below is None:
            return []
        pts = self._export(series, 0).get(series) or []
        bad = [p for p in pts if (above is not None and p[1] > above) or (below is not None and p[1] < below)]
        if not bad:
            return []
        self._delete(self._sel(series))
        gone = set(bad)
        keep = [(series, t, v) for t, v in pts if (t, v) not in gone]
        if keep:
            self._import(keep)
        self._aside(series, bad)
        return bad

    def drop(self) -> None:
        """Every series of this project, gone (``ergostat reset``; the conformance suite's clean-up), with what this
        process had yet to send."""
        self._sync_reads()
        self._delete(self._sel())
