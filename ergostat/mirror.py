"""A mirror's cite id (SPEC §2, the ``collect`` template's ``mirror:``): an outside log's entry recorded once, under an id
that names the log and the entry's position in it, ``cite:<log>:<type>:<position>``.

The log is the sensor that mirrors it (``<flow>.<sensor>``): only that sensor's lines may carry its cites (the engine
checks ``valid``), and nothing pushed may carry a cite at all (``intake/envelope.py``). The type is ``i`` (a whole
number, ordered as one) or ``t`` (text, ordered as text). ``recorded`` finds the greatest position the record holds
of a log: the cursor a collector that lost its memory resumes from."""

from __future__ import annotations

import re

PREFIX = "cite:"
PAGE = 5000                 # events read from the record at a time while looking for a log's greatest cite
TYPES = {"int": "i", "text": "t", "i": "i", "t": "t"}
WHOLE = re.compile(r"^(0|[1-9][0-9]{0,18})$")
TEXT = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
LOG = re.compile(r"^[^:\s]{1,200}$")


class MirrorError(ValueError):
    """Not a position, or not a cite id; or two positions that can't be compared."""


def position(value, type: str) -> int | str:
    """A position as the record keeps it: an ``int`` for ``int`` (``9`` and ``"9"`` alike), the text for ``text``."""
    t = TYPES.get(type)
    if t == "i":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise MirrorError(f"{value!r} is not a whole number (a JSON integer, or its digits as text)")
        if isinstance(value, int):
            if value < 0:
                raise MirrorError(f"{value} is negative: a position is 0 or more")
            return value
        if not WHOLE.match(value):
            raise MirrorError(f"{value!r} is not a whole number's digits (no sign, no leading 0, at most 19)")
        return int(value)
    if t == "t":
        if not isinstance(value, str) or not TEXT.match(value):
            raise MirrorError(f"{value!r} is not a text position (1-128 of letters, digits and ._:+-)")
        return value
    raise MirrorError(f"{type!r}: a position is int or text")


def cite(log: str, type: str, pos) -> str:
    t = TYPES.get(type)
    if not isinstance(log, str) or not LOG.match(log):
        raise MirrorError(f"{log!r}: a log's name has no : or space, 1-200 characters")
    return f"{PREFIX}{log}:{t}:{position(pos, t or type)}"


def parse(id) -> tuple[str, str, int | str]:
    """(log, type, position) of a cite id, the position typed as when it was written; MirrorError when it is not one."""
    if not isinstance(id, str) or not id.startswith(PREFIX):
        raise MirrorError(f"{str(id)[:80]!r} is not a cite id ({PREFIX}LOG:i|t:POSITION)")
    parts = id[len(PREFIX):].split(":", 2)
    if len(parts) != 3 or parts[1] not in ("i", "t") or not LOG.match(parts[0]):
        raise MirrorError(f"{id[:80]!r} is not a cite id ({PREFIX}LOG:i|t:POSITION)")
    return parts[0], parts[1], position(parts[2], parts[1])


def key(type: str, pos, other: str | None = None, log: str = "the log"):
    """The one order of a log's positions: the position itself. ``other``: the type it is compared with, which must
    be the same."""
    if other is not None and other != type:
        raise MirrorError(f"the record cites {log} both as whole numbers and as text")
    return pos


def valid(id, sensor: str) -> str | None:
    """Why ``sensor`` may not record ``id``, or None: a log is bound to the one sensor whose name it carries."""
    try:
        log, _, _ = parse(id)
    except MirrorError as e:
        return str(e)
    return None if log == sensor else f"{id[:120]}: a cite of {log}, and only the sensor {log} records its cites"


def greatest(ids, log: str) -> tuple[str, int | str] | None:
    """The greatest of these cite ids of ``log`` (others are left out): (type, position)."""
    best = None
    for i in ids:
        try:
            lg, t, pos = parse(i)
        except MirrorError:
            continue
        if lg == log and (best is None or key(t, pos, best[0], log) > best[1]):
            best = (t, pos)
    return best


def recorded(events, sensor: str) -> tuple[str, int | str] | None:
    """The greatest cite of ``sensor``'s log in the record, (type, position): its own events (by source, read newest
    first a page at a time), and what the snapshots of rolled-up items kept (``data.rollup.cites``). None only when
    there is none; a store's error is raised."""
    from .spec.items import SNAPSHOT
    best = None

    def take(got):
        nonlocal best
        if got is not None and (best is None or key(got[0], got[1], best[0], sensor) > best[1]):
            best = got
    for kw in ({"source": sensor}, {"type": SNAPSHOT}):
        before = None
        while True:
            page = events.query(n=PAGE, before_seq=before, **kw)
            if not page:
                break
            if "source" in kw:
                take(greatest((e["id"] for e in page if e.get("source") == sensor), sensor))
            else:
                for e in page:
                    v = ((e.get("data") or {}).get("rollup") or {}).get("cites", {}).get(sensor)
                    for i in (v if isinstance(v, list) else [v] if v else []):
                        take(greatest([i], sensor))
            before = page[0]["seq"]
    return best


def kept(old: dict | None, events: list[dict]) -> dict:
    """A snapshot's ``rollup.cites``: per source, the greatest cite of its own log among these events and what the
    snapshot before kept (two ids, a list, when a log was cited both as whole numbers and as text)."""
    by: dict[tuple[str, str], tuple] = {}
    pairs = [(s, i) for s, v in (old or {}).items() for i in (v if isinstance(v, list) else [v])]
    for src, i in pairs + [(e.get("source"), e["id"]) for e in events]:
        try:
            lg, t, pos = parse(i)
        except MirrorError:
            continue
        if lg == src and ((src, t) not in by or pos > by[(src, t)][0]):
            by[(src, t)] = (pos, i)
    out: dict = {}
    for (src, _), (_, i) in sorted(by.items()):
        out[src] = sorted([out[src], i]) if src in out else i
    return out
