"""The page's addresses, from what each system contains (SPEC §4f, *Addresses*; docs/roadmap/systems-and-projections.md).

``/api`` and ``/static`` are the server's (the remote API is under ``/api/remote/``). Every other address is read one
segment at a time from the top level (the scope ``TOP``, ""). In a scope a name goes to the first of (the fixed order):

1. a dashboard the model writes in that system (``dashboards:`` in a file whose ``defaults: system:`` is it; at the top
   level, one in a file that names no system), by its own name (``factory.review`` is ``review`` in ``factory``). One
   named as a default replaces that default there; one named as a projection the scope contains is that projection's
   list dashboard there, the projection's items still under it (neither is a shadowing);
2. a default dashboard: ``overview``, ``diagrams``, ``goals``, ``agents``, ``events``. ``goals/NAME`` and
   ``agents/NAME`` are a goal's and an agent's show dashboards, for a goal or agent the scope contains;
3. a subsystem: what follows is read in it;
4. a projection the scope contains (scope.py: defined or ancillary there): ``NAME`` its list, ``NAME/REST`` one of its
   items, REST what its id glob's ``*`` matched (``factory/intake/ticket/1234`` at ``.../ticket/1234``; a glob that is
   not PREFIX* writes the whole id). Between two of one rank (two projections, or two goals under ``goals/``), the one
   defined in that scope, then the first in the model's order.

At the top level ``api`` and ``static`` go to the server before all of these.

**Names.** A thing is named in a scope by its own name, except a part a remote or a template's instance made
(``spec.belongs``: its system and its short name), which inside that system (it, or a system within it) is named by
its short name: the remote ``incidents``'s ``ticket`` projection, ``incidents-ticket`` model-wide, is
``/incidents/ticket``, its subsystem ``incidents-triage`` is ``/incidents/triage``, its goal ``incidents-full``
``/incidents/goals/full``; outside it, the full name.

**Shadowed.** A thing that loses its name at a scope is not addressed there (a finding, ``address-shadowed``, naming
both things and the scope). A thing is *at* the scopes that contain it where it holds its name.

**The top-most address.** A projection, item, goal or agent may be at several scopes. Its address read in a scope
redirects to the highest scope on that scope's own chain (it and the systems it is within, up to the top level) that
it is at, when that is higher: ``/factory/intake/ticket/1234`` redirects to ``/factory/ticket/1234`` once a flow makes
``ticket`` cross into ``factory``, and to ``/ticket/1234`` once it is at the top level; a scope where its name is taken
is skipped. Its canonical address (``href``) is the same rule read from the system it is defined in; one not at any
scope on that chain (ergostat's own, or shadowed on its whole chain) is at the highest scope it is at, the first of
them in the model's order on a tie. Never sideways from a scope: an agent carried from ``intake`` into its sibling
``qa`` (and not into ``factory``) is at both, and neither redirects. A dashboard is only where it is written; a system
only under its parent (scope.py does not compute systems as things that cross: an open question).

**Errors.** A thing some scope contains that is at none (shadowed everywhere it is: a top-level system or projection
named ``api`` or ``static``, a subsystem named as a default dashboard or as a dashboard its parent writes, a projection
whose name is taken in every scope that contains it) has no address: an error (``address-unreachable``), and the model
does not load. Nothing else is: two things never share an address, since each name in a scope goes to one of them.

The table is plain JSON, served at GET /api/route-table; the page reads it with the same rules
(web/ui/src/lib/systemRoutes.ts), both checked against tests/fixtures/route_cases.json.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

from .scope import TOP, scope

RESERVED = ("api", "static")
DEFAULTS = ("overview", "diagrams", "goals", "agents", "events")
SHOWS = {"goals": "goal", "agents": "agent"}        # a default dashboard whose next segment names one thing
RANK = {"server": 0, "dashboard": 1, "default": 2, "system": 3, "projection": 4}


def table(spec) -> dict:
    """The route table: ``{"reserved", "defaults", "scopes": {SCOPE: {"within", "name", "path", "segments": {SEGMENT:
    {"kind": "dashboard" | "projection" | "system", "name", ("default": True | "projection": NAME)}}, "goals" and
    "agents": {SEGMENT: NAME}}}, "projections": {NAME: {"id", "defined_in", "in": [SCOPE, ...], "at": {SCOPE:
    SEGMENT}}}, "goals" and "agents": {NAME: {"defined_in", "in", "at"}}, "dashboards": {NAME: SCOPE}, "shadowed":
    [...], "unaddressed": [...]}``. ``in`` lists the scopes that contain it, in the model's order, ``at`` those where
    it holds its name (and the name); ``defined_in`` is None for ergostat's own. A scope's ``name`` is its segment
    under its parent."""
    sc = scope(spec) if spec is not None else {TOP: {"within": None, "systems": [], "contains": {}}}
    belongs = (getattr(spec, "belongs", None) or {}) if spec is not None else {}
    out: dict = {"reserved": list(RESERVED), "defaults": list(DEFAULTS), "scopes": {}, "projections": {}, "goals": {},
                 "agents": {}, "dashboards": {}, "shadowed": [], "unaddressed": []}
    chains = {s: _sc_chain(sc, s) for s in sc}

    def named(keys, name: str, s: str) -> str:
        """Its name in scope ``s``: its short name inside the system that made it, else its own."""
        for k in keys:
            b = belongs.get(k)
            if b is not None and b.system in chains.get(s, ()):
                return b.short
        return name

    for name, got in sc.items():
        seg = "" if name == TOP else named([f"system.{name}"], name, got["within"] if got["within"] is not None else TOP)
        out["scopes"][name] = {"within": got["within"], "name": seg, "path": "", "segments": {}, "goals": {},
                               "agents": {}}
    for name in sc:
        out["scopes"][name]["path"] = _path(out["scopes"], name)

    keys: dict[tuple[str, str], list[str]] = {}     # (plural, name) → its belongs keys
    defined: dict[tuple[str, str], set] = {}
    for plural, into, one in (("projections", "projections", "projection"), ("goals", "goals", "goal"),
                              ("agents", "agents", "agent"), ("blocks", "agents", "block")):
        for name, got in sc.items():                # a block is the page's agent too (/api/agents/NAME: its runs)
            for row in got["contains"].get(plural, []):
                thing = out[into].setdefault(row["name"], {"defined_in": row["defined_in"], "in": [], "at": {}})
                if name not in thing["in"]:
                    thing["in"].append(name)
                keys.setdefault((into, row["name"]), []).append(f"{one}.{row['name']}")
                if row["status"] == "defined":
                    defined.setdefault((into, row["name"]), set()).add(name)
    for into in ("projections", "goals", "agents"):         # each scope's list in the model's scope order
        for name, thing in out[into].items():
            thing["in"].sort(key=list(sc).index)
    for name, thing in out["projections"].items():
        k = spec.items.get(name)
        thing["id"] = k.id if k is not None else f"{name}/*"
        thing["open"] = bool(k is not None and k.open)      # its items not told by its id glob: their ids whole

    dashboards: dict[str, list] = {s: [] for s in sc}
    for full, d in (spec.dashboards.items() if spec is not None else ()):
        system = d.system or TOP
        if d.page or system not in sc:
            continue
        local = full[len(d.system) + 1:] if d.system and full.startswith(d.system + ".") else full
        out["dashboards"][full] = system
        dashboards[system].append((local, full, d))

    lost: list[tuple[str, str, dict, dict]] = []    # (scope, segment, kept, lost)
    for s, got in sc.items():
        here = out["scopes"][s]
        claims: dict[str, list[dict]] = {}

        def claim(seg: str, entry: dict) -> None:
            claims.setdefault(seg, []).append(entry)

        if s == TOP:
            for r in RESERVED:
                claim(r, {"kind": "server", "name": r})
        for local, full, _ in dashboards[s]:
            claim(local, {"kind": "dashboard", "name": full})
        for d in DEFAULTS:
            claim(d, {"kind": "dashboard", "name": d, "default": True})
        for child in got["systems"]:
            claim(out["scopes"][child]["name"], {"kind": "system", "name": child})
        rows = got["contains"].get("projections", [])
        for row in sorted(rows, key=lambda r: r["status"] != "defined"):
            n = row["name"]
            claim(named(keys[("projections", n)], n, s), {"kind": "projection", "name": n})
        for seg, said in claims.items():
            said.sort(key=lambda e: RANK["default" if e.get("default") else e["kind"]])     # (stable: model order)
            kept, rest = dict(said[0]), said[1:]
            if kept["kind"] == "dashboard" and not kept.get("default"):
                rest = [e for e in rest if not e.get("default")]            # a model's dashboard replaces a default
                p = next((e for e in rest if e["kind"] == "projection"), None)
                if p is not None:                       # and is a projection's list dashboard there
                    kept["projection"] = p["name"]
                    out["projections"][p["name"]]["at"][s] = seg
                    rest = [e for e in rest if e is not p]
            for e in rest:
                lost.append((s, seg, kept, e))
            if kept["kind"] == "projection":
                out["projections"][kept["name"]]["at"][s] = seg
            if kept["kind"] != "server":
                here["segments"][seg] = kept
        for into in ("goals", "agents"):            # goals/NAME, agents/NAME: their own names, one each
            mine: dict[str, list[str]] = {}
            for n, thing in out[into].items():
                if s in thing["in"]:
                    mine.setdefault(named(keys[(into, n)], n, s), []).append(n)
            for seg, ns in mine.items():
                ns.sort(key=lambda n: s not in defined.get((into, n), ()))
                here[into][seg] = ns[0]
                out[into][ns[0]]["at"][s] = seg
                for n in ns[1:]:
                    lost.append((s, f"{into}/{seg}", {"kind": into[:-1], "name": ns[0]}, {"kind": into[:-1], "name": n}))
    for into in ("projections", "goals", "agents"):         # each thing's scopes in the model's scope order
        for thing in out[into].values():
            thing["at"] = {x: thing["at"][x] for x in sorted(thing["at"], key=list(sc).index)}

    reached = {s for s in sc if s == TOP or out["scopes"][s]["name"] in
               out["scopes"][sc[s]["within"]]["segments"] and
               out["scopes"][sc[s]["within"]]["segments"][out["scopes"][s]["name"]] == {"kind": "system", "name": s}}
    for s, seg, kept, e in lost:
        where = _where(s)
        at = f"{out['scopes'][s]['path'].rstrip('/')}/{seg}"
        if e["kind"] == "system":
            elsewhere = None
        elif e["kind"] in ("projection", "goal", "agent"):
            elsewhere = href(out, {"kind": e["kind"], "name": e["name"]})
        else:
            elsewhere = None
        out["shadowed"].append({
            "scope": s, "segment": seg, "kept": {"kind": kept["kind"], "name": kept["name"]},
            "lost": {"kind": e["kind"], "name": e["name"]}, "at": elsewhere,
            "message": f"{at} is {_said(kept)}" + ("" if kept["kind"] == "server" else f" in {where}")
                       + f", so {_said(e)} is not addressed there"
                       + (f"; it is at {elsewhere}" if elsewhere else "")})
    for s in sc:
        if s not in reached:
            parent = sc[s]["within"]
            seg = out["scopes"][s]["name"]
            kept = out["scopes"][parent]["segments"].get(seg) or {"kind": "server", "name": seg}
            out["unaddressed"].append({"kind": "system", "name": s, "message": (
                f"system {s} has no address: {out['scopes'][parent]['path'].rstrip('/')}/{seg} is {_said(kept)}"
                + ("" if kept["kind"] == "server" else f" in {_where(parent)}") + "; rename one")})
    for into in ("projections", "goals", "agents"):
        for n, thing in out[into].items():
            if thing["in"] and not thing["at"]:
                takers = [f"{_said(k)} in {_where(s)}" for s, _seg, k, e in lost if e["name"] == n
                          and e["kind"] == ("projection" if into == "projections" else into[:-1])]
                out["unaddressed"].append({"kind": into[:-1] if into != "projections" else "projection", "name": n,
                                           "message": f"{into[:-1] if into != 'projections' else 'projection'} {n} "
                                                      f"has no address: its name is taken by "
                                                      + ("; ".join(takers) or "?") + " (every scope that contains it); "
                                                      "rename one"})
    gone = {(u["kind"], u["name"]) for u in out["unaddressed"]}       # said once, as the error
    out["shadowed"] = [c for c in out["shadowed"] if (c["lost"]["kind"], c["lost"]["name"]) not in gone]
    return out


def _said(e: dict) -> str:
    if e["kind"] == "server":
        return "the server's own"
    if e["kind"] == "dashboard":
        return f"the default dashboard {e['name']}" if e.get("default") else f"dashboard {e['name']}"
    return f"{e['kind']} {e['name']}"


def _where(system) -> str:
    return "ergostat" if system is None else "the top level" if system == TOP else system


def _sc_chain(sc: dict, s: str) -> list[str]:
    out: list[str] = []
    while s is not None and s not in out:
        out.append(s)
        s = sc.get(s, {}).get("within")
    return out


def _path(scopes: dict, system: str) -> str:
    names: list[str] = []
    seen: list[str] = []
    while system not in (TOP, None) and system not in seen:
        seen.append(system)
        names.append(scopes[system]["name"] if system in scopes else system)
        system = scopes.get(system, {}).get("within")
    return "/" + "/".join(quote(n, safe="!*'()") for n in reversed(names))


def shadowed(t: dict) -> list[dict]:
    """Each name a thing lost at a scope: ``{"scope", "segment", "kept", "lost", "at", "message"}``."""
    return list(t["shadowed"])


def problems(spec) -> list:
    """Each shadowing as a finding (``address-shadowed``); each thing with no address as an error
    (``address-unreachable``: the model does not load, and the page shows its errors)."""
    from .load import Problem
    t = table(spec)

    def where_of(kind: str, name: str):
        got = {"projection": spec.items, "dashboard": spec.dashboards, "goal": spec.goals,
               "agent": spec.agents}.get(kind, {}).get(name)
        return getattr(got, "where", None)

    out = []
    for c in t["shadowed"]:
        where = where_of(c["lost"]["kind"], c["lost"]["name"]) or where_of(c["kept"]["kind"], c["kept"]["name"])
        out.append(Problem("finding", f"address shadowed: {c['message']}", where, "address-shadowed",
                           f"{c['scope'] or 'top'}.{c['segment']}"))
    for u in t["unaddressed"]:
        out.append(Problem("error", f"address: {u['message']}", where_of(u["kind"], u["name"]), "address-unreachable",
                           f"{u['kind']}.{u['name']}"))
    return out


# ---- reading an address, writing one

def _chain(t: dict, s: str) -> list[str]:
    """The scope and every scope it is within, innermost first, ending at the top level."""
    out = []
    while s is not None and s not in out:
        out.append(s)
        s = t["scopes"].get(s, {}).get("within")
    return out


def _top(t: dict, thing: dict, s: str | None) -> str | None:
    """The highest scope on ``s``'s chain that the thing is at (None: none is)."""
    if s is None:
        return None
    on = [x for x in _chain(t, s) if x in thing["at"]]
    return on[-1] if on else None


def _canonical(t: dict, thing: dict) -> str | None:
    at = list(thing["at"])
    if not at:
        return None
    if thing["defined_in"] is not None and (got := _top(t, thing, thing["defined_in"])) is not None:
        return got
    return min(at, key=lambda x: (len(_chain(t, x)), at.index(x)))


def _enc(s: str) -> str:
    return quote(s, safe="!*'()")


def _segs(s: str) -> str:
    return "/".join(_enc(x) for x in s.split("/"))


def _glob_re(g: str) -> re.Pattern:
    """fnmatch's glob, as lib/routes.ts reads it: ``*`` anything (a / too), ``?`` one character, ``[...]`` one of
    them."""
    out, i = "", 0
    while i < len(g):
        ch = g[i]
        if ch == "*":
            out += ".*"
        elif ch == "?":
            out += "."
        elif ch == "[" and (j := g.find("]", i + 2)) >= 0:
            body = g[i + 1:j]
            out += "[" + ("^" + body[1:] if body[:1] == "!" else body).replace("\\", "\\\\") + "]"
            i = j
        else:
            out += re.escape(ch)
        i += 1
    return re.compile(f"^{out}$", re.S)


def _prefix(glob: str) -> str | None:
    if not glob.endswith("*"):
        return None
    p = glob[:-1]
    return None if re.search(r"[*?\[]", p) else p


def _prefix_of(thing: dict) -> str | None:
    """What a projection's items' ids start with, left out of their addresses: none of an open one's (keyed by its
    events' data, or read by a query: its items' ids are whole, /instance/ACCOUNT/REGION/ID)."""
    return "" if thing.get("open") else _prefix(thing["id"])


def _at(t: dict, s: str, rest: str = "") -> str:
    base = t["scopes"][s]["path"].rstrip("/")
    return (base + "/" + rest) if rest else (base or "/")


def _addr(t: dict, kind: str, name: str, s: str, id_: str | None = None) -> str:
    seg = t["projections" if kind in ("projection", "item") else kind + "s"][name]["at"].get(s, name)
    if kind == "projection":
        return _at(t, s, _enc(seg))
    if kind == "item":
        p = _prefix_of(t["projections"][name])
        rest = id_[len(p):] if p is not None and id_.startswith(p) else id_
        return _at(t, s, f"{_enc(seg)}/{_segs(rest)}")
    return _at(t, s, f"{'goals' if kind == 'goal' else 'agents'}/{_enc(seg)}")


def resolve(t: dict, path: str) -> dict | None:
    """What an address names: ``{"scope", "kind": "dashboard" | "projection" | "item" | "goal" | "agent" | "system",
    "name", "id"?, "projection"?, "redirect"?}``, or None (nothing there, or the server's own). ``redirect``: the
    top-most address of the same thing, when this one is deeper. A scope's own address (``/``, ``/factory``) is the
    system (``name`` "" for the top level)."""
    path = path.split("?", 1)[0].split("#", 1)[0]
    segs = [unquote(x) for x in path.strip("/").split("/")] if path.strip("/") else []
    if segs and segs[0] in t["reserved"]:
        return None
    s, i = TOP, 0
    while i < len(segs):
        e = t["scopes"][s]["segments"].get(segs[i])
        if e is None:
            return None
        rest = segs[i + 1:]
        if e["kind"] == "system":
            s, i = e["name"], i + 1
            continue
        if e["kind"] == "dashboard":
            if not rest:
                return {"scope": s, "kind": "dashboard", "name": e["name"],
                        **({"projection": e["projection"]} if e.get("projection") else {})}
            if e.get("projection"):
                return _thing(t, s, "item", e["projection"], "/".join(rest))
            if segs[i] in SHOWS and len(rest) == 1 and (e.get("default") or e["name"] == segs[i]
                                                         or e["name"].endswith("." + segs[i])):
                got = t["scopes"][s][segs[i]].get(rest[0])
                return _thing(t, s, SHOWS[segs[i]], got) if got is not None else None
            return None
        if e["kind"] == "projection":
            return _thing(t, s, "item" if rest else "projection", e["name"], "/".join(rest) if rest else None)
        return None
    return {"scope": s, "kind": "system", "name": s}


def _thing(t: dict, s: str, kind: str, name: str, rest: str | None = None) -> dict | None:
    table_ = t["projections" if kind in ("projection", "item") else kind + "s"]
    thing = table_.get(name)
    if thing is None or s not in thing["at"]:
        return None
    out: dict = {"scope": s, "kind": kind, "name": name}
    if kind == "item":
        p = _prefix_of(thing)
        out["id"] = p + rest if p is not None else rest
    top = _top(t, thing, s)
    if top is not None and top != s:
        out["redirect"] = _addr(t, kind, name, top, out.get("id"))
    return out


def projection_of(t: dict, id_: str) -> str | None:
    """The first projection, in the model's order, whose id glob matches the id."""
    return next((n for n, k in t["projections"].items() if _glob_re(k["id"]).match(id_)), None)


def href(t: dict, thing: dict, scope_: str | None = None) -> str | None:
    """A thing's address: ``{"kind": "projection" | "goal" | "agent", "name"}``, ``{"kind": "item", "id",
    "projection"?}`` (the first projection whose glob matches, when not given), ``{"kind": "dashboard", "name"}`` (the
    model's, by its full name, or a default's in ``scope_``) or ``{"kind": "system", "name"}`` ("" the top level).
    Given ``scope_``, a projection, item, goal or agent is at the highest scope on its chain that contains it, else at
    its canonical address. None: nothing has that address."""
    kind, name = thing["kind"], thing.get("name")
    if kind == "system":
        return t["scopes"][name]["path"] if name in t["scopes"] else None
    if kind == "dashboard":
        if name in t["dashboards"]:
            s = t["dashboards"][name]
            local = name.split(".", 1)[1] if s and name.startswith(s + ".") else name
            return _at(t, s, _enc(local))
        s = scope_ or TOP
        return _at(t, s, _enc(name)) if name in t["defaults"] and s in t["scopes"] else None
    if kind == "item":
        name = thing.get("projection") or projection_of(t, thing["id"])
        if name is None:
            return None
    got = t["projections" if kind in ("projection", "item") else kind + "s"].get(name)
    if got is None:
        return None
    s = _top(t, got, scope_) if scope_ is not None else None
    s = s if s is not None else _canonical(t, got)
    return None if s is None else _addr(t, kind, name, s, thing.get("id"))


# ---- what the server writes with these: the table kept per version of the model, a system's events, old links

def kept_table(spec) -> dict:
    """``table(spec)``, worked out once per version of the model (kept with its lookups, as scope.py's)."""
    if spec is None:
        return table(None)
    kept = spec.lookups().kept
    key = (id(scope(spec)), id(spec.dashboards), len(spec.dashboards))
    got = kept.get("route-table")
    if got is None or got[0] != key:
        got = kept["route-table"] = (key, table(spec))
    return got[1]


def events_of(spec, system: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What a system's Events shows (SPEC §4f): the item globs of the projections it contains, and its blocks' and
    agents' names (the sources of what they record): ``(globs, sources)``, both empty for a system the model has
    not."""
    got = scope(spec).get(system) if spec is not None else None
    if got is None:
        return (), ()
    t = kept_table(spec)
    globs = tuple(dict.fromkeys(t["projections"][r["name"]]["id"] for r in got["contains"].get("projections", [])
                                if r["name"] in t["projections"]))
    sources = tuple(dict.fromkeys(r["name"] for k in ("blocks", "agents") for r in got["contains"].get(k, [])))
    return globs, sources


def link(spec, path: str | None) -> str | None:
    """A link ergostat writes (an inbox entry's, a why's evidence) at its canonical address: ``/item/ID`` at its
    projection's (``/factory/ticket/12``; one no projection, or several, see stays ``/item/ID``), ``/agent/NAME`` at
    the agent's, ``/diagram?...`` at the Diagrams of the system it names (``system=``), ``/record?...`` at
    ``/events?...``. Anything else is returned as it is."""
    if not path or spec is None or not path.startswith("/"):
        return path
    base, _, q = path.partition("?")
    t = kept_table(spec)
    tail = f"?{q}" if q else ""
    if base.startswith("/item/"):
        id_ = unquote(base[len("/item/"):])
        seen = [n for n, k in t["projections"].items() if _glob_re(k["id"]).match(id_)]
        got = href(t, {"kind": "item", "id": id_, "projection": seen[0]}) if len(seen) == 1 else None
        return got + tail if got else path
    if base.startswith("/agent/"):
        got = href(t, {"kind": "agent", "name": unquote(base[len("/agent/"):])})
        return got + tail if got else path
    if base == "/diagram":
        from urllib.parse import parse_qsl, urlencode
        pairs = parse_qsl(q, keep_blank_values=True)
        system = next((v for k, v in pairs if k == "system"), "")
        rest = urlencode([(k, v) for k, v in pairs if k != "system"], safe="/,*")
        at = href(t, {"kind": "dashboard", "name": "diagrams"}, system if system in t["scopes"] else TOP)
        return (at or "/diagrams") + (f"?{rest}" if rest else "")
    if base == "/record":
        return "/events" + tail
    return path


def relinked(spec, x):
    """An answer with every ``link`` in it (an inbox entry's, a why's evidence) at its canonical address (``link``)."""
    if isinstance(x, dict):
        return {k: link(spec, v) if k == "link" and isinstance(v, str) else relinked(spec, v) for k, v in x.items()}
    if isinstance(x, list):
        return [relinked(spec, v) for v in x]
    return x
