"""``ergostat migrate`` (SPEC §4b, *Moving the readings to VictoriaMetrics*): a project's readings copied into
VictoriaMetrics under their names and labels (victoria.promql_name), so ergostat's own series answer PromQL.

What is copied: every reading the SQLite store answers (``measurements.db``: the raw readings, and where only buckets
are kept, each bucket's last reading, as ``range`` reads them), and any reading an earlier VictoriaMetrics record
holds under the one old name (``ergostat_reading``), which is renamed (written under its labels, then the old name
deleted). Idempotent: for each series, only the readings VictoriaMetrics does not already hold under its new name
(the same millisecond and the same value) are sent, so running it again sends nothing and changes nothing. The
SQLite file is only read (nothing is written or deleted in it): the project goes on with it until its YAML names
``backend: victoriametrics``. Times are kept to the millisecond, which is all VictoriaMetrics keeps."""

from __future__ import annotations

from pathlib import Path

from .victoria import OLD_METRIC, Victoria, _q

UNTIL = 1e10                      # (a time past any reading: the year 2286)


def _key(t: float, v: float) -> tuple[int, str]:
    return round(t * 1000), f"{v:.12g}"          # (VictoriaMetrics keeps milliseconds, and its values to 12 digits)


def _held(dst: Victoria, series: str) -> set:
    sel = "{" + f'__name__=~"ergostat_.+",__name__!="{OLD_METRIC}",project={_q(dst.project)},series={_q(series)}' + "}"
    return {_key(t, v) for t, v in dst._export(None, 0, UNTIL, sel=sel).get(series) or []}


def _send(dst: Victoria, series: str, pts: list, dry: bool) -> int:
    held = _held(dst, series)
    rows = [(series, t, v) for t, v in pts if _key(t, v) not in held and not held.add(_key(t, v))]
    if rows and not dry:
        dst.add_many(rows)
    return len(rows)


def migrate(directory: Path, dst: Victoria, tiers: list | None = None, dry: bool = False) -> dict:
    """The readings of the record in ``directory`` copied into ``dst``: ``{series, readings, sent, renamed}`` (the
    series and readings read, those sent, and the old-named series renamed), or with ``dry`` what would be."""
    got = {"series": 0, "readings": 0, "sent": 0, "renamed": 0}
    old = dst._export(None, 0, UNTIL, sel="{" + f'__name__="{OLD_METRIC}",project={_q(dst.project)}' + "}")
    for series, pts in sorted(old.items()):
        got["sent"] += _send(dst, series, pts, dry)
        got["renamed"] += 1
    if old and not dry:
        dst._req("/api/v1/admin/tsdb/delete_series",
                 {"match[]": "{" + f'__name__="{OLD_METRIC}",project={_q(dst.project)}' + "}"}, body=b"")
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
            got["sent"] += _send(dst, series, pts, dry)
    return got
