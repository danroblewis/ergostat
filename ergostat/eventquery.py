"""The query engine over the whole record (SPEC §5a, *The query engine*): ``POST /api/events/query``.

A query is an expression of the event, in the handlers' language (``spec/handlers.py``): ``data``, ``type``, ``key``,
``source``, ``time``, missing paths null. It is never answered by reading the whole record: an index of its own
(``<state>/eventquery.db``) holds, per event, a posting for each value at the paths queries and ``when:``s use (the
event's ``type``, ``source`` and ``key``, and its data's paths to three levels deep, at most ``POSTINGS`` of them), kept
up to date as events are recorded (caught up from the record's last indexed ``seq`` before each answer: a constant cost
per event). A query is planned over its expression: ``path == value``, ``path != value``, ``path.startswith(text)``,
``glob(path, pattern)``, ``has(text)`` (from a trigram index of each event's text values, lower-cased: exact for text
of three characters or more), ``not``, ``and`` and ``or`` of them read their candidates from the index; a candidate set
that the index answers exactly (every part of the expression one of those, on an indexed path) needs no event read but
the ones shown; otherwise the expression is evaluated on the candidates (at most ``EVALUATE_MOST``, the newest first).
A query no part of which the index can answer is a scan (``scanned: true``), of the newest ``SCAN_MOST`` events.

The answer: the matching events, newest first (``limit``, at most ``LIMIT_MOST``), the total, how it was answered,
and, given ``compare`` (an earlier query), how many events this one adds and drops against it."""

from __future__ import annotations

import ast
import json
import random
import sqlite3
import threading
import time
from pathlib import Path

INDEX = "eventquery.db"
VERSION = 2
POSTINGS = 64              # the most postings one event writes (its paths beyond are not indexed)
DEPTH = 3                  # data paths indexed: data.a, data.a.b, data.a.b.c
TEXT_MOST = 100            # text longer than this is indexed by its first TEXT_MOST characters (as a prefix)
CHUNK = 20_000             # events indexed per transaction while catching up
EVALUATE_MOST = 100_000    # candidates an expression is evaluated on, at most (the newest)
SCAN_MOST = 50_000         # events a query the index cannot answer reads, at most (the newest)
LIMIT_MOST = 500           # events an answer lists, at most
SCHEMA = """
create table if not exists meta (key text primary key, value);
create table if not exists paths (id integer primary key, path text unique not null);
create table if not exists ev (seq integer primary key, id text, time real, type text, item text, source text, data text);
create index if not exists ev_time on ev(time);
create table if not exists post (p integer not null, v text not null, seq integer not null);
create index if not exists post_pv on post(p, v, seq);
create virtual table if not exists txt using fts5(t, tokenize='trigram case_sensitive 1', content='', detail=full);
"""
SEP = "\x1f"               # between an event's texts in its text row (a searched text never holds it: no match spans two)
RESET = "delete from ev; delete from post; delete from paths; delete from meta; insert into txt(txt) values('delete-all');"
_LOCK = threading.RLock()   # also held through a query: one connection, shared by the server's threads


class QueryError(ValueError):
    """A query that does not parse, or uses what the expression language does not allow."""


# ---- values as the index keeps them

def canon(v) -> str | None:
    """A value's key in the index: text ``s...`` (``t...``: the first TEXT_MOST characters of longer text), a number
    ``n...`` (1 and 1.0 the same), a boolean ``b1``/``b0``, null ``z``; a list or an object ``c`` (only that the path
    is there)."""
    if v is None:
        return "z"
    if isinstance(v, bool):
        return "b1" if v else "b0"
    if isinstance(v, (int, float)):
        return "n" + (str(int(v)) if float(v).is_integer() and abs(v) < 1e15 else repr(float(v)))
    if isinstance(v, str):
        return ("s" + v) if len(v) <= TEXT_MOST else ("t" + v[:TEXT_MOST])
    return "c"


def postings(e: dict) -> list[tuple[str, str]]:
    """The (path, value key) pairs an event is indexed under: its type, source and key, and its data's paths to DEPTH
    levels (a list or an object: that it is there), at most POSTINGS."""
    out = [("type", canon(e.get("type")))]
    if e.get("source") is not None:
        out.append(("source", canon(e.get("source"))))
    if e.get("item") is not None:
        out.append(("key", canon(e.get("item"))))
    stack = [("data", e.get("data") if isinstance(e.get("data"), dict) else {}, 0)]
    while stack and len(out) < POSTINGS:
        path, d, depth = stack.pop(0)
        for k, v in d.items():
            if len(out) >= POSTINGS:
                break
            p = f"{path}.{k}"
            out.append((p, canon(v)))
            if isinstance(v, dict) and depth + 1 < DEPTH:
                stack.append((p, v, depth + 1))
    return out


def text_of(e: dict) -> str:
    """An event's text row, what ``has(TEXT)`` is answered from: its text values (type, key, source, data's,
    nested), lower-cased, SEP between them."""
    from .spec.handlers import event_texts
    return SEP.join(t.replace(SEP, " ").lower() for t in event_texts(_env(e)))


# ---- the index

def state_dir(events) -> Path | None:
    from .spec.itemindex import state_dir as sd
    return sd(events)


class Index:
    def __init__(self, events):
        self.events = events
        d = state_dir(events)
        self.path = (d / INDEX) if d is not None else None
        self.db = sqlite3.connect(str(self.path) if self.path else ":memory:", check_same_thread=False, timeout=30)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma synchronous=normal")
        self.db.executescript(SCHEMA)
        self._paths: dict[str, int] = {p: i for i, p in self.db.execute("select id, path from paths")}
        self.upkeep = {"events": 0, "seconds": 0.0}

    def _meta(self, k, default=None):
        r = self.db.execute("select value from meta where key = ?", (k,)).fetchone()
        return r[0] if r else default

    def _pid(self, path: str, make: bool = True) -> int | None:
        i = self._paths.get(path)
        if i is None and make:
            i = self.db.execute("insert into paths(path) values (?)", (path,)).lastrowid
            self._paths[path] = i
        return i

    def catch_up(self) -> int:
        """Every event recorded since the last one indexed, indexed; how many. The record gone back (a fresh one,
        events taken out) rebuilds it."""
        gen = getattr(self.events, "generation", lambda: 0)()
        if self._meta("version") != VERSION or self._meta("generation", gen) != gen:
            self.db.executescript(RESET)
            self._paths = {}
        last = int(self._meta("last", 0) or 0)
        if last > self.events.last_seq():
            self.db.executescript(RESET)
            self._paths, last = {}, 0
        n = 0
        while True:
            evs = self.events.query(n=None, after_seq=last, first=CHUNK)
            if not evs:
                break
            t0 = time.perf_counter()
            self.db.execute("begin immediate")
            try:
                self.db.executemany("insert or replace into ev(seq, id, time, type, item, source, data) values (?,?,?,?,?,?,?)",
                                    [(e["seq"], e["id"], e["time"], e["type"], e.get("item"), e.get("source"),
                                      json.dumps(e.get("data") or {}, separators=(",", ":"), default=str)) for e in evs])
                rows = []
                for e in evs:
                    for p, v in postings(e):
                        rows.append((self._pid(p), v, e["seq"]))
                self.db.executemany("insert into post(p, v, seq) values (?,?,?)", rows)
                self.db.executemany("insert into txt(rowid, t) values (?, ?)", [(e["seq"], text_of(e)) for e in evs])
                last = evs[-1]["seq"]
                self.db.executemany("insert or replace into meta(key, value) values (?, ?)",
                                    [("last", last), ("version", VERSION), ("generation", gen)])
                self.db.execute("commit")
            except BaseException:
                self.db.execute("rollback")
                raise
            self.upkeep["events"] += len(evs)
            self.upkeep["seconds"] += time.perf_counter() - t0
            n += len(evs)
        return n

    # ---- reading it

    def lookup(self, path: str, value) -> set[int]:
        p = self._pid(path, make=False)
        if p is None:
            return set()
        return {r[0] for r in self.db.execute("select seq from post where p = ? and v = ?", (p, canon(value)))}

    def prefixed(self, path: str, prefix: str) -> set[int]:
        p = self._pid(path, make=False)
        if p is None:
            return set()
        out: set[int] = set()
        for tag in ("s", "t"):
            lo = tag + prefix
            out |= {r[0] for r in self.db.execute("select seq from post where p = ? and v >= ? and v < ?",
                                                  (p, lo, lo + "\U0010ffff"))}
        return out

    def containing(self, text: str) -> set[int] | None:
        """The events some text of which contains ``text`` (lower-cased), from the trigram index: exact for text of
        three characters or more; None for shorter (the index cannot say)."""
        t = text.lower()
        if len(t) < 3 or SEP in t:
            return None
        return {r[0] for r in self.db.execute("select rowid from txt where txt match ?", ('"' + t.replace('"', '""') + '"',))}

    def present(self, path: str) -> set[int]:
        p = self._pid(path, make=False)
        if p is None:
            return set()
        return {r[0] for r in self.db.execute("select seq from post where p = ? and v != 'z'", (p,))}

    def all(self) -> set[int]:
        return {r[0] for r in self.db.execute("select seq from ev")}

    def window(self, since: float | None, until: float | None) -> set[int] | None:
        if since is None and until is None:
            return None
        return {r[0] for r in self.db.execute("select seq from ev where time >= ? and time <= ?",
                                              (since if since is not None else -1e300, until if until is not None else 1e300))}

    def newest(self, n: int, since: float | None = None, until: float | None = None) -> list[int]:
        return [r[0] for r in self.db.execute("select seq from ev where time >= ? and time <= ? order by seq desc limit ?",
                                              (since if since is not None else -1e300,
                                               until if until is not None else 1e300, n))]

    def events_of(self, seqs: list[int]) -> list[dict]:
        out: dict[int, dict] = {}
        for i in range(0, len(seqs), 500):
            part = seqs[i:i + 500]
            for r in self.db.execute(f"select seq, id, time, type, item, source, data from ev where seq in "
                                     f"({','.join('?' * len(part))})", part):
                out[r[0]] = {"seq": r[0], "id": r[1], "time": r[2], "type": r[3], "item": r[4], "source": r[5],
                             "data": json.loads(r[6] or "{}")}
        return [out[s] for s in seqs if s in out]

    def count(self) -> int:
        return self.db.execute("select count(*) from ev").fetchone()[0]

    def close(self) -> None:
        self.db.close()


_OPEN: dict[str, Index] = {}


def index_for(events) -> Index:
    """The record's query index, kept open, caught up."""
    d = state_dir(events)
    k = str(d) if d is not None else f"mem:{id(events)}"
    with _LOCK:
        ix = _OPEN.get(k)
        if ix is None or ix.events is not events:
            if ix is not None:
                ix.close()
            ix = _OPEN[k] = Index(events)
        ix.catch_up()
        return ix


# ---- planning

def compile_query(text: str):
    """A query's expression (handlers.Value); QueryError when it is not one."""
    from .spec.handlers import BadExpr, compile_value
    if not isinstance(text, str) or not text.strip():
        raise QueryError("query: an expression of the event (type == 'x', data.a.b == 'y', ...)")
    try:
        return compile_value(text, {}, ("data", "time", "type", "key", "source"))
    except BadExpr as e:
        raise QueryError(f"query: {e}") from None


def path_of(n) -> str | None:
    """The indexed path an expression names (``type``, ``key``, ``source``, ``data.a.b``), or None."""
    parts = []
    while isinstance(n, (ast.Attribute, ast.Subscript)):
        if isinstance(n, ast.Attribute):
            parts.append(n.attr)
        else:
            if not (isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)):
                return None
            parts.append(n.slice.value)
        n = n.value
    if not isinstance(n, ast.Name):
        return None
    if n.id in ("type", "key", "source") and not parts:
        return n.id
    if n.id == "data" and 1 <= len(parts) <= DEPTH:
        return "data." + ".".join(reversed(parts))
    return None


def _const(n):
    if isinstance(n, ast.Constant):
        return True, n.value
    if isinstance(n, ast.Name) and n.id in ("true", "false", "null", "True", "False", "None"):
        return True, {"true": True, "True": True, "false": False, "False": False}.get(n.id)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant) \
            and isinstance(n.operand.value, (int, float)):
        return True, -n.operand.value
    return False, None


class Plan:
    def __init__(self, ix: Index):
        self.ix = ix
        self._all: set[int] | None = None
        self.used: list[str] = []          # how each part was read (said in the answer)

    def all(self) -> set[int]:
        if self._all is None:
            self._all = self.ix.all()
        return self._all

    def of(self, n) -> tuple[set[int] | None, bool]:
        """The candidates the index gives for expression ``n`` (None: it cannot say), and whether they are exactly
        the events it holds for."""
        if isinstance(n, ast.BoolOp):
            parts = [self.of(v) for v in n.values]
            if isinstance(n.op, ast.And):
                sets = [s for s, _ in parts if s is not None]
                if not sets:
                    return None, False
                out = set.intersection(*sorted(sets, key=len))
                return out, all(s is not None and ex for s, ex in parts)
            if any(s is None for s, _ in parts):
                return None, False
            return set().union(*(s for s, _ in parts)), all(ex for _, ex in parts)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            s, ex = self.of(n.operand)
            if s is None or not ex:
                return None, False
            return self.all() - s, True
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], (ast.Eq, ast.NotEq)):
            a, b = n.left, n.comparators[0]
            for x, y in ((a, b), (b, a)):
                p = path_of(x)
                ok, c = _const(y)
                if p is not None and ok and (c is None or isinstance(c, (str, int, float, bool))):
                    if c is None:                      # == null: the path missing, or null
                        s = self.all() - self.ix.present(p)
                    elif isinstance(c, str) and len(c) > TEXT_MOST:
                        s = self.ix.prefixed(p, c[:TEXT_MOST])
                        self.used.append(f"{p} (prefix)")
                        return (s if isinstance(n.ops[0], ast.Eq) else None), False
                    else:
                        s = self.ix.lookup(p, c)
                    self.used.append(p)
                    return (s, True) if isinstance(n.ops[0], ast.Eq) else (self.all() - s, True)
            return None, False
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == "startswith" and len(n.args) == 1:
                p = path_of(f.value)
                ok, c = _const(n.args[0])
                if p is not None and ok and isinstance(c, str):
                    self.used.append(p)
                    return self.ix.prefixed(p, c[:TEXT_MOST]), len(c) <= TEXT_MOST
            if isinstance(f, ast.Name) and f.id == "has" and n.args:
                ok, c = _const(n.args[-1])
                if ok and isinstance(c, str):
                    got = self.ix.containing(c)
                    if got is not None:
                        self.used.append("text")
                        return got, len(n.args) == 1           # has(VALUE, 'x'): the event's text has it; VALUE's, evaluated
            if isinstance(f, ast.Name) and f.id == "glob" and len(n.args) == 2:
                p = path_of(n.args[0])
                ok, c = _const(n.args[1])
                if p is not None and ok and isinstance(c, str):
                    cut = min([c.index(x) for x in "*?[" if x in c] or [len(c)])
                    self.used.append(p)
                    exact = cut == len(c) - 1 and c.endswith("*") and cut <= TEXT_MOST
                    return self.ix.prefixed(p, c[:min(cut, TEXT_MOST)]), exact
            return None, False
        p = path_of(n)                               # a path alone: it is there (and the expression says the rest)
        if p is not None:
            self.used.append(p)
            return self.ix.present(p), False
        ok, c = _const(n)
        if ok and isinstance(c, bool):
            return (self.all() if c else set()), True
        return None, False


# ---- answering

def _env(e: dict) -> dict:
    return {"data": e.get("data") or {}, "time": e.get("time"), "type": e.get("type"), "key": e.get("item"),
            "source": e.get("source")}


def matches(ix: Index, q, since=None, until=None, sample: int | None = None) -> dict:
    """The seqs of the events query ``q`` holds for (newest first), and how they were found."""
    from .spec.handlers import evaluate
    plan = Plan(ix)
    cands, exact = plan.of(q.tree) if q.tree is not None else ((plan.all() if q.literal else set()), True)
    win = ix.window(since, until)
    out = {"indexed": cands is not None, "exact": bool(exact and cands is not None), "paths": sorted(set(plan.used))}
    if cands is None:                                # a scan: the newest events, each evaluated
        seqs = ix.newest(SCAN_MOST, since, until)
        out.update(scanned=True, read=len(seqs), capped=len(seqs) >= SCAN_MOST)
    else:
        if win is not None:
            cands = cands & win
        seqs = sorted(cands, reverse=True)
        out.update(scanned=False, candidates=len(seqs))
        if exact:
            out.update(seqs=seqs, total=len(seqs), read=0)
            return out
        if len(seqs) > EVALUATE_MOST:
            out["capped"] = True
            seqs = seqs[:EVALUATE_MOST]
    if sample and len(seqs) > sample:
        rng = random.Random(0)
        picked = sorted(rng.sample(seqs, sample), reverse=True)
        out.update(sampled=True, sample_of=len(seqs))
        ratio = len(seqs) / sample
        seqs = picked
    else:
        ratio = None
    got = []
    for i in range(0, len(seqs), 2000):
        for e in ix.events_of(seqs[i:i + 2000]):
            if evaluate(q, _env(e)):
                got.append(e["seq"])
    out.update(seqs=got, total=round(len(got) * ratio) if ratio else len(got), read=len(seqs))
    if ratio:
        out["estimated"] = True
    return out


def run(events, ask: dict) -> dict:
    """``POST /api/events/query``: ``{query, since?, until?, limit?, sample?, compare?}``."""
    with _LOCK:                    # the index's one connection is not read by two threads at once, nor closed under one
        return _run(events, ask)


def _run(events, ask: dict) -> dict:
    if not isinstance(ask, dict):
        raise QueryError("a query is {query, since?, until?, limit?, sample?, compare?}")
    q = compile_query(ask.get("query"))
    since, until = ask.get("since"), ask.get("until")
    lim = ask.get("limit")
    limit = max(0, min(int(lim) if isinstance(lim, (int, float)) and not isinstance(lim, bool) else 50, LIMIT_MOST))
    sample = ask.get("sample")
    sample = int(sample) if isinstance(sample, (int, float)) and not isinstance(sample, bool) and sample > 0 else None
    t0 = time.perf_counter()
    ix = index_for(events)
    m = matches(ix, q, since, until, sample)
    seqs = m.pop("seqs")
    shown = ix.events_of(seqs[:limit])
    out = {"query": q.text, "total": m.pop("total"), "events": shown, "shown": len(shown), **m,
           "record": ix.count()}
    if ask.get("compare") not in (None, ""):
        c = compile_query(ask["compare"])
        old = matches(ix, c, since, until, sample)
        a, b = set(seqs), set(old["seqs"])
        out["compare"] = {"query": c.text, "total": old["total"], "added": len(a - b), "dropped": len(b - a),
                          **({"estimated": True} if old.get("estimated") or m.get("estimated") else {})}
    out["took_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out


def events_matching(events, text: str, since=None, until=None, most: int = 200_000) -> tuple[list[dict], dict]:
    """Every event a query holds for, oldest first (at most ``most``, the newest), and how they were found: what the
    workbench's answers read."""
    q = compile_query(text)
    with _LOCK:
        return _matching(events, q, since, until, most)


def _matching(events, q, since, until, most: int) -> tuple[list[dict], dict]:
    ix = index_for(events)
    m = matches(ix, q, since, until)
    seqs = m.pop("seqs")
    if len(seqs) > most:
        m["capped"] = True
        seqs = seqs[:most]
    return ix.events_of(sorted(seqs)), m
