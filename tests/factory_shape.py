"""A generated record of the factory's shape, for the Items overview's tests (items-one-section-per-kind-closed): about
25 projections (the model's own and ergostat's built-in ones) in four systems, 700 gaps and 2,500 sessions over a week,
each moving through its states, with a few hundred items of each other kind."""

from __future__ import annotations

import random
import time
from pathlib import Path

SYSTEMS = {"intake": ["request", "idea", "bug", "question"], "build": ["gap", "session", "review", "merge", "suite"],
           "run": ["deploy", "incident", "alert", "rollout"], "keep": ["doc", "note", "benchmark"]}
STATES = ["queued", "working", "checking", "done", "parked"]
SIZE = {"gap": 700, "session": 2500}           # the rest: OTHERS each
OTHERS = 120


def model_yaml() -> str:
    lines = ["name: factory-shape", "systems:"]
    lines += [f"  {s}:\n    description: the {s} side" for s in SYSTEMS]
    lines.append("projections:")
    for s, kinds in SYSTEMS.items():
        for k in kinds:
            on = ", ".join(f"{k}.{st}: {{state: set('{st}')}}" for st in STATES)
            lines += [f"  {k}:", f"    match: {{key: {k}/*}}", f"    system: {s}", f"    states: [{', '.join(STATES)}]",
                      f"    events: {{{on}}}", "    otherwise: rest"]
    done = ", ".join(f"{k}: [done]" for ks in SYSTEMS.values() for k in ks)
    paused = ", ".join(f"{k}: [parked]" for ks in SYSTEMS.values() for k in ks)
    lines += ["messages:", f"  done: {{{done}}}", f"  paused: {{{paused}}}"]
    return "\n".join(lines) + "\n"


def write(d: Path, seed: int = 7) -> None:
    """The model in ``d`` and its record (under the ERGOSTAT_HOME already set)."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(model_yaml())
    p = Project(mdl.load(d))
    rnd = random.Random(seed)
    now = time.time()
    evs = []
    for ks in SYSTEMS.values():
        for k in ks:
            for i in range(SIZE.get(k, OTHERS)):
                t = now - rnd.uniform(60, 7 * 86400)
                path = STATES[:rnd.randint(1, 4)] if rnd.random() > 0.05 else ["queued", "parked"]
                for st in path:
                    evs.append({"type": f"{k}.{st}", "item": f"{k}/{i}", "data": {"title": f"{k} {i}"}, "at": min(t, now - 1)})
                    t += rnd.uniform(60, 4 * 3600)
    evs.sort(key=lambda e: e["at"])
    p.events.add_many(evs, new=True)
