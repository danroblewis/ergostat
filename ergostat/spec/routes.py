"""The page's addresses, from what each system contains (SPEC §4f, *Addresses*; docs/roadmap/systems-and-projections.md).

``/api``, ``/static`` and ``/remote`` are the server's. Every other address is read one segment at a time from the top
level (the scope ``TOP``, ""); in a scope each segment is, in this order:

1. a dashboard the model writes in that system (``dashboards:`` in a file whose ``defaults: system:`` is it; at the top
   level, one in a file that names no system), by its own name (``factory.review`` is ``review`` in ``factory``). One
   named as a default replaces that default there; one named as a projection the scope contains is that projection's
   list dashboard there (dashboards come before projections), the projection's items still under it;
2. a default dashboard: ``overview``, ``diagrams``, ``goals``, ``agents``, ``events``. ``goals/NAME`` and
   ``agents/NAME`` are a goal's and an agent's show dashboards, for a goal or agent the scope contains;
3. a projection the scope contains (scope.py: defined or ancillary there): ``NAME`` its list, ``NAME/REST`` one of its
   items, REST what its id glob's ``*`` matched (``factory/intake/ticket/1234`` at ``.../ticket/1234``; a glob that is
   not PREFIX* writes the whole id);
4. a subsystem, by its own name: what follows is read in it.

A dashboard drawn in place of a page (``page:``) has no address of its own: that page's link reaches it.

**The top-most address.** A projection, item, goal or agent may be at several scopes' addresses: every scope that
contains it. Its address read in a scope redirects to the highest scope on that scope's own chain (it and the systems
it is within, up to the top level) that contains it, when that is higher: ``/factory/intake/ticket/1234`` redirects to
``/factory/ticket/1234`` once a flow makes ``ticket`` cross into ``factory``, and to ``/ticket/1234`` once it is at the
top level. Its canonical address (``href``) is the same rule read from the system it is defined in; one defined
nowhere (ergostat's own) is at the highest scope that contains it, the first of them in the model's order on a tie.
Never sideways: an agent carried from ``intake`` into its sibling ``qa`` (and not into ``factory``) is at both, and
neither redirects. A dashboard is only where it is written; a system only under its parent (scope.py does not compute
systems as things that cross: an open question).

**Collisions.** Two things at one segment of one scope (a subsystem and a dashboard both named ``review`` in
``factory``; a projection named ``events``; a top-level one named ``api``) are a problem of the model (``collisions``,
``problems``), at ``LEVEL``. The design makes them errors (the model does not load, and the page shows the errors);
until these addresses are the page's they are findings, since the project's own model and two examples have one (a
system and a projection of one name, in one scope). The two exceptions above (a model's dashboard over a default, or
over a projection) are not collisions.

The table is plain JSON, served at GET /api/route-table; the page reads it with the same rules
(web/ui/src/lib/systemRoutes.ts), both checked against tests/fixtures/route_cases.json.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

from .scope import TOP, scope

RESERVED = ("api", "static", "remote")
DEFAULTS = ("overview", "diagrams", "goals", "agents", "events")
LEVEL = "finding"       # "error" once the page reads its addresses here (docs/roadmap/systems-and-projections.md, step 5)
SHOWS = {"goals": "goal", "agents": "agent"}        # a default dashboard whose next segment names one thing


def table(spec) -> dict:
    """The route table: ``{"reserved", "defaults", "scopes": {SCOPE: {"within", "path", "segments": {SEGMENT:
    {"kind": "dashboard" | "projection" | "system", "name", ("default": True | "projection": NAME)}}}},
    "projections": {NAME: {"id", "defined_in", "in": [SCOPE, ...]}}, "goals" and "agents": {NAME: {"defined_in",
    "in"}}, "dashboards": {NAME: SCOPE}, "collisions": [...]}``. ``in`` lists the scopes that contain it, in the
    model's order; ``defined_in`` is None for ergostat's own."""
    sc = scope(spec) if spec is not None else {TOP: {"within": None, "systems": [], "contains": {}}}
    out: dict = {"reserved": list(RESERVED), "defaults": list(DEFAULTS), "scopes": {}, "projections": {}, "goals": {},
                 "agents": {}, "dashboards": {}, "collisions": []}
    for name, got in sc.items():
        out["scopes"][name] = {"within": got["within"], "path": _path(sc, name), "segments": {}}
    for plural in ("projections", "goals", "agents"):
        for name, got in sc.items():
            for row in got["contains"].get(plural, []):
                thing = out[plural].setdefault(row["name"], {"defined_in": row["defined_in"], "in": []})
                thing["in"].append(name)
    for name, thing in out["projections"].items():
        k = spec.items.get(name)
        thing["id"] = k.id if k is not None else f"{name}/*"

    dashboards: dict[str, list] = {s: [] for s in sc}
    for full, d in (spec.dashboards.items() if spec is not None else ()):
        system = d.system or TOP
        if d.page or system not in sc:
            continue
        local = full[len(d.system) + 1:] if d.system and full.startswith(d.system + ".") else full
        out["dashboards"][full] = system
        dashboards[system].append((local, full, d))

    for s, got in sc.items():
        claims: dict[str, list[tuple[dict, str]]] = {}

        def claim(seg: str, entry: dict, said: str) -> None:
            claims.setdefault(seg, []).append((entry, said))

        for local, full, _ in dashboards[s]:
            claim(local, {"kind": "dashboard", "name": full}, f"dashboard {full}")
        for d in DEFAULTS:
            claim(d, {"kind": "dashboard", "name": d, "default": True}, f"the default dashboard {d}")
        for row in got["contains"].get("projections", []):
            claim(row["name"], {"kind": "projection", "name": row["name"]},
                  f"projection {row['name']}" + ("" if row["status"] == "defined" else
                                                 f" (ancillary, defined in {_where(row['defined_in'])})"))
        for child in got["systems"]:
            claim(child, {"kind": "system", "name": child}, f"system {child}")
        if s == TOP:
            for r in RESERVED:
                if r in claims:
                    claim(r, {"kind": "server", "name": r}, f"the server's own /{r}")
        segs = out["scopes"][s]["segments"]
        for seg, said in claims.items():
            kept = _merge(said)
            if kept is None:
                things = [w for _, w in said]
                out["collisions"].append({
                    "scope": s, "segment": seg, "things": [{k: e[k] for k in ("kind", "name")} for e, _ in said],
                    "message": f"{out['scopes'][s]['path'].rstrip('/')}/{seg} names {len(said)} things in "
                               f"{_where(s)}: " + " and ".join(things) + "; rename one"})
                kept = said[0][0]
            if kept["kind"] != "server":
                segs[seg] = kept
    return out


def _merge(said: list[tuple[dict, str]]) -> dict | None:
    """The one entry a segment names, or None when it names two things: a model's dashboard over a default (it
    replaces it) or over a projection (that projection's list dashboard there) is not a collision."""
    if len(said) == 1:
        return said[0][0]
    mine = [e for e, _ in said if e["kind"] == "dashboard" and not e.get("default")]
    rest = [e for e, _ in said if e not in mine]
    if len(mine) != 1:
        return None
    projection = None
    for e in rest:
        if e["kind"] == "projection" and projection is None:
            projection = e["name"]
        elif not (e["kind"] == "dashboard" and e.get("default")):
            return None
    return {**mine[0], **({"projection": projection} if projection else {})}


def _where(system) -> str:
    return "ergostat" if system is None else "the top level" if system == TOP else system


def _path(sc: dict, system: str) -> str:
    names: list[str] = []
    while system not in (TOP, None) and system not in names:
        names.append(system)
        system = sc.get(system, {}).get("within")
    return "/" + "/".join(quote(n, safe="!*'()") for n in reversed(names))


def collisions(t: dict) -> list[dict]:
    """Two things at one segment of one scope: each ``{"scope", "segment", "things", "message"}``."""
    return list(t["collisions"])


def problems(spec, level: str = LEVEL) -> list:
    """Each collision as a problem of the model; as an error, the model does not load and the page shows its errors."""
    from .load import Problem
    out = []
    for c in collisions(table(spec)):
        where = None
        for x in c["things"]:
            got = {"projection": spec.items, "dashboard": spec.dashboards}.get(x["kind"], {}).get(x["name"])
            if (where := getattr(got, "where", None)) is not None:
                break
        out.append(Problem(level, f"address collision: {c['message']}", where, "address-collision",
                           f"{c['scope'] or 'top'}.{c['segment']}"))
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
    """The highest scope on ``s``'s chain that contains the thing (None: none does)."""
    if s is None:
        return None
    on = [x for x in _chain(t, s) if x in thing["in"]]
    return on[-1] if on else None


def _canonical(t: dict, thing: dict) -> str | None:
    if not thing["in"]:
        return None
    if thing["defined_in"] is not None and (got := _top(t, thing, thing["defined_in"])) is not None:
        return got
    return min(thing["in"], key=lambda x: (len(_chain(t, x)), thing["in"].index(x)))


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


def _at(t: dict, s: str, rest: str = "") -> str:
    base = t["scopes"][s]["path"].rstrip("/")
    return (base + "/" + rest) if rest else (base or "/")


def _addr(t: dict, kind: str, name: str, s: str, id_: str | None = None) -> str:
    if kind == "projection":
        return _at(t, s, _enc(name))
    if kind == "item":
        p = _prefix(t["projections"][name]["id"])
        rest = id_[len(p):] if p is not None and id_.startswith(p) else id_
        return _at(t, s, f"{_enc(name)}/{_segs(rest)}")
    return _at(t, s, f"{'goals' if kind == 'goal' else 'agents'}/{_enc(name)}")


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
                return _thing(t, s, SHOWS[segs[i]], rest[0])
            return None
        if e["kind"] == "projection":
            return _thing(t, s, "item" if rest else "projection", e["name"], "/".join(rest) if rest else None)
        return None
    return {"scope": s, "kind": "system", "name": s}


def _thing(t: dict, s: str, kind: str, name: str, rest: str | None = None) -> dict | None:
    table_ = t["projections" if kind in ("projection", "item") else kind + "s"]
    thing = table_.get(name)
    if thing is None or s not in thing["in"]:
        return None
    out: dict = {"scope": s, "kind": kind, "name": name}
    if kind == "item":
        p = _prefix(thing["id"])
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
