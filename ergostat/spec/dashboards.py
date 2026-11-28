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
DASHBOARD_KEYS = {"title", "description", "window", "panels", "nav", "page", "system"}   # system: the system it is
#                                                  the dashboard of, over its file's defaults: (named SYSTEM.NAME)
# the server's own first parts of a path: nothing of the model's is drawn at them (every other path is the page's)
RESERVED = ("api", "static")
# ergostat's own pages: each system's default dashboards (spec/routes.py DEFAULTS: at /SYSTEM/NAME, and at /NAME for
# the top level), replaced there by the model's dashboard of that name, and an agent's and an item's page
BUILTIN = ("overview", "diagrams", "goals", "agents", "events", "agent", "item")
# the pages of one thing a dashboard may be drawn for (``page:``) → the address's word it binds: a panel's parameter
# written ``$WORD`` (``agent: $agent``) takes it from the address (/agents/NAME, /PROJECTION/ID, /PROJECTION). A
# dashboard named as a projection is that projection's page and binds ``$projection`` too. Every dashboard binds
# ``$system``: the system whose address it is drawn at ("" the top level: everything)
PAGES = {"agent": "agent", "item": "item", "projection": "projection"}
# a projection's own dashboards (``projections: P: dashboards:``), each drawn where the projection is: ``list`` at /P,
# ``show`` for each of its items at /P/REST → the address's words its panels may write ``$WORD`` for
PROJECTION_DASHBOARDS = {"list": ("projection",), "show": ("item", "projection")}
OWN_KEYS = {"title", "description", "window", "panels"}   # a projection's own: drawn at its addresses, so no nav or page
PANEL_KEYS = {"panel", "title", "size", "note", "fit", "quiet"}   # fit: as tall as what it shows (a page made of panels);
#                                                  quiet: not drawn while it has nothing to say (an item's part, quiet systems)
ITEM_SET = {"projection", "state", "where", "moved", "moved_since", "moved_until", "through", "followed", "search", "n"}
# each kind of panel → the parameters it takes (those of its endpoint, by the same names)
KINDS = {
    "note": {"text"},
    "goals": {"goals", "columns", "system"},              # the loops rows (GET /api/loops), these goals or all, or a
    #                                                       system's (spec/scope.py: what it contains); columns
    "chart": {"refs", "points", "replay", "fan", "system"},   # GET /api/series: refs, or a system's stocks and flows
    "items": ITEM_SET,                                    # GET /api/items
    "states": {"projection", "points"},                   # GET /api/items-flow
    "cycle-time": {"projection", "points"},               # GET /api/items-flow
    "scope": {"goal", "points"},                          # GET /api/loop-scope
    "items-graph": {"projections", "system"},             # GET /api/items-graph
    "timeline": {"projections", "system"},                # GET /api/items-graph
    "query": {"form", "queries", "display", "layout"},   # the page's own panel, as a kept draft holds it (GET /api/query)
    "diagram": {"address"},                               # a Diagram address, drawn by the page (it asks GET /api/graph)
}
# ---- the agents group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/agents.tsx): KIND → its parameters
KINDS.update({
    "ladder": {"system"},                                 # GET /api/agents: how many on each rung, and the exceptions
    "agents": {"system"},                                 # GET /api/agents: every agent by rung (a system's), their cost
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
    "projections": {"states", "system"},                  # GET /api/items-overview: each projection, a card each (a
    #                                                       system's: those it contains)
    "items-by-projection": {"q", "finished", "per_projection"},   # GET /api/items: each projection's newest, by system
    "projection-now": {"projection", "points", "states"},  # GET /api/items-flow (and /api/projections/P): its states
    "projection-model": {"projection"},                   # GET /api/projections/P: what counts it, its goals and loops
    "projection-definition": {"projection"},              # GET /api/projections/P: its definition
    "item-list": {"projection", "state", "q", "sort", "finished", "n"},   # GET /api/items: one projection's, paged
    **{k: _ITEM for k in _ONE_ITEM},                      # GET /api/items/ITEM (item-why: GET /api/why?item=ITEM)
    "item-changes": _ITEM | {"history"},                  # GET /api/items/ITEM?history=FIELD|all: each field's changes
    "item-state-timeline": _ITEM,                         # GET /api/items/ITEM: its states over time, a band
    "item-field-chart": _ITEM | {"field"},                # GET /api/items/ITEM?history=all: a numeric field's values
    #                                                       over time (field: that one; else each that changed twice)
    "item-events-histogram": _ITEM,                       # GET /api/items/ITEM: its events per time bucket, by kind
})
NEEDS_ITEMS: dict[str, str] = {"projection-now": "projection", "projection-model": "projection",
                               "projection-definition": "projection", "item-list": "projection",
                               **{k: "item" for k in _ONE_ITEM}, "item-state-timeline": "item",
                               "item-field-chart": "item", "item-events-histogram": "item"}


def _one_of(*words):
    def check(v):
        return None if v in words else f"one of {', '.join(words)}"
    check.words = words                       # what the page's panel editor offers (dashboard_api.kinds)
    return check


def _text(v):
    return None if isinstance(v, str) and v.strip() else "text"


def _whole(low: int, top: int):
    return lambda v: None if not isinstance(v, bool) and isinstance(v, int) and low <= v <= top else \
        f"a whole number from {low} to {top}"


# KIND → {parameter: its check, None or what it must be}: read before the shared checks (which then check its names)
CHECKS_ITEMS = {
    "projections": {"states": _one_of("all", "groups")},
    "items-by-projection": {"q": _text, "finished": _one_of("hide", "waits", "show"), "per_projection": _whole(1, 500)},
    "projection-now": {"states": _one_of("all", "groups")},
    "item-list": {"state": _text, "q": _text, "sort": _text, "finished": _one_of("hide", "waits", "show")},
    **{k: {"item": _text} for k in _ONE_ITEM},
    "item-changes": {"item": _text, "history": _text},
    "item-state-timeline": {"item": _text},
    "item-field-chart": {"item": _text, "field": _text},
    "item-events-histogram": {"item": _text},
}

# ---- the record group's kinds of panel (ergostat/web/ui/src/components/panels/kinds/record.tsx): KIND → its parameters
KINDS.update({
    # GET /api/events: the record's events, newest first (the Record page's own); remote: a remote's, read there
    "events": {"match", "item", "about", "machine", "runs", "window", "from", "to", "n", "remote", "system"},
    #   system: the events behind what that system contains (its projections' items, its blocks' and agents' own)
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
    "attention": {"show", "system"},                      # GET /api/status (its attention), these parts or all; a
    #                                                       system's: what is about a part it contains
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

NEEDS = {"query": "queries", "diagram": "address", "chart": "refs",   # (a chart: refs, or system) "states": "projection", "cycle-time": "projection", "scope": "goal",
         "items": "projection", "note": "text"}
NEEDS.update({**NEEDS_AGENTS, **NEEDS_ITEMS, **NEEDS_RECORD, **NEEDS_ATTENTION})
CHECKS = {**CHECKS_ITEMS}      # KIND → {parameter: its check}: a group's kinds' own parameters
TEXTS = {"text", "address", "moved", "moved_since", "moved_until", "through", "followed", "search"}
LISTS = {"refs", "goals", "projections", "state", "where"}     # a list, or one string (comma-separated as the address writes it)
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
    for name, entry in body.items():
        w = body.at(name)
        own = entry.get("system") if isinstance(entry, dict) else None
        if own is not None and (not isinstance(own, str) or not NAME.match(own)):
            doc.problems.append(Problem("error", f"dashboard {name}.system: a system's name", w, "bad-name"))
            continue
        system = own or defaults.get("system")
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
    own check of a reference, as ``show:``'s), those under ``dashboards:`` and each projection's own."""
    for name, (m, w, system) in c.doc.dashboards.items():
        what = f"dashboard {name}"
        if not isinstance(m, dict):
            c.err(f"{what}: a map of its keys (title, description, window, panels)", w, "not-a-map")
            continue
        c.keys(m, DASHBOARD_KEYS, what)
        nav = _nav(c, m, what)
        page = m.get("page")
        if isinstance(page, str) and page in BUILTIN and page not in PAGES:
            c.err(f"{what}.page: {page} is drawn by the dashboard named {page}: name this one {page} to draw it at "
                  f"/{page}", m.at("page"), "bad-dashboard")
            page = None
        elif page is not None and (not isinstance(page, str) or page not in PAGES):
            c.err(f"{what}.page: one of {', '.join(PAGES)} (every agent's, item's or projection's page)", m.at("page"),
                  "bad-dashboard")
            page = None
        elif page is not None and nav is not None:
            c.err(f"{what}.nav: a dashboard in place of a page is reached by that page's own link", m.at("nav"),
                  "bad-dashboard")
            nav = None
        binds = (PAGES[page],) if page in PAGES else ()  # its panels read as that page's, though the page is taken
        if not binds and name.rsplit(".", 1)[-1] in spec.items:   # named as a projection: its page, its $projection it
            binds = ("projection",)
        binds = (*binds, "system")                        # every dashboard: the system it is drawn in
        if page is not None and (other := next((x for x in spec.dashboards.values() if x.page == page), None)):
            c.err(f"{what}.page: the {page} page is drawn by dashboard {other.name} already", m.at("page"),
                  "defined-twice", f"dashboard.{other.name}")
            page = None
        d = _dashboard(c, spec, exists, name, m, w, what, binds)
        d.system, d.nav, d.page = system, nav, page
        spec.dashboards[name] = d
    for name, m in (c.doc.sections.get("projections") or {}).items():
        if name not in spec.items or not isinstance(m, dict) or m.get("dashboards") is None:
            continue
        own = m["dashboards"]
        what = f"projection {name}.dashboards"
        if not isinstance(own, dict):
            c.err(f"{what}: a map of list: (drawn at /{name}) and show: (each of its items)", m.at("dashboards"),
                  "not-a-map")
            continue
        c.keys(own, set(PROJECTION_DASHBOARDS), what)
        for role, binds in PROJECTION_DASHBOARDS.items():
            x = own.get(role)
            if x is None:
                continue
            w, full = own.at(role) if isinstance(own, Map) else m.at("dashboards"), f"{name}.{role}"
            if not isinstance(x, dict):
                c.err(f"{what}.{role}: a map of its keys (title, description, window, panels)", w, "not-a-map")
                continue
            if full in spec.dashboards:
                c.err(f"{what}.{role}: dashboard {full} is defined twice: here and at {spec.dashboards[full].where}", w,
                      "defined-twice", f"dashboard.{full}")
                continue
            c.keys(x, OWN_KEYS, f"{what}.{role}")
            d = _dashboard(c, spec, exists, full, x, w, f"{what}.{role}", (*binds, "system"))
            d.system, d.projection, d.role = spec.items[name].system, name, role
            spec.dashboards[full] = d


def _dashboard(c, spec, exists, name: str, m, w, what: str, binds: tuple) -> Dashboard:
    """One dashboard's words, window and panels, checked (``binds``: the address's words its panels may write
    ``$WORD`` for)."""
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
        c.err(f"{what}.panels: a list of panels, each {{panel: KIND, ...}}", m.at("panels") or w, "bad-dashboard")
        panels = []
    if len(panels) > MOST:
        c.err(f"{what}.panels: {len(panels)} panels; at most {MOST}", m.at("panels"), "bad-dashboard")
        panels = []
    d = Dashboard(name, str(m.get("title") or ""), str(m.get("description") or ""), window, where=w)
    for i, x in enumerate(panels):
        got = _panel(c, spec, exists, x, f"{what}.panels[{i}]", m.at("panels"), binds)
        if got is not None:
            d.panels.append(got)
    return d


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


def _panel(c, spec, exists, x, what: str, near, binds: tuple = ()) -> Panel | None:
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
    if NEEDS.get(kind) and x.get(NEEDS[kind]) is None and not (kind == "chart" and x.get("system") is not None):
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
            if v[1:] not in binds or k != v[1:]:
                c.err(f"{what}.{k}: {v!r} is taken from no address" + (
                      f" (this page's: {', '.join(f'{b}: ${b}' for b in binds)})" if binds else
                      " (only $system, or in place of the agent, item or projection page its word)"), w,
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
        elif k in TEXTS or k in ("projection", "goal", "system", "agent"):
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
    if ok and kind == "diagram" and not (str(params.get("address", "")).split("?")[0].rstrip("/") + "/").endswith(
            ("/diagram/", "/diagrams/")):                 # a system's Diagrams (/SYSTEM/diagrams), or the old /diagram
        c.err(f"{what}.address: a Diagram address, a system's Diagrams, like /diagrams?view=blocks or /SYSTEM/diagrams", at("address"),
              "bad-dashboard")
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
    the projection each reads the model's."""
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
        k = x.get("projection") if isinstance(x, dict) else None
        if k is not None and k not in spec.items:
            c.err(f"{what}.queries: {k!r} is not a projection" + c.suggest(str(k), spec.items), w, "unknown-ref",
                  f"projections.{k}")
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
    elif k in ("projection", "projections"):
        for n in [v] if k == "projection" else v:
            if n not in spec.items:
                ok = bad(f"{n!r} is not a projection" + c.suggest(n, spec.items), f"projections.{n}")
    elif k == "system" and v not in spec.systems and v not in {x.system for t in (spec.stocks, spec.flows, spec.goals,
                                                                                    spec.blocks) for x in t.values()}:
        ok = bad(f"{v!r} is not a system" + c.suggest(v, spec.systems), f"system.{v}")
    elif k == "agent" and v not in spec.blocks:          # the model's agents are its blocks
        ok = bad(f"{v!r} is not an agent" + c.suggest(v, spec.blocks), f"block.{v}")
    elif k == "state":
        kind = spec.items.get(params.get("projection") or "")
        for s in v:
            if kind is not None and s not in kind.states:
                ok = bad(f"{kind.name} has no state {s!r} (its states: {', '.join(kind.states) or 'none'})" +
                         c.suggest(s, kind.states), f"projections.{kind.name}")
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
            "nav": d.nav, "page": d.page, "projection": d.projection, "role": d.role, "declared": True,
            "panels": [plain_panel(p) for p in d.panels]}


def bound(p: Panel, address: dict) -> Panel:
    """A panel with each ``$WORD`` parameter taken from the page's address (``address``: WORD → its value); one the
    address does not give is left as written (its endpoint says it is not there)."""
    if not any(isinstance(v, str) and v.startswith("$") for v in p.params.values()):
        return p
    params = {k: (address[v[1:]] if address.get(v[1:]) is not None else v) if isinstance(v, str) and v.startswith("$")
              else v for k, v in p.params.items()}
    return Panel(p.panel, p.title, p.size, p.note, params, p.where)
