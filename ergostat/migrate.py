"""``ergostat migrate`` (SPEC §4b, *Moving the readings to VictoriaMetrics*): a project's readings copied into
VictoriaMetrics under their names and labels (victoria.promql_name), so ergostat's own series answer PromQL.

What is copied: every reading the SQLite store answers (``measurements.db``: the raw readings, and where only buckets
are kept, each bucket's last reading, as ``range`` reads them), and any reading an earlier VictoriaMetrics record
holds under the one old name (``ergostat_reading``), which is renamed (written under its labels, then the old name
deleted, only once every one of its readings is held under the new). For each series, only the readings
VictoriaMetrics does not already hold under its new name (the same millisecond, and the same value to ``TOL``) are
sent, and the series is read back after: a reading the server did not keep (older than its ``-retentionPeriod``, or
too far ahead) is not counted as sent but as ``missing``, with its series' span in ``lost``. So once every reading is
held, running it again sends nothing and changes nothing. The SQLite file is only read (nothing is written or deleted
in it): the project goes on with it until its YAML names ``backend: victoriametrics``. Times are kept to the
millisecond, which is all VictoriaMetrics keeps."""

from __future__ import annotations

import math
from pathlib import Path

from .victoria import OLD_METRIC, Victoria, _q

UNTIL = 1e10                      # (a time past any reading: the year 2286)
TOL = 1e-9                        # relative: the server keeps a value's leading decimal digits, not its binary float


def _held(dst: Victoria, series: str) -> dict[int, list[float]]:
    sel = "{" + f'__name__=~"ergostat_.+",__name__!="{OLD_METRIC}",project={_q(dst.project)},series={_q(series)}' + "}"
    out: dict[int, list[float]] = {}
    for t, v in dst._export(None, 0, UNTIL, sel=sel).get(series) or []:
        out.setdefault(round(t * 1000), []).append(v)
    return out


def _has(held: dict, t: float, v: float) -> bool:
    return any(math.isclose(v, w, rel_tol=TOL) or (math.isnan(v) and math.isnan(w)) for w in held.get(round(t * 1000), ()))


def _send(dst: Victoria, series: str, pts: list, dry: bool, got: dict) -> bool:
    """The readings of ``series`` the server lacks, sent and read back: whether it holds every one after."""
    held = _held(dst, series)
    rows = []
    for t, v in pts:
        if not _has(held, t, v):
            rows.append((series, t, v))
            held.setdefault(round(t * 1000), []).append(v)
    if dry or not rows:
        got["sent"] += len(rows)
        return True
    dst.add_many(rows)
    after = _held(dst, series)
    lost = [t for _, t, v in rows if not _has(after, t, v)]
    got["sent"] += len(rows) - len(lost)
    if lost:
        got["missing"] += len(lost)
        got["lost"][series] = {"n": len(lost), "first": min(lost), "last": max(lost)}
    return not lost


def migrate(directory: Path, dst: Victoria, tiers: list | None = None, dry: bool = False) -> dict:
    """The readings of the record in ``directory`` copied into ``dst``: ``{series, readings, sent, renamed, missing,
    lost}`` (the series and readings read; those sent and held; the old-named series renamed; and the readings sent
    that the server did not keep, by series, ``{n, first, last}``), or with ``dry`` what would be sent."""
    got = {"series": 0, "readings": 0, "sent": 0, "renamed": 0, "missing": 0, "lost": {}}
    old_sel = "{" + f'__name__="{OLD_METRIC}",project={_q(dst.project)}' + "}"
    old = dst._export(None, 0, UNTIL, sel=old_sel)
    whole = all([_send(dst, series, pts, dry, got) for series, pts in sorted(old.items())])
    if old and whole:
        got["renamed"] = len(old)
        if not dry:
            dst._req("/api/v1/admin/tsdb/delete_series", {"match[]": old_sel}, body=b"")
    if (Path(directory) / "measurements.db").exists():
        from .store import Measurements
        src = Measurements(Path(directory), tiers=tiers)
        with src._c() as c:
            names = sorted({r[0] for q in ("select distinct series from samples", "select distinct series from tiers")
                            for r in c.execute(q)})
        for series in names:
            pts = src.range(series, 0, UNTIL)
            got["series"] += 1
            got["readings"] += len(pts)
            _send(dst, series, pts, dry, got)
    return got
