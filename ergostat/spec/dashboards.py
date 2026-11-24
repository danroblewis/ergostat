"""``dashboards:``: shared, named dashboards, read and checked like a system's ``show:`` (SPEC §4f). Each panel's
parameters are exactly those its endpoint and page address take; every reference in them must name something
the model has, or it is an error at its line, so a renamed stock is a finding instead of a blank panel."""

from __future__ import annotations

import json
import math

from ..durations import DurationError, parse_duration
from .ir import NAME, Dashboard, Panel, Ref
from .load import Map, Problem

MOST = 24                          # panels in one dashboard (docs/proposals/dashboard.md, section 6, rule 5)
SIZES = ("s", "m", "l", "full", "s-tall", "m-tall", "l-tall", "full-tall")
DASHBOARD_KEYS = {"title", "description", "window", "panels"}
PANEL_KEYS = {"panel", "title", "size", "note"}
ITEM_SET = {"kind", "state", "where", "moved", "moved_since", "moved_until", "through", "followed", "search", "n"}
# each kind of panel → the parameters it takes (those of its endpoint, by the same names)
KINDS = {
    "note": {"text"},
    "goals": {"goals"},                                   # the loops rows (GET /api/loops), these goals or all
    "chart": {"refs", "points", "replay", "fan"},         # GET /api/series
    "items": ITEM_SET,                                    # GET /api/items
    "states": {"kind", "points"},                         # GET /api/items-flow
    "cycle-time": {"kind", "points"},                     # GET /api/items-flow
    "scope": {"goal", "points"},                          # GET /api/loop-scope
    "items-graph": {"kinds", "system"},                   # GET /api/items-graph
    "timeline": {"kinds", "system"},                      # GET /api/items-graph
    "query": {"form", "queries", "display", "layout"},   # the page's own panel, as a kept draft holds it (GET /api/query)
}
NEEDS = {"query": "queries","chart": "refs", "states": "kind", "cycle-time": "kind", "scope": "goal", "items": "kind", "note": "text"}
TEXTS = {"text", "moved", "moved_since", "moved_until", "through", "followed", "search"}
LISTS = {"refs", "goals", "kinds", "state", "where"}     # a list, or one string (comma-separated as the address writes it)


def take(doc, data: Map, defaults: dict) -> None:
    """At load: each dashboard of this file, named SYSTEM.NAME when the file's ``defaults:`` sets a system."""
    body = data["dashboards"]
    if not isinstance(body, dict):
        doc.problems.append(Problem("error", "dashboards: must be a map, each dashboard keyed by its name",
                                    data.at("dashboards"), "not-a-map"))
        return
    system = defaults.get("system")
    for name, entry in body.items():
        w = body.at(name)
        if not isinstance(name, str) or not NAME.match(name):
            doc.problems.append(Problem("error", f"dashboard {name}: a name is lowercase letters, digits and -, starting "
                                        "with a letter", w, "bad-name"))
            continue
        full = f"{system}.{name}" if system else name
        if full == "default":
            doc.problems.append(Problem("error", "dashboard default: is the model's own (each top system's measures and "
                                        "goals); name this one otherwise", w, "bad-name"))
            continue
        if full in doc.dashboards:
            doc.problems.append(Problem("error", f"dashboard {full} is defined twice: here and at {doc.dashboards[full][1]}",
                                        w, "defined-twice", f"dashboard.{full}"))
            continue
        doc.dashboards[full] = (entry, w, system)


def names(v) -> list | None:
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
        return [str(x) for x in v]
    return None


def check(c, spec, exists) -> None:
    """At compile, once every part is read: each dashboard's keys, caps and references (``exists``: the compiler's
    own check of a reference, as ``show:``'s)."""
    for name, (m, w, system) in c.doc.dashboards.items():
        what = f"dashboard {name}"
        if not isinstance(m, dict):
            c.err(f"{what}: a map of its keys (title, description, window, panels)", w, "not-a-map")
            continue
        c.keys(m, DASHBOARD_KEYS, what)
        _words(c, m, ("title", "description"), what)
        window = None
        if m.get("window") is not None:
            try:
                window = parse_duration(m["window"], f"{what}.window")
            except (DurationError, OverflowError, ValueError) as e:
                c.err(f"{e} (like 1h, 1d, 7d)", m.at("window"), "bad-duration")
            if window is not None and not math.isfinite(window):
                c.err(f"{what}.window: {m['window']!r} is not a duration (like 1h, 1d, 7d)", m.at("window"), "bad-duration")
                window = None
            if window is not None and window > spec.keep:
                c.err(f"{what}.window: longer than keep: ({spec.keep / 86400:g}d): the record holds no more", m.at("window"),
                      "bad-dashboard")
                window = None
        panels = m.get("panels")
        if not isinstance(panels, list) or not panels:
            c.err(f"{what}.panels: a list of panels, each {{panel: KIND, ...}}", m.at("panels"), "bad-dashboard")
            panels = []
        if len(panels) > MOST:
            c.err(f"{what}.panels: {len(panels)} panels; at most {MOST}", m.at("panels"), "bad-dashboard")
            panels = []
        d = Dashboard(name, str(m.get("title") or ""), str(m.get("description") or ""), window, system=system, where=w)
        for i, x in enumerate(panels):
            got = _panel(c, spec, exists, x, f"{what}.panels[{i}]", m.at("panels"))
            if got is not None:
                d.panels.append(got)
        spec.dashboards[name] = d


def _panel(c, spec, exists, x, what: str, near) -> Panel | None:
    if not isinstance(x, dict):
        c.err(f"{what}: a map, {{panel: KIND, ...}}", near, "bad-dashboard")
        return None
    at = x.at if isinstance(x, Map) else (lambda k: near)
    kind = x.get("panel")
    if kind not in KINDS:
        c.err(f"{what}.panel: {kind!r} is not a kind of panel (known: {', '.join(KINDS)})", at("panel"), "bad-dashboard")
        return None
    c.keys(x, PANEL_KEYS | KINDS[kind], f"{what} ({kind})")
    _words(c, x, ("title", "note"), what)
    size = x.get("size", "m")
    if size not in SIZES:
        c.err(f"{what}.size: one of {', '.join(SIZES)}", at("size"), "bad-dashboard")
    if NEEDS.get(kind) and x.get(NEEDS[kind]) is None:
        c.err(f"{what}: a {kind} panel needs {NEEDS[kind]}:", at("panel"), "bad-dashboard")
        return None
    params: dict = {}
    ok = True
    for k in sorted(KINDS[kind] & set(x)):
        v, w = x[k], at(k)
        if k in LISTS:                     # kept as written (a round trip); read as a list for the checks
            v = names(v) if not (k == "where" and isinstance(v, str)) else [v]
            params[k] = x[k]
            if v is None:
                c.err(f"{what}.{k}: a name, or a list of them", w, "bad-dashboard")
                ok = False
                continue
        elif k in ("points", "n"):
            low, top = (2, 1000) if k == "points" else (1, 500)
            if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= top:
                c.err(f"{what}.{k}: a whole number from {low} to {top}", w, "bad-dashboard")
                ok = False
                continue
        elif k in ("replay", "fan"):
            if not isinstance(v, bool):
                c.err(f"{what}.{k}: true or false", w, "bad-dashboard")
                ok = False
                continue
        elif k in TEXTS or k in ("kind", "goal", "system"):
            if not isinstance(v, str) or not v:
                c.err(f"{what}.{k}: text", w, "bad-dashboard")
                ok = False
                continue
        elif k == "queries":
            ok = _queries(c, spec, v, what, w) and ok
        elif k in ("display", "layout") and not isinstance(v, dict):
            c.err(f"{what}.{k}: a map", w, "bad-dashboard")
            ok = False
            continue
        elif k == "form" and (not isinstance(v, str) or not v):
            c.err(f"{what}.{k}: text", w, "bad-dashboard")
            ok = False
            continue
        params.setdefault(k, v)
        ok = _refs(c, spec, exists, k, v, params, what, w) and ok
    if ok and kind == "items":
        from .item_sets import BadSet, parse
        try:
            parse(query(params))
        except BadSet as e:
            c.err(f"{what}: {e}", at("panel"), "bad-dashboard")
            ok = False
    if not ok:
        return None
    return Panel(kind, str(x.get("title") or ""), size if size in SIZES else "m", str(x.get("note") or ""), params,
                 getattr(x, "where", None) or near)


def sent(v) -> tuple[list, list]:
    """A query panel's queries as the page sends them (panels.js ``queryPanels``, its ``send``): its own words (``id``,
    ``label``, ``hidden``) left out; an ``input`` or ``output`` naming another query by id gets that query, as
    written, in its place (one level); an ``x.query`` by id is sent as a query of its own, named by its new id; a
    reference that leads nowhere, or back along its path, gets an ``unknown:`` name the engine refuses; queries asked
    alike are sent once, as ``q0``, ``q1``, .... Unlike the page, every query is sent (a hidden one too) and no form's
    ``ask`` is applied. Returns the queries sent, and each written query's id with the id it went as. At most
    ``MOST_QUERIES`` are read, so an ``x.query`` chain is no deeper than that and costs no more than its square."""
    from ..query.parse import MOST_QUERIES
    qs = [x for x in v if isinstance(x, dict)][:MOST_QUERIES] if isinstance(v, list) else []
    by = {str(x["id"]): x for x in qs if x.get("id") is not None}
    asked: dict[str, dict] = {}

    def plain(x):
        return {k: w for k, w in x.items() if k not in ("id", "label", "hidden")} if isinstance(x, dict) else x

    def named(r) -> bool:
        return isinstance(r, str | int) and not isinstance(r, bool)

    def send(q: dict, path: tuple) -> str:
        rest = plain(q)
        x = rest.get("x")
        if isinstance(x, dict) and named(x.get("query")):
            other = by.get(str(x["query"]))
            rest["x"] = {**x, "query": send(other, (*path, id(other))) if other is not None and id(other) not in path
                         else f"unknown:{x['query']}"}
        elif isinstance(x, dict) and isinstance(x.get("query"), dict):
            rest["x"] = {**x, "query": plain(x["query"])}
        for side in ("input", "output"):
            part = rest.get(side)
            if named(part):
                other = by.get(str(part))
                rest[side] = plain(other) if other is not None and id(other) not in path else {"source": f"unknown:{part}"}
            elif isinstance(part, dict):
                rest[side] = plain(part)
        shape = json.dumps(rest, default=str)
        if shape not in asked:
            asked[shape] = {**rest, "id": f"q{len(asked)}"}
        return asked[shape]["id"]
    wanted = [(str(n if q.get("id") is None else q["id"]), send(q, (id(q),))) for n, q in enumerate(qs)]
    return list(asked.values()), wanted


def _queries(c, spec, v, what: str, w) -> bool:
    """A query panel's queries, as the query engine reads them (``query.parse``): each must be asked as written, and
    the kind of item each reads the model's."""
    from ..query.parse import MOST_QUERIES, BadQuery, Refused, parse
    if not isinstance(v, list) or not 1 <= len(v) <= MOST_QUERIES:
        c.err(f"{what}.queries: a list of 1 to {MOST_QUERIES} queries", w, "bad-dashboard")
        return False
    flat, wanted = sent(v)
    try:
        got = parse({"queries": flat}).queries
    except BadQuery as e:
        c.err(f"{what}.queries: {e}", w, "bad-dashboard")
        return False
    ok = True
    for q in got:
        if isinstance(q, Refused):
            whose = ", ".join(mine for mine, went in wanted if went == q.id) or q.id
            c.err(f"{what}.queries: {whose}: {q.error}", w, "bad-dashboard")
            ok = False
    for x in v:
        k = x.get("kind") if isinstance(x, dict) else None
        if k is not None and k not in spec.items:
            c.err(f"{what}.queries: {k!r} is not a kind of item" + c.suggest(str(k), spec.items), w, "unknown-ref",
                  f"items.{k}")
            ok = False
    return ok


def _words(c, m, keys: tuple, what: str) -> None:
    for k in keys:
        if m.get(k) is not None and not isinstance(m[k], str):
            c.err(f"{what}.{k}: text", m.at(k) if isinstance(m, Map) else None, "bad-dashboard")


def _refs(c, spec, exists, k: str, v, params: dict, what: str, w) -> bool:
    """Whether every name in ``v`` is the model's: a missing one is ``unknown-ref`` at its line."""
    def bad(msg: str, about: str) -> bool:
        c.err(f"{what}.{k}: {msg}", w, "unknown-ref", about)
        return False
    ok = True
    if k == "refs":
        for raw in v:
            r = c.ref(raw, w, f"{what}.refs", ("stock", "flow", "auxiliary"))
            if r is None:
                ok = False
            elif (why := exists(r)) is not None:
                ok = bad(why, str(r))
    elif k in ("goal", "goals"):
        for g in [v] if k == "goal" else v:
            if g not in spec.goals:
                ok = bad(f"{g!r} is not a goal" + c.suggest(g, spec.goals), str(Ref("goal", g)))
    elif k in ("kind", "kinds"):
        for n in [v] if k == "kind" else v:
            if n not in spec.items:
                ok = bad(f"{n!r} is not a kind of item" + c.suggest(n, spec.items), f"items.{n}")
    elif k == "system" and v not in spec.systems and v not in {x.system for t in (spec.stocks, spec.flows, spec.goals,
                                                                                    spec.blocks) for x in t.values()}:
        ok = bad(f"{v!r} is not a system" + c.suggest(v, spec.systems), f"system.{v}")
    elif k == "state":
        kind = spec.items.get(params.get("kind") or "")
        for s in v:
            if kind is not None and s not in kind.states:
                ok = bad(f"{kind.name} has no state {s!r} (its states: {', '.join(kind.states) or 'none'})" +
                         c.suggest(s, kind.states), f"items.{kind.name}")
    return ok


def query(params: dict) -> dict:
    """A panel's parameters as its endpoint's query (each a list of strings, as ``parse_qs`` gives them)."""
    q: dict = {}
    for k, v in params.items():
        if isinstance(v, bool):
            if v:
                q[k] = ["1"]
        elif k == "where":
            q[k] = [v] if isinstance(v, str) else [str(x) for x in v]
        elif isinstance(v, list):
            q[k] = [",".join(str(x) for x in v)]
        else:
            q[k] = [str(v)]
    return q


def plain_panel(p: Panel) -> dict:
    return {"panel": p.panel, "title": p.title, "size": p.size, "note": p.note, **p.params}


def plain(d: Dashboard) -> dict:
    """A dashboard as the API and the snapshot carry it: what was declared, in the declaration's own words."""
    return {"name": d.name, "title": d.title, "description": d.description, "window": d.window, "system": d.system,
            "declared": True, "panels": [plain_panel(p) for p in d.panels]}
