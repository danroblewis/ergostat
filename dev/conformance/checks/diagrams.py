"""The checks of ergostat's diagrams list (dev/conformance/diagrams.yaml): ``diagrams.py CASE``.

Each builds the graph answer for examples/image-squeeze in-process, through the function the ``/graph`` route
calls (``ergostat.web.server.api``), on a copy of the example with a state dir of its own under a temp folder: no
server, no network. Exit 0: the answer holds what the case says. 1: the view or a field is missing. 2: the check's
own error (the example will not load, an exception, a case unknown), so it reads as broken, never as unmet."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class Unmet(Exception):          # the answer lacks what the case says: exit 1
    pass


def need(ok, why: str) -> None:
    if not ok:
        raise Unmet(why)


def record(p, now: float) -> dict[str, list[str]]:
    """A small record: two cases moved between states, each event caused by the one written before it."""
    moves, last, t = {"case/a": ["unmet", "met", "unmet"], "case/b": ["unmet", "met"]}, None, now - 900
    for item, states in moves.items():
        for s in states:
            t += 60
            last = p.events.add(f"case.{s}", item=item, source="bench", causedby=last, at=t)["id"]
    return moves


def ids(g: dict) -> set[str]:
    return {n.get("id") for n in g.get("nodes") or []}


def stock_and_flow(graph, m, moves) -> None:
    if not m.stocks or not m.flows:
        raise RuntimeError("the example has no stocks or no flows: nothing to check")
    want = {f"stock:{s}" for s in m.stocks} | {f"flow:{f}" for f in m.flows}
    need(want <= ids(graph(view="dynamics", open="*")), "no node for some stock or flow")


def block_diagram(graph, m, moves) -> None:
    have, s = ids(graph(view="blocks", open="*")), m.spec
    served = [g for g in s.goals if s.loop(g).controllers or s.loop(g).actuators]
    if not s.blocks or not served:
        raise RuntimeError("the example has no blocks or no goal served: nothing to check")
    for n, b in s.blocks.items():   # a block reading nothing that only moves flows is the world: a disturbance, if read
        world = b.targets() and not b.reads() and all(t.kind in ("flow", "auxiliary") for t in b.targets())
        need(f"blk:{n}" in have or world, f"no block for {n}")
    need(any(x.startswith("blk:") for x in have), "no block drawn")
    need({f"sum:{g}" for g in served} <= have, f"no summing junction for {sorted({f'sum:{g}' for g in served} - have)}")


def process_map(graph, m, moves) -> None:
    g = graph(view="process", kinds="case", by="states", since="1h")
    have, lines = ids(g), {(e.get("source"), e.get("target")) for e in g.get("edges") or [] if e.get("kind") == "follows"}
    for states in moves.values():
        need({f"p:case:{x}" for x in states} <= have, f"no node for a state of {states}")
        for a, b in zip(states, states[1:], strict=False):
            need((f"p:case:{a}", f"p:case:{b}") in lines, f"no line for the move {a} -> {b}")


def service_map(graph, m, moves) -> None:
    g = graph(view="map", since="1h")
    need(g.get("kind") == "map", f"no map view: view=map answers kind {g.get('kind')!r}")
    need(g.get("edges"), "the map has no edges")
    for e in g["edges"]:
        need(all(k in e for k in ("rate", "failures", "delay")), f"edge {e.get('id')} lacks rate, failures or delay")


def sequence_diagram(ask, m, moves) -> None:
    g = ask("items/case%2Fb") or {}               # opened from the item's page, not a view (diagram-options.md:65-68)
    need("lifelines" in g and "messages" in g, "the item's answer has no lifelines or no messages")
    lifelines, msgs = g.get("lifelines") or [], g.get("messages") or []
    need(set(moves) <= {x.get("id") for x in lifelines}, "no lifeline for each item of the chain")
    need(len(msgs) == 5 and [x.get("seq") for x in msgs] == sorted(x.get("seq") for x in msgs),
         "the chain's five messages are not there in order")


CASES = {"stock-and-flow": stock_and_flow, "block-diagram": block_diagram, "process-map": process_map,
         "service-map": service_map, "sequence-diagram": sequence_diagram}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in CASES:
        print(f"usage: diagrams.py {{{','.join(CASES)}}}", file=sys.stderr)
        return 2
    try:
        tmp, home = Path(tempfile.mkdtemp(prefix="conformance-diagrams-")), os.environ.get("ERGOSTAT_HOME")
        try:
            os.environ["ERGOSTAT_HOME"] = str(tmp / "home")
            sys.path.insert(0, str(ROOT))
            from ergostat import model as mdl
            from ergostat.store import Project
            from ergostat.web.server import Live, api
            shutil.copytree(ROOT / "examples" / "image-squeeze", tmp / "image-squeeze",
                            ignore=shutil.ignore_patterns("run", "__pycache__"))
            (tmp / "state").mkdir()
            p = Project(mdl.load(tmp / "image-squeeze"), tmp / "state")
            moves = record(p, time.time())
            live = Live(p)
            CASES[argv[0]](lambda path="graph", **q: api(live, path, {k: [v] for k, v in q.items()}), p.model, moves)
        finally:
            os.environ.pop("ERGOSTAT_HOME") if home is None else os.environ.update(ERGOSTAT_HOME=home)
            shutil.rmtree(tmp, ignore_errors=True)
    except Unmet as e:
        print(f"unmet: {e}", file=sys.stderr)
        return 1
    except Exception as e:                        # the check's own error: broken, never read as unmet
        print(f"broken: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print("met")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
