"""The events no projection explains (SPEC §12e, *Unexplained events*): the modelling subsystem's third loop, beside the
fit and the requests. The blocks emit events; a projection turns them into items, stocks and flows. What no projection
takes is **unexplained**, a stock the goal ``events-explained`` holds at 0, and the drafter (an AI agent, ``ai: true``)
drafts the projections that take it.

**What counts.** An event is unexplained when no projection of the model takes it: none reads it (``unread``), or one
reads it and no kind of event takes it (``remainder:P``, its residual's remainder), or a kind takes it and its key
finds nothing (``no-key:P``). Left out, counted nowhere: ergostat's own events (``OWN``: its types, the record's
bookkeeping, its runs, loops, sensors, leases, sessions and transcripts; any event whose source is ``ergostat``), and a
projection's own published events (``source: projection:*``, SPEC §5a, *Emitted events*): they are not the world's.

**Groups.** Never one request an event: by source and type, and, for a type that tells nothing (``GENERIC``: ``log``,
``event``, ``message``, an empty one...), by the envelope's shape too (its top-level data keys). Each group is one
request (``ergostat.modelling-request``, ``source: events``, ``code: events-unexplained``, tier ``events``) with its
count, its first and last time and a few example event ids; answered when no event of it is unexplained. The request is
modelling's bookkeeping: the one thing the owner watches is the group's object (``ergostat.unexplained``, ``objects``),
and every link the owner follows for a group (the inbox's held entry, the Goals row's) is to that object.

**Ignored.** The owner ignores a group in the model, in the modelling template's ``with: ignore-events:`` (a type glob,
or ``SOURCE TYPE`` globs): it stays explained, as ``ignored``, and raises no request. (Denying a held request in the
inbox dismisses it too, in the record, until it is raised again.)

**Kept incrementally** (never a scan of the record). A cursor (the record's ``seq``) and the groups are kept in
``<state>/modelling/unexplained.json``: each update reads only the events after the cursor (``CHUNK`` at most a run),
counts them per group and day, and keeps the newest ``SAMPLES`` ids of each. When the model's projections change, each
group is held again by its samples alone: a group none of whose samples is unexplained now is gone, one some of them
are is scaled by that share (said ``estimated`` until it is counted on). When events are taken out (a prune, a
roll-up: the record's generation moved), the days before the record's first event are dropped. Each unexplained
event read is also a posting in the event-query index (``unexplained()`` in the Events query, eventquery.py).

**The judge's rule for a change to the projections** (``judged``): the change applied beside the model, the events of
the groups it cites (the newest ``JUDGE_MOST`` of each, by its indexed type) are counted unexplained before and after,
and each projection it adds or changes is reviewed as the workbench reviews it (``spec/workbench.py``: its residual)
before and after. It passes only when the unexplained events it targets fall and it adds no event with no key, no
refused event, no contradiction, no split and no finding of ``check``'s; else it fails, saying which."""

from __future__ import annotations

import contextlib
import fcntl
import fnmatch
import hashlib
import json
import math
import time
from pathlib import Path

CODE = "events-unexplained"
SOURCE = "events"
TIER = "events"
CHUNK = 20_000              # events read in one update at most (the rest the next)
SAMPLES = 20                # the newest event ids kept a group, to hold it again when the projections change
EXAMPLES = 5                # example ids a request says
GROUPS_MOST = 500           # groups kept; past this, the rest are counted in one (``OVERFLOW``)
OVERFLOW = "~more"
DAY = 86400.0
JUDGE_MOST = 2000           # a group's newest events the judge counts before and after
OWN = ("ergostat.", "model.", "agent.", "loop.", "controller.", "valve.", "sensor.", "block.", "person.", "trigger.",
       "steptest.", "session.", "claude.", "auxiliary.", "variable.", "review.", "run.", "extractor.", "context.",
       "lease.", "cost.")
GENERIC = {"", "event", "events", "log", "logs", "line", "lines", "message", "messages", "record", "records", "data",
           "raw", "entry", "entries", "item"}
VERSION = 1


# ---- what counts

def own(e: dict) -> bool:
    """Ergostat's own (its bookkeeping, runs, loops, sensors, sessions, transcripts) or a projection's published
    event: never unexplained, counted nowhere."""
    from ..spec.items import SNAPSHOT
    t, s = str(e.get("type") or ""), str(e.get("source") or "")
    return t == SNAPSHOT or t.startswith(OWN) or s == "ergostat" or s.startswith("projection:")


def why(spec, e: dict) -> str | None:
    """None when a projection of the model takes ``e``; else why not: ``unread``, ``remainder:P`` (P reads it, no kind
    of event takes it) or ``no-key:P`` (a kind takes it, its key finds nothing)."""
    said = None
    for name, k in (getattr(spec, "items", None) or {}).items():
        if name.startswith("ergostat."):
            continue
        try:
            if not k.reads(e):
                continue
            if k.keys_of(e):
                return None
            took = k.kind_of(e) if getattr(k, "handlers", None) is not None else True
        except Exception:                       # an event a query cannot read is not taken by it
            continue
        said = said or (f"remainder:{name}" if took is None else f"no-key:{name}")
    return said or "unread"


def shape(e: dict) -> str:
    d = e.get("data")
    return ",".join(sorted(str(k) for k in d)[:8]) if isinstance(d, dict) else type(d).__name__


def group_of(e: dict) -> tuple[str, dict]:
    """The group an event is counted in: its id and what names it (source, type, and the envelope's shape for a type
    that tells nothing)."""
    s, t = str(e.get("source") or ""), str(e.get("type") or "")
    g = {"source": s, "type": t, **({"shape": shape(e)} if t.lower() in GENERIC else {})}
    return gid(g), g


def gid(g: dict) -> str:
    return hashlib.sha256(f"{g.get('source', '')}|{g.get('type', '')}|{g.get('shape', '')}".encode()).hexdigest()[:10]


def label(g: dict) -> str:
    return (f"{g.get('type') or '(no type)'}" + (f" from {g['source']}" if g.get("source") else "")
            + (f" shaped {{{g['shape']}}}" if g.get("shape") else ""))


# ---- ignored, by the owner, in the model

def ignores(spec) -> list:
    """The modelling template's ``with: ignore-events:`` (each a type glob, ``SOURCE TYPE`` globs, or a map of
    ``source:`` and ``type:`` globs)."""
    for u in (getattr(spec, "uses", None) or {}).values():
        if isinstance(u, dict) and u.get("template") == "modelling":
            got = (u.get("values") or {}).get("ignore-events") or []
            return got if isinstance(got, list) else [got]
    return []


def ignored(spec, g: dict, rules: list | None = None) -> str | None:
    """The rule of ``ignore-events`` that ignores the group, as written; None when none does."""
    for r in ignores(spec) if rules is None else rules:
        if isinstance(r, dict):
            s, t = str(r.get("source") or "*"), str(r.get("type") or "*")
        else:
            w = str(r).split()
            s, t = (w[0], w[1]) if len(w) >= 2 else ("*", w[0] if w else "")
        if t and fnmatch.fnmatchcase(g.get("type") or "", t) and fnmatch.fnmatchcase(g.get("source") or "", s):
            return str(r) if not isinstance(r, dict) else json.dumps(r, sort_keys=True)
    return None


# ---- the tally, kept

def _dir(p) -> Path:
    d = Path(p.dir) / "modelling"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextlib.contextmanager
def _kept(p):
    d = _dir(p)
    path = d / "unexplained.json"
    with open(d / "unexplained.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text()) if path.is_file() else {}
        except ValueError:
            data = {}
        if data.get("version") != VERSION:
            data = {"version": VERSION, "seq": 0, "gen": None, "kinds": None, "groups": {}, "own": 0, "read": 0}
        yield data
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)


def kinds_hash(spec) -> str:
    from ..spec.itemindex import kinds_key
    own_kinds = type("S", (), {"items": {n: k for n, k in (spec.items or {}).items() if not n.startswith("ergostat.")},
                               "functions_hash": getattr(spec, "functions_hash", "")})()
    return hashlib.sha256(repr(kinds_key(own_kinds)).encode()).hexdigest()[:16]


def count_of(g: dict) -> int:
    return int(sum(g.get("days", {}).values()))


def _bump(groups: dict, e: dict, reason: str) -> None:
    k, g = group_of(e)
    if k not in groups and len(groups) >= GROUPS_MOST:
        k, g = OVERFLOW, {"source": "", "type": "(many more groups)"}
    x = groups.setdefault(k, {**g, "days": {}, "first": e["time"], "last": e["time"], "samples": [], "by": {}})
    day = str(int(e["time"] // DAY))
    x["days"][day] = x["days"].get(day, 0) + 1
    x["first"], x["last"] = min(x["first"], e["time"]), max(x["last"], e["time"])
    x["by"][reason] = x["by"].get(reason, 0) + 1
    x["samples"] = (x["samples"] + [e["id"]])[-SAMPLES:]


def _again(p, spec, groups: dict) -> None:
    """The projections changed: each group held again by its samples alone."""
    for k in list(groups):
        x = groups[k]
        evs = [e for i in x.get("samples") or [] if (e := p.events.get(i)) is not None]
        still = [(e, r) for e in evs if (r := why(spec, e)) is not None]
        if not still:
            del groups[k]
            continue
        share = len(still) / max(1, len(evs))
        if share < 1.0:
            x["days"] = {d: max(1, round(n * share)) for d, n in x["days"].items()}
            x["estimated"] = True
        by: dict[str, int] = {}
        for _, r in still:
            by[r] = by.get(r, 0) + 1
        total = count_of(x)
        x["by"] = {r: max(1, round(total * n / len(still))) for r, n in by.items()}
        x["samples"] = [e["id"] for e, _ in still]


def update(p, spec=None, most: int = CHUNK) -> dict:
    """The tally brought up to the record: only the events after its cursor read (``most`` at most), the groups held
    again when the projections changed, the days the record no longer holds dropped. Returns the kept state."""
    from ..spec.items import TRANSCRIPT_TYPES
    spec = spec or p.model.spec
    with _kept(p) as st:
        h = kinds_hash(spec)
        if st.get("kinds") not in (None, h):
            _again(p, spec, st["groups"])
        st["kinds"] = h
        gen = p.events.generation()
        if st.get("gen") is not None and st["gen"] != gen:      # events taken out: the days before the record's first
            first = p.events.first_time()
            cut = int(first // DAY) if first is not None else math.inf
            for k in list(st["groups"]):
                x = st["groups"][k]
                x["days"] = {d: n for d, n in x["days"].items() if int(d) >= cut}
                if not x["days"]:
                    del st["groups"][k]
        st["gen"] = gen
        again = p.events.last_seq() < int(st.get("seq") or 0)
        if again:                                                 # a record made again: counted again from its start
            st.update(seq=0, groups={}, own=0, read=0)
        new = p.events.query(n=None, after_seq=int(st.get("seq") or 0), skip=(TRANSCRIPT_TYPES,), first=most)
        found = []
        for e in new:
            st["read"] = int(st.get("read") or 0) + 1
            if own(e):
                st["own"] = int(st.get("own") or 0) + 1
                continue
            r = why(spec, e)
            if r is not None:
                _bump(st["groups"], e, r)
                found.append(e["seq"])
        if new:
            st["seq"] = max(int(st.get("seq") or 0), max(int(e["seq"]) for e in new))
        if len(new) < most:
            st["seq"] = max(int(st.get("seq") or 0), p.events.last_seq())
        _indexed(p, found, int(st["seq"] or 0), again)
        return json.loads(json.dumps(st))


def _indexed(p, seqs: list[int], upto: int, again: bool) -> None:
    """Each unexplained event a posting in the event-query index (``unexplained()``, eventquery.py), as it is read:
    the query re-checks only the ones it shows. Never fails the tally."""
    try:
        from ..eventquery import mark_unexplained
        mark_unexplained(p.events, seqs, upto, again)
    except Exception:                               # noqa: BLE001 - the index is a convenience; the tally is the count
        pass


def groups(p, spec=None, st: dict | None = None) -> list[dict]:
    """The groups as they are, each ``{id, source, type, shape?, count, first, last, examples, by, ignored?,
    estimated?}``, the largest first."""
    spec = spec or p.model.spec
    st = st if st is not None else update(p, spec)
    rules = ignores(spec)
    out = []
    for k, x in st.get("groups", {}).items():
        n = count_of(x)
        if n <= 0:
            continue
        out.append({"id": k, **{f: x[f] for f in ("source", "type", "shape") if f in x}, "count": n,
                    "first": x["first"], "last": x["last"], "examples": (x.get("samples") or [])[-EXAMPLES:],
                    "by": x.get("by") or {}, **({"estimated": True} if x.get("estimated") else {}),
                    **({"ignored": ig} if (ig := ignored(spec, x, rules)) else {})})
    return sorted(out, key=lambda g: (-g["count"], g["id"]))


def total(gs: list[dict]) -> int:
    """The unexplained events: every group's count but the ignored."""
    return sum(g["count"] for g in gs if not g.get("ignored"))


# ---- the requests

def request_of(g: dict) -> dict:
    by = ", ".join(f"{n} {r}" for r, n in sorted(g["by"].items(), key=lambda kv: -kv[1])[:3])
    return {"source": SOURCE, "code": CODE, "about": f"events:{g['id']}", "level": "finding", "tier": TIER,
            "where": None, "group": {f: g[f] for f in ("source", "type", "shape") if f in g},
            "says": f"events of {label(g)} that no projection takes: draft a projection for them, or add kinds of "
                    f"event to one that reads them (or ignore them in the modelling template's ignore-events)",
            "unexplained": {"count": g["count"], "first": g["first"], "last": g["last"], "examples": g["examples"],
                            "by": by, **({"estimated": True} if g.get("estimated") else {})}}


def _changed(old: dict | None, new: dict) -> bool:
    if not old:
        return True
    a, b = int(old.get("count") or 0), int(new["count"])
    return abs(a - b) >= max(1, 0.1 * max(a, 1)) or old.get("last") != new["last"] and b != a


def sync(p, spec=None, now: float | None = None) -> dict:
    """The groups raised as requests (the ignored ones not), those no longer unexplained answered, and each moved to
    where its changes say it is (``requests._moved``, for the events' requests alone). Returns the moves, ``open`` and
    ``events`` (the unexplained events now: what the stock reads)."""
    from . import requests as rq
    spec = spec or p.model.spec
    now = now or time.time()
    gs = groups(p, spec)
    found = {}
    for g in gs:
        if g.get("ignored"):
            continue
        r = request_of(g)
        k = rq.rid(SOURCE, CODE, r["about"])
        found[k] = {"id": k, **r}
    with rq.locked(p):
        got = rq._moved(p, spec, now, found, scope=lambda x: x.get("source") == SOURCE)
        have = rq.stored(p)
        for k, r in found.items():                    # its count and times kept current, not on every event
            x = have.get(k)
            if x is not None and x["state"] in rq.OPEN and _changed(x.get("unexplained"), r["unexplained"]):
                rq.event(p, k, x["state"], {"unexplained": r["unexplained"]})
        have = rq.stored(p)
    from ..spec.ir import UNEXPLAINED
    if UNEXPLAINED in (spec.items or {}):
        got = {**got, "objects": objects(p, spec, gs, have)}
    return {**got, "events": total(gs), "ignored": sum(g["count"] for g in gs if g.get("ignored")), "groups": len(found)}


# ---- the groups as the built-in projection's objects: the one thing the owner watches a group's progress by

STAGE = {"judge": "judging", "reviewer": "reviewing", "you": "waiting", "sent-back": "sent-back"}   # stuck.py's steps
KEPT = ("state", "why", "request", "change", "round", "latest", "count", "last")


def _line(s: str) -> str:
    s = " ".join(str(s or "").split())
    return s[:197] + "..." if len(s) > 200 else s


def _latest(kind: str, c: dict) -> str:
    """The latest word on a change, in a line: the reviewer's finding or the judge's (or check's) why; else what the
    judge said of it, else its title."""
    from ..stuck import _finding
    return _line(_finding(kind, c) or (c.get("verdict") or {}).get("why") or (c.get("review") or {}).get("summary")
                 or c.get("title") or "")


def object_of(spec, g: dict, req: dict | None, cites: dict) -> dict:
    """A group as the built-in projection's object (``ergostat.unexplained``): its fields, and its state, its progress
    toward a projection that takes it, from its request and the latest change citing it (the changes store, as the
    Goals row's stuck line reads them: ``stuck._kind_of``): judging (with the judge), reviewing (with the reviewer),
    sent-back (the reviewer sent it back, ``round``), waiting (passed, for the owner), held (tried and failed, or written
    and still unexplained: ``why``), ignored (``ignore-events``, or dismissed by the owner); else unexplained."""
    from ..stuck import _kind_of
    state, why, change, rnd, latest, title = "unexplained", None, None, None, None, None
    rs = (req or {}).get("state")
    since = float((req or {}).get("since") or (req or {}).get("raised") or 0.0)
    mine = [c for c in cites.get(f"request:{(req or {}).get('id')}", []) if (c.get("made") or c.get("created") or 0) >= since - 1]
    c = max(mine, key=lambda c: c.get("made") or c.get("created") or 0.0, default=None)
    if c is not None:
        kind = _kind_of(spec, c)
        change, title = c["id"], c.get("title")
        rnd = int(c.get("review_round") or (c.get("review") or {}).get("round") or 1)
        latest = _latest(kind, c) or None
        state = STAGE.get(kind, "held" if rs == "held" else "unexplained")
    elif rs == "held":
        state = "held"
    if state == "held":
        why = (req or {}).get("why") or latest
    if g.get("ignored"):
        state, why = "ignored", f"ignore-events: {g['ignored']}"
    elif rs == "dismissed":
        state, why = "ignored", "dismissed by the owner" + (f": {req['note']}" if req.get("note") else "")
    rid = (req or {}).get("id")
    return {**{f: g[f] for f in ("source", "type", "shape") if f in g}, "label": label(g), "count": g["count"],
            "first": g["first"], "last": g["last"], "examples": g["examples"], "state": state, "why": why,
            "request": rq_item(rid) if rid else None, "change": f"ergostat.model-change/{change}" if change else None,
            "round": rnd, "latest": latest, "title": title,
            "drafts": sorted((c or {}).get("drafted") or {}) or None,
            **({"estimated": True} if g.get("estimated") else {})}


def rq_item(x: str) -> str:
    from .requests import item_of
    return item_of(x)


def _moves(old: dict | None, new: dict) -> bool:
    """Whether a group's object is written again: its state, why, request, change, round or latest word moved, or its
    count moved as a request's does (``_changed``: a tenth, or its last time with its count): never on every event."""
    if old is None:
        return True
    if any(old.get(f) != new.get(f) for f in ("state", "why", "request", "change", "round", "latest")):
        return True
    return new["state"] != "explained" and _changed(old, new)


def objects(p, spec, gs: list[dict], have: dict) -> dict:
    """The groups written as the built-in projection's objects (``ergostat.unexplained.<state>``), each only when it
    moved since it was last written (kept beside the tally): a second sync with nothing changed writes nothing, and each
    attempt (a change made, judged, reviewed, sent back) is an event of the group's, in its history. A group no longer
    counted is explained. Returns ``{written, explained}``."""
    from ..spec.ir import UNEXPLAINED
    from . import proposals as pr
    from . import requests as rq
    by_about = {r.get("about"): r for r in have.values() if r.get("source") == SOURCE}
    cites = rq._citing(pr.changes(p))
    written = explained = 0
    with _kept(p) as st:
        kept = st.setdefault("objects", {})
        now_ids = set()
        for g in gs:
            if g["id"] == OVERFLOW:
                continue
            now_ids.add(g["id"])
            o = object_of(spec, g, by_about.get(f"events:{g['id']}"), cites)
            if _moves(kept.get(g["id"]), o):
                p.events.add(f"{UNEXPLAINED}.{o['state']}", item=f"{UNEXPLAINED}/{g['id']}", source="ergostat", data=o)
                kept[g["id"]] = {f: o.get(f) for f in KEPT}
                written += 1
        for k, old in list(kept.items()):
            if k in now_ids or old.get("state") == "explained":
                continue
            r = by_about.get(f"events:{k}") or {}
            o = {"count": 0, "state": "explained", "why": None,
                 "request": rq_item(r["id"]) if r.get("id") else old.get("request"), "change": old.get("change"),
                 "latest": "none of its events is unexplained now"}
            p.events.add(f"{UNEXPLAINED}.explained", item=f"{UNEXPLAINED}/{k}", source="ergostat", data=o)
            kept[k] = {**old, **{f: o.get(f) for f in KEPT if f in o}}
            explained += 1
    return {"written": written, "explained": explained}


def open_requests(p) -> list[dict]:
    """The event requests a drafter takes up: open, or held and not the owner's, no change waiting cites them."""
    from . import requests as rq
    return [r for r in rq.waiting(p, ("open", "held")) if r.get("source") == SOURCE and not r.get("owner")]


# ---- what a change to the projections does, held beside the model

def _definition(k) -> str:
    try:
        return json.dumps(k.definition(), sort_keys=True, default=str)
    except Exception:
        return repr(k)


def changed_projections(before, after) -> list[str]:
    """The projections of the model's own a change adds or changes."""
    out = []
    for n, k in (getattr(after, "items", None) or {}).items():
        if n.startswith("ergostat."):
            continue
        b = (before.items or {}).get(n)
        if b is None or _definition(b) != _definition(k):
            out.append(n)
    return sorted(out)


def residual_counts(p, kind) -> dict:
    """The workbench's residual of a projection over its events (``workbench.residual``), as counts; with what its
    objects hold (``fields``: each field's coverage and commonest values; ``states``: each state field's objects now and
    its moves) and the mechanical findings on them (``findings``: ``projection_findings``)."""
    from ..spec import workbench as wb
    q = kind.query.text if kind.query is not None else f"glob(key, {kind.id!r})"
    evs, _ = wb.events_for(p, q)
    items, by_key, took, remainder, unkeyed = wb.fold_all(kind, evs)
    objs = list(items.values())
    lives = wb.lifecycles(kind, objs)
    res = wb.residual(kind, items, by_key, took, remainder, unkeyed, lives)
    fields = {r["field"]: {"have": r["have"], "objects": r["objects"], **({"top": r["top"][:3]} if r.get("top") else {})}
              for r in wb.distributions(kind, objs)}
    states = {f: {"values": lc.get("values"), "now": lc.get("now"),
                  "moves": [[t["from"], t["to"], t["count"]] for t in lc.get("transitions") or []][:12]}
              for f, lc in lives.items()}
    got = {"read": len(evs), "taken": sum(1 for v in took.values() if v is not None), "remainder": len(remainder),
           "no_key": res["no_key"]["count"], "refused": res["refused"]["count"],
           "contradictions": res["contradictions"]["count"], "splits": res["splits"]["count"],
           "merges": res["merges"]["count"], "objects": len(items), "fields": fields, "states": states}
    got["findings"] = projection_findings(kind, evs, took, got)
    return got


FAILED = ("errorcode", "error_code", "errormessage", "error_message", "failurereason", "failure_reason")
FAILURE_WORDS = {"failed", "failure", "error", "errored"}
MANY = 3                    # objects left in a state none ever leaves, before it is said
ONE_EACH = 20               # objects, each with about one event, past which the key may be an event's id


def _failed(e: dict) -> str | None:
    """The path that says the call an event records failed (an error code, a failure's reason, a result of failure)."""
    def walk(v, path, depth):
        if not isinstance(v, dict) or depth > 4:
            return None
        for k, x in v.items():
            low = str(k).lower()
            if low in FAILED and x not in (None, "", False):
                return ".".join((*path, str(k)))
            if low in ("result", "status", "outcome") and isinstance(x, str) and x.lower() in FAILURE_WORDS:
                return ".".join((*path, str(k)))
            if (got := walk(x, (*path, str(k)), depth + 1)) is not None:
                return got
        return None
    return walk(e.get("data") if isinstance(e.get("data"), dict) else {}, ("data",), 0)


def projection_findings(kind, evs: list[dict], took: dict, got: dict) -> list[dict]:
    """What the review's numbers show mechanically wrong with a projection, each ``{check, says, level}``: ``fail`` when
    it is clear (a field no event gives a value: it reads a path none has), ``warn`` for the reviewer and the owner to
    weigh (a state entered and never left, failed calls moving state, a state with no ``values:``, two writers of one
    field with no ``time:``, a key that looks like an event's id). Cheap: over the events the review already read."""
    from ..spec.handlers import env_of, evaluate
    out: list[dict] = []
    if not got.get("objects"):
        return out
    declared = getattr(kind, "declared", None) or {}
    kinds = {k.name: k for k in getattr(kind, "kinds", None) or []}
    by_kind: dict[str, list[dict]] = {}
    for e in evs:
        if (kn := took.get(e["id"])) is not None:
            by_kind.setdefault(kn, []).append(e)
    # every field gets a value on some object: one null on every object reads a path no event has (a fail), or is
    # cleared again by what follows (a warning)
    for f, row in (got.get("fields") or {}).items():
        if f not in declared or row.get("have") or getattr(declared[f], "expr", None):
            continue
        writers = [(kn, k.fields[f]) for kn, k in kinds.items() if f in k.fields]
        if not writers:
            continue
        fills = sum(1 for kn, v in writers for e in by_kind.get(kn, [])[-500:]
                    if evaluate(v, {**env_of(e, kind), "current": None}) is not None)
        texts = ", ".join(dict.fromkeys(v.text for _, v in writers))[:120]
        out.append({"check": "fills", "level": "fail",
                    "says": f"{f} is null on every one of {got['objects']} objects: {texts} reads a path none of the "
                            f"events that map it carries (events shape shows the paths they have)"} if not fills else
                   {"check": "fills", "level": "warn",
                    "says": f"{f} is null on every one of {got['objects']} objects, though {fills} events give it a "
                            f"value: what follows them clears it"})
    # every state but a final one has a way out
    final = set(getattr(kind, "final", None) or {}) | set(getattr(kind, "finished", None) or []) \
        | set(getattr(kind, "lost", None) or [])
    for f, st in (got.get("states") or {}).items():
        left = {m[0] for m in st.get("moves") or [] if m[0] is not None and m[0] != m[1]}
        values = st.get("values") or []
        for s, n in (st.get("now") or {}).items():
            if s in final or s in left or n < MANY:
                continue
            out.append({"check": "exit", "level": "warn",
                        "says": f"{f} {s!r}: {n} objects entered it and none ever left it, and it is not final: "
                                + ("if it ends the object, declare it under final:" if values and s == values[-1] else
                                   "what moves an object on from it? No kind of event does, in this record")})
    # failed calls do not move state
    for kn, k in kinds.items():
        v = k.fields.get("state")
        when = str(getattr(k.when, "text", "") or "").lower()
        if v is None or "error" in when or "fail" in when:
            continue
        bad, path = 0, None
        for e in by_kind.get(kn, [])[-2000:]:
            if (w := _failed(e)) is None:
                continue
            to = evaluate(v, {**env_of(e, kind), "current": None})
            if to is not None and str(to).lower() not in FAILURE_WORDS:
                bad, path = bad + 1, path or w
        if bad:
            out.append({"check": "failed-calls", "level": "warn",
                        "says": f"{kn} moves state on {bad} events whose {path} says the call failed: a failed call "
                                f"changed nothing in the world; leave them out of its when: (or give them a kind of "
                                f"event of their own that moves nothing)"})
    # a state read from the data is mapped to values:
    setters = [kn for kn, k in kinds.items() if "state" in k.fields]
    if setters and not getattr(kind, "states", None):
        out.append({"check": "values", "level": "warn",
                    "says": f"state is set (by {', '.join(setters[:3])}) with no values:: whatever the data carries is "
                            f"stored unchecked; list its states, in order, under values: (and map the source's words)"})
    # two writers of one field are ordered by the event's own time
    if getattr(kind, "own_time", None) is None:
        for f in ["state", *sorted(declared)]:
            writers = [kn for kn, k in kinds.items() if f in k.fields and by_kind.get(kn)]
            if len(writers) >= 2 and f not in (getattr(kind, "key", None) or []):
                out.append({"check": "time", "level": "warn",
                            "says": f"{f} is written by {len(writers)} kinds of event ({', '.join(writers[:3])}) and the "
                                    f"projection has no time:, so whichever arrives last wins; fold by the event's own "
                                    f"time (time: the path of the time the source stamped)"})
                break
    # the key is the object's identity, not an event's
    key_text = " ".join(v.text for k in kinds.values() for v in (k.key or [])).lower().replace("_", "")
    one_each = got["objects"] >= ONE_EACH and got["objects"] >= 0.95 * max(1, int(got.get("taken") or 0))
    if "eventid" in key_text or "requestid" in key_text or one_each:
        out.append({"check": "key", "level": "warn",
                    "says": f"{got['objects']} objects from {got.get('taken')} events: "
                            + ("nearly every object has one event; is the key an event's id, not the thing's?" if one_each
                               else "the key reads an event's (or a request's) id, not the thing's")})
    return out


WORSE = ("no_key", "refused", "contradictions", "splits")


def targeted(p, spec, after, ids: list[str]) -> dict:
    """The events of the groups these requests name (the newest ``JUDGE_MOST`` of each, by type): how many are
    unexplained with the model as it is and with the change."""
    from . import requests as rq
    have = rq.stored(p)
    before = with_it = read = 0
    for i in ids:
        g = (have.get(i) or {}).get("group") or {}
        if not g.get("type") and not g.get("source"):
            continue
        evs = p.events.query(n=JUDGE_MOST, type=g.get("type") or None, source=g.get("source") or None)
        evs = [e for e in evs if (not g.get("shape") or shape(e) == g["shape"]) and not own(e)
               and str(e.get("type") or "") == (g.get("type") or "")]
        read += len(evs)
        before += sum(1 for e in evs if why(spec, e) is not None)
        with_it += sum(1 for e in evs if why(after, e) is not None)
    return {"read": read, "before": before, "after": with_it}


def judged(p, x: dict, spec) -> tuple[str, str, dict]:
    """A change to the projections judged on the record it reads: ``(verdict, why, evidence)``; ``TrialError`` when its
    edit no longer applies."""
    from . import trial as tr
    after = tr.spec_after(p, tr.edits_of(x))
    t = targeted(p, spec, after, list(x.get("explains") or []))
    ev: dict = {"targeted": t, "projections": {}, "findings": []}
    worse = []
    for n in changed_projections(spec, after):
        try:
            a = residual_counts(p, after.items[n])
        except Exception as e:                      # its residual cannot be worked out: no evidence for it
            worse.append(f"{n}: its review cannot be made ({type(e).__name__}: {e})"[:300])
            continue
        b = None
        if n in (spec.items or {}):
            try:
                b = residual_counts(p, spec.items[n])
            except Exception:
                b = None
        ev["projections"][n] = {"before": b, "after": a}
        for f in WORSE:
            was = int((b or {}).get(f) or 0)
            if a[f] > was:
                worse.append(f"{n}: {a[f]} {f.replace('_', ' ')} (was {was})")
        had = {(g["check"], g["says"].split(":")[0]) for g in (b or {}).get("findings") or []}
        for g in a.get("findings") or []:            # the mechanical findings it adds: the clear ones fail it, the
            if (g["check"], g["says"].split(":")[0]) in had:  # rest go with it to the reviewer and the owner
                continue
            ev["findings"].append({"projection": n, **g})
            if g["level"] == "fail":
                worse.append(f"{n}: {g['says']}"[:300])
    new = (x.get("findings") or {}).get("new") or []
    if new:
        worse.append(f"{len(new)} new finding{'s' if len(new) > 1 else ''} of check's ({', '.join(new[:3])})")
    fell = t["before"] - t["after"]
    said = (f"of {t['read']} events it targets, {t['before']} unexplained before and {t['after']} with it")
    if worse:
        return "failed", f"{said}; but it adds " + "; ".join(worse[:4]), ev
    if fell <= 0:
        return "failed", f"{said}: it explains none of them", ev
    warns = [g for g in ev["findings"] if g["level"] != "fail"]
    return "passed", f"{said}: it explains {fell}, and adds no event with no key, no refusal, contradiction, split " \
                     f"or finding" + (f"; {len(warns)} for the reviewer: " + "; ".join(
                         f"{g['projection']}: {g['says']}" for g in warns[:2]) if warns else ""), ev


# ---- the drafter's edit: a draft put into the model

def draft_edit(p, spec, name: str, body: str) -> dict:
    """The edit that puts a drafted projection body in the model (in place of the one of that name, or at the end of
    ``projections:``), in the review queue's form."""
    from ..spec import trying
    from .structural import PENDING
    said = f"# inferred: {PENDING} (drafted by the modelling subsystem for events no projection took)\n"
    edit, _, _ = trying.placed(p, spec, name, said + body)   # what it adds says so (invariant 11): stamped with the
    return {"files": [edit.as_dict()]}                       # change's id when it is recorded


def proposal_of(p, spec, d: dict) -> dict:
    """A drafter's ``{"draft": {name, yaml, requests, title?, review?}}`` as an ordinary proposal: a structure change
    citing the requests it answers, its review's numbers in its reasons."""
    name, body = str(d.get("name") or ""), str(d.get("yaml") or "")
    from ..spec import trying
    name, body = trying.body_of(name, body)
    ids = [str(i).removeprefix("ergostat.modelling-request/") for i in (d.get("requests") or [])]
    rv = d.get("review") if isinstance(d.get("review"), dict) else {}
    says = str(d.get("says") or f"a projection {name} takes events no projection explains")
    if rv:
        says += " (its review: " + ", ".join(f"{k} {v}" for k, v in list(rv.items())[:8]) + ")"
    return {"kind": "structure", "parts": [f"items.{name}"] if name in (spec.items or {}) else [],
            "title": str(d.get("title") or (f"projection {name}" + (" changed" if name in (spec.items or {}) else " drafted"))),
            "edit": draft_edit(p, spec, name, body), "drafted": {name: body},
            "reasons": [{"says": says, "evidence": f"request:{i}"} for i in ids] or [{"says": says, "evidence": "none"}],
            "confidence": d.get("confidence") if isinstance(d.get("confidence"), (int, float)) else 0.6}
