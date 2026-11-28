"""The projection workbench's answers (SPEC §5a, *The workbench*; docs/roadmap/projection-workbench.md): what the page
(and an agent) asks while turning a query's events into a projection, each answer compact and every list capped.

- ``suggest(p, ask)``: the kinds of event a query's result holds, suggested from the data (``POST /api/events/kinds``):
  the result broken down by shape (the paths present, and the values that split it into structurally different
  groups), each with its count, a suggested ``when:``, the paths every event of it has, and two trimmed samples. Given
  ``taken`` (the ``when:``s of the kinds accepted), only the events none of them takes are suggested from, and a
  suggestion that would take no event (the first whose ``when:`` holds takes it) is left out.
- ``folded(p, ask)``: events folded by a draft into new objects (``POST /api/projections/fold``): the record one
  sample event makes.
- ``review(p, ask)``: a draft definition held against its events (``POST /api/projections/review``): per kind of event
  its count and the events it took; the remainder grouped by shape; per field its value distribution across the
  objects; per ``one of`` field the objects' lifecycle (its transitions, counted); the residual (the remainder, events
  with no key, refused events grouped by reason, contradictions, possible splits and merges); the comparison with the
  saved definition; the unmapped paths (paths in the kinds' events no field, key or ``time:`` reads, and not in
  ``ignore:``: what is left to decide); and, given ``item``, one object's timeline."""

from __future__ import annotations

import ast
import json
import keyword
import re
import time
from collections import Counter

from . import trying
from .trying import GROUPS, SAMPLES, TryError, said, trim

FIELDS_MOST = 30           # fields described, at most
TOP = 8                    # top values of a field
BUCKETS = 10               # a number's or a time's histogram
TRANSITIONS = 20           # transitions said per lifecycle
PATHS_MOST = 30            # paths said per kind suggested
MOST = 200_000             # events one answer reads, at most (the newest)
RARE = 0.01                # a transition in fewer than this share of the objects with the field: a contradiction
RARE_FROM = 50             # ... once at least this many objects have the field
TIMELINE_MOST = 200        # events in one object's timeline
KEYS_MOST = 1000           # objects' keys the item browser steps through
OPEN_MOST = 10             # whole events a residual group gives, to open in the mapping step
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED = ("data", "time", "type", "key", "source", "current", "true", "false", "null", "True", "False", "None")


# ---- the events asked for

def events_for(p, query: str | None, since=None, until=None, given=None) -> tuple[list[dict], dict]:
    """The events a query holds for (oldest first; the query engine, ``eventquery.py``), or the events given."""
    if given is not None:
        if not isinstance(given, list):
            raise TryError("events: a list of events (or leave it out to read the record)")
        return trying._normal(given, time.time()), {"source": "given"}
    if not query:
        raise TryError("query: an expression of the event saying which events to read")
    from ..eventquery import QueryError, events_matching
    try:
        evs, how = events_matching(p.events, query, since, until, MOST)
    except QueryError as e:
        raise TryError(str(e)) from None
    return evs, {"source": "record", **{k: v for k, v in how.items() if k != "paths"}, "paths": how.get("paths")}


# ---- kinds of event, suggested

def expr_path(path: str) -> str:
    """``data.detail.eventName`` as the expression language writes it (``data['detail-type']`` for a name that is not
    an identifier)."""
    parts = path.split(".")
    out = parts[0]
    for x in parts[1:]:
        out += f".{x}" if IDENT.match(x) and x not in RESERVED else f"[{x!r}]"
    return out


def literal(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return repr(v)


def _paths(e: dict, out: set, v=None, path="data", depth=0) -> None:
    v = (e.get("data") or {}) if v is None and depth == 0 else v
    if isinstance(v, dict) and depth < 4:
        for k, x in v.items():
            p = f"{path}.{k}"
            out.add(p)
            _paths(e, out, x, p, depth + 1)


def _slug(v) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-")
    s = s[:40].rstrip("-") or "event"
    return s if s[0].isalpha() else "e-" + s


TELLING = ("eventName", "event", "detail-type", "type", "action", "kind", "verb", "name", "status", "state")


def _telling(es: list[dict]) -> dict:
    """For a group nothing split: up to two paths whose one value all its events share and whose names say what
    happened (``detail.eventName``, ``detail-type``), most telling first; {} when none."""
    if not es:
        return {}
    sc = [trying._scalars(e) for e in es[:500]]
    same = {k: v for k, v in sc[0].items() if not k.endswith("[]") and isinstance(v, (str, bool, int))
            and all(s.get(k) == v for s in sc[1:])}
    ranked = sorted((k for k in same if k.rsplit(".", 1)[-1] in TELLING),
                    key=lambda k: (TELLING.index(k.rsplit(".", 1)[-1]), len(k)))
    return {k: same[k] for k in sorted(ranked[:2], key=len)}


def shapes(evs: list[dict], cap: int = GROUPS) -> dict:
    """Events grouped by shape (their type, then the one or two data paths whose values tell their shapes apart), each
    group with a suggested name and ``when:``, its count, the paths all its events have and two trimmed samples."""
    by_type: dict[str, list[dict]] = {}
    for e in evs:
        by_type.setdefault(e.get("type") or "", []).append(e)
    one_type = len(by_type) == 1
    groups = []
    for t, es in by_type.items():
        sc = [trying._scalars(e) for e in es]
        first = trying._splitter(es, sc, trying._purity(sc))
        if first is None:
            groups.append(({}, t, es))
            continue
        parts: dict = {}
        for e, s in zip(es, sc, strict=True):
            parts.setdefault(json.dumps(s.get(first)), []).append((e, s))
        for v, pairs in parts.items():
            sub_e, sub_s = [x[0] for x in pairs], [x[1] for x in pairs]
            second = trying._splitter(sub_e, sub_s, trying._purity(sub_s), outcome_too=False)
            if second is None:
                groups.append(({first: json.loads(v)}, t, sub_e))
                continue
            sub: dict = {}
            for e, s in pairs:
                sub.setdefault(json.dumps(s.get(second)), []).append(e)
            for v2, es2 in sub.items():
                groups.append(({first: json.loads(v), second: json.loads(v2)}, t, es2))
    groups.sort(key=lambda g: -len(g[2]))
    groups = [(split or _telling(es), t, es) for split, t, es in groups]
    used: set = set()
    out = []
    for split, t, es in groups[:cap]:
        terms = ([] if one_type else [f"type == {t!r}"]) + [
            (f"{expr_path(k)} == {literal(v)}" if v is not None else f"{expr_path(k)} == null") for k, v in split.items()]
        name = _slug(next(reversed(split.values())) if split else t)
        base, i = name, 2
        while name in used:
            name, i = f"{base}-{i}", i + 1
        used.add(name)
        common: set | None = None
        for e in es[:500]:
            ps: set = set()
            _paths(e, ps)
            common = ps if common is None else common & ps
        paths = sorted(common or ())
        out.append({"name": name, "count": len(es), "when": " and ".join(terms) or "true",
                    "shape": {"type": t, **{k.removeprefix("data."): trim(v) for k, v in split.items()}},
                    "paths": paths[:PATHS_MOST], **({"paths_left": len(paths) - PATHS_MOST} if len(paths) > PATHS_MOST else {}),
                    "samples": [trying._sample(e) for e in es[:SAMPLES]]})
    return {"count": len(evs), "kinds": out, **({"kinds_left": len(groups) - cap} if len(groups) > cap else {})}


def _whens(texts) -> list:
    """``when:``s as the query engine compiles them (one that does not compile is left out)."""
    from ..eventquery import QueryError, compile_query
    out = []
    for t in texts or ():
        try:
            out.append(compile_query(t if isinstance(t, str) else json.dumps(t)))
        except QueryError:
            pass
    return out


def _holds(q, e: dict) -> bool:
    from ..eventquery import _env
    from .handlers import evaluate
    return bool(q.literal) if q.tree is None else bool(evaluate(q, _env(e)))


KINDS_MOST = 200           # kinds of event one suggestion considers, at most (paged: offset, limit, all)


def suggest(p, ask: dict) -> dict:
    """``POST /api/events/kinds``: ``{query, since?, until?, events?, taken?, offset?, limit?, all?}`` → the kinds of
    event its result holds (``taken``: the accepted kinds' ``when:``s; only the events none of them takes are suggested
    from, and only suggestions that would take one), the largest first, ``limit`` of them (10) from ``offset`` (0),
    or every one (``all``: up to KINDS_MOST); ``kinds_left``: how many come after the page."""
    if not isinstance(ask, dict):
        raise TryError("a suggestion is {query, since?, until?, events?, taken?, offset?, limit?, all?}")
    t0 = time.time()
    evs, how = events_for(p, ask.get("query"), ask.get("since"), ask.get("until"), ask.get("events"))
    taken = _whens(ask.get("taken"))
    left = [e for e in evs if not any(_holds(q, e) for q in taken)] if taken else evs
    got = shapes(left, KINDS_MOST)
    rest, kept = left, []
    for k in got["kinds"]:                       # in order, the first whose when: holds takes an event
        q = _whens([k["when"]])
        if not q or not rest:
            continue
        mine = [e for e in rest if _holds(q[0], e)]
        if mine:
            rest = [e for e in rest if not _holds(q[0], e)] if len(mine) < len(rest) else []
            kept.append({**k, "count": len(mine)})

    def num(x, d):
        return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else d
    off = num(ask.get("offset"), 0)
    lim = len(kept) if ask.get("all") else max(1, num(ask.get("limit"), GROUPS))
    page = kept[off:off + lim]
    left_after = len(kept) - off - len(page) + got.get("kinds_left", 0)
    got.pop("kinds_left", None)
    return {"query": ask.get("query"), "taken": list(ask.get("taken") or []), "read": how, **got, "kinds": page,
            "count": len(evs), "untaken": len(left), "offset": off, "kinds_total": len(kept),
            **({"kinds_left": left_after} if left_after > 0 else {}),
            **({"window": w} if (w := window_note(p, ask.get("query"), ask.get("since"), ask.get("until"),
                                                  len(evs), ask.get("events"))) else {}),
            "took_s": round(time.time() - t0, 3)}


def window_note(p, query, since, until, read: int, given=None) -> dict | None:
    """When a window (since, until) leaves events out: how many the query holds in the whole record, the record's
    span, and the words to say it ("read 0 of 2,501 events: since 1h ago; the record spans 3d"); None otherwise."""
    if given is not None or (since is None and until is None):
        return None
    from ..eventquery import index_for, matches, compile_query, QueryError, _LOCK
    try:
        q = compile_query(query) if query else None
    except QueryError:
        return None
    with _LOCK:
        ix = index_for(p.events)
        whole = matches(ix, q)["total"] if q is not None else ix.count()
        lo, hi = ix.db.execute("select min(time), max(time) from ev").fetchone()
    if whole <= read:
        return None
    from ..durations import human as format_duration
    span = format_duration(max(0.0, (hi or 0) - (lo or 0))) if lo is not None else "0s"
    bits = []
    if since is not None:
        bits.append(f"since {format_duration(max(0.0, time.time() - since))} ago")
    if until is not None:
        bits.append(f"until {format_duration(max(0.0, time.time() - until))} ago")
    return {"read": read, "of": whole, "left_out": whole - read, "record_from": lo, "record_to": hi,
            "says": f"read {read:,} of {whole:,} events: {', '.join(bits)}; the record spans {span} "
                    f"(leave out since/until for the whole record)"}


# ---- paths: what the kinds' events hold, and what the draft reads of them

ROOTS = ("data", "type", "key", "source", "time")
UNMAPPED_READ = 300        # events read per kind of event for its paths


def chain(n) -> tuple | None:
    """The path an expression names (``data.detail['instance-id']`` → (data, detail, instance-id)); through a list's
    member (``data.items[0].id``), the list's path; None when it names none."""
    parts: list = []
    while isinstance(n, (ast.Attribute, ast.Subscript)):
        if isinstance(n, ast.Attribute):
            parts.append(n.attr)
        elif isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
            parts.append(n.slice.value)
        else:
            parts = []                           # a list's member, or a lookup by a value: the path up to it
        n = n.value
    if isinstance(n, ast.Name) and n.id in ROOTS:
        return (n.id, *reversed(parts))
    return None


def refs(tree, out: set) -> set:
    """Every path an expression reads (its longest: ``data.a.b``, not also ``data.a``)."""
    if tree is None:
        return out
    c = chain(tree)
    if c is not None:
        out.add(c)
        m = tree
        while isinstance(m, (ast.Attribute, ast.Subscript)):
            if isinstance(m, ast.Subscript) and not isinstance(m.slice, ast.Constant):
                refs(m.slice, out)
            m = m.value
        return out
    for x in ast.iter_child_nodes(tree):
        refs(x, out)
    return out


def path_of_text(s: str) -> tuple | None:
    """An ``ignore:`` entry as a path (None: not one)."""
    try:
        return chain(ast.parse(s.strip(), mode="eval").body)
    except SyntaxError:
        return None


def path_text(parts: tuple) -> str:
    """A path as the expression language (and the page) writes it."""
    out = str(parts[0])
    for x in parts[1:]:
        out += f".{x}" if IDENT.match(str(x)) and not keyword.iskeyword(str(x)) else f"[{str(x)!r}]"
    return out


def leaves(e: dict) -> set:
    """An event's paths to its values (a list a value whole): its type, source, key and data's."""
    out = {("type",)} if e.get("type") is not None else set()
    for k in ("source", "item"):
        if e.get(k) is not None:
            out.add(("source",) if k == "source" else ("key",))

    def walk(v, path, depth):
        if isinstance(v, dict) and v and depth < 8:
            for k, x in v.items():
                walk(x, (*path, str(k)), depth + 1)
        elif path != ("data",):
            out.add(path)
    walk(e.get("data") if isinstance(e.get("data"), dict) else {}, ("data",), 0)
    return out


def covered(path: tuple, by) -> bool:
    """Whether a path is read (or ignored) by one of ``by``: the same path, or one inside the other."""
    return any(path[:len(b)] == b or b[:len(path)] == path for b in by)


def unmapped(kind, evs: list[dict], took: dict) -> dict:
    """The paths in the kinds' events that no field, key, ``time:`` or ``when:`` of the kind that took them
    reads, and that are not ignored, each with how many events have it and which kinds: what is left to decide."""
    ignored = {x for x in (path_of_text(s) for s in kind.ignore) if x is not None}
    base: set = {("key",)} if kind.key is None else set()
    read = {}
    for k in kind.kinds:
        r = set(base)
        if kind.own_time is not None:
            refs(kind.own_time.tree, r)
        refs(k.when.tree, r)                         # what tells the kind's events apart is read too
        for v in (k.key or []):
            refs(v.tree, r)
        for v in k.fields.values():
            refs(v.tree, r)
        read[k.name] = r
    seen: dict[str, int] = Counter()
    count: Counter = Counter()
    where: dict[tuple, set] = {}
    for e in evs:
        kn = took.get(e["id"])
        if kn is None or kn not in read or seen[kn] >= UNMAPPED_READ:
            continue
        seen[kn] += 1
        for path in leaves(e):
            if covered(path, read[kn]) or covered(path, ignored):
                continue
            count[path] += 1
            where.setdefault(path, set()).add(kn)
    order = [k.name for k in kind.kinds]
    rows = [{"path": path_text(x), "events": c, "kinds": sorted(where[x], key=order.index)}
            for x, c in count.most_common()]
    return {"count": len(rows), "paths": rows[:FIELDS_MOST], **({"paths_left": len(rows) - FIELDS_MOST}
            if len(rows) > FIELDS_MOST else {}), "ignored": len(kind.ignore), "read": sum(seen.values())}


# ---- a draft, reviewed

def _histogram(nums: list[float]) -> list[list]:
    lo, hi = min(nums), max(nums)
    if lo == hi:
        return [[lo, hi, len(nums)]]
    w = (hi - lo) / BUCKETS
    counts = [0] * BUCKETS
    for x in nums:
        counts[min(BUCKETS - 1, int((x - lo) / w))] += 1
    return [[round(lo + i * w, 6), round(lo + (i + 1) * w, 6), c] for i, c in enumerate(counts)]


def _iso(t: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def distributions(kind, items: list) -> list[dict]:
    """Per field (the declared ones first, then any a spread brought), its value distribution across the objects."""
    from .fields import Type, seconds
    names = list(kind.declared) + sorted({f for it in items for f in it.fields} - set(kind.declared))
    if kind.states and "state" not in names:
        names.insert(0, "state")
    out = []
    for f in names[:FIELDS_MOST]:
        d = kind.declared.get(f)
        t = d.type if d is not None else Type(None)
        vals = [(it.state if f == "state" and kind.states else it.fields.get(f)) for it in items]
        have = [v for v in vals if v is not None]
        row = {"field": f, "type": str(t), "declared": d is not None, "have": len(have), "objects": len(items),
               **({"computed": True, "from": d.expr} if d is not None and d.expr else {})}
        nums = [v for v in have if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if t.base == "time" or (t.base is None and have and all(seconds(v) is not None and isinstance(v, str) for v in have[:50])):
            secs = [s for s in (seconds(v) for v in have) if s is not None]
            if secs:
                row.update(min=_iso(min(secs)), max=_iso(max(secs)),
                           histogram=[[_iso(a), _iso(b), c] for a, b, c in _histogram(secs)])
        elif nums and len(nums) >= len(have) * 0.9:
            row.update(min=min(nums), max=max(nums), histogram=_histogram(nums))
        elif have:
            c = Counter(json.dumps(v, sort_keys=True, default=str) if not isinstance(v, str) else v for v in have
                        if not isinstance(v, (dict, list)))
            if c:
                row["distinct"] = len(c)
                row["top"] = [[trim(k if not k.startswith(("{", "[", '"')) else k), n] for k, n in c.most_common(TOP)]
            sized = [len(v) for v in have if isinstance(v, (dict, list))]
            if sized:
                row["sizes"] = {"min": min(sized), "max": max(sized), "mean": round(sum(sized) / len(sized), 2)}
        if t.base not in (None,):
            bad = sum(1 for v in have if not t.fits(v))
            if bad:
                row["not_its_type"] = bad
        out.append(row)
    return out


def lifecycles(kind, items: list) -> dict:
    """Per ``one of`` field, its transitions across the objects (each with how many times, and in how many objects),
    the values the objects hold now, and the contradictions: a transition seen in under RARE of the objects that have
    the field (once RARE_FROM have it)."""
    out = {}
    for f, d in kind.declared.items():
        if d.type.base != "values":
            continue
        trans: Counter = Counter()
        objs: dict[tuple, set] = {}
        having = 0
        for it in items:
            if f == "state" and kind.states:
                steps = [(m["from"], m["to"]) for m in it.moves]
            else:
                steps = [(c["before"], c["after"]) for c in it.changes
                         if c.get("path") == "/" + f and c.get("op") in ("add", "replace", "remove")]
            if steps or it.fields.get(f) is not None:
                having += 1
            for s in steps:
                trans[s] += 1
                objs.setdefault(s, set()).add(it.id)
        now = Counter((it.state if f == "state" and kind.states else it.fields.get(f)) for it in items)
        rows = [{"from": a, "to": b, "count": n, "objects": len(objs[(a, b)])} for (a, b), n in trans.most_common()]
        rare = [r for r in rows if r["from"] is not None and having >= RARE_FROM and r["objects"] < RARE * having]
        out[f] = {"values": d.type.values, "objects": having, "now": {str(k): v for k, v in now.most_common() if k is not None},
                  "transitions": rows[:TRANSITIONS], **({"transitions_left": len(rows) - TRANSITIONS} if len(rows) > TRANSITIONS else {}),
                  "rare": [{**r, "samples": sorted(objs[(r["from"], r["to"])])[:SAMPLES]} for r in rare[:GROUPS]]}
    return out


def _first_fields(kind, ek) -> dict:
    """The fields a kind of event writes by ``first``: field → the value's expression (handlers.Value)."""
    from .handlers import Value
    out = {}
    for f, v in ek.fields.items():
        if v.call == "first" and v.tree is not None and len(v.tree.args) == 1:
            import ast
            out[f] = Value(ast.unparse(v.tree.args[0]), tree=v.tree.args[0])
    return out


def fold_all(kind, evs: list[dict], history: bool = True):
    """The draft's objects from the events (each folded by ``items.fold``, as the item index folds), and what happened
    to every event: the kind that took it, its keys."""
    from .changes import form_of
    from .items import fold
    by_key: dict[str, list[dict]] = {}
    took: dict[str, str | None] = {}
    remainder, unkeyed = [], []
    for e in evs:
        if not kind.reads(e):
            continue
        own = str(e.get("type") or "").startswith("ergostat.") or form_of(e) != "data"
        ek = None if own else kind.kind_of(e)
        took[e["id"]] = ek.name if ek is not None else None
        if ek is None and not own:
            remainder.append(e)
            continue
        keys = kind.keys_of(e)
        if not keys:
            unkeyed.append(e)
            continue
        for k in keys:
            by_key.setdefault(k, []).append(e)
    items = {k: fold(k, sorted(es, key=lambda x: (x["time"], x.get("seq") or 0)), kind, history=history)
             for k, es in by_key.items()}
    return items, by_key, took, remainder, unkeyed


def _whole(e: dict, took: dict) -> dict:
    """An event as the query engine gives it, and the kind of event that took it: one the page opens to map."""
    return {"seq": e.get("seq"), "id": e["id"], "time": e["time"], "type": e.get("type"), "item": e.get("item"),
            "source": e.get("source"), "data": e.get("data"), "kind": took.get(e["id"])}


REFUSED_AT = re.compile(r"^([A-Za-z_][\w-]*): (.+?) is not ")


def _refused_at(why: str) -> tuple[str | None, object]:
    """The field a refusal names and the value refused (``state: "stopping" is not one of its states``), else None."""
    m = REFUSED_AT.match(why)
    if not m:
        return None, None
    try:
        return m.group(1), json.loads(m.group(2))
    except ValueError:
        return m.group(1), m.group(2)


def _no_value(kind, ek, e: dict) -> list:
    """The key fields whose expression in kind of event ``ek`` reads no value in event ``e``."""
    from .handlers import Each, env_of, evaluate
    if not ek.key or not kind.key:
        return []
    env, out = env_of(e, kind), []
    for f, v in zip(kind.key, ek.key, strict=False):
        try:
            x = evaluate(v, env)
        except Exception:                                 # noqa: BLE001 - a part that fails reads nothing
            x = None
        xs = list(x) if isinstance(x, Each) else [x]
        if not any(y is not None and y != "" and not isinstance(y, (dict, list)) for y in xs):
            out.append(f)
    return out


def residual(kind, items: dict, by_key: dict, took: dict, remainder: list, unkeyed: list, lives: dict) -> dict:
    from .handlers import env_of, evaluate
    refusals: dict[str, list] = {}
    for it in items.values():
        for r in it.refused:
            refusals.setdefault(str(r["why"])[:160], []).append((it.id, r))
    contradictions = [{"field": f, **r} for f, lc in lives.items() for r in lc["rare"]]
    finals = [(k, r) for k, x in refusals.items() for _, r in x if r.get("form") == "final"]
    # splits: objects only kinds keyed another way ever wrote: the key the kinds that took the most events solve to is
    # the main way; an object none of those kinds wrote may be one thing named two ways
    sig = {k.name: tuple(v.text.strip() for v in k.key) for k in kind.kinds if k.key}
    by_sig: Counter = Counter()
    for kn in took.values():
        if kn in sig:
            by_sig[sig[kn]] += 1
    splits: dict[tuple, list] = {}
    if len(by_sig) > 1:
        main = by_sig.most_common(1)[0][0]
        others = {kn for kn, s in sig.items() if s != main}
        for key, es in by_key.items():
            ks = {took.get(e["id"]) for e in es} - {None}
            if ks and ks <= others:
                splits.setdefault(tuple(sorted(ks)), []).append(key)
    # merges: a field written by first twice, with different values (two births in one object's history)
    merges: dict[str, list] = {}
    kinds = {k.name: k for k in kind.kinds}
    firsts = {k.name: _first_fields(kind, k) for k in kind.kinds}
    for f, d in kind.declared.items():
        if d.fold == "first":
            for k in kind.kinds:
                v = k.fields.get(f)
                if v is not None and v.call is None:
                    firsts[k.name][f] = v
    for key, es in by_key.items():
        seen: dict[str, set] = {}
        for e in es:
            ek = kinds.get(took.get(e["id"]) or "")
            if ek is None:
                continue
            env = env_of(e, kind)
            for f, v in firsts[ek.name].items():
                x = evaluate(v, env)
                if x is not None:
                    seen.setdefault(f, set()).add(json.dumps(x, sort_keys=True, default=str))
        for f, vals in seen.items():
            if len(vals) > 1:
                merges.setdefault(f, []).append(key)
    # what the page opens in its mapping step: per kind with no key, per refusal, per split, its events whole
    nk: dict[str, list] = {}
    for e in unkeyed:
        nk.setdefault(took.get(e["id"]) or "-", []).append(e)
    nk_groups = []
    for kn, es in sorted(nk.items(), key=lambda kv: -len(kv[1]))[:GROUPS]:
        ek = kinds.get(kn)
        reads_none = Counter(f for e in es[:300] for f in (_no_value(kind, ek, e) if ek else []))
        nk_groups.append({"kind": kn, "count": len(es), "lacks": list(ek.untold) if ek and ek.untold else [],
                          "no_value": [f for f, _ in reads_none.most_common()],
                          "events": [_whole(e, took) for e in es[-OPEN_MOST:]]})
    by_id = {e["id"]: e for es in by_key.values() for e in es}
    ref_groups = []
    for w, x in sorted(refusals.items(), key=lambda kv: -len(kv[1]))[:GROUPS]:
        f, v = _refused_at(w)
        evs = [by_id[r["event"]] for _, r in x if r["event"] in by_id]
        ref_groups.append({"why": w, "count": len(x), "objects": len({k for k, _ in x}),
                           "events": [r["event"] for _, r in x[:SAMPLES]],
                           **({"field": f, "value": v} if f is not None else {}),
                           "kinds": [k for k, _ in Counter(took.get(e["id"]) for e in evs if took.get(e["id"])).most_common()],
                           "samples": [_whole(e, took) for e in evs[-OPEN_MOST:]]})
    main_sig = by_sig.most_common(1)[0][0] if by_sig else ()
    main_kinds = [kn for kn, s in sig.items() if s == main_sig]
    split_groups = []
    width = len(kind.key or [])
    mains = [k for k in by_key if k not in {x for v in splits.values() for x in v}]
    at: list[dict] = [{} for _ in range(width)]        # per key part, its value → the other objects' keys
    for k in mains:
        parts = k.split("/")
        if len(parts) == width:
            for i, x in enumerate(parts):
                at[i].setdefault(x, []).append(k)

    # a key part that tells objects apart: most objects keyed the main way have a value of their own there (an instance
    # id), unlike a part many share (an account, a region)
    distinct = [len(at[i]) > 0.5 * max(1, len(mains)) for i in range(width)]

    def alike(a: str, b: str) -> bool:
        """Two key values that are likely one thing written two ways: equal but for case or spaces, or one inside
        the other (an ARN and the id it ends with)."""
        x, y = a.strip().lower(), b.strip().lower()
        return x != y and bool(x) and bool(y) and (x == y.replace(" ", "") or x in y or y in x)

    def counterpart(key: str) -> tuple[str | None, list]:
        """An object keyed the main way that is likely the same thing as ``key``: every key part equal or alike, at
        least one alike (not merely equal account and region, which many objects share); and the key fields that
        differ. None when there is none: then it is no split, only an object the main kinds never reached."""
        parts = key.split("/")
        if len(parts) != width:
            return None, []
        for other in sorted({o for i, x in enumerate(parts) for o in at[i].get(x, ())}):
            theirs = other.split("/")
            same = [a == b for a, b in zip(parts, theirs, strict=True)]
            if any(sm and distinct[i] for i, sm in enumerate(same)):     # the part that tells objects apart is equal
                return other, [f for f, sm in zip(kind.key, same, strict=True) if not sm]
            if all(sm or alike(a, b) for sm, a, b in zip(same, parts, theirs, strict=True)) and not all(same):
                return other, [f for f, sm in zip(kind.key, same, strict=True) if not sm]
        if width == 1 or not mains:
            return None, []
        for other in mains:                               # a part that differs only in its form, the others equal
            theirs = other.split("/")
            if len(theirs) == width and all(a == b or alike(a, b) for a, b in zip(parts, theirs, strict=True)) \
                    and any(alike(a, b) for a, b in zip(parts, theirs, strict=True)):
                return other, [f for f, a, b in zip(kind.key, parts, theirs, strict=True) if a != b]
        return None, []

    real = {}
    for ks, v in splits.items():                          # a split only where its twin is found
        found = [k for k in v if counterpart(k)[0] is not None]
        if found:
            real[ks] = found
    splits = real
    for ks, v in sorted(splits.items(), key=lambda kv: -len(kv[1]))[:GROUPS]:
        twin, differ = counterpart(v[0])
        half = OPEN_MOST // 2 if twin else OPEN_MOST
        evs = by_key[v[0]][-half:] + (by_key[twin][-(OPEN_MOST - half):] if twin else [])
        split_groups.append({"kinds": list(ks), "objects": len(v), "samples": v[:SAMPLES], "main": main_kinds,
                             "differ": differ, **({"twin": twin} if twin else {}),
                             "events": [{**_whole(e, took), "object": v[0] if e in by_key[v[0]] else twin} for e in evs]})
    return {
        "remainder": shapes(remainder),
        "no_key": {"count": len(unkeyed), "by_kind": dict(Counter(took.get(e["id"]) or "-" for e in unkeyed).most_common(GROUPS)),
                   "lacks": {kn: kinds[kn].untold for kn in dict.fromkeys(took.get(e["id"]) for e in unkeyed)
                             if kn in kinds and kinds[kn].untold},
                   "groups": nk_groups, **shapes(unkeyed, GROUPS // 2)},
        "refused": {"count": sum(len(x) for x in refusals.values()), "groups": ref_groups},
        "contradictions": {"count": len(contradictions) + len(finals), "rare": contradictions[:GROUPS],
                           "after_final": len(finals)},
        "splits": {"count": sum(len(v) for v in splits.values()), "groups": split_groups},
        "merges": {"count": len({k for v in merges.values() for k in v}),
                   "fields": [{"field": f, "objects": len(v), "samples": v[:SAMPLES]}
                              for f, v in sorted(merges.items(), key=lambda kv: -len(kv[1]))[:GROUPS]]},
    }


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def compared(p, name: str, items: dict, since, until, saved=None) -> dict | None:
    """The draft's objects against the saved definition's (folded over its own query's events): the objects that
    appear, disappear, and whose fields change (per field, how many), with samples."""
    saved = saved if saved is not None else trying.existing(p.model.spec, name)
    if saved is None:
        return None
    q = saved.query.text if saved.query is not None else f"glob(key, {saved.id!r})"
    try:
        evs, how = events_for(p, q, since, until)
    except TryError as e:
        return {"error": str(e)}
    old, _, _, _, _ = fold_all(saved, evs, history=False)
    a, b = set(items), set(old)
    changed: Counter = Counter()
    samples: dict[str, list] = {}
    n_changed = 0
    for k in a & b:
        x, y = items[k], old[k]
        diff = [f for f in set(x.fields) | set(y.fields) if not _same(x.fields.get(f), y.fields.get(f))]
        if x.state != y.state:
            diff.append("state")
        if diff:
            n_changed += 1
        for f in diff:
            changed[f] += 1
            if len(samples.setdefault(f, [])) < SAMPLES:
                samples[f].append({"key": k, "saved": said(y.state if f == "state" else y.fields.get(f), 80),
                                   "draft": said(x.state if f == "state" else x.fields.get(f), 80)})
    return {"saved": len(b), "draft": len(a), "appear": len(a - b), "appear_sample": sorted(a - b)[:SAMPLES],
            "disappear": len(b - a), "disappear_sample": sorted(b - a)[:SAMPLES], "change": n_changed,
            "fields": [{"field": f, "objects": n, "samples": samples.get(f, [])} for f, n in changed.most_common(FIELDS_MOST)],
            "saved_read": how}


def timeline(kind, it, evs: list[dict], key: str, took: dict) -> dict:
    """One object's events in time order: which kind took each, each field's before → after, a move, a refusal."""
    if it is None:
        return {"key": key, "found": False}
    from .handlers import own_time
    ch: dict[str, list] = {}
    for c in it.changes:
        ch.setdefault(c["event"], []).append(c)
    mv = {m["event"]: m for m in it.moves}
    rf = {r["event"]: r for r in it.refused}
    rows = []
    late, newest = set(), None                       # arrived after an event of a later event time: late
    for e in sorted(evs, key=lambda e: (e["time"], e.get("seq") or 0)):
        t = own_time(kind, e) or e["time"]
        if newest is not None and t < newest:
            late.add(e["id"])
        newest = t if newest is None else max(newest, t)
    order = sorted(evs, key=lambda e: (own_time(kind, e) or e["time"], e.get("seq") or 0))
    for e in order[:TIMELINE_MOST]:
        t = own_time(kind, e)
        row = {"id": e["id"], "time": t, "recorded": e["time"], "type": e.get("type"), "kind": took.get(e["id"]),
               **({"late": True} if e["id"] in late else {})}
        cs = [c for c in ch.get(e["id"], []) if c.get("op") != "refused"]
        if cs:
            row["changes"] = [{"field": c["path"][1:] or "/", "before": trim(c["before"]), "after": trim(c["after"])}
                              for c in cs[:FIELDS_MOST]]
        if e["id"] in mv:
            row["move"] = {"from": mv[e["id"]]["from"], "to": mv[e["id"]]["to"]}
        if e["id"] in rf:
            row["refused"] = said(rf[e["id"]]["why"], 160)
        elif not cs and e["id"] not in mv:
            row["unchanged"] = True
        rows.append(row)
    return {"key": key, "found": True, "state": it.state, "events": len(evs), "order": "event time", "late": len(late),
            "steps": rows,
            **({"steps_left": len(evs) - TIMELINE_MOST} if len(evs) > TIMELINE_MOST else {}), "fields": trim(it.fields)}


LIST_MOST = 200            # objects one listing (state, where) gives, at most


def review(p, ask: dict) -> dict:
    """``POST /api/projections/review``: ``{name, yaml, since?, until?, item?, events?, compare?, state?, where?,
    width?}`` (``yaml``: the draft projection's body; ``compare``: false to leave out the comparison with the saved
    definition; ``state``/``where``: list the objects in that state, or for which that expression over the folded
    object holds (``state``, ``key``, ``name``, ``events``, ``fields.F``), up to ``limit`` (LIST_MOST); ``width``: the
    longest text said whole, 0 for any (the default)) → the review."""
    if not isinstance(ask, dict):
        raise TryError("a review is {name, yaml, since?, until?, item?, events?, compare?, state?, where?, width?}")
    w = ask.get("width")
    tok = trying.WIDTH.set(int(w) if isinstance(w, (int, float)) and not isinstance(w, bool) and w >= 0 else 0)
    try:
        return _review(p, ask)
    finally:
        trying.WIDTH.reset(tok)


def listed(kind, items: dict, state=None, where=None, limit=None) -> dict:
    """The folded objects in ``state`` (any of a list), or for which ``where`` holds (an expression over the object:
    ``state``, ``key``, ``name``, ``events``, ``fields.F``), each its key, name and state; at most ``limit``."""
    from .handlers import BadExpr, compile_value, evaluate
    from .items import display_name
    q = None
    if where not in (None, ""):
        try:
            q = compile_value(str(where), {}, ("state", "key", "name", "events", "fields"))
        except BadExpr as e:
            raise TryError(f"where: {e} (an expression over an object: state, key, name, events, fields.F)") from None
    states = None if state in (None, "") else ([str(x) for x in state] if isinstance(state, list) else
                                                [x.strip() for x in str(state).split(",") if x.strip()])
    most = max(1, min(int(limit), 5000)) if isinstance(limit, (int, float)) and not isinstance(limit, bool) else LIST_MOST
    got = []
    for k in sorted(items):
        it = items[k]
        if states is not None and it.state not in states:
            continue
        nm = display_name(kind, it) if kind.display is not None else None
        if q is not None and not evaluate(q, {"state": it.state, "key": k, "name": nm, "events": it.n,
                                              "fields": it.fields}):
            continue
        got.append({"key": k, **({"name": nm} if nm else {}), "state": it.state})
    return {**({"state": states} if states is not None else {}), **({"where": str(where)} if q is not None else {}),
            "count": len(got), "objects": got[:most], **({"objects_left": len(got) - most} if len(got) > most else {})}


def _review(p, ask: dict) -> dict:
    if not isinstance(ask, dict):
        raise TryError("a review is {name, yaml, since?, until?, item?, events?, compare?}")
    if getattr(p.model, "spec", None) is None:
        raise TryError("the model is an ergostat.toml: projections are declared in ergostat.yaml")
    text = ask.get("yaml")
    if not isinstance(text, str):
        raise TryError("yaml: the projection's body (query:, key:, fields:, events:...) as text")
    name, text = trying.body_of(ask.get("name"), text)
    if not name:
        raise TryError("name: the projection's name")
    spec, _, errors = trying.compiled(p, name, text, str(ask.get("system") or ""))
    out: dict = {"projection": name, "ok": not errors}
    if errors:
        return {**out, "errors": errors[:GROUPS]}
    kind = spec.items[name]
    t0 = time.time()
    since, until = ask.get("since"), ask.get("until")
    q = kind.query.text if kind.query is not None else f"glob(key, {kind.id!r})"
    evs, how = events_for(p, q, since, until, ask.get("events"))
    items, by_key, took, remainder, unkeyed = fold_all(kind, evs)
    taken = Counter(v for v in took.values() if v is not None)
    per_kind = []
    for k in kind.kinds:
        ids = [i for i, v in took.items() if v == k.name]
        per_kind.append({"name": k.name, "when": k.when.text if k.when.tree is not None else k.when.literal,
                         "count": taken.get(k.name, 0), "events": ids[:SAMPLES],
                         "objects": len({key for key, es in by_key.items() if any(took.get(e["id"]) == k.name for e in es)})})
    its = list(items.values())
    lives = lifecycles(kind, its)
    out.update({
        "read": {"events": len(evs), **how},
        "kinds": per_kind,
        "objects": {"count": len(items), "sample": sorted(items)[:3], "keys": sorted(items)[:KEYS_MOST],
                    "key": list(kind.key) if kind.key else ["key (the events' item)"],
                    "one_event": sum(1 for it in its if it.n == 1)},
        "fields": distributions(kind, its),
        "lifecycles": lives,
        "residual": residual(kind, items, by_key, took, remainder, unkeyed, lives),
        "duplicates": trying._dups([e for e in evs if took.get(e["id"]) is not None]),
        "unmapped": unmapped(kind, evs, took),
    })
    if kind.emit:                                # what each emit: entry would have published over this history (none is)
        from .emit import counted
        out["emits"] = counted(kind, by_key)
    if ask.get("compare", True) is not False and trying.existing(p.model.spec, name) is not None:
        out["compared"] = compared(p, name, items, since, until)
    if ask.get("expected") is not None:
        out["expected"] = trying.scored(items, ask["expected"])
    if kind.display is not None:                 # each listed object's name (SPEC §5a, *An object's name*), when it has one
        from .items import display_name
        out["objects"]["names"] = {k: nm for k in out["objects"]["keys"] if (nm := display_name(kind, items[k]))}
    if ask.get("state") not in (None, "", []) or ask.get("where") not in (None, ""):
        out["listed"] = listed(kind, items, ask.get("state"), ask.get("where"), ask.get("limit"))
    note = window_note(p, q, since, until, len(evs), ask.get("events"))
    if note:
        out["read"]["window"] = note
    if ask.get("item"):
        k = str(ask["item"])
        out["timeline"] = timeline(kind, items.get(k), by_key.get(k) or [], k, took)
        if kind.display is not None and items.get(k) is not None:
            from .items import display_name
            out["timeline"]["name"] = display_name(kind, items[k])
    out["took_s"] = round(time.time() - t0, 3)
    return out


def folded(p, ask: dict) -> dict:
    """``POST /api/projections/fold``: ``{name, yaml, events, system?}`` → the objects those events alone make by the
    draft (``objects: [{key, state, fields, refused}]``), and the kind of event that took each (``took``)."""
    if not isinstance(ask, dict) or not isinstance(ask.get("yaml"), str) or not isinstance(ask.get("events"), list):
        raise TryError("a fold is {name, yaml, events}")
    if getattr(p.model, "spec", None) is None:
        raise TryError("the model is an ergostat.toml: projections are declared in ergostat.yaml")
    name, text = trying.body_of(ask.get("name"), ask["yaml"])
    if not name:
        raise TryError("name: the projection's name")
    spec, _, errors = trying.compiled(p, name, text, str(ask.get("system") or ""))
    if errors:
        return {"ok": False, "errors": errors[:GROUPS]}
    kind = spec.items[name]
    evs = trying._normal(ask["events"][:50], time.time())
    items, _, took, remainder, unkeyed = fold_all(kind, evs)
    return {"ok": True, "took": took, "remainder": len(remainder), "no_key": len(unkeyed),
            "objects": [{"key": k, "state": it.state, "fields": trim(it.fields),
                         "refused": [said(r["why"], 160) for r in it.refused][:SAMPLES]} for k, it in items.items()]}
