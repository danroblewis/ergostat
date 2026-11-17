"""The measurements in VictoriaMetrics (SPEC §4b, ``storage: measurements: {backend: victoriametrics,
url: ...}``): the same interface as ``store.Measurements``, over its HTTP API (standard library only).

Every reading is a sample of ``ergostat_reading{project="<state key>", series="<series>"}``, so
ergostat's own series can be queried by PromQL like any other source. Writes: ``/api/v1/import``
(JSON lines, millisecond timestamps, out of order allowed), then ``/internal/force_flush`` so what
was written is read at once. Raw reads: ``/api/v1/export``. Buckets: MetricsQL over
``/api/v1/query_range`` (``avg_over_time``, ``last_over_time``, ``tlast_over_time``), computed by the
server, so a month of readings never leaves it one by one. Retention is the server's own
(``-retentionPeriod``); VictoriaMetrics compresses what it keeps, and the open-source server has no
downsampling, so ``roll`` does nothing and old spans are bucketed when they are asked for. A reading
set aside (``forget``) is kept in ``measurements.forgotten.json`` in the state directory."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

METRIC = "ergostat_reading"
FOREVER = "3650d"
EPS = 0.001                       # a bucket is (start, end]: queried a millisecond early, so it is [start, end)


class VictoriaError(RuntimeError):
    pass


def _q(s: str) -> str:
    return json.dumps(s)


class Victoria:
    name = "victoriametrics"

    def __init__(self, url: str, directory: Path, project: str | None = None, raw: float | None = None,
                 tiers: list[tuple[float, float]] | None = None):
        self.base = url.rstrip("/")
        self.dir = directory
        self.project = project or directory.name
        self.raw = raw
        self.tiers = sorted(tiers or [])
        self._pending: list[tuple[str, float, float]] = []    # written here, not yet sent: sent within FLUSH
        self._lock = threading.Lock()
        self._flusher: threading.Thread | None = None

    FLUSH = 0.5                   # seconds a reading waits before it is sent (one import for many)

    def flush(self) -> None:
        """Send what is pending, now (every read does first: what was written here is read here)."""
        with self._lock:
            rows, self._pending = self._pending, []
        if rows:
            try:
                self._import(rows)
            except VictoriaError:
                with self._lock:                       # the server away: kept, and sent with the next
                    self._pending[:0] = rows
                raise

    def _later(self) -> None:
        while True:
            time.sleep(self.FLUSH)
            try:
                self.flush()
            except VictoriaError:
                pass                                       # kept (flush put them back) for the next try

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
            raise VictoriaError(f"VictoriaMetrics at {self.base}: {e}") from e

    def _sel(self, series: str | None = None) -> str:
        return "{" + f'__name__="{METRIC}",project={_q(self.project)}' + (f",series={_q(series)}" if series else "") + "}"

    def _import(self, rows: list[tuple[str, float, float]]) -> None:
        groups: dict[str, dict] = {}
        for s, t, v in rows:
            g = groups.setdefault(s, {"metric": {"__name__": METRIC, "project": self.project, "series": s}, "values": [], "timestamps": []})
            g["values"].append(float(v))
            g["timestamps"].append(round(float(t) * 1000))
        self._req("/api/v1/import", body="".join(json.dumps(g) + "\n" for g in groups.values()).encode())
        self._req("/internal/force_flush")

    def _export(self, series: str | None, start: float | None = None, end: float | None = None) -> dict[str, list]:
        params: dict = {"match[]": self._sel(series)}
        if start is not None:
            params["start"] = f"{start:.3f}"
        if end is not None:
            params["end"] = f"{end:.3f}"
        out: dict[str, list] = {}
        for line in self._req("/api/v1/export", params).decode().splitlines():
            if line.strip():
                r = json.loads(line)
                pts = out.setdefault(r["metric"].get("series", ""), [])
                pts += [(t / 1000, float(v)) for t, v in zip(r["timestamps"], r["values"], strict=True)]
        for pts in out.values():
            pts.sort()
        return out

    def _query(self, q: str, at: float) -> list[tuple[dict, float]]:
        d = json.loads(self._req("/api/v1/query", {"query": q, "time": f"{at:.3f}", "nocache": "1", "latency_offset": "1ms"}))
        if d.get("status") != "success":
            raise VictoriaError(d.get("error", "query failed"))
        return [(r["metric"], float(r["value"][1])) for r in d["data"]["result"]]

    def _range(self, q: str, start: float, end: float, step: float) -> dict[float, float]:
        d = json.loads(self._req("/api/v1/query_range", {"query": q, "start": f"{start:.3f}", "end": f"{end:.3f}",
                                                          "step": f"{step:.3f}s", "nocache": "1", "latency_offset": "1ms"}))
        if d.get("status") != "success":
            raise VictoriaError(d.get("error", "query failed"))
        res = d["data"]["result"]
        return {float(t): float(v) for t, v in res[0]["values"]} if res else {}

    # ---- writing

    def _sync_reads(self) -> None:
        if self._pending:
            self.flush()

    def add(self, series: str, value: float, at: float | None = None) -> None:
        """A reading, sent with the others written within ``FLUSH`` (the engine writes one at a time,
        and one import and flush each would hold it back)."""
        with self._lock:
            self._pending.append((series, at if at is not None else time.time(), float(value)))
            if self._flusher is None:
                self._flusher = threading.Thread(target=self._later, name="ergostat-victoria-flush", daemon=True)
                self._flusher.start()

    def add_many(self, rows: list[tuple[str, float, float]]) -> None:
        self.flush()
        for i in range(0, len(rows), 200_000):
            self._import(rows[i:i + 200_000])

    # ---- reading

    def latest(self, series: str, before: float | None = None) -> tuple[float, float] | None:
        self._sync_reads()
        before = before if before is not None else time.time() + 86400
        for back in (3600, 86400, 30 * 86400, None):
            pts = self._export(series, None if back is None else before - back, before).get(series) or []
            if pts:
                return pts[-1]
        return None

    RAW_MOST = 20_000             # readings of one series read one by one, at most; more are bucketed

    def range(self, series: str, since: float, until: float | None = None, last: int | None = None) -> list[tuple[float, float]]:
        """The readings, one by one when there are few (or for the recent ``raw``); otherwise, before
        that, each bucket of the finest tier that keeps them to ``RAW_MOST`` as its last reading."""
        self._sync_reads()
        until = until if until is not None else time.time() + 1
        if last:
            got: list[tuple[float, float]] = []
            for back in (3600, 86400, 30 * 86400, None):
                lo = since if back is None else max(since, until - back)
                got = [p for p in self._export(series, lo, until).get(series) or [] if since <= p[0] <= until]
                if len(got) >= last or lo == since:
                    break
            return got[-last:]
        if not self.tiers or self.count(series, since, until) <= self.RAW_MOST:
            return [p for p in self._export(series, since, until).get(series) or [] if since <= p[0] <= until]
        cut = max(since, time.time() - (self.raw or 0))
        out: list[tuple[float, float]] = []
        if cut > since:
            e = next((e for e, _ in self.tiers if (min(cut, until) - since) / e <= self.RAW_MOST), self.tiers[-1][0])
            sel = self._sel(series)
            vals = self._range(f"last_over_time({sel}[{e:g}s])", since + e - EPS, min(cut, until), e)
            ts = self._range(f"tlast_over_time({sel}[{e:g}s])", since + e - EPS, min(cut, until), e)
            out = sorted((ts[t], v) for t, v in vals.items() if t in ts and since <= ts[t] < cut)
        if until >= cut:
            out += [p for p in self._export(series, cut, until).get(series) or [] if cut <= p[0] <= until]
        return out

    def count(self, series: str | None = None, since: float | None = None, until: float | None = None) -> int:
        self._sync_reads()
        until = until if until is not None else time.time() + 86400
        span = f"{max(1.0, until - since) + EPS:.3f}s" if since is not None else FOREVER
        got = self._query(f"sum(count_over_time({self._sel(series)}[{span}]))", until)
        return int(got[0][1]) if got else 0

    def bucketed(self, series: str, since: float, until: float, n: int) -> list[tuple[int, float, float, float]]:
        self._sync_reads()
        w = (until - since) / max(n, 1) or 1.0
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

    def sampled(self, series: str, since: float, until: float | None = None, points: int = 600) -> list[tuple[float, float]]:
        until = until if until is not None else time.time() + 1
        if self.count(series, since, until) <= points * 2:
            return self.range(series, since, until)
        first, last = self.first(series, since, until), self.latest(series, until)
        mid = [(t, mean) for _, mean, t, _ in self.bucketed(series, since, until, points) if first[0] < t < last[0]]
        return [first, *mid, last]

    def first(self, series: str, since: float, until: float) -> tuple[float, float] | None:
        self._sync_reads()
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
        sel = self._sel()
        n = {m["series"]: v for m, v in self._query(f"count_over_time({sel}[{FOREVER}])", time.time() + 86400)}
        last = {m["series"]: v for m, v in self._query(f"tlast_over_time({sel}[{FOREVER}])", time.time() + 86400)}
        val = {m["series"]: v for m, v in self._query(f"last_over_time({sel}[{FOREVER}])", time.time() + 86400)}
        return [{"series": s, "n": int(n[s]), "last": last.get(s), "value": val.get(s)} for s in sorted(n)]

    def first_time(self) -> float | None:
        self._sync_reads()
        got = self._query(f"min(tfirst_over_time({self._sel()}[{FOREVER}]))", time.time() + 86400)
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
        self._req("/api/v1/admin/tsdb/delete_series", {"match[]": self._sel(series)}, body=b"")
        keep = [(series, t, v) for t, v in pts if (t, v) not in set(bad)]
        if keep:
            self._import(keep)
        note = self.dir / "measurements.forgotten.json"
        old = json.loads(note.read_text()) if note.exists() else []
        note.write_text(json.dumps(old + [{"series": series, "time": t, "value": v, "forgotten_at": time.time()} for t, v in bad]))
        return bad

    def roll(self, now: float | None = None) -> dict:
        return {"rolled": 0, "forgot": 0}               # the server keeps and compresses; buckets are asked for

    def prune(self, before: float) -> int:
        return 0                                         # retention is the server's (-retentionPeriod)

    def drop(self) -> None:
        """Every series of this project, gone (the conformance suite's clean-up)."""
        self._req("/api/v1/admin/tsdb/delete_series", {"match[]": self._sel()}, body=b"")
