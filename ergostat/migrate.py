"""``ergostat migrate`` (SPEC §4b, *Moving the readings to VictoriaMetrics*): a project's readings copied into
VictoriaMetrics under the names and labels the model gives them (promnames.py), so its own series answer PromQL.

What is copied: every reading the SQLite store answers (``measurements.db``: the raw readings, and where only buckets
are kept, each bucket's last reading, as ``range`` reads them), and any reading VictoriaMetrics holds under a name its
series is no longer written under (the one old name ``ergostat_reading``, the old generic ``ergostat_sensor{part}``, a
part's name before the model changed it), which is moved: written under the current name, then the old deleted, only
once every one of its readings is held under the new. The item metrics written under the old generic names
(``ergostat_items{kind="gap"}``) are moved the same way to their kind's own (``gap_items``). For each series, only the
readings VictoriaMetrics does not already hold under its current name (the same millisecond, and the same value to
``TOL``) are sent, and the series is read back after: a reading the server did not keep (older than its
``-retentionPeriod``, or too far ahead) is not counted as sent but as ``missing``, with its series' span in ``lost``.
So once every reading is held, running it again sends nothing and changes nothing. The SQLite file is only read
(nothing is written or deleted in it): the project goes on with it until its YAML names ``backend: victoriametrics``.
Times are kept to the millisecond, which is all VictoriaMetrics keeps."""

from __future__ import annotations

import math
from pathlib import Path

from .promnames import ITEM, item_labels
from .victoria import Victoria, _q

UNTIL = 1e10                      # (a time past any reading: the year 2286)
TOL = 1e-9                        # relative: the server keeps a value's leading decimal digits, not its binary float


def _held(dst: Victoria, series: str) -> dict[int, list[float]]:
    sel = "{" + f'__name__={_q(dst.labels(series)["__name__"])},project={_q(dst.project)},series={_q(series)}' + "}"
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


def _stale(dst: Victoria) -> dict[str, tuple[set, list]]:
    """Each series' readings held under a name it is no longer written under, and those names."""
    out: dict[str, tuple[set, list]] = {}
    for metric, pts in dst._rows(dst._own(), 0, UNTIL):
        s = metric.get("series", "")
        if metric.get("__name__") != dst.labels(s)["__name__"]:
            names, got = out.setdefault(s, (set(), []))
            names.add(metric["__name__"])
            got += pts
    return out


def _items(dst: Victoria, dry: bool, got: dict) -> int:
    """The item metrics under the old generic names, moved to their kind's own: each sample written under the new,
    read back, and the old deleted only when every one is held (else each sample not held is ``missing``, under
    ``lost["(item metrics)"]``). Returns the series moved (or, ``dry``, to move)."""
    old_sel = "{" + f'__name__=~"{"|".join(sorted(ITEM))}",project={_q(dst.project)},kind!=""' + "}"
    old = dst._rows(old_sel, 0, UNTIL)
    if dry or not old:
        return len(old)
    bare = lambda m: {k: v for k, v in m.items() if k != "project"}   # noqa: E731
    want = {(tuple(sorted(item_labels(bare(m)).items())), round(t * 1000)) for m, pts in old for t, _ in pts}
    dst.put([(bare(m), t, v) for m, pts in old for t, v in pts])          # (put names them for their kind)
    have = {(tuple(sorted(bare(m).items())), round(t * 1000))
            for m, pts in dst._rows("{" + f'project={_q(dst.project)},series=""' + "}", 0, UNTIL) for t, _ in pts}
    if gone := sorted(t / 1000 for _, t in want - have):     # (the old kept: a run later tries again)
        got["missing"] += len(gone)
        got["lost"]["(item metrics)"] = {"n": len(gone), "first": gone[0], "last": gone[-1]}
        return 0
    dst._req("/api/v1/admin/tsdb/delete_series", {"match[]": old_sel}, body=b"")
    return len(old)


def migrate(directory: Path, dst: Victoria, tiers: list | None = None, dry: bool = False) -> dict:
    """The readings of the record in ``directory`` copied into ``dst``: ``{series, readings, sent, renamed, missing,
    lost}`` (the series and readings read; those sent and held; the series moved from an old name; and the readings
    sent that the server did not keep, by series, ``{n, first, last}``), or with ``dry`` what would be sent."""
    got = {"series": 0, "readings": 0, "sent": 0, "renamed": 0, "missing": 0, "lost": {}}
    for series, (names, pts) in sorted(_stale(dst).items()):
        if _send(dst, series, sorted(pts), dry, got):
            got["renamed"] += 1
            if not dry:
                sel = "{" + f'__name__=~"{"|".join(sorted(names))}",project={_q(dst.project)},series={_q(series)}' + "}"
                dst._req("/api/v1/admin/tsdb/delete_series", {"match[]": sel}, body=b"")
    got["renamed"] += _items(dst, dry, got)
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
