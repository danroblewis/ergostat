"""How well a small model adds a small control system from a request in plain words.

    uv run python scripts/authoring_bench.py ROUND [--model haiku] [--only 1,3] [--out /tmp/ergostat-bench]
        [--repeat 3] [--skill PATH] [--diagrams] [--grade-only] [--ports 8795,8796]

For each request below: a scratch copy of examples/the-job with the ergostat-author skill in .claude/skills/ and
ergostat's MCP server, and Claude Code (``claude -p``, the model asked) given the request text alone (the harness
says only that the owner is away and approves writing it to the copy). Then, independently of what the agent said:
did the model check, was an instance written, and does it run (a 30-second trial of each new system), and, once the
copy has run on its stand-ins for 40 seconds, do the three views of the kinds it added agree (coherence.py). Per request:
whether its first add_use passed check and its first try_use ran without a failure, the turns, the cost, and the
trial's verdict. Writes ROUND/results.json and prints a table.

The workflow requests (6; and 7, written by hand as the owner's agent did) are graded
for their shape too, on the parts the agent added to the-job: the stock groups no
flow joins (one chain is 1), the stocks nothing fills (a source's first stock is one), the goals' loops and the
groups they make by the stocks they share, and check's chain findings (spec/chains.py). ``--repeat`` runs each
request that many times at once (haiku varies), ``--skill`` gives the agent another SKILL.md (an older one, to
compare), ``--diagrams`` lets it take screenshots of the two diagrams and look at them (scripts/diagram_shots.py, a
port of its own from 8791), ``--empty`` starts from a project with nothing in it instead of the-job (which models
a ramp approval of its own), and ``--grade-only`` grades the folders of a round already run (with this checkout's
code).

Request 8 (``triage``) is an alert triage with a fan-out to three investigation facets and a join, modelled by hand;
every request is also graded for craft (docs/MODELLING-WELL.md): the share of the parts it added that carry a
description, of its stocks with a unit, of its flows between stocks with an equation, its goals and their
tolerances, the tiers of its blocks; the lines between kinds the Process view draws after the stand-in run; and the
rendering audit of its Dynamics and Blocks views (scripts/diagram_audit.py: lines through a part, on top of another,
detours)."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUESTS = [
    ("respond", "Questions for me land in our team's shared help queue. bin/help-queue.sh prints the open ones as JSON "
                "(one object per line, each with an id, a title and who asked). Draft an answer for each new one as it "
                "comes in, into outbox/, and let me know if any question has gone four hours without an answer."),
    ("reping", "When I ask someone for a review of my pull request and they haven't answered within a day, remind "
               "them. Remind at most three times, then hand it back to me so I can chase them in person."),
    ("report", "Every weekday at 8:30 in the morning, write me a short report of what's open right now: the goals "
               "that are off and the items still waiting."),
    ("keep", "Keep the build cache directory (~/.cache/build) under 20 GB. When it goes over, delete the oldest "
             "artifacts until it's back under 15 GB."),
    ("steps", "When a regression ticket arrives from our tracker (https://tracker.example.internal/api/issues?type="
              "regression, a JSON list; the token is in $TRACKER_TOKEN), work it through these steps in order: "
              "label it, find the commit that probably caused it, and draft a revert description into outbox/."),
    ("workflow", "Feature-flag ramp requests come in from our tracker: bin/flag-requests.sh prints the open ones as JSON "
                 "(one per line, each with an id, the flag and who asked). Each request is first researched (what the "
                 "flag touches, who owns that code, how risky it is), then approved by me, then ramped in stages (1%, "
                 "10%, 50%, then 100%, checking the error rate before each next stage), and finally confirmed once it "
                 "has run at 100% for a day. Keep every request moving through this, and tell me when one has waited "
                 "too long at any stage."),
    ("model", "Model our feature-flag ramp approval process in ergostat.yaml, so I can see it in the diagrams and keep "
              "it running: a ramp request arrives from our tracker (bin/flag-requests.sh prints the open ones as JSON), "
              "is researched (what the flag touches, who owns it, the risk), approved by me, ramped in stages (1%, 10%, "
              "50%, 100%, checking the error rate before each next stage) and confirmed once it has run at 100% for a "
              "day. Write the item kind and its stocks, flows, goals and blocks yourself, one per stage, rather than "
              "using a template."),
    ("triage", "Model our alert triage in ergostat.yaml, so I can see it in the three diagrams and keep it running. "
               "Alerts come from our pager: bin/pager-alerts.sh prints the new ones as JSON (one per line, each with an "
               "id, the service and a summary). An AI agent triages each alert: noise is dismissed, the rest go on. "
               "Each alert that goes on is investigated along three lines at once, each its own piece of work done by "
               "an AI agent: the service's logs, its recent deploys, and its metrics. Once all three are done, an AI "
               "agent writes a summary from their findings; most alerts are then closed, but some are escalated to "
               "the on-call engineer (a person), who either handles it or sends it back for more investigation. Write "
               "the item kinds and their stocks, flows, goals and blocks yourself rather than using a template, with "
               "stand-in scripts for each step so it runs here."),
]
HARNESS = ("The owner is away and cannot answer questions: make reasonable assumptions and list them at the end. The "
           "owner has approved turning the result on in this folder (a scratch copy), once it checks and runs.")
DIAGRAMS = ("To see the model's two diagrams as pictures, run `{py} {shots} . shots --port {port}` (add `--system "
            "NAME` for one system): it writes shots/dynamics.png (stock and flow) and shots/blocks.png (control); look "
            "at them with Read.")
PORTS = [8791, 8792, 8793, 8795, 8796, 8797, 8798, 8799]     # 8790 is the owner's; 8794 is often taken
TOOLS = ["mcp__ergostat", "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]


EMPTY = "# The owner's project: nothing in it yet.\nname: flags\n"


def setup(base: Path, n: int, skill_md: Path | None = None, empty: bool = False) -> Path:
    copy = base / f"{n}" / ("flags" if empty else "the-job")
    if copy.parent.exists():
        shutil.rmtree(copy.parent)
    if empty:                                             # a project with nothing in it: the model built from nothing
        copy.mkdir(parents=True)
        (copy / "ergostat.yaml").write_text(EMPTY)
        (copy.parent / "base").mkdir()
        (copy.parent / "base" / "ergostat.yaml").write_text(EMPTY)
    else:
        shutil.copytree(ROOT / "examples" / "the-job", copy, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__"))
    skill = copy / ".claude" / "skills" / "ergostat-author"
    skill.mkdir(parents=True)
    shutil.copy(skill_md or ROOT / "docs" / "skills" / "ergostat-author" / "SKILL.md", skill / "SKILL.md")
    py = ROOT / ".venv" / "bin" / "python"
    (copy.parent / "mcp.json").write_text(json.dumps({"mcpServers": {"ergostat": {
        "command": str(py), "args": ["-m", "ergostat", "-C", str(copy), "mcp"],
        "env": {"ERGOSTAT_HOME": str(copy.parent / "home")}}}}))
    subprocess.run(["git", "init", "-q"], cwd=copy)       # a repository of its own, so nothing reaches the real one
    return copy


def calls(stream: list[dict]) -> list[tuple[str, dict, str]]:
    """(tool, input, result text) in order."""
    pending: dict = {}
    out = []
    for m in stream:
        if m.get("type") == "assistant":
            for c in (m.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    pending[c["id"]] = (c["name"], c.get("input") or {})
        elif m.get("type") == "user":
            for c in (m.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                    body = c.get("content")
                    text = body if isinstance(body, str) else "".join(x.get("text", "") for x in body or [] if isinstance(x, dict))
                    out.append((*pending.pop(c["tool_use_id"]), text))
    return out


def first(cs, name: str):
    return next(((i, r) for t, i, r in cs if t == f"mcp__ergostat__{name}"), None)


def grade(copy: Path, before: set[str]) -> dict:
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "grade-home")}
    chk = subprocess.run([py, "-m", "ergostat", "-C", str(copy), "check"], capture_output=True, text=True, env=env)
    code = ("import json,sys; from pathlib import Path; from ergostat.spec.load import load; "
            "d=load(Path(sys.argv[1])/'ergostat.yaml'); "
            "print(json.dumps({k:{'template':v['template'],'values':v['values'],'standins':v['standins'],'where':str(v['where'])} "
            "for k,v in d.uses.items()}))")
    got = subprocess.run([py, "-c", code, str(copy)], capture_output=True, text=True, env=env)
    uses = json.loads(got.stdout or "{}") if got.returncode == 0 else {}
    new = {k: v for k, v in uses.items() if k not in before}
    trials = {}
    for inst in new:
        for how, standins in (("as_written", False), ("on_stand_ins", True)):
            t = subprocess.run([py, "-c", "import json,sys; from pathlib import Path; from ergostat.library import author; "
                                "r=author.trial(Path(sys.argv[1]), sys.argv[2], seconds=30, standins=sys.argv[3]=='1'); "
                                "print(json.dumps({'verdict': r.get('verdict'), 'check': r.get('check'), 'error': r.get('error')}))",
                                str(copy), inst, "1" if standins else "0"], capture_output=True, text=True, env=env, timeout=400)
            try:
                trials.setdefault(inst, {})[how] = json.loads(t.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                trials.setdefault(inst, {})[how] = {"error": (t.stderr or t.stdout)[-800:]}
    return {"check_ok": chk.returncode == 0, "check": chk.stdout.strip().splitlines()[:1] + [
                x for x in chk.stdout.splitlines() if x.startswith("error")][:8],
            "uses": new, "trials": trials}


SHAPE = r"""
import json, sys
from pathlib import Path
from ergostat.spec import read, chains
base, _ = read(Path(sys.argv[2]) / "ergostat.yaml")
spec, problems = read(Path(sys.argv[1]) / "ergostat.yaml")
if any(p.level == "error" for p in problems):
    print(json.dumps({"error": [str(p) for p in problems if p.level == "error"][:3]})); sys.exit()
new = [s for s in spec.stocks if s not in base.stocks]
parent = {s: s for s in new}
def root(x):
    while parent[x] != x:
        x = parent[x]
    return x
for f in spec.flows.values():
    if f.source in parent and f.target in parent:
        parent[root(f.source)] = root(f.target)
groups = {}
for s in new:
    groups.setdefault(root(s), []).append(s)
no_in = [s for s in new if not any(f.target == s for f in spec.flows.values())]
goals = [g for n, g in spec.goals.items() if n not in base.goals and g.of.kind == "stock"]
sets = {}
for g in goals:
    mine = {g.of.name}
    for a in spec.loop(g.name).actuators:
        for r in spec.blocks[a].targets():
            f = spec.flows.get(r.name) if r.kind == "flow" else None
            if f is not None:
                mine |= {x for x in (f.source, f.target) if x}
    sets[g.name] = mine
lp = {n: n for n in sets}
def lroot(x):
    while lp[x] != x:
        x = lp[x]
    return x
names = list(sets)
for i, a in enumerate(names):
    for b in names[i + 1:]:
        if sets[a] & sets[b]:
            lp[lroot(a)] = lroot(b)
lg = {}
for n in names:
    lg.setdefault(lroot(n), []).append(n)
found = [x for x in problems if x.code in ("outflow-not-chained", "inflow-not-chained", "state-stock-without-inflow",
                                           "move-without-flow", "state-stocks-disconnected", "loops-not-connected",
                                           "chain-stock-not-a-count")]
print(json.dumps({"stocks": len(new), "stock_groups": len(groups), "groups": sorted(groups.values(), key=len, reverse=True),
                  "no_inflow": no_in, "loops": len(goals), "loop_groups": len(lg),
                  "loops_closed": sum(1 for g in goals if spec.loop(g.name).closes),
                  "loops_connected": sum(len(g) for g in lg.values() if len(g) > 1),
                  "chain_findings": [f"{x.code}@{x.about}" for x in found],
                  "kinds": [k for k in spec.items if k not in base.items and not k.startswith("ergostat.")]}))
"""


def shape(copy: Path) -> dict:
    """The parts the agent added, as one chain or many (with this checkout's code)."""
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "grade-home")}
    base = copy.parent / "base" if (copy.parent / "base").exists() else ROOT / "examples" / "the-job"
    got = subprocess.run([py, "-c", SHAPE, str(copy), str(base)], capture_output=True, text=True,
                         env=env, timeout=300)
    try:
        return json.loads(got.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": (got.stderr or got.stdout)[-600:]}


COHERENT = r"""
import json, sys, time
from pathlib import Path
from ergostat import coherence as co, model as mdl, process as pm
from ergostat.spec import read
from ergostat.store import Project
base, _ = read(Path(sys.argv[2]) / "ergostat.yaml")
p = Project(mdl.load(Path(sys.argv[1])))
got = co.of_project(p, p.model.spec)
mine = {k: x for k, x in got["kinds"].items() if k not in base.items and not k.startswith("ergostat.")}
kinds = [k for k in p.model.spec.items if k not in base.items and not k.startswith("ergostat.")]
cross = []
if kinds:
    m = pm.process(p.events, p.model.spec, kinds, time.time() - 3600, time.time())
    cross = [f"{e['causeKind']}:{e['from']}>{e['itemKind']}:{e['to']} x{e['count']}" for e in m["edges"]
             if e["kind"] == "caused"]
print(json.dumps({"scores": [co.score_line(k, x) for k, x in mine.items()],
                  "agree": sum(x["agree"] for x in mine.values()), "compared": sum(x["compared"] for x in mine.values()),
                  "mismatches": [f["id"] for f in got["findings"] if f["level"] == "mismatch" and f["kind"] in mine],
                  "cross_kind": cross}))
"""


CRAFT = r"""
import json, sys
from pathlib import Path
from ergostat.spec import read
base, _ = read(Path(sys.argv[2]) / "ergostat.yaml")
spec, problems = read(Path(sys.argv[1]) / "ergostat.yaml")
if any(p.level == "error" for p in problems):
    print(json.dumps({"error": "check fails"})); sys.exit()
def new(d, old):
    return {k: v for k, v in d.items() if k not in old and not k.startswith("ergostat")}
st, fl = new(spec.stocks, base.stocks), new(spec.flows, base.flows)
au, go, bl = new(spec.auxiliaries, base.auxiliaries), new(spec.goals, base.goals), new(spec.blocks, base.blocks)
bl = {k: b for k, b in bl.items() if not getattr(b, "implied", False) and not k.startswith("keep-")}
parts = [*st.values(), *fl.values(), *au.values(), *go.values(), *bl.values()]
def share(xs, ok):
    xs = list(xs)
    return f"{sum(1 for x in xs if ok(x))}/{len(xs)}"
print(json.dumps({
    "described": share(parts, lambda x: bool(getattr(x, "description", None))),
    "units": share(st.values(), lambda x: bool(getattr(x, "unit", None))),
    "flow_equations": share([f for f in fl.values() if f.source], lambda x: bool(getattr(x, "equation", None))),
    "goals": len(go), "goals_with_tolerance": share(go.values(), lambda g: bool(getattr(g, "tolerance", 0))),
    "tiers": sorted({b.type for b in bl.values()}),
    "kinds": len(new(spec.items, base.items)),
}))
"""


def craft(copy: Path) -> dict:
    """What a professional would look for beyond correctness, on the parts the agent added: descriptions, units,
    equations, goals' tolerances, the tiers its blocks are on, and the kinds it declared."""
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "grade-home")}
    base = copy.parent / "base" if (copy.parent / "base").exists() else ROOT / "examples" / "the-job"
    got = subprocess.run([py, "-c", CRAFT, str(copy), str(base)], capture_output=True, text=True, env=env, timeout=300)
    try:
        return json.loads(got.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": (got.stderr or got.stdout)[-600:]}


def audit(copy: Path, port: int) -> dict:
    """The rendering audit of the Dynamics and Blocks views (lines through a part, lines on top of another, detours):
    none now. scripts/diagram_audit.py measured the old page, removed when the React page became the page; the grade
    says so instead of a number."""
    return {"error": "no rendering audit: scripts/diagram_audit.py measured the old page, which is gone"}


def coherent(copy: Path, seconds: float = 40) -> dict:
    """The coherence of the kinds the agent added (coherence.py), after the copy has run on its stand-ins for a while."""
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "grade-home")}
    base = copy.parent / "base" if (copy.parent / "base").exists() else ROOT / "examples" / "the-job"
    if subprocess.run([py, "-m", "ergostat", "-C", str(copy), "run", "--no-web"], capture_output=True, env=env,
                      timeout=120).returncode != 0:
        return {"error": "it does not run"}
    try:
        time.sleep(seconds)
    finally:
        subprocess.run([py, "-m", "ergostat", "-C", str(copy), "run", "--stop"], capture_output=True, env=env, timeout=120)
    got = subprocess.run([py, "-c", COHERENT, str(copy), str(base)], capture_output=True, text=True, env=env, timeout=300)
    try:
        return json.loads(got.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": (got.stderr or got.stdout)[-600:]}


def run_one(base: Path, n: int, model: str, timeout: float, skill_md: Path | None = None, diagrams: bool = False,
            r: int = 0, port: int = 8791, empty: bool = False) -> dict:
    key, text = REQUESTS[n - 1]
    copy = setup(base / f"r{r}", n, skill_md, empty)
    began = time.time()
    harness = HARNESS + (" " + DIAGRAMS.format(py=sys.executable, shots=ROOT / "scripts" / "diagram_shots.py",
                                               port=port) if diagrams else "")
    cmd = ["claude", "-p", text, "--model", model, "--mcp-config", str(copy.parent / "mcp.json"), "--strict-mcp-config",
           "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
           "--allowedTools", *TOOLS, "--append-system-prompt", harness, "--max-turns", "80"]
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "home")}
    try:
        p = subprocess.run(cmd, cwd=copy, capture_output=True, text=True, timeout=timeout, env=env)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    stream = []
    for line in out.splitlines():
        try:
            stream.append(json.loads(line))
        except ValueError:
            pass
    (copy.parent / "transcript.jsonl").write_text(out)
    result = next((m for m in reversed(stream) if m.get("type") == "result"), {})
    cs = calls(stream)
    fa, ft = first(cs, "add_use"), first(cs, "try_use")

    def ok_add(r):
        try:
            return json.loads(r)["ok"]
        except (ValueError, KeyError, TypeError):
            return False

    def ok_try(r):
        try:
            d = json.loads(r)
        except (ValueError, TypeError):
            return False
        ran = d.get("ran")
        return bool(d.get("check", {}).get("ok")) and isinstance(ran, dict) and not ran.get("sensor_failures") and \
            not any(b.get("failed") for b in ran.get("blocks", {}).values()) and bool(ran.get("items") or ran.get("stocks"))
    skill_used = any(t == "Skill" for t, _, _ in cs) or any("ergostat-author" in json.dumps(i) for t, i, _ in cs if t == "Read")
    graded = grade(copy, set())
    looked = any(t == "Read" and str(i.get("file_path", "")).endswith(".png") for t, i, _ in cs)
    return {"n": n, "r": r, "request": key, "shape": shape(copy), "looked_at_diagrams": looked,
            "where_drawn": any(t == "mcp__ergostat__where_drawn" for t, _, _ in cs),
            "coherence_called": any(t == "mcp__ergostat__coherence" for t, _, _ in cs),
            "coherence": coherent(copy) if graded["check_ok"] else {"error": "check fails"},
            "craft": craft(copy), "audit": audit(copy, port) if graded["check_ok"] else {"error": "check fails"},
            "seconds": round(time.time() - began), "turns": result.get("num_turns"),
            "cost_usd": result.get("total_cost_usd"), "stopped": result.get("subtype"), "skill_used": skill_used,
            "tools": [t.replace("mcp__ergostat__", "") for t, _, _ in cs],
            "first_add_ok": ok_add(fa[1]) if fa else None, "first_try_ok": ok_try(ft[1]) if ft else None,
            "first_add": fa[0] if fa else None, "final_text": (result.get("result") or "")[-1500:], **graded,
            "folder": str(copy)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("round")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--only")
    ap.add_argument("--out", default="/tmp/ergostat-bench")
    ap.add_argument("--timeout", type=float, default=1500)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--skill")
    ap.add_argument("--diagrams", action="store_true")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--empty", action="store_true")
    ap.add_argument("--ports", help="the ports its jobs' pages may use, joined by commas (default: 8791-8799 but 8794)")
    a = ap.parse_args()
    ports = [int(x) for x in a.ports.split(",")] if a.ports else PORTS
    base = Path(a.out) / a.round
    base.mkdir(parents=True, exist_ok=True)
    which = [int(x) for x in a.only.split(",")] if a.only else list(range(1, len(REQUESTS) + 1))
    if a.grade_only:
        got = json.loads((base / "results.json").read_text())
        for r in got:
            r["shape"] = shape(Path(r["folder"]))
        (base / "results.json").write_text(json.dumps(got, indent=1, default=str))
        print_shapes(got)
        print_craft(got)
        return 0
    jobs = [(n, r) for r in range(a.repeat) for n in which]
    skill_md = Path(a.skill).resolve() if a.skill else None
    with cf.ThreadPoolExecutor(len(jobs)) as ex:
        got = list(ex.map(lambda j: run_one(base, j[0], a.model, a.timeout, skill_md, a.diagrams, j[1],
                                            ports[jobs.index(j) % len(ports)], a.empty), jobs))
    (base / "results.json").write_text(json.dumps(got, indent=1, default=str))
    print(f"{'#':<3}{'request':<9}{'skill':<7}{'add 1st':<9}{'try 1st':<9}{'check':<7}{'written':<18}{'runs':<6}{'stand-ins':<10}"
          f"{'turns':<7}{'cost':<8}")

    def runs(t: dict) -> bool:
        return bool(t) and not t.get("error") and t.get("check", {}).get("ok") and \
            not any("failed" in v for v in t.get("verdict") or [])
    for r in got:
        ts = r["trials"].values()
        print(f"{r['n']:<3}{r['request']:<9}{str(r['skill_used']):<7}{str(r['first_add_ok']):<9}{str(r['first_try_ok']):<9}"
              f"{str(r['check_ok']):<7}{','.join(r['uses']) or '-':<18}{str(bool(ts) and all(runs(t.get('as_written')) for t in ts)):<6}"
              f"{str(bool(ts) and all(runs(t.get('on_stand_ins')) for t in ts)):<10}{str(r['turns']):<7}{(r['cost_usd'] or 0):<8.3f}")
    print_shapes(got)
    print_craft(got)
    return 0


def print_craft(got: list[dict]) -> None:
    print(f"\n{'#':<3}{'run':<5}{'request':<10}{'described':<11}{'units':<7}{'flow eqs':<10}{'goals':<6}{'tolerance':<11}"
          f"{'tiers':<22}{'cross-kind':<12}{'audit (through/overlap/detour)':<32}{'cost'}")
    for r in got:
        c, co, au = r.get("craft") or {}, r.get("coherence") or {}, r.get("audit") or {}
        a = " ".join(f"{v[:3]} {x['through']}/{x['overlap']}/{x['detour']}" for v, x in au.items() if isinstance(x, dict))
        print(f"{r['n']:<3}{r.get('r', 0):<5}{r['request']:<10}{c.get('described', '-'):<11}{c.get('units', '-'):<7}"
              f"{c.get('flow_equations', '-'):<10}{str(c.get('goals', '-')):<6}{c.get('goals_with_tolerance', '-'):<11}"
              f"{','.join(c.get('tiers') or []):<22}{len(co.get('cross_kind') or []):<12}{a or str(au.get('error', '-'))[:30]:<32}"
              f"{(r.get('cost_usd') or 0):.2f}")


def print_shapes(got: list[dict]) -> None:
    print(f"\n{'#':<3}{'run':<5}{'request':<10}{'stocks':<8}{'groups':<8}{'no inflow':<11}{'loops':<7}{'loop groups':<13}"
          f"{'connected':<11}{'closed':<8}{'chain findings':<16}{'where_drawn':<13}{'looked':<8}{'coherence'}")
    for r in got:
        s = r.get("shape") or {}
        if s.get("error"):
            print(f"{r['n']:<3}{r.get('r', 0):<5}{r['request']:<10}error: {str(s['error'])[:120]}")
            continue
        print(f"{r['n']:<3}{r.get('r', 0):<5}{r['request']:<10}{s.get('stocks', 0):<8}{s.get('stock_groups', 0):<8}"
              f"{len(s.get('no_inflow') or []):<11}{s.get('loops', 0):<7}{s.get('loop_groups', 0):<13}"
              f"{s.get('loops_connected', 0):<11}{s.get('loops_closed', 0):<8}"
              f"{len(s.get('chain_findings') or []):<16}{str(r.get('where_drawn')):<13}"
              f"{str(r.get('looked_at_diagrams')):<8}{_coh(r.get('coherence'))}")


def _coh(c: dict | None) -> str:
    if not c:
        return "-"
    if c.get("error"):
        return c["error"][:40]
    return f"{c['agree']}/{c['compared']}" + (f" {len(c['mismatches'])} mismatched" if c["mismatches"] else "")


if __name__ == "__main__":
    sys.exit(main())
