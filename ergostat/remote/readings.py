"""A sensor that reads a remote ergostat (a source of ``type: ergostat``, SPEC §4c and §11):
``query: {source: incidents, series: sensor/open.count}`` (a measurement series there) or ``query: {source:
incidents, ref: stock.open}`` (a part's reading as the remote reckons it). Every sensor of one remote is read in
one request a period: the first to read asks for every series and part the model reads of that remote, and the
others take theirs from that answer for half their period. A reading older than three of the sensor's periods (two
minutes at least) is stale and is not taken; a remote that does not answer fails the reading. Either way the engine
keeps the last reading, with its time, and records why."""

from __future__ import annotations

import threading
import time

from . import cache, client

STALE_RUNS, STALE_LEAST = 3, 120.0
REFS = ("stock", "flow", "auxiliary", "goal")
_kept: dict[str, dict] = {}            # source name and url: the last answer (when, what it held)
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def check_query(q: dict) -> str | None:
    """Why an ergostat source's query is not one, or None."""
    extra = set(q) - {"source", "series", "ref"}
    if extra:
        return f"an ergostat query takes series: or ref:, not {', '.join(sorted(extra))}"
    if bool(q.get("series")) == bool(q.get("ref")):
        return "an ergostat query names one of series: (a measurement there: sensor/open.count) or ref: (stock.open)"
    if q.get("ref") and str(q["ref"]).split(".")[0] not in REFS:
        return f"ref: {q['ref']} is not one of {', '.join(r + '.NAME' for r in REFS)}"
    return None


def wanted(spec, source: str) -> tuple[list[str], list[str]]:
    """Every series and part the model reads of one source."""
    series, refs = set(), set()
    for s in spec.sensors():
        if s.query and s.query.get("source") == source:
            if s.query.get("series"):
                series.add(str(s.query["series"]))
            elif s.query.get("ref"):
                refs.add(str(s.query["ref"]))
    return sorted(series), sorted(refs)


def _lock(key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def _folder(spec, source: str):
    r = (getattr(spec, "remotes", None) or {}).get(source)
    from pathlib import Path
    return Path(r["dir"]) if r and r.get("dir") else None


def answer(spec, src, period: float) -> tuple[dict | None, str]:
    """The newest answer from this source, asked again when older than half ``period``."""
    key = f"{src.name}|{src.url}"
    with _lock(key):
        got = _kept.get(key)
        series, refs = wanted(spec, src.name)
        if got and time.time() - got["t"] < max(1.0, period / 2) and set(series) <= set(got["series"]) \
                and set(refs) <= set(got["refs"]):
            return got["answer"], got["why"]
        token, why = client.token_of(src.token_file, spec.root)
        body = None
        if token is not None:
            code, body, _, why = client.get(src.url, "readings", token, {"series": ",".join(series) or None,
                                                                         "ref": ",".join(refs) or None}, timeout=10.0,
                                         tls=getattr(src, "tls", None))
            if code != 200:
                body = None
        why = "" if body is not None else f"{src.name} at {src.url}: {why or 'no answer'}"
        _kept[key] = {"t": time.time(), "answer": body, "why": why, "series": series, "refs": refs}
    d = _folder(spec, src.name)
    if d is not None:
        try:
            cache.note(d, body is not None, why, (body or {}).get("version"))
        except OSError:
            pass
        have = (spec.remotes.get(src.name) or {}).get("version")
        if body is not None and body.get("version") and have and body["version"] != have:   # its model moved: read it now
            r = spec.remotes[src.name]
            threading.Thread(target=cache.refresh, args=(d, r["url"], r.get("token_file"), spec.root, r["every"], True),
                             kwargs={"tls": r.get("tls")}, daemon=True).start()
    return body, why


def read(spec, src, s) -> tuple[float | None, str]:
    """One sensor's reading from a remote: the number, or None and why not."""
    period = float(s.every or 60.0)
    body, why = answer(spec, src, period)
    if body is None:
        return None, why
    q = s.query
    got = (body.get("series") or {}).get(q["series"]) if q.get("series") else (body.get("refs") or {}).get(q["ref"])
    what = q.get("series") or q.get("ref")
    if not got or got.get("missing"):
        return None, f"{src.name} has no {what}"
    if got.get("value") is None:
        return None, f"{src.name} has no reading of {what} yet"
    now = float(body.get("now") or time.time())
    if got.get("time") is not None:
        age = now - float(got["time"])
        if age > max(STALE_LEAST, STALE_RUNS * period):
            from ..durations import human
            return None, f"{src.name}'s reading of {what} is {human(age)} old (stale: its sensor there has not read since)"
    try:
        return float(got["value"]), ""
    except (TypeError, ValueError):
        return None, f"{src.name}: {what} is not a number ({got['value']!r})"
