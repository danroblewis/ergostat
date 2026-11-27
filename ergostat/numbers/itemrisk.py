"""Each item's risk score, learned from what failed before (SPEC §5a, *Risk score*), for a kind that declares
``risk-score:`` (off unless declared).

An **attempt** opens each time an item enters the declared ``at`` state, with the declared fields' values as they
stand then. It is **judged** failed at the first event of a ``failed`` type about the item (one after it passed turns
it failed: a change reverted), and passed when the item enters a ``passed`` state. An item that enters ``at`` again
while an attempt is open withdraws that attempt, so it is never judged. A kind that declares ``undone`` (the event
types that say a failure was not the item's: a flake retried) has a failure of an open attempt **held** until the
item's next change of state: an ``undone`` event first withdraws the attempt unjudged, any other change judges it
failed. A change of state is one the item's own events make: a lease's moves (taken into ``leased``, given back,
dead) are the runner's, and neither judge, withdraw nor open an attempt. An event the fold refused (from a run whose
lease ended, a stale read, a move from the wrong state) neither fails nor undoes an attempt. The record is replayed in its own order
(each event's ``seq``, never its time), so an attempt is scored only from the attempts judged before it.

The score is a naive Bayes estimate. It starts from the base rate of failure, and then, for each declared field, adds
the log odds by which that field's value has failed more or less often. Each value's rate is shrunk toward the base
rate by ``PRIOR`` attempts. How a field is read:

    value   its value, as text                 (an author, a source, a kind of change)
    each    each element of a list, the riskiest one counting   (the paths a change touched)
    size    a number, in bands of powers of two                  (lines changed, conflicts)

A missing value is the value ``(none)``, learned like any other, never read as safe. With fewer than ``least`` judged
attempts there is no score (None), never 0. The backtest replays the same way and reports each score band's failure
rate (calibration), the Brier score against the base rate alone, and the AUC."""

from __future__ import annotations

import math
import threading

from ..leases import PREFIX as LEASE_PREFIX
from ..spec.items import SNAPSHOT, TRANSCRIPT_TYPES, Item, asks_transcript, field_at, fold

HOWS = ("value", "each", "size")
FIELDS_MOST = 16          # fields one kind's score learns from
EACH_MOST = 200           # elements of one list read (a change's paths)
LEAST = 10                # judged attempts before any score, unless declared
LEAST_MOST = 10_000
PRIOR = 4.0               # attempts' worth of base rate each value's rate is shrunk toward
EDGES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
NONE = "(none)"
CACHED_MOST = 8           # records whose replay is kept between calls (a web server's item pages)


def keys(v, how: str) -> list[str]:
    """What a field's value is learned as."""
    if how == "size":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return [NONE]
        if v < 1:
            return ["<1"]
        lo = 2 ** int(math.log2(v))
        return [str(lo) if lo == 1 else f"{lo}-{2 * lo - 1}"]
    if how == "each":
        vs = v if isinstance(v, list) else [] if v is None else [v]
        out = sorted({str(x)[:200] for x in vs[:EACH_MOST] if x is not None and x != ""})
        return out or [NONE]
    return [NONE] if v is None or v == "" or v == [] else [str(v)[:200]]


def logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def platt(zy: list[tuple[float, bool]], ridge: float = 1.0) -> tuple[float, float]:
    """(a, b) with P(failed) = 1 / (1 + exp(-(a z + b))) fit to the judged attempts' raw log odds by Newton's method
    (Platt scaling), held toward (1, 0) by ``ridge``: naive Bayes adds up evidence that overlaps, and this is what
    takes its overconfidence back out, from the record itself."""
    a, b = 1.0, 0.0
    for _ in range(30):
        ga, gb, haa, hab, hbb = ridge * (a - 1), ridge * b, ridge, 0.0, ridge
        for z, y in zy:
            z = max(-12.0, min(12.0, z))
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, a * z + b))))
            w = p * (1 - p)
            ga, gb = ga + (p - y) * z, gb + (p - y)
            haa, hab, hbb = haa + w * z * z, hab + w * z, hbb + w
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-6:
            break
    return a, b


class Learner:
    """The replay of one kind's events: every attempt, the counts judged so far, each item as it stands."""

    def __init__(self, kind):
        self.kind, self.decl = kind, kind.risk
        self.items: dict[str, Item] = {}
        self.open: dict[str, dict] = {}       # item: its open attempt
        self.last: dict[str, dict] = {}       # item: its latest attempt (open or judged)
        self.own: dict[str, str | None] = {}  # item: its state as its own events moved it (a lease's moves left out)
        self.attempts: list[dict] = []
        self.n = self.f = 0                    # judged attempts, and of them failed
        self.by: dict[tuple, list[int]] = {}   # (field, value): [judged, failed]
        self.rolled: set[str] = set()          # items whose earlier events are rolled into a snapshot: not seen
        self.seq, self.last_id, self.withdrawn = 0, None, 0
        self.judged: list[dict] = []           # attempts judged, in the order they were
        self.fit, self.fit_at, self.said = None, 0, 0   # the calibration (platt), and the judgements when it was fit

    def features(self, fields: dict) -> list[tuple[str, list[str]]]:
        return [(f, keys(field_at(fields, f), how)) for f, how in self.decl["from"].items()]

    def score(self, feats) -> tuple[float | None, list[dict]]:
        z, why = self.raw(feats)
        if self.n < self.decl["least"] or self.fit is None:
            return None, []
        a, b = self.fit
        return round(1 / (1 + math.exp(-max(-30.0, min(30.0, a * z + b)))), 4), why

    def raw(self, feats) -> tuple[float, list[dict]]:
        """The naive Bayes log odds, before calibration, and the fields that moved it most."""
        r0 = (self.f + 1) / (self.n + 2)
        z, why = logit(r0), []
        for f, ks in feats:
            best = None
            for k in ks:
                n, bad = self.by.get((f, k), (0, 0))
                r = (bad + PRIOR * r0) / (n + PRIOR)
                if best is None or r > best[0]:
                    best = (r, k, n, bad)
            r, k, n, bad = best
            z += logit(r) - logit(r0)
            why.append({"field": f, "value": k, "judged": n, "failed": bad, "rate": round(r, 3)})
        why.sort(key=lambda w: -abs(logit(w["rate"]) - logit(r0)))
        return z, why[:3]

    def count(self, a: dict, judged: int, failed: int) -> None:
        self.n, self.f = self.n + judged, self.f + failed
        if judged:
            self.judged.append(a)
        for f, ks in a["feats"]:
            for k in ks:
                c = self.by.setdefault((f, k), [0, 0])
                c[0], c[1] = c[0] + judged, c[1] + failed
        self.said += 1                     # refit as judgements come, never on a read: a kept replay and a fresh one agree
        if self.n >= self.decl["least"] and (self.fit is None or self.said >= self.fit_at + max(10, self.fit_at // 10)):
            self.fit, self.fit_at = platt([(x["z"], x["failed"] is True) for x in self.judged]), self.said

    def judge(self, a: dict, failed: bool) -> None:
        if a["failed"] is None:
            self.open.pop(a["item"], None)
            self.count(a, 1, int(failed))
        elif failed:                                     # passed before: failed after all
            self.count(a, 0, 1)
        a["failed"], a["judged_seq"], a["held"] = failed, self.seq, False

    def withdraw(self, a: dict) -> None:
        self.withdrawn += 1
        self.open.pop(a["item"], None)
        a["failed"], a["held"] = "withdrawn", False

    def feed(self, events: list[dict]) -> None:
        d = self.decl
        for e in events:
            self.seq, self.last_id = max(self.seq, e.get("seq") or 0), e.get("id")
            id = e["item"]
            if e["type"] == SNAPSHOT:
                self.rolled.add(id)
            it = self.items.get(id)
            before, said = (it.state, len(it.refused)) if it else (None, 0)
            it = self.items[id] = fold(id, [e], self.kind, it=it)
            if e["type"].startswith(LEASE_PREFIX):      # a lease's moves (to leased, back, dead) are its runner's:
                continue                                 # never the item's own change of state
            # an event the fold refused (fenced, sealed, a stale read, moves-from, final) never fails or undoes
            # the attempt: the item's page shows it refused. Only a move it still made (final's) counts as one
            typ = None if e["type"] != SNAPSHOT and len(it.refused) > said else e["type"]
            was = self.own.get(id)
            now = self.own[id] = it.state if it.state != before else was
            a = self.last.get(id)
            if a is not None and a.get("held") and typ in d["undone"]:
                self.withdraw(a)                         # the failure was not the item's: never judged
            elif typ in d["failed"] and a is not None and a["failed"] in (None, False):
                if a["failed"] is None and d["undone"]:
                    a["held"] = True                     # judged at the next change of state, unless undone first
                else:
                    self.judge(a, True)
            elif a is not None and a.get("held") and now != was:
                self.judge(a, True)
            if now == was:
                continue
            if now == d["at"]:
                if id in self.open:
                    self.withdraw(self.open[id])
                feats = self.features(it.fields)
                score, _ = self.score(feats)
                a = {"item": id, "seq": self.seq, "feats": feats, "score": score, "z": self.raw(feats)[0],
                     "failed": None, "base": self.base()}
                self.attempts.append(a)
                self.open[id] = self.last[id] = a
            elif now in d["passed"] and id in self.open:
                self.judge(self.open[id], False)

    def base(self) -> float | None:
        return None if self.n < self.decl["least"] else (self.f + 1) / (self.n + 2)


_CACHE: dict = {}
_LOCK = threading.Lock()


def learned(events, spec, kind: str, then):
    """``then(the replay of kind)``, caught up with the record, with no other caller between. The replay is kept
    between calls for a record on disk, and replayed from the start when the record or the declaration changed under
    it (the last event it read is gone, or the record's last seq is behind it)."""
    k = spec.items[kind]
    skip = () if asks_transcript([k]) else (TRANSCRIPT_TYPES,)
    where = getattr(events, "path", None) or getattr(events, "dir", None)
    key = (str(where), kind, repr(k.risk), repr(sorted(k.on.items())), repr(sorted(k.fold.items())), repr(k.states),
           repr(sorted(getattr(k, "bounds", {}).items())))
    with _LOCK:                                       # read, catch up and keep under one lock: no other caller between
        lr = _CACHE.get(key) if where is not None else None
        if lr is not None:
            got = events.get(lr.last_id) if lr.last_id else None
            if events.last_seq() < lr.seq or (lr.last_id and (got is None or got.get("seq") != lr.seq)):
                lr = None
        if lr is None:
            lr = Learner(k)
            lr.feed(events.of_items([k.id], skip=skip))
        else:
            lr.feed(events.of_items([k.id], skip=skip, after_seq=lr.seq))
        if where is not None:
            _CACHE.pop(key, None)
            _CACHE[key] = lr
            while len(_CACHE) > CACHED_MOST:
                _CACHE.pop(next(iter(_CACHE)))
        return then(lr)


def of(lr: Learner, it: Item) -> dict:
    """One item's score now, from every attempt judged so far, with the fields that moved it most."""
    score, why = lr.score(lr.features(it.fields))
    return {"score": score, "why": why, "judged": lr.n, "failed": lr.f,
            "said": f"fewer than {lr.decl['least']} attempts judged ({lr.n})" if score is None else None}


def item(events, spec, kind: str, id: str) -> dict | None:
    return learned(events, spec, kind, lambda lr: of(lr, lr.items[id]) if id in lr.items else None)


def scores(events, spec, kind: str) -> dict:
    """Every item of the kind with its score, the highest first (an item with none last)."""
    def read(lr: Learner) -> dict:
        rows = [{"id": i, "state": it.state, **of(lr, it)} for i, it in lr.items.items()]
        rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["id"]))
        return {"projection": kind, "judged": lr.n, "failed": lr.f, "least": lr.decl["least"], "items": rows}
    return learned(events, spec, kind, read)


def backtest(events, spec, kind: str) -> dict:
    """Each judged attempt's score as it was given (from the attempts judged before it), against what became of it:
    the failure rate per score band, the Brier score beside the base rate's, and the AUC."""
    return learned(events, spec, kind, lambda lr: _backtest(lr, kind))


def _backtest(lr: Learner, kind: str) -> dict:
    done = [a for a in lr.attempts if a["failed"] in (True, False)]
    scored = [a for a in done if a["score"] is not None]
    bands = []
    for lo, hi in zip(EDGES, EDGES[1:], strict=False):
        inn = [a for a in scored if lo <= a["score"] < hi or hi == 1.0 and a["score"] == 1.0]
        if inn:
            bad = sum(a["failed"] is True for a in inn)
            bands.append({"band": f"{lo:.1f}-{hi:.1f}", "attempts": len(inn), "failed": bad,
                          "rate": round(bad / len(inn), 3),
                          "mean_score": round(sum(a["score"] for a in inn) / len(inn), 3)})
    y = [1.0 if a["failed"] is True else 0.0 for a in scored]
    brier = round(sum((a["score"] - v) ** 2 for a, v in zip(scored, y, strict=True)) / len(y), 4) if y else None
    base = round(sum((a["base"] - v) ** 2 for a, v in zip(scored, y, strict=True)) / len(y), 4) if y else None
    return {"projection": kind, "attempts": len(lr.attempts), "judged": len(done), "scored": len(scored),
            "failed": sum(a["failed"] is True for a in done), "open": len(lr.open), "withdrawn": lr.withdrawn,
            "held": sum(bool(a.get("held")) for a in lr.open.values()),
            "unscored": len(done) - len(scored), "rolled_up": len(lr.rolled), "bands": bands,
            "brier": brier, "brier_base_rate": base, "auc": auc(scored)}


def auc(scored: list[dict]) -> float | None:
    """The chance a failed attempt was scored above a passed one (ties half): None without both."""
    bad = sorted(a["score"] for a in scored if a["failed"] is True)
    good = sorted(a["score"] for a in scored if a["failed"] is False)
    if not bad or not good:
        return None
    import bisect
    wins = sum(bisect.bisect_left(good, s) + (bisect.bisect_right(good, s) - bisect.bisect_left(good, s)) / 2 for s in bad)
    return round(wins / (len(bad) * len(good)), 4)
