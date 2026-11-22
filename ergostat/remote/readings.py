"""A sensor that reads a remote ergostat (a source of ``type: ergostat``, SPEC §4c and §11):
``query: {source: incidents, series: sensor/open.count}`` (a measurement series there) or ``query: {source:
incidents, ref: stock.open}`` (a part's reading as the remote reckons it). Every sensor of one remote is read in
one request a period: the first to read asks for every series and part the model reads of that remote, and the
others take theirs from that answer for half their period. A reading's age is the answer's ``now`` less its
``time``, both in the answerer's clock (never compared with this one): one older than three of the sensor's periods
(two minutes at least), more than five seconds in the answerer's future, with no finite ``time``, in an answer with
no finite ``now``, or marked ``unreachable`` is not taken; a remote that does not answer fails the reading. Either way the
engine keeps the last reading, with its time, and records why.

A middle (an ergostat serving on parts it imported, SPEC §4c *A remote composed of remotes*) keeps each answer
whole in ``<state>/remotes/NAME/readings.json`` (the answerer's instance, when it was got here, and each reading's
age there), marking it ``unreachable`` when the remote stops answering; ``relayed`` serves an imported part's
reading from it with the origin's age carried into this clock (``got - age``), so a hop adds no freshness."""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from . import cache, client

STALE_RUNS, STALE_LEAST, FUTURE_LEAST = 3, 120.0, 5.0
RELAYED = "readings.json"
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


def _num(x) -> bool:
    """A finite number: a NaN or infinite time (JSON takes the literals) would make every age test False."""
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


def keep(d: Path, body: dict | None, why: str) -> None:
    """What the remote answered, kept whole for serving on (``relayed``): the file replaced, never merged. When it
    did not answer, the last answer is kept with ``unreachable`` (its ages and ``got`` as they were)."""
    f = d / RELAYED
    if body is None:
        data = cache._read(f)
        if data is None:
            return
        data["unreachable"] = why or "no answer"
    else:
        now = body.get("now")

        def entry(e) -> dict:
            e = e if isinstance(e, dict) else {}
            age = now - e["time"] if _num(now) and _num(e.get("time")) else None
            return {"value": e.get("value"), "age": age,
                    **({"unreachable": str(e["unreachable"])} if e.get("unreachable") else {})}
        data = {"instance": body.get("instance"), "got": time.time(),
                **{k: {str(n): entry(e) for n, e in body[k].items()} if isinstance(body.get(k), dict) else {}
                   for k in ("series", "refs")}}
    cache._write(f, data)


def relayed(spec, series: str | None = None, ref: str | None = None) -> dict | None:
    """A reading of a part this ergostat imported, served on from what its remote last answered: ``time`` is when
    it was read at the origin, carried into this clock (``got - age``); None when the series or part is this
    ergostat's own. Anything missing answers ``value: null, time: null`` with why."""
    from . import remote_of

    def null(why: str) -> dict:
        return {"value": None, "time": None, "why": why}
    if series:
        s = next((x for x in spec.sensors() if x.series == series), None)
        if s is None:
            return None
        part = f"{s.of.kind}.{s.of.name}"
    else:
        part = str(ref)
    r = remote_of(spec, part)
    if r is None:
        return None
    kind, _, n = part.partition(".")
    if not series:
        if kind == "goal":
            return null(f"goal {n} is reckoned at remote {r}: ask it there")
        t = spec.measured(kind).get(n)
        sensors = t.sensors if t else {}
        s = sensors.get("main") or (next(iter(sensors.values())) if len(sensors) == 1 else None)
        if s is None:
            return null(f"{part} has no one sensor reading it from remote {r}")
    q = s.query or {}
    d = Path(spec.remotes[r]["dir"])
    data = cache._read(d / RELAYED)
    if data is None:
        return null(f"nothing has been read from remote {r} yet")
    have = (cache.model(d) or {}).get("instance")
    if not have or data.get("instance") != have:
        return null(f"what was last read from remote {r} came from instance {data.get('instance')}, not the one its "
                    f"model here is from ({have})")
    e = (data.get("series" if q.get("series") else "refs") or {}).get(q.get("series") or q.get("ref"))
    if not isinstance(e, dict) or not _num(e.get("age")) or not _num(data.get("got")):
        return null(f"remote {r} gave no timed reading of {q.get('series') or q.get('ref')}")
    out = {"value": e.get("value"), "time": data["got"] - e["age"]}
    why = e.get("unreachable") or data.get("unreachable")
    return {**out, "unreachable": str(why)} if why else out


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
                                                                         "ref": ",".join(refs) or None}, timeout=10.0)
            if code != 200 or not isinstance(body, dict):
                body = None
        why = "" if body is not None else f"{src.name} at {src.url}: {why or 'no answer'}"
        _kept[key] = {"t": time.time(), "answer": body, "why": why, "series": series, "refs": refs}
        d = _folder(spec, src.name)
        if d is not None:
            try:
                keep(d, body, why)
            except OSError:
                pass
    if d is not None:
        try:
            cache.note(d, body is not None, why, (body or {}).get("version"))
        except OSError:
            pass
        have = (spec.remotes.get(src.name) or {}).get("version")
        if body is not None and body.get("version") and have and body["version"] != have:   # its model moved: read it now
            r = spec.remotes[src.name]
            threading.Thread(target=cache.refresh, args=(d, r["url"], r.get("token_file"), spec.root, r["every"], True),
                             daemon=True).start()
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
    if not isinstance(got, dict) or got.get("missing"):
        return None, f"{src.name} has no {what}"
    if got.get("unreachable"):
        return None, f"{src.name}'s reading of {what} is not current: {got['unreachable']}"
    if got.get("value") is None:
        return None, f"{src.name} has no reading of {what} yet" + (f" ({got['why']})" if got.get("why") else "")
    now, at = body.get("now"), got.get("time")
    if not _num(now):
        return None, f"{src.name} answered without its own time (now:), so how old {what} is is not known"
    if not _num(at):
        return None, f"{src.name}'s reading of {what} has no time, so it counts as stale"
    from ..durations import human
    age = now - at                                       # both in the answerer's clock
    if not age >= -FUTURE_LEAST:                         # written so an age that is not a number is refused
        return None, f"{src.name}'s reading of {what} is {human(-age)} in its own future (stale)"
    if not age <= max(STALE_LEAST, STALE_RUNS * period):
        return None, f"{src.name}'s reading of {what} is {human(age)} old (stale: its sensor there has not read since)"
    try:
        return float(got["value"]), ""
    except (TypeError, ValueError):
        return None, f"{src.name}: {what} is not a number ({got['value']!r})"
