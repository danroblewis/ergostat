"""The graphs ergostat works out itself, each as a ``graph`` of one named kind for a panel (SPEC §4e, *A graph*; the
chart catalog's §2.2): ``{"source": "graph", "diagram": D, "kind"?: K}``.

- ``dependency``: the Items page's precedence network (``precedence.py``, through ``web/relations_api.py``), an item a
  node and a precedence relation an edge from what comes first (``blocks``, or ``met`` once that item is finished:
  never drawn as a wait still held, G40). Its routes are real (``paths_real``), each node has its ``slack``,
  ``duration`` and whether it is ``critical``, and the answer says the critical path's end beside the end levelled by
  each block's capacity (G42: the critical path alone is not the finish date). Charts 74 and 75.
- ``process``: the process map (``process.py``), a step a node and a line an edge; its routes are not real.
- ``service``: the wiring the event log proves (``graph.wiring``), a machine a node and what passed between two an
  edge, ``observed``, ``declared`` (never seen in the window) or ``both``, with when it was last seen. The service map
  from callers' and callees' labels in metrics is ``service-map-diff-and-time``'s.

Each is checked as a data source's graph is (datasources/_frames.py), its cycles worked out on the whole of it, and
fitted to the panel (graphfit.py), with the matrix beside it. What a cycle means is said by kind (G44). A graph its
maker read only in part (past its own caps) says so, and whether it has a cycle is then not known (G43). A maker's
answer is kept ``KEPT`` seconds for each graph asked, so the record is read at most that often, however many ask."""

from __future__ import annotations

import threading
import time

from ..datasources import _frames
from ..durations import human
from . import graphfit
from .sources import Unanswerable

KEPT = 30.0
MOST_KEPT = 32
CYCLE = {   # kind: (whether a cycle is a warning, what it means). The kind sets the wording (G44)
    "process": (False, "a line back is a return or concurrency, not a defect: the items' own steps say which"),
    "conformance": (False, "a line back is a return or concurrency, not a defect: the items' own steps say which"),
    "dependency": (True, "a cycle of precedence is a defect: none of its items can ever be ready"),
    "wait_for": (True, "a cycle is a deadlock if each thing held has one unit, and otherwise only possible"),
    "impact": (False, "a cycle is shared fate: each of its members can affect the others"),
    "service": (False, "calls that go round are normal, but a cold start of them needs one to go first"),
    "lineage": (True, "a cycle in lineage is a defect: nothing is its own source"),
}
_KEPT: dict = {}
_LOCK = threading.Lock()


def _col(rows: list[dict], key: str, default=None) -> list:
    return [r.get(key, default) for r in rows]


def dependency(ans: dict) -> tuple[dict, dict]:
    """``precedence.build``'s answer as a ``dependency`` frame, and what is said beside it."""
    items = ans["items"]
    by = {x["id"]: x for x in items}
    prec = [e for e in ans["edges"] if e["kind"] == "precedence" and e["from"] in by and e["to"] in by]
    frame = {"shape": "graph", "kind": "dependency",
             "nodes": {"id": list(by), "label": [x.get("title") or x["id"] for x in items], "type": _col(items, "kind"),
                       "group": _col(items, "group"), "health": ["unhealthy" if x.get("cycle") else "ok" for x in items],
                       "fields": [{"name": "slack", "unit": "s", "role": "slack", "values": _col(items, "slack")},
                                  {"name": "duration", "unit": "s", "values": _col(items, "duration")},
                                  {"name": "critical", "unit": "", "values": [None if "critical" not in x else
                                                                              float(x["critical"]) for x in items]}]},
             "edges": {"id": [f"{e['from']}>{e['to']}:{e['rel']}" for e in prec], "source": _col(prec, "from"),
                       "target": _col(prec, "to"), "evidence": ["declared"] * len(prec),
                       "relation": ["met" if by[e["from"]]["status"] == "done" else "blocks" for e in prec],
                       "fields": [{"name": "critical", "unit": "", "values": [float(e.get("critical", False)) for e in prec]}]},
             "semantics": {"paths_real": True, "focus": ans.get("critical") or []},
             "time": {"mode": "snapshot", "since": ans.get("since"), "until": ans.get("now")},
             "omitted": {"nodes": (ans.get("capped") or {}).get("open", 0), "edges": 0, "weight_share": None if ans.get("capped") else 0.0,
                         "how": "the items past precedence.py's caps" if ans.get("capped") else ""}}
    ends = [x["lf"] for x in items if x.get("lf") is not None]
    said = {"truncated": bool(ans.get("capped")), "cycles": ans.get("cycles") or []}
    if ends:
        now = ans["now"]
        said["ends"] = {"now": now, "critical_path": max(ends), "levelled": ans["end"]}
        said["note"] = (f"The critical path ends in {human(max(ends) - now)}; levelled by each block's capacity, the work "
                        f"ends in {human(ans['end'] - now)}: the critical path alone is not the finish date")
    return frame, said


def process(ans: dict) -> tuple[dict, dict]:
    """``process.process``'s answer as a ``process`` frame."""
    ns, es, total = ans["nodes"], ans["edges"], ans.get("total") or {}
    capped = ans.get("capped") or {}
    frame = {"shape": "graph", "kind": "process",
             "nodes": {"id": _col(ns, "id"), "label": _col(ns, "label"), "type": _col(ns, "kind"), "group": _col(ns, "itemKind"),
                       "fields": [{"name": "count", "unit": "", "role": "count", "values": _col(ns, "count")},
                                  {"name": "items", "unit": "", "values": _col(ns, "items")}]},
             "edges": {"id": _col(es, "id"), "source": _col(es, "source"), "target": _col(es, "target"),
                       "relation": _col(es, "kind"), "n": _col(es, "count"),
                       "evidence": ["declared" if e["kind"] == "related" else "observed" for e in es],
                       "fields": [{"name": "count", "unit": "", "role": "count", "values": _col(es, "count")},
                                  {"name": "returns", "unit": "", "role": "count", "values": _col(es, "returns", 0)},
                                  {"name": "median", "unit": "s", "role": "latency", "values": _col(es, "median")}]},
             "semantics": {"paths_real": False},
             "time": {"mode": "window", "since": ans.get("since"), "until": ans.get("until")},
             "omitted": {"nodes": max(0, total.get("nodes", len(ns)) - len(ns)), "edges": max(0, total.get("edges", len(es)) - len(es)),
                         "weight_share": None if capped else 0.0,
                         "how": f"only what process.py draws ({', '.join(sorted(capped))} capped)" if capped else ""}}
    return frame, {"truncated": bool(capped)}


def service(ans: dict) -> tuple[dict, dict]:
    """``graph.wiring``'s answer as a ``service`` frame: what the event log proves passed between machines."""
    ns, es = ans["nodes"], ans["edges"]
    frame = {"shape": "graph", "kind": "service",
             "nodes": {"id": _col(ns, "id"), "label": _col(ns, "label"), "type": _col(ns, "agentKind"),
                       "health": ["unhealthy" if x.get("failing") else "ok" for x in ns],
                       "fields": [{"name": "runs", "unit": "", "role": "count", "values": _col(ns, "runs")}]},
             "edges": {"id": _col(es, "id"), "source": _col(es, "source"), "target": _col(es, "target"),
                       "relation": ["sends"] * len(es), "n": _col(es, "count"), "last_seen": _col(es, "last"),
                       "evidence": ["both" if e["seen"] and e["declared"] else "observed" if e["seen"] else "declared" for e in es],
                       "fields": [{"name": "per hour", "unit": "/h", "role": "rate", "values": _col(es, "perHour")}]},
             "semantics": {"paths_real": False},
             "time": {"mode": "window", "since": ans.get("since"), "until": ans.get("until")},
             "omitted": {"nodes": 0, "edges": 0, "weight_share": None if ans.get("capped") else 0.0,
                         "how": "the events past graph.py's newest 50,000" if ans.get("capped") else ""}}
    return frame, {"truncated": bool(ans.get("capped"))}


ADAPT = {"dependency": dependency, "process": process, "service": service}


def drawn(frame: dict, said: dict) -> dict:
    """A maker's frame, checked, then made a panel's (``panel``)."""
    try:
        full = _frames.answer(frame, None, 0)
    except _frames.Bad as e:
        raise Unanswerable(f"the {frame.get('kind')} graph is not well formed: {e}") from e
    return panel(full, said)


def panel(full: dict, said: dict) -> dict:
    """A checked graph, a data source's or ergostat's own: its cycles worked out on the whole of it and said by kind,
    unknown when it was cut before it came here; fitted to a panel; and the matrix beside it. ``said``: what its maker
    adds (``note``, ``truncated``, ``cycles``, ``ends``)."""
    kind, warnings, notes = full["kind"], [*full.get("warnings", ())], [said["note"]] if said.get("note") else []
    if said.get("truncated") or full["omitted"]["nodes"] or full["omitted"]["edges"]:
        full["semantics"]["acyclic"] = None
        warnings.append(("graph-truncated", f"only part of the {kind} graph was read ({full['omitted']['how']}), so "
                                            "whether it has a cycle, and what reaches what, is not known"))
    elif full["semantics"]["acyclic"] is False:
        warn, words = CYCLE[kind]
        cycles = said.get("cycles") or []
        words = f"{words} ({'; '.join(', '.join(c) for c in cycles[:3])})" if cycles else words
        (warnings.append(("graph-cycle", words)) if warn else notes.append(words))
    n, m = len(full["nodes"]["id"]), len(full["edges"]["id"])
    shown, how = graphfit.fit(full, *graphfit.PANEL)
    if how:
        warnings.append(("graph-over-budget", f"{n} nodes and {m} edges are more than the {graphfit.PANEL[0]} and "
                                              f"{graphfit.PANEL[1]} a panel draws: {'; '.join(how)}"))
    out = {**shown, "matrix": graphfit.matrix(full), "warnings": warnings}
    if notes:                                         # (said under the drawing; not a warning: a note is the engine's)
        out["said"] = notes
    if "ends" in said:
        out["ends"] = said["ends"]
    return out


def _made(p, diagram: str, kinds: list[str], since: float, until: float, past: bool, gate) -> tuple[dict, bool]:
    """The maker's answer, and whether the record was read for it now (else it was kept)."""
    key = (id(p), diagram, tuple(kinds), round(until - since), until if past else None)
    with _LOCK:
        got = _KEPT.get(key)
        if got is not None and time.monotonic() - got[0] < KEPT:
            return got[1], False
    if not gate.acquire(blocking=False):
        raise Unanswerable("busy: the record is being read for other charts; try again shortly")
    try:
        snap = {"at": until, "window": until - since}
        if diagram == "dependency":
            from ..web.relations_api import graph
            ans = graph(p, p.model, snap, {"kinds": [",".join(kinds)]} if kinds else {})
        elif diagram == "process":
            from .. import process as pm
            spec = p.model.spec
            ans = pm.process(p.events, spec, kinds or pm.kinds_of(spec, None), since, until)
        else:
            from .. import graph as gr
            ans = gr.wiring(p.model, p, snap, p.model.members(None))
    finally:
        gate.release()
    with _LOCK:
        _KEPT[key] = (time.monotonic(), ans)
        while len(_KEPT) > MOST_KEPT:
            _KEPT.pop(next(iter(_KEPT)))
    return ans, True


def answer(p, q, since: float, until: float, past: bool, gate) -> dict:
    """``q``, a graph query, over the window: the panel's graph, or ``Unanswerable``."""
    spec = getattr(p.model, "spec", None)
    if spec is None and q.diagram != "service":
        raise Unanswerable(f"this model declares no items to draw a {q.diagram} graph of")
    if q.kind is not None and (q.diagram == "service" or q.kind not in spec.items):
        raise Unanswerable(f"a {q.diagram} graph takes no kind" if q.diagram == "service"
                           else f"kind {q.kind!r} is not in the model")
    ans, read = _made(p, q.diagram, [q.kind] if q.kind else [], since, until, past, gate)
    return {"id": q.id, **drawn(*ADAPT[q.diagram](ans)), "read_log": read and q.diagram != "dependency"}
