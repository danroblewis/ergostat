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
DASHBOARD_KEYS = {"title", "description", "window", "panels", "nav", "page"}
# the server's own first parts of a path: nothing of the model's is drawn at them (every other path is the page's)
RESERVED = ("api", "static", "remote")
# ergostat's own pages, each a dashboard drawn at its name until the model's own dashboard or kind of that name takes
# the address (web/ui/src/lib/routes.ts): a kind of item is at /KIND, and its items at /KIND/ID
BUILTIN = ("diagram", "dashboard", "goals", "agents", "agent", "record", "item")
# the pages of one thing a dashboard may be drawn for (``page:``) → the address's word it binds: a panel's parameter
# written ``$WORD`` (``agent: $agent``) takes it from the address (/agent/NAME, /KIND/ID, /KIND). A dashboard named
# as a kind is that kind's page and binds ``$kind`` too
PAGES = {"agent": "agent", "item": "item", "kind": "kind"}
PANEL_KEYS = {"panel", "title", "size", "note", "fit", "quiet"}   # fit: as tall as what it shows (a page made of panels);
#                                                  quiet: not drawn while it has nothing to say (an item's part, quiet systems)
ITEM_SET = {"kind", "state", "where", "moved", "moved_since", "moved_until", "through", "followed", "search", "n"}
# each kind of panel → the parameters it takes (those of its endpoint, by the same names)
KINDS = {
    "note": {"text"},
    "goals": {"goals", "columns"},                        # the loops rows (GET /api/loops), these goals or all; columns
    "chart": {"refs", "points", "replay", "fan"},         # GET /api/series
    "items": ITEM_SET,                                    # GET /api/items
    "states": {"kind", "points"},                         # GET /api/items-flow
    "cycle-time": {"kind", "points"},                     # GET /api/items-flow
    "scope": {"goal", "points"},                          # GET /api/loop-scope
    "items-graph": {"kinds", "system"},                   # GET /api/items-graph
    "timeline": {"kinds", "system"},                      # GET /api/items-graph
    "query": {"form", "queries", "display", "layout"},   # the page's own panel, as a kept draft holds it (GET /api/query)
    "diagram": {"address"},                               # a Diagram address, drawn by the page (it asks GET /api/graph)
}
# ---- the agents group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/agents.tsx): KIND → its parameters
KINDS.update({
    "ladder": set(),                                      # GET /api/agents: how many on each rung, and the exceptions
    "agents": set(),                                      # GET /api/agents: every agent by rung, what its runs cost
    "daemons": set(),                                     # GET /api/daemons
    "agent-what": {"agent"},                              # GET /api/agents/AGENT (and its files): what it is, by rung
    "agent-definition": {"agent"},                        # GET /api/agents/AGENT: its block as written
    "agent-place": {"agent"},                             # GET /api/agents/AGENT: its place in the model
    "agent-runs": {"agent"},                              # GET /api/agents/AGENT: its runs' tally, cost, recent runs
    "agent-log": {"agent"},                               # GET /api/agents/AGENT: the end of its log
})
NEEDS_AGENTS: dict[str, str] = {k: "agent" for k in ("agent-what", "agent-definition", "agent-place", "agent-runs",
                                                     "agent-log")}      # KIND → the parameter it cannot do without

# ---- the items group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/items.tsx): KIND → its parameters
_ITEM = {"item"}                      # one item, by its id (any id: it need not be recorded yet)
_ONE_ITEM = ("item-summary", "item-why", "item-path", "item-relations", "item-fields", "item-refused", "item-moves",
             "item-events", "item-changes")
KINDS.update({
    "kinds": {"states"},                                  # GET /api/items-overview: each system's kinds, a card each
    "items-by-kind": {"q", "finished", "per_kind"},       # GET /api/items: each kind's newest, under its system
    "kind-now": {"kind", "points", "states"},             # GET /api/items-flow (and /api/kinds/KIND): its states
    "kind-model": {"kind"},                               # GET /api/kinds/KIND: what counts it, its goals and loops
    "kind-definition": {"kind"},                          # GET /api/kinds/KIND: its definition
    "item-list": {"kind", "state", "q", "sort", "finished", "n"},   # GET /api/items: one kind's, paged, searched, sorted
    **{k: _ITEM for k in _ONE_ITEM},                      # GET /api/items/ITEM (item-why: GET /api/why?item=ITEM)
    "item-changes": _ITEM | {"history"},                  # GET /api/items/ITEM?history=FIELD|all: each field's changes
})
NEEDS_ITEMS: dict[str, str] = {"kind-now": "kind", "kind-model": "kind", "kind-definition": "kind", "item-list": "kind",
                               **{k: "item" for k in _ONE_ITEM}}


def _one_of(*words):
    return lambda v: None if v in words else f"one of {', '.join(words)}"


def _text(v):
    return None if isinstance(v, str) and v.strip() else "text"


def _whole(low: int, top: int):
    return lambda v: None if not isinstance(v, bool) and isinstance(v, int) and low <= v <= top else \
        f"a whole number from {low} to {top}"


# KIND → {parameter: its check, None or what it must be}: read before the shared checks (which then check its names)
CHECKS_ITEMS = {
    "kinds": {"states": _one_of("all", "groups")},
    "items-by-kind": {"q": _text, "finished": _one_of("hide", "waits", "show"), "per_kind": _whole(1, 500)},
    "kind-now": {"states": _one_of("all", "groups")},
    "item-list": {"state": _text, "q": _text, "sort": _text, "finished": _one_of("hide", "waits", "show")},
    **{k: {"item": _text} for k in _ONE_ITEM},
    "item-changes": {"item": _text, "history": _text},
}

# ---- the record group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/record.tsx): KIND → its parameters
KINDS.update({
    # GET /api/events: the record's events, newest first (the Record page's own); remote: a remote's, read there
    "events": {"match", "item", "about", "machine", "runs", "window", "from", "to", "n", "remote"},
    "goal-crossings": {"goal"},                           # GET /api/loops/{goal}: its crossings in the window
    "goal-decisions": {"goal"},                           # GET /api/loops/{goal}: its controller's decisions, alike
})
NEEDS_RECORD: dict[str, str] = {"goal-crossings": "goal", "goal-decisions": "goal"}   # KIND → the parameter it cannot do without


def _check_record(c, spec, kind: str, x, at, what: str) -> bool:
    """An events panel's own parameters: text, a flag, a time; ``about`` a goal and ``remote`` a remote of the model's
    (each wrong one an error at its line). ``n`` is checked with every kind's."""
    if kind != "events":
        return True
    ok = True
    remotes = getattr(spec, "remotes", None) or {}
    for k in sorted(KINDS["events"] & set(x)):
        v, w = x[k], at(k)
        if k in ("match", "item", "about", "machine", "remote") and (not isinstance(v, str) or not v.strip()):
            c.err(f"{what}.{k}: text", w, "bad-dashboard")
        elif k in ("runs", "window") and not isinstance(v, bool):
            c.err(f"{what}.{k}: true or false", w, "bad-dashboard")
        elif k in ("from", "to") and (isinstance(v, bool) or not isinstance(v, int | float) or not 0 <= v < 1e11):
            c.err(f"{what}.{k}: a time, in seconds since 1970", w, "bad-dashboard")
        elif k == "about" and v not in spec.goals:
            c.err(f"{what}.about: {v!r} is not a goal" + c.suggest(v, spec.goals), w, "unknown-ref", str(Ref("goal", v)))
        elif k == "remote" and v not in remotes:
            c.err(f"{what}.remote: {v!r} is not one of the model's remotes" + c.suggest(v, remotes), w, "unknown-ref",
                  f"remote.{v}")
        else:
            continue
        ok = False
    if ok and isinstance(x.get("from"), int | float) and isinstance(x.get("to"), int | float) and x["from"] > x["to"]:
        c.err(f"{what}.to: before from", at("to"), "bad-dashboard")
        ok = False
    return ok

# ---- the attention group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/attention.tsx): KIND → its parameters
KINDS.update({
    "attention": {"show"},                                # GET /api/status (its attention), these parts or all
    "legend": {"view"},                                   # drawn by the page: how to read that view's drawing
    "feedback-loops": {"system"},                         # GET /api/graph?view=dynamics: its feedback loops
    "control-loops": {"system"},                          # GET /api/graph?view=blocks: its control loops
    "quiet-systems": set(),                               # GET /api/systems: each quiet system's sentence
    "goal-runbook": {"goal"},                             # GET /api/loops/GOAL: runbook, remedy, numbers
    "goal-parts": {"goal"},                               # GET /api/loops/GOAL: its parts along the loop
    "goal-control": {"goal"},                             # GET /api/loop-control: its control loop, and proposals
})
NEEDS_ATTENTION: dict[str, str] = {"legend": "view", "goal-runbook": "goal", "goal-parts": "goal",
                                   "goal-control": "goal"}
CHOICES_ATTENTION = {"view": ("dynamics", "blocks", "process"),             # a parameter → the words it may be
                     "show": ("waiting", "off", "housekeeping", "suggestions")}
LISTS_ATTENTION = {"show"}

NEEDS = {"query": "queries", "diagram": "address", "chart": "refs", "states": "kind", "cycle-time": "kind", "scope": "goal", "items": "kind", "note": "text"}
NEEDS.update({**NEEDS_AGENTS, **NEEDS_ITEMS, **NEEDS_RECORD, **NEEDS_ATTENTION})
CHECKS = {**CHECKS_ITEMS}      # KIND → {parameter: its check}: a group's kinds' own parameters
TEXTS = {"text", "address", "moved", "moved_since", "moved_until", "through", "followed", "search"}
LISTS = {"refs", "goals", "kinds", "state", "where"}     # a list, or one string (comma-separated as the address writes it)
LISTS |= LISTS_ATTENTION | {"columns"}
# a goals panel's columns (web/ui/src/components/GoalsTable.tsx ALL_COLUMNS), or all of them
GOAL_COLUMNS = ("goal", "status", "measure", "value", "bound", "far", "timeOff", "backIn", "spark", "performance", "acted",
                "card", "all")
CHOICES: dict[str, tuple] = {**CHOICES_ATTENTION, "columns": GOAL_COLUMNS}   # a parameter whose every word is one of these


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
        if full in RESERVED:
            doc.problems.append(Problem("error", f"dashboard {full}: /{full} is the server's own address; name this one "
                                        "otherwise", w, "bad-name"))
            continue
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
        nav = _nav(c, m, what)
        page = m.get("page")
        if isinstance(page, str) and page in BUILTIN and page not in PAGES:
            c.err(f"{what}.page: {page} is drawn by the dashboard named {page}: name this one {page} to draw it at "
                  f"/{page}", m.at("page"), "bad-dashboard")
            page = None
        elif page is not None and (not isinstance(page, str) or page not in PAGES):
            c.err(f"{what}.page: one of {', '.join(PAGES)} (every agent's, item's or kind's page)", m.at("page"),
                  "bad-dashboard")
            page = None
        elif page is not None and nav is not None:
            c.err(f"{what}.nav: a dashboard in place of a page is reached by that page's own link", m.at("nav"),
                  "bad-dashboard")
            nav = None
        binds = PAGES.get(page or "")                    # its panels read as that page's, though the page is taken
        if binds is None and name in spec.items:          # named as a kind: that kind's page, its $kind the kind
            binds = "kind"
        if page is not None and (other := next((x for x in spec.dashboards.values() if x.page == page), None)):
            c.err(f"{what}.page: the {page} page is drawn by dashboard {other.name} already", m.at("page"),
                  "defined-twice", f"dashboard.{other.name}")
            page = None
        panels = m.get("panels")
        if not isinstance(panels, list) or not panels:
            c.err(f"{what}.panels: a list of panels, each {{panel: KIND, ...}}", m.at("panels"), "bad-dashboard")
            panels = []
        if len(panels) > MOST:
            c.err(f"{what}.panels: {len(panels)} panels; at most {MOST}", m.at("panels"), "bad-dashboard")
            panels = []
        d = Dashboard(name, str(m.get("title") or ""), str(m.get("description") or ""), window, system=system, where=w,
                      nav=nav, page=page)
        for i, x in enumerate(panels):
            got = _panel(c, spec, exists, x, f"{what}.panels[{i}]", m.at("panels"), binds)
            if got is not None:
                d.panels.append(got)
        spec.dashboards[name] = d


def routes(c, spec) -> None:
    """Each kind of item is at /KIND: a kind named as the server's own address has no page, and one named as one of
    ergostat's own pages takes its address (ergostat's at ?builtin=1). Findings, never errors: the model runs."""
    for name, k in spec.items.items():
        w = getattr(k, "where", None)
        if name in RESERVED:
            c.problems.append(Problem("finding", f"kind {name}: /{name} is the server's own address, so its items have "
                                      "no page; rename it to have one", w, "unrouted-kind", f"items.{name}"))
        elif name in BUILTIN and name not in spec.dashboards:
            c.problems.append(Problem("finding", f"kind {name} is at /{name}, in place of ergostat's own {name} page "
                                      f"(still at /{name}?builtin=1)", w, "kind-takes-page", f"items.{name}"))


def _nav(c, m, what: str) -> str | None:
    """``nav:``: true (its title, else its name, in the page's navigation) or the words of its link; None: not there."""
    v = m.get("nav")
    if v is None or v is False:
        return None
    if v is True:
        return ""
    if isinstance(v, str) and v.strip() and len(v) <= 40:
        return v.strip()
    c.err(f"{what}.nav: true, or its link's words (at most 40 characters)", m.at("nav"), "bad-dashboard")
    return None


def _panel(c, spec, exists, x, what: str, near, binds: str | None = None) -> Panel | None:
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
    for flag in ("fit", "quiet"):
        if flag not in x:
            continue
        if not isinstance(x[flag], bool):
            c.err(f"{what}.{flag}: true or false", at(flag), "bad-dashboard")
            ok = False
        elif x[flag]:
            params[flag] = True
    for k in sorted(KINDS[kind] & set(x)):
        v, w = x[k], at(k)
        if isinstance(v, str) and v.startswith("$"):      # taken from the page's address (page:)
            if binds is None or v != f"${binds}" or k != binds:
                c.err(f"{what}.{k}: {v!r} is taken from no address" + (f" (this page's is ${binds}, as {binds}: ${binds})"
                      if binds else " (only a dashboard in place of the agent, item or kind page takes one)"), w,
                      "bad-dashboard")
                ok = False
            else:
                params[k] = v
            continue
        if (own := CHECKS.get(kind, {}).get(k)) is not None and (why := own(v)) is not None:
            c.err(f"{what}.{k}: {why}", w, "bad-dashboard")
            ok = False
            continue
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
        elif k in TEXTS or k in ("kind", "goal", "system", "agent"):
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
        elif k in CHOICES and not isinstance(v, str):
            c.err(f"{what}.{k}: one of {', '.join(CHOICES[k])}", w, "bad-dashboard")
            ok = False
            continue
        if k in CHOICES and (wrong := [x for x in ([v] if isinstance(v, str) else v) if x not in CHOICES[k]]):
            c.err(f"{what}.{k}: {wrong[0]!r} is not one of {', '.join(CHOICES[k])}", w, "bad-dashboard")
            ok = False
            continue
        params.setdefault(k, v)
        ok = _refs(c, spec, exists, k, v, params, what, w) and ok
    if ok and kind == "diagram" and not str(params.get("address", "")).startswith("/diagram"):
        c.err(f"{what}.address: a Diagram address, like /diagram?view=blocks&system=NAME", at("address"), "bad-dashboard")
        ok = False
    if ok and kind == "items" and not any(str(v).startswith("$") for v in params.values()):
        from .item_sets import BadSet, parse
        try:
            parse(query(params))
        except BadSet as e:
            c.err(f"{what}: {e}", at("panel"), "bad-dashboard")
            ok = False
    ok = _check_record(c, spec, kind, x, at, what) and ok
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
    elif k == "agent" and v not in spec.blocks:          # the model's agents are its blocks
        ok = bad(f"{v!r} is not an agent" + c.suggest(v, spec.blocks), f"block.{v}")
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
            "nav": d.nav, "page": d.page, "declared": True, "panels": [plain_panel(p) for p in d.panels]}


def bound(p: Panel, address: dict) -> Panel:
    """A panel with each ``$WORD`` parameter taken from the page's address (``address``: WORD → its value); one the
    address does not give is left as written (its endpoint says it is not there)."""
    if not any(isinstance(v, str) and v.startswith("$") for v in p.params.values()):
        return p
    params = {k: (address.get(v[1:]) or v) if isinstance(v, str) and v.startswith("$") else v for k, v in p.params.items()}
    return Panel(p.panel, p.title, p.size, p.note, params, p.where)
