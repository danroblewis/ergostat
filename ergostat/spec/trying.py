"""A projection tried before it is written (SPEC §5a, *Trying a projection*): its YAML body compiled in the context of
the model as it is (in memory: no file, no item index, no model changed), folded over the record's events (or events
given) by the same fold the item index uses (``items.fold``), and said as a small report, sized for an agent's
tokens: what it matched and by which handler, what it read and could not key, what changed nothing, what it refused,
its items and their fields, its states, the events that came twice, and, given what each item should be, how far it
is from that. The draft's items are kept here a while under a draft id, so the projection's own page can draw them
(``scratch``). ``shape`` is the stream's shape: each path into the events' JSON, its types, how often it is there
and a few of its values, so an agent reads that instead of the events themselves."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import yaml

MOST = 200_000            # the most events one try reads from the record (the newest)
GROUPS = 10               # the most groups any list holds
SAMPLES = 2
SAMPLE_CHARS = 200
FIELDS = 30
TRACE = 60                # the most events an item's trace lists
KEEP_S = 900              # how long a draft's items are kept for the page
DRAFTS_KEPT = 8
SKIP = ("agent.*", "loop.*", "valve.*", "controller.*", "model.*", "ergostat.*", "auxiliary.*", "variable.*",
        "trigger.*", "budget.*", "claude.*", "block.*", "person.*", "sensor.*")   # ergostat's own record, not a stream
NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class TryError(ValueError):
    """A try that cannot be made at all (no model, a name that is not one)."""


# ---- trimming: every value said is short

def trim(v, depth: int = 0):
    if isinstance(v, str):
        return v if len(v) <= 60 else v[:57] + "..."
    if isinstance(v, dict):
        if depth >= 3:
            return "{...}"
        out = {}
        for i, (k, x) in enumerate(v.items()):
            if i >= 8:
                out["..."] = f"+{len(v) - 8}"
                break
            out[k] = trim(x, depth + 1)
        return out
    if isinstance(v, list):
        if depth >= 3:
            return "[...]"
        return [trim(x, depth + 1) for x in v[:3]] + ([f"...+{len(v) - 3}"] if len(v) > 3 else [])
    return v


def said(v, most: int = SAMPLE_CHARS) -> str:
    s = json.dumps(trim(v), default=str, separators=(",", ":"))
    return s if len(s) <= most else s[:most - 3] + "..."


def _sample(e: dict) -> str:
    return said({"type": e.get("type"), **({"item": e["item"]} if e.get("item") else {}), "data": e.get("data")})


# ---- the draft as YAML lines in the model

def body_of(name: str | None, text: str) -> tuple[str, str]:
    """The projection's name and its body's text from what was given: a body (``match:``, ``events:``...), or a file
    of ``projections: {NAME: {...}}`` (its one projection, or ``name``'s)."""
    try:
        data = yaml.safe_load(text) if text and text.strip() else {}
    except yaml.YAMLError:
        return str(name or ""), text or ""              # said by check, with its line
    if isinstance(data, dict) and isinstance(data.get("projections"), dict):
        ps = data["projections"]
        pick = name if name in ps else (next(iter(ps)) if len(ps) == 1 else None)
        if pick is None:
            raise TryError(f"the file declares projections {', '.join(map(str, ps))}: name one (--name)")
        body = ps[pick] or {}
        return str(pick), yaml.safe_dump(body, sort_keys=False, allow_unicode=True)
    return str(name or ""), text or ""


def _dedent(text: str) -> list[str]:
    ls = text.replace("\t", "  ").rstrip("\n").split("\n") if text.strip() else []
    pad = min((len(x) - len(x.lstrip()) for x in ls if x.strip()), default=0)
    return [x[pad:] if x.strip() else "" for x in ls]


def _yaml_error(text: str) -> dict | None:
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        return {"line": mark.line + 1 if mark else None, "message": f"the YAML does not read: "
                f"{getattr(e, 'problem', None) or e}"}
    if data is not None and not isinstance(data, dict):
        return {"line": 1, "message": "a projection's body is a map (match:, key:, states:, events:...)"}
    if isinstance(data, dict) and "dashboards" in data:
        return {"line": None, "message": "dashboards: are edited on the page, not in the definition"}
    return None


def existing(spec, name: str):
    k = (getattr(spec, "items", None) or {}).get(name)
    return k if k is not None and getattr(k, "where", None) is not None else None


def definition_text(spec, name: str) -> str | None:
    """The projection's body as it is written in its file, its ``dashboards:`` left out (the page edits them)."""
    from ..numbers import display
    from ..numbers import yamledit as ye
    if existing(spec, name) is None:
        return None
    f, at = display._projection_line(spec, name)
    ls = ye.lines_of(f)
    end, _ = ye.children(ls, at)
    body = ls[at:end]
    dash = ye.key_line(ls, at, "dashboards")
    if dash is not None:
        dend, _ = ye.children(ls, dash)
        body = ls[at:dash - 1] + ls[dend:end]
    return "\n".join(_dedent("\n".join(body))) + "\n"


def placed(p, spec, name: str, text: str, system: str = ""):
    """The YAML edit that puts the draft in the model (in place of the projection, its ``dashboards:`` kept; a new one
    at the end of ``projections:`` in the system's file, else the main file), and the line its body starts on."""
    from ..numbers import display
    from ..numbers import yamledit as ye
    body = _dedent(text)
    k = (getattr(spec, "items", None) or {}).get(name)
    if k is not None and getattr(k, "where", None) is None:
        raise TryError(f"{name} is one of ergostat's own projections: name yours otherwise")
    if k is not None:
        f, at = display._projection_line(spec, name)
        ls = ye.lines_of(f)
        end, _ = ye.children(ls, at)
        head = ls[at - 1].split("#")[0].rstrip()
        pad = " " * (ye.indent(head) + 2)
        dash = ye.key_line(ls, at, "dashboards")
        kept = []
        if dash is not None:
            dend, _ = ye.children(ls, dash)
            kept = ls[dash - 1:dend]
        new = [head, *((pad + x) if x else "" for x in body), *kept]
        return ye.Edit(str(f), [ye.Hunk(at, ls[at - 1:end], new)]), at + 1, len(body)
    if not NAME.match(name):
        raise TryError(f"{name!r} is not a projection's name (lowercase letters, digits and -, starting with a letter)")
    f = (display.system_file(spec, system) if system else None) or Path(p.model.path)
    extra = [f"    system: {json.dumps(system)}"] if system and display._defaults_system(f) != system else []
    lines = [f"  {name}:", *extra, *(("    " + x) if x else "" for x in body)]
    edit = ye.add_entries(f, "projections", [lines])
    h = edit.hunks[0]
    start = h.line + next(i for i, x in enumerate(h.new) if x.strip() == f"{name}:") + 1 + len(extra)
    return edit, start, len(body)


def compiled(p, name: str, text: str, system: str = ""):
    """The model with the draft in it: ``(spec, edit, errors)``; each error of the draft's with its line in the body
    (None: not on one). The model's own errors elsewhere are not the draft's."""
    from ..numbers import trial as tr
    from ..numbers import yamledit as ye
    bad = _yaml_error(text)
    if bad:
        return None, None, [bad]
    spec = p.model.spec
    try:
        edit, start, n = placed(p, spec, name, text, system)
        texts = tr.texts_after([edit])
    except (ye.EditError, tr.TrialError, TryError) as e:
        return None, None, [{"line": None, "message": str(e)}]
    after, problems = tr.compiled(Path(p.model.path), texts)
    f = str(Path(edit.file).resolve())
    errors = []
    for x in problems:
        w = x.where
        line = None
        if w is not None and str(Path(str(w.file)).resolve()) == f and start <= w.line < start + max(n, 1):
            line = w.line - start + 1
        if line is not None or f"projection {name}" in x.message or f"projection {name}." in x.message:
            errors.append({"line": line, "message": x.message})
    if name not in after.items:
        errors = errors or [{"line": None, "message": f"projection {name} does not compile"}]
    return after, edit, errors


# ---- the events read

def _normal(evs: list, now: float) -> list[dict]:
    """Events given (recorded ones, or event lines: ``{"event": TYPE, "item", "data", "at"}``) as the record holds
    them: an id, a time, a type, a seq in the order given."""
    out = []
    n = len(evs)
    for i, e in enumerate(evs):
        if not isinstance(e, dict):
            continue
        t = e.get("time") if isinstance(e.get("time"), (int, float)) else e.get("at")
        out.append({"id": str(e.get("id") or f"given-{i + 1}"), "seq": i + 1,
                    "time": float(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else now - (n - i),
                    "type": str(e.get("type") or e.get("event") or ""), "item": e.get("item"),
                    "source": e.get("source"), "causedby": e.get("causedby"),
                    "data": e.get("data") if isinstance(e.get("data"), dict) else {},
                    **({"patch": e["patch"]} if e.get("patch") is not None else {}),
                    **({"set": e["set"]} if e.get("set") is not None else {})})
    return out


def read_events(p, since: float | None, until: float | None, limit: int | None) -> list[dict]:
    return p.events.query(n=max(1, min(int(limit or MOST), MOST)), since=since, until=until, skip=SKIP)


def handler_of(kind, e: dict) -> str:
    from .changes import form_of
    t = e.get("type") or ""
    if t.startswith("ergostat."):
        return "ergostat"
    if kind.handlers is None or form_of(e) != "data":
        return "fold" if form_of(e) == "data" else form_of(e)
    if t in kind.handlers:
        return t
    if "*" in kind.handlers:
        return "*"
    return f"otherwise: {kind.otherwise}"


# ---- telling groups apart

def _leaves(v, path: str, out: dict, depth: int = 0) -> None:
    if isinstance(v, dict) and depth < 5:
        for k, x in v.items():
            _leaves(x, f"{path}.{k}", out, depth + 1)
    elif isinstance(v, list):
        out[path + "[]"] = len(v)
    elif not isinstance(v, dict):
        out[path] = v


def _scalars(e: dict) -> dict:
    out: dict = {}
    _leaves(e.get("data") or {}, "data", out)
    return out


def _splitter(evs: list[dict], sc: list[dict], base: float) -> str | None:
    """The data path whose values best tell these events' shapes apart (each value's events of one shape): present in
    nine in ten of them, 2 to 20 values; None when none tells them apart better than ``base``."""
    n = len(evs)
    if n < 2:
        return None
    sigs = [frozenset(s) for s in sc]
    seen: dict[str, dict] = {}
    for s in sc:
        for k, v in s.items():
            if isinstance(v, (str, bool, int)) and not k.endswith("[]"):
                d = seen.setdefault(k, {})
                if len(d) <= 20:
                    d.setdefault(json.dumps(v), []).append(1)
    best, score = None, base
    for k, d in seen.items():
        have = sum(len(x) for x in d.values())
        if have < 0.9 * n or not 2 <= len(d) <= 20 or len(d) > max(2, have / 3):
            continue                                 # (an id, a time: a value of each its own tells nothing)
        by: dict = {}
        for s, sig in zip(sc, sigs, strict=True):
            if k in s:
                by.setdefault(json.dumps(s[k]), Counter())[sig] += 1
        purity = sum(c.most_common(1)[0][1] for c in by.values()) / n
        if purity > score + 0.02 or (best is not None and abs(purity - score) <= 0.02 and len(d) < len(seen[best])):
            best, score = k, max(purity, score)
    return best


def _purity(sc: list[dict]) -> float:
    c = Counter(frozenset(s) for s in sc)
    return c.most_common(1)[0][1] / len(sc) if sc else 1.0


def grouped(evs: list[dict], cap: int = GROUPS, samples: int = 1) -> dict:
    """Events grouped by shape: their type, then the one or two data paths whose values tell their shapes apart
    (``detail-type``, then ``detail.eventName``); each group's count and a sample, the largest first."""
    by_type: dict[str, list[dict]] = {}
    for e in evs:
        by_type.setdefault(e.get("type") or "", []).append(e)
    groups = []
    for t, es in by_type.items():
        sc = [_scalars(e) for e in es]
        first = _splitter(es, sc, _purity(sc))
        if first is None:
            groups.append(({"type": t}, es))
            continue
        parts: dict = {}
        for e, s in zip(es, sc, strict=True):
            parts.setdefault(json.dumps(s.get(first)), []).append((e, s))
        for v, pairs in parts.items():
            sub_e, sub_s = [x[0] for x in pairs], [x[1] for x in pairs]
            second = _splitter(sub_e, sub_s, _purity(sub_s))
            if second is None:
                groups.append(({"type": t, first.removeprefix("data."): json.loads(v)}, sub_e))
                continue
            sub: dict = {}
            for e, s in pairs:
                sub.setdefault(json.dumps(s.get(second)), []).append(e)
            for v2, es2 in sub.items():
                groups.append(({"type": t, first.removeprefix("data."): json.loads(v),
                                second.removeprefix("data."): json.loads(v2)}, es2))
    groups.sort(key=lambda g: -len(g[1]))
    out = [{"shape": trim(sh), "count": len(es), "samples": [_sample(e) for e in es[:samples]]}
           for sh, es in groups[:cap]]
    return {"count": len(evs), "groups": out, **({"groups_left": len(groups) - cap} if len(groups) > cap else {})}


# ---- fields

def _type_name(v) -> str:
    return "null" if v is None else "bool" if isinstance(v, bool) else "number" if isinstance(v, (int, float)) else \
        "text" if isinstance(v, str) else "list" if isinstance(v, list) else "object" if isinstance(v, dict) else \
        type(v).__name__


def fields_of(items: list) -> dict:
    n = len(items) or 1
    stats: dict[str, dict] = {}
    for it in items:
        for f, v in it.fields.items():
            s = stats.setdefault(f, {"have": 0, "types": Counter(), "values": Counter(), "nums": []})
            s["have"] += 1
            s["types"][_type_name(v)] += 1
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                s["nums"].append(v)
            elif isinstance(v, (str, bool)) or v is None:
                if len(s["values"]) < 500 or v in s["values"]:
                    s["values"][json.dumps(v)] += 1
    out = []
    for f, s in sorted(stats.items(), key=lambda x: (-x[1]["have"], x[0]))[:FIELDS]:
        d = {"field": f, "pct": round(100 * s["have"] / n, 1), "types": dict(s["types"])}
        if s["nums"]:
            d["min"], d["max"] = min(s["nums"]), max(s["nums"])
        if s["values"]:
            d["distinct"] = len(s["values"]) if len(s["values"]) < 500 else "500+"
            d["top"] = [[trim(json.loads(k)), c] for k, c in s["values"].most_common(5)]
        out.append(d)
    return {"fields": out, **({"fields_left": len(stats) - FIELDS} if len(stats) > FIELDS else {})}


# ---- what each item should have been

def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return a == b
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _cause(want, got, have: bool) -> str:
    if not have:
        return "missing"
    if _type_name(want) != _type_name(got):
        if isinstance(want, (int, float)) and isinstance(got, str) or isinstance(want, str) and isinstance(got, (int, float)):
            return "number vs text"
        return f"{_type_name(want)} expected, {_type_name(got)} folded"
    if isinstance(want, str) and want.lower() == got.lower():
        return "case"
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return "fewer" if got < want else "more"
    if isinstance(want, (dict, list)):
        return "different contents"
    return "different value"


def scored(items: dict, expected: dict) -> dict:
    """The items held against what each should be (key → fields; ``state`` its state): per field, how many match,
    and the mismatches grouped by their likely cause, with a sample or two."""
    if not isinstance(expected, dict):
        raise TryError("expected: a map of each item's key to the fields it should have")
    found = [k for k in expected if k in items]
    missing = [k for k in expected if k not in items]
    extra = [k for k in items if k not in expected]
    per: dict[str, dict] = {}
    for k in found:
        it, want = items[k], expected[k] if isinstance(expected[k], dict) else {}
        for f, w in want.items():
            have = f in it.fields or (f == "state" and it.state is not None)
            got = it.fields.get(f) if f in it.fields else (it.state if f == "state" else None)
            s = per.setdefault(f, {"field": f, "match": 0, "mismatch": 0, "causes": Counter(), "samples": []})
            if have and _same(w, got):
                s["match"] += 1
                continue
            s["mismatch"] += 1
            c = _cause(w, got, have)
            s["causes"][c] += 1
            if len(s["samples"]) < SAMPLES:
                s["samples"].append({"key": k, "expected": said(w, 80), "got": said(got, 80) if have else None,
                                     "cause": c})
    rows = sorted(per.values(), key=lambda s: (-s["mismatch"], s["field"]))[:FIELDS]
    for s in rows:
        s["causes"] = dict(s["causes"].most_common(4))
    total_m = sum(s["match"] for s in per.values())
    total = total_m + sum(s["mismatch"] for s in per.values())
    return {"items": {"expected": len(expected), "found": len(found), "missing": len(missing),
                      "missing_sample": missing[:3], "extra": len(extra), "extra_sample": extra[:3]},
            "fields_matched_pct": round(100 * total_m / total, 1) if total else None,
            "fields": rows}


# ---- the try

def _dups(evs: list[dict]) -> dict:
    """Events that came twice: the same id (the envelope's), or the same type and the same data whole (an upstream's
    own event id in it too, as EventBridge's ``data.id``): a handler that counts or appends counts them twice."""
    ids = Counter(e["id"] for e in evs)
    first: dict[str, str] = {}
    same: Counter = Counter()
    for e in evs:
        h = digest(json.dumps([e.get("type"), e.get("data")], sort_keys=True, default=str))
        if h in first:
            same[first[h]] += 1
        else:
            first[h] = e["id"]
    env = {k: c for k, c in ids.items() if c > 1}
    out = {"envelope_id": {"repeats": sum(env.values()) - len(env), "sample": list(env)[:SAMPLES]},
           "same_data": {"repeats": sum(same.values()), "sample": [k for k, _ in same.most_common(SAMPLES)]}}
    byid = {e["id"]: e for e in evs}
    data_id = any(isinstance((byid[k].get("data") or {}).get("id"), (str, int)) for k in same)
    if same:
        out["says"] = (f"{sum(same.values())} events repeat an earlier one's type and data whole"
                       f"{' (its data.id too)' if data_id else ''}: delivered twice, most likely; a handler that "
                       "counts or appends counts them twice")
    elif env:
        out["says"] = f"{sum(env.values()) - len(env)} events repeat an earlier one's id"
    return out


def run(p, name: str | None, text: str, since: float | None = None, until: float | None = None, events=None,
        expected=None, item: str | None = None, refused: str | None = None, limit: int | None = None,
        system: str = "", keep: bool = True) -> dict:
    """The try's report (see the module's words). Never raises for what the draft gets wrong: its check errors are
    the report (``ok`` false)."""
    if getattr(p.model, "spec", None) is None:
        raise TryError("the model is an ergostat.toml: projections are declared in ergostat.yaml")
    name, text = body_of(name, text)
    if not name:
        raise TryError("name: the projection's name")
    spec, _, errors = compiled(p, name, text, system)
    out: dict = {"projection": name, "ok": not errors}
    if errors:
        return {**out, "errors": errors[:GROUPS]}
    kind = spec.items[name]
    t0 = time.time()
    evs = _normal(events, t0) if events is not None else read_events(p, since, until, limit)
    from .items import fold
    read, unkeyed, by_key = [], [], {}
    for e in evs:
        if not kind.reads(e):
            continue
        read.append(e)
        k = kind.key_of(e)
        if k:
            by_key.setdefault(k, []).append(e)
        else:
            unkeyed.append(e)
    items = {k: fold(k, es, kind, history=True) for k, es in by_key.items()}
    changed: set[str] = set()
    refusals: dict[str, list] = {}
    for it in items.values():
        changed.update(c["event"] for c in it.changes)
        changed.update(m["event"] for m in it.moves)
        for r in it.refused:
            changed.add(r["event"])
            refusals.setdefault(str(r["why"])[:160], []).append((it.id, r))
    matched = [e for es in by_key.values() for e in es]
    handlers = Counter(handler_of(kind, e) for e in matched)
    n_all = len(evs)
    states = Counter(it.state for it in items.values() if it.state is not None)
    out.update({
        "events": {"read": n_all, "source": "given" if events is not None else "record",
                   **({"capped": True} if events is None and n_all >= (limit or MOST) else {})},
        "matched": {"count": len(matched), "pct": round(100 * len(matched) / n_all, 1) if n_all else 0.0,
                    "by_handler": dict(handlers.most_common(GROUPS))},
        "unmatched": {"not_read": grouped([e for e in evs if not kind.reads(e)], GROUPS // 2),
                      "no_key": grouped(unkeyed)},
        "unchanged": grouped([e for e in matched if e["id"] not in changed and not e["type"].startswith("ergostat.")]),
        "refused": {"count": sum(len(x) for x in refusals.values()),
                    "groups": [{"why": w, "count": len(x), "events": [r["event"] for _, r in x[:SAMPLES]]}
                               for w, x in sorted(refusals.items(), key=lambda kv: -len(kv[1]))[:GROUPS]]},
        "items": {"count": len(items), "key": [v.text for v in kind.key] if kind.key else ["key (the events' item)"],
                  "sample": list(items)[:3], "one_event": sum(1 for it in items.values() if it.n == 1)},
        **fields_of(list(items.values())),
        "states": dict(states.most_common()) if kind.states else None,
        "duplicates": _dups(read),
    })
    if expected is not None:
        out["expected"] = scored(items, expected)
    if item is not None:
        out["trace"] = trace(kind, items.get(item), by_key.get(item) or [], item)
    if refused is not None:
        hits = [(k, r) for w, x in refusals.items() if refused.lower() in w.lower() for k, r in x]
        byid = {e["id"]: e for e in matched}
        out["refused_events"] = {"reason": refused, "count": len(hits), "events": [
            {"id": r["event"], "time": r["time"], "type": r["type"], "item": k, "why": said(r["why"], 160),
             "event": _sample(byid[r["event"]]) if r["event"] in byid else None} for k, r in hits[:GROUPS]]}
    out["took_s"] = round(time.time() - t0, 3)
    if keep:
        out["draft"] = _keep(name, spec, read)
    return out


def trace(kind, it, evs: list[dict], key: str) -> dict:
    """An item's fold, event by event: which handler ran, each field before → after, a move, a refusal."""
    if it is None:
        return {"item": key, "found": False}
    ch: dict[str, list] = {}
    for c in it.changes:
        ch.setdefault(c["event"], []).append(c)
    mv = {m["event"]: m for m in it.moves}
    rf = {r["event"]: r for r in it.refused}
    rows = []
    for e in evs[:TRACE]:
        row = {"id": e["id"], "time": e["time"], "type": e["type"], "handler": handler_of(kind, e)}
        cs = [c for c in ch.get(e["id"], []) if c.get("op") != "refused"]
        if cs:
            row["changes"] = [{"field": c["path"][1:] or "/", "before": said(c["before"], 80), "after": said(c["after"], 80)}
                              for c in cs[:10]]
        if e["id"] in mv:
            row["move"] = f"{mv[e['id']]['from']} -> {mv[e['id']]['to']}"
        if e["id"] in rf:
            row["refused"] = said(rf[e["id"]]["why"], 160)
        rows.append(row)
    return {"item": key, "found": True, "state": it.state, "events": len(evs), "steps": rows,
            **({"steps_left": len(evs) - TRACE} if len(evs) > TRACE else {}), "fields": trim(it.fields)}


# ---- the stream's shape

def shape(evs: list[dict], most: int = 80) -> dict:
    """Each path into the events (``type``, ``item``, ``source``, ``data.a.b``; a list's members ``[]``): its types,
    how often it is there, how many values it takes, up to five of them."""
    n = len(evs)
    stats: dict[str, dict] = {}

    def walk(v, path: str, here: set, depth: int) -> None:
        s = stats.setdefault(path, {"n": 0, "types": Counter(), "values": set(), "examples": []})
        if path not in here:
            here.add(path)
            s["n"] += 1
        s["types"][_type_name(v)] += 1
        if isinstance(v, dict):
            if depth < 8:
                for k, x in v.items():
                    walk(x, f"{path}.{k}", here, depth + 1)
        elif isinstance(v, list):
            for x in v[:20]:
                walk(x, path + "[]", here, depth + 1)
        else:
            j = json.dumps(v, default=str)
            if len(s["values"]) <= 1000:
                s["values"].add(j)
            if len(s["examples"]) < 5 and v not in s["examples"]:
                s["examples"].append(v)

    for e in evs:
        here: set = set()
        for top in ("type", "item", "source"):
            if e.get(top) is not None:
                walk(e[top], top, here, 0)
        walk(e.get("data") or {}, "data", here, 0)
    types = Counter(e.get("type") for e in evs)
    rows = []
    for path, s in list(stats.items())[:most]:
        r = {"path": path, "pct": round(100 * s["n"] / n, 1) if n else 0, "types": dict(s["types"])}
        if s["values"]:
            r["distinct"] = len(s["values"]) if len(s["values"]) <= 1000 else "1000+"
            r["examples"] = [trim(x) for x in s["examples"]]
        rows.append(r)
    return {"events": n, "types": dict(types.most_common(GROUPS)), "paths": rows,
            **({"paths_left": len(stats) - most} if len(stats) > most else {})}


def stream_shape(p, type: str | None = None, since: float | None = None, limit: int | None = None,
                 draft: str | None = None) -> dict:
    if draft is not None:
        d = _get(draft)
        if d is not None and d["events"]:
            return {**shape(d["events"][-(limit or 5000):]), "of": f"the events projection {d['name']} reads"}
    n = max(1, min(int(limit or 5000), 50_000))
    evs = p.events.query(n=n, type=type or None, since=since, skip=() if type else SKIP)
    return {**shape(evs), "of": f"the newest {n} events" + (f" of type {type}" if type else "")}


# ---- the drafts kept for the page

_DRAFTS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _forget(d: dict) -> None:
    if d.get("dir"):
        shutil.rmtree(d["dir"], ignore_errors=True)


def _keep(name: str, spec, events: list[dict]) -> str:
    did = uuid.uuid4().hex[:12]
    with _LOCK:
        now = time.time()
        for k in [k for k, d in _DRAFTS.items() if now - d["at"] > KEEP_S]:
            _forget(_DRAFTS.pop(k))
        while len(_DRAFTS) >= DRAFTS_KEPT:
            _forget(_DRAFTS.pop(next(iter(_DRAFTS))))
        _DRAFTS[did] = {"name": name, "spec": spec, "events": events, "at": now, "project": None, "dir": None}
    return did


def _get(did: str) -> dict | None:
    with _LOCK:
        d = _DRAFTS.get(str(did))
        if d is not None and time.time() - d["at"] > KEEP_S:
            _forget(_DRAFTS.pop(str(did)))
            return None
        return d


def scratch(p, did: str):
    """The project as the page reads it for a draft: the model with the draft in it, and a record of its own holding
    only the events the draft reads (in a folder of its own, never the project's); None when the draft is gone."""
    d = _get(did)
    if d is None:
        return None
    with _LOCK:
        if d["project"] is not None:
            return d["project"]
        from ..store import Events
        folder = Path(tempfile.mkdtemp(prefix="ergostat-draft-"))
        ev = Events(folder)
        ev.add_many([{"id": e["id"], "at": e["time"], "type": e["type"], "item": e.get("item"), "source": e.get("source"),
                      "causedby": e.get("causedby"), "data": e.get("data"), "patch": e.get("patch"), "set": e.get("set")}
                     for e in d["events"]])
        sp = copy.copy(p)
        m = copy.copy(p.model)
        m.spec = d["spec"]
        sp.model, sp.events = m, ev
        d["project"], d["dir"] = sp, str(folder)
        return sp


def digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


# ---- said at a glance

def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def text_of(r: dict) -> str:
    """The report as a few aligned lines (the CLI's)."""
    if not r.get("ok"):
        return "\n".join([f"projection {r['projection']}: does not check"] +
                         [f"  {'line ' + str(e['line']) + ': ' if e.get('line') else ''}{e['message']}" for e in r["errors"]])
    m, ev = r["matched"], r["events"]
    out = [f"projection {r['projection']}: {_n(ev['read'])} events read ({ev['source']}"
           f"{', capped' if ev.get('capped') else ''}), {r['took_s']}s",
           f"  matched    {_n(m['count']):>8}  {m['pct']}%   " + ", ".join(f"{h} {_n(c)}" for h, c in m["by_handler"].items())]

    def groups(label, g):
        if not g["count"]:
            return
        out.append(f"  {label:<10} {_n(g['count']):>8}")
        for x in g["groups"]:
            sh = " ".join(f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in x["shape"].items())
            out.append(f"    {_n(x['count']):>8}  {sh}")
        if g.get("groups_left"):
            out.append(f"    ... {g['groups_left']} more groups")
    groups("not read", r["unmatched"]["not_read"])
    groups("no key", r["unmatched"]["no_key"])
    groups("unchanged", r["unchanged"])
    if r["refused"]["count"]:
        out.append(f"  refused    {_n(r['refused']['count']):>8}")
        out += [f"    {_n(g['count']):>8}  {g['why']}" for g in r["refused"]["groups"]]
    it = r["items"]
    out.append(f"  items      {_n(it['count']):>8}  key {' / '.join(it['key'])}; {it['one_event']} with one event"
               + (f"; e.g. {', '.join(it['sample'][:2])}" if it["sample"] else ""))
    if r.get("states"):
        out.append("  states     " + ", ".join(f"{s} {_n(c)}" for s, c in r["states"].items()))
    for f in r["fields"]:
        vals = f"{f['min']}..{f['max']}" if "min" in f else ", ".join(f"{json.dumps(v)} {c}" for v, c in f.get("top", [])[:3])
        out.append(f"    {f['field']:<18} {f['pct']:>5}%  {'/'.join(f['types'])}  {vals}"[:140])
    d = r["duplicates"]
    if d.get("says"):
        out.append(f"  duplicates {d['says']}")
    if "expected" in r:
        x = r["expected"]
        i = x["items"]
        out.append(f"  expected   {i['found']}/{i['expected']} items found ({i['missing']} missing, {i['extra']} extra); "
                   f"fields {x['fields_matched_pct']}% right")
        for f in x["fields"]:
            if f["mismatch"]:
                cs = ", ".join(f"{c} {n}" for c, n in f["causes"].items())
                s = f["samples"][0] if f["samples"] else None
                out.append(f"    {f['field']:<18} {f['match']} right, {f['mismatch']} wrong ({cs})"
                           + (f"  e.g. {s['key']}: {s['expected']} != {s['got']}" if s else "")[:200])
    if "trace" in r:
        t = r["trace"]
        if not t["found"]:
            out.append(f"  trace      {t['item']}: no such item")
        else:
            out.append(f"  trace      {t['item']}: {t['events']} events, now {t['state']}")
            for s in t["steps"]:
                what = "; ".join(f"{c['field']} {c['before']} -> {c['after']}" for c in s.get("changes", []))
                out.append(f"    {s['type']:<20} {s['handler']:<18} {s.get('move', '')} {what} "
                           f"{'REFUSED ' + s['refused'] if s.get('refused') else ''}".rstrip()[:200])
    if "refused_events" in r:
        x = r["refused_events"]
        out.append(f"  refused '{x['reason']}': {x['count']}")
        out += [f"    {e['id']} {e['item']}: {e['why']}" for e in x["events"]]
    return "\n".join(out)


def shape_text(r: dict) -> str:
    out = [f"{_n(r['events'])} events ({r.get('of', '')}); types: " + ", ".join(f"{t} {_n(c)}" for t, c in r["types"].items())]
    for x in r["paths"]:
        ex = ", ".join(json.dumps(v, default=str) for v in x.get("examples", []))
        out.append(f"  {x['path']:<40} {x['pct']:>5}%  {'/'.join(x['types']):<12} "
                   f"{('distinct ' + str(x['distinct'])) if 'distinct' in x else '':<14} {ex}"[:160].rstrip())
    if r.get("paths_left"):
        out.append(f"  ... {r['paths_left']} more paths")
    return "\n".join(out)
