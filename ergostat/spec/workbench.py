"""The projection workbench's answers (SPEC §5a, *The workbench*; docs/roadmap/projection-workbench.md): what the page
(and an agent) asks while turning a query's events into a projection, each answer compact and every list capped.

- ``suggest(p, ask)``: the kinds of event a query's result holds, suggested from the data (``POST /api/events/kinds``):
  the result broken down by shape (the paths present, and the values that split it into structurally different
  groups), each with its count, a suggested ``when:``, the paths every event of it has, and two trimmed samples.
- ``review(p, ask)``: a draft definition held against its events (``POST /api/projections/review``): per kind of event
  its count and the events it took; the remainder grouped by shape; per field its value distribution across the
  objects; per ``one of`` field the objects' lifecycle (its transitions, counted); the residual (the remainder, events
  with no key, refused events grouped by reason, contradictions, possible splits and merges); the comparison with the
  saved definition; and, given ``item``, one object's timeline."""

from __future__ import annotations

import json
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
            second = trying._splitter(sub_e, sub_s, trying._purity(sub_s))
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


def suggest(p, ask: dict) -> dict:
    """``POST /api/events/kinds``: ``{query, since?, until?, events?}`` → the kinds of event its result holds."""
    if not isinstance(ask, dict):
        raise TryError("a suggestion is {query, since?, until?, events?}")
    t0 = time.time()
    evs, how = events_for(p, ask.get("query"), ask.get("since"), ask.get("until"), ask.get("events"))
    return {"query": ask.get("query"), "read": how, **shapes(evs), "took_s": round(time.time() - t0, 3)}


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
        row = {"field": f, "type": str(t), "declared": d is not None, "have": len(have), "objects": len(items)}
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
        if d.type.base != "one of":
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


def residual(kind, items: dict, by_key: dict, took: dict, remainder: list, unkeyed: list, lives: dict) -> dict:
    from .handlers import env_of, evaluate
    refusals: dict[str, list] = {}
    for it in items.values():
        for r in it.refused:
            refusals.setdefault(str(r["why"])[:160], []).append((it.id, r))
    contradictions = [{"field": f, **r} for f, lc in lives.items() for r in lc["rare"]]
    finals = [(k, r) for k, x in refusals.items() for _, r in x if r.get("form") == "final"]
    # splits: objects only kinds with a key of their own ever wrote, when kinds keyed the default way exist
    own_keyed = {k.name for k in kind.kinds if k.key is not None}
    default_keyed = {k.name for k in kind.kinds if k.key is None}
    splits: dict[tuple, list] = {}
    if own_keyed and default_keyed:
        for key, es in by_key.items():
            ks = {took.get(e["id"]) for e in es} - {None}
            if ks and ks <= own_keyed:
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
    return {
        "remainder": shapes(remainder),
        "no_key": {"count": len(unkeyed), "by_kind": dict(Counter(took.get(e["id"]) or "-" for e in unkeyed).most_common(GROUPS)),
                   **shapes(unkeyed, GROUPS // 2)},
        "refused": {"count": sum(len(x) for x in refusals.values()),
                    "groups": [{"why": w, "count": len(x), "objects": len({k for k, _ in x}),
                                "events": [r["event"] for _, r in x[:SAMPLES]]}
                               for w, x in sorted(refusals.items(), key=lambda kv: -len(kv[1]))[:GROUPS]]},
        "contradictions": {"count": len(contradictions) + len(finals), "rare": contradictions[:GROUPS],
                           "after_final": len(finals)},
        "splits": {"count": sum(len(v) for v in splits.values()),
                   "groups": [{"kinds": list(ks), "objects": len(v), "samples": v[:SAMPLES]}
                              for ks, v in sorted(splits.items(), key=lambda kv: -len(kv[1]))[:GROUPS]]},
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
    order = sorted(evs, key=lambda e: (own_time(kind, e) or e["time"], e.get("seq") or 0))
    for e in order[:TIMELINE_MOST]:
        t = own_time(kind, e)
        row = {"id": e["id"], "time": t, "recorded": e["time"], "type": e.get("type"), "kind": took.get(e["id"])}
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
    return {"key": key, "found": True, "state": it.state, "events": len(evs), "steps": rows,
            **({"steps_left": len(evs) - TIMELINE_MOST} if len(evs) > TIMELINE_MOST else {}), "fields": trim(it.fields)}


def review(p, ask: dict) -> dict:
    """``POST /api/projections/review``: ``{name, yaml, since?, until?, item?, events?, compare?}`` (``yaml``: the draft
    projection's body; ``compare``: false to leave out the comparison with the saved definition) → the review."""
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
        "objects": {"count": len(items), "sample": sorted(items)[:3],
                    "key": [v.text for v in kind.key] if kind.key else ["key (the events' item)"],
                    "one_event": sum(1 for it in its if it.n == 1)},
        "fields": distributions(kind, its),
        "lifecycles": lives,
        "residual": residual(kind, items, by_key, took, remainder, unkeyed, lives),
        "duplicates": trying._dups([e for e in evs if took.get(e["id"]) is not None]),
    })
    if ask.get("compare", True) is not False and trying.existing(p.model.spec, name) is not None:
        out["compared"] = compared(p, name, items, since, until)
    if ask.get("expected") is not None:
        out["expected"] = trying.scored(items, ask["expected"])
    if ask.get("item"):
        k = str(ask["item"])
        out["timeline"] = timeline(kind, items.get(k), by_key.get(k) or [], k, took)
    out["took_s"] = round(time.time() - t0, 3)
    return out
