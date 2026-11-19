"""The events as an append-only segmented log (SPEC §4b, ``storage: events: segments``): the same
interface as ``store.Events``, without SQLite.

``<state>/events/``:

- ``head.jsonl``: the newest events, one JSON line each, appended under a lock (``lock``, flock), so
  several processes (the runner, the page, the command line) write one record;
- ``seg-<first seq>-<tag>.gz``: a sealed segment of up to ``SEAL`` events, gzip blocks of
  ``BLOCK`` lines each (a block is read alone);
- ``seg-<...>.idx``: its index, written last (a segment without one is not there yet): a JSON
  header (seq and time range, the blocks, each item's and type's rows, a Bloom filter of the ids)
  and the columns (seq, time, item, type, and the rows ordered by item and by type), so a query by
  item, type and time reads only what matches, and only the blocks those rows are in;
- ``seg-<...>.ids``: the ids, a line per row, read only to find one event by its id;
- ``meta.json``: the generation, changed whenever events are taken out (pruned, rolled up).

Readers follow the head by its offset, and see a sealed or rewritten segment by the folder
changing. A roll-up or a prune rewrites the segments it touches (a new name, then the old one
removed); a reader that finds a file gone asks again."""

from __future__ import annotations

import array
import base64
import bisect
import fcntl
import gzip
import hashlib
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

SEAL = 32768              # events per sealed segment
BLOCK = 512               # lines per gzip block
BLOCK_BYTES = 32 << 20    # blocks kept read, by the size of their text (a demo's events can be kilobytes each)
BLOOM_BITS = 10           # per id: about one false hit in a hundred, with K hashes
BLOOM_K = 7
COLS = (("seq", "q"), ("time", "d"), ("item", "i"), ("type", "I"), ("by_item", "I"), ("by_type", "I"), ("pos", "I"))
SNAPSHOT = "ergostat.item.snapshot"
INF = float("inf")


def unpacked(e) -> dict:
    """An event, from the compressed JSON a roll-up keeps its snapshots as (``rollup.packed``)."""
    if isinstance(e, bytes):
        import zlib
        return json.loads(zlib.decompress(e))
    return e


def _hashes(id: str, m: int) -> list[int]:
    h = hashlib.blake2b(id.encode(), digest_size=16).digest()
    a, b = int.from_bytes(h[:8], "little"), int.from_bytes(h[8:], "little") | 1
    return [(a + i * b) % m for i in range(BLOOM_K)]


def _row(e: dict, shared: bool = False) -> dict:
    """An event as every backend returns it; one ``shared`` (the head's, kept in memory) copied, so
    a caller changing what it got changes nothing kept."""
    out = {"seq": e["seq"], "id": e["id"], "time": e["time"], "type": e["type"], "item": e.get("item"),
           "source": e.get("source"), "causedby": e.get("causedby"), "data": e.get("data") or {}}
    for k in ("patch", "set"):
        if e.get(k) is not None:
            out[k] = e[k]
    if shared:
        for k in ("data", "patch", "set"):
            if k in out and out[k]:
                out[k] = json.loads(json.dumps(out[k], default=str))
    return out


def _amount(e) -> float:
    a = (e.get("data") or {}).get("amount")
    return float(a) if a is not None else 1.0


def _decision(e) -> dict:
    d = (e.get("data") or {}).get("decision")
    return {"" if d is None else str(d): 1}


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def _run(e) -> tuple:
    d = e.get("data") or {}
    mine = d.get("why") != "by hand"
    return (1, int(e["type"] == "agent.failed"), int(d.get("refused") or 0) if mine else 0,
            int(d.get("unread") or 0) if mine else 0)


# what each tally adds up, over an item's events of some types: (types, of each event, adding two, nothing yet).
# A segment adds up its own when it is sealed (its header's "tallies"), so a month's window is read from headers.
TALLIES = {
    "opened": ("valve.opened", lambda e: (1, _amount(e), e["time"]),
               lambda a, b: (a[0] + b[0], a[1] + b[1], max(a[2], b[2])), lambda: (0, 0.0, -INF)),
    "decided": ("controller.decided", _decision, _merge, dict),
    "runs": ("agent.ran,agent.failed", _run, lambda a, b: tuple(x + y for x, y in zip(a, b, strict=True)), lambda: (0, 0, 0, 0)),
}


def tallies_of(events: list[dict]) -> dict:
    """Each tally of each item, over these events (a segment's, as it is sealed)."""
    out: dict = {}
    for what, (types, f, add, zero) in TALLIES.items():
        test = _types_matcher(types, ())
        mine: dict = {}
        for e in events:
            if test(e["type"]) and e.get("item") is not None:
                mine[e["item"]] = add(mine.get(e["item"], zero()), f(e))
        out[what] = {k: (v if isinstance(v, dict) else list(v)) for k, v in mine.items()}
    return out


def _types_matcher(type: str | None, skip: tuple[str, ...]):
    """A test of a type: one of ``type`` (comma separated, ``*`` a prefix), none of ``skip``."""
    want = [t.strip() for t in (type or "").split(",") if t.strip()]

    def one(t: str, pat: str) -> bool:
        return t.startswith(pat[:-1]) if pat.endswith("*") else t == pat
    return lambda t: (not want or any(one(t, w) for w in want)) and not any(one(t, s) for s in skip)


class _Head:
    """The head's events in memory, indexed by item and by type (positions only grow: a reader
    takes the length it saw)."""

    def __init__(self, evs=()):
        self.evs: list[dict] = []
        self.seqs: list[int] = []
        self.by_item: dict = {}
        self.by_type: dict = {}
        for e in evs:
            self.add(e)

    def add(self, e: dict) -> None:
        i = len(self.evs)
        self.evs.append(e)
        self.seqs.append(e["seq"])
        self.by_item.setdefault(e.get("item"), []).append(i)
        self.by_type.setdefault(e["type"], []).append(i)

    def __len__(self) -> int:
        return len(self.evs)


class Segment:
    """A sealed segment: its header always in memory, its columns read when asked."""

    def __init__(self, path: Path):
        self.path = path                       # the .idx
        self.name = path.name[:-4]
        with open(path, "rb") as f:
            line = f.readline()
            self.body = len(line)
        h = json.loads(line)
        self.first, self.last, self.count = h["first"], h["last"], h["count"]
        self.t_min, self.t_max = h["t_min"], h["t_max"]
        self.blocks = h["blocks"]
        self.items: list[str | None] = h["items"]          # sorted, None last: found by bisection
        self.types: list[str] = h["types"]
        self._named = len(self.items) - (1 if self.items and self.items[-1] is None else 0)
        self._span = array.array("I", (x for sp in h["item_span"] for x in sp))      # per item: its first row by item, how many
        self._times = array.array("d", (x for t in h["item_times"] for x in t))      # per item: its first and last time
        self.type_span = dict(zip(self.types, (tuple(s) for s in h["type_span"]), strict=True))
        self.bloom = base64.b64decode(h["bloom"])
        self.tallies: dict | None = h.get("tallies")     # what it adds up to, per tally and item (TALLIES); older segments: none
        self.m = len(self.bloom) * 8
        self._cols: dict | None = None

    def at(self, item) -> int | None:
        """Where ``item`` is in ``items``, or None."""
        if item is None:
            return self._named if self._named < len(self.items) else None
        i = bisect.bisect_left(self.items, item, 0, self._named)
        return i if i < self._named and self.items[i] == item else None

    def span(self, item) -> tuple[int, int] | None:
        """``item``'s rows (in by_item order): the first and how many; None when it has none here."""
        i = self.at(item)
        return None if i is None else (self._span[2 * i], self._span[2 * i + 1])

    def times(self, item) -> tuple[float, float]:
        i = self.at(item)
        return self._times[2 * i], self._times[2 * i + 1]

    def spans(self):
        """(item, first row, how many, first time, last time) for each item."""
        sp, ts = self._span, self._times
        for i, it in enumerate(self.items):
            yield it, sp[2 * i], sp[2 * i + 1], ts[2 * i], ts[2 * i + 1]

    def maybe(self, id: str) -> bool:
        return all(self.bloom[i >> 3] & (1 << (i & 7)) for i in _hashes(id, self.m))

    def cols(self) -> dict:
        if self._cols is None:
            raw = self.path.read_bytes()[self.body:]
            out, at = {}, 0
            for name, code in COLS:
                a = array.array(code)
                size = a.itemsize * self.count
                a.frombytes(raw[at:at + size])
                out[name] = a
                at += size
            self._cols = out
        return self._cols

    def gz(self) -> Path:
        return self.path.with_suffix(".gz")


def write_segment(d: Path, events: list[dict]) -> Path:
    """Seal these events (in seq order) as a segment: blocks, ids, index (last). Returns the index."""
    name = f"seg-{events[0]['seq']:012d}-{uuid.uuid4().hex[:8]}"
    gz, ids, idx = d / f"{name}.gz", d / f"{name}.ids", d / f"{name}.idx"
    items = sorted({e.get("item") for e in events}, key=lambda x: (x is None, x or ""))
    types = sorted({e["type"] for e in events})
    item_ix = {x: i for i, x in enumerate(items)}
    type_ix = {x: i for i, x in enumerate(types)}
    by_item = sorted(range(len(events)), key=lambda r: (item_ix[events[r].get("item")], r))
    by_type = sorted(range(len(events)), key=lambda r: (type_ix[events[r]["type"]], r))
    pos = array.array("I", bytes(4 * len(events)))       # each row's place in the blocks, which hold the rows by item:
    for p_, r in enumerate(by_item):                     # one item's events are a block or two, read alone
        pos[r] = p_
    blocks = []
    with open(gz, "wb") as f:
        for i in range(0, len(events), BLOCK):
            body = gzip.compress(("\n".join(json.dumps(events[r], separators=(",", ":"), default=str)
                                            for r in by_item[i:i + BLOCK]) + "\n").encode(), compresslevel=6)
            blocks.append([f.tell(), len(body)])
            f.write(body)
        f.flush()
        os.fsync(f.fileno())
    ids.write_text("\n".join(e["id"] for e in events) + "\n")

    def spans(order, key, names):
        out, at = {}, 0
        for r in order:
            k = key(events[r])
            if k not in out:
                out[k] = [at, 0]
            out[k][1] += 1
            at += 1
        return [out[n] for n in names]
    m = max(64, len(events) * BLOOM_BITS)
    m += -m % 8
    bloom = bytearray(m // 8)
    for e in events:
        for i in _hashes(e["id"], m):
            bloom[i >> 3] |= 1 << (i & 7)
    header = {"first": events[0]["seq"], "last": events[-1]["seq"], "count": len(events),
              "t_min": min(e["time"] for e in events), "t_max": max(e["time"] for e in events), "blocks": blocks,
              "items": items, "types": types, "item_span": spans(by_item, lambda e: e.get("item"), items),
              "type_span": spans(by_type, lambda e: e["type"], types),
              "item_times": [[min(events[r]["time"] for r in by_item[a:a + n]), max(events[r]["time"] for r in by_item[a:a + n])]
                             for a, n in spans(by_item, lambda e: e.get("item"), items)],
              "bloom": base64.b64encode(bytes(bloom)).decode(), "tallies": tallies_of(events)}
    cols = {"seq": array.array("q", (e["seq"] for e in events)), "time": array.array("d", (e["time"] for e in events)),
            "item": array.array("i", (item_ix[e.get("item")] for e in events)),
            "type": array.array("I", (type_ix[e["type"]] for e in events)),
            "by_item": array.array("I", by_item), "by_type": array.array("I", by_type), "pos": pos}
    tmp = idx.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write((json.dumps(header, separators=(",", ":")) + "\n").encode())
        for name_, _ in COLS:
            f.write(cols[name_].tobytes())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, idx)
    return idx


class Segments:
    """``store.Events``'s interface over a segmented log."""

    name = "segments"

    def __init__(self, directory: Path, seal: int = SEAL):
        self.dir = directory / "events"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.head_path = self.dir / "head.jsonl"
        if not self.head_path.exists():                     # made once; a reader opening it leaves it as it was
            self.head_path.touch()
        self.seal = seal
        self._lock = threading.RLock()
        self._head = _Head()
        self._head_off, self._head_ino = 0, None
        self._segs: list[Segment] = []
        self._dir_stamp = None
        self._blocks: OrderedDict = OrderedDict()          # (segment, block): (its lines, their size), at most BLOCK_BYTES
        self._block_bytes = 0
        self._open_cols: OrderedDict = OrderedDict()
        self._tallies: OrderedDict = OrderedDict()
        from .notify import key_of
        self._nkey = key_of(directory)                    # its waiters' board (notify.py)
        self._sync()

    # ---- following the files

    def _sync(self) -> None:
        with self._lock:
            for _ in range(20):
                ino = os.stat(self.head_path).st_ino
                stamp = os.stat(self.dir).st_mtime_ns
                if stamp != self._dir_stamp:
                    have = {s.name: s for s in self._segs}
                    segs = []
                    for p in sorted(self.dir.glob("seg-*.idx")):
                        s = have.get(p.name[:-4])
                        if s is None:
                            try:
                                s = Segment(p)
                            except (OSError, ValueError):
                                continue
                        segs.append(s)
                    self._segs = sorted(segs, key=lambda s: s.first)
                    self._dir_stamp = stamp
                if ino != self._head_ino:
                    self._head, self._head_off, self._head_ino = _Head(), 0, ino
                with open(self.head_path, "rb") as f:
                    f.seek(self._head_off)
                    chunk = f.read()
                end = chunk.rfind(b"\n")
                if end >= 0:
                    sealed = self._segs[-1].last if self._segs else 0
                    for line in chunk[:end].split(b"\n"):
                        if line.strip():
                            e = json.loads(line)
                            if e["seq"] > sealed:
                                self._head.add(e)
                    self._head_off += end + 1
                if os.stat(self.head_path).st_ino == ino and os.stat(self.dir).st_mtime_ns == stamp:
                    sealed = self._segs[-1].last if self._segs else 0
                    if self._head.evs and self._head.evs[0]["seq"] <= sealed:
                        self._head = _Head(e for e in self._head.evs if e["seq"] > sealed)
                    return

    def _state(self) -> tuple[list[Segment], list[dict]]:
        self._sync()
        with self._lock:
            return list(self._segs), self._head.evs[:]

    def _hstate(self) -> tuple[list[Segment], _Head, int]:
        self._sync()
        with self._lock:
            return list(self._segs), self._head, len(self._head)

    @contextmanager
    def _writing(self):
        with self._lock, open(self.dir / "lock", "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                self._sync()
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def _next_seq(self) -> int:
        if self._head.evs:
            return self._head.evs[-1]["seq"] + 1
        return (self._segs[-1].last if self._segs else 0) + 1

    # ---- reading a segment

    def _cols(self, s: Segment) -> dict:
        with self._lock:
            got = self._open_cols.get(s.name)
            if got is not None:
                self._open_cols.move_to_end(s.name)
                return got
        cols = s.cols()
        s._cols = None                                  # kept here, not on the segment, so the cache bounds it
        with self._lock:
            self._open_cols[s.name] = cols
            while len(self._open_cols) > 48:
                self._open_cols.popitem(last=False)
        return cols

    def _block(self, s: Segment, b: int) -> list[str]:
        key = (s.name, b)
        with self._lock:
            got = self._blocks.get(key)
            if got is not None:
                self._blocks.move_to_end(key)
                return got[0]
        off, n = s.blocks[b]
        with open(s.gz(), "rb") as f:
            f.seek(off)
            text = gzip.decompress(f.read(n)).decode()
        evs = [x for x in text.splitlines() if x]                  # parsed when read: never shared
        with self._lock:
            self._blocks[key] = (evs, len(text))
            self._block_bytes += len(text)
            while len(self._blocks) > 1 and (len(self._blocks) > 256 or self._block_bytes > BLOCK_BYTES):
                self._block_bytes -= self._blocks.popitem(last=False)[1][1]
        return evs

    def _event(self, s: Segment, row: int) -> dict:
        p = self._cols(s)["pos"][row]
        return json.loads(self._block(s, p // BLOCK)[p % BLOCK])

    def _rows(self, s: Segment, item=..., types=None, since=None, until=None, after_seq=None, before_seq=None,
              item_test=None) -> list[int]:
        """The rows of ``s`` matching, in seq order; ``types`` a test of a type, ``item_test`` of an item."""
        if since is not None and s.t_max < since or until is not None and s.t_min > until:
            return []
        if after_seq is not None and s.last <= after_seq or before_seq is not None and s.first >= before_seq:
            return []
        want_types = None if types is None else [t for t in s.types if types(t)]
        if want_types is not None and not want_types:
            return []
        if item is not ... and s.span(item) is None:
            return []
        items_ok = None if item_test is None else [i for i, x in enumerate(s.items) if item_test(x)]
        if items_ok is not None and not items_ok:
            return []
        c = self._cols(s)
        if item is not ...:
            a, n = s.span(item)
            rows = list(c["by_item"][a:a + n])
            if want_types is not None and len(want_types) < len(s.types):
                ok = {s.types.index(t) for t in want_types}
                rows = [r for r in rows if c["type"][r] in ok]
        elif items_ok is not None and len(items_ok) < len(s.items) // 4:     # a few items: their rows alone
            rows = sorted(r for i in items_ok for r in c["by_item"][s._span[2 * i]:s._span[2 * i] + s._span[2 * i + 1]])
            items_ok = None
            if want_types is not None and len(want_types) < len(s.types):
                ok = {s.types.index(t) for t in want_types}
                rows = [r for r in rows if c["type"][r] in ok]
        elif want_types is not None and len(want_types) < len(s.types):
            rows = sorted(r for t in want_types for r in (lambda sp: c["by_type"][sp[0]:sp[0] + sp[1]])(s.type_span[t]))
        else:
            rows = range(s.count)
        if items_ok is not None and len(items_ok) < len(s.items):
            ok = set(items_ok)
            rows = [r for r in rows if c["item"][r] in ok]
        t, q = c["time"], c["seq"]
        return [r for r in rows if (since is None or t[r] >= since) and (until is None or t[r] <= until)
                and (after_seq is None or q[r] > after_seq) and (before_seq is None or q[r] < before_seq)]

    def _scan(self, *, n=None, item=..., type=None, skip=(), since=None, until=None, after_seq=None, before_seq=None,
              item_test=None, test=None, limit=None):
        """Matching events, oldest first (the newest ``n``); ``test``, of a whole event, last."""
        types = _types_matcher(type, skip) if type or skip else None
        for attempt in range(3):
            segs, hd, hn = self._hstate()
            # each type and item of the head tested once, not once for each of its events
            ok_types = None if types is None else {t for t in list(hd.by_type) if types(t)}
            ok_items = None if item_test is None else {it for it in list(hd.by_item) if item_test(it)}
            if item is not ...:
                at = hd.by_item.get(item, [])
            elif types is not None and len(ok_types) < len(hd.by_type):
                at = sorted(i for t in ok_types for i in hd.by_type.get(t, ()))
            elif types is not None:                       # every type the head holds: all of it, in order
                at = range(hn)
            elif item_test is not None:
                at = sorted(i for it in ok_items for i in hd.by_item.get(it, ()))
            else:
                at = range(hn)
            lo = bisect.bisect_right(hd.seqs, after_seq, 0, hn) if after_seq is not None else 0   # seqs only grow
            head = [hd.evs[i] for i in at if lo <= i < hn]
            try:
                out: list[dict] = []
                hs = [e for e in head if (item is ... or e.get("item") == item) and (ok_types is None or e["type"] in ok_types)
                      and (ok_items is None or e.get("item") in ok_items)
                      and (since is None or e["time"] >= since) and (until is None or e["time"] <= until)
                      and (after_seq is None or e["seq"] > after_seq) and (before_seq is None or e["seq"] < before_seq)
                      and (test is None or test(e))]
                if n is not None:
                    out = [_row(e, True) for e in hs[-n:]] if n else []
                    for s in reversed(segs):
                        if len(out) >= n:
                            break
                        got = []
                        for r in reversed(self._rows(s, item, types, since, until, after_seq, before_seq, item_test)):
                            e = self._event(s, r)
                            if test is None or test(e):
                                got.append(_row(e))
                                if len(got) + len(out) >= n:
                                    break
                        out = got[::-1] + out
                    return out[-n:] if n else []
                for s in segs:
                    if limit and len(out) >= limit:
                        return out[:limit]
                    for r in self._rows(s, item, types, since, until, after_seq, before_seq, item_test):
                        e = self._event(s, r)
                        if test is None or test(e):
                            out.append(_row(e))
                out += [_row(e, True) for e in hs]
                return out[:limit] if limit else out
            except FileNotFoundError:                    # rewritten under us: ask again
                if attempt == 2:
                    raise
                with self._lock:
                    self._dir_stamp = None
        return []

    # ---- the interface

    def add(self, type: str, *, item: str | None = None, source: str | None = None, data: dict | None = None,
            causedby: str | None = None, at: float | None = None, id: str | None = None, patch: list | None = None,
            set: dict | None = None) -> dict:
        from .store import ChangesetError, changeset
        change = changeset(data, patch, set)
        if change and (not isinstance(item, str) or "/" not in item):
            raise ChangesetError("a patch or a set changes an item: name it (an id with a /, ticket/12)")
        ev = {"id": id or uuid.uuid4().hex, "time": at if at is not None else time.time(), "type": type, "item": item,
              "source": source, "causedby": causedby, "data": data or {}}
        if patch is not None:
            ev["patch"] = patch
        if set is not None:
            ev["set"] = set
        with self._writing():
            if id is not None and self.known([id]):
                ev["seq"] = None
                return ev
            self._append([ev])
        return ev

    def add_many(self, evs: list[dict], new: bool = False) -> int:
        """As ``store.Events.add_many``; ``new``: the caller knows none of them is recorded (a record
        written whole), so their ids are not looked for."""
        from .store import changeset
        rows = []
        for e in evs:
            changeset(e.get("data"), e.get("patch"), e.get("set"))
            ev = {"id": e.get("id") or uuid.uuid4().hex, "time": e["at"] if e.get("at") is not None else time.time(),
                  "type": e["type"], "item": e.get("item"), "source": e.get("source"), "causedby": e.get("causedby"),
                  "data": e.get("data") or {}}
            for k in ("patch", "set"):
                if e.get(k) is not None:
                    ev[k] = e[k]
            rows.append(ev)
        with self._writing():
            given = [] if new else [e["id"] for e, x in zip(rows, evs, strict=True) if x.get("id")]
            have = self.known(given) if given else set()
            fresh, seen = [], set()
            for e in rows:
                if e["id"] in have or e["id"] in seen:
                    continue
                seen.add(e["id"])
                fresh.append(e)
            for i in range(0, len(fresh), self.seal):
                self._append(fresh[i:i + self.seal])
        return len(fresh)

    def _append(self, evs: list[dict]) -> None:
        """Under the lock: number these events and append them to the head; seal it when full."""
        seq = self._next_seq()
        for e in evs:
            e["seq"] = seq
            seq += 1
        body = "".join(json.dumps(e, separators=(",", ":"), default=str) + "\n" for e in evs).encode()
        fd = os.open(self.head_path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, body)
        finally:
            os.close(fd)
        for e in evs:
            self._head.add(e)
        self._head_off += len(body)
        if len(self._head) >= self.seal:
            self._seal()
        from .notify import written
        written(self._nkey)

    def board(self):
        """What waits for this record's new events wakes on (``notify.py``): written here, or by another process."""
        from .notify import board
        b = board(self.dir.parent)
        if b.watcher is None:
            b.watch([self.head_path, self.dir])
        return b

    def _seal(self) -> None:
        while len(self._head) >= self.seal:
            part, rest = self._head.evs[:self.seal], self._head.evs[self.seal:]
            write_segment(self.dir, part)
            self._rewrite_head(rest)
            self._sync()

    def _rewrite_head(self, evs: list[dict]) -> None:
        tmp = self.dir / f"head.{uuid.uuid4().hex[:8]}.tmp"
        tmp.write_bytes("".join(json.dumps(e, separators=(",", ":"), default=str) + "\n" for e in evs).encode())
        os.replace(tmp, self.head_path)
        self._head, self._head_off, self._head_ino = _Head(evs), self.head_path.stat().st_size, os.stat(self.head_path).st_ino

    def known(self, ids: list[str]) -> set[str]:
        """Which of these event ids are recorded."""
        want = set(ids)
        segs, head = self._state()
        out = {e["id"] for e in head if e["id"] in want}
        rest = want - out
        for s in segs:
            if not rest:
                break
            maybe = [i for i in rest if s.maybe(i)]
            if maybe:
                have = set(s.path.with_suffix(".ids").read_text().split())
                got = {i for i in maybe if i in have}
                out |= got
                rest -= got
        return out

    def query(self, *, n: int | None = 100, type: str | None = None, item: str | None = None, source: str | None = None,
              since: float | None = None, after_seq: int | None = None, until: float | None = None,
              skip: tuple[str, ...] = (), unvoided: bool = False, machine: str | None = None,
              before_seq: int | None = None) -> list[dict]:
        tests = []
        if source is not None:
            tests.append(lambda e: e.get("source") == source)
        if machine:
            tests.append(lambda e: (e.get("source") or "") == machine or (e.get("source") or "").startswith(machine + "/"))
        if unvoided:
            void = {v for f in self._scan(type="ergostat.forgotten") for v in (f["data"].get("voids") or [])}
            if void:
                tests.append(lambda e: e["id"] not in void)
        test = (lambda e: all(t(e) for t in tests)) if tests else None
        return self._scan(n=n, item=item if item is not None else ..., type=type, skip=tuple(skip), since=since, until=until,
                          after_seq=after_seq, before_seq=before_seq, test=test)

    def get(self, id: str) -> dict | None:
        segs, head = self._state()
        exact = len(id) >= 32
        for e in reversed(head):
            if e["id"] == id or (not exact and e["id"].startswith(id)):
                return _row(e, True)
        for s in reversed(segs):
            if exact and not s.maybe(id):
                continue
            try:
                ids = s.path.with_suffix(".ids").read_text().split()
            except FileNotFoundError:
                return self.get(id) if self._resync() else None
            for r, x in enumerate(ids):
                if x == id or (not exact and x.startswith(id)):
                    return _row(self._event(s, r))
        return None

    def _resync(self) -> bool:
        with self._lock:
            self._dir_stamp = None
        self._sync()
        return True

    def times(self, items: list[str], type: str, since: float, until: float) -> dict[str, list[tuple[float, str, int]]]:
        """For each of ``items``, (time, type, seq) of its events of ``type`` in the span, in seq order:
        from the segments' columns, no event read, each segment's columns once for all of them."""
        test = _types_matcher(type, ())
        want = set(items)
        out: dict[str, list] = {i: [] for i in items}
        segs, hd, hn = self._hstate()
        for s in segs:
            if s.t_max < since or s.t_min > until:
                continue
            here = [(i, sp) for i in want if (sp := s.span(i)) is not None]
            types = [t for t in s.types if test(t)]
            if not here or not types:
                continue
            ok = {s.types.index(t) for t in types}
            c = self._cols(s)
            tm, ty, sq = c["time"], c["type"], c["seq"]
            for i, (a, n) in here:
                out[i] += [(tm[r], s.types[ty[r]], sq[r]) for r in sorted(c["by_item"][a:a + n])
                           if ty[r] in ok and since <= tm[r] <= until]
        for j in range(hn):
            e = hd.evs[j]
            if e.get("item") in want and test(e["type"]) and since <= e["time"] <= until:
                out[e["item"]].append((e["time"], e["type"], e["seq"]))
        return out

    def caused_by(self, id: str) -> list[dict]:
        return self._scan(test=lambda e: e.get("causedby") == id)

    def items(self, since: float | None = None, own: bool = False) -> list[dict]:
        """Each item: how many events (a snapshot counting what it holds), the first and last, the latest type."""
        segs, head = self._state()
        st: dict[str, list] = {}                          # item: [n, first, last, latest seq, latest type]

        def note(it, n, t0, t1, seq, ty):
            x = st.setdefault(it, [0, INF, -INF, -1, ""])
            x[0] += n
            x[1], x[2] = min(x[1], t0), max(x[2], t1)
            if seq > x[3]:
                x[3], x[4] = seq, ty
        for s in segs:
            c = None
            for it, a, n, t0, t1 in s.spans():
                if it is None or (not own and "/" not in it):
                    continue
                if since is not None and t1 < since:
                    continue
                c = c or self._cols(s)
                last = c["by_item"][a + n - 1]
                note(it, n, t0, t1, c["seq"][last], s.types[c["type"][last]])
                if SNAPSHOT in s.type_span:              # a snapshot counts the events it holds
                    for r in c["by_item"][a:a + n]:
                        if s.types[c["type"][r]] == SNAPSHOT:
                            roll = self._event(s, r)["data"].get("rollup") or {}
                            note(it, roll.get("n", 1) - 1, roll.get("first", t0), t0, -1, "")
        for e in head:
            it = e.get("item")
            if it is None or (not own and "/" not in it) or (since is not None and e["time"] < since):
                continue
            roll = (e["data"].get("rollup") or {}) if e["type"] == SNAPSHOT else {}
            note(it, roll.get("n", 1), roll.get("first", e["time"]), e["time"], e["seq"], e["type"])
        rows = [{"item": k, "n": v[0], "first": v[1], "last": v[2], "latest": v[4]} for k, v in st.items()]
        return sorted(rows, key=lambda r: -r["last"])

    def item_ids(self) -> set[str]:
        """Every item (an id with a ``/``) the record holds an event about: from the segments' headers."""
        segs, hd, hn = self._hstate()
        out = {it for s in segs for it in s.items if it and "/" in it}
        return out | {it for it in list(hd.by_item) if it and "/" in it}

    def last_times(self) -> dict[str, float]:
        """Each item's latest event time, from the segments' headers (``prune``: what is still alive)."""
        segs, hd, hn = self._hstate()
        out: dict[str, float] = {}
        for s in segs:
            for it, _, _, _, t1 in s.spans():
                if it and "/" in it and t1 > out.get(it, -INF):
                    out[it] = t1
        for i in range(hn):
            e = hd.evs[i]
            it = e.get("item")
            if it and "/" in it and e["time"] > out.get(it, -INF):
                out[it] = e["time"]
        return out

    def of_items(self, globs: list[str] | None = None, until: float | None = None, skip: tuple[str, ...] = (),
                 after_seq: int | None = None, limit: int | None = None, ids=None) -> list[dict]:
        """Every event about an item, or about ids matching one of ``globs`` (or among ``ids``), oldest first."""
        if ids is not None:
            want = set(ids)
            return self._scan(item_test=lambda it: it in want, skip=tuple(skip), until=until, after_seq=after_seq or None,
                              limit=limit)
        import fnmatch
        pats = [fnmatch.translate(g) for g in globs] if globs else None
        import re
        rx = re.compile("|".join(pats)) if pats else None
        def test(it) -> bool:
            return isinstance(it, str) and "/" in it and (rx is None or rx.match(it) is not None)
        return self._scan(item_test=test, skip=tuple(skip), until=until, after_seq=after_seq or None, limit=limit)

    def counted(self, prefix: str, until: float | None = None) -> dict[str, tuple[int, float]]:
        """Per item, how many events of types starting ``prefix`` (``claude.*``) and the latest one's time:
        from the columns, never the lines themselves."""
        lo = prefix.rstrip("*")
        until = until if until is not None else INF
        out: dict[str, list] = {}

        def note(it, t):
            if it is not None and t <= until:
                x = out.setdefault(it, [0, -INF])
                x[0] += 1
                x[1] = max(x[1], t)
        segs, hd, hn = self._hstate()
        for s in segs:
            if s.t_min > until or not any(ty.startswith(lo) for ty in s.type_span):
                continue
            whole = s.t_max <= until
            got = self._tallies.get((s.name, "counted", lo)) if whole else None
            if got is None:                               # a sealed segment never changes: what it counts is kept
                got = {}
                c = self._cols(s)
                for ty, (a, n) in s.type_span.items():
                    if ty.startswith(lo):
                        for r in c["by_type"][a:a + n]:
                            t = c["time"][r]
                            if t <= until:
                                it = s.items[c["item"][r]]
                                x = got.get(it, (0, -INF))
                                got[it] = (x[0] + 1, max(x[1], t))
                if whole:
                    with self._lock:
                        self._tallies[(s.name, "counted", lo)] = got
                        while len(self._tallies) > 20_000:
                            self._tallies.popitem(last=False)
            for it, (k, t) in got.items():
                if it is not None:
                    x = out.setdefault(it, [0, -INF])
                    x[0] += k
                    x[1] = max(x[1], t)
        for ty, ix in list(hd.by_type.items()):          # the head's, by its index of types
            if ty.startswith(lo):
                for i in ix:
                    if i < hn:
                        note(hd.evs[i].get("item"), hd.evs[i]["time"])
        return {k: (v[0], v[1]) for k, v in out.items()}

    def count(self) -> int:
        segs, _, hn = self._hstate()
        return sum(s.count for s in segs) + hn

    def first_time(self) -> float | None:
        segs, hd, hn = self._hstate()
        got = [s.t_min for s in segs] + [hd.evs[i]["time"] for i in range(hn)]
        return min(got) if got else None

    def last_seq(self) -> int:
        segs, hd, hn = self._hstate()
        return hd.evs[hn - 1]["seq"] if hn else (segs[-1].last if segs else 0)

    def _tally(self, what: str, item: str, since: float, until: float | None):
        """A tally (``TALLIES``) of an item's events in a span. A sealed segment never changes: what it
        adds up to, when the span holds all of it, is in its header (or, for a segment sealed before
        headers had them, worked out once and kept), so a month's window reads only the segments at its ends."""
        type, f, add, zero = TALLIES[what]
        until = until if until is not None else 1e18
        total = zero()
        segs, hd, hn = self._hstate()
        head = [hd.evs[i] for i in hd.by_item.get(item, ()) if i < hn]    # the head's events about it, by its index
        types = _types_matcher(type, ())
        for s in segs:
            if s.t_max < since or s.t_min > until or s.span(item) is None:
                continue
            whole = since <= s.t_min and s.t_max <= until
            key = (s.name, what, item)
            got = self._tallies.get(key) if whole else None
            if whole and got is None and s.tallies is not None:
                got = s.tallies[what].get(item)
                got = zero() if got is None else got if isinstance(got, dict) else tuple(got)
                total = add(total, got)
                continue
            if got is None:
                got = zero()
                for r in self._rows(s, item, types, since, until):
                    got = add(got, f(self._event(s, r)))
                if whole:
                    with self._lock:
                        self._tallies[key] = got
                        while len(self._tallies) > 20_000:
                            self._tallies.popitem(last=False)
            total = add(total, got)
        for e in head:
            if e.get("item") == item and types(e["type"]) and since <= e["time"] <= until:
                total = add(total, f(e))
        return total

    def opened(self, valve: str, since: float, until: float | None = None) -> dict:
        n, amt, last = self._tally("opened", valve, since, until)
        return {"count": n, "amount": amt, "last": last if n else None}

    def last_opening(self, valve: str, until: float | None = None) -> dict | None:
        until = until if until is not None else 1e18
        got = self._scan(n=1, item=valve, type="valve.opened", until=until)
        if not got:
            return None
        last = got[0]
        if last["causedby"] is None:
            return {"time": last["time"], "count": 1, "amount": _amount(last)}
        cause = self.get(last["causedby"])                 # the run that opened it: its lines are after it began
        since = cause["time"] if cause else last["time"] - 86400
        run = self._scan(item=valve, type="valve.opened", since=since, until=until, test=lambda e: e.get("causedby") == last["causedby"])
        return {"time": last["time"], "count": len(run), "amount": sum(_amount(e) for e in run)}

    def decided(self, controller: str, since: float, until: float | None = None) -> list[tuple[str, int]]:
        return list(self._tally("decided", controller, since, until).items())

    def runs(self, item: str, since: float, until: float | None = None) -> dict:
        r, f, ref, un = self._tally("runs", item, since, until)
        return {"runs": r, "failed": f, "refused": ref, "unread": un}

    # ---- taking events out

    def generation(self) -> int:
        try:
            return json.loads((self.dir / "meta.json").read_text()).get("generation", 0)
        except (OSError, ValueError):
            return 0

    def _bump(self) -> None:
        tmp = self.dir / "meta.tmp"
        tmp.write_text(json.dumps({"generation": self.generation() + 1}))
        os.replace(tmp, self.dir / "meta.json")

    def _edit(self, drop_rows, keep_head, extra: dict[int, dict] | None = None) -> int:
        """Under the lock: rewrite each segment ``drop_rows`` takes rows from (or ``extra``, seq: event,
        puts one in), and the head (keeping what ``keep_head`` keeps). Returns how many went."""
        extra = dict(extra or {})
        gone = 0
        for s in list(self._segs):
            here = {q: e for q, e in extra.items() if s.first <= q <= s.last}
            rows = drop_rows(s)
            if not rows and not here:
                continue
            evs = sorted((json.loads(x) for b in range(len(s.blocks)) for x in self._block(s, b)), key=lambda e: e["seq"])
            new = [e for r, e in enumerate(evs) if r not in rows]
            gone += len(evs) - len(new)
            for q, e in here.items():
                new.append({**unpacked(e), "seq": q})
                extra.pop(q)
                gone -= 1
            new.sort(key=lambda e: e["seq"])
            if new:
                write_segment(self.dir, new)
            for suf in (".idx", ".gz", ".ids"):
                s.path.with_suffix(suf).unlink(missing_ok=True)
            with self._lock:
                self._open_cols.pop(s.name, None)
        head = [e for e in self._head.evs if keep_head(e)]
        gone += len(self._head) - len(head)
        for q, e in extra.items():
            head.append({**unpacked(e), "seq": q})
            gone -= 1
        if len(head) != len(self._head) or extra:
            head.sort(key=lambda e: e["seq"])
            self._rewrite_head(head)
        self._dir_stamp = None
        self._sync()
        return gone

    def replace(self, changes: list[tuple[str, list[int], dict]]) -> None:
        """Roll up (``rollup.py``): for each ``(item, seqs, snapshot)``, those events out and the snapshot in
        their place, at the last one's ``seq``; the segments they were in rewritten."""
        import bisect
        if not changes:
            return
        drop = sorted({q for _, seqs, _ in changes for q in seqs})
        put = {max(seqs): snap if isinstance(snap, bytes) else {**snap, "item": item, "causedby": None}
               for item, seqs, snap in changes}

        def rows(s: Segment) -> set[int]:
            a, b = bisect.bisect_left(drop, s.first), bisect.bisect_right(drop, s.last)
            if a == b:
                return set()
            want = set(drop[a:b])
            return {r for r, q in enumerate(self._cols(s)["seq"]) if q in want}
        gone = set(drop)
        with self._writing():
            self._edit(rows, lambda e: e["seq"] not in gone, put)
            self._bump()

    def prune(self, before: float) -> int:
        """As ``store.Events.prune``: older than ``before``, but the model's history, each loop's last
        crossing, and every item that has anything newer. Only the segments that lose something are
        rewritten, read by their columns."""
        alive = {it for it, t in self.last_times().items() if t >= before}
        last_loop: dict[str | None, int] = {}            # each loop's last crossing, of all time, from the columns
        segs, head = self._state()
        for s in segs:
            c = None
            for t, (a, n) in s.type_span.items():
                if t.startswith("loop."):
                    c = c or self._cols(s)
                    for r in c["by_type"][a:a + n]:
                        it = s.items[c["item"][r]]
                        last_loop[it] = max(last_loop.get(it, 0), c["seq"][r])
        for e in head:
            if e["type"].startswith("loop."):
                last_loop[e.get("item")] = max(last_loop.get(e.get("item"), 0), e["seq"])
        loops = set(last_loop.values())

        def old(it, ty, seq) -> bool:
            if ty == "model.changed":
                return False
            if it and "/" in it:
                return it not in alive
            return seq not in loops

        def rows(s: Segment) -> set[int]:
            if s.t_min >= before:
                return set()
            c = self._cols(s)
            return {r for r in range(s.count) if c["time"][r] < before
                    and old(s.items[c["item"][r]], s.types[c["type"][r]], c["seq"][r])}
        with self._writing():
            gone = self._edit(rows, lambda e: e["time"] >= before or not old(e.get("item"), e["type"], e["seq"]))
            if gone:
                self._bump()
        return gone

    def size(self) -> int:
        return sum(f.stat().st_size for f in self.dir.glob("*") if f.is_file())
