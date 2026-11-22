"""Rolling up the record (SPEC §4b): an item's events older than a horizon replaced by one
``ergostat.item.snapshot`` event, the originals moved to a compressed archive, and the record kept
to its ``keep``; the measurements rolled into their tiers. The engine does it every ``storage:
rollup: every`` (an hour), and ``ergostat compact`` does it now.

A snapshot is a ``set`` (SPEC §5a: the whole document at once) of the item's document as of the
last event it replaces, with what else the fold keeps in its ``data.rollup``: the state and when it
was entered, every move, the first and last times, how many events, the latest type, what was
refused, and each field's history summarised (how many changes, the first and the last). It takes
the ``seq`` of the last event it replaces, so it folds where they did, and folding it with what
came after gives the same item as folding the originals (``tests/test_rollup.py``). Only a prefix
of the item's events (by ``seq``) all older than the horizon is rolled up. A transcript's lines
(``claude.*``) are rolled up with the rest, and the snapshot keeps both folds: without them (its
``set``, what counting items reads) and with them (``rollup.transcript``).

The archive: ``archive/<kind>/<YYYY-MM>.jsonl.gz`` (gzip members appended, one per roll-up, an
event per line) and ``<YYYY-MM>.idx.jsonl`` beside it (per item and member: where it is, how many,
first and last time). The item page's full history reads it (``archived``)."""

from __future__ import annotations

import gzip
import json
import os
import re
import time
import uuid
from pathlib import Path

from . import mirror
from .spec.items import SNAPSHOT, TRANSCRIPT_TYPES, field_of, fold, kind_of
from .store import KEPT  # (an item holding an operating state's events is never rolled up: operating/trips.py)

MIN_EVENTS = 2              # a prefix of fewer events is left as it is: one event is already as small as a snapshot


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "_"


def _month(t: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(t))


class Archive:
    """The events rolled up out of the record, per item kind and month, compressed."""

    def __init__(self, directory: Path):
        self.dir = directory / "archive"

    def write(self, kind: str, events: list[dict]) -> list[str]:
        """Append these events (several items') to their months' segments: one gzip member per month,
        and an index line per item in it. Returns the segments written (``kind/YYYY-MM``)."""
        by: dict[str, dict[str, list[dict]]] = {}
        for e in events:
            by.setdefault(_month(e["time"]), {}).setdefault(e["item"], []).append(e)
        out = []
        d = self.dir / _safe(kind)
        d.mkdir(parents=True, exist_ok=True)
        for month, items in sorted(by.items()):
            seg, idx = d / f"{month}.jsonl.gz", d / f"{month}.idx.jsonl"
            lines, spans = [], []
            for item, evs in sorted(items.items()):
                lines += [json.dumps(e, separators=(",", ":"), default=str) for e in evs]
                spans.append((item, len(evs), min(e["time"] for e in evs), max(e["time"] for e in evs)))
            body = gzip.compress(("\n".join(lines) + "\n").encode(), compresslevel=6)
            with open(seg, "ab") as f:
                off = f.seek(0, os.SEEK_END)
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            with open(idx, "a") as f:
                for item, n, t0, t1 in spans:
                    f.write(json.dumps({"item": item, "off": off, "len": len(body), "n": n, "first": t0, "last": t1}) + "\n")
            out.append(f"{_safe(kind)}/{month}")
        return out

    def read(self, item: str, segments: list[str] | None = None) -> list[dict]:
        """Every archived event of ``item``, oldest first (by ``seq``), from the segments named (else all)."""
        names = segments if segments is not None else [f"{d.name}/{f.name.split('.')[0]}" for d in self.dir.glob("*")
                                                       for f in d.glob("*.idx.jsonl")]
        seen: dict[str, dict] = {}
        for name in names:
            seg, idx = self.dir / f"{name}.jsonl.gz", self.dir / f"{name}.idx.jsonl"
            if not idx.exists() or not seg.exists():
                continue                                # forgotten (older than keep)
            members = set()
            for line in idx.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r["item"] == item:
                    members.add((r["off"], r["len"]))
            with open(seg, "rb") as f:
                for off, n in sorted(members):
                    f.seek(off)
                    try:
                        text = gzip.decompress(f.read(n)).decode()
                    except (OSError, EOFError):
                        continue
                    for line in text.splitlines():
                        if f'"item":{json.dumps(item)}' in line:
                            e = json.loads(line)
                            if e.get("item") == item:
                                seen[e["id"]] = e
        return sorted(seen.values(), key=lambda e: (e.get("seq") or 0, e["time"]))

    def forget(self, before: float) -> int:
        """Drop the months that ended before ``before``. Returns how many segments went."""
        cut, n = _month(before), 0
        for d in self.dir.glob("*"):
            for f in list(d.glob("*.jsonl.gz")):
                month = f.name.split(".")[0]
                if month < cut:
                    f.unlink(missing_ok=True)
                    (d / f"{month}.idx.jsonl").unlink(missing_ok=True)
                    n += 1
        return n

    def size(self) -> int:
        return sum(f.stat().st_size for f in self.dir.rglob("*") if f.is_file()) if self.dir.exists() else 0


def summarise(it) -> dict:
    """Each field's history, summarised: how many changes, the first and the last (time, event, type)."""
    out: dict[str, dict] = {}
    for c in it.changes:
        f = field_of(c["path"])
        if c.get("op") == "rolled up":               # an earlier snapshot's summary
            h = out.setdefault(f, {"changes": 0, "first": c["first"], "last": c["last"]})
            h["changes"] += c["count"]
            h["last"] = c["last"]
            continue
        at = {"time": c["time"], "event": c["event"], "type": c["type"]}
        h = out.setdefault(f, {"changes": 0, "first": at, "last": at})
        h["changes"] += 1
        h["last"] = at
    return out


def _meta(it) -> dict:
    return {"state": it.state, "entered": it.entered, "first": it.first, "last": it.last, "n": it.n, "latest": it.latest,
            "moves": it.moves, "refused": it.refused, "fields": summarise(it)}


def snapshot_of(id: str, prefix: list[dict], kind, segments: list[str], now: float) -> dict:
    """The snapshot that replaces ``prefix`` (an item's oldest events, by ``seq``): its document and
    the fold's state without the transcript's lines, and, when it has some, the fold with them."""
    line = lambda e: e["type"].startswith(TRANSCRIPT_TYPES[:-1])           # noqa: E731
    own = fold(id, [e for e in prefix if not line(e)], kind, history=True, transcript=False)
    old = next((e["data"].get("rollup") or {} for e in prefix if e["type"] == SNAPSHOT), {})
    archived = (old.get("archived") or {}).get("events", 0) + sum(1 for e in prefix if e["type"] != SNAPSHOT)
    lines = old.get("lines", 0) + sum(1 for e in prefix if line(e))
    rollup = {**_meta(own), "lines": lines,
              "archived": {"events": archived, "segments": sorted({*(old.get("archived") or {}).get("segments", []), *segments})},
              "made": now}
    cites = mirror.kept(old.get("cites"), [e for e in prefix if e["type"] != SNAPSHOT])
    if cites:                                   # a mirror's greatest position, so it resumes from it (mirror.recorded)
        rollup["cites"] = cites
    if lines:
        whole = fold(id, prefix, kind, history=True, transcript=True)
        rollup["transcript"] = {**_meta(whole), "set": whole.fields}
    return {"id": uuid.uuid4().hex, "type": SNAPSHOT, "item": id, "time": max(e["time"] for e in prefix), "source": "ergostat",
            "data": {"rollup": rollup}, "set": own.fields}


BATCH = 20_000              # items read from the record at a time (a range of ids: the blocks that hold them)
FLUSH = 1_000_000           # snapshots put into the record at a time (each time rewrites the segments they are in)


def candidates(p, now: float, cap: float | None) -> list[str] | None:
    """The items a roll-up could take, from the item index: those whose first event since their
    snapshot (or ever) is older than their horizon, and those with a transcript's lines (which the
    index does not fold). None when there is no index: every item is looked at."""
    from .spec.itemindex import index_for
    cfg = p.storage
    ix = index_for(p.events, getattr(p.model, "spec", None), False)
    if ix is None:
        return None
    with ix.lock:
        rows = ix.candidates()
    out = set()
    for id, kind, t in rows:
        h = cfg.horizon(kind)
        if h is None and cap is None:
            continue
        if t is not None and t < now - min(x for x in (h, cap) if x is not None):
            out.add(id)
    out |= set(p.events.counted(TRANSCRIPT_TYPES))
    return sorted(out)


def batches(p, now: float | None = None, cap: float | None = None):
    """What a roll-up would take, a batch of items at a time: per item, its kind and the prefix of its
    events (by ``seq``, a transcript's lines among them) all older than its horizon (``cap``: never
    later than this). Only the items the index names are read (``candidates``)."""
    now = now if now is not None else time.time()
    cfg = p.storage
    spec = getattr(p.model, "spec", None)
    ids = candidates(p, now, cap)
    for i in range(0, len(ids) if ids is not None else 1, BATCH):
        by: dict[str, list[dict]] = {}
        for e in p.events.of_items(None, ids=ids[i:i + BATCH] if ids is not None else None):
            by.setdefault(e["item"], []).append(e)
        out = []
        for id, evs in by.items():
            k = kind_of(spec, id) if spec is not None and getattr(spec, "items", None) else None
            h = cfg.horizon(k.name if k else None)
            if h is None and cap is None:
                continue
            cut = now - min(x for x in (h, cap) if x is not None)
            prefix = []
            for e in evs:
                if e["time"] >= cut:
                    break
                prefix.append(e)
            originals = sum(1 for e in prefix if e["type"] != SNAPSHOT)
            if originals == 0 or len(prefix) < MIN_EVENTS or any(e["type"].startswith(KEPT) for e in prefix):
                continue
            out.append((id, k, prefix, evs[len(prefix):]))
        if out:
            yield out


def plan(p, now: float | None = None, cap: float | None = None) -> list[tuple[str, object, list[dict]]]:
    """Every batch of ``batches`` at once: per item, its kind and the prefix a roll-up takes."""
    return [(id, k, pre) for b in batches(p, now, cap) for id, k, pre, _ in b]


def compact(p, now: float | None = None, cap: float | None = None, dry: bool = False) -> dict:
    """Roll every item's old events up into its snapshot, archiving the originals. Returns what it did.
    A batch of items at a time is read, archived and made into snapshots; the record is rewritten once."""
    now = now if now is not None else time.time()
    began = time.time()
    done = {"items": 0, "events": 0}
    arc = Archive(p.dir)
    changes, rest = [], {}
    for todo in batches(p, now, cap):
        done["items"] += len(todo)
        done["events"] += sum(sum(1 for e in pre if e["type"] != SNAPSHOT) for _, _, pre, _ in todo)
        if dry:
            continue
        by_kind: dict[str, list] = {}
        for id, k, pre, after in todo:
            by_kind.setdefault(k.name if k else "unkinded", []).append((id, k, pre))
            rest[id] = [(e["seq"], e["time"]) for e in after if not e["type"].startswith(TRANSCRIPT_TYPES[:-1])]
        for kind, rows in by_kind.items():
            segs = arc.write(kind, [e for *_, pre in rows for e in pre if e["type"] != SNAPSHOT])
            for id, k, pre in rows:
                months = {f"{_safe(kind)}/{_month(e['time'])}" for e in pre if e["type"] != SNAPSHOT}
                changes.append((id, [e["seq"] for e in pre], packed(snapshot_of(id, pre, k, sorted(months & set(segs)), now))))
        if len(changes) >= FLUSH:
            _replace(p, changes, rest)
            changes, rest = [], {}
    if dry or not done["items"]:
        return {**done, "seconds": time.time() - began}
    _replace(p, changes, rest)
    return {**done, "seconds": time.time() - began, "archive_bytes": arc.size()}


def packed(snap: dict) -> bytes:
    """A snapshot as a roll-up keeps it until it is put into the record: compressed JSON, a tenth of the
    dict's size (a first roll-up of 800,000 items held 9.7 GB of them as dicts)."""
    import zlib
    return zlib.compress(json.dumps({**snap, "causedby": None}, separators=(",", ":"), default=str).encode(), 1)


def _replace(p, changes: list, rest: dict) -> None:
    """The snapshots into the record in place of their events; the item index told what is left of each."""
    if not changes:
        return
    p.events.replace(changes)
    from .spec.itemindex import index_for
    ix = index_for(p.events, getattr(p.model, "spec", None), False)
    if ix is not None:                          # what is left of each outside its snapshot: not to be looked at again till due
        ix.rolled(rest)


def archived(p, id: str, offset: int = 0, n: int = 200) -> dict | None:
    """``GET /api/items/<id>?archived=1``: the item's full history, a page at a time: the events
    rolled up into its snapshot (from the archive), then those still in the record."""
    snap = p.events.query(n=1, item=id, type=SNAPSHOT)
    live = [e for e in p.events.query(n=None, item=id) if e["type"] != SNAPSHOT]
    if not snap and not live:
        return None
    segs = (snap[0]["data"].get("rollup") or {}).get("archived", {}).get("segments") if snap else []
    old = Archive(p.dir).read(id, segs) if segs else []
    every = old + live
    return {"item": id, "total": len(every), "archived": len(old), "offset": offset, "events": every[offset:offset + n]}


def upkeep(p, now: float | None = None) -> dict:
    """What the engine does every ``storage: rollup: every``: roll items up (never keeping more than
    ``keep`` outside a snapshot), forget what is older than ``keep``, and roll the measurements into
    their tiers."""
    now = now if now is not None else time.time()
    keep = p.model.keep
    out = {"rollup": compact(p, now, cap=keep), "pruned": p.events.prune(now - keep),
           "archive_forgot": Archive(p.dir).forget(now - keep)}
    if hasattr(p.measurements, "roll"):
        out["measurements"] = p.measurements.roll(now)
    return out


def vacuum(p) -> int:
    """``ergostat compact``: the SQLite stores' files made as small as what they hold."""
    from .store import vacuum as one
    return one(p.events) + one(p.measurements)
