"""Generate a large, realistic ergostat model, for measuring what breaks first as it grows (docs/proposals/scale.md).

    uv run python scripts/scale_model.py N OUT_DIR [--per-system 15] [--rate 6] [--step-seconds 3] [--seed 1] [--handoff 0.1]

N workflows, each a connected chain like docs/AGENT-GUIDE.md's example and examples/ticket-factory: an item kind
with 4 to 8 states, a stock per waiting state, chained flows (in from outside, out to done and dropped), a collector
that finds the work, a step block per waiting state taking its items under leases, and goals. About half are
written as plain YAML; the other half use the built-in `steps` template (`uses:`), which makes its own chain of
waiting and working stocks per step.

The workflows are grouped into systems of 10 to 20, and systems into areas of five. What they share:

- a **worker pool** per system (an agent, `at-once` six), which every plain step block of the system runs on;
- an **on-call load** per system (an auxiliary driven by every workflow's intake stock), held by a goal whose
  person block (the area's on-call person) drops work from every plain workflow of the system: a balancing loop
  through each of them;
- a **global on-call load**, driven by every system's, held by the incident lead, who drops work from one
  workflow in each system: loops that cross every system;
- **hand-offs**: one plain workflow in ten passes its finished items to another workflow's intake, half the
  time in another system (the chain continues there), so chains and loops cross systems;
- the **modelling** subsystem the-job has: ergostat's built-in fit measure, the change queue, the judge (built
  in) and a stand-in improver (a program: no AI, no cost).

Everything that runs is a stand-in that costs nothing: `bin/feed.py` prints new items at `--rate` an hour per
workflow (Poisson), `bin/step.py` works an item for about `--step-seconds` and moves it on (5% dropped, 3%
failing, which a lease retries), `bin/oncall.py` reads a load. No block is of type `ai`; the generated project's
README says how to run it."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import textwrap
from pathlib import Path

import yaml

STEP_WORDS = ["triage", "research", "draft", "review", "approve", "rollout", "verify", "close-out"]
EVERY = "10s"            # how often an item count is read (the steps template's own default)
OVER = "10m"             # a flow's rate window


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s,
                                                            style='"' if s[:1] in "<>=!" else None))


def dump(doc: dict) -> str:
    return yaml.dump(doc, Dumper=Dumper, sort_keys=False, width=120, default_flow_style=False)


def plan(n: int, per_system: int, seed: int, handoff: float = 0.1) -> dict:
    """Which workflows there are, in which systems, of which shape, and where each hands its work on."""
    rnd = random.Random(seed)
    wfs, systems = [], []
    i = 0
    while i < n:
        size = min(n - i, max(10, min(20, int(rnd.gauss(per_system, 3)))) if n - i > 20 else n - i)
        sname = f"sys-{len(systems) + 1:03d}"
        systems.append({"name": sname, "area": f"area-{len(systems) // 5 + 1:02d}", "workflows": []})
        for j in range(size):
            k = rnd.randint(4, 8)                                     # states, done and dropped among them
            steps = rnd.sample(STEP_WORDS, k - 3)                     # the waiting states after new
            steps = [s for s in STEP_WORDS if s in steps]             # in a sensible order
            plain = j == 0 or rnd.random() < 0.5                      # every system has a plain one (the lead drops from it)
            w = {"name": f"w{i + 1:04d}", "system": sname, "plain": plain, "states": ["new", *steps] if plain else steps,
                 "handoff": None}
            wfs.append(w)
            systems[-1]["workflows"].append(w["name"])
            i += 1
    by = {w["name"]: w for w in wfs}
    for s in systems:                                                 # the incident lead sheds from each system's first
        by[s["workflows"][0]]["lead_sheds"] = True
    for w in wfs:                                                     # one plain workflow in ten (handoff) hands its work on
        if w["plain"] and len(wfs) > 1 and rnd.random() < handoff:
            same = [x for x in wfs if x["system"] == w["system"] and x is not w]
            other = [x for x in wfs if x["system"] != w["system"]]
            pool = other if (other and (rnd.random() < 0.5 or not same)) else same
            w["handoff"] = rnd.choice(pool)["name"]
    return {"workflows": wfs, "systems": systems, "by": by}


def intake(w: dict) -> str:
    """The stock where a workflow's work arrives."""
    return f"{w['name']}-{w['states'][0]}"


def plain_workflow(w: dict, by: dict, rate: float, step_seconds: float) -> dict:
    n, st = w["name"], w["states"]
    out: dict = {"items": {}, "stocks": {}, "auxiliaries": {}, "flows": {}, "parameters": {}, "goals": {}, "blocks": {}}
    on = {f"{n}.{s}": s for s in st[1:]}
    on.update({f"{n}.new": "new", f"{n}.done": "done", f"{n}.dropped": "dropped"})
    out["items"][n] = {"id": f"{n}/*", "description": f"a piece of work of kind {n}",
                       "states": [*st, "done", "dropped"], "on": on, "show": ["title"], "lease": {"attempts": 3}}
    for s in st:
        out["stocks"][f"{n}-{s}"] = {"unit": "items", "description": f"{n} items waiting at {s}",
                                     "sensor": {"items": n, "state": s, "every": EVERY}}
    out["auxiliaries"][f"{n}-oldest"] = {"unit": "hours", "description": f"how long the oldest {n} item has waited",
                                         "driven-by": [f"+stock.{n}-{s}" for s in st],
                                         "sensor": {"items": n, "state": list(st), "measure": "oldest", "every": EVERY}}
    out["flows"][f"{n}-arriving"] = {"to": f"{n}-new", "description": f"new {n} items, as the collector finds them",
                                     "sensor": {"items": n, "entering": "new", "over": OVER}}
    for a, b in zip(st, st[1:], strict=False):
        out["flows"][f"{n}-{b}"] = {"from": f"{n}-{a}", "to": f"{n}-{b}", "driven-by": [f"+stock.{n}-{a}"],
                                    "equation": f"stock.{n}-{a} / {n}-{a}-time",
                                    "sensor": {"items": n, "entering": b, "over": OVER}}
    done = {"from": f"{n}-{st[-1]}", "driven-by": [f"+stock.{n}-{st[-1]}"], "equation": f"stock.{n}-{st[-1]} / {n}-{st[-1]}-time",
            "sensor": {"items": n, "entering": "done", "over": OVER}}
    if w["handoff"]:
        done["to"] = intake(by[w["handoff"]])
        done["description"] = f"finished {n} items, handed on to {w['handoff']}"
    out["flows"][f"{n}-done"] = done
    mid = st[len(st) // 2]
    out["flows"][f"{n}-dropped"] = {"from": f"{n}-{mid}", "driven-by": [f"+stock.{n}-{mid}"],
                                    "description": f"{n} items dropped: not worth doing, or dropped by on-call",
                                    "sensor": {"items": n, "entering": "dropped", "over": OVER}}
    if len(st) > 1:
        out["flows"][f"{n}-expedited"] = {"from": f"{n}-{st[0]}", "to": f"{n}-{st[1]}", "driven-by": [f"+stock.{n}-{st[0]}"],
                                          "description": f"{n} items a person pushed on past the queue",
                                          "sensor": {"items": n, "entering": st[1], "where": {"expedited": "yes"}, "over": OVER}}
    if w.get("lead_sheds"):
        out["flows"][f"{n}-shed"] = {"from": f"{n}-{st[0]}", "driven-by": [f"+stock.{n}-{st[0]}"],
                                     "description": f"{n} items the incident lead shed",
                                     "sensor": {"items": n, "entering": "dropped", "where": {"shed": "yes"}, "over": OVER}}
    for s in st:
        out["parameters"][f"{n}-{s}-time"] = {"value": f"{max(1, round(step_seconds))}s", "estimate": True,
                                              "description": f"how long step {s} takes"}
        out["goals"][f"{n}-{s}-clear"] = {"stock": f"{n}-{s}", "hold": "<= 0", "description": f"nothing waits at {s}"}
    out["goals"][f"{n}-prompt"] = {"auxiliary": f"{n}-oldest", "hold": "<= 2",
                                   "description": f"no {n} item waits over two hours"}
    sys_ = w["system"]
    out["blocks"][f"{n}-collect"] = {"type": "program", "run": f"python3 bin/feed.py {n} {rate:g}", "every": "1m",
                                     "out": f"flow.{n}-arriving"}
    for i, s in enumerate(st):
        nxt = st[i + 1] if i + 1 < len(st) else "done"
        leaving = f"flow.{n}-{nxt}" if nxt != "done" else f"flow.{n}-done"
        out["blocks"][f"{n}-{s}"] = {"type": "program", "agent": f"pool-{sys_}", "goal": f"{n}-{s}-clear",
                                     "run": f"python3 bin/step.py {n}.{nxt} {step_seconds:g}",
                                     "takes": {"kind": n, "at": s, "to": [nxt, "dropped"]}, "pool": 2,
                                     "out": leaving}
    out["blocks"][f"{n}-chase"] = {"type": "person", "agent": f"lead-{sys_}", "goal": f"{n}-prompt",
                                   "ask": f"A {n} item has waited over two hours: look at why.",
                                   "out": f"flow.{n}-expedited" if len(st) > 1 else f"flow.{n}-done"}
    return out


def template_workflow(w: dict, rate: float, step_seconds: float) -> dict:
    return {"use": "steps", "within": w["system"], "description": f"a piece of work of kind {w['name']}, step by step",
            "with": {"kind": w["name"], "pool": 2, "poll": "1m", "stand-in-rate": rate,
                     "steps": [{"name": s, "run": f"python3 bin/step.py - {step_seconds:g}"} for s in w["states"]]}}


def system_file(s: dict, by: dict, rate: float, step_seconds: float) -> dict:
    doc: dict = {"defaults": {"system": s["name"]}}
    parts: dict = {k: {} for k in ("items", "stocks", "auxiliaries", "flows", "parameters", "goals", "blocks")}
    uses = {}
    for name in s["workflows"]:
        w = by[name]
        if w["plain"]:
            for k, v in plain_workflow(w, by, rate, step_seconds).items():
                parts[k].update(v)
        else:
            uses[name] = template_workflow(w, rate, step_seconds)
    plains = [by[x] for x in s["workflows"] if by[x]["plain"]]
    load = f"oncall-load-{s['name']}"
    parts["auxiliaries"][load] = {"unit": "items", "description": f"what is waiting on the system's on-call, {s['name']}",
                                  "driven-by": [f"+stock.{intake(by[x])}" for x in s["workflows"]],
                                  "sensor": {"run": f"python3 bin/oncall.py {s['name']}", "every": "30s"}}
    parts["goals"][f"{load}-ok"] = {"auxiliary": load, "hold": "<= 40", "description": "on-call is not swamped"}
    parts["blocks"][f"oncall-{s['name']}"] = {"type": "person", "agent": f"oncall-{s['area']}", "goal": f"{load}-ok",
                                              "ask": "On-call is swamped: drop what can wait.",
                                              "out": [f"flow.{w['name']}-dropped" for w in plains]}
    doc.update({k: v for k, v in parts.items() if v})
    if uses:
        doc["uses"] = uses
    return doc


MODELLING = {
    "defaults": {"system": "modelling"},
    "items": {"session": {"id": "session/*", "states": ["open", "done", "failed", "lost"],
                          "on": {"session.ran": "done", "session.failed": "failed", "session.lost": "lost"},
                          "show": ["role", "model", "cost_usd", "seconds"]}},
    "stocks": {
        "model-error": {"unit": "1", "description": "the scaled error of the model's replay on the record",
                        "sensor": {"builtin": "ergostat.model.fit", "every": "1m"}},
        **{f"{k}-changes": {"unit": "changes", "sensor": {"items": "ergostat.model-change", "state": s, "every": EVERY},
                            **({"cumulative": True} if s == "accepted" else {})}
           for k, s in (("pending", "checked"), ("testing", "testing"), ("passed", "passed"), ("accepted", "accepted"))}},
    "flows": {
        "model-drift": {"to": "model-error", "two-way": True, "sensor": {"changes": "rest", "over": OVER, "every": "1m"}},
        "model-mended": {"from": "model-error", "driven-by": ["+stock.model-error", {"cause": "+flow.changes-accepted", "instant": True}],
                         "sensor": {"items": "ergostat.model-change", "entering": "accepted", "sum": "fit_gained", "over": OVER}},
        "changes-made": {"to": "pending-changes", "sensor": {"items": "ergostat.model-change", "entering": "checked", "over": OVER}},
        "changes-superseded": {"from": "pending-changes", "driven-by": "+stock.pending-changes",
                               "sensor": {"items": "ergostat.model-change", "entering": "superseded", "over": OVER}},
        "tests-started": {"from": "pending-changes", "to": "testing-changes", "driven-by": "+stock.pending-changes",
                          "sensor": {"items": "ergostat.model-change", "entering": "testing", "over": OVER}},
        "changes-passed": {"from": "testing-changes", "to": "passed-changes", "driven-by": "+stock.testing-changes",
                           "sensor": {"items": "ergostat.model-change", "entering": "passed", "over": OVER}},
        "changes-failed": {"from": "testing-changes", "driven-by": "+stock.testing-changes",
                           "sensor": {"items": "ergostat.model-change", "entering": "failed", "over": OVER}},
        "changes-accepted": {"from": "passed-changes", "to": "accepted-changes", "driven-by": "+stock.passed-changes",
                             "sensor": {"items": "ergostat.model-change", "entering": "accepted", "over": OVER}}},
    "goals": {"model-fits": {"stock": "model-error", "hold": "<= 0.05", "description": "the model follows the record"}},
    "blocks": {
        "improver": {"type": "program", "agent": "modeller", "goal": "model-fits", "run": "python3 bin/improver.py",
                     "every": "3m", "timeout": "15m", "out": "flow.changes-made"},
        "judge": {"type": "judge", "every": "30s", "hold-out": "4m", "windows": [1, 2, 4], "threshold": "2%",
                  "accept": {"parameter": "auto"},
                  "in": {"waiting": "+stock.pending-changes", "testing": "+stock.testing-changes"},
                  "out": {"testing": "flow.tests-started", "passed": "flow.changes-passed",
                          "failed": "flow.changes-failed", "accepted": "flow.changes-accepted"}}}}


def main_file(p: dict, n: int) -> dict:
    systems_: dict = {"org": {"description": f"{n} workflows, as one system"}}
    areas = sorted({s["area"] for s in p["systems"]})
    for a in areas:
        systems_[a] = {"within": "org", "description": "five systems, one on-call person"}
    for s in p["systems"]:
        systems_[s["name"]] = {"within": s["area"], "description": f"{len(s['workflows'])} workflows"}
    systems_["modelling"] = {"description": "the model, improved by a loop of its own"}
    agents: dict = {"owner": {"kind": "person", "description": "the owner"},
                    "incident-lead": {"kind": "person", "description": "holds the whole on-call load"},
                    "modeller": {"kind": "program", "description": "the stand-in improver"}}
    for a in areas:
        agents[f"oncall-{a}"] = {"kind": "person", "description": f"on-call for {a}"}
    for s in p["systems"]:
        agents[f"pool-{s['name']}"] = {"kind": "program", "at-once": 6, "description": f"the worker pool of {s['name']}"}
        agents[f"lead-{s['name']}"] = {"kind": "person", "description": f"the lead of {s['name']}"}
    by = p["by"]
    first_plain = [next(by[w] for w in s["workflows"] if by[w]["plain"]) for s in p["systems"]]
    return {
        "name": f"scale-{n}",
        "include": ["systems/*.yaml", "modelling.yaml"],
        "systems": systems_,
        "agents": agents,
        "auxiliaries": {"oncall-load": {"system": "org", "unit": "items", "description": "the whole on-call load",
                                        "driven-by": [f"+auxiliary.oncall-load-{s['name']}" for s in p["systems"]],
                                        "sensor": {"run": "python3 bin/oncall.py all", "every": "30s"}}},
        "goals": {"oncall-load-ok": {"system": "org", "auxiliary": "oncall-load", "hold": f"<= {40 * len(p['systems'])}",
                                     "description": "the organisation's on-call is not swamped"}},
        "blocks": {"incident-lead": {"system": "org", "type": "person", "agent": "incident-lead", "goal": "oncall-load-ok",
                                     "ask": "On-call is swamped everywhere: drop what can wait.",
                                     "out": [f"flow.{w['name']}-shed" for w in first_plain]}},
    }


FEED = '''"""Stand-in collector: new items of KIND at RATE an hour (Poisson), one event line each, then the rate."""
import json, os, random, sys, time, uuid
from pathlib import Path
kind, rate = sys.argv[1], float(sys.argv[2])
mem = Path("run") / f"feed-{kind}.json"
mem.parent.mkdir(exist_ok=True)
now = time.time()
try:
    last = json.loads(mem.read_text())["last"]
except (OSError, ValueError):
    last = now - 60
mem.write_text(json.dumps({"last": now}))
lam = rate * max(0.0, now - last) / 3600
n, t = 0, random.expovariate(1.0) if lam > 0 else 1e9
while t < lam:
    n += 1
    t += random.expovariate(1.0)
for _ in range(n):
    print(json.dumps({"event": f"{kind}.new", "item": f"{kind}/{uuid.uuid4().hex[:10]}", "data": {"title": "stand-in work"}}))
print(json.dumps({"out": f"flow.{kind}-arriving", "moved": n}))
'''

STEP = '''"""Stand-in step: works its item (ERGOSTAT_ITEM, given on standard input) for about SECONDS and moves it on with
EVENT (- : the steps template's own program moves it; exit 0). 5% dropped, 3% fail (the lease retries them)."""
import json, os, random, sys, time
event, seconds = sys.argv[1], float(sys.argv[2])
sys.stdin.read()
time.sleep(random.uniform(0.5, 1.5) * seconds)
r = random.random()
if r < 0.03:
    print("stand-in failure", file=sys.stderr)
    sys.exit(1)
if event != "-":
    kind = event.split(".", 1)[0]
    if r < 0.08:
        print(json.dumps({"event": f"{kind}.dropped"}))
    else:
        print(json.dumps({"event": event}))
    print(json.dumps({"moved": 1}))
'''

ONCALL = '''"""Stand-in reading of an on-call load: a slow random walk (kept in run/)."""
import json, random, sys
from pathlib import Path
mem = Path("run") / f"oncall-{sys.argv[1]}.json"
mem.parent.mkdir(exist_ok=True)
try:
    v = json.loads(mem.read_text())["v"]
except (OSError, ValueError):
    v = 10.0
v = max(0.0, v + random.gauss(0, 2))
mem.write_text(json.dumps({"v": v}))
print(round(v * (20 if sys.argv[1] == "all" else 1), 2))
'''


def improver_text() -> str:
    """the-job's stand-in improver, less its AI session: it never calls an AI (no cost)."""
    src = (Path(__file__).resolve().parent.parent / "examples/the-job/bin/improver.py").read_text()
    src = src.replace('if os.environ.get("JOB_AI") == "claude":\n        return session(prompt, me, item, started)\n', "")
    assert 'os.environ.get("JOB_AI")' not in src.split("def main")[1], "the improver's AI branch is still there"
    return src


def generate(n: int, out: Path, per_system: int = 15, rate: float = 6.0, step_seconds: float = 3.0, seed: int = 1,
             handoff: float = 0.1) -> dict:
    p = plan(n, per_system, seed, handoff)
    if out.exists():
        shutil.rmtree(out)
    (out / "systems").mkdir(parents=True)
    (out / "bin").mkdir()
    for s in p["systems"]:
        (out / "systems" / f"{s['name']}.yaml").write_text(dump(system_file(s, p["by"], rate, step_seconds)))
    (out / "modelling.yaml").write_text(dump(MODELLING))
    (out / "ergostat.yaml").write_text(f"# Generated by scripts/scale_model.py {n} (seed {seed}); do not edit.\n" +
                                       dump(main_file(p, n)))
    for name, text in (("feed.py", FEED), ("step.py", STEP), ("oncall.py", ONCALL), ("improver.py", improver_text())):
        (out / "bin" / name).write_text(text)
    (out / "README.md").write_text(textwrap.dedent(f"""\
        # scale-{n}

        Generated by `scripts/scale_model.py {n}`: {n} workflows in {len(p['systems'])} systems. Stand-ins only.
        Run it with its own record: `ERGOSTAT_HOME=/tmp/h ergostat -C . run --foreground --no-web`.
        """))
    stats = {"workflows": n, "systems": len(p["systems"]), "plain": sum(w["plain"] for w in p["workflows"]),
             "template": sum(not w["plain"] for w in p["workflows"]),
             "handoffs": sum(bool(w["handoff"]) for w in p["workflows"]),
             "handoffs_across": sum(bool(w["handoff"]) and p["by"][w["handoff"]]["system"] != w["system"]
                                    for w in p["workflows"])}
    (out / "plan.json").write_text(json.dumps(stats, indent=1))
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("n", type=int, help="workflows")
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-system", type=int, default=15)
    ap.add_argument("--rate", type=float, default=6.0, help="new items an hour per workflow")
    ap.add_argument("--step-seconds", type=float, default=3.0, help="how long a stand-in step works an item")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--handoff", type=float, default=0.1, help="the share of plain workflows that hand their work on")
    a = ap.parse_args()
    print(json.dumps(generate(a.n, a.out, a.per_system, a.rate, a.step_seconds, a.seed, a.handoff)))


if __name__ == "__main__":
    main()
