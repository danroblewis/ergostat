"""Write a factory-size state directory, the same for a seed, so page speed and answer sizes are tested without the
live factory (tests/README.md says what it holds): `scripts/factory_fixture.py OUT [--seed 1] [--end EPOCH]`.

OUT/model is the model (a projection each of scale_model.py's plain workflows, measures, `use: modelling`, `upkeep`),
OUT/home its ERGOSTAT_HOME, holding its record: the 24 h before --end; its readings are written to the VictoriaMetrics
the record uses (ERGOSTAT_METRICS_URL), and kept in OUT/readings.json.gz too, so another server can be given them
(tests/conftest.py, one VictoriaMetrics a test process). Prints what it wrote, as JSON."""

import argparse
import gzip
import heapq
import itertools
import json
import os
import random
import sys
import uuid
from functools import partial
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scale_model as sm  # noqa: E402

KINDS = {"gap": (430, "building", ["new", "ready", "building", "review", "approved"]), "flake": (140, "landing", ["new", "seen"]),
         "review": (260, "building", ["new", "reading", "judged"]), "upgrade": (90, "landing", ["new", "installing", "checking"]),
         "research": (60, "planning", ["new", "asked", "reading"]), "situation": (180, "oversight", ["new", "raised"]),
         "lesson": (120, "intake", ["new", "proposed", "applying"]), "knowledge": (220, "pools", ["new", "drafted"])}
SYSTEMS = ["intake", "building", "landing", "pools", "oversight", "planning"]
LEASED, GATED, OFF_GOAL = ("building", "review", "approved"), "gap-approved", "gap-prompt"
PAUSED, DEAD, SEGMENTS, END, DAY = 40, 10, 30, 1795305600, 86400.0     # END: 2026-11-22 00:00 UTC


def write_model(d: Path) -> None:
    for x in ("parts", "bin"):
        (d / x).mkdir(parents=True)
    for name, text in (("feed.py", sm.FEED), ("step.py", sm.STEP), ("read.py", "print(0)\n")):
        (d / "bin" / name).write_text(text)
    for kind, (_, system, states) in KINDS.items():
        w = {"name": kind, "system": system, "plain": True, "states": states, "handoff": None}
        doc = {"defaults": {"system": system}, **{k: v for k, v in sm.plain_workflow(w, {}, 6, 3).items() if v}}
        if kind == "gap":                     # paused (parked), chained (depends_on), and its last step gated
            g = doc["projections"]["gap"]
            g["fields"]["state"]["values"].append("parked")
            g["relations"] = {"depends_on": "gap"}
            other = g["events"].pop("other")            # (the catch-all stays last: the first kind that takes an event wins)
            g["events"]["gap-parked"] = {"when": "type == 'gap.parked'", "...": "data", "state": "set('parked')"}
            g["events"]["other"] = other
            doc["blocks"][GATED]["actions"] = ["ship"]
        (d / "parts" / f"{kind}.yaml").write_text(sm.dump(doc))
    agents = {f"{r}-{s}": {"kind": k, **({"at-once": 6} if k == "program" else {}), "description": f"the {r} of {s}"}
              for s in SYSTEMS for r, k in (("pool", "program"), ("lead", "person"))}
    (d / "ergostat.yaml").write_text(sm.dump({
        "name": "factory-fixture", "include": ["parts/*.yaml"],
        "systems": {s: {"description": f"the factory's {s}, a stand-in"} for s in SYSTEMS},
        "agents": {"owner": {"kind": "person", "description": "the owner"}, **agents},
        "actions": {"ship": {"run": "python3 bin/read.py ship", "in": ".", "gate": "approve", "class": "push",
                             "description": "Ship a gap (a stand-in): the owner approves it"}},
        "messages": {"paused": {"gap": ["parked"]}},
        "uses": {"modelling": {"use": "modelling"}, "upkeep": {"use": "upkeep"}}}))


def write_measures(d: Path, spec) -> None:
    """The sensors and goals the workflows and the uses leave to reach 260 and 60, over 16 files of auxiliaries."""
    left = {"sensors": 260 - len(spec.sensors()), "goals": 60 - len(spec.goals)}
    for j in range(16):
        n, g = (x // 16 + (j < x % 16) for x in left.values())
        aux = {f"m{j:02d}-{i}": {"unit": "1", "description": "a reading of the factory's own (a stand-in)",
                                 "sensor": {"run": f"python3 bin/read.py m{j}-{i}", "every": "1m"}} for i in range(n)}
        goals = {f"{a}-ok": {"auxiliary": a, "hold": "<= 100", "description": "within its bound"} for a in list(aux)[:g]}
        doc = {"defaults": {"system": SYSTEMS[j % 6]}, "auxiliaries": aux, "goals": goals}
        (d / "parts" / f"measures-{j:02d}.yaml").write_text(sm.dump({k: v for k, v in doc.items() if v}))


def machine(spec) -> list[str]:
    """The blocks declared for a program to fill: not an AI agent's or a person's, nor ergostat's (an onoff, a watchdog)."""
    return sorted(n for n, b in spec.blocks.items() if b.type not in ("ai", "person", "onoff", "external"))


def counts(spec) -> dict:
    return {"files": len(spec.files), "systems": len(spec.systems), "goals": len(spec.goals), "sensors": len(spec.sensors()),
            "machine": len(machine(spec)), "kinds": sum(not k.startswith("ergostat.") for k in spec.items)}


class Record:
    def __init__(self, seed: int, end: float):
        self.rnd, self.end, self.n, self.evs = random.Random(seed), end, 0, []

    def add(self, t: float, type: str, item: str, data: dict | None = None) -> None:
        self.n += 1
        self.evs.append({"id": f"c{self.n:07d}", "at": min(t, self.end - 1), "type": type, "item": item,
                         "source": "fixture", "data": data or {}})

    def lease(self, item: str, t: float, state: str, fence: int, how: str, count: bool = True) -> float:
        run = {"run": f"run-{self.n:07d}", "fence": fence}
        self.add(t, "ergostat.lease.taken", item, {**run, "block": f"gap-{state}", "ttl": 3600, "max": 3, "back": state,
                                                   "tier": "program"})
        self.add(t + 60, "ergostat.lease.ended", item, {**run, "how": how, "exit": int(how != "ack"), "why": how,
                                                        **({} if count else {"count": False})})
        return t + 120

    def items(self) -> dict:
        """Items made over the day and moved on; a gap leased at LEASED (a tenth given back once first), given back
        uncounted at the gated block until those are 60% of all attempts; PAUSED parked, DEAD given back three times."""
        r, gated, tries = self.rnd, 0, 0
        for kind, (n, _, states) in KINDS.items():
            last = None
            for i in range(n):
                id, t, fence = f"{kind}/{i:04d}", self.end - DAY + r.uniform(0, DAY - 3600), 0
                after = last if kind == "gap" and last and r.random() < 0.8 else None
                self.add(t, f"{kind}.new", id, {"title": f"stand-in {kind} {i}", **({"depends_on": [after]} if after else {})})
                last = id
                depth = len(states) if r.random() < 0.45 else r.randrange(len(states))     # done, or still under way
                if kind == "gap" and i < PAUSED + DEAD:
                    depth = 3 if i < PAUSED else 2                                          # parked at review, dead at building
                for s, nxt in zip(states, [*states[1:], "done"][:depth], strict=False):
                    t += r.uniform(300, 1800)
                    while kind == "gap" and f"gap-{s}" == GATED and gated < 1.5 * tries:
                        fence, gated, t = fence + 1, gated + 1, self.lease(id, t, s, fence + 1, "nack", count=False)
                    for how in (["nack"] if r.random() < 0.1 else []) + ["ack"] if kind == "gap" and s in LEASED else []:
                        fence, tries, t = fence + 1, tries + 1, self.lease(id, t, s, fence + 1, how)
                    self.add(t, f"{kind}.{nxt}", id)
                if kind == "gap" and i < PAUSED:
                    self.add(t + 600, "gap.parked", id)
                for _ in range(3 if kind == "gap" and PAUSED <= i < PAUSED + DEAD else 0):
                    fence, tries, t = fence + 1, tries + 1, self.lease(id, t + 600, "building", fence + 1, "nack")
        return {"lease_attempts": tries + gated, "uncounted": gated}

    def write(self, p, spec, model) -> dict:
        said, r, t0 = self.items(), self.rnd, self.end - DAY
        upkept = {str(s.of) for s in spec.sensors() if (s.builtin or "").startswith("ergostat.upkeep.")}
        offs = {OFF_GOAL: (self.end - 6 * 3600, self.end - 6 * 3600 + 1200),            # off 20 min; an upkeep goal off now
                sorted(g for g, x in spec.goals.items() if str(x.of) in upkept)[0]: (self.end - 7200, self.end + 1)}
        for g, (a, b) in offs.items():
            self.add(a, "loop.off", g, {"setpoint": str(spec.goals[g].hold), "planted": True})
            if b < self.end:
                self.add(b, "loop.holding", g, {"setpoint": str(spec.goals[g].hold)})
        rows = []                             # a random walk a minute, held within its goal but where planted off
        for s in model.sensors.values():
            g = next((x for x in spec.goals.values() if x.of.name == s.measures), None)
            v, (a, b), h = r.uniform(0, 5), offs.get(g.name if g else "", (0, 0)), g.hold if g else None
            for k in range(1440):
                at, v = t0 + 60 * k + 30, max(0.0, v + r.gauss(0, 0.5))
                y = v if h is None else min(v, h.value) if "<" in h.op else max(v, h.value) if ">" in h.op else h.value
                if a <= at < b:
                    y = h.value + 1 + 2 * g.tolerance if "<" in h.op else h.value - 1 - 2 * g.tolerance
                rows.append((f"sensor/{s.name}", at, round(y, 3)))
        p.measurements.add_many(rows)
        self.rows = rows
        blocks, seal = machine(spec), p.events.seal   # the rest: the machine blocks' runs, evenly over the day
        pairs = (SEGMENTS * seal + seal // 2 - len(self.evs)) // 2
        started = ({"id": f"r{k:07d}a", "at": t0 + (k + 0.5) * DAY / pairs, "type": "agent.started",
                    "item": blocks[k % len(blocks)], "source": "ergostat", "data": {}} for k in range(pairs))
        runs = (e for s in started for e in (s, {**s, "id": s["id"][:-1] + "b", "at": s["at"] + 2, "type": "agent.ran",
                                                 "causedby": s["id"], "data": {"seconds": 2, "exit": 0}}))
        for chunk in itertools.batched(heapq.merge(sorted(self.evs, key=lambda e: (e["at"], e["id"])), runs,
                                                   key=lambda e: e["at"]), seal):
            p.events.add_many(list(chunk), new=True)
        return {**said, "events": len(self.evs) + 2 * pairs, "readings": len(rows), "off": sorted(offs)}


def build(out: Path, seed: int = 1, end: float = END) -> dict:
    from ergostat import model as mdl
    from ergostat.spec import read
    from ergostat.store import Project
    if out.exists():
        raise SystemExit(f"{out} exists: give a new directory")
    write_model(out / "model")
    write_measures(out / "model", read(out / "model" / "ergostat.yaml", extremes=False)[0])
    spec, problems = read(out / "model" / "ergostat.yaml", extremes=False)
    if errors := [str(x) for x in problems if x.level == "error"]:
        raise SystemExit("the model does not compile: " + "; ".join(errors))
    os.environ["ERGOSTAT_HOME"] = str(out / "home")
    ids = random.Random(seed)                 # the segments' names and the layout token, and gzip's stamp: as the seed says
    with mock.patch.object(uuid, "uuid4", lambda: uuid.UUID(int=ids.getrandbits(128))), \
            mock.patch.object(gzip, "compress", partial(gzip.compress, mtime=0)):
        p = Project(m := mdl.load(out / "model"))
        said = (rec := Record(seed, end)).write(p, spec, m)
        (out / "readings.json.gz").write_bytes(gzip.compress(json.dumps(rec.rows).encode()))
    return {**counts(spec), **said, "seed": seed, "end": end, "record": str(p.dir)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--end", type=float, default=END, help="the record's last moment (epoch seconds)")
    print(json.dumps(build(**vars(ap.parse_args()))))
