"""ergostat on ergostat: the factory's model at the repository's root, and its programs (dev/bin/), run against a
fixture repository with the free stand-ins (no AI, no push). docs/roadmap/overnight/factory.md names these tests.

The engine is played by a small harness: each program is run as ergostat runs a block that takes an item (its input on
standard input, the item's environment, $ERGOSTAT_CMD), and the event lines it prints are folded into the record by
the kinds the root model declares, so a line the model does not know fails here."""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import textwrap
import threading
import time
import tomllib
from pathlib import Path

import pytest

from ergostat.spec import read

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
# What the queue sets in its suite containers (fac.suite, agents.queued): never inherited by the factory's processes the
# Factory fixture starts (dropped, or set by it), so a test of the queue reads the same settings inside the queue's own
# container as outside it
QUEUE_ENV = ("PYTEST_ADDOPTS", "UV_PROJECT_ENVIRONMENT", "PYTHONPYCACHEPREFIX", "RUFF_CACHE_DIR", "SPLIT_SHOTS")

FAKE = r'''
import json, sys
from pathlib import Path
rec = Path(__file__).with_name("record.json")
db = json.loads(rec.read_text())
args = sys.argv[1:]
if args[0] == "item" and "--kind" in args:
    kind = args[args.index("--kind") + 1]
    state = args[args.index("--state") + 1] if "--state" in args else None
    got = [i for i in db["items"].values() if i["kind"] == kind and (state is None or i["state"] == state)]
    print(json.dumps({"items": got, "total": len(got)}))
elif args[0] == "act":
    db.setdefault("acts", []).append(args)
    import fcntl, os                                               # (whether the queue's lock is held while it asks)
    if os.environ.get("FAKE_PROBE_LOCK"):
        with open(os.environ["FAKE_PROBE_LOCK"], "a") as lk:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                db["lock_held_at_act"] = False
            except BlockingIOError:
                db["lock_held_at_act"] = True
    reply = db.get("act_reply") or {"rc": 3, "id": True}          # (as gated.py answers: held, with its id)
    aid = "ergostat.action/" + format(len(db["acts"]), "010x")
    db.setdefault("actions", {})[aid] = {3: "held", 4: "denied", 1: "failed", 0: "ran"}.get(reply["rc"], "refused")
    rec.write_text(json.dumps(db))
    print(f"{args[1]}: " + (f"({aid}) " if reply["id"] else "") + "x" * reply.get("noise", 0), file=sys.stderr)
    sys.exit(reply["rc"])
elif args[0] == "item" and "/" in args[1]:
    if args[1] in db["items"]:
        print(json.dumps(db["items"][args[1]]))
    elif args[1] in db.get("actions", {}):
        print(json.dumps({"id": args[1], "state": db["actions"][args[1]]}))
    else:
        sys.exit(f"no item {args[1]}")
elif args[0] == "event" and args[1] == "--add" and args[args.index("--item") + 1].startswith("flake/"):
    import os, types                                               # (dev/bin/flakes.py: folded at once, as ergostat does)
    sys.path[:0] = [os.environ["FAKE_ROOT"]]
    from tests.test_factory import fold_line
    line = {"event": args[2], "item": args[args.index("--item") + 1]}
    line.update({f: json.loads(args[args.index(f"--{f}") + 1]) for f in ("data", "patch") if f"--{f}" in args})
    fold_line(db, {"flake": types.SimpleNamespace(**json.loads(os.environ["FAKE_FLAKE_KIND"]))}, line)
    db.setdefault("flakes_said", []).append(args[2])
    rec.write_text(json.dumps(db))
elif args[0] == "lease":
    if "--nack" in args:                                           # (a lease given back, as its run would)
        import os
        db.setdefault("nacks", []).append({k: os.environ.get(f"ERGOSTAT_{k.upper()}") for k in ("item", "lease", "run")}
                                          | {"count": "--no-count" not in args})
        rec.write_text(json.dumps(db))
elif args[0] == "actions" and "--deny" in args:
    db["actions"][args[1]] = "denied"
    db.setdefault("notes", {})[args[1]] = args[args.index("--note") + 1]
    rec.write_text(json.dumps(db))
else:
    sys.exit(f"the fake ergostat does not know {args}")
'''

CHECK = r'''
import json, pathlib, sys
d = pathlib.Path("found")                       # (`ergostat check` played: each file found/CODE@PART is a finding)
names = sorted(p.name for p in d.iterdir()) if d.is_dir() else []
if "broken" in names:
    sys.exit("Traceback (most recent call last): the check crashed")
print("Resolved 3 packages in 1ms {not json}")
print(json.dumps({"ok": True, "errors": 0, "found": [{"level": "finding", "code": n.split("@")[0],
                  "about": n.split("@")[1] if "@" in n else None} for n in names]}, indent=2))
'''


def git(repo: Path, *args: str) -> str:
    """git in a fixture repository, with an identity of its own: a machine with no global git config (the dev
    container, the factory's suite containers) can still commit."""
    who = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    return subprocess.run(["git", "-C", str(repo), *who, *args], check=True, capture_output=True, text=True).stdout.strip()


GAPS = """\
# Known gaps

## Modelling

- **Alpha thing** (open; the first gap): what it lacks.
  More of it.
- **Beta** (done, abc1234): landed.
- **Delta** (parked on `delta`, *Where it stopped*): stopped.

## Done recently

- **Gamma**: done.
"""


class Factory:
    """A fixture: an origin, its checkout with a GAPS.md, the factory's settings, a model folder, a fake ergostat."""

    GATES = {"kill_after": 3, "build_failures": 2, "build_hours": 4.0}   # the kill rule's numbers, read by the tests

    def __init__(self, tmp: Path, unit: str = "true", alone: str = "true", **gates):
        self.tmp = tmp
        self.gates = {**self.GATES, **gates}
        self.origin, self.checkout = tmp / "origin.git", tmp / "checkout"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.checkout)], check=True, capture_output=True)
        (self.checkout / "docs" / "roadmap" / "overnight").mkdir(parents=True)
        (self.checkout / "docs" / "GAPS.md").write_text(GAPS)
        (self.checkout / "app.py").write_text("print('hello')\n")
        git(self.checkout, "checkout", "-q", "-b", "main")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "start")
        git(self.checkout, "push", "-q", "origin", "main")
        self.model = tmp / "instance"
        self.model.mkdir()
        (self.model / "dev").symlink_to(ROOT / "dev")
        self.config = tmp / "factory.toml"
        self.config.write_text(textwrap.dedent(f"""\
            [paths]
            checkout = "{self.checkout}"
            worktrees = "{tmp / 'wt'}"
            live = "{tmp / 'live'}"
            queue_lock = "{tmp / 'queue.lock'}"
            run = "run"
            [gates]
            kill_after = {self.gates["kill_after"]}
            build_failures = {self.gates["build_failures"]}
            build_hours = {self.gates["build_hours"]}
            [git]
            base = "main"
            remote = "origin"
            [ai]
            mode = "standin"
            implementor_model = "opus"
            reviewer_model = "opus"
            implementor_session_usd = 1.0
            reviewer_session_usd = 1.0
            suite_fix_rounds = 0
            [pools]
            implementor_max = 4
            reviewer_max = 2
            probation = 3
            batch_max = 4
            [instance]
            port = 0
            [load]
            threads = 1500
            memory_gb = 6.0
            wait_poll = 0.2
            wait = false                       # (other suites on this machine would hold the tests)
            [suites]
            ruff = "true"
            unit = "{unit}"
            browser = "true"
            browser_ready = "true"
            demo = "true"
            rerun = "echo again {{tests}}"
            alone = "{alone} {{tests}}"
            queue_container = false            # (tests/test_agents.py runs the queue's in a fake Docker)
            check = "{sys.executable} {tmp / 'fake_check.py'}"
            """))
        (tmp / "fake_check.py").write_text(CHECK)
        self.fake = tmp / "fake_ergostat.py"
        self.fake.write_text(FAKE)
        self.record = tmp / "record.json"
        self.record.write_text(json.dumps({"items": {}}))
        spec, problems = read(ROOT / "ergostat.yaml")
        assert not [p for p in problems if p.level == "error"]
        self.kinds = spec.items
        mine = {k: v for k, v in os.environ.items() if k not in QUEUE_ENV}       # (never the queue container's)
        caches = {"UV_PROJECT_ENVIRONMENT": sys.prefix, "PYTHONPYCACHEPREFIX": str(tmp / "pycache"),
                  "RUFF_CACHE_DIR": str(tmp / "ruff")}               # set here: the running venv, caches out of checkouts
        self.env = {**mine, **caches, "FACTORY_CONFIG": str(self.config), "ERGOSTAT_CMD": f"{sys.executable} {self.fake}",
                    "FAKE_ROOT": str(ROOT), "FAKE_FLAKE_KIND": json.dumps({k: getattr(self.kinds["flake"], k) for k in (
                        "name", "id", "states", "on", "fold", "relations")}),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@example.com"}

    def db(self) -> dict:
        return json.loads(self.record.read_text())

    def item(self, iid: str) -> dict:
        return self.db()["items"][iid]

    def fold(self, lines: list[dict], about: str | None) -> list[str]:
        """The event lines into the record, by the root model's kinds; the event types, in order (but a session item's,
        test_factory_sessions.py)."""
        db, said = self.db(), []
        for line in lines:
            if "event" not in line:
                continue
            fold_line(db, self.kinds, line, about)
            if not line["event"].startswith(("session.", "batch.")):   # (each AI session's own item: sessions.py; each
                said.append(line["event"])                              # queue batch's: batches.py)
        self.record.write_text(json.dumps(db))
        return said

    def run(self, program: str, iid: str | None = None, argv: tuple = (), lease: dict | None = None, fails: bool = False,
            timeout: float = 120, **env) -> tuple[list[str], list[dict]]:
        """A run of a block: (the events it said, every JSON line it printed). ``lease``: more of its lease (its
        attempt); ``fails``: it is expected to exit non-zero (a counted attempt)."""
        it = self.item(iid) if iid else None
        given = {"trigger": "item", "item": it,
                 "lease": {"fence": 1, "back": it["state"], **(lease or {})} if it else None}
        r = subprocess.run([sys.executable, str(BIN / program), *argv], input=json.dumps(given), cwd=self.model,
                           capture_output=True, text=True, timeout=timeout,
                           env={**self.env, **({"ERGOSTAT_ITEM": iid, "ERGOSTAT_LEASE": "1"} if iid else {}), **env})
        assert (r.returncode != 0) == fails, r.stderr
        self.stderr = r.stderr
        lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        return self.fold(lines, iid), lines

    def flakes_said(self) -> list[str]:
        """The flake events written at once (dev/bin/flakes.py, `event --add`) since last asked, in order."""
        db = self.db()
        got = db.pop("flakes_said", [])
        self.record.write_text(json.dumps(db))
        return got


def fold_line(db: dict, kinds: dict, line: dict, about: str | None = None) -> None:
    """One event line into the record ``db``, by ``kinds`` (its data by their fold rules, or a patch of top-level
    fields), and its state moved: the fixture's fold, and the fake ergostat's for `event --add`."""
    iid = line.get("item") or about
    kind = next(k for k in kinds.values() if Path(iid).match(k.id) or iid.startswith(k.id[:-1]))
    assert line["event"] in kind.on or line["event"].endswith((".measured", ".push-asked", ".switch-asked", ".pushed",
                                                                ".dependencies", ".push-settled", ".groomed",
                                                                ".resumed", ".need-met", ".released",
                                                                ".reverted", ".stage-started", ".stage-finished")), line
    it = db["items"].setdefault(iid, {"id": iid, "kind": kind.name, "state": kind.states[0], "fields": {}})
    for op in line.get("patch") or []:                             # (RFC 6902, as flakes.py writes it: top level)
        k = op["path"][1:].replace("~1", "/").replace("~0", "~")
        if op["op"] == "remove":
            del it["fields"][k]                                    # (a missing field refuses the event: a KeyError)
        else:
            it["fields"][k] = op["value"]
    for k, v in (line.get("data") or {}).items():
        rule = "relation" if k in kind.relations else kind.fold.get(k, "replace")
        was = it["fields"].get(k)
        if rule == "relation":                                     # (SPEC 5a: a set of ids, or set/add/remove)
            got = set(was or [])
            if isinstance(v, dict):
                got = set(v.get("set", got)) | set([v["add"]] if isinstance(v.get("add"), str) else
                                                    v.get("add") or []) - set(v.get("remove") or [])
            else:
                got |= set([v] if isinstance(v, str) else v)
            it["fields"][k] = sorted(got)
        elif rule == "sum":
            it["fields"][k] = (was or 0) + v
        elif rule == "append":
            it["fields"][k] = (was or []) + (v if isinstance(v, list) else [v])
        elif rule == "union":
            it["fields"][k] = sorted(set(was or []) | set(v if isinstance(v, list) else [v]))
        else:
            it["fields"][k] = v
    if line["event"] in kind.on:
        it["state"] = kind.on[line["event"]]


def module(name: str):
    spec = importlib.util.spec_from_file_location(f"factory_{name}", BIN / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_factory_model_loads():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    assert {"gap", "review", "flake", "intervention", "upgrade"} <= set(spec.items)
    assert {"intake", "implementor", "reviewer", "merge-queue", "flake-triage", "upgrader"} <= set(spec.blocks)
    assert {"ai-budget", "machine-quiet", "first-pass-good", "suites-in-time"} <= set(spec.goals)
    assert {"sessions-fit", "cpu-within", "memory-within", "disk-free-enough", "factory-disk-within"} <= set(spec.goals)
    assert {"machine-full", "disk-cleanup"} <= set(spec.blocks)
    assert spec.blocks["implementor"].takes.at == ["fix", "ready"] and spec.blocks["implementor"].pool == 9
    assert {"implementor-pool", "reviewer-pool"} <= set(spec.stocks) and "raise-pool" in spec.actions
    assert {"factory-interventions", "escapes"} <= set(spec.stocks) and "risk-tolerance" in spec.parameters
    assert {"pool-risk", "pool-risk-bound", "pool-target"} <= set(spec.auxiliaries)        # the pools' loop
    assert [str(p) for p in problems if "pools.yaml" in str(p.where)] == []
    assert spec.blocks["merge-queue"].pool == 1
    assert set(spec.items["upgrade"].states) >= {"installed", "switched", "healthy", "reverted"}


def without_landed(text: str) -> str:
    """A model file as main had it before gaps-landed-stock: no stock gaps-landed (its block, whatever it holds),
    gaps-merged and joins-covered to clouds, gaps-merged counting every gap entering merged."""
    import re
    return re.sub(r"(?m)^  gaps-landed:\n(?:    .*\n)*", "", text).replace("    to: gaps-landed\n", "").replace(
        "entering: merged, where: {merged_by: null}, over: 1d", "entering: merged, over: 1d")


def without_stack_forward(text: str) -> str:
    """A model file as main had it before merge-pipeline-stacks-merged-forward: no block stack-forward, nor its
    sensor stale-stacks, its gate stack-forward-when or its flow sent-back-by-stack-forward."""
    return re.sub(r"(?m)^  (?:stack-forward|stale-stacks|stack-forward-when|sent-back-by-stack-forward):\n(?:    .*\n)*",
                  "", text)


def without_stacking(text: str) -> str:
    """A model file (or ergostat.yaml) as main had it before merge-pipeline-stacks-turned-on: no gaps-stacked,
    depends_on finish-to-start."""
    return re.sub(r"(?m)^  gaps-stacked:\n(?:    .*\n)*", "", text).replace(
        "depends_on: {kind: gap, starts_at: [approved, queued, push-pending]}", "depends_on: gap")


def factory_copy(where: Path, edit=lambda text: text) -> Path:
    """The factory's model in a folder of its own, each model file (and ergostat.yaml) passed through ``edit``."""
    (where / "dev" / "model").mkdir(parents=True)
    for x in (ROOT / "dev").iterdir():
        if x.name != "model":
            (where / "dev" / x.name).symlink_to(x)
    for x in (ROOT / "dev" / "model").iterdir():
        (where / "dev" / "model" / x.name).write_text(edit(x.read_text()))
    (where / "ergostat.yaml").write_text(edit((ROOT / "ergostat.yaml").read_text()))
    return where


def test_the_factory_model_loads_with_gaps_landed_and_the_flows_into_it():
    """gaps-landed-stock: a stock of the gaps merged on main, filled by every flow that ends a gap in merged (the
    queue's, and the join judge's), drained by none, and read by no goal, pool or gate."""
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    st = spec.stocks["gaps-landed"]
    assert st.unit == "gaps" and st.system == "landing" and "merged on main" in st.description
    (sensor,) = st.sensors.values()
    assert sensor.items["kind"] == "gap" and sensor.items["state"] == ["merged"] and sensor.every == 60
    into = {f.name for f in spec.flows.values() if f.target == "gaps-landed"}
    assert into == {"gaps-merged", "joins-covered"}
    assert not [f.name for f in spec.flows.values() if f.source == "gaps-landed"]           # it only rises
    ends_merged = {f.name for f in spec.flows.values() for s in f.sensors.values()
                   if s.items and s.items.get("kind") == "gap" and s.items.get("entering") == "merged"}
    assert ends_merged == into                                   # every flow ending a gap in merged goes to it
    gm = spec.flows["gaps-merged"]
    assert gm.source == "gaps-queued" and gm.equation.text == \
        "(1 - queue-fail-share - conflict-share) * stock.gaps-queued / queue-time"
    assert not [g.name for g in spec.goals.values() if g.of.name == "gaps-landed"]          # no goal on it
    texts = "".join(x.read_text() for x in (ROOT / "dev" / "model").iterdir()) + (ROOT / "ergostat.yaml").read_text()
    assert texts.count("stock.gaps-landed") == 0                 # nothing reads it: no pool, gate or equation
    assert spec.flows["upgrades-opened"].equation.text == "upgrades-per-merge * flow.gaps-merged"


def test_a_joined_gap_that_lands_enters_the_landed_stock_once(tmp_path):
    """gaps-landed-stock: a gap the queue merged is counted by gaps-merged alone, a joined gap the join judge found
    covered (merged_by join-judge, plan.py) by joins-covered alone, so the inflows' count is the stock's rise."""
    from ergostat import model as mdl
    from ergostat.spec import items as its
    from ergostat.store import Project
    m = mdl.load(factory_copy(tmp_path / "m"))
    (tmp_path / "state").mkdir()
    p = Project(m, directory=tmp_path / "state")
    ev, spec = p.events, m.spec
    t = time.time() - 3600
    for g in ("sub-a", "sub-b"):                                 # the queue's merges: the joined gap's sub-gaps
        for k, e in enumerate(("gap.found", "gap.defined", "gap.started", "gap.built", "gap.review-started",
                               "gap.approved", "gap.queued", "gap.merged")):
            ev.add(e, item=f"gap/{g}", data={"parent": ["gap/whole"]} if k == 0 else {}, at=t + k)
    ev.add("gap.found", item="gap/whole", at=t)
    ev.add("gap.split", item="gap/whole", data={"children": ["gap/sub-a", "gap/sub-b"]}, at=t + 1)
    ev.add("gap.merged", item="gap/whole", data={"merged_by": "join-judge", "join_verdict": "covered"}, at=t + 20)
    now = t + 30

    def reading(part) -> float:
        (s,) = part.sensors.values()
        v, _ = its.measure(ev, spec, s, now=now)
        return v
    day = 86400 / 3600                                           # (a flow's reading is per hour, over a day)
    merged, covered = reading(spec.flows["gaps-merged"]) * day, reading(spec.flows["joins-covered"]) * day
    assert (round(merged), round(covered)) == (2, 1)            # the joined gap in joins-covered alone
    assert reading(spec.stocks["gaps-landed"]) == 3 == round(merged + covered)


@pytest.mark.slow
def test_ergostat_check_on_the_factory_model_reports_no_new_finding(tmp_path, capsys, monkeypatch):
    """gaps-landed-stock: `ergostat check` on the model with gaps-landed says nothing it did not say without it, and
    the Dynamics diagram draws the stock with the pipes into it. merge-pipeline-stacks-merged-forward: nor with the
    block stack-forward and its sensor, goal and flow (removed from the model checked before, too).
    merge-pipeline-stacks-turned-on: nor with depends_on's starts_at and the auxiliary gaps-stacked, which the
    Dynamics diagram draws."""
    from ergostat import model as mdl
    from ergostat.cli import main, spec_cmds
    from ergostat.numbers import extremes_cache
    from ergostat.store import Project
    from ergostat.web.server import Live, api
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # (no extremes kept from another test's run)
    monkeypatch.setattr(spec_cmds, "CHECK_WAIT", None)                # both sides' extreme-conditions tests run whole
    monkeypatch.setattr(extremes_cache, "BOUND", 900.0)

    def found(where: Path) -> set[str]:
        main(["-C", str(where), "check", "--json"])
        got = json.loads(capsys.readouterr().out)
        assert got["ok"], [x for x in got["found"] if x["level"] == "error"]
        return {x["id"] for x in got["found"] if x["level"] != "error"}
    before = factory_copy(tmp_path / "before", lambda t: without_stacking(without_stack_forward(without_landed(t))))
    old = "".join(x.read_text() for x in (before / "dev" / "model").iterdir())
    assert "\n  gaps-landed:" not in old and "to: gaps-landed" not in old and "merged_by: null" not in old
    assert "stack-forward" not in old and "stale-stacks" not in old and "gaps-stacked" not in old
    assert "      depends_on: gap\n" in (before / "ergostat.yaml").read_text()
    now = found(factory_copy(tmp_path / "now"))
    assert not [x for x in now if x.startswith(("extremes-running", "extremes-skipped"))]
    assert sorted(now - found(before)) == []
    (tmp_path / "state").mkdir()
    live = Live(Project(mdl.load(tmp_path / "now"), directory=tmp_path / "state"))
    g = api(live, "graph", {"view": ["dynamics"], "open": ["*"]})
    ids = {n["id"] for n in g["nodes"]}
    assert "stock:gaps-landed" in ids and "stock:gaps-stacked" in ids      # (an auxiliary's node is named stock: too)
    into = {e.get("from", e["source"]) for e in g["edges"] if e["kind"] == "pipe" and e["target"] == "stock:gaps-landed"}
    assert {"flow:gaps-merged", "flow:joins-covered"} <= into, into


def test_the_factory_blocks_take_their_pools_from_the_pool_stocks():
    from ergostat.spec.ir import Ref
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    imp, rev = spec.blocks["implementor"], spec.blocks["reviewer"]
    assert imp.pool_now == Ref("stock", "implementor-pool") and imp.pool == 9   # main's operator: was 4
    assert rev.pool_now == Ref("stock", "reviewer-pool") and rev.pool == 6     # main's operator: was 2


def test_intake_reads_gaps_and_requests(tmp_path):
    f = Factory(tmp_path)
    said, lines = f.run("intake.py")
    found = {x["item"] for x in lines if x["event"] == "gap.found"}
    assert found == {"gap/alpha-thing", "gap/delta"}                   # not Beta (done), not Gamma (done recently)
    assert "gap.defined" not in said                                    # no definition yet
    (tmp_path / "instance" / "run" / "defs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "instance" / "run" / "defs" / "alpha-thing.md").write_text("# alpha\n\n## Definition of done\n\nIt.\n")
    (tmp_path / "instance" / "run" / "defs" / "ask.md").write_text("# my ask\n\nDo it.\n")
    f.fold([{"event": "gap.requested", "item": "gap/my-ask", "data": {"title": "My ask", "source": "request",
                                                                       "definition": "run/defs/ask.md"}},
            {"event": "gap.requested", "item": "gap/sneaky", "data": {"source": "request", "definition": "/etc/hosts"}},
            {"event": "gap.requested", "item": "gap/escape", "data": {"source": "request", "branch": "../ergostat",
                                                                      "definition": "run/defs/ask.md"}}], None)
    said, lines = f.run("intake.py")
    assert [x["item"] for x in lines if x["event"] == "gap.found"] == []    # nothing found twice
    assert {x["item"] for x in lines if x["event"] == "gap.defined"} == {"gap/alpha-thing", "gap/my-ask"}
    # (not gap/sneaky: a definition outside run/defs/; not gap/escape: a branch that is a path)
    assert f.item("gap/alpha-thing")["state"] == "ready" and f.item("gap/delta")["state"] == "open"


def test_load_sensor_counts_suites(tmp_path):
    (tmp_path / "pytest.py").write_text("import time\ntime.sleep(30)\n")
    p = subprocess.Popen([sys.executable, "-m", "pytest"], cwd=tmp_path)
    try:
        load = module("load")
        deadline = time.time() + 10
        while time.time() < deadline:
            rows = load.processes()
            if p.pid in load.suite_trees(rows):
                break
            time.sleep(0.2)
        assert p.pid in load.suite_trees(rows)
        assert load.threads({p.pid}) >= 1
        assert load.reading("suites") >= 1 and load.reading("memory") > 0
    finally:
        p.kill()
        p.wait()


def test_budget_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fac = module("fac")
    cfg = {"paths": {"run": str(tmp_path / "run")}}
    assert fac.daily_cap() > 0
    assert fac.may_spend(cfg, 1.0) is None                                     # nothing spent yet
    fac.record_cost(cfg, fac.daily_cap() - 0.5, role="implementor")
    assert "cap" in fac.may_spend(cfg, 1.0)                                    # would pass the cap
    assert fac.may_spend(cfg, 0.25) is None
    (tmp_path / "run" / "costs.jsonl").write_text("not json\n")
    assert "cannot be told" in fac.may_spend(cfg, 0.01)                        # an unreadable ledger refuses
    (tmp_path / "run" / "costs.jsonl").write_text(json.dumps({"at": time.time() - 2 * 86400, "usd": 999}) + "\n")
    assert fac.may_spend(cfg, 1.0) is None                                     # spent more than a day ago


def ready(f: Factory, iid: str = "gap/alpha-thing") -> str:
    d = f.tmp / "instance" / "run" / "defs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "alpha-thing.md").write_text("# alpha thing\n\n## Definition of done\n\nIt works.\n\n## Size budget\n\n600 net lines.\n")
    f.run("intake.py")
    assert f.item(iid)["state"] == "ready"
    return iid


def test_dry_run_one_gap(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    drop = tmp_path / "live" / "drop.git"
    first = git(drop, "log", "--reverse", "--format=%s", "main..factory/alpha-thing").splitlines()
    assert first[0] == "alpha-thing: the definition of done" and len(first) == 2
    gap = f.item(gid)
    assert gap["state"] == "built" and gap["fields"]["suites_fast"]["unit"]["rc"] == 0
    ctx = gap["fields"]["contexts"][0]
    assert ctx["role"] == "implementor" and ctx["brief_chars"] > 0 and "CLAUDE.md" in ctx["guides"]
    assert any(x.get("type") == "result" for x in lines)                      # its cost reported to the run

    said, _ = f.run("review.py", gid)
    assert said == ["gap.review-started", "review.written", "review.approved", "gap.approved"]
    review = f.item("review/alpha-thing-1")
    assert review["fields"]["verdict"] == "merge" and review["fields"]["context"]["role"] == "reviewer"
    assert "work_said" not in review["fields"]["context"]

    origin_before = git(f.origin, "rev-parse", "main")
    said, _ = f.run("queue.py", gid)
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    gap = f.item(gid)
    assert gap["state"] == "merged" and gap["fields"]["push"] == "held"
    assert git(f.checkout, "rev-parse", "main") == gap["fields"]["main_sha"]
    assert git(f.origin, "rev-parse", "main") == origin_before                 # asked for, not made
    assert f.db()["acts"][0][:2] == ["act", "push-main"]
    assert git(f.checkout, "rev-parse", "main^2") == gap["fields"]["reviewed_head"]   # the reviewed commit merged


def test_fix_then_park(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    last = f.gates["kill_after"]
    for n in range(1, last + 1):
        said, _ = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.built"]
        if n > 1:
            assert f.item(gid)["fields"]["rework"] is True
            assert f.item(gid)["fields"]["contexts"][-1]["findings"] == 1      # the findings went into its brief
        said, _ = f.run("review.py", gid, FACTORY_STANDIN_VERDICT="fix")
        if n < last:                                                          # a failed gate: another round
            assert said[-1] == "gap.sent-back" and f.item(gid)["state"] == "fix"
            assert f.item(gid)["fields"]["findings"] == ["the stand-in's blocking finding"]
    assert said[-1] == "gap.parked" and f.item(gid)["state"] == "parked"      # the kill rule: the last failed gate
    assert f.item(gid)["fields"]["parked_in"] == "review"
    definition = git(tmp_path / "live" / "drop.git", "show",
                     "factory/alpha-thing:dev/records/alpha-thing.md")
    assert "## Where it stopped" in definition


def test_flake_retried(tmp_path):
    flaky = tmp_path / "flaky.sh"
    flaky.write_text(f"#!/bin/sh\nif [ ! -e {tmp_path}/failed-once ]; then touch {tmp_path}/failed-once;"
                     " echo 'FAILED tests/test_x.py::test_y - boom'; exit 1; fi\necho '1 passed'\n")
    flaky.chmod(0o755)
    f = Factory(tmp_path, unit=str(flaky))
    gid = ready(f)
    (tmp_path / "failed-once").touch()                 # the implementor's fast suite passes
    f.run("implement.py", gid)
    f.run("review.py", gid)
    (tmp_path / "failed-once").unlink()                # the queue's unit run fails once
    said, _ = f.run("queue.py", gid)
    assert said == ["gap.queued", "gap.queue-failed", "gap.measured"] and f.item(gid)["fields"]["failed_tests"] == [
        "tests/test_x.py::test_y"]
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "start"     # the merge undone
    said, _ = f.run("triage.py", gid)
    assert said == ["gap.retried"] and f.flakes_said() == ["flake.seen"] and f.item(gid)["state"] == "approved"
    assert f.item("flake/tests-test-x-py-test-y")["fields"]["times"] == 1
    said, _ = f.run("queue.py", gid)
    assert said[:2] == ["gap.queued", "gap.merged"]


def queue_failed(tmp_path) -> tuple[Factory, str]:
    """A gap whose queue run failed on tests/test_x.py::test_y, waiting for triage; its rerun prints the commit it
    stands on (HEAD, with the branch merged uncommitted on it) to rerun-head and passes."""
    red = tmp_path / "red"
    f = Factory(tmp_path, unit=f"if [ -e {red} ]; then echo 'FAILED tests/test_x.py::test_y - boom'; exit 1; fi")
    f.config.write_text(f.config.read_text().replace(
        'rerun = "echo again {tests}"', f'rerun = "git rev-parse HEAD > {tmp_path / "rerun-head"}; echo again {{tests}}"'))
    gid = ready(f)
    f.run("implement.py", gid)                                                 # the implementor's fast suite passes
    f.run("review.py", gid)
    red.touch()                                                                # the queue's unit run fails
    said, _ = f.run("queue.py", gid)
    assert said[-2:] == ["gap.queue-failed", "gap.measured"], said
    return f, gid


def test_triage_runs_while_the_queue_holds_its_lock(tmp_path):
    f, gid = queue_failed(tmp_path)
    pre = f.item(gid)["fields"]["pre"]
    (f.checkout / "later.txt").write_text("main moved on\n")                   # main moves while triage waits
    git(f.checkout, "add", "later.txt")
    git(f.checkout, "commit", "-q", "-m", "later")
    with open(tmp_path / "queue.lock", "a") as lock:                           # the queue's run, holding its lock
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        said, _ = f.run("triage.py", gid, timeout=30)
    assert said == ["gap.retried"] and f.flakes_said() == ["flake.seen"] and f.item(gid)["state"] == "approved"
    assert (tmp_path / "rerun-head").read_text().strip() == pre                # judged on the main it failed on (lesson-1)
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "later"      # and main left as the queue has it


def test_triage_waiting_on_load_does_not_block_the_queue(tmp_path, monkeypatch, capsys):
    f, gid = queue_failed(tmp_path)
    monkeypatch.setenv("FACTORY_CONFIG", str(f.config))
    monkeypatch.syspath_prepend(str(BIN))                                      # (triage.py imports review beside it)
    sys.modules.setdefault("fac", module("fac"))
    triage = module("triage")
    taken = []

    def busy(cfg, why=""):                                                     # the machine busy: the queue comes by
        with open(tmp_path / "queue.lock", "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                taken.append(True)
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BlockingIOError:
                taken.append(False)
        return 0.0

    for k in ("ERGOSTAT_CMD", "FAKE_ROOT", "FAKE_FLAKE_KIND"):                                    # (the flake written at once: flakes.py)
        monkeypatch.setenv(k, f.env[k])
    monkeypatch.setattr(triage.fac, "MODEL", f.model)                          # (its lock in the instance's run dir)
    monkeypatch.setattr(triage.fac, "read_input", lambda: {"item": f.item(gid)})
    monkeypatch.setattr(triage.fac, "wait_quiet", busy)
    monkeypatch.setattr(triage, "rerun", lambda *a: (0, {"seconds": 0, "tests": []}))
    capsys.readouterr()
    assert triage.main() == 0
    assert taken == [True]                                                     # the queue took its lock while triage waited
    said = [json.loads(x)["event"] for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert said == ["gap.retried"] and f.flakes_said() == ["flake.seen"]


# ---- one writer of a flake's state (dev/records/regression-flake-writes-hold-state.md)

FLAKY = "tests/test_x.py::test_y"


def flake_record(tmp_path, monkeypatch):
    """A real project holding the root model's flake kind, ergostat on it, and the factory's run dir under tmp_path:
    dev/bin/flakes.py as the writers call it."""
    text = (ROOT / "ergostat.yaml").read_text()
    (tmp_path / "ergostat.yaml").write_text("name: flakes\nitems:" + text[text.index("\n  flake:\n"):
                                                                         text.index("\n  situation:\n")] + "\n")
    (tmp_path / "factory.toml").write_text(f'[paths]\nrun = "{tmp_path / "run"}"\n')
    monkeypatch.setenv("FACTORY_CONFIG", str(tmp_path / "factory.toml"))
    monkeypatch.setenv("ERGOSTAT_CMD", f"{sys.executable} -m ergostat -C {tmp_path}")
    monkeypatch.setenv("ERGOSTAT_NO_SOCKET", "1")
    sys.modules.setdefault("fac", module("fac"))
    flakes = module("flakes")
    monkeypatch.setattr(flakes.fac, "MODEL", tmp_path)
    return flakes


def flake_now(flakes, test: str = FLAKY) -> dict:
    return json.loads(flakes.fac.ergostat("item", f"flake/{flakes.fac.slug(test, 80)}", "--json").stdout)


def test_no_code_but_flakes_py_writes_a_flake_state():
    """Every flake.seen and flake.main-broken goes through flakes.say: no other file in dev/bin names either event as
    a string but as flakes.say's first argument (so none emits it), and the four writers call flakes.say."""
    named = re.compile(r"(?<!flakes\.say\()[\"']flake\.(seen|main-broken)[\"']")
    said = [f"{p.name}:{n}" for p in sorted(BIN.glob("*.py")) if p.name != "flakes.py"
            for n, line in enumerate(p.read_text().splitlines(), 1) if named.search(line)]
    assert said == []
    for name in ("onmain", "queue", "triage", "manage"):
        assert 'flakes.say("flake.' in (BIN / f"{name}.py").read_text(), name


def test_a_flake_seen_on_a_main_broken_test_is_counted_and_stays_main_broken(tmp_path, monkeypatch, capsys):
    flakes = flake_record(tmp_path, monkeypatch)
    assert flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0) == "flake.seen"
    assert flakes.say("flake.main-broken", FLAKY, main="m1", gaps=["gap/b"], main_broken_at=10.0) == "flake.main-broken"
    assert flakes.say("flake.seen", FLAKY, gaps=["gap/c"], times=1, seen_at=20.0) == "flake.measured"
    d = flake_now(flakes)
    assert d["state"] == "main-broken" and d["fields"]["times"] == 2 and d["fields"]["gaps"] == ["gap/a", "gap/b", "gap/c"]
    real = flakes.fac.ergostat                                     # the item unreadable: written as said, and said so
    monkeypatch.setattr(flakes.fac, "ergostat", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "the record is "
                        "busy") if a[0] == "item" else real(*a, **k))
    assert flakes.say("flake.seen", FLAKY, gaps=["gap/d"], times=1, seen_at=30.0) == "flake.seen"
    assert "could not be read (exit 1: the record is busy)" in capsys.readouterr().err
    monkeypatch.setattr(flakes.fac, "ergostat", real)
    assert flake_now(flakes)["state"] == "seen"


def test_a_second_main_broken_keeps_the_first_clock(tmp_path, monkeypatch):
    flakes = flake_record(tmp_path, monkeypatch)
    flakes.say("flake.main-broken", FLAKY, main="m1", gaps=["gap/a"], main_broken_at=10.0)
    flakes.say("flake.main-broken", FLAKY, main="m2", gaps=["gap/b"], main_broken_at=50.0)
    d = flake_now(flakes)
    assert d["state"] == "main-broken" and d["fields"]["main_broken_at"] == 10.0
    assert d["fields"]["main"] == "m2" and d["fields"]["gaps"] == ["gap/a", "gap/b"]


def test_a_fixed_flake_seen_again_is_made_anew(tmp_path, monkeypatch):
    """lesson-5: a fixed flake said again (seen, or main-broken) starts a new count, its fixed fields gone."""
    flakes = flake_record(tmp_path, monkeypatch)
    for test, again in ((FLAKY, "flake.seen"), ("tests/test_x.py::test_z", "flake.main-broken")):
        iid = f"flake/{flakes.fac.slug(test, 80)}"
        flakes.say("flake.seen", test, gaps=["gap/a"], times=1, seen_at=1.0)
        flakes.say("flake.seen", test, gaps=["gap/a"], times=1, seen_at=2.0)
        flakes.fac.add("flake.fixed", iid, main_fixed_at=5.0, fixed_by="gap/fix", green_passes=3)
        assert flake_now(flakes, test)["state"] == "fixed"
        assert flakes.say(again, test, gaps=["gap/b"], main="m3", main_broken_at=9.0, seen_at=9.0) == again
        d = flake_now(flakes, test)
        assert d["state"] == again.split(".")[1] and not d["refused"], d["refused"]
        assert d["fields"]["times"] == 1 and d["fields"]["gaps"] == ["gap/b"] and d["fields"]["main_broken_at"] == 9.0
        assert not {"main_fixed_at", "fixed_by"} & set(d["fields"])
        assert d["fields"].get("green_passes") == (0 if again == "flake.seen" else None)   # (3 gone: counted anew)


def test_two_flake_writers_at_once_never_lose_a_state(tmp_path, monkeypatch):
    """lesson-1: a main-broken written in the gap between a flake.seen's read and its write waits for the lock, reads
    the seen, and is kept; with nothing held, the seen written last would take the test out of main-broken."""
    flakes = flake_record(tmp_path, monkeypatch)
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    real, other = flakes.read, []

    def read_then_competitor(iid):
        got = real(iid)
        if not other:                                              # (the first read only: the seen writer's)
            other.append(threading.Thread(target=flakes.say, args=("flake.main-broken", FLAKY),
                                          kwargs={"main": "m1", "gaps": ["gap/b"], "main_broken_at": 10.0}))
            other[0].start()
            other[0].join(timeout=5)                               # (held by the lock: it cannot finish here)
        return got
    monkeypatch.setattr(flakes, "read", read_then_competitor)
    assert flakes.say("flake.seen", FLAKY, gaps=["gap/c"], times=1, seen_at=2.0) == "flake.seen"
    other[0].join(timeout=60)
    d = flake_now(flakes)
    assert d["state"] == "main-broken" and d["fields"]["main_broken_at"] == 10.0 and d["fields"]["times"] == 2


# ---- a seen flake fixed after green queue runs (dev/records/regression-flake-fixed-after-green.md)

def green_run(tmp_path, n: int, unit: str, browser: str | None = None, over: dict | None = None) -> dict:
    """A green run's suites as queue.suites records them: unit (and browser) green, each with its log (``over``:
    a suite's entry otherwise)."""
    over = over or {}
    got = {}
    for name, text in (("unit", unit), ("browser", browser)):
        if text is not None:
            (tmp_path / f"{name}-{n}.txt").write_text(text)
            got[name] = {"rc": 0, "seconds": 1, "log": str(tmp_path / f"{name}-{n}.txt")} | over.get(name, {})
    return got


PASSED = f"....\nPASSED {FLAKY}\nPASSED tests/test_x.py::test_other\n2 passed in 0.1s\n"


def test_n_consecutive_green_runs_naming_the_test_passed_fix_it(tmp_path, monkeypatch):
    flakes = flake_record(tmp_path, monkeypatch)
    (tmp_path / "factory.toml").write_text(f'[paths]\nrun = "{tmp_path / "run"}"\n[gates]\nflake_fixed_after = 3\n')
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    for i in (1, 2):
        assert flakes.green(green_run(tmp_path, i, "", PASSED), f"m{i}") == []           # (in the browser log)
        d = flake_now(flakes)
        assert d["state"] == "seen" and d["fields"]["green_passes"] == i and not d["refused"], d["refused"]
    assert flakes.green(green_run(tmp_path, 3, PASSED), "m3") == [f"flake/{flakes.fac.slug(FLAKY, 80)}"]
    d = flake_now(flakes)
    assert d["state"] == "fixed" and d["fields"]["fixed_by"] == "green-runs" and d["fields"]["fixed_on"] == "m3"
    assert d["fields"]["green_passes"] == 3
    assert flakes.green(green_run(tmp_path, 4, PASSED), "m4") == []                     # (fixed: no longer seen)


def test_a_seen_between_green_runs_restarts_the_count(tmp_path, monkeypatch):
    flakes = flake_record(tmp_path, monkeypatch)
    (tmp_path / "factory.toml").write_text(f'[paths]\nrun = "{tmp_path / "run"}"\n[gates]\nflake_fixed_after = 2\n')
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    flakes.green(green_run(tmp_path, 1, PASSED), "m1")
    assert flake_now(flakes)["fields"]["green_passes"] == 1
    flakes.say("flake.seen", FLAKY, gaps=["gap/b"], times=1, seen_at=2.0)
    assert flake_now(flakes)["fields"]["green_passes"] == 0
    assert flakes.green(green_run(tmp_path, 2, PASSED), "m2") == []                     # (one in a row, not two)
    d = flake_now(flakes)
    assert d["state"] == "seen" and d["fields"]["green_passes"] == 1
    assert flakes.green(green_run(tmp_path, 3, PASSED), "m3") and flake_now(flakes)["state"] == "fixed"


def test_a_test_absent_from_the_log_never_counts(tmp_path, monkeypatch):
    """Unknown changes nothing: a deleted or renamed test (no PASSED line), a suite not run in that batch, a red,
    stopped or unreadable one, a FAILED line beside a PASSED one, a quarantined flake; and a flake_fixed_after past
    its ceiling is refused, never read as some other count."""
    flakes = flake_record(tmp_path, monkeypatch)
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    gone = "PASSED tests/test_x.py::test_y_renamed\nSKIPPED [1] tests/test_x.py:3: no\n1 passed in 0.1s\n"
    for i, run in enumerate((green_run(tmp_path, 1, gone), {"ruff": {"rc": 0}}, {"unit": {"rc": 0}},
                             green_run(tmp_path, 2, PASSED, over={"unit": {"rc": 1}}),
                             green_run(tmp_path, 3, PASSED, over={"unit": {"stopped_by": "browser"}}),
                             {"unit": {"rc": 0, "log": str(tmp_path / "missing.txt")}},
                             green_run(tmp_path, 4, PASSED, f"FAILED {FLAKY} - boom\n"))):
        assert flakes.green(run, f"m{i}") == []
        assert flake_now(flakes)["fields"]["green_passes"] == 0, run
    flakes.fac.add("flake.measured", f"flake/{flakes.fac.slug(FLAKY, 80)}", quarantined=True)
    flakes.green(green_run(tmp_path, 5, PASSED), "m5")
    assert flake_now(flakes)["fields"]["green_passes"] == 0
    for bad in (0, 51, "5", 2.5, True):
        with pytest.raises(ValueError, match="flake_fixed_after"):
            flakes.fixed_after({"gates": {"flake_fixed_after": bad}})
    assert flakes.fixed_after({}) == 5 and flakes.fixed_after({"gates": {"flake_fixed_after": 50}}) == 50


# ---- a flake said fixed by hand, and the quarantine's release (dev/records/regression-flake-fixed-by-hand.md)

def manage_record(tmp_path, monkeypatch):
    """flake_record's project, and dev/bin/manage.py on it: (manage, its flakes module)."""
    flakes = flake_record(tmp_path, monkeypatch)
    monkeypatch.syspath_prepend(str(BIN))
    monkeypatch.setitem(sys.modules, "fac", flakes.fac)            # (manage's imports: its own for this test, the
    monkeypatch.setitem(sys.modules, "flakes", flakes)             # ones earlier tests left in sys.modules unused,
    for name in ("agents", "onmain", "runs"):                      # and none left behind for the tests after it)
        monkeypatch.setitem(sys.modules, name, module(name))
    manage = module("manage")
    assert manage.fac is flakes.fac and manage.flakes is flakes and manage.onmain.flakes is flakes
    return manage, flakes


def fixes(flakes) -> list[dict]:
    return [i for i in flakes.fac.items("intervention") if i["fields"].get("action") == "flake-fixed"]


def test_flake_fixed_moves_a_seen_or_main_broken_flake_to_fixed_with_one_intervention(tmp_path, monkeypatch):
    manage, flakes = manage_record(tmp_path, monkeypatch)
    broken = "tests/test_x.py::test_z"
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    flakes.say("flake.main-broken", broken, main="m1", gaps=["gap/b"], main_broken_at=10.0)
    for n, test in enumerate((FLAKY, broken), 1):
        got = manage.run({}, ["flake-fixed", test, "--why", "the test was renamed"])
        assert got["ok"] and got["said"] == f"{test} fixed", got
        d = flake_now(flakes, test)
        assert d["state"] == "fixed" and d["fields"]["fixed_by"] == "coordinator", d
        assert d["fields"]["why"] == "the test was renamed"
        assert sorted(i["fields"]["subject"] for i in fixes(flakes)) == sorted((FLAKY, broken)[:n])   # one each
    assert {i["fields"]["class"] for i in fixes(flakes)} == {"flake"}


def test_flake_fixed_refuses_an_unknown_test_or_one_already_fixed(tmp_path, monkeypatch):
    """lesson-1: a second flake-fixed in the gap between the first's read and its write waits for the flakes lock,
    reads the fixed item and is refused, so one fix is one intervention."""
    import threading
    manage, flakes = manage_record(tmp_path, monkeypatch)
    got = manage.run({}, ["flake-fixed", FLAKY, "--why", "gone"])
    assert not got["ok"] and "no flake recorded" in got["said"] and fixes(flakes) == []
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    real, other = flakes.read, []

    def read_then_competitor(iid):
        got = real(iid)
        if not other:                                              # (the first read only)
            other.append(threading.Thread(target=lambda: other.append(
                manage.run({}, ["flake-fixed", FLAKY, "--why", "me too"]))))
            other[0].start()
            other[0].join(timeout=5)                               # (held by the lock: it cannot finish here)
        return got
    monkeypatch.setattr(flakes, "read", read_then_competitor)
    assert manage.run({}, ["flake-fixed", FLAKY, "--why", "deleted"])["ok"]
    other[0].join(timeout=60)
    assert not other[1]["ok"] and "is fixed" in other[1]["said"], other[1]
    assert len(fixes(flakes)) == 1 and flake_now(flakes)["fields"]["why"] == "deleted"
    monkeypatch.setattr(flakes, "read", real)
    got = manage.run({}, ["flake-fixed", FLAKY, "--why", "again"])
    assert not got["ok"] and "is fixed" in got["said"] and len(fixes(flakes)) == 1
    monkeypatch.setattr(flakes, "read", lambda iid: None)          # an unreadable item: refused, nothing written
    assert not manage.run({}, ["flake-fixed", FLAKY, "--why", "x"])["ok"] and len(fixes(flakes)) == 1
    monkeypatch.setattr(flakes, "read", real)                      # the pipeline manager's call: refused, unlisted
    other_test = FLAKY + "_two"
    flakes.say("flake.seen", other_test, gaps=["gap/a"], times=1, seen_at=1.0)
    monkeypatch.setattr(manage, "BY", ["pipeline-manager"])       # (as watch.py sets it for the manager's run)
    got = manage.run({}, ["flake-fixed", other_test, "--why", "looks gone"])
    assert not got["ok"] and "by a person" in got["said"] and len(fixes(flakes)) == 1, got
    assert flake_now(flakes, other_test)["state"] == "seen"
    assert "flake-fixed" not in manage.__doc__


def test_a_quarantine_release_is_one_flake_released(tmp_path, monkeypatch):
    flakes = flake_record(tmp_path, monkeypatch)
    fac, iid, said = flakes.fac, f"flake/{flakes.fac.slug(FLAKY, 80)}", []
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    fac.add("flake.measured", iid, test=FLAKY, quarantined=True, last_run="fail")
    monkeypatch.setattr(fac, "say", lambda event, it, **data: (said.append((event, it)), fac.add(event, it, **data)))
    assert fac.beside([], tmp_path / "none.txt", lambda _: None) == {}             # FLAKY is no longer listed
    assert said == [("flake.released", iid)]
    d = flake_now(flakes)
    assert d["fields"]["quarantined"] is False and d["fields"]["released_at"] > 0 and d["state"] == "seen"
    fac.beside([], tmp_path / "none.txt", lambda _: None)                           # released once, not again
    assert said == [("flake.released", iid)]


# ---- main-mend: out of main-broken after two passes alone on the pushed main (dev/records/regression-flake-main-fixed.md)

BROWSER_TEST = "tests/test_items_page.py::test_b"


def mend_record(tmp_path, monkeypatch, says: dict, most=5, quarantined=()):
    """flake_record, and dev/bin/mend.py on it: a repository whose main is c1 then c2 (c3 off c1, never on main), main
    as pushed c2, and each suite run played by ``says`` ({test: [what run 1 prints, run 2]}: PASSED, FAILED or None,
    no line). The suite runs made, as (command, tests, box), in the list returned."""
    flakes = flake_record(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    shas = {}
    for n in ("c1", "c2"):
        (repo / n).write_text(n)
        git(repo, "add", n)
        git(repo, "commit", "-q", "-m", n)
        shas[n] = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "side", shas["c1"])
    (repo / "c3").write_text("c3")
    git(repo, "add", "c3")
    git(repo, "commit", "-q", "-m", "c3")
    shas["c3"] = git(repo, "rev-parse", "HEAD")
    (tmp_path / "factory.toml").write_text(textwrap.dedent(f"""\
        [paths]
        run = "{tmp_path / 'run'}"
        checkout = "{repo}"
        worktrees = "{tmp_path / 'wt'}"
        [gates]
        mend_most = {json.dumps(most)}
        [suites]
        browser = "uv run pytest -q tests/test_items_page.py tests/test_page_refresh.py"
        """))
    monkeypatch.setitem(sys.modules, "flakes", flakes)
    mend = module("mend")
    ran: list[tuple] = []

    def suite(cfg, name, cwd, log, box="", tests=(), **_):
        tests = [t for t in tests if t != "-rA"]
        n = sum(1 for r in ran if r[0] == name)
        ran.append((name, tuple(tests), box))
        log.write_text("".join(f"{says[t][n]} {t}\n" for t in tests if says[t][n]) + "1 passed in 0.1s\n")
        return 0, 0.1
    monkeypatch.setattr(mend.fac, "suite", suite)
    monkeypatch.setattr(mend.fac, "wait_quiet", lambda cfg, why="": 0.0)
    monkeypatch.setattr(mend.fac, "stop_on_term", lambda: None)    # (no SIGTERM handler left in the pytest worker)
    monkeypatch.setattr(mend.fac, "quarantine", lambda repo, ref: list(quarantined) if ref == shas["c2"] else [])
    monkeypatch.setattr(mend, "pushed", lambda cfg: shas["c2"])
    monkeypatch.setattr(mend, "tree", lambda cfg, sha: repo)
    return flakes, mend, shas, ran


def test_main_mend_clears_only_a_test_passing_twice_on_the_pushed_main(tmp_path, monkeypatch):
    """Two PASSED lines on main as pushed clear it (fixed, with passed_on, main_fixed_at, fixed_by); a failure, a run
    with no line for it (skipped, not collected), or a quarantine at that commit leaves it main-broken. A browser
    file's test runs with `rerun` (Playwright), the rest with `alone`, each with -rA, in a suite container."""
    says = {"tests/test_a.py::test_ok": ["PASSED", "PASSED"], "tests/test_a.py::test_once": ["PASSED", "FAILED"],
            "tests/test_a.py::test_skip": ["PASSED", None], "tests/test_a.py::test_held": ["PASSED", "PASSED"],
            BROWSER_TEST: ["PASSED", "PASSED"]}
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, says, quarantined=["tests/test_a.py::test_held"])
    for n, t in enumerate(says):
        flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0 + n)
    assert mend.main() == 0
    state = {t: flake_now(flakes, t) for t in says}
    assert {t: d["state"] for t, d in state.items()} == {
        "tests/test_a.py::test_ok": "fixed", "tests/test_a.py::test_once": "main-broken",
        "tests/test_a.py::test_skip": "main-broken", "tests/test_a.py::test_held": "main-broken", BROWSER_TEST: "fixed"}
    f = state["tests/test_a.py::test_ok"]["fields"]
    assert f["passed_on"] == shas["c2"] and f["fixed_by"] == "main-mend" and f["main_fixed_at"] > 10.0
    alone = ("tests/test_a.py::test_ok", "tests/test_a.py::test_once", "tests/test_a.py::test_skip")
    assert sorted(ran) == sorted([("alone", alone, "mend")] * 2 + [("rerun", (BROWSER_TEST,), "mend")] * 2)


def test_main_mend_writes_only_where_the_items_main_is_the_commit_run_on_or_an_ancestor(tmp_path, monkeypatch):
    """A main-broken written on a commit main as pushed does not hold (c3, off main) is not cleared by passes on c2."""
    says = {"tests/test_a.py::test_old": ["PASSED", "PASSED"], "tests/test_a.py::test_off": ["PASSED", "PASSED"],
            "tests/test_a.py::test_now": ["PASSED", "PASSED"]}
    flakes, mend, shas, _ = mend_record(tmp_path, monkeypatch, says)
    for t, at in zip(says, ("c1", "c3", "c2"), strict=True):
        flakes.say("flake.main-broken", t, main=shas[at], gaps=["gap/a"], main_broken_at=10.0)
    assert mend.main() == 0
    assert [flake_now(flakes, t)["state"] for t in says] == ["fixed", "main-broken", "fixed"]


def test_a_newer_break_written_in_between_refuses_main_fixed_and_its_move(tmp_path, monkeypatch):
    """lesson-1: a newer main written on the item after main-mend read it (by a writer outside flakes.py's lock) fails
    the patch's first op, a test of /main as read: the whole event is refused, its move to fixed too."""
    t = "tests/test_a.py::test_ok"
    flakes, mend, shas, _ = mend_record(tmp_path, monkeypatch, {t: ["PASSED", "PASSED"]})
    flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0)
    iid, real = f"flake/{flakes.fac.slug(t, 80)}", flakes.read

    def read_then_break(i):
        got = real(i)
        flakes.fac.add("flake.measured", iid, main=shas["c2"])     # (broken again on c2, between the read and the write)
        return got
    monkeypatch.setattr(flakes, "read", read_then_break)
    assert mend.main() == 0
    d = flake_now(flakes, t)
    assert d["state"] == "main-broken" and d["fields"]["main"] == shas["c2"] and "passed_on" not in d["fields"]
    assert d["refused"] and d["refused"][-1]["type"] == "flake.main-fixed" and "test /main" in d["refused"][-1]["why"]


def test_main_mend_takes_at_most_mend_most_a_run_oldest_first(tmp_path, monkeypatch):
    """lesson-4: [gates] mend_most tests a run, the oldest main-broken first; held to 1..20, 5 when not a number."""
    says = {f"tests/test_a.py::test_{n}": ["PASSED", "PASSED"] for n in range(7)}
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, says, most=3)
    for n, t in enumerate(says):
        flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=100.0 - n)
    assert mend.main() == 0
    oldest = ("tests/test_a.py::test_6", "tests/test_a.py::test_5", "tests/test_a.py::test_4")
    assert ran == [("alone", oldest, "mend")] * 2
    assert sorted(t for t in says if flake_now(flakes, t)["state"] == "fixed") == sorted(oldest)
    assert [mend.most({"gates": {"mend_most": v}}) for v in (500, 0, "9", True, 7)] == [20, 1, 5, 5, 7]
    assert mend.most({}) == 5


def test_main_mend_items_left_unknown_give_up_their_place(tmp_path, monkeypatch):
    """mend_most items that stay unknown run after run (still failing) do not hold the front: the next run takes the
    untried item behind them first and clears it, and a try counts only for the break it was made on."""
    bad, new = ["tests/test_a.py::test_0", "tests/test_a.py::test_1"], "tests/test_a.py::test_2"
    says = {**{t: ["FAILED"] * 6 for t in bad}, new: ["PASSED"] * 6}
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, says, most=2)
    for n, t in enumerate([*bad, new]):
        flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0 + n)
    assert mend.main() == 0 and ran[-1] == ("alone", tuple(bad), "mend")
    assert mend.main() == 0 and new in ran[-1][1] and flake_now(flakes, new)["state"] == "fixed"
    assert set(json.loads((tmp_path / "run" / "mend" / "tried.json").read_text())) <= {
        f"flake/{flakes.fac.slug(t, 80)}" for t in bad}
    flakes.say("flake.main-broken", bad[0], main=shas["c2"], gaps=["gap/a"], main_broken_at=50.0)   # (again, on c2)
    assert mend.main() == 0 and ran[-1][1] == (bad[0], bad[1])     # (tried last run, but untried since this break)


def test_a_main_mend_run_killed_after_the_pick_still_counts_its_items_tried(tmp_path, monkeypatch):
    """lesson-3: a run stopped in its suite (a hanging test past the block's timeout or lease: SIGTERM is
    sys.exit(143)) has tried what it picked, so the next run takes the untried item behind them and clears it."""
    hang, new = ["tests/test_a.py::test_0", "tests/test_a.py::test_1"], "tests/test_a.py::test_2"
    says = {**{t: ["FAILED"] * 4 for t in hang}, new: ["PASSED"] * 4}
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, says, most=2)
    for n, t in enumerate([*hang, new]):
        flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0 + n)
    played = mend.fac.suite

    def killed(cfg, name, cwd, log, box="", tests=(), **_):
        ran.append((name, tuple(t for t in tests if t != "-rA"), box))
        raise SystemExit(143)
    monkeypatch.setattr(mend.fac, "suite", killed)
    with pytest.raises(SystemExit):
        mend.main()
    assert ran == [("alone", tuple(hang), "mend")]
    monkeypatch.setattr(mend.fac, "suite", played)
    assert mend.main() == 0 and ran[1][1][0] == new and flake_now(flakes, new)["state"] == "fixed"


def test_a_hanging_test_that_kills_every_run_does_not_hold_back_its_batch_mates(tmp_path, monkeypatch):
    """lesson-3, lesson-6: a stock within mend_most is picked whole every run; one test that hangs past the block's
    timeout kills each run it is in (SIGTERM: sys.exit(143)). After a run that died, its items run one at a time,
    each stamped tried as it starts, so the hanging test goes behind the others and they are cleared."""
    hang, ok = "tests/test_a.py::test_hang", ["tests/test_a.py::test_0", "tests/test_a.py::test_1"]
    says = {hang: ["FAILED"] * 9, **{t: ["PASSED"] * 9 for t in ok}}
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, says, most=5)
    for n, t in enumerate([hang, *ok]):
        flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0 + n)
    played = mend.fac.suite

    def hangs(cfg, name, cwd, log, box="", tests=(), **kw):
        if hang in tests:
            ran.append((name, tuple(t for t in tests if t != "-rA"), box))
            raise SystemExit(143)
        return played(cfg, name, cwd, log, box=box, tests=tests, **kw)
    monkeypatch.setattr(mend.fac, "suite", hangs)
    for _ in range(3):
        with pytest.raises(SystemExit):
            mend.main()
    assert ran[0] == ("alone", (hang, *ok), "mend") and ran[1] == ("alone", (hang,), "mend")
    assert [flake_now(flakes, t)["state"] for t in [hang, *ok]] == ["main-broken", "fixed", "fixed"]


def test_main_mend_is_a_scheduled_block_and_main_fixed_moves_to_fixed():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"]
    b = spec.blocks["main-mend"]
    assert (b.every, b.pool, b.timeout, b.lease.ttl) == (1800.0, 1, 1800.0, 1800.0) and b.takes is None
    assert "dev/bin/mend.py" in json.dumps(b.params, default=str)
    assert spec.items["flake"].on["flake.main-fixed"] == "fixed"
    assert "main-mend" in (ROOT / "dev" / "README.md").read_text()
    assert tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["gates"]["mend_most"] == 5


# ---- the guarantees: main's failing tests a stock, held at zero by main-green (dev/records/regression-guarantees-model.md)

def test_the_guarantees_model_checks_clean():
    """The system and its file; check finds no error and no missing feedback for main-green, whose loop closes through
    the coordinator (fix-main, a block of its own), and is drawn balancing under the name main-repair. No block
    outside the system moves what its loop uses: check finds no `interface` on it."""
    from ergostat.spec import causal
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    assert [p for p in problems if p.code == "missing-feedback" and p.about == "goal.main-green"] == []
    assert [p for p in problems if p.code == "interface" and p.about == "system.guarantees"] == []
    assert "guarantees" in spec.systems and spec.within["guarantees"] == "oversight"
    g = spec.goals["main-green"]
    assert (g.of.kind, g.of.name, g.hold.op, g.hold.value, g.critical, g.on_stale, g.system) == (
        "stock", "main-failing-tests", "<=", 0, True, "off", "guarantees")
    assert spec.blocks["fix-main"].system == "guarantees"
    lp = spec.loop("main-green")
    assert lp.closes, lp
    assert (lp.actuators, lp.valves, lp.disturbances) == (["fix-main"], ["main-tests-fixed"], ["main-tests-broken"])
    # the cycle, by the links ergostat draws (their signs its own), named and signed as check names and signs loops
    # (causal.loops stops at its first 300, and in the factory's model this one was past them: it is walked here)
    drawn = {(x.source, x.target): x for x in causal.links(spec)}
    parts = ["stock.main-failing-tests", "goal.main-green", "block.fix-main", "flow.main-tests-fixed"]
    cycle = [drawn[(a, b)] for a, b in zip(parts, parts[1:] + parts[:1], strict=True)]
    (lp,) = causal._named(spec, [cycle])
    assert (lp.name, lp.polarity) == ("main-repair", "B"), [(x.source, x.target, x.sign) for x in cycle]


def guarantees_project(tmp_path, every: str):
    """The flake fixture's project (the root model's flake kind) with dev/model/guarantees.yaml's stock, flows,
    parameter and goal added as written, its sensors every ``every``: a project ergostat runs on."""
    import yaml

    from ergostat import model as mdl
    from ergostat.store import Project
    parts = yaml.safe_load((ROOT / "dev" / "model" / "guarantees.yaml").read_text())
    for table in ("stocks", "flows"):
        for p in parts[table].values():
            p["sensor"]["every"] = every
    extra = {k: parts[k] for k in ("stocks", "flows", "parameters", "goals")}
    with (tmp_path / "ergostat.yaml").open("a") as out:
        out.write(yaml.safe_dump(extra, sort_keys=False))
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    return p


def main_green_off(p, want: float, within: float = 20.0) -> None:
    """The real engine on the project, its sensors running, till main-green's .off is ``want``."""
    from ergostat.spec.engine import Engine
    e = Engine(p, say=lambda s: None)
    e.start_all()
    deadline = time.monotonic() + within
    try:
        while e.signals.get("goal.main-green.off") != want and time.monotonic() < deadline:
            time.sleep(0.1)
        assert e.signals.get("goal.main-green.off") == want, e.signals.get("stock.main-failing-tests")
        assert e.signals.get("stock.main-failing-tests") == (1 if want else 0)
    finally:
        e.close()


def test_main_green_goes_off_and_holds_again(tmp_path, monkeypatch):
    """A test found failing on main (flake.main-broken, by flakes.say) turns main-green off; main-mend seeing it pass
    twice alone on the pushed main (flake.main-fixed) turns it holding again."""
    t = "tests/test_a.py::test_ok"
    flakes, mend, shas, ran = mend_record(tmp_path, monkeypatch, {t: ["PASSED", "PASSED"]})
    p = guarantees_project(tmp_path, "0.2s")
    main_green_off(p, 0.0)                                                     # nothing failing: holding
    flakes.say("flake.main-broken", t, main=shas["c1"], gaps=["gap/a"], main_broken_at=10.0)
    main_green_off(p, 1.0)
    assert p.events.query(n=None, type="loop.off", item="main-green")
    assert mend.main() == 0
    assert flake_now(flakes, t)["state"] == "fixed" and flake_now(flakes, t)["fields"]["fixed_by"] == "main-mend"
    main_green_off(p, 0.0)
    assert p.events.query(n=None, type="loop.holding", item="main-green")


def test_main_green_stale_is_off(tmp_path, monkeypatch):
    """main-green's policy is off: a stale reading of main-failing-tests counts as off (its .off 1 at a value of 0), and
    reading again makes it hold. An items sensor is never stale (SPEC §9.6: the engine reads the item index itself), so
    the reading here is made stale as a periodic sensor's would be: what main-green does then is its own on-stale."""
    from ergostat.spec import observer
    from ergostat.spec.engine import Engine
    flake_record(tmp_path, monkeypatch)
    p = guarantees_project(tmp_path, "1m")
    assert observer.stale_by(next(iter(p.model.spec.stocks["main-failing-tests"].sensors.values())), 0.0) is None
    monkeypatch.setattr(observer, "stale_by", lambda s, last: last + observer.STALE_AFTER * s.every)
    clock = [1_800_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    e = Engine(p, say=lambda s: None)
    e.start = lambda b, why: None                                              # (nothing runs)
    series = next(iter(p.model.spec.stocks["main-failing-tests"].sensors.values())).series
    p.measurements.add(series, 0, clock[0])
    e.evaluate(tick=True)
    assert e.signals["goal.main-green.off"] == 0 and not e.stale
    clock[0] += 600                                                            # 10 min unread, its sensor every 1m
    e.evaluate(tick=True)
    assert "main-green" in e.stale and e.signals["goal.main-green.off"] == 1
    went = p.events.query(n=None, type="ergostat.goal.stale", item="main-green")
    assert len(went) == 1 and went[0]["data"]["on_stale"] == "off"
    clock[0] += 1
    p.measurements.add(series, 0, clock[0])
    e.evaluate(tick=True)
    assert not e.stale and e.signals["goal.main-green.off"] == 0


def held_on(tmp_path, monkeypatch, text: str | None, marked=()):
    """dev/bin/held.py on a checkout whose main as pushed (refs/remotes/origin/main) holds ``text`` as
    tests/quarantine.txt (None: no such ref), the flake items marked quarantined being ``marked``; (held, cfg)."""
    sys.modules.setdefault("fac", module("fac"))
    held = module("held")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    if text is not None:
        (repo / "tests").mkdir()
        (repo / "tests" / "quarantine.txt").write_text(text)
        git(repo, "add", "tests")
        git(repo, "commit", "-q", "-m", "q")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    items = [{"id": f"flake/{n}", "fields": {"test": t, "quarantined": True}} for n, t in enumerate(marked)]
    monkeypatch.setattr(held.fac, "items", lambda kind: items)
    return held, {"paths": {"checkout": str(repo)}, "git": {"base": "main", "remote": "origin"}}


QUARANTINE = ("# a comment\n# Released: tests/test_x.py::test_old | them | 2026-01-01 | gone\n"
              "tests/test_a.py::test_one | them | 2026-11-21 | load\n\n"
              "tests/test_b.py::test_two | them | 2026-11-12 | load\n")


def test_held_counts_the_quarantine_and_the_age_of_its_oldest_test(tmp_path, monkeypatch, capsys):
    """The tests listed on main as pushed (comments and released lines not counted) and the days since the oldest
    `when`; the list's tests all marked quarantined on their flake items: nothing named."""
    import datetime
    held, cfg = held_on(tmp_path, monkeypatch, QUARANTINE, ["tests/test_a.py::test_one", "tests/test_b.py::test_two"])
    today = datetime.date(2026, 11, 23)
    assert held.reading("quarantined", cfg, today) == 2
    assert held.reading("quarantine-oldest-days", cfg, today) == 11
    assert capsys.readouterr().err == ""


def test_held_gives_no_value_for_a_list_or_date_it_cannot_read(tmp_path, monkeypatch):
    """No main as pushed, a line not `test | who | when | why`, or a `when` not a date: no value (exit 1), never 0;
    nothing listed has no oldest age (and a count of 0)."""
    import datetime
    today = datetime.date(2026, 11, 23)
    for n, text in enumerate([None, QUARANTINE + "tests/test_c.py::test_three | them\n",
                              QUARANTINE + "tests/test_c.py::test_three | them | last week | load\n"]):
        held, cfg = held_on(tmp_path / str(n), monkeypatch, text)
        for name in ("quarantined", "quarantine-oldest-days"):
            with pytest.raises(SystemExit) as e:
                held.reading(name, cfg, today)
            assert "no value" in str(e.value.code), (n, name)
    held, cfg = held_on(tmp_path / "empty", monkeypatch, "# nothing\n")
    assert held.reading("quarantined", cfg, today) == 0
    with pytest.raises(SystemExit, match="no value"):
        held.reading("quarantine-oldest-days", cfg, today)


def test_held_names_a_listed_test_with_no_quarantined_flake_and_the_reverse(tmp_path, monkeypatch, capsys):
    """A listed test no flake item marks quarantined, and a flake item marked quarantined whose test is not listed,
    each named on stderr; the reading is still the list's."""
    import datetime
    held, cfg = held_on(tmp_path, monkeypatch, QUARANTINE, ["tests/test_a.py::test_one", "tests/test_z.py::test_gone"])
    assert held.reading("quarantined", cfg, datetime.date(2026, 11, 23)) == 2
    err = capsys.readouterr().err
    assert "listed, no flake item marked quarantined: tests/test_b.py::test_two" in err
    assert "marked quarantined, not listed: tests/test_z.py::test_gone" in err
    assert "test_one" not in err


def test_quarantine_small_holds_on_main_and_is_off_with_one_test_added(tmp_path):
    """check finds no error in the factory's model, quarantine-small is `<= quarantine-most` (one number), no goal is
    on quarantine-oldest-days, and the real engine on dev/model/guarantees-quarantine.yaml holds quarantine-small at the
    count tests/quarantine.txt lists and turns it off with one test more."""
    import yaml

    from ergostat import model as mdl
    from ergostat.spec.engine import Engine
    from ergostat.store import Project
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    mine = {"stock.quarantined", "flow.quarantine-added", "flow.quarantine-released", "parameter.quarantine-most",
            "auxiliary.quarantine-oldest-days", "parameter.quarantine-release-time", "goal.quarantine-small",
            "block.release-quarantined"}
    assert [(p.code, p.about) for p in problems if p.about in mine] == []          # what check finds on its parts
    g = spec.goals["quarantine-small"]
    assert (g.of.kind, g.of.name, g.hold.op, g.on_stale, g.system) == ("stock", "quarantined", "<=", "off", "guarantees")
    assert g.hold.value == spec.parameters["quarantine-most"].value
    assert [n for n, x in spec.goals.items() if x.of.name == "quarantine-oldest-days"] == []
    sys.modules.setdefault("fac", module("fac"))
    count = len(module("held").listed((ROOT / "tests" / "quarantine.txt").read_text()))
    parts = yaml.safe_load((ROOT / "dev" / "model" / "guarantees-quarantine.yaml").read_text())
    (tmp_path / "ergostat.yaml").write_text(yaml.safe_dump(
        {"name": "q", **{k: parts[k] for k in ("stocks", "parameters", "goals")}}, sort_keys=False))
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    e.start = lambda b, why: None                                              # (nothing runs)
    series = next(iter(p.model.spec.stocks["quarantined"].sensors.values())).series
    p.measurements.add(series, count, time.time())
    e.evaluate(tick=True)
    assert e.signals["goal.quarantine-small.off"] == 0, count
    p.measurements.add(series, count + 1, time.time() + 1)
    e.evaluate(tick=True)
    assert e.signals["goal.quarantine-small.off"] == 1


# ---- flakes open, the hours main stays broken and a flake stays unfixed (dev/records/regression-flake-measures.md)

def moved(*steps) -> list[dict]:
    """Moves as `ergostat item ID --json` gives them, in the record's order: (to, hour) each."""
    out, was = [], None
    for to, h in steps:
        out.append({"from": was, "to": to, "time": 1000.0 + h * 3600})
        was = to
    return out


def test_main_repair_hours_from_the_first_break(tmp_path, monkeypatch):
    """Two breaks, one fix: the stay is measured from the first break (a repeat move into main-broken, as a record may
    carry it, keeps the clock); and the real record's moves of break, break, fix are one stay, from its first move."""
    flakes = flake_record(tmp_path, monkeypatch)
    assert flakes.stays(moved(("main-broken", 0), ("main-broken", 5), ("fixed", 10)), "main-broken") == [
        (1000.0 + 36000, 10.0)]
    iid = f"flake/{flakes.fac.slug(FLAKY, 80)}"
    flakes.say("flake.main-broken", FLAKY, main="m1", gaps=["gap/a"], main_broken_at=10.0)
    flakes.say("flake.main-broken", FLAKY, main="m2", gaps=["gap/b"], main_broken_at=50.0)
    flakes.fac.add("flake.main-fixed", iid, main_fixed_at=60.0, fixed_by="main-mend")
    moves = flake_now(flakes)["moves"]
    assert [m["to"] for m in moves][-1] == "fixed"
    got = flakes.stays(moves, "main-broken")
    assert got == [(float(moves[-1]["time"]), (float(moves[-1]["time"]) - float(moves[0]["time"])) / 3600)]
    monkeypatch.setattr(flakes, "read", lambda iid: {"moves": moved(("main-broken", 0), ("main-broken", 5),
                                                                    ("fixed", 10))})
    monkeypatch.setattr(flakes.fac, "items", lambda kind, state=None: [{"id": iid}])
    assert flakes.reading("main-repair-hours", 1000.0 + 11 * 3600) == 10.0


def test_a_remake_is_a_new_stay(tmp_path, monkeypatch):
    """A flake fixed then broken (or seen) again starts a new stay: two stays, each its own hours; a seen stay that
    went to main-broken ended unfixed, and the main-broken stay starts at that move."""
    flakes = flake_record(tmp_path, monkeypatch)
    m = moved(("main-broken", 0), ("fixed", 2), ("main-broken", 10), ("fixed", 13))
    assert [h for _, h in flakes.stays(m, "main-broken")] == [2.0, 3.0]
    m = moved(("seen", 0), ("seen", 1), ("fixed", 4), ("seen", 20), ("main-broken", 22), ("fixed", 30))
    assert [h for _, h in flakes.stays(m, "seen")] == [4.0]
    assert [h for _, h in flakes.stays(m, "main-broken")] == [8.0]
    iid = f"flake/{flakes.fac.slug(FLAKY, 80)}"                      # the real record: break, fix, break again, fix
    for n in (1, 2):
        flakes.say("flake.main-broken", FLAKY, main=f"m{n}", gaps=[f"gap/{n}"], main_broken_at=float(n))
        flakes.fac.add("flake.main-fixed", iid, main_fixed_at=float(n), fixed_by="main-mend")
    moves = flake_now(flakes)["moves"]
    assert len(flakes.stays(moves, "main-broken")) == 2, moves
    monkeypatch.setattr(flakes, "read", lambda iid: {"moves": moved(("main-broken", 0), ("fixed", 2),
                                                                    ("main-broken", 10), ("fixed", 14))})
    monkeypatch.setattr(flakes.fac, "items", lambda kind, state=None: [{"id": iid}])
    assert flakes.reading("main-repair-hours", 1000.0 + 15 * 3600) == 3.0         # the median of 2 and 4


def test_no_ended_stay_has_no_value(tmp_path, monkeypatch, capsys):
    """Nothing ended fixed (a flake seen, one main-broken), nothing ended inside the 14 days, or a flake that cannot
    be read: no value (SystemExit), never 0; past READ_MOST flakes it says so."""
    flakes = flake_record(tmp_path, monkeypatch)
    flakes.say("flake.seen", FLAKY, gaps=["gap/a"], times=1, seen_at=1.0)
    flakes.say("flake.main-broken", "tests/test_x.py::test_z", main="m1", gaps=["gap/b"], main_broken_at=1.0)
    for name in ("main-repair-hours", "flake-fix-hours"):
        with pytest.raises(SystemExit, match="no value"):
            flakes.reading(name, time.time())
    flakes.fac.add("flake.fixed", f"flake/{flakes.fac.slug(FLAKY, 80)}", fixed_by="green-runs")
    assert flakes.reading("flake-fix-hours", time.time()) >= 0
    with pytest.raises(SystemExit, match="no value"):
        flakes.reading("flake-fix-hours", time.time() + 15 * 86400)       # (ended, but before the window)
    real = flakes.read
    monkeypatch.setattr(flakes, "read", lambda iid: None if iid.endswith("z") else real(iid))
    with pytest.raises(SystemExit, match="could not be read"):
        flakes.reading("flake-fix-hours", time.time())
    monkeypatch.setattr(flakes, "READ_MOST", 1)
    monkeypatch.setattr(flakes, "read", real)
    assert flakes.reading("flake-fix-hours", time.time()) >= 0            # (the fixed one, test_y, first by id)
    with pytest.raises(SystemExit, match="no value"):
        flakes.reading("main-repair-hours", time.time())
    assert "2 flakes, the first 1 by id read" in capsys.readouterr().err


def test_flakes_few_names_the_oldest(tmp_path):
    """check finds no error, and on the parts and the flake kind only the findings the definition's allows-findings
    line allows; nothing reads either goal (unserved until regression-guarantees-wired); the setpoints are the
    parameters; flakes-open's two flows add up to it (in at seen, out at every move out of seen); and flakes-few, on
    the real model's parts and flake kind, goes off naming the seen flakes past it, oldest first (a fixed or
    main-broken one never)."""
    import yaml

    from ergostat import model as mdl
    from ergostat.spec.goal_per import worst
    from ergostat.spec.items import in_states
    from ergostat.spec.items import moved as moves_of
    from ergostat.store import Project
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    mine = {"stock.flakes-open", "stock.flakes-open-hours", "flow.flakes-seen", "flow.flakes-fixed",
            "auxiliary.main-repair-hours", "auxiliary.flake-fix-hours", "parameter.flake-hours-most",
            "parameter.main-repair-hours-most", "goal.flakes-few", "goal.main-repaired-fast", "items.flake",
            "system.guarantees"}
    allowed = module("fac").allowances((ROOT / "dev" / "records" / "regression-flake-measures.md").read_text())
    got = [f"{p.code} {p.about}: {p}" for p in problems if p.about in mine and f"{p.code} {p.about}" not in allowed]
    assert not got, "\n".join(got)
    assert mine - {"items.flake", "system.guarantees"} <= {f"{k}.{n}" for k, d in (
        ("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries), ("parameter", spec.parameters),
        ("goal", spec.goals)) for n in d}
    gone = {"oldest-flake-fix", "main-repair-hasten", "time-to-main-broken", "flake-fix-time"}
    assert not gone & {*spec.blocks, *spec.parameters}                          # (no person block asks on them)
    assert spec.flows["main-tests-broken"].source is None                       # (main's chain as main has it)
    few, fast = spec.goals["flakes-few"], spec.goals["main-repaired-fast"]
    assert (few.per, few.on_stale, fast.on_stale, fast.of.name) == ("item", "off", "off", "main-repair-hours")
    assert few.hold.value == spec.parameters["flake-hours-most"].value
    assert fast.hold.value == spec.parameters["main-repair-hours-most"].value == 24
    parts = yaml.safe_load((ROOT / "dev" / "model" / "guarantees-flakes.yaml").read_text())
    text = (ROOT / "ergostat.yaml").read_text()                      # (the kind as text: YAML 1.1 reads `on:` as true)
    (tmp_path / "ergostat.yaml").write_text("name: f\nitems:" + text[text.index("\n  flake:\n"):
                                                                     text.index("\n  intervention:\n")] + "\n" +
                                            yaml.safe_dump({"stocks": parts["stocks"], "goals": {
                                                "flakes-few": parts["goals"]["flakes-few"]}}, sort_keys=False))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for n, (event, hours) in enumerate((("flake.seen", 50), ("flake.seen", 1), ("flake.seen", 80),
                                        ("flake.main-broken", 90), ("flake.seen", 20)), 1):
        p.events.add(event, item=f"flake/t{n}", data={"test": f"t{n}"}, at=now - hours * 3600)
    p.events.add("flake.fixed", item="flake/t5", at=now - 3600)
    for event, hours in (("flake.seen", 30), ("flake.main-broken", 20), ("flake.main-fixed", 2)):   # seen, main's, fixed
        p.events.add(event, item="flake/t6", data={"test": "t6"}, at=now - hours * 3600)
    p.events.add("flake.fixed", item="flake/t4", at=now - 5 * 3600)          # main-broken first, then fixed
    p.events.add("flake.main-broken", item="flake/t5", data={"test": "t5"}, at=now - 1800)   # a remake, from fixed
    for event, hours in (("flake.seen", 10), ("flake.main-broken", 5)):     # seen, then main's, not fixed yet
        p.events.add(event, item="flake/t7", data={"test": "t7"}, at=now - hours * 3600)
    value, breaking, n = worst(p.model.spec, p.model.spec.goals["flakes-few"], None, p.events, now)
    assert [b["item"] for b in breaking] == ["flake/t3", "flake/t1"] and n == 2 and round(value) == 80
    counted = {}
    for name in ("flakes-seen", "flakes-fixed"):          # each flow's own sensor, as the model writes it, over it all
        q = next(iter(spec.flows[name].sensors.values())).items
        key, state = ("to", q["entering"]) if q.get("entering") else ("from", q["leaving"])
        counted[name] = len(moves_of(p.events, p.model.spec, "flake", key, state, 0.0, now + 1, q.get("where")))
    # t6 and t7 left seen once each (t7 not fixed: a sensor entering fixed would miss it); t4, main-broken first, is
    # drawn as arriving in seen and leaving it at once (the kind's first state); t5's remake from fixed straight into
    # main-broken is neither: 7 in, 4 out, 3 seen
    assert counted == {"flakes-seen": 7, "flakes-fixed": 4}
    assert in_states(p.events, p.model.spec, "flake", ["seen"], until=now + 1)[0] == 7 - 4


def pools_module():
    sys.modules.setdefault("fac", module("fac"))       # (pools.py imports fac and risk from beside it)
    sys.modules.setdefault("risk", module("risk"))
    return module("pools")


def gap(n: int, state: str = "approved", at: float = 100.0, **f) -> dict:
    """A gap: approved or merged (approved first), parked, or with no verdict yet (ready, fix)."""
    times = {"approved": ["approved_at"], "merged": ["approved_at", "merged_at"], "parked": ["parked_at"]}
    return {"id": f"gap/g{n}", "state": state, "last": at + n,
            "fields": {**{k: at + n for k in times.get(state, [])}, **f}}


def intervention(n: int, at: float = 100.0, **f) -> dict:
    return {"id": f"intervention/i{n}", "state": "open", "fields": {"recorded_at": at + n, **f}}


def clean(n: int, at: float = 100.0) -> list[dict]:
    """n gaps merged with nothing wrong, the first at ``at``."""
    return [gap(i, "merged", at=at) for i in range(n)]


def test_risk_counts_factory_caused_interventions_and_escapes_not_review_findings():
    risk = module("risk")
    gaps = [gap(1), gap(2, "parked", parked_by="review"), gap(3, "merged", reverted=True),
            gap(4, "merged", broke_main=True), gap(5, "merged"), gap(6, "merged"), gap(7, "merged"),
            gap(8, "fix", findings=["a blocking finding"]),                  # sent back: no verdict yet, not processed
            gap(9, "ready", caused_by="gap/g6")]                             # a later gap names g6 as its cause
    ivs = [intervention(1, **{"class": "environment-defect"}), intervention(2, factory=True),
           intervention(3, **{"class": "queue-interleaving"}), intervention(4, **{"class": "review-finding"}),
           intervention(5, **{"class": "park"}), intervention(6, **{"class": "worktree"}, caused_by="gap/g5")]
    upgrades = [{"state": "reverted", "fields": {"gap": "gap/g7"}}]
    ev = risk.evidence(gaps, ivs, upgrades, [])
    assert ev == {1: [3, 7, 5, 5]}       # 3 factory-caused of 7 processed; escapes g3, g4, g5, g6, g7 of 5 merged
    assert risk.evidence(gaps, ivs[3:], [], [])[1][0] == 0                  # findings and parks are no harm
    quiet = risk.evidence([*clean(7), gaps[1]], [], [], [])
    assert quiet == {1: [0, 8, 0, 7]}
    hurt, calm = risk.table(ev, 2, 6)[1], risk.table(quiet, 2, 6)[1]
    assert hurt["risk"] > calm["risk"] and hurt["bound"] > calm["bound"]
    assert hurt["per_day"] == 4 and hurt["risk"] == round(sum(r[0] for r in hurt["rates"].values()) * 4, 3)
    assert ivs[0]["fields"]["class"] in risk.FACTORY and not risk.factory_caused(ivs[3])
    own = [intervention(7, **{"class": "queue"}), intervention(8, **{"class": "switch"})]   # the factory's own records
    assert risk.evidence(gaps, [*ivs, *own], upgrades, [])[1][0] == 5
    assert risk.table(risk.evidence(gaps, [*ivs, *own], upgrades, []), 2, 6)[1]["bound"] > hurt["bound"]
    # main failing its suites after a merge (onmain.py's main-broken intervention, `main` its commit): an escape of
    # the gap(s) whose merge made that commit, counted once each, at the pool size of their merge, not as factory harm
    merged = [gap(1, "merged", main_sha="aaaa1111bbbb2222"), gap(2, "merged", main_sha="cccc3333dddd4444"),
              gap(3, "merged", at=1000, main_sha="cccc3333dddd4444")]          # g2 and g3 landed in one batch
    broke = intervention(9, at=2000, main="cccc3333dddd", gaps=["gap/g8"], **{"class": "main-broken"})
    assert risk.evidence(merged, [], [], [[500, 2]]) == {1: [0, 2, 0, 2], 2: [0, 1, 0, 1]}
    assert risk.evidence(merged, [broke], [], [[500, 2]]) == {1: [0, 2, 1, 2], 2: [0, 1, 1, 1]}
    assert risk.evidence(merged, [broke, {**broke, "id": "intervention/i10"}], [], [[500, 2]])[1][2] == 1
    unknown = intervention(9, at=2000, main="eeee5555", **{"class": "main-broken"})   # no merge found: still counted
    assert risk.evidence(merged, [unknown], [], [[500, 2]]) == {1: [0, 2, 0, 2], 2: [0, 1, 1, 1]}


def test_an_untried_pool_size_has_a_wide_bound_and_is_not_jumped_to():
    risk = module("risk")
    ev = risk.evidence(clean(40), [], [], [])                  # 40 clean gaps, all at a pool of 1
    tab = risk.table(ev, 4, 24)
    per_gap = {n: sum(r[1] for r in tab[n]["rates"].values()) for n in tab}
    assert per_gap[1] < per_gap[2] < per_gap[3]               # each size above the largest tried: a wider bound
    assert risk.target(tab, 100, 10) == 4
    assert risk.step(1, tab, 100, 10, 99, 3)[:2] == ("raise", 2)            # one step, never straight to the target
    tried = risk.evidence([*clean(40), *clean(40, at=1000)], [], [], [[500, 2]])   # 40 more, run at 2
    assert sum(r[1] for r in risk.table(tried, 4, 24)[2]["rates"].values()) < per_gap[2] / 2   # evidence narrows it
    assert risk.size_at([[500, 2], [900, 3]], 700) == 2 and risk.size_at([[500, 2]], 10) == 1


def test_target_is_the_largest_pool_within_tolerance_and_demand():
    risk = module("risk")
    tab = {n: {"bound": b} for n, b in {1: 0.5, 2: 1.5, 3: 1.9, 4: 2.5}.items()}
    assert risk.target(tab, 2, 10) == 3
    assert risk.target(tab, 2, 2) == 2 and risk.target(tab, 2, 0) == 1    # not above the ready and fix gaps
    assert risk.target(tab, 0.1, 10) == 1                                   # at least 1
    assert risk.target({**tab, 2: {"bound": 9}}, 2, 10) == 1                # every step on the way within it
    real = risk.table(risk.evidence(clean(60), [], [], []), 4, 2)
    within = [n for n in real if real[n]["bound"] <= 2]
    assert risk.target(real, 2, 10) == max(within) and real[max(within) + 1]["bound"] > 2


def test_raising_the_tolerance_raises_the_target(tmp_path):
    risk = module("risk")
    assert risk.tolerance() == 2                                             # the model's, the owner's default
    model = tmp_path / "pools.yaml"
    model.write_text("parameters:\n  risk-tolerance:\n    value: 6\n    unit: interventions/day\n")
    assert risk.tolerance(model) == 6
    assert risk.tolerance(tmp_path / "missing.yaml") == 0                    # not read: the pools go down to 1
    tab = risk.table(risk.evidence(clean(60), [], [], []), 4, 2)          # a gap every 2 hours
    assert risk.target(tab, risk.tolerance(), 10) < risk.target(tab, risk.tolerance(model), 10)


def test_risk_over_tolerance_lowers_the_pool_at_once(tmp_path):
    risk = module("risk")
    tab = {n: {"bound": b} for n, b in {1: 0.5, 2: 1.5, 3: 2.1}.items()}
    assert risk.step(3, tab, 2, 10, 0, 3)[:2] == ("lower", 2)               # at once: no probation for a drop
    assert risk.step(3, tab, 2.2, 10, 0, 3)[0] is None                      # within it: held
    assert risk.step(3, tab, 2.2, 1, 0, 3)[:2] == (None, 3)                 # demand alone never lowers it
    f = Factory(tmp_path)
    t0 = time.time() - 1000                         # 40 clean gaps at a pool of 1, 4 hours each from ready to merged
    f.fold([{"event": "gap.merged", "item": f"gap/c{i}", "data": {"ready_at": t0 + i - 4 * 3600, "approved_at": t0 + i,
                                                                    "merged_at": t0 + i}} for i in range(40)], None)
    for role in ("implementor", "reviewer"):
        subprocess.run([sys.executable, str(BIN / "pools.py"), "set", role, "2", "test"], cwd=f.model, env=f.env,
                       check=True, capture_output=True)
    said, lines = f.run("pools.py", argv=("tune",))                        # nothing ready: target 1, but held
    held = next(x["data"] for x in lines if x.get("event") == "pool.measured")
    assert "pool.lowered" not in said and held["demand"] == 0 and held["target"] == 1 and held["risk_bound"] <= 2
    code = ("import sys; sys.path[:0] = [sys.argv[1]]; import fac, queue; "
            "queue.block(fac.config(), {}, 'a push failed')")                # the queue's own intervention
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    f.fold([json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")], None)
    said, lines = f.run("pools.py", argv=("tune",))
    assert said[0] == "pool.lowered" and f.item("pool/implementor")["fields"]["pool"] == 1
    got = json.loads((f.model / "run" / "pools.json").read_text())
    assert (got["implementor"], got["reviewer"]) == (1, 1)                  # the reviewer follows it down
    low = [x["data"] for x in lines if x.get("event") == "pool.lowered"]
    assert [x["pool"] for x in low] == [1, 1] and f.item("pool/reviewer")["fields"]["pool"] == 1   # each its event
    assert low[0]["risk_bound"] > low[0]["tolerance"] == 2 and {"rates", "demand", "target"} <= set(low[0])
    assert "acts" not in f.db()                                              # a drop asks no one
    r = subprocess.run([sys.executable, str(BIN / "pools.py"), "raise", "implementor", "2", "3", "stale"],
                       cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 1 and json.loads((f.model / "run" / "pools.json").read_text())["implementor"] == 1


def test_probation_after_a_raise():
    risk = module("risk")
    tab = {n: {"bound": 0.1} for n in (1, 2, 3, 4)}
    assert risk.step(2, tab, 2, 10, 2, 3) == (None, 2, "on probation: 2 of 3 gaps since the last raise")
    assert risk.step(2, tab, 2, 10, 3, 3)[:2] == ("raise", 3)
    assert risk.processed_since([gap(1), gap(5, "parked"), gap(9, "fix")], 103) == 1   # verdicts since the raise


def test_an_approved_raise_is_decided_again_under_the_lock(tmp_path, monkeypatch):
    pools = pools_module()
    cfg = {"paths": {"run": str(tmp_path)}, "pools": {"implementor_max": 4, "reviewer_max": 2, "probation": 3}}
    m = {"table": {2: {"bound": 1.0}, 3: {"bound": 1.0}}, "tolerance": 2, "since_raise": 3}
    monkeypatch.setattr(pools.fac, "items", lambda kind: [])
    monkeypatch.setattr(pools, "measured", lambda cfg, st, gaps: m)     # what the record says when it is approved
    assert pools.raise_pool(cfg, "implementor", 1, 2, "approved") == 0
    got = pools.state(cfg)
    assert (got["implementor"], got["reviewer"]) == (2, 2)              # the reviewer pool comes up with it
    assert got["raised_at"] > 0 and got["history"][-1][1] == 2          # the probation starts
    assert pools.raise_pool(cfg, "implementor", 2, 4, "a jump") == 1     # one step at a time
    m["table"][3]["bound"] = 2.5                                         # the bound crossed since it was asked
    assert pools.raise_pool(cfg, "implementor", 2, 3, "late") == 1 and pools.state(cfg)["implementor"] == 2
    m["table"][3]["bound"], m["since_raise"] = 1.0, 2                   # the probation not over
    assert pools.raise_pool(cfg, "implementor", 2, 3, "early") == 1 and pools.state(cfg)["implementor"] == 2
    m["since_raise"] = 3
    assert pools.raise_pool(cfg, "implementor", 2, 3, "due") == 0
    assert (pools.state(cfg)["implementor"], pools.state(cfg)["reviewer"]) == (3, 2)   # the reviewer at its most
    assert pools.raise_pool(cfg, "reviewer", 2, 3, "past its most") == 1


def test_pools_set_by_hand_keeps_the_cap(tmp_path):
    pools = pools_module()
    assert pools.most({"pools": {"implementor_max": 5000}}, "implementor") == pools.HARD
    f = Factory(tmp_path)
    for want, asked in ((4, "9"), (1, "0"), (2, "2")):
        r = subprocess.run([sys.executable, str(BIN / "pools.py"), "set", "implementor", asked, "test"],
                           cwd=f.model, env=f.env, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr
        assert json.loads((f.model / "run" / "pools.json").read_text())["implementor"] == want   # within 1 and 4


def test_a_run_waits_its_turn_in_the_pool(tmp_path):
    f = Factory(tmp_path)
    lease = lambda t: {"lease": {"block": "implementor", "holder": f"run-{t}", "taken": t}}  # noqa: E731
    f.fold([{"event": "gap.requested", "item": "gap/a", "data": lease(1)},
            {"event": "gap.requested", "item": "gap/b", "data": lease(2)}], None)
    code = ("import sys; sys.path[:0] = [sys.argv[1]]; import fac, pools; cfg = fac.config(); "
            "print(pools.my_turn(cfg, 'implementor', 'implementor', 'gap/a'), "
            "pools.my_turn(cfg, 'implementor', 'implementor', 'gap/b'))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.stdout.split() == ["True", "False"], r.stderr                     # a pool of 1: the first taken goes on


def long_record(tmp_path, monkeypatch, n: int = 600):
    """A real project (no fake ergostat) with gap/long: a build at its start, then ``n`` events after it, so the build
    is outside the last 500 that `ergostat item --json` carries; and gap/short, three events."""
    from ergostat import model as mdl
    from ergostat.store import Project
    (tmp_path / "ergostat.yaml").write_text("name: timer\nitems:\n  gap:\n    id: gap/*\n    states: [ready, building, built]\n"
                                            "    on: {gap.ready: ready, gap.started: building, gap.built: built}\n")
    p = Project(mdl.load(tmp_path))
    p.events.add("gap.ready", item="gap/long", source="test", at=100.0)
    p.events.add("gap.built", item="gap/long", source="test", data={"build_hours": 0.5}, at=200.0)
    for i in range(n):
        p.events.add("gap.noted", item="gap/long", source="test", data={"i": i}, at=300.0 + i)
    for t, e in ((100.0, "gap.ready"), (110.0, "gap.started"), (120.0, "gap.built")):
        p.events.add(e, item="gap/short", source="test", data={"build_hours": 0.25} if e == "gap.built" else {}, at=t)
    monkeypatch.setenv("ERGOSTAT_CMD", f"{sys.executable} -m ergostat -C {tmp_path}")
    monkeypatch.setenv("ERGOSTAT_NO_SOCKET", "1")
    sys.modules.setdefault("fac", module("fac"))
    return module("times")


def test_the_timer_reads_a_gap_past_500_events(tmp_path, monkeypatch):
    """timer-long-records: past 500 events the record is read whole through the real `ergostat event` (it was
    `ergostat events`, not a command), so the build at its start is counted."""
    times = long_record(tmp_path, monkeypatch)
    d = json.loads(times.fac.ergostat("item", "gap/long", "--json").stdout)
    assert d["record_total"] == 602 and len(d["record"]) == 500                # cut short: the build is not in it
    assert times.timing(d)["gates"]["implementor"] == {"minutes": 30.0, "at": 200.0}
    marks = tmp_path / "times.json"
    gaps = json.loads(times.fac.ergostat("item", "--kind", "gap", "--json").stdout)["items"]
    assert times.write(gaps, marks) == 2
    assert json.loads(marks.read_text())["gap/long"] == 603                     # read, and its own gap.timed counted


def test_one_unreadable_gap_does_not_stop_the_timer(tmp_path, monkeypatch, capsys):
    """timer-long-records: a gap that cannot be read (here: not in the record, `ergostat item` exits 2) keeps its
    bookmark and fails the run by name, after every other gap was timed and the bookmark saved."""
    times = long_record(tmp_path, monkeypatch, n=0)
    gaps = json.loads(times.fac.ergostat("item", "--kind", "gap", "--json").stdout)["items"]
    gone = {"id": "gap/gone", "kind": "gap", "state": "ready", "events": 4, "fields": {}}
    marks = tmp_path / "times.json"
    with pytest.raises(SystemExit) as e:
        times.write([gone, *gaps], marks)                                       # the unreadable one is read first
    assert "gap/gone" in str(e.value) and "gap/long" not in str(e.value)
    said = {json.loads(x)["item"] for x in capsys.readouterr().out.splitlines()}
    assert said == {"gap/long", "gap/short"}                                    # both others timed
    assert json.loads(marks.read_text()) == {"gap/long": 3, "gap/short": 4}     # saved; gap/gone read again next run


def test_a_long_gap_past_its_ceiling_or_a_full_page_is_unreadable_not_half_read(tmp_path, monkeypatch):
    """timer-long-records: a gap past LONGEST is not read, and one whose record grows past the page while it is read
    (here: 1,000 events said between `ergostat item` and `ergostat event`) is unreadable, not timed from a cut page."""
    from ergostat import model as mdl
    from ergostat.store import Project
    times = long_record(tmp_path, monkeypatch)
    d = json.loads(times.fac.ergostat("item", "gap/long", "--json").stdout)
    monkeypatch.setattr(times, "LONGEST", 601)
    with pytest.raises(ValueError, match="past the 601"):
        times.timing(d)
    monkeypatch.setattr(times, "LONGEST", 100_000)
    real = times.fac.ergostat

    def growing(*args, **kw):
        if args[:1] == ("event",):
            p = Project(mdl.load(tmp_path))
            for i in range(1000):
                p.events.add("gap.noted", item="gap/long", source="test", data={"i": i}, at=5000.0 + i)
        return real(*args, **kw)
    monkeypatch.setattr(times.fac, "ergostat", growing)
    with pytest.raises(ValueError, match="grew past 1602"):
        times.timing(d)


def test_setpoints_refuse_a_model_with_no_stamp_line(tmp_path, monkeypatch):
    """timer-long-records: with its `# setpoints:` line gone, `times.py setpoints` fails and writes nothing, rather
    than setting holds with no record of when."""
    times = long_record(tmp_path, monkeypatch, n=0)
    copy = tmp_path / "times.yaml"
    copy.write_text(before := times.GOALS.read_text().replace("# setpoints:", "# set:"))
    monkeypatch.setattr(times, "GOALS", copy)
    monkeypatch.setattr(times.fac, "items", lambda kind, state=None: [])
    with pytest.raises(SystemExit, match="no `# setpoints:` line"):
        times.setpoints(time.time())
    assert copy.read_text() == before


def test_setpoints_record_when_they_were_derived(tmp_path, monkeypatch):
    """timer-long-records: `times.py setpoints` rewrites the model's `# setpoints:` line (first guesses until then)."""
    times = long_record(tmp_path, monkeypatch, n=0)
    copy = tmp_path / "times.yaml"
    copy.write_text(times.GOALS.read_text())
    assert "# setpoints: first guesses, never derived" in copy.read_text()
    monkeypatch.setattr(times, "GOALS", copy)
    monkeypatch.setattr(times.fac, "items", lambda kind, state=None: [])
    times.setpoints(time.mktime((2026, 11, 21, 12, 0, 0, 0, 0, -1)))
    assert "# setpoints: derived from the record on 2026-11-21, over 0 gaps: 0 holds set" in copy.read_text()
    assert "first guesses, never derived" not in copy.read_text()


def fac_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return module("fac")


def test_names_and_definitions_stay_inside(tmp_path, monkeypatch):
    fac = fac_module(tmp_path, monkeypatch)
    for bad in ("../ergostat", "Main", "a/b", "-x", "x" * 65, "a b"):
        with pytest.raises(ValueError):
            fac.branch_of({"id": "gap/x", "fields": {"branch": bad}})
    assert fac.branch_of({"id": "gap/ok", "fields": {"branch": "ok-1"}}) == "ok-1"
    f = Factory(tmp_path / "f")
    code = ("import sys; sys.path[:0] = [sys.argv[1]]; import fac, brief; cfg = fac.config(); "
            "print([bool(brief.definition_text(cfg, w, 'alpha-thing')) for w in sys.argv[2:]])")
    d = f.model / "run" / "defs"
    d.mkdir(parents=True)
    (d / "ok.md").write_text("# ok\n")
    (f.model / "run" / "elsewhere.md").write_text("# no\n")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), "run/defs/ok.md", "/etc/hosts", "run/elsewhere.md",
                        "run/defs/../elsewhere.md", "inline text", "main:../../etc/hosts"], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "[True, False, False, False, False, False]", r.stderr


def test_a_session_that_fails_keeps_its_whole_reservation(tmp_path, monkeypatch):
    fac = fac_module(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "fac", fac)
    monkeypatch.setitem(sys.modules, "sessions", module("sessions"))           # (each session kept: sessions.py)
    cfg = {"paths": {"run": str(tmp_path / "run"), "live": str(tmp_path / "live")},
           "ai": {"mode": "container", "implementor_model": "opus", "implementor_session_usd": 5.0}}
    fake = type(sys)("agents")
    fake.token = lambda cfg: "t"
    def crash(*a, **k):
        raise RuntimeError("the implementor session ran past 10800s and was killed")
    fake.session = crash
    monkeypatch.setitem(sys.modules, "agents", fake)
    with pytest.raises(RuntimeError):
        fac.session(cfg, "implementor", "brief", tmp_path)
    assert fac.spent_today(cfg) == 5.0                                         # a timeout or crash: the whole most
    fake.session = lambda *a, **k: {"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.75}
    fac.session(cfg, "implementor", "brief", tmp_path)
    assert fac.spent_today(cfg) == 5.75                                        # a known cost: what it spent
    fake.token = lambda cfg: (_ for _ in ()).throw(RuntimeError("no session token"))
    with pytest.raises(RuntimeError):
        fac.session(cfg, "implementor", "brief", tmp_path)
    assert fac.spent_today(cfg) == 5.75                                        # refused before: nothing charged


def test_the_token_file_must_be_the_owners_alone(tmp_path, monkeypatch):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    tok = tmp_path / "claude-token"
    cfg = {"agents": {"token_file": str(tok)}}
    with pytest.raises(agents.Refused, match="claude setup-token"):
        agents.token(cfg)                                                      # missing: refused
    tok.write_text("secret-value-123\n")
    tok.chmod(0o644)
    with pytest.raises(agents.Refused) as e:
        agents.token(cfg)                                                      # readable by others: refused
    assert "secret-value-123" not in str(e.value)
    tok.chmod(0o600)
    assert agents.token(cfg) == "secret-value-123"
    args = agents.run_args({**cfg, "ai": {"reviewer_model": "opus", "reviewer_session_usd": 1}}, "reviewer",
                           tmp_path, "n")
    assert "secret-value-123" not in " ".join(args) and "CLAUDE_CODE_OAUTH_TOKEN" in args   # by name only
    assert f"{tmp_path}:/work:ro" in args and "--restricted" in args and "--network" in args
    assert not any(a.startswith(("-v", str(Path.home()))) and ".git" in a for a in args)


def test_the_queue_refuses_a_branch_moved_after_its_review(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    drop = tmp_path / "live" / "drop.git"
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", "-b", "factory/alpha-thing", str(drop), str(other)], check=True, env=f.env)
    (other / "late.txt").write_text("after the review\n")
    git(other, "add", "-A")
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "late"], check=True, env=f.env)
    git(other, "push", "-q", "origin", "factory/alpha-thing")
    said, _ = f.run("queue.py", gid)
    assert said == ["gap.queued", "gap.sent-back"] and "moved after the review" in f.item(gid)["fields"]["findings"][0]
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "start"


def test_failing_fast_suites_park_the_gap(tmp_path):
    f = Factory(tmp_path, unit="exit 1")
    gid = ready(f)
    for _ in range(f.gates["build_failures"] - 1):
        said, lines = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.measured"] and any("nack" in x for x in lines)
    said, _ = f.run("implement.py", gid)
    assert said[-1] == "gap.parked" and f.item(gid)["fields"]["parked_in"] == "building"   # never stuck


def test_build_failures_add_up_in_the_real_fold(tmp_path):
    """implement.py's own events, folded by ergostat's fold (spec.changes.fold_event) with the gap kind's rules from
    ergostat.yaml: each failed build adds one, and a later successful build resets nothing (dev/README.md)."""
    from ergostat.spec.changes import fold_event
    passes = tmp_path / "passes"
    f = Factory(tmp_path, unit=f"test -e {passes}", build_failures=6)
    gid = ready(f)
    rules, doc = read(ROOT / "ergostat.yaml")[0].items["gap"].fold, {}
    assert rules.get("build_failures") == "sum"
    for n in (1, 2, 3):
        said, lines = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.measured"]
        for e in lines:
            if e.get("event") and (e.get("item") or gid) == gid:
                assert fold_event(doc, e, rules)[1] is None
        assert doc["build_failures"] == n == f.item(gid)["fields"]["build_failures"]
    passes.write_text("")
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    for e in lines:
        if e.get("event") and (e.get("item") or gid) == gid:
            fold_event(doc, e, rules)
    assert doc["build_failures"] == 3                                     # a success resets nothing


def test_the_sixth_failed_build_parks_the_gap(tmp_path):
    f = Factory(tmp_path, unit="exit 1", build_failures=6)
    gid = ready(f)
    for n in range(1, 6):
        said, lines = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.measured"] and any("nack" in x for x in lines)
        assert f.item(gid)["fields"]["build_failures"] == n
    said, _ = f.run("implement.py", gid)
    gap = f.item(gid)
    assert said[-2:] == ["gap.measured", "gap.parked"] and gap["state"] == "parked"
    assert gap["fields"]["parked_for"] == "kill-rule" and "failed 6 times" in gap["fields"]["where_it_stopped"]


def test_a_committed_scratch_file_is_refused_before_the_suites(tmp_path):
    log = tmp_path / "suite-runs.log"
    f = Factory(tmp_path, unit=f"echo ran >> {log}")
    gid = ready(f)
    scratch = "tests/_probe_test.py,.scratch/floors.py,tests/test_a_probe.py,app.py.orig"
    said, lines = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=scratch)   # (suite_fix_rounds 0: no next round)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert "refused before the suites" in nack["why"] and all(p in nack["why"] for p in scratch.split(","))
    assert f.item(gid)["fields"]["suites_fast"]["stray"] == sorted(scratch.split(","))
    assert not log.exists()                                                   # the suites never ran

    f.config.write_text(f.config.read_text().replace("suite_fix_rounds = 0", "suite_fix_rounds = 1"))
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=scratch)      # the next round is told, and removes them
    gap = f.item(gid)["fields"]
    assert said == ["gap.started", "gap.built"] and gap["sessions"] == 1 + 2 and gap["build_failures"] == 1
    assert not gap.get("failed_gates") and log.read_text() == "ran\n"         # no review round counted; suites ran once
    files = git(tmp_path / "live" / "drop.git", "ls-tree", "-r", "--name-only", "factory/alpha-thing").splitlines()
    assert not set(scratch.split(",")) & set(files) and "standin/work.txt" in files


def test_a_new_top_level_file_not_in_the_definition_is_refused(tmp_path):
    f = Factory(tmp_path)
    d = tmp_path / "instance" / "run" / "defs"
    d.mkdir(parents=True)
    (d / "alpha-thing.md").write_text("# alpha thing\n\n## Definition of done\n\nIt works.\n\n## Files to touch\n\n"
                                      "- `standin/work.txt` (new)\n- `newdir/x.py` (new)\n- `app.py`\n\n"
                                      "## Size budget\n\n600 net lines.\n")
    f.run("intake.py")
    gid = "gap/alpha-thing"
    said, lines = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="newdir/x.py,docs/more.md,notes.txt,extra/y.py")
    assert said == ["gap.started", "gap.measured"]
    assert f.item(gid)["fields"]["suites_fast"]["stray"] == ["extra/y.py", "notes.txt"]   # named, or under main's: kept
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import implement; from pathlib import Path; "
            "no_files = '# x\\n\\n## Definition of done\\n\\nIt works.\\n'\n"
            "print(json.dumps(implement.strays(json.loads(sys.argv[3]), Path(sys.argv[2]), 'main', "
            "'factory/alpha-thing', no_files)))")
    drop = str(tmp_path / "live" / "drop.git")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), drop, "{}"], capture_output=True, text=True, env=f.env)
    assert json.loads(r.stdout) == []                                         # no Files to touch: nothing to compare
    bad = json.dumps({"gates": {"scratch_patterns": "tmp*"}})
    r = subprocess.run([sys.executable, "-c", code, str(BIN), drop, bad], capture_output=True, text=True, env=f.env)
    assert r.returncode and "scratch_patterns must be a list" in r.stderr     # a bad setting stops, never passes


# The strays committed on 2026-11-21's branches (review findings and their removal commits). Seven are on the record;
# the eighth is tests/_probe_test.py, the earlier finding the stray-files gate was built from (the audit's list itself
# is not in the repository). operating-states.md.tail is taken to sit beside its definition, under docs/.
REAL_STRAYS = ["tests/test_zz_scratch.py", "tests/test_zz_profile_tmp.py",
               "docs/roadmap/overnight/operating-states.md.tail", "scratch_probe.py", ".bench/test_bench_detach.py",
               ".mut/mut.py", "tests/test_probe_tmp.py", "tests/_probe_test.py"]


def strays_of(f: Factory, cfg: dict, definition: str, fn: str = "strays") -> list[str]:
    """implement.strays (or unlisted) on the drop's factory/alpha-thing against main, in a process of its own."""
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import implement; from pathlib import Path; "
            "a = (json.loads(sys.argv[3]),) if sys.argv[5] == 'strays' else (); "
            "print(json.dumps(getattr(implement, sys.argv[5])(*a, Path(sys.argv[2]), 'main', 'factory/alpha-thing', "
            "sys.argv[4])))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(f.tmp / "live" / "drop.git"), json.dumps(cfg),
                        definition, fn], capture_output=True, text=True, env=f.env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_gate_catches_the_eight_real_strays(tmp_path):
    import tomllib
    f = Factory(tmp_path)
    gid = ready(f)
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=",".join(REAL_STRAYS))
    assert said == ["gap.started", "gap.measured"]                              # refused before the suites
    assert f.item(gid)["fields"]["suites_fast"]["stray"] == sorted(REAL_STRAYS)
    real = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())           # the factory's own setting, and the default
    listed = "# x\n\n## Definition of done\n\nIt works.\n\n## Files to touch\n\n`standin/work.txt`, `tests/test_x.py`.\n"
    for cfg in (real, {}):
        for definition in ("# x\n\n## Definition of done\n\nIt works.\n", listed):
            assert sorted(strays_of(f, cfg, definition)) == sorted(REAL_STRAYS)


def test_a_file_the_definition_names_is_not_refused(tmp_path):
    f = Factory(tmp_path)
    d = tmp_path / "instance" / "run" / "defs"
    d.mkdir(parents=True)
    (d / "alpha-thing.md").write_text("# alpha thing\n\n## Definition of done\n\nIt works.\n\n## Files to touch\n\n"
                                      "- `standin/work.txt` (new)\n- `scripts/load_probe.py` (new)\n- `tests/test_zz_last.py`"
                                      "\n- `scripts/bench/` (new)\n\n## Size budget\n\n600 net lines.\n")
    f.run("intake.py")
    gid = "gap/alpha-thing"
    named = "scripts/load_probe.py,tests/test_zz_last.py,scripts/bench/run_tmp.py"   # each matches a scratch pattern
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=named + ",docs/loose.md")
    assert said == ["gap.started", "gap.built"] and not f.item(gid)["fields"]["suites_fast"].get("stray")
    definition = (d / "alpha-thing.md").read_text()
    loose = ["dev/records/alpha-thing.md", "docs/loose.md"]                  # (its own definition is shown too)
    assert strays_of(f, {}, definition) == [] and sorted(strays_of(f, {}, definition, "unlisted")) == loose
    said, _ = f.run("review.py", gid)                     # a new file matching no pattern, named by no Files to touch:
    text = (tmp_path / "instance" / "run" / "briefs" / "alpha-thing-reviewer-1.md").read_text()   # shown to the reviewer
    shown = text.split('## New files the definition\'s "Files to touch" does not name\n\n', 1)[1].split("\n\n", 1)[0]
    assert sorted(shown.splitlines()) == [f"- `{p}`" for p in loose]


def on_main(f: Factory, *paths: str) -> None:
    """Files committed on main and pushed (the main the drop's branches are made from)."""
    for p in paths:
        (f.checkout / p).parent.mkdir(parents=True, exist_ok=True)
        (f.checkout / p).write_text("on main\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "main moves")
    git(f.checkout, "push", "-q", "origin", "main")


def test_a_build_adding_a_check_finding_is_sent_back(tmp_path):
    log = tmp_path / "suite-runs.log"
    f = Factory(tmp_path, unit=f"echo ran >> {log}")
    on_main(f, "found/model-x@stock.a")
    gid = ready(f)
    writes = "found/model-x@stock.a,found/model-x@stock.b,found/unit-unknown"   # main's, its code on another part, new
    said, lines = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=writes)     # (suite_fix_rounds 0: no next round)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert "new `ergostat check` findings: model-x stock.b, unit-unknown" in nack["why"]
    assert f.item(gid)["fields"]["suites_fast"]["findings"] == ["model-x stock.b", "unit-unknown"]
    assert not log.exists()                                                   # the suites never ran

    f.config.write_text(f.config.read_text().replace("suite_fix_rounds = 0", "suite_fix_rounds = 1"))
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=writes)       # the next round is given the list:
    gap = f.item(gid)["fields"]                                # (the stand-in removes a finding only if its brief lists it)
    assert said == ["gap.started", "gap.built"] and gap["sessions"] == 1 + 2 and log.read_text() == "ran\n"

    for side in ("main and the branch", "the branch"):        # lesson-3: a check that cannot run never passes
        g = Factory(tmp_path / side.replace(" ", "-"), unit=f"echo ran >> {log}")
        if side.startswith("main"):                           # (the branch holds main: broken on both)
            on_main(g, "found/broken")
        said, lines = g.run("implement.py", ready(g), FACTORY_STANDIN_WRITES="" if side.startswith("main") else "found/broken")
        assert said == ["gap.started", "gap.measured"]
        why = next(x["nack"] for x in lines if "nack" in x)["why"]
        assert f"could not compare: `ergostat check` said nothing readable on {side}" in why, why
    assert log.read_text() == "ran\n"


def test_an_allowed_finding_passes_and_is_shown_to_the_reviewer(tmp_path):
    f = Factory(tmp_path)
    d = tmp_path / "instance" / "run" / "defs"
    d.mkdir(parents=True)
    (d / "alpha-thing.md").write_text("# alpha thing\n\nallows-findings: [model-x stock.b: its loop is the next gap, "
                                      "model-y stock.c:]\n\n## Definition of done\n\nIt works.\n\n## Size budget\n\n"
                                      "600 net lines.\n")
    f.run("intake.py")
    gid = "gap/alpha-thing"
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="found/model-x@stock.b")
    assert said == ["gap.started", "gap.built"]
    assert f.item(gid)["fields"]["allowed_findings"] == ["model-x stock.b: its loop is the next gap"]
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved"
    text = (tmp_path / "instance" / "run" / "briefs" / "alpha-thing-reviewer-1.md").read_text()
    assert "allowed by the definition (judge its reason): model-x stock.b: its loop is the next gap" in text
    fac = module("fac")                                       # a reason left out allows nothing
    assert fac.allowances((d / "alpha-thing.md").read_text()) == {"model-x stock.b": "its loop is the next gap"}
    assert fac.allowances("# x\n\n## Definition of done\n\nIt works.\n") == {}
    assert fac.allowances("allows-findings: [unit-unknown: a unit for later, a b: why]\n") == {
        "unit-unknown": "a unit for later", "a b": "why"}                   # a finding about no part: its code alone


def test_record_dependent_findings_are_not_counted(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    writes = "found/calibration-worse-than-mean@flow.x,found/fit-unknown@model,found/extremes-running,found/takes-order-unset@block.b"
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES=writes)
    assert said == ["gap.started", "gap.built"]
    fac = module("fac")
    out = json.dumps({"found": [{"code": c, "about": "x"} for c in ("calibration-worse-than-mean", "calibrations")]})
    assert fac.findings(f"uv: noise\n{out}\n", fac.RECORD_FINDINGS) == {"calibrations x"}   # by code, not prefix
    assert fac.findings("Traceback: no output\n", fac.RECORD_FINDINGS) is None

    for unfinished, built in (("branch", True), ("", False)):   # extreme-conditions tests finished in check's wait
        g = Factory(tmp_path / f"x-{unfinished or 'none'}")        # differ with load (either side's note: the same)
        on_main(g, "found/extreme-conditions@stock.a")
        writes = "found/extreme-conditions@stock.b" + ",found/extremes-running" * (unfinished == "branch")
        said, _ = g.run("implement.py", ready(g), FACTORY_STANDIN_WRITES=writes)
        assert said == ["gap.started", "gap.built" if built else "gap.measured"], unfinished  # compared only when both


T ="tests/test_x.py::test_y"
TEST_Y = "def test_y():\n    assert False\n"


def suite_sh(tmp: Path, fails: str) -> Path:
    """A stand-in for the unit suite and its `alone` run: each run logged (where, and the tests it was given), and
    failing T while the shell test ``fails`` holds in the folder it runs in."""
    sh = tmp / "suite.sh"
    sh.write_text(f"#!/bin/sh\necho \"$PWD $*\" >> {tmp}/runs.log\nif {fails}; then echo 'FAILED {T} - boom'; exit 1; fi\n"
                  "echo '1 passed'\n")
    sh.chmod(0o755)
    return sh


def runs(tmp: Path) -> list[str]:
    log = tmp / "runs.log"
    return log.read_text().splitlines() if log.exists() else []


def test_a_failure_on_main_too_waits_for_main(tmp_path):
    sh = suite_sh(tmp_path, "[ -e broken ]")
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    (f.checkout / "broken").write_text("main's own failure\n")
    (f.checkout / "tests").mkdir()
    (f.checkout / "tests" / "test_x.py").write_text(TEST_Y)                  # (only a test main has can be main's)
    git(f.checkout, "add", "broken", "tests")
    git(f.checkout, "commit", "-q", "-m", "main breaks a test")
    git(f.checkout, "push", "-q", "origin", "main")
    main = git(f.checkout, "rev-parse", "main")
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "intervention.recorded", "gap.measured"] and f.flakes_said() == ["flake.main-broken"]
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert nack["count"] is False and "waits for main to move" in nack["why"]
    gap = f.item(gid)["fields"]
    assert gap["waits_on_main"] == main and gap["main_broken_tests"] == [T] and not gap.get("build_failures")
    assert f.item("flake/tests-test-x-py-test-y")["state"] == "main-broken"
    iv = f.item(f"intervention/main-broken-{main[:12]}")
    assert iv["state"] == "open" and iv["fields"]["class"] == "main-broken" and iv["fields"]["gaps"] == [gid]
    alone = [r for r in runs(tmp_path) if r.endswith(T)]
    assert len(runs(tmp_path)) == 3 and len(alone) == 2                    # the suite, alone on the branch, on main
    assert sum("-main-" in r for r in alone) == 1                           # one run on main for the failure
    takes = read(ROOT / "ergostat.yaml")[0].blocks["implementor"].takes
    assert takes.where.get("waits_on_main", "unset") is None                # the implementor skips it meanwhile
    said, _ = f.run("intake.py")
    assert "gap.measured" not in said                                       # main has not moved: still waits
    git(f.checkout, "rm", "-q", "broken")
    git(f.checkout, "commit", "-q", "-m", "main fixed")
    git(f.checkout, "push", "-q", "origin", "main")
    said, _ = f.run("intake.py")
    assert said == ["gap.measured"] and f.item(gid)["fields"]["waits_on_main"] is None
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]                             # retried once main moved


def test_a_failure_that_passes_on_main_is_counted(tmp_path):
    sh = suite_sh(tmp_path, "[ -d standin ]")                              # (the stand-in's work: on the branch only)
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    on_main_files(f, {"tests/test_x.py": TEST_Y})                         # (main has it: run there)
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert not f.item(gid)["fields"].get("waits_on_main") and "flake/tests-test-x-py-test-y" not in f.db()["items"]
    assert [r for r in runs(tmp_path) if "-main-" in r and r.endswith(T)]   # it was run on main, and passed there
    for _ in range(f.gates["build_failures"] - 1):
        said, _ = f.run("implement.py", gid)
    assert said[-1] == "gap.parked"                                         # counted, as before


def test_a_test_main_does_not_have_is_never_mains_failure(tmp_path):
    """main-broken-needs-the-test-on-main: a test failing everywhere it runs, but whose file (or function) main does
    not have, is the gap's: counted, never run on main, no main-broken item, and the gap told so."""
    for case, files in (("no file", {}), ("renamed", {"tests/test_x.py": "def test_other():\n    assert False\n"})):
        where = tmp_path / case.replace(" ", "-")
        where.mkdir()
        sh = suite_sh(where, "true")                                       # (it would fail on main too, if run)
        f = Factory(where, unit=str(sh), alone=str(sh))
        if files:
            on_main_files(f, files)
        main = git(f.checkout, "rev-parse", "main")
        gid = ready(f)
        said, lines = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1, case
        gap = f.item(gid)["fields"]
        assert not gap.get("waits_on_main") and gap["main_broken_tests"] == [] and not f.flakes_said(), case
        assert gap["suites_fast"]["not_on_main"] == {T: gid} and gap["suites_fast"]["main_broken"] is False
        assert not [r for r in runs(where) if "-main-" in r], case          # never run on main
        why = next(x["nack"] for x in lines if "nack" in x)["why"]
        assert f"not on main {main[:12]}, so not main's: {T} (this gap)" in why, why


def test_a_stacked_gaps_failure_from_its_base_names_the_base(tmp_path):
    sh = suite_sh(tmp_path, "true")
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    base_gap(f, "beta-base", {"tests/test_x.py": TEST_Y}, rank=1)           # the test is the base's, not main's
    gid = stacked(f, "gap/beta-base")
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    gap = f.item(gid)["fields"]
    assert gap["suites_fast"]["not_on_main"] == {T: "gap/beta-base"} and not gap.get("waits_on_main")
    assert not f.flakes_said() and not [r for r in runs(tmp_path) if "-main-" in r]
    assert f"{T} (its base gap/beta-base)" in next(x["nack"] for x in lines if "nack" in x)["why"]


def test_a_gap_held_on_a_test_main_does_not_have_is_released(tmp_path):
    """An existing main-broken hold (waits_on_main) on a test its main commit lacks stops holding the gap at once;
    one on a test main has still waits for main to move."""
    f = Factory(tmp_path)
    on_main_files(f, {"tests/test_x.py": TEST_Y})
    main = git(f.checkout, "rev-parse", "main")
    gid = ready(f)
    f.fold([{"event": "gap.measured", "item": gid, "data": {"waits_on_main": main, "main_broken_tests": [T]}}], None)
    said, _ = f.run("intake.py")
    assert "gap.measured" not in said and f.item(gid)["fields"]["waits_on_main"] == main     # main's own: held
    gone = "tests/test_control_spike.py::test_gate_cost_per_event"
    f.fold([{"event": "gap.measured", "item": gid, "data": {"main_broken_tests": [T, gone]}}], None)
    said, _ = f.run("intake.py")
    gap = f.item(gid)["fields"]
    assert said == ["gap.measured"] and gap["waits_on_main"] is None and gap["not_on_main"] == {gone: gid}


def test_present_reads_the_test_at_the_commit(tmp_path, monkeypatch):
    f = Factory(tmp_path)
    on_main_files(f, {"tests/test_x.py": "class TestA:\n    async def test_b(self):\n        pass\n\n"
                                         "def test_y_more():\n    pass\n"})
    monkeypatch.setattr(sys, "path", [*sys.path, str(BIN)])     # (appended: dev/bin/queue.py must not shadow queue)
    onmain = module("onmain")
    yes = ("tests/test_x.py::TestA::test_b", "tests/test_x.py::TestA::test_b[1-2]")
    no = ("tests/test_x.py::test_y", "tests/test_x.py::TestB::test_b", "tests/test_gone.py::test_b", "tests/test_x.py")
    assert all(onmain.present(f.checkout, "main", t) for t in yes)
    assert not any(onmain.present(f.checkout, "main", t) for t in no)
    assert not onmain.present(f.checkout, "0" * 40, yes[0]) and not onmain.present(f.checkout, "", yes[0])  # unreadable


def on_main_files(f: Factory, files: dict[str, str]) -> None:
    for p, text in files.items():
        (f.checkout / p).parent.mkdir(parents=True, exist_ok=True)
        (f.checkout / p).write_text(text)
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "main has tests")
    git(f.checkout, "push", "-q", "origin", "main")


def test_a_flake_in_the_fast_suites_is_retried(tmp_path):
    sh = suite_sh(tmp_path, f"[ ! -e {tmp_path}/once ] && touch {tmp_path}/once")   # fails its first run only
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    gid = ready(f)
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"] and f.flakes_said() == ["flake.seen"]
    assert f.item(gid)["fields"]["flakes"] == [T] and not f.item(gid)["fields"].get("build_failures")
    assert f.item("flake/tests-test-x-py-test-y")["state"] == "seen"
    assert not [r for r in runs(tmp_path) if "-main-" in r]                # passed alone: never run on main


def test_no_reruns_past_the_building_hours(tmp_path):
    sh = suite_sh(tmp_path, "true")
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    gid = ready(f)
    f.fold([{"event": "gap.measured", "item": gid, "data": {"build_hours": f.gates["build_hours"] - 0.001}}], None)
    said, _ = f.run("implement.py", gid)                                    # (3.6 seconds left: no room for a rerun)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert len(runs(tmp_path)) == 1 and "no building hours" in f.item(gid)["fields"]["suites_fast"]["not_checked"]


def test_a_gap_past_its_build_hours_is_parked(tmp_path):
    """The kill rule's `build_hours` (implement.py): a gap whose building reached the limit is parked with the kill
    rule's reason and starts no session; one just under it is built."""
    limit = Factory.GATES["build_hours"]
    for hours, parked in ((limit, True), (limit - 0.001, False)):
        where = tmp_path / str(parked)
        where.mkdir()
        f = Factory(where)
        gid = ready(f)
        f.fold([{"event": "gap.measured", "item": gid, "data": {"build_hours": hours}}], None)
        said, lines = f.run("implement.py", gid)
        gap = f.item(gid)
        session = any(x.get("type") == "result" for x in lines)              # (the stand-in session's cost line)
        if parked:
            assert said == ["gap.parked"] and not session and gap["state"] == "parked"
            assert gap["fields"]["parked_for"] == "kill-rule" and gap["fields"]["parked_in"] == "building"
            assert f"past the kill rule's {limit:g}" in gap["fields"]["where_it_stopped"]
            assert not (where / "live" / "drop.git").exists() or not git(
                where / "live" / "drop.git", "branch", "--list", "factory/alpha-thing")   # no branch pushed
        else:
            assert said == ["gap.started", "gap.built"] and session and gap["state"] == "built"


def quarantined(tmp: Path, says: str, rc: int = 0, on_main: bool = True) -> Factory:
    """A factory whose main quarantines T (``on_main``; else main has no list and T fails only where a
    tests/quarantine.txt is in the tree): the unit suite fails T unless it is deselected, and the run of the
    quarantined tests (`alone`, and triage's `rerun`) prints ``says`` and exits ``rc``."""
    unit, alone = tmp / "unit.sh", tmp / "alone.sh"
    guard = "" if on_main else '[ -f tests/quarantine.txt ] || { echo "1 passed"; exit 0; }\n'
    unit.write_text(f'#!/bin/sh\necho "unit $*" >> {tmp}/runs.log\n{guard}case "$*" in *"--deselect {T}"*) echo'
                    f' "1 passed"; exit 0;; esac\necho "FAILED {T} - boom"; exit 1\n')
    (tmp / "alone.out").write_text(says)
    alone.write_text(f'#!/bin/sh\necho "alone $*" >> {tmp}/runs.log\ncat {tmp}/alone.out\nexit {rc}\n')
    for sh in (unit, alone):
        sh.chmod(0o755)
    f = Factory(tmp, unit=str(unit), alone=str(alone))
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"', f'rerun = "{alone} {{tests}}"'))
    if not on_main:
        return f
    (f.checkout / "tests").mkdir()
    (f.checkout / "tests" / "quarantine.txt").write_text(f"# test | who | when | why\n{T} | t | 2026-11-21 | flaky\n")
    git(f.checkout, "add", "tests")
    git(f.checkout, "commit", "-q", "-m", "quarantine T")
    git(f.checkout, "push", "-q", "origin", "main")
    return f


def last_runs(lines: list[dict]) -> list[str]:
    return [x["data"]["last_run"] for x in lines if x.get("event") == "flake.measured" and "last_run" in x["data"]]


def test_a_quarantined_test_does_not_block_the_queue(tmp_path):
    f = quarantined(tmp_path, f"FAILED {T} - boom\n", rc=1)            # T fails every run
    gid = ready(f)
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "flake.measured", "gap.built"]
    f.run("review.py", gid)
    said, lines = f.run("queue.py", gid)
    assert said == ["gap.queued", "flake.measured", "gap.merged", "gap.push-asked"] and last_runs(lines) == ["fail"]
    unit = [r for r in runs(tmp_path) if r.startswith("unit ")]
    assert len(unit) == 2 and all(r.endswith(f"--deselect {T}") for r in unit)     # deselected from both suites
    assert [r for r in runs(tmp_path) if r.startswith("alone ")] == [f"alone {T} -rA"] * 2   # run beside each


def test_a_skipped_quarantined_test_is_not_a_pass(tmp_path, monkeypatch):
    f = quarantined(tmp_path, f"SKIPPED [1] {T.split('::')[0]}:3: no port\n1 skipped\n")    # exits 0
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert "gap.built" in said and last_runs(lines) == ["unknown"]
    flake = f.item("flake/tests-test-x-py-test-y")["fields"]
    assert flake["last_run"] == "unknown" and flake["quarantined"] is True
    fac = fac_module(tmp_path, monkeypatch)
    assert fac.outcomes(f"PASSED {T}\n", [T]) == {T: "pass"}                        # (what a pass looks like)
    assert fac.outcomes(f"PASSED {T}\nERROR {T} - teardown\n", [T]) == {T: "fail"}  # passed, then errored
    assert fac.outcomes("", [T]) == {T: "unknown"}                                  # an empty log
    def gone(_):
        raise FileNotFoundError("no suite")
    assert fac.quarantine(f.checkout, "main") == [T] and fac.quarantine(f.checkout, "nowhere") == []
    assert fac.beside([T], tmp_path / "never.txt", gone) == {T: "unknown"}          # a run that never ran


def test_the_quarantine_list_parses_with_who_when_why():
    """Each line of the real tests/quarantine.txt is `test id | who | when | why`: an id naming a test that exists,
    who added it, an ISO date and a reason, all four given; and the id is what fac.quarantine reads."""
    import datetime
    text = (ROOT / "tests" / "quarantine.txt").read_text()
    lines = [x for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    for line in lines:
        fields = [x.strip() for x in line.split("|")]
        assert len(fields) == 4 and all(fields), line
        test, who, when, why = fields
        path, name = test.split("::")
        assert f"def {name}(" in (ROOT / path).read_text(), test                    # a test that exists
        datetime.date.fromisoformat(when)
    ids = [x.split("|")[0].strip() for x in lines]
    assert len(set(ids)) == len(ids)                                                # each test listed once


def test_a_quarantined_failure_is_recorded(tmp_path):
    f = quarantined(tmp_path, f"FAILED {T} - boom\n", rc=1)
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    flake = f.item("flake/tests-test-x-py-test-y")["fields"]
    assert last_runs(lines) == ["fail"] and flake["last_run"] == "fail" and flake["test"] == T
    assert f"FAILED {T}" in Path(flake["last_run_log"]).read_text()                 # read from the run's whole log
    f.run("review.py", gid)
    git(f.checkout, "fetch", "-q", str(tmp_path / "live" / "drop.git"), "factory/alpha-thing")  # (as the queue does)
    pre = git(f.checkout, "rev-parse", "main")                                      # a queue failure naming T (a run
    f.fold([{"event": "gap.queue-failed", "item": gid, "data": {"failed_suite": "unit", "failed_tests": [T],  # from
                                                                 "pre": pre}}], None)                # before the list)
    said, lines = f.run("triage.py", gid)
    assert said == ["flake.measured", "gap.retried"] and last_runs(lines) == ["fail"]   # no flake seen for it,
    assert f.item(gid)["state"] == "approved" and not f.item(gid)["fields"].get("retries")   # and no retry spent
    assert [r for r in runs(tmp_path) if r.startswith("alone ")][-1] == f"alone {T} -rA"   # never rerun as blocking


def test_a_branch_cannot_quarantine_its_own_failing_test(tmp_path):
    f = quarantined(tmp_path, f"PASSED {T}\n", on_main=False)          # main lists nothing; T fails beside a list
    f.fold([{"event": "flake.measured", "item": "flake/old", "data": {"test": "tests/old.py::test_z",  # released by
                                                                       "quarantined": True}}], None)   # hand on main
    gid = ready(f)
    f.run("implement.py", gid)
    assert f.item("flake/old")["fields"]["quarantined"] is False                  # no longer listed: released
    work = tmp_path / "home" / "work"                                               # the branch quarantines T itself
    git(tmp_path, "clone", "-q", "-b", "factory/alpha-thing", str(tmp_path / "live" / "drop.git"), str(work))
    (work / "tests").mkdir()
    (work / "tests" / "quarantine.txt").write_text(f"{T} | me | 2026-11-21 | in my way\n")
    git(work, "add", "tests")
    git(work, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "quarantine my test")
    git(work, "push", "-q", "origin", "factory/alpha-thing")
    f.fold([{"event": "gap.measured", "item": gid, "data": {"head": git(work, "rev-parse", "HEAD")}}], None)
    f.run("review.py", gid)
    assert f.item(gid)["fields"]["reviewed_head"] == git(work, "rev-parse", "HEAD")
    (tmp_path / "rerun.sh").write_text(f'echo "rerun $*" >> {tmp_path}/runs.log\nif [ -e tests/quarantine.txt ]; then '
                                       f'echo "FAILED {T} - boom"; exit 1; fi\necho "PASSED {T}"\n')
    f.config.write_text(f.config.read_text().replace(f'rerun = "{tmp_path / "alone.sh"} {{tests}}"',  # (T fails alone on
                                                     f'rerun = "sh {tmp_path / "rerun.sh"} {{tests}}"'))  # the branch: no
    # flake; it passes on main, which lists nothing: not main's)
    said, _ = f.run("queue.py", gid)
    assert said[:2] == ["gap.queued", "gap.queue-failed"] and f.item(gid)["fields"]["failed_tests"] == [T]  # red
    unit = [r for r in runs(tmp_path) if r.startswith("unit ")]
    assert "--deselect" not in unit[-1] and not [r for r in runs(tmp_path) if r.startswith("alone ")]
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, agents; from pathlib import Path; "
            "h = Path(sys.argv[2]); print(json.dumps(agents.suites(fac.config(), h, ('unit',), h, 'own')))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(work.parent)], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    assert json.loads(r.stdout.strip().splitlines()[-1])["unit"]["rc"] == 0       # the implementor's own run: held
    assert f"--deselect {T}" in runs(tmp_path)[-1] and not runs(tmp_path)[-1].startswith("alone ")   # back, unrun


def test_upgrades_follow_the_pushed_main(tmp_path):
    f = Factory(tmp_path)
    said, lines = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened"] and lines[0]["data"]["sha"] == git(f.origin, "rev-parse", "main")
    (f.checkout / "x.txt").write_text("merged, not pushed\n")
    git(f.checkout, "add", "-A")
    subprocess.run(["git", "-C", str(f.checkout), "commit", "-q", "-m", "local"], check=True, env=f.env)
    assert f.run("upgrade.py", argv=["watch"])[0] == []                        # a local merge opens nothing
    git(f.checkout, "push", "-q", "origin", "main")
    said, lines = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened"] and lines[0]["data"]["sha"] == git(f.origin, "rev-parse", "main")


def land(f: Factory, *names: str) -> dict[str, tuple[str, str]]:
    """Each branch (a commit of its own off main) merged onto main --no-ff, as the queue merges, then pushed together
    as one batch: {name: (its merge, its head)}; each gap's record carries its reviewed head and the batch's head."""
    got = {}
    for n in names:
        git(f.checkout, "checkout", "-q", "-b", n, "main")
        (f.checkout / f"{n}.txt").write_text(f"{n}\n")
        git(f.checkout, "add", "-A")
        git(f.checkout, "commit", "-q", "-m", n)
        head = git(f.checkout, "rev-parse", "HEAD")
        git(f.checkout, "checkout", "-q", "main")
        git(f.checkout, "merge", "-q", "--no-ff", n, "-m", f"merge {n}")
        got[n] = (git(f.checkout, "rev-parse", "HEAD"), head)
    git(f.checkout, "push", "-q", "origin", "main")
    db, top = f.db(), got[names[-1]][0]
    for n, (_, head) in got.items():
        db["items"][f"gap/{n}"] = {"id": f"gap/{n}", "kind": "gap", "state": "merged",
                                   "fields": {"merged_at": 100.0, "reviewed_head": head, "main_sha": top}}
    f.record.write_text(json.dumps(db))
    return got


def revert(f: Factory, sha: str, merge: bool = True) -> str:
    git(f.checkout, "revert", "--no-edit", *(["-m", "1"] if merge else []), sha)
    git(f.checkout, "push", "-q", "origin", "main")
    return git(f.checkout, "rev-parse", "HEAD")


def test_a_revert_on_main_is_recorded_once_however_often_main_watch_runs(tmp_path):
    f = Factory(tmp_path)
    merge, _ = land(f, "alpha")["alpha"]
    rv = revert(f, merge)
    said, lines = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened", "gap.reverted"]
    g = f.item("gap/alpha")["fields"]
    assert g["reverted"] is True and g["revert_sha"] == rv and g["reverted_at"] > 0
    assert f.run("upgrade.py", argv=["watch"])[0] == []                       # nothing new on main: nothing said
    (f.model / "run" / "escapes.json").unlink()                                # main read again from its start
    assert f.run("upgrade.py", argv=["watch"])[0] == []                       # the gap is reverted already
    assert json.loads((f.model / "run" / "escapes.json").read_text())["last"] == rv
    risk = module("risk")
    assert risk.evidence(list(f.db()["items"].values()), [], [], [])[1][2] == 1
    readme = (ROOT / "dev" / "README.md").read_text()
    assert "reverts are found by `main-watch`" in readme


def test_a_revert_of_one_merge_of_a_batch_of_three_blames_only_that_gap(tmp_path):
    f = Factory(tmp_path)
    got = land(f, "one", "two", "three")                 # one batch: the three gaps share its head as main_sha
    revert(f, got["two"][0])                             # the middle merge: its main_sha is no gap's own
    said, _ = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened", "gap.reverted"]
    assert [g for g in ("one", "two", "three") if f.item(f"gap/{g}")["fields"].get("reverted")] == ["two"]
    revert(f, got["three"][0])                           # the batch's head: its reviewed head names three, not all
    assert f.run("upgrade.py", argv=["watch"])[0] == ["upgrade.opened", "gap.reverted"]
    assert [g for g in ("one", "two", "three") if f.item(f"gap/{g}")["fields"].get("reverted")] == ["two", "three"]


def test_an_unmatched_revert_still_counts_as_an_escape(tmp_path):
    f = Factory(tmp_path)
    land(f, "alpha")
    (f.checkout / "loose.txt").write_text("a commit straight on main, no gap's merge\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "loose")
    loose = git(f.checkout, "rev-parse", "HEAD")
    revert(f, loose, merge=False)
    said, _ = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened", "intervention.recorded"]
    iv = f.item(f"intervention/reverted-{loose[:12]}")
    assert iv["fields"]["class"] == "reverted-unmatched" and not f.item("gap/alpha")["fields"].get("reverted")
    (f.model / "run" / "escapes.json").unlink()
    assert f.run("upgrade.py", argv=["watch"])[0] == []                       # its id: a second read says nothing
    risk = module("risk")
    items = list(f.db()["items"].values())
    gaps, ivs = [i for i in items if i["kind"] == "gap"], [i for i in items if i["kind"] == "intervention"]
    assert risk.evidence(gaps, ivs, [], []) == {1: [0, 0, 1, 1]}               # an escape, no gap blamed
    assert risk.found_since(gaps, ivs, time.time() - 86400) == 1
    assert risk.found_since(gaps, ivs, time.time() + 60) == 0


def test_a_git_error_stops_only_the_escapes_step(tmp_path):
    f = Factory(tmp_path)
    (f.model / "run").mkdir()
    (f.model / "run" / "escapes.json").write_text("{not json")                 # the step cannot read where it was
    said, lines = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened"] and "escapes:" in f.stderr               # the upgrade still opened
    (f.model / "run" / "escapes.json").unlink()
    git(f.checkout, "commit", "-q", "--allow-empty", "-m", "more")
    git(f.checkout, "push", "-q", "origin", "main")
    root = git(f.checkout, "rev-list", "--max-parents=0", "main")
    (f.checkout / ".git" / "objects" / root[:2] / root[2:]).unlink()          # git cannot read main's history
    said, _ = f.run("upgrade.py", argv=["watch"])
    assert said == ["upgrade.opened"] and "escapes:" in f.stderr and "git" in f.stderr
    assert not (f.model / "run" / "escapes.json").exists()                     # nothing taken as read


def test_check_reports_no_flow_without_a_sensor_in_pools_yaml(tmp_path, capsys, monkeypatch):
    """escapes-found is measured (pools.py read escapes-day): of pools.yaml's flows, only factory-harm is still neither
    measured nor moved by a block (outside this gap); `ergostat check` says nothing of escapes-found (it says nothing
    of a flow without a sensor either: the first assertion is the one that fails without it); its sensor reads."""
    from ergostat.cli import main, spec_cmds
    from ergostat.numbers import extremes_cache
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(spec_cmds, "CHECK_WAIT", None)
    monkeypatch.setattr(extremes_cache, "BOUND", 900.0)
    spec, _ = read(ROOT / "ergostat.yaml")
    moved = {r.name for b in spec.blocks.values() for refs in b.outputs.values() for r in refs if r.kind == "flow"}
    mine = [x for x in spec.flows.values() if x.where and x.where.file.name == "pools.yaml"]
    assert "escapes-found" in {x.name for x in mine}
    assert {x.name for x in mine if not x.sensors and not x.equation and x.name not in moved} == {"factory-harm"}
    assert [s.run for s in spec.flows["escapes-found"].sensors.values()] == ["python3 dev/bin/pools.py read escapes-day"]
    main(["-C", str(factory_copy(tmp_path / "now")), "check", "--json"])
    got = json.loads(capsys.readouterr().out)
    assert [x for x in got["found"] if "escapes-found" in json.dumps(x)] == []
    f = Factory(tmp_path)
    db = f.db()
    db["items"]["gap/alpha"] = {"id": "gap/alpha", "kind": "gap", "state": "merged",
                                "fields": {"merged_at": 100.0, "reverted": True, "reverted_at": time.time()}}
    f.record.write_text(json.dumps(db))
    r = subprocess.run([sys.executable, str(BIN / "pools.py"), "read", "escapes-day"], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and float(r.stdout.strip()) == round(1 / 24, 4), r.stderr     # one a day, per hour


def fake_version(live: Path, sha: str, starts: bool) -> None:
    """A version whose `ergostat` is a script: it starts (writing the heartbeat) or fails to."""
    d = live / sha
    (d / ".venv" / "bin").mkdir(parents=True)
    (d / "dev").mkdir()
    (d / "ergostat.yaml").write_text("name: fake\n")
    log = live / "calls.log"
    (d / ".venv" / "bin" / "ergostat").write_text(f"""#!{sys.executable}
import json, os, sys, time, hashlib, pathlib
args = sys.argv[3:]
open({str(log)!r}, "a").write({sha!r} + " " + " ".join(args) + "\\n")
inst = pathlib.Path(sys.argv[2]).resolve()
state = pathlib.Path(os.environ["ERGOSTAT_HOME"]) / ("fake-" + hashlib.sha256(str(inst).encode()).hexdigest()[:8])
if args[:1] == ["run"] and "--stop" not in args:
    if not {starts!r}:
        sys.exit("does not start")
    state.mkdir(parents=True, exist_ok=True)
    (state / "heartbeat.json").write_text(json.dumps({{"pass": time.time() + 3600}}))
elif args[:1] == ["sensor"]:
    print(json.dumps({{"now": {{"readings": [{{"at": time.time(), "value": 0}}]}}}}))
elif args[:1] == ["item"]:
    print(json.dumps({{"items": []}}))
""")
    (d / ".venv" / "bin" / "ergostat").chmod(0o755)


def test_a_switch_to_a_version_that_will_not_start_reverts(tmp_path):
    f = Factory(tmp_path)
    live = tmp_path / "live"
    fake_version(live, "a" * 40, starts=True)
    fake_version(live, "b" * 40, starts=False)
    with f.config.open("a") as c:
        c.write("health_wait = 1\n")
    env = {**f.env, "ERGOSTAT_HOME": str(tmp_path / "home"), "FACTORY_CONFIG": str(f.config)}
    live_py = [sys.executable, str(BIN / "live.py")]
    inst = live / "instance"
    inst.mkdir(parents=True)
    (live / "current").symlink_to("a" * 40)
    subprocess.run([*live_py, "init"], cwd=inst, env=env, check=True, capture_output=True)
    subprocess.run([*live_py, "start"], cwd=inst, env=env, check=True, capture_output=True)
    r = subprocess.run([*live_py, "switch", "b" * 40], cwd=inst, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "does not start" in r.stdout
    assert os.readlink(live / "current") == "a" * 40                           # back on the version before
    calls = (live / "calls.log").read_text()
    assert f"{'a' * 40} run --port" in calls.splitlines()[-2] or "upgrade.reverted" in calls
    assert "upgrade.reverted" in calls


def docker_ready() -> bool:
    try:
        return all(subprocess.run(["docker", "image", "inspect", i], capture_output=True, timeout=20).returncode == 0
                   for i in ("ergostat-agent:latest", "ergostat-dev:latest"))
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the agent image (dev/agent/Dockerfile)")
def test_containers_reach_only_the_api_and_return_a_bundle(tmp_path):
    f = Factory(tmp_path)
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, agents; cfg = fac.config(); "
            "cfg['ai']['mode'] = 'container'; home, work = agents.clone(cfg, 'alpha-thing', 'implementor'); "
            "base = fac.git(work, 'rev-parse', 'origin/main'); was = agents.publish(cfg, work, 'alpha-thing'); "
            "(work / 'made-inside.txt').write_text('x'); "
            "print(json.dumps([agents.finish(cfg, home, 'alpha-thing', base, base, was=was), str(home)]))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    head, home = json.loads(r.stdout.strip().splitlines()[-1])
    drop = tmp_path / "live" / "drop.git"
    assert git(drop, "rev-parse", "factory/alpha-thing") == head                 # the bundle came back to the drop
    assert "made-inside.txt" in git(drop, "show", "--name-only", "--format=", head)
    check = tmp_path / "egress_check.py"
    check.write_text(
        "import socket, http.client\n"
        "def tunnel(h):\n"
        "    c = http.client.HTTPConnection('ergostat-egress', 3128, timeout=10); c.set_tunnel(h, 443)\n"
        "    try:\n        c.connect(); return True\n    except Exception:\n        return False\n"
        "def direct(h):\n"
        "    try:\n        socket.create_connection((h, 443), timeout=5); return True\n    except Exception:\n"
        "        return False\n"
        "print([tunnel('api.anthropic.com'), tunnel('github.com'), tunnel('example.com'), direct('github.com')])\n")
    r = subprocess.run(["docker", "run", "--rm", "--network", "ergostat-agents", "-v", f"{tmp_path}:/c:ro",
                        "ergostat-agent:latest", "python3", "/c/egress_check.py"], capture_output=True, text=True,
                       timeout=120)
    assert r.stdout.strip() == "[True, False, False, False]", r.stderr[-400:]   # the API alone


def test_an_overshoot_is_charged_on_the_sessions_day(tmp_path, monkeypatch):
    fac = fac_module(tmp_path, monkeypatch)
    cfg = {"paths": {"run": str(tmp_path / "run")}}
    at = fac.reserve(cfg, 1.0, role="implementor")
    fac.settle(cfg, 1.0, 1.5, at, role="implementor")
    assert fac.spent_today(cfg) == 1.5                                         # spent past the reservation: charged
    at = fac.reserve(cfg, 1.0, role="reviewer")
    fac.settle(cfg, 1.0, 0.25, at, role="reviewer")
    assert fac.spent_today(cfg) == 1.75
    rows = [json.loads(x) for x in (tmp_path / "run" / "costs.jsonl").read_text().splitlines()]
    assert rows[1]["at"] == rows[0]["at"] and rows[3]["at"] == rows[2]["at"]   # dated with its reservation


def merged(f: Factory) -> str:
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    said, _ = f.run("queue.py", gid)
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    return gid


def settle(f: Factory) -> tuple[list[str], str]:
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, queue; cfg = fac.config(); "
            "print(json.dumps({'why': queue.settle(cfg, fac.path(cfg, 'checkout'))}))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return f.fold([x for x in lines if "event" in x], None), lines[-1]["why"]


def set_action(f: Factory, state: str) -> None:
    db = f.db()
    aid = next(iter(db["actions"]))
    db["actions"][aid] = state
    f.record.write_text(json.dumps(db))


def test_a_denied_push_undoes_its_merge(tmp_path):
    f = Factory(tmp_path)
    gid = merged(f)
    said, why = settle(f)
    assert said == [] and "is held" in why                                     # one unpushed merge at a time
    set_action(f, "denied")
    said, why = settle(f)
    assert said == ["gap.sent-back"] and why is None and f.item(gid)["state"] == "fix"
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "start"     # the merge undone


def add_lines(f: Factory, files: dict[str, int], name: str = "alpha-thing") -> None:
    """Lines added on the gap's branch in the drop, the stand-in's note taken out (so only these lines count), and
    recorded as its built head (what the review judges)."""
    wt = f.tmp / f"edit-{len(list(f.tmp.glob('edit-*')))}"
    subprocess.run(["git", "clone", "-q", "-b", f"factory/{name}", str(f.tmp / "live" / "drop.git"), str(wt)],
                   check=True, capture_output=True)
    for rel, n in files.items():
        p = wt / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text((p.read_text() if p.exists() else "") + "x = 1\n" * n)
    git(wt, "rm", "-rq", "standin")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "lines")
    git(wt, "push", "-q", "origin", f"factory/{name}")
    f.fold([{"event": "gap.measured", "item": f"gap/{name}", "data": {"head": git(wt, "rev-parse", "HEAD")}}], None)


def queue_with(f: Factory, gid: str, patch: str = "") -> list[str]:
    """queue.py run in one process with ``patch`` applied first (e.g. a line count that raises)."""
    it = f.item(gid)
    given = {"trigger": "item", "item": it, "lease": {"fence": 1, "back": it["state"]}}
    code = f"import sys; sys.path[:0] = [{str(BIN)!r}]; import fac, queue\n{patch}\nsys.exit(queue.main())"
    r = subprocess.run([sys.executable, "-c", code], input=json.dumps(given), cwd=f.model, capture_output=True,
                       text=True, timeout=120, env={**f.env, "ERGOSTAT_ITEM": gid, "ERGOSTAT_LEASE": "1"})
    assert r.returncode == 0, r.stderr
    return f.fold([json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")], gid)


BOOM = "def boom(*a, **k):\n    raise RuntimeError('git diff failed')\nfac.net_lines = boom"


def merge_again(f: Factory, gid: str, files: dict[str, int], patch: str = "") -> list[str]:
    """The pending push denied (the merge undone, the gap sent back), then built, reviewed and merged again."""
    set_action(f, "denied")
    assert settle(f)[0] == ["gap.sent-back"]
    f.run("implement.py", gid)
    add_lines(f, files)
    f.run("review.py", gid)
    return queue_with(f, gid, patch)


def test_merge_records_merged_lines(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    f.run("implement.py", gid)
    add_lines(f, {"dev/bin/extra.py": 30, "ergostat/extra.py": 20, "tests/test_extra.py": 100})
    f.run("review.py", gid)
    assert f.run("queue.py", gid)[0] == ["gap.queued", "gap.merged", "gap.push-asked"]
    assert f.item(gid)["fields"]["merged_lines"] == 50 and f.item(gid)["fields"]["merged_lines_error"] is None
    assert merge_again(f, gid, {"dev/bin/extra.py": 10})[:2] == ["gap.queued", "gap.merged"]
    assert f.item(gid)["fields"]["merged_lines"] == 60             # the newer merge's count (from main before it)


def test_merge_stands_when_lines_unreadable(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    assert queue_with(f, gid, BOOM) == ["gap.queued", "gap.merged", "gap.push-asked"]
    gap = f.item(gid)
    assert gap["state"] == "merged" and gap["fields"]["merged_lines"] is None
    assert "git diff failed" in gap["fields"]["merged_lines_error"]
    assert git(f.checkout, "rev-parse", "main") == gap["fields"]["main_sha"]   # the merge stands


def test_a_merge_again_whose_count_fails_keeps_no_old_count(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    f.run("implement.py", gid)
    add_lines(f, {"dev/bin/extra.py": 40})
    f.run("review.py", gid)
    f.run("queue.py", gid)
    f.fold([{"event": "gap.measured", "item": gid, "data": {"planned_size": "S", "size_confidence": "high"}}], None)
    assert f.item(gid)["fields"]["merged_lines"] == 40
    assert merge_again(f, gid, {"dev/bin/extra.py": 5}, BOOM)[:2] == ["gap.queued", "gap.merged"]
    gap = f.item(gid)["fields"]
    assert gap["merged_lines"] is None and "git diff failed" in gap["merged_lines_error"]
    r = subprocess.run([sys.executable, str(BIN / "measure.py"), "size-accuracy"], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "no value yet" in r.stderr and gid in r.stderr    # left out, named, not a hit


def test_a_failed_push_blocks_the_queue_until_the_coordinator_looks(tmp_path):
    f = Factory(tmp_path)
    merged(f)
    set_action(f, "failed")
    said, why = settle(f)
    assert said == ["intervention.recorded"] and "failed" in why
    iid = next(i for i in f.db()["items"] if i.startswith("intervention/"))
    assert "blocked until" in settle(f)[1]                                     # still blocked
    f.fold([{"event": "intervention.remedied", "item": iid, "data": {"remedy": "pushed by hand"}}], None)
    said, why = settle(f)                                                      # (the action stays failed: it is)
    assert why is None and said == ["gap.push-settled"]                        # the remedy settles that merge
    assert settle(f) == ([], None)                                             # and the queue goes on, unblocked


def test_no_dead_letters(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    db = f.db()
    db["items"][gid]["fields"]["definition"] = "run/defs/missing.md"           # its definition gone: it cannot build
    db["items"][gid]["fields"]["branch"] = "gone-def"
    f.record.write_text(json.dumps(db))
    f.run("implement.py", gid, fails=True)                                     # not its last attempt: counted
    said, _ = f.run("implement.py", gid, lease={"attempt": 2, "attempts": 2})  # its last: parked, not a dead letter
    assert said[-1] == "gap.parked" and "Stopped on its last attempt" in f.item(gid)["fields"]["where_it_stopped"]
    assert f.item(gid)["fields"]["build_hours"] >= 0
    g = Factory(tmp_path / "g")
    gid = ready(g)
    g.run("implement.py", gid)
    said, _ = g.run("review.py", gid, lease={"attempt": 2, "attempts": 2}, FACTORY_STANDIN_VERDICT="nonsense")
    assert said[-1] == "gap.parked"                                            # an unparsable verdict, last attempt
    g.fold([{"event": "gap.requested", "item": "gap/lost", "data": {"source": "request"}}], None)
    db = g.db()
    db["items"]["gap/lost"]["state"] = "dead"
    g.record.write_text(json.dumps(db))
    said, _ = g.run("dead.py")
    assert said == ["gap.parked"] and g.item("gap/lost")["fields"]["parked_in"] == "dead-letter"


def test_a_revert_puts_back_the_instances_model_and_says_when_it_cannot(tmp_path):
    f = Factory(tmp_path)
    live = tmp_path / "live"
    fake_version(live, "a" * 40, starts=True)
    fake_version(live, "b" * 40, starts=False)
    with f.config.open("a") as c:
        c.write("health_wait = 1\n")
    env = {**f.env, "ERGOSTAT_HOME": str(tmp_path / "home")}
    live_py = [sys.executable, str(BIN / "live.py")]
    inst = live / "instance"
    inst.mkdir(parents=True)
    (live / "current").symlink_to("a" * 40)
    subprocess.run([*live_py, "init"], cwd=inst, env=env, check=True, capture_output=True)
    (inst / "dev" / "accepted-change.yaml").write_text("an edit made in the instance\n")
    r = subprocess.run([*live_py, "switch", "b" * 40], cwd=inst, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and os.readlink(live / "current") == "a" * 40
    assert (inst / "dev" / "accepted-change.yaml").is_file()                   # the instance's model as it ran
    assert "gap.requested" in (live / "calls.log").read_text()                 # its edit is a gap all the same
    (live / ("a" * 40) / ".venv" / "bin" / "ergostat").write_text(
        (live / ("b" * 40) / ".venv" / "bin" / "ergostat").read_text().replace("b" * 40, "a" * 40))
    r = subprocess.run([*live_py, "switch", "b" * 40], cwd=inst, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "did not start" in r.stderr                   # the revert's start failed twice
    calls = (live / "calls.log").read_text()
    assert "upgrade.failed" in calls and "intervention.recorded" in calls


@pytest.mark.slow
def test_a_switch_keeps_the_local_settings_and_makes_no_gap_of_them(tmp_path):
    f = Factory(tmp_path)
    live = tmp_path / "live"
    fake_version(live, "a" * 40, starts=True)
    fake_version(live, "b" * 40, starts=True)
    with f.config.open("a") as c:
        c.write("health_wait = 1\n")
    env = {**f.env, "ERGOSTAT_HOME": str(tmp_path / "home")}
    live_py = [sys.executable, str(BIN / "live.py")]
    inst = live / "instance"
    inst.mkdir(parents=True)
    (live / "current").symlink_to("a" * 40)
    subprocess.run([*live_py, "init"], cwd=inst, env=env, check=True, capture_output=True)
    local = "web: {names: [private-tunnel.example.org], open: read}\n"
    (inst / "ergostat.local.yaml").write_text(local)
    r = subprocess.run([*live_py, "switch", "b" * 40], cwd=inst, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and os.readlink(live / "current") == "b" * 40, r.stdout + r.stderr
    assert (inst / "ergostat.local.yaml").read_text() == local                  # kept across the switch
    assert "gap.requested" not in (live / "calls.log").read_text()              # and no gap made of it
    (inst / "ergostat.yaml").write_text("name: fake\n# an edit made in the instance\n")
    r = subprocess.run([*live_py, "switch", "a" * 40], cwd=inst, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and (inst / "ergostat.local.yaml").read_text() == local
    assert "gap.requested" in (live / "calls.log").read_text()                  # a model edit is a gap all the same,
    made = [p.read_text() for p in tmp_path.rglob("model-edit-*.md")]
    assert len(made) == 1 and "an edit made in the instance" in made[0]
    assert "private-tunnel" not in made[0] and "ergostat.local.yaml" not in made[0]   # with nothing of this machine's


@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the agent image (dev/agent/Dockerfile)")
def test_the_factorys_containers_are_counted_and_swept(tmp_path, monkeypatch):
    sys.modules.setdefault("fac", module("fac"))
    agents, load = module("agents"), module("load")
    name = "ergostat-factory-suite-testsweep"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    before = load.docker_suites()
    subprocess.run(["docker", "run", "-d", "--init", "--name", name, "--network", "none", "ergostat-agent:latest",
                    "sleep", "300"], check=True, capture_output=True)
    try:
        assert load.docker_suites() == before + 1                              # the interlock counts it
        assert "--init" in agents.LIMITS
        monkeypatch.setitem(agents.TIMEOUTS, "suite", -1200)                   # (as if it ran past its time)
        assert name in agents.sweep({})
        assert subprocess.run(["docker", "inspect", name], capture_output=True).returncode != 0
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


DEPS_GAPS = """\
# Known gaps

## Modelling

- **Warm workers** (parked on `warm`, *Where it stopped*): per-item state.
- **Remote systems** (open): composed. The rest comes after `warm`, and the cache needs `nosuch` first.
- **Layout rules** (open): see `docs/x.md`; the watchdog's last resort after `runner.kill_all()` stays.
- **Loop a** (open): after `loop-b`.
- **Loop b** (open): after `loop-a`.

| Branch | Gap | Depends on |
|---|---|---|
| `layout-rules` | layout | `remote-systems` |

## Done recently

- **Old** (done): after `warm`.
"""


def test_dependencies_are_read_conservatively_with_where_they_came_from(tmp_path, monkeypatch):
    fac_module(tmp_path, monkeypatch)
    sys.modules["fac"] = module("fac")
    deps = module("deps")
    parsed, own = deps.from_gaps(DEPS_GAPS)
    assert [n for n, _ in parsed["gap/remote-systems"]] == ["warm", "nosuch"]
    assert "gap/layout-rules" not in parsed                                    # not `runner.kill_all()`
    assert [n for n, _ in parsed["@layout-rules"]] == ["remote-systems"]       # the table
    assert own["gap/warm-workers"] == {"warm"} and "GAPS.md:" in parsed["gap/remote-systems"][0][1]
    assert deps.from_definition("# x\n\ndepends-on: [warm, `gap/loop-a`]\n") == ["warm", "gap/loop-a"]
    assert deps.from_definition("no line here") == []
    gaps = {f"gap/{g}": {"id": f"gap/{g}", "state": "open", "fields": {"branch": g}}
            for g in ("warm-workers", "remote-systems", "layout-rules", "loop-a", "loop-b", "asked")}
    gaps["gap/warm-workers"]["state"] = "parked"
    gaps["gap/warm-workers"]["fields"]["where_it_stopped"] = "per-item state leaked"
    gaps["gap/asked"]["fields"]["depends_on"] = ["gap/nowhere"]
    assert "'nosuch'" not in str(deps.plan(gaps, parsed, own, {"nosuch"})["gap/remote-systems"]["problems"])
    want = deps.plan(gaps, parsed, own)
    assert want["gap/remote-systems"]["depends_on"] == ["gap/warm-workers"]   # by the branch its entry names
    assert "'nosuch'" in want["gap/remote-systems"]["problems"][0]            # no gap: said, not dropped
    assert want["gap/layout-rules"]["depends_on"] == ["gap/remote-systems"]
    assert want["gap/loop-a"]["depends_on"] == ["gap/loop-b"]                  # the first link of the cycle stands
    assert want["gap/loop-b"]["depends_on"] == [] and "cycle" in want["gap/loop-b"]["problems"][0]
    assert "no gap" in want["gap/asked"]["problems"][0]
    assert "parked: per-item state leaked" in want["gap/remote-systems"]["blocked_reason"]
    assert "remote-systems" in deps.tree({k: {**g, "fields": {**g["fields"], "depends_on": want[k]["depends_on"]}}
                                          for k, g in gaps.items()})


def test_a_gap_is_taken_only_once_its_dependencies_merged_the_critical_first(tmp_path):
    from ergostat import model as mdl
    from ergostat import precedence as pr
    from ergostat.spec import items as its
    from ergostat.store import Project
    root = tmp_path / "m"
    root.mkdir()
    (root / "ergostat.yaml").write_text((ROOT / "ergostat.yaml").read_text())
    (root / "dev").symlink_to(ROOT / "dev")
    m = mdl.load(root)
    (tmp_path / "state").mkdir()
    p = Project(m, directory=tmp_path / "state")
    ev, spec = p.events, m.spec
    t = time.time() - 6000
    steps = ("gap.found", "gap.defined", "gap.started", "gap.built", "gap.review-started", "gap.approved",
             "gap.queued", "gap.merged")
    for n in range(4):                                     # a history: each state an hour, so the path is long
        for k, e in enumerate(steps):
            ev.add(e, item=f"gap/old{n}", at=t - 40000 + n + 3600 * k)
    for g in ("base", "lone", "mid", "top", "other"):
        ev.add("gap.found", item=f"gap/{g}", data={"source": "gaps"}, at=t)
        ev.add("gap.defined", item=f"gap/{g}", at=t + 1)
    ev.add("gap.dependencies", item="gap/mid", data={"depends_on": {"set": ["gap/base"]}}, at=t + 2)
    ev.add("gap.dependencies", item="gap/top", data={"depends_on": {"set": ["gap/mid"]}}, at=t + 2)
    ev.add("gap.dependencies", item="gap/other", data={"depends_on": {"set": ["gap/base"]}}, at=t + 2)
    take = spec.blocks["implementor"]
    ready = lambda now: [i for i in sorted(its.project(ev, spec, "gap"), key=lambda i: i.first)  # noqa: E731
                         if i.state in take.takes.at]
    got = [i.id for i in pr.order_ready(ev, spec, "gap", ready(t + 3), t + 3)]
    assert got == ["gap/base", "gap/lone"]                                     # unblocked only; the critical first
    for e in ("gap.started", "gap.built", "gap.review-started", "gap.approved", "gap.queued", "gap.merged"):
        ev.add(e, item="gap/base", at=t + 10)
    got = [i.id for i in pr.order_ready(ev, spec, "gap", ready(t + 11), t + 11)]
    assert got[0] == "gap/mid" and set(got) == {"gap/mid", "gap/other", "gap/lone"}   # merged: its dependents ready
    ev.add("gap.parked", item="gap/mid", at=t + 12)
    ev.add("gap.dependencies", item="gap/top", data={"waits_on_parked": True, "blocked_reason": "waits on gap/mid"},
           at=t + 12)
    takeable = [i for i in ready(t + 13) if its.matches(i, take.takes.where)]
    got = [i.id for i in pr.order_ready(ev, spec, "gap", takeable, t + 13)]
    assert "gap/top" not in got and "gap/other" in got                         # a parked dependency still holds it
    from ergostat.spec.itemindex import index_for
    info = pr.Kinds(spec, index_for(ev, spec, False))["gap"]
    assert info["paused"] == ["parked"] and "parked" not in info["finished"]   # paused, not done: never projected on


def test_a_push_without_an_action_id_never_stalls_silently(tmp_path):
    f = Factory(tmp_path)
    db = f.db()
    db["act_reply"] = {"rc": 4, "id": False}                                   # denied at once, no id said
    f.record.write_text(json.dumps(db))
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    said, _ = f.run("queue.py", gid)
    assert said[-1] == "gap.sent-back" and f.item(gid)["state"] == "fix"      # undone at once
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "start"
    g = Factory(tmp_path / "g")
    db = g.db()
    db["act_reply"] = {"rc": 3, "id": False}                                   # held, and no id to follow it by
    g.record.write_text(json.dumps(db))
    gid = ready(g)
    g.run("implement.py", gid)
    g.run("review.py", gid)
    said, _ = g.run("queue.py", gid)
    assert said[-1] == "intervention.recorded"                                 # blocked, asking the coordinator
    assert "blocked until" in settle(g)[1]
    h = Factory(tmp_path / "h")
    db = h.db()
    db["act_reply"] = {"rc": 3, "id": True, "noise": 5000}                     # a long answer: the id is still read
    h.record.write_text(json.dumps(db))
    gid = ready(h)
    h.run("implement.py", gid)
    h.run("review.py", gid)
    h.run("queue.py", gid)
    assert "is held" in settle(h)[1]


def behind_main(f: Factory, conflict: bool = False, name: str = "warm") -> tuple[str, str]:
    """A branch of the checkout (its definition its first commit, then work), and main moved on since (in the file the
    branch changed, when ``conflict``); (the branch's tip, main's)."""
    git(f.checkout, "checkout", "-q", "-b", name, "main")
    (f.checkout / "docs" / "roadmap" / "overnight" / f"{name}.md").write_text(
        f"# {name}\n\n## Definition of done\n\nIt works.\n\n## Size budget\n\n600 net lines.\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", f"{name}: the definition of done")
    (f.checkout / "app.py").write_text("print('the branch')\n")
    git(f.checkout, "commit", "-qam", "the branch's work")
    tip = git(f.checkout, "rev-parse", "HEAD")
    git(f.checkout, "checkout", "-q", "main")
    (f.checkout / ("app.py" if conflict else "main.py")).write_text("print('main')\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "main moved on")
    git(f.checkout, "push", "-q", "origin", "main")                             # (the drop's main is main as pushed)
    return tip, git(f.checkout, "rev-parse", "main")


def continues(f: Factory, name: str = "warm", gid: str = "gap/warm-again") -> str:
    f.fold([{"event": "gap.requested", "item": gid, "data": {"title": "Warm again", "source": "request",
                                                             "continues": name}}], None)
    f.run("intake.py")
    return gid


def test_a_gap_continues_a_named_branch(tmp_path):
    f = Factory(tmp_path)
    tip, _ = behind_main(f)
    f.fold([{"event": "gap.requested", "item": "gap/escape", "data": {"source": "request", "continues": "../warm"}},
            {"event": "gap.requested", "item": "gap/nowhere", "data": {"source": "request", "continues": "no-such"}},
            {"event": "gap.requested", "item": "gap/two", "data": {"continues": "warm", "branch": "other"}}], None)
    gid = continues(f)
    drop = tmp_path / "live" / "drop.git"
    assert git(drop, "rev-parse", "factory/warm") == tip                       # fetched into the drop as factory/warm
    assert f.item(gid)["state"] == "ready"                                      # its own definition, found on it
    assert f.item(gid)["fields"]["definition"] == "factory/warm:docs/roadmap/overnight/warm.md"
    for refused in ("gap/escape", "gap/nowhere", "gap/two"):
        assert f.item(refused)["state"] == "open"
    assert git(drop, "for-each-ref", "--format=%(refname)", "refs/heads/factory/").split() == ["refs/heads/factory/warm"]
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    head = f.item(gid)["fields"]["head"]
    assert git(drop, "rev-parse", "factory/warm") == head
    assert subprocess.run(["git", "-C", str(drop), "merge-base", "--is-ancestor", tip, head]).returncode == 0
    first = git(drop, "log", "--reverse", "--first-parent", "--format=%s", "main..factory/warm").splitlines()
    assert first[:2] == ["warm: the definition of done", "the branch's work"]  # no second definition committed


def test_a_branch_behind_main_has_main_merged_before_the_session(tmp_path):
    f = Factory(tmp_path)
    tip, main = behind_main(f)
    gid = continues(f)
    f.run("implement.py", gid)
    drop = tmp_path / "live" / "drop.git"
    line = git(drop, "log", "--first-parent", "--format=%H %P|%s", "factory/warm").splitlines()
    session, merge = line[0].split("|"), line[1].split("|")
    assert session[1].endswith("uncommitted")                                   # the stand-in's work, after the merge
    assert merge[0].split()[1:] == [tip, main]                                   # main merged into the branch
    assert merge[1] == f"Merge main ({main[:12]}) into the branch"              # by the program, before the session
    assert session[0].split()[1] == merge[0].split()[0]
    assert f.item(gid)["fields"]["contexts"][0]["merge_conflicts"] == []
    assert f.item(gid)["fields"]["suites_fast"]["unit"]["rc"] == 0              # the fast suites ran after it


def test_a_conflicted_merge_is_handed_to_the_session_with_its_conflicts(tmp_path):
    f = Factory(tmp_path)
    tip, main = behind_main(f, conflict=True)
    gid = continues(f)
    drop = tmp_path / "live" / "drop.git"
    f.run("implement.py", gid, fails=True, FACTORY_STANDIN_IMPLEMENTOR="I did nothing")   # the merge left unfinished
    assert git(drop, "rev-parse", "factory/warm") == tip                        # refused: nothing came back
    f.run("implement.py", gid, fails=True, FACTORY_STANDIN_MERGE="abort")      # aborted, and its work committed
    assert git(drop, "rev-parse", "factory/warm") == tip                        # refused before the drop's branch moved
    assert git(drop, "for-each-ref", "refs/incoming/") == ""                    # (its side ref gone)
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    brief = sorted((f.model / "run" / "briefs").glob("warm-implementor-*.md"))[-1].read_text()
    assert "finish the merge of main" in brief and "- `app.py`" in brief and main in brief
    assert f.item(gid)["fields"]["contexts"][-1]["merge_conflicts"] == ["app.py"]
    sys.modules.setdefault("fac", module("fac"))                                 # (agents.py imports fac beside it)
    tools = module("agents").TOOLS["implementor"]
    assert {"Bash(git merge:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git status:*)"} <= set(tools)
    assert not {t for t in tools if t.startswith(("Bash(git push", "Bash(git fetch", "Bash(git pull", "Bash(git remote"))}
    head = f.item(gid)["fields"]["head"]
    assert subprocess.run(["git", "-C", str(drop), "merge-base", "--is-ancestor", main, head]).returncode == 0
    assert git(drop, "show", f"{head}:app.py") == "print('main')"             # the session's resolution kept


def test_a_branch_moved_by_another_writer_during_the_session_is_not_overwritten(tmp_path):
    f = Factory(tmp_path)
    drop = tmp_path / "live" / "drop.git"
    code = ("import sys, json, subprocess; sys.path[:0] = [sys.argv[1]]; import fac, agents; cfg = fac.config(); "
            "home, work = agents.clone(cfg, 'alpha-thing', 'implementor'); "
            "base = fac.git(work, 'rev-parse', 'origin/main'); was = agents.publish(cfg, work, 'alpha-thing'); "
            "d = agents.drop(cfg); tree = fac.git(d, 'rev-parse', was + '^{tree}'); "
            "other = fac.git(d, 'commit-tree', tree, '-p', was, '-m', 'another writer'); "
            "fac.git(d, 'update-ref', 'refs/heads/factory/alpha-thing', other); "   # (in the session's gap)
            "(work / 'made-inside.txt').write_text('x'); out = [other]\n"
            "try:\n    out.append(agents.finish(cfg, home, 'alpha-thing', base, base, was=was))\n"
            "except RuntimeError as e:\n    out.append(str(e))\n"
            "print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    other, said = json.loads(r.stdout.strip().splitlines()[-1])
    assert "moved" in said and "refused" in said                                # not moved over the other write
    assert git(drop, "rev-parse", "factory/alpha-thing") == other              # the other writer's commit kept
    assert git(drop, "for-each-ref", "refs/incoming/") == ""


def test_gate_one_accepts_a_continued_branch_definition(tmp_path):
    f = Factory(tmp_path)
    behind_main(f)
    gid = continues(f)
    f.run("implement.py", gid)
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved"                                           # its first commit is its definition
    assert not f.item("review/warm-1")["fields"]["blocking"]
    built = f.item(gid)["fields"]["built_main"]
    (f.checkout / "later.py").write_text("print('later')\n")                   # main moves on after the build
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "main moved on again")
    git(f.checkout, "push", "-q", "origin", "main")
    for n in (2, 3):                                                            # reviewed twice more: never parked
        f.fold([{"event": "gap.sent-back", "item": gid, "data": {}}], None)   # for main moving (the queue's to
        f.fold([{"event": "gap.built", "item": gid, "data": {}}], None)       # settle), not past the kill rule
        said, _ = f.run("review.py", gid)
        assert said[-1] == "gap.approved" and f.item(gid)["state"] != "parked"
        assert not f.item(f"review/warm-{n}")["fields"]["blocking"]
    assert f.item(gid)["fields"]["built_main"] == built
    moved = git(f.checkout, "rev-parse", "main")                                # a build that claims a main its
    f.fold([{"event": "gap.sent-back", "item": gid, "data": {}}], None)       # branch does not hold: refused
    f.fold([{"event": "gap.built", "item": gid, "data": {"built_main": moved}}], None)
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.sent-back"
    assert any("does not hold main as of its build" in b for b in f.item("review/warm-4")["fields"]["blocking"])


def test_gate_one_takes_a_continued_gaps_named_definition_first_committed_under_the_branchs_old_name(tmp_path):
    f = Factory(tmp_path)
    tip, _ = behind_main(f)
    git(f.checkout, "branch", "warm2", tip)                                     # warm, carried on under a new name:
    gid = "gap/warm2-again"                                                     # its first commit is warm.md
    f.fold([{"event": "gap.requested", "item": gid, "data": {
        "title": "Warm 2", "source": "request", "continues": "warm2",
        "definition": "factory/warm2:docs/roadmap/overnight/warm.md"}}], None)
    f.run("intake.py")
    assert f.item(gid)["state"] == "ready"
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    drop = tmp_path / "live" / "drop.git"
    head = f.item(gid)["fields"]["head"]
    assert subprocess.run(["git", "-C", str(drop), "cat-file", "-e", f"{head}:docs/roadmap/overnight/warm2.md"],
                          capture_output=True).returncode                       # no copy under the new name
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved"
    assert not f.item("review/warm2-1")["fields"]["blocking"]
    wt = tmp_path / "wt-check"                                                  # the program's own check, not the
    subprocess.run(["git", "clone", "-q", str(drop), str(wt)], check=True, capture_output=True)   # prompt's
    git(wt, "checkout", "-q", "--detach", head)

    def gate(rel: str) -> list[str]:
        code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import review; "
                "print(json.dumps(review.gates({}, __import__('pathlib').Path(sys.argv[2]), 'warm2', 'origin/main', "
                "continued=True, rel=sys.argv[3])[0]))")
        r = subprocess.run([sys.executable, "-c", code, str(BIN), str(wt), rel], cwd=f.model, env=f.env,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-800:]
        return json.loads(r.stdout.strip().splitlines()[-1])

    assert gate("docs/roadmap/overnight/warm.md") == []
    assert gate("") == ["gate 1: dev/records/warm2.md is not on the branch"]   # (without it)
    (wt / "docs" / "roadmap" / "overnight" / "later.md").write_text("# later\n")  # a definition the branch added
    git(wt, "add", "-A")                                                        # later: its place in history is
    git(wt, "commit", "-q", "-m", "a later file")                               # not checked
    assert gate("docs/roadmap/overnight/later.md") == []
    (wt / "docs" / "roadmap" / "overnight" / "later.md").write_text("# later, changed\n")
    git(wt, "commit", "-qam", "the definition changed")                         # changed after it: still refused
    assert gate("docs/roadmap/overnight/later.md") == [
        "gate 1: docs/roadmap/overnight/later.md was changed after its first commit (other than a 'Where it "
        "stopped' section)"]


# ---- gap-records-out-of-docs: a gap's definition under dev/records/, the old docs/roadmap/overnight/ still read

OLD, NEW = "docs/roadmap/overnight", "dev/records"
DONE = "## Definition of done\n\nIt works.\n\n## Size budget\n\n600 net lines.\n"


def commit_files(f: Factory, files: dict[str, str], branch: str = "main") -> None:
    """Files committed on main (pushed: the drop's main is main as pushed), or on a new branch of the checkout."""
    if branch != "main":
        git(f.checkout, "checkout", "-q", "-b", branch, "main")
    for rel, text in files.items():
        (f.checkout / rel).parent.mkdir(parents=True, exist_ok=True)
        (f.checkout / rel).write_text(text)
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", f"{branch}: the definition of done")
    if branch == "main":
        git(f.checkout, "push", "-q", "origin", "main")
    else:
        git(f.checkout, "checkout", "-q", "main")


def on_head(f: Factory, gid: str, rel: str) -> bool:
    head = f.item(gid)["fields"]["head"]
    return subprocess.run(["git", "-C", str(f.tmp / "live" / "drop.git"), "cat-file", "-e", f"{head}:{rel}"],
                          capture_output=True).returncode == 0


def built_and_approved(f: Factory, gid: str, review: str) -> None:
    """Through the real readers: intake took it, implement.py built it, review.py's gate 1 found its definition."""
    assert f.item(gid)["state"] == "ready"
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved" and not f.item(review)["fields"]["blocking"]


def test_a_new_definition_is_written_under_dev_records(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)                                                              # (run/defs/: the implementor commits it)
    built_and_approved(f, gid, "review/alpha-thing-1")
    assert on_head(f, gid, f"{NEW}/alpha-thing.md") and not on_head(f, gid, f"{OLD}/alpha-thing.md")
    drop = tmp_path / "live" / "drop.git"
    assert git(drop, "log", "--reverse", "--format=%s", "main..factory/alpha-thing").splitlines()[0] == \
        "alpha-thing: the definition of done"
    brief = (tmp_path / "instance" / "run" / "briefs" / "alpha-thing-implementor-1.md").read_text()
    assert f"committed first, at `{NEW}/alpha-thing.md`" in brief               # the implementor is told the new path
    g = Factory(tmp_path / "on-main")                                           # one committed on main at the new path
    commit_files(g, {f"{NEW}/alpha-thing.md": f"# alpha thing\n\n{DONE}"})
    g.run("intake.py")
    assert g.item("gap/alpha-thing")["fields"]["definition"] == f"main:{NEW}/alpha-thing.md"
    built_and_approved(g, "gap/alpha-thing", "review/alpha-thing-1")


def test_a_definition_at_the_old_path_still_resolves(tmp_path):
    f = Factory(tmp_path)                                                       # on main
    commit_files(f, {f"{OLD}/alpha-thing.md": f"# alpha thing\n\n{DONE}"})
    f.run("intake.py")
    assert f.item("gap/alpha-thing")["fields"]["definition"] == f"main:{OLD}/alpha-thing.md"
    built_and_approved(f, "gap/alpha-thing", "review/alpha-thing-1")
    assert not on_head(f, "gap/alpha-thing", f"{NEW}/alpha-thing.md")           # no copy at the new path
    g = Factory(tmp_path / "branch")                                            # on a gap's branch in flight
    behind_main(g)                                                              # (its definition at the old path)
    gid = continues(g)
    assert g.item(gid)["fields"]["definition"] == f"factory/warm:{OLD}/warm.md"
    built_and_approved(g, gid, "review/warm-1")
    assert not on_head(g, gid, f"{NEW}/warm.md")
    said, _ = g.run("review.py", gid, FACTORY_STANDIN_VERDICT="park")           # its park note goes into that file
    assert said[-1] == "gap.parked"
    assert "## Where it stopped" in git(tmp_path / "branch" / "live" / "drop.git", "show", f"factory/warm:{OLD}/warm.md")


def test_a_ref_to_the_old_path_still_resolves(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, {f"{OLD}/warm.md": f"# warm\n\n{DONE}"}, branch="warm2")    # carried on under a new name
    gid = "gap/warm2-again"
    f.fold([{"event": "gap.requested", "item": gid, "data": {
        "title": "Warm 2", "source": "request", "continues": "warm2", "definition": f"factory/warm2:{OLD}/warm.md"}}],
        None)
    f.run("intake.py")
    assert f.item(gid)["fields"]["definition"] == f"factory/warm2:{OLD}/warm.md"
    built_and_approved(f, gid, "review/warm2-1")
    assert not on_head(f, gid, f"{NEW}/warm2.md") and not on_head(f, gid, f"{OLD}/warm2.md")   # no copy made
    g = Factory(tmp_path / "on-main")                                           # a REF on main, of a gap not continued
    commit_files(g, {f"{OLD}/ask.md": f"# my ask\n\n{DONE}"})
    g.fold([{"event": "gap.requested", "item": "gap/my-ask", "data": {
        "title": "My ask", "source": "request", "definition": f"main:{OLD}/ask.md"}}], None)
    g.run("intake.py")
    assert g.item("gap/my-ask")["state"] == "ready"


def test_the_new_path_wins_when_both_exist(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, {f"{OLD}/warm.md": "# warm, old\n\nThe old one.\n", f"{NEW}/warm.md": f"# warm, new\n\n{DONE}"},
                 branch="warm")
    gid = continues(f)
    assert f.item(gid)["fields"]["definition"] == f"factory/warm:{NEW}/warm.md"
    wt = tmp_path / "wt-both"
    subprocess.run(["git", "clone", "-q", "-b", "warm", str(f.checkout), str(wt)], check=True, capture_output=True)
    code = ("import sys; sys.path[:0] = [sys.argv[1]]; import fac, pathlib; "
            "print(fac.definition_file({'id': 'gap/warm', 'fields': {'branch': 'warm'}}, pathlib.Path(sys.argv[2])))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(wt)], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=60)
    assert r.stdout.strip() == f"{NEW}/warm.md", r.stderr[-800:]
    (wt / OLD / "warm.md").unlink()                                             # only the old one: it is taken
    (wt / NEW / "warm.md").unlink()
    (wt / OLD / "warm.md").write_text("x\n")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(wt)], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=60)
    assert r.stdout.strip() == f"{OLD}/warm.md", r.stderr[-800:]
    built_and_approved(f, gid, "review/warm-1")                                 # gate 1 on the new one
    g = Factory(tmp_path / "on-main")                                           # both on main: the new one
    commit_files(g, {f"{OLD}/alpha-thing.md": "# old\n", f"{NEW}/alpha-thing.md": f"# alpha thing\n\n{DONE}"})
    g.run("intake.py")
    assert g.item("gap/alpha-thing")["fields"]["definition"] == f"main:{NEW}/alpha-thing.md"


def test_a_branch_another_gap_still_holds_is_not_continued_until_it_stops(tmp_path):
    f = Factory(tmp_path)
    behind_main(f)
    first = continues(f, gid="gap/warm-first")
    f.run("implement.py", first)
    assert f.run("review.py", first)[0][-1] == "gap.approved"                  # approved, waiting for the queue
    drop = tmp_path / "live" / "drop.git"
    reviewed = git(drop, "rev-parse", "factory/warm")
    second = continues(f, gid="gap/warm-second")
    assert f.item(second)["state"] == "open"                                    # not taken: warm is the first's
    assert "gap/warm-second continues 'warm', which gap/warm-first still holds (approved)" in f.stderr
    assert git(drop, "rev-parse", "factory/warm") == reviewed
    for state in ("building", "built", "fix", "queued"):                         # nor while it is anywhere live
        db = f.db()
        db["items"][first]["state"] = state
        f.record.write_text(json.dumps(db))
        f.run("intake.py")
        assert f.item(second)["state"] == "open"
    f.fold([{"event": "gap.parked", "item": first, "data": {}}], None)        # parked: the branch is free
    f.run("intake.py")
    assert f.item(second)["state"] == "ready"
    f.fold([{"event": "gap.requested", "item": f"gap/warm-{n}", "data": {"source": "request", "continues": "warm"}}
            for n in ("x", "y")], None)                                         # two asked at once: neither blocks
    f.run("intake.py")                                                           # the other while open, and only
    assert [f.item(f"gap/warm-{n}")["state"] for n in ("x", "y")] == ["open", "open"]   # (the second holds it now)
    f.fold([{"event": "gap.parked", "item": second, "data": {}}], None)
    f.run("intake.py")
    assert sorted(f.item(f"gap/warm-{n}")["state"] for n in ("x", "y")) == ["open", "ready"]   # one is taken


def test_overlapping_finishes_on_one_branch_each_read_their_own_side_ref(tmp_path):
    f = Factory(tmp_path)
    drop = tmp_path / "live" / "drop.git"
    script = tmp_path / "overlap.py"
    script.write_text(textwrap.dedent("""\
        import json, sys
        sys.path[:0] = [sys.argv[1]]
        import agents, fac
        cfg = fac.config()
        runs = [agents.clone(cfg, "alpha-thing", "implementor") for _ in range(2)]
        base = fac.git(runs[0][1], "rev-parse", "origin/main")
        was = [agents.publish(cfg, work, "alpha-thing") for _, work in runs][0]
        for i, (_, work) in enumerate(runs):
            (work / f"run{i}.txt").write_text(str(i))
        real, got = fac.git, {}
        def spy(repo, *args, check=True):                  # the second run finishes between the first's fetch to
            out = real(repo, *args, check=check)           # its side ref and its reading it back
            if args[:1] == ("fetch",) and any("refs/incoming/" in a for a in args) and "second" not in got:
                got["second"] = "running"
                got["second"] = agents.finish(cfg, runs[1][0], "alpha-thing", base, base, was=was)
            return out
        fac.git = spy
        try:
            got["first"] = agents.finish(cfg, runs[0][0], "alpha-thing", base, base, was=was)
        except RuntimeError as e:
            got["first"] = str(e)
        fac.git = real
        print(json.dumps(got))
        """))
    r = subprocess.run([sys.executable, str(script), str(BIN)], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert git(drop, "rev-parse", "factory/alpha-thing") == got["second"]      # the second's own head, moved in
    assert git(drop, "show", f"{got['second']}:run1.txt") == "1"
    assert "moved" in got["first"] and "refused" in got["first"]                # the first refused for the move,
    assert git(drop, "for-each-ref", "refs/incoming/") == ""                    # never reading the second's head


def test_conflicts_are_listed_whole_when_a_path_has_a_space(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "my app.py").write_text("base\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "my app.py").write_text("side\n")
    git(repo, "commit", "-qam", "side")
    git(repo, "checkout", "-q", "main")
    (repo / "my app.py").write_text("main\n")
    git(repo, "commit", "-qam", "main")
    assert subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "merge",
                           "-q", "side"], capture_output=True).returncode
    assert module("fac").conflicted(repo) == ["my app.py"]


def test_a_continued_branch_already_reviewed_gets_reviews_and_logs_of_its_own(tmp_path):
    f = Factory(tmp_path)
    behind_main(f)
    f.fold([{"event": "review.written", "item": "review/warm-1", "data": {"verdict": "fix", "classes": ["lesson-5"]}},
            {"event": "review.written", "item": "review/warm-2", "data": {"verdict": "park", "where_it_stopped": "x"}},
            {"event": "review.written", "item": "review/warmer-7", "data": {"verdict": "merge"}}], None)
    logs = f.model / "run" / "logs"
    logs.mkdir(parents=True)
    (logs / "warm-1-0-unit.txt").write_text("the parked gap's log")             # (the old tag: branch-round-i)
    gid = continues(f)
    f.run("implement.py", gid)
    assert (logs / "warm-1-0-unit.txt").read_text() == "the parked gap's log"
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved"
    new = f.item("review/warm-3")                                                # past the parked gap's, not -1
    assert new["fields"]["gap"] == [gid] and "classes" not in new["fields"]
    assert new["fields"].get("where_it_stopped") != "x" and new["fields"]["verdict"] == "merge"
    assert f.item("review/warm-1")["fields"] == {"verdict": "fix", "classes": ["lesson-5"]}
    assert f.item("review/warm-2")["fields"] == {"verdict": "park", "where_it_stopped": "x"}


# ---- the merge queue's batches (docs/roadmap/overnight/merge-batching.md)

RED = "echo run >> {runs}; if [ -e bad.txt ]; then echo 'FAILED tests/test_b.py::test_b - boom'; exit 1; fi"


def approved_gaps(f: Factory, ranks: dict[str, int], bad: str = "", batch: int | None = None,
                  edits: dict[str, str] | None = None) -> dict[str, str]:
    """Gaps approved on branches of their own in the drop (each adds NAME.txt; ``bad`` adds bad.txt too, which fails the
    unit suite; ``edits`` {name: file} writes that file too, with the name), ranked as given; the queue's batch set when
    ``batch``. {name: its reviewed commit}."""
    drop = f.tmp / "live" / "drop.git"
    if not drop.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(drop)], check=True)
    out = {}
    for name, rank in ranks.items():
        git(f.checkout, "checkout", "-q", "-b", name, "main")
        (f.checkout / f"{name}.txt").write_text(name)
        if name == bad:
            (f.checkout / "bad.txt").write_text("breaks the suite")
        if name in (edits or {}):
            (f.checkout / edits[name]).write_text(f"{name}\n")
        git(f.checkout, "add", "-A")
        git(f.checkout, "commit", "-q", "-m", name)
        out[name] = git(f.checkout, "rev-parse", "HEAD")
        git(f.checkout, "push", "-q", str(drop), f"{name}:refs/heads/factory/{name}")
        git(f.checkout, "checkout", "-q", "main")
        git(f.checkout, "branch", "-q", "-D", name)
        f.fold([{"event": "gap.approved", "item": f"gap/{name}",
                 "data": {"branch": name, "reviewed_head": out[name], "approved_at": time.time() - 3600, "rank": rank}}],
               None)
    if batch:
        (f.model / "run").mkdir(exist_ok=True)
        (f.model / "run" / "pools.json").write_text(json.dumps({"batch": batch}))
    return out


def suite_runs(f: Factory) -> int:
    p = f.tmp / "runs"
    return len(p.read_text().splitlines()) if p.exists() else 0


def merges(f: Factory) -> list[str]:
    """main's merges, oldest first, by the branch each merged."""
    return [s.removeprefix("Merge branch 'factory/").rstrip("'") for s in
            git(f.checkout, "log", "--first-parent", "--reverse", "--format=%s", "main").splitlines()[1:]]


def test_a_green_batch_lands_every_gap(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 3, "b": 1, "c": 2, "d": 4, "e": 0}, batch=3)
    db = f.db()
    db["items"]["gap/e"]["fields"]["lease"] = {"holder": "run-x", "block": "flake-triage"}   # held by another run
    f.record.write_text(json.dumps(db))
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued"] + ["gap.merged"] * 3 + ["gap.push-asked"] * 3    # the others never left approved
    assert suite_runs(f) == 1                                                        # the suites once, for the batch
    assert merges(f) == ["b", "c", "a"]                                        # in rank order (not d: the batch is 3)
    head = git(f.checkout, "rev-parse", "main")
    for g in ("a", "b", "c"):
        it = f.item(f"gap/{g}")
        assert it["state"] == "merged" and it["fields"]["main_sha"] == head and it["fields"]["batch_size"] == 3
        assert it["fields"]["queue_attempts"] == 1 and len(it["fields"]["queue_runs"]) == 1
        assert it["fields"]["merged_lines"] == 1                       # its own merge's line, not the batch's 3
    assert f.item("gap/d")["state"] == "approved" and f.item("gap/e")["state"] == "approved"
    acts = f.db()["acts"]
    assert len(acts) == 1 and acts[0][:2] == ["act", "push-main"] and f"sha={head}" in acts[0]   # one approval
    pending = json.loads((f.model / "run" / "queue.json").read_text())["pending"]
    assert pending["gaps"] == ["gap/b", "gap/c", "gap/a"]
    set_action(f, "ran")
    said, why = settle(f)
    assert said == ["gap.pushed"] * 3 and why is None                          # the one push lands all three


def test_a_red_batch_is_bisected_to_the_failing_merge(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 3 and "gap.queued" not in said[1:]
    # all four red; p, q green and r, s red at once; on p, q: r red and s green at once
    assert suite_runs(f) == 5
    r = f.item("gap/r")
    assert r["state"] == "queue-failed" and r["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert merges(f) == ["p", "q", "s"] and not (f.checkout / "bad.txt").exists()
    onto = r["fields"]["pre"]                                                  # what r was merged onto: main with p, q
    assert git(f.checkout, "log", "--first-parent", "--format=%s", "-1", onto) == "Merge branch 'factory/q'"
    assert git(f.checkout, "rev-parse", "main~1") == onto                      # and the rest landed on it
    assert all(f.item(f"gap/{g}")["state"] == "merged" for g in "pqs")
    assert [f.item(f"gap/{g}")["fields"]["merged_lines"] for g in "pqs"] == [1, 1, 1]   # s: its merge onto p, q
    assert "merged_lines" not in f.item("gap/r")["fields"]                     # not merged: no count
    assert len(f.db()["acts"]) == 1
    run = {g: f.item(f"gap/{g}")["fields"]["queue_runs"] for g in "pqrs"}
    assert all(v == run["p"] for v in run.values()) and len(run["p"]) == 1     # the one run, on all four
    db = f.db()
    db["items"]["gap/p"]["fields"]["queue_runs"][0]["minutes"] = 40            # (a run this fast reads 0 minutes)
    for g in "qrs":
        db["items"][f"gap/{g}"]["fields"]["queue_runs"] = db["items"]["gap/p"]["fields"]["queue_runs"]
    db["items"]["gap/old"] = {"id": "gap/old", "kind": "gap", "state": "queue-failed",   # a run that landed nothing
                              "fields": {"queue_runs": [{"run": "y", "minutes": 20, "at": time.time()}]}}
    f.record.write_text(json.dumps(db))
    r = subprocess.run([sys.executable, str(BIN / "measure.py"), "merges-per-hour"], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.returncode == 0 and float(r.stdout) == 3.0, r.stderr                 # 3 merged in an hour of running
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "{RED.format(runs=tmp_path / "reruns")}"'))
    said, _ = f.run("triage.py", "gap/r")                                     # flake triage, on r's own merge
    assert said == ["gap.sent-back"] and f.item("gap/r")["fields"]["sent_back_by"] == "triage"


def test_batch_of_one_is_todays_queue(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 2, "b": 1}, bad="a")                                # no batch set: 1
    start = git(f.checkout, "rev-parse", "main")
    said, lines = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.queue-failed", "gap.measured"] and suite_runs(f) == 1   # as before: no bisecting
    assert f.item("gap/a")["fields"]["pre"] == start and git(f.checkout, "rev-parse", "main") == start
    assert f.item("gap/b")["state"] == "approved"                              # b ranks higher, but is not this run's
    said, _ = f.run("queue.py", "gap/b")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and merges(f) == ["b"]
    assert {x.get("item") for x in lines if "event" in x and not x["event"].startswith("batch.")} <= {None, "gap/a"}
    (own,) = {x["item"] for x in lines if x.get("event", "").startswith("batch.")}    # and its own batch item, a's
    assert own.startswith("batch/a-")


def main_moves(f: Factory, path: str) -> None:
    """main as pushed changes ``path`` (after the gaps branched)."""
    (f.checkout / path).write_text("main\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", f"main changes {path}")
    git(f.checkout, "push", "-q", "origin", "main")


def test_a_conflicting_gap_takes_no_batch_slot(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=2, edits={"a": "app.py"})
    main_moves(f, "app.py")                                                    # a conflicts with main now
    said, _ = f.run("queue.py", "gap/b")
    assert said == ["gap.queued", "gap.sent-back"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2
    assert merges(f) == ["main changes app.py", "b", "c"] and suite_runs(f) == 1   # c took the slot a would have
    a = f.item("gap/a")["fields"]
    assert a["failed_gates"] == 1 and a["findings"] == ["conflicts with main: app.py"]  # sent back at once, a gate


def test_a_batch_mate_conflict_is_not_a_failed_gate(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=2, edits={"a": "app.py", "b": "app.py"})   # a, b: each other
    said, lines = f.run("queue.py", "gap/a")
    assert said == ["gap.queued"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2 and merges(f) == ["a", "c"]
    b = f.item("gap/b")
    assert b["state"] == "approved" and "failed_gates" not in b["fields"] and "findings" not in b["fields"]
    assert not [x for x in lines if "nack" in x]
    # the run's own gap, behind a higher-ranked batch-mate it conflicts with: kept (its lease holds the push), and the
    # batch-mate it conflicts with is the one left approved, no gate failed
    g = Factory(tmp_path / "g", unit=RED.format(runs=tmp_path / "g" / "runs"))
    approved_gaps(g, {"a": 1, "b": 2, "c": 3}, batch=2, edits={"a": "app.py", "b": "app.py"})
    said, lines = g.run("queue.py", "gap/b")
    assert said == ["gap.queued"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2 and merges(g) == ["b", "c"]
    assert not [x for x in lines if "nack" in x] and g.item("gap/b")["state"] == "merged"
    a = g.item("gap/a")
    assert a["state"] == "approved" and "failed_gates" not in a["fields"] and "findings" not in a["fields"]


def test_the_run_s_own_gap_ranked_below_a_full_batch_is_still_taken(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=2)                       # all merge; the run is c's
    said, lines = f.run("queue.py", "gap/c")
    assert said == ["gap.queued"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2 and merges(f) == ["a", "c"]
    assert f.item("gap/c")["state"] == "merged" and f.item("gap/b")["state"] == "approved"
    assert not [x for x in lines if "nack" in x]


def test_batch_keeps_rank_order_among_mergeable_gaps(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"s": 4, "r": 3, "t": 5, "q": 2, "p": 1}, batch=3,         # (the record's order is not the rank's)
                  edits={"p": "main.py", "q": "app.py", "r": "app.py"})        # p: with main; r: with q
    main_moves(f, "main.py")
    said, _ = f.run("queue.py", "gap/t")
    assert merges(f) == ["main changes main.py", "q", "s", "t"] and suite_runs(f) == 1
    assert json.loads((f.model / "run" / "queue.json").read_text())["pending"]["gaps"] == ["gap/q", "gap/s", "gap/t"]
    assert f.item("gap/p")["fields"]["failed_gates"] == 1
    r = f.item("gap/r")
    assert r["state"] == "approved" and "failed_gates" not in r["fields"]


def stacked_gaps(f: Factory, ranks: dict[str, int], bad: str = "", batch: int | None = None) -> dict[str, str]:
    """A stack in the drop: each gap branched from the tip of the one before it (the first from main), adding
    NAME.txt (``bad``: bad.txt too), approved with `stacked_on` naming the one below at its commit. {name: commit}."""
    drop = f.tmp / "live" / "drop.git"
    if not drop.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(drop)], check=True)
    out, below = {}, None
    git(f.checkout, "checkout", "-q", "-b", "stack", "main")
    for name, rank in ranks.items():
        (f.checkout / f"{name}.txt").write_text(name)
        if name == bad:
            (f.checkout / "bad.txt").write_text("breaks the suite")
        git(f.checkout, "add", "-A")
        git(f.checkout, "commit", "-q", "-m", name)
        out[name] = git(f.checkout, "rev-parse", "HEAD")
        git(f.checkout, "push", "-q", str(drop), f"stack:refs/heads/factory/{name}")
        on = {"stacked_on": [{"gap": f"gap/{below}", "sha": out[below]}]} if below else {}
        f.fold([{"event": "gap.approved", "item": f"gap/{name}", "data": {
            "branch": name, "reviewed_head": out[name], "approved_at": time.time() - 3600, "rank": rank, **on}}], None)
        below = name
    git(f.checkout, "checkout", "-q", "main")
    git(f.checkout, "branch", "-q", "-D", "stack")
    if batch:
        (f.model / "run").mkdir(exist_ok=True)
        (f.model / "run" / "pools.json").write_text(json.dumps({"batch": batch}))
    return out


def test_a_stacked_gap_brings_its_base_into_its_batch_below_it(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    stacked_gaps(f, {"a": 5, "b": 0}, batch=2)                    # b ranks first, but holds a's commit
    said, _ = f.run("queue.py", "gap/b")
    assert said == ["gap.queued"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2 and suite_runs(f) == 1
    assert merges(f) == ["a", "b"]                                # a, then b, in one batch
    assert f.item("gap/a")["state"] == f.item("gap/b")["state"] == "merged"
    assert [f.item(f"gap/{g}")["fields"]["merged_lines"] for g in "ab"] == [1, 1]   # each its own commits only
    assert json.loads((f.model / "run" / "queue.json").read_text())["pending"]["gaps"] == ["gap/a", "gap/b"]


def test_a_stacked_gap_whose_base_is_in_fix_is_given_back_uncounted(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    stacked_gaps(f, {"a": 1, "b": 0}, batch=2)
    f.fold([{"event": "gap.sent-back", "item": "gap/a", "data": {"findings": ["x"]}}], None)
    assert f.item("gap/a")["state"] == "fix"
    said, lines = f.run("queue.py", "gap/b")
    assert said == ["gap.queued"] and suite_runs(f) == 0 and merges(f) == []
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert nack["count"] is False and nack["after"] == "10m" and "gap/a" in nack["why"] and "stack" in nack["why"]
    assert "empty_batches" not in f.item("gap/b")["fields"]      # never counted towards EMPTY_MOST
    f.fold([{"event": "gap.approved", "item": "gap/b", "data": {}}], None)   # (its lease given back, as the engine)
    approved_gaps(f, {"p": 9})                                    # b as a batch-mate: skipped, stays approved
    assert f.item("gap/b")["state"] == "approved"
    said, _ = f.run("queue.py", "gap/p")
    assert merges(f) == ["p"] and f.item("gap/b")["state"] == "approved" and "gap.sent-back" not in said


def test_a_failing_base_gives_its_descendants_back(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"p": 0})
    stacked_gaps(f, {"a": 1, "b": 2}, bad="a", batch=3)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 1
    assert f.item("gap/a")["state"] == "queue-failed" and f.item("gap/b")["state"] == "approved"
    assert "failed_gates" not in f.item("gap/b")["fields"] and f.item("gap/p")["state"] == "merged"
    assert suite_runs(f) == 4                                     # all red; p green, a+b red; a red: b never run
    pending = json.loads((f.model / "run" / "queue.json").read_text())["pending"]
    assert pending["gaps"] == ["gap/p"] and merges(f) == ["p"]
    tree = git(f.checkout, "ls-tree", "--name-only", pending["sha"]).split()
    assert "p.txt" in tree and not {"a.txt", "b.txt", "bad.txt"} & set(tree)   # the pushed tree


def test_a_stack_deeper_than_the_cap_gives_the_own_gap_back(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    stacked_gaps(f, {"a": 0, "b": 1, "c": 2}, batch=2)
    said, lines = f.run("queue.py", "gap/c")
    assert said == ["gap.queued"] and suite_runs(f) == 0 and merges(f) == []
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert nack["count"] is False and nack["after"] == "10m" and "does not fit a batch of 2" in nack["why"]
    assert "empty_batches" not in f.item("gap/c")["fields"]
    f.fold([{"event": "gap.approved", "item": "gap/c", "data": {}}], None)   # (its lease given back, as the engine)
    said, _ = f.run("queue.py", "gap/a")                       # the bottom base, in its own run
    assert said[:2] == ["gap.queued", "gap.merged"] and merges(f)[0] == "a" and f.item("gap/a")["state"] == "merged"
    assert merges(f) == ["a", "b"] and f.item("gap/c")["state"] == "approved"   # b fits on it; c waits


def test_gaps_passed_over_for_the_own_gap_fill_its_slot_once_it_is_sent_back(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=2, edits={"c": "app.py"})
    main_moves(f, "app.py")                                                    # the run's own c conflicts with main
    f.run("queue.py", "gap/c")
    assert merges(f) == ["main changes app.py", "a", "b"] and suite_runs(f) == 1   # b, passed over, fills the batch
    assert f.item("gap/a")["state"] == f.item("gap/b")["state"] == "merged"
    assert f.item("gap/c")["state"] == "push-pending"                          # its sending back waits for the push
    then = json.loads((f.model / "run" / "queue.json").read_text())["pending"]["then"]
    assert [(e["event"], e["data"]["failed_gates"]) for e in then] == [("gap.sent-back", 1)]


def test_a_conflict_naming_no_file_is_still_a_conflict_with_main(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    code = ("import sys, json, subprocess; sys.path[:0] = [sys.argv[1]]; import queue\n"
            "queue.subprocess = type('S', (), {'run': staticmethod(lambda *a, **k: subprocess.CompletedProcess("
            "a, 1, '0' * 40 + '\\0', ''))})\n"
            "print(json.dumps(queue.dry('.', 'x', 'y', 'm')))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    made, files = json.loads(r.stdout.splitlines()[-1])
    assert made is None and files                                              # never read as "only a batch-mate"


def test_the_tree_tested_is_the_tree_dry_merged(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, edits={"a": "app.py"})
    code = ("import sys, json, time; sys.path[:0] = [sys.argv[1]]; import fac, queue; cfg = fac.config(); "
            "repo = fac.path(cfg, 'checkout'); pre = fac.git(repo, 'rev-parse', 'HEAD'); "
            "own = next(g for g in fac.items('gap', 'approved') if g['id'] == 'gap/a'); "
            "batch, dried, _ = queue.picks(cfg, repo, own, 2, pre); out = {'moved': fac.git(repo, 'rev-parse', 'HEAD') != pre}; "
            "alone = queue.dry(repo, pre, batch[0][1], 'a alone')[0]\n"
            "try:\n queue.land(cfg, repo, batch, pre, time.time(), 0, alone)\n"
            "except RuntimeError as e:\n out['raised'] = str(e)\n"
            "landed, head, _ = queue.land(cfg, repo, batch, pre, time.time(), 0, dried)\n"
            "out.update(landed=[g['id'] for g, _ in landed], same=fac.git(repo, 'rev-parse', head + '^{tree}') == "
            "fac.git(repo, 'rev-parse', dried + '^{tree}')); print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.splitlines()[-1])
    assert out["moved"] is False                                               # a dry merge leaves the checkout be
    assert "differ from its dry merge" in out["raised"] and suite_runs(f) == 1  # never tested: only the true one ran
    assert out["landed"] == ["gap/a", "gap/b"] and out["same"] is True


def test_a_failed_suite_stops_its_sibling(tmp_path):
    fast = "echo 'FAILED tests/test_b.py::test_b - boom'; exit 1"
    slow = f"sleep 30; echo ran >> {tmp_path}/slow-ran"                 # finished only if it is never stopped
    for failing, other in (("unit", "browser"), ("browser", "unit")):
        f = Factory(tmp_path / failing, unit=fast if failing == "unit" else slow)
        f.config.write_text(f.config.read_text().replace('browser = "true"',
                                                         f'browser = "{fast if failing == "browser" else slow}"'))
        approved_gaps(f, {"a": 1})
        said, _ = f.run("queue.py", "gap/a")
        assert said == ["gap.queued", "gap.queue-failed", "gap.measured"]
        got = f.item("gap/a")["fields"]
        assert got["failed_suite"] == failing and got["failed_tests"] == ["tests/test_b.py::test_b"]   # first to fail
        assert got["suites_queue"][other]["stopped_by"] == failing and got["suites_queue"][other]["rc"] != 0
        assert not (tmp_path / "slow-ran").exists()                       # the sibling was killed, never finished


def bisect_stand_ins(tmp: Path, unit_names_tests: bool = True, rerun: str = "") -> Factory:
    """A unit suite that stops at its first failure, as `-x` would (test_b while bad.txt is there, then test_c while
    badc.txt is), each run logged in ``runs`` and each green one's tree in ``greens``; and the named tests' rerun,
    which says PASSED or FAILED for each test it is given and logs its arguments in ``reruns``."""
    say = (lambda t: f"echo 'FAILED tests/{t}.py::{t} - boom'") if unit_names_tests else (lambda t: "echo boom")
    (tmp / "unit.sh").write_text(f"echo run >> {tmp}/runs\n"
                                 f"if [ -e bad.txt ]; then {say('test_b')}; exit 1; fi\n"
                                 f"if [ -e badc.txt ]; then {say('test_c')}; exit 1; fi\n"
                                 f"git rev-parse 'HEAD^{{tree}}' >> {tmp}/greens\n")
    (tmp / "rerun.sh").write_text(f'echo "$*" >> {tmp}/reruns\nrc=0\nfor t in "$@"; do\n case "$t" in\n'
                                  ' *::test_b) f=bad.txt;;\n *::test_c) f=badc.txt;;\n *) continue;;\n esac\n'
                                  ' if [ -e $f ]; then echo "FAILED $t - boom"; rc=1; else echo "PASSED $t"; fi\n'
                                  'done\nexit $rc\n')
    f = Factory(tmp, unit=f"sh {tmp / 'unit.sh'}")
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "{rerun or "sh " + str(tmp / "rerun.sh")} {{tests}}"'))
    return f


def reruns(f: Factory) -> list[str]:
    p = f.tmp / "reruns"
    return p.read_text().splitlines() if p.exists() else []


def test_a_red_tree_s_named_tests_are_asked_alone_before_it_is_split(tmp_path):
    f = bisect_stand_ins(tmp_path)
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 3
    # test_b alone: on the red four, on main, then on the four prefixes at once; then one full run on p, q, s
    assert reruns(f) == ["tests/test_b.py::test_b -rA"] * 6 and suite_runs(f) == 2
    r = f.item("gap/r")["fields"]
    assert r["failed_suite"] == "unit" and r["failed_tests"] == ["tests/test_b.py::test_b"]
    assert r["suites_queue"]["batch_rounds"] == 1 and "1 round" in r["findings"][-1]
    assert merges(f) == ["p", "q", "s"] and not (f.checkout / "bad.txt").exists()
    assert git(f.checkout, "rev-parse", r["pre"]) == git(f.checkout, "rev-parse", "main~3")   # main before the batch


def flaky_stand_ins(tmp: Path, tests: list[str], rerun: str = "") -> Factory:
    """A unit suite that names ``tests`` as failed while bad.txt is there (each run logged in ``runs``), and a rerun
    (by default: PASSED for every test it is given, its arguments logged in ``reruns``)."""
    tmp.mkdir(exist_ok=True)
    said = "; ".join(f"echo 'FAILED {t} - boom'" for t in tests)
    (tmp / "unit.sh").write_text(f"echo run >> {tmp}/runs\nif [ -e bad.txt ]; then {said}; exit 1; fi\n")
    (tmp / "pass.sh").write_text(f'echo "$*" >> {tmp}/reruns\nfor t in "$@"; do echo "PASSED $t"; done\n')
    f = Factory(tmp, unit=f"sh {tmp / 'unit.sh'}")
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "{rerun or "sh " + str(tmp / "pass.sh")} {{tests}}"'))
    return f


def test_a_batch_whose_one_failed_test_passes_alone_twice_lands_as_a_flake(tmp_path):
    # test_b fails only in the full run (order, pollution, load): alone on the red tree it passes, twice
    t = "tests/test_b.py::test_b"
    f = flaky_stand_ins(tmp_path, [t])
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    assert "gap.queue-failed" not in said and said.count("gap.merged") == 4 and merges(f) == ["p", "q", "r", "s"]
    assert reruns(f) == [f"{t} -rA"] * 2 and suite_runs(f) == 1                # no bisect: the red run, twice alone
    flake = f.item("flake/tests-test-b-py-test-b")["fields"]
    assert flake["test"] == t and flake["times"] == 1 and flake["suite"] == "unit" and flake["passed_alone"] == 2
    assert flake["run"] == f.item("gap/p")["fields"]["batch_id"] and flake["log"].endswith("-unit.txt")
    assert sorted(flake["gaps"]) == ["gap/p", "gap/q", "gap/r", "gap/s"]
    got = f.item("gap/r")["fields"]["suites_queue"]
    assert got["excused"]["tests"] == [t] and "failed" not in got and got["demo"]["rc"] == 0   # the rest ran: green
    # a batch of one, too
    g = flaky_stand_ins(tmp_path / "one", [t])
    approved_gaps(g, {"a": 1}, bad="a")
    said, _ = g.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and len(reruns(g)) == 2
    assert g.flakes_said() == ["flake.seen"]
    # the suites the red run did not finish run before it lands: red there, it bisects (in full) and nothing lands
    h = flaky_stand_ins(tmp_path / "rest", [t])
    h.config.write_text(h.config.read_text().replace('demo = "true"', 'demo = "false"'))
    approved_gaps(h, {"p": 1, "q": 2}, bad="q", batch=2)
    said, _ = h.run("queue.py", "gap/p")
    assert "gap.merged" not in said and said.count("gap.queue-failed") == 2
    assert "flake/tests-test-b-py-test-b" not in h.db()["items"]


# ---- the browser step only on its paths (dev/records/merge-pipeline-browser-only-on-its-paths.md)

NOT_RUN = {"not_run": "no browser path changed", "counts": "not_run"}


def browser_on_paths(f: Factory, paths: list[str] | None = None) -> Path:
    """``f``'s browser step logging each run in browser-runs, and ``paths`` as `[suites] browser_paths` (None: the
    factory's own default, read from dev/factory.toml). The log's path."""
    runs = f.tmp / "browser-runs"
    if paths is None:
        paths = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]["browser_paths"]
    text = f.config.read_text().replace('\nbrowser = "true"', f'\nbrowser = "echo run >> {runs}"')
    f.config.write_text(text + f"browser_paths = {json.dumps(paths)}\n")       # ([suites] is the fixture's last table)
    return runs


def gaps_editing(f: Factory, edits: dict[str, str], bad: str = "", batch: int | None = None) -> None:
    """approved_gaps, one at a time, each gap writing its file (its folders made first: git drops empty ones)."""
    for i, (name, path) in enumerate(edits.items()):
        (f.checkout / path).parent.mkdir(parents=True, exist_ok=True)
        approved_gaps(f, {name: i + 1}, bad=bad if bad == name else "", batch=batch, edits={name: path})


def runs_of(p: Path) -> int:
    return len(p.read_text().splitlines()) if p.exists() else 0


def test_a_batch_without_browser_paths_skips_browser_and_says_so(tmp_path):
    from tests.test_queue_host import queue_module  # (dev/bin on the path, never the stdlib's queue)

    queue = queue_module()
    f = Factory(tmp_path)
    runs = browser_on_paths(f)
    gaps_editing(f, {"a": "dev/bin/a.py", "b": "dev/bin/b.py"}, batch=2)
    said, _ = f.run("queue.py", "gap/a")
    assert said.count("gap.merged") == 2 and runs_of(runs) == 0                    # done 1: no browser step
    a = f.item("gap/a")["fields"]
    assert a["suites_queue"]["browser"] == NOT_RUN and a["suites_queue"]["unit"]["rc"] == 0
    assert a["queue_runs"][-1]["suites"] == ["unit"]                               # not counted as a suite that ran
    # done 3: a red unit run with no browser path: browser is finished (not_run), so the rest of a flake's run skips it
    t = "tests/test_b.py::test_b"
    g = flaky_stand_ins(tmp_path / "red", [t])
    runs = browser_on_paths(g)
    gaps_editing(g, {"p": "dev/bin/p.py", "q": "docs/q.md"}, bad="q", batch=2)
    said, _ = g.run("queue.py", "gap/p")
    assert said.count("gap.merged") == 2 and len(reruns(g)) == 2 and runs_of(runs) == 0
    got = g.item("gap/q")["fields"]["suites_queue"]
    assert got["excused"]["tests"] == [t] and got["browser"] == NOT_RUN and got["demo"]["rc"] == 0
    red = {"ruff": {"rc": 0}, "unit": {"rc": 1}, "browser": dict(NOT_RUN), "failed": "unit", "tests": [t]}
    assert queue.rest(red) == ("host", "demo") and "browser" in queue.rest({**red, "browser": {"stopped_by": "unit"}})


def test_a_batch_touching_the_web_runs_browser(tmp_path):
    f = Factory(tmp_path)
    runs = browser_on_paths(f)
    gaps_editing(f, {"a": "dev/bin/a.py", "w": "ergostat/web/w.js"}, batch=2)
    said, _ = f.run("queue.py", "gap/a")
    assert said.count("gap.merged") == 2 and runs_of(runs) == 1                    # done 2: as today
    assert f.item("gap/w")["fields"]["suites_queue"]["browser"]["rc"] == 0
    # its halves keep the batch's decision: the half with only dev/bin still runs browser
    g = Factory(tmp_path / "halves", unit=RED.format(runs=tmp_path / "halves" / "runs"))
    runs = browser_on_paths(g)
    gaps_editing(g, {"a": "dev/bin/a.py", "w": "examples/w/w.yaml"}, bad="a", batch=2)
    said, _ = g.run("queue.py", "gap/w")                    # (the run's own gap lands: a's failure is said at once)
    assert said.count("gap.queue-failed") == 1 and merges(g) == ["w"]
    assert suite_runs(g) == 3 and runs_of(runs) == 3                               # the batch, then each half
    assert "not_run" not in g.item("gap/a")["fields"]["suites_queue"]["browser"]


def test_an_empty_browser_paths_runs_browser_always(tmp_path):
    from tests.test_queue_host import queue_module  # (dev/bin on the path, never the stdlib's queue)

    queue = queue_module()
    f = Factory(tmp_path)
    runs = browser_on_paths(f, [])
    gaps_editing(f, {"a": "dev/bin/a.py"})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and runs_of(runs) == 1   # done 4
    assert f.item("gap/a")["fields"]["suites_queue"]["browser"]["rc"] == 0
    # absent, not a list of globs, or a diff that cannot be read: browser runs (the worst case, never a skip)
    head = git(f.checkout, "rev-parse", "HEAD")
    for paths in (None, "ergostat/web/**", [""], [3]):
        cfg = {"suites": {} if paths is None else {"browser_paths": paths}}
        assert queue.browser_wanted(cfg, f.checkout, f"{head}~1") is True, paths
    cfg = {"suites": {"browser_paths": ["ergostat/web/**"]}}
    assert queue.browser_wanted(cfg, f.checkout, f"{head}~1") is False                     # (dev/bin/a.py only)
    assert queue.browser_wanted(cfg, f.checkout, "no-such-commit") is True
    assert queue.browser_wanted({"suites": {"browser_paths": ["dev/**"]}}, f.checkout, f"{head}~1") is True


def test_a_test_that_fails_alone_on_either_rerun_still_bisects(tmp_path):
    # the first rerun failing is test_bisect_reruns_only_the_failing_tests; here the second fails, then a rerun that
    # says no PASSED line (rc 0, lesson-3), each bisecting on the named tests as before
    t = "tests/test_b.py::test_b"
    (tmp_path / "second.sh").write_text(
        f'echo "$*" >> {tmp_path}/reruns\nn=$(wc -l < {tmp_path}/reruns)\n'
        'for t in "$@"; do case "$t" in -*) continue;; esac\n'
        ' if [ -e bad.txt ] && [ "$n" -ne 1 ]; then echo "FAILED $t - boom"; rc=1; else echo "PASSED $t"; fi\n'
        'done\nexit ${rc:-0}\n')
    f = flaky_stand_ins(tmp_path, [t], rerun=f"sh {tmp_path / 'second.sh'}")
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and merges(f) == ["p", "q", "s"]
    assert len(reruns(f)) == 7 and suite_runs(f) == 2             # twice on p..s, on main, a round of 4 prefixes
    r = f.item("gap/r")["fields"]
    assert r["failed_tests"] == [t] and r["suites_queue"]["rounds"][0]["kind"] == "named"
    assert "flake/tests-test-b-py-test-b" not in f.db()["items"]
    (tmp_path / "g").mkdir()
    (tmp_path / "mute.sh").write_text(f'echo "$*" >> {tmp_path / "g"}/reruns\n')      # rc 0, says nothing
    g = flaky_stand_ins(tmp_path / "g", [t], rerun=f"sh {tmp_path / 'mute.sh'}")
    approved_gaps(g, {"a": 1}, bad="a")
    said, _ = g.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.queue-failed", "gap.measured"] and len(reruns(g)) == 2   # (and on main)


def test_four_failed_tests_that_each_pass_alone_still_bisect(tmp_path):
    four = [f"tests/test_{x}.py::test_{x}" for x in "bcde"]
    f = flaky_stand_ins(tmp_path, four)
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    # they pass alone, so no name finds it: the halves in full, and r (not the last merge, s) is blamed. Alone on p..s,
    # on main, on the red half r, s (r alone is not asked: four cannot be excused, and nothing is left to find)
    assert said.count("gap.queue-failed") == 1 and merges(f) == ["p", "q", "s"]
    assert len(reruns(f)) == 3 and suite_runs(f) == 5
    r = f.item("gap/r")["fields"]
    assert r["failed_tests"] == four and "named" not in r["suites_queue"]
    assert not [i for i in f.db()["items"] if i.startswith("flake/")]
    g = flaky_stand_ins(tmp_path / "three", four[:3])                          # three: the most excused
    approved_gaps(g, {"p": 1, "q": 2}, bad="q", batch=2)
    said, _ = g.run("queue.py", "gap/p")
    assert said.count("gap.merged") == 2 and len([i for i in g.db()["items"] if i.startswith("flake/")]) == 3


def test_a_page_polling_failure_is_never_excused(tmp_path):
    for n, tests in enumerate((["tests/test_page_polling.py::test_a_page_left_open_does_not_grow"],
                               ["tests/test_b.py::test_b", "tests/test_page_polling.py::test_x[dynamics]"])):
        f = flaky_stand_ins(tmp_path / str(n), tests)
        approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
        said, _ = f.run("queue.py", "gap/p")
        assert said.count("gap.queue-failed") == 1 and merges(f) == ["p", "q", "s"]
        assert len(reruns(f)) == 3 and suite_runs(f) == 5      # (p..s, main, r+s) passing alone: split
        assert f.item("gap/r")["fields"]["failed_tests"] == sorted(tests)
        assert not [i for i in f.db()["items"] if i.startswith("flake/")]


def test_a_failure_naming_no_test_bisects_in_full(tmp_path):
    f = bisect_stand_ins(tmp_path, unit_names_tests=False)
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and merges(f) == ["p", "q", "s"]
    assert reruns(f) == [] and suite_runs(f) == 5                               # every run in full
    assert f.item("gap/r")["fields"]["failed_tests"] == []
    assert not [i for i in f.db()["items"] if i.startswith("flake/")]          # nothing excused
    # a named run that cannot tell (its test not found: rc 4, no result for it) excuses nothing, and is never green
    (tmp_path / "g").mkdir()
    (tmp_path / "notfound.sh").write_text(f'echo "$*" >> {tmp_path / "g" / "reruns"}\necho "ERROR: not found: $1"\n'
                                          'exit 4\n')
    g = bisect_stand_ins(tmp_path / "g", rerun=f"sh {tmp_path / 'notfound.sh'}")
    approved_gaps(g, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    g.run("queue.py", "gap/p")
    assert len(reruns(g)) == 4 and suite_runs(g) == 5 and merges(g) == ["p", "q", "s"]   # (p..s, main, r+s, r)
    assert g.item("gap/r")["state"] == "queue-failed"


def queue_json(f: Factory) -> dict:
    return json.loads((f.model / "run" / "queue.json").read_text())


def test_a_batch_failing_on_a_test_that_also_fails_on_main_sends_no_gap_back(tmp_path):
    f = bisect_stand_ins(tmp_path)
    main_has_test_b(f)
    main_moves(f, "bad.txt")                                                   # main itself fails test_b
    start = git(f.checkout, "rev-parse", "main")
    approved_gaps(f, {"p": 1, "q": 2, "r": 3}, batch=3)
    said, lines = f.run("queue.py", "gap/p")
    assert said == ["gap.queued", "intervention.recorded"]                     # no gap blamed or sent back
    assert f.flakes_said() == ["flake.main-broken"]                            # (written at once: flakes.py)
    assert [x["nack"] for x in lines if "nack" in x][0]["count"] is False         # the own gap's lease, uncounted
    assert all(f.item(f"gap/{g}")["state"] == "approved" for g in "qr")
    assert git(f.checkout, "rev-parse", "main") == start and merges(f) == ["main changes bad.txt"]
    t = "tests/test_b.py::test_b"
    # the red run, test_b alone on its tree, then on main alone twice: only the named test, no suite on main
    assert suite_runs(f) == 1 and reruns(f) == [f"{t} -rA"] * 3
    held = queue_json(f)["main_red"]
    assert held["pre"] == start and held["tests"] == [t] and held["suite"] == "unit"
    iv = f.item(held["intervention"])
    assert iv["fields"]["class"] == "queue" and iv["fields"]["main"] == start and iv["fields"]["tests"] == [t]
    assert f.item("flake/tests-test-b-py-test-b")["fields"]["main"] == start
    given = f.db()
    given["items"]["gap/p"]["state"] = "approved"                              # (the nack played)
    f.record.write_text(json.dumps(given))
    said, _ = f.run("queue.py", "gap/q")                                       # main still fails: no batch taken
    assert said == [] and suite_runs(f) == 1 and reruns(f)[-1] == f"{t} -rA" and len(reruns(f)) == 4
    (f.checkout / "tests").mkdir(exist_ok=True)                                # quarantined on main: taken again
    (f.checkout / "tests" / "quarantine.txt").write_text(f"{t} | main's, for now\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "quarantine test_b")
    git(f.checkout, "push", "-q", "origin", "main")
    f.config.write_text(f.config.read_text().replace(f"sh {tmp_path / 'unit.sh'}", "true"))  # (deselected, as unit is)
    said, _ = f.run("queue.py", "gap/q")
    said = [e for e in said if e != "flake.measured"]                         # (the quarantined test, run beside)
    assert said == ["intervention.remedied", "gap.queued"] + ["gap.merged"] * 3 + ["gap.push-asked"] * 3
    assert "main_red" not in queue_json(f) and f.item(held["intervention"])["state"] == "remedied"
    assert len(reruns(f)) == 4                                                 # (nothing left to run on main)


def main_has_test_b(f: Factory, body: str = "def test_b():\n    pass\n") -> None:
    """main's tree holds tests/test_b.py (committed with the next main_moves()), so main_red() runs it there."""
    (f.checkout / "tests").mkdir(exist_ok=True)
    (f.checkout / "tests" / "test_b.py").write_text(body)


def held_red(f: Factory) -> dict:
    """main fails test_b: a batch of p held by main (main_red), and p approved again (its nack played)."""
    main_has_test_b(f)
    main_moves(f, "bad.txt")
    approved_gaps(f, {"p": 1}, batch=1)
    f.run("queue.py", "gap/p")
    held = queue_json(f)["main_red"]
    given = f.db()
    given["items"]["gap/p"]["state"] = "approved"
    f.record.write_text(json.dumps(given))
    return held


def test_main_red_clears_when_its_intervention_is_remedied(tmp_path):
    f = bisect_stand_ins(tmp_path)
    held = held_red(f)
    assert len(reruns(f)) == 3                                                 # the red tree, main twice
    f.fold([{"event": "intervention.remedied", "item": held["intervention"], "data": {"remedied_by": "coordinator"}}], None)
    said, _ = f.run("queue.py", "gap/p")                                       # main still fails test_b
    assert said[0] == "gap.queued"                                             # taken at once: no check first
    assert len(reruns(f)) == 6 and "intervention.remedied" not in said        # (the batch fails on main again)


@pytest.mark.parametrize("fix", ["removed", "renamed"])
def test_a_held_test_main_no_longer_has_clears_the_hold(tmp_path, fix):
    f = bisect_stand_ins(tmp_path)
    held = held_red(f)
    if fix == "removed":
        git(f.checkout, "rm", "-q", "tests/test_b.py")
    else:
        main_has_test_b(f, "def test_b_renamed():\n    pass\n\n\ndef helper_test_b():\n    pass\n")
    git(f.checkout, "commit", "-qam", f"{fix} test_b")
    git(f.checkout, "push", "-q", "origin", "main")
    said, _ = f.run("queue.py", "gap/p")                                       # bad.txt stays: test_b would fail
    assert said[:2] == ["intervention.remedied", "gap.queued"] and len(reruns(f)) == 6   # never run before the batch
    assert f.item(held["intervention"])["fields"]["remedy"] == "they are quarantined or gone from main"


def test_main_red_clears_once_its_tests_pass_on_main(tmp_path):
    f = bisect_stand_ins(tmp_path)
    main_has_test_b(f)
    main_moves(f, "bad.txt")
    approved_gaps(f, {"p": 1}, batch=1)
    f.run("queue.py", "gap/p")
    assert queue_json(f)["main_red"]["tests"] == ["tests/test_b.py::test_b"]
    git(f.checkout, "rm", "-q", "bad.txt")                                     # main fixed
    git(f.checkout, "commit", "-q", "-m", "fix main")
    git(f.checkout, "push", "-q", "origin", "main")
    given = f.db()
    given["items"]["gap/p"]["state"] = "approved"
    f.record.write_text(json.dumps(given))
    said, _ = f.run("queue.py", "gap/p")
    assert said == ["intervention.remedied", "gap.queued", "gap.merged", "gap.push-asked"]
    assert "main_red" not in queue_json(f) and merges(f)[-1] == "p"


def test_a_batch_failing_on_a_test_that_passes_on_main_bisects_as_today(tmp_path):
    f = bisect_stand_ins(tmp_path)
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    start = git(f.checkout, "rev-parse", "main")
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 3 and merges(f) == ["p", "q", "s"]
    assert "intervention.recorded" not in said and "main_red" not in queue_json(f)
    t = "tests/test_b.py::test_b"
    assert reruns(f) == [f"{t} -rA"] * 6 and suite_runs(f) == 2               # the red four, main, 4 prefixes
    assert f.item("gap/r")["state"] == "queue-failed" and f.item("gap/r")["fields"]["failed_tests"] == [t]
    assert not [i for i in f.db()["items"] if i.startswith("flake/")]
    assert git(f.checkout, "rev-parse", "main~3") == start                     # (main as it was, then the three)


def test_a_test_that_fails_on_main_then_passes_is_a_flake_not_mains(tmp_path):
    # the second rerun (main's first; the first is on the red tree) fails whatever the tree; main's re-run passes
    (tmp_path / "once.sh").write_text(
        f'echo "$*" >> {tmp_path}/reruns\nn=$(wc -l < {tmp_path}/reruns)\n'
        'for t in "$@"; do case "$t" in -*) continue;; esac\n'
        ' if [ -e bad.txt ] || [ "$n" -eq 2 ]; then echo "FAILED $t - boom"; rc=1; else echo "PASSED $t"; fi\n'
        'done\nexit ${rc:-0}\n')
    t = "tests/test_b.py::test_b"
    f = flaky_stand_ins(tmp_path, [t], rerun=f"sh {tmp_path / 'once.sh'}")
    approved_gaps(f, {"p": 1, "q": 2}, bad="q", batch=2)
    said, _ = f.run("queue.py", "gap/p")
    assert "intervention.recorded" not in said and "main_red" not in queue_json(f)
    flake = f.item("flake/tests-test-b-py-test-b")
    assert flake["state"] != "main-broken" and flake["fields"]["failed_on_main"]
    assert f.item("gap/q")["state"] == "queue-failed" and merges(f) == ["p"]   # bisected as before


def test_nothing_lands_without_a_full_green_run(tmp_path):
    # q breaks test_c, which the first run never names (the suite stops at r's test_b): on test_b alone, p, q is green.
    # Landed then, q would be on main broken and s blamed for it. Merged again with s and run in full, it is found.
    f = bisect_stand_ins(tmp_path)
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4, edits={"q": "badc.txt"})
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.queue-failed") == 2 and said.count("gap.merged") == 2
    assert merges(f) == ["p", "s"] and f.item("gap/s")["state"] == "merged"
    assert f.item("gap/q")["fields"]["failed_tests"] == ["tests/test_c.py::test_c"]
    assert f.item("gap/r")["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    greens = (tmp_path / "greens").read_text().split()
    assert git(f.checkout, "rev-parse", "main^{tree}") in greens               # what landed ran green in full
    for g in "ps":
        assert "named" not in f.item(f"gap/{g}")["fields"]["suites_queue"]     # never a named run's green
    assert len(f.db()["acts"]) == 1


def test_a_stopped_batch_puts_its_other_gaps_back(tmp_path):
    # the run stopped during its suites: only ever the queue's own process (never whatever else $PPID could be)
    f = Factory(tmp_path, unit="ps -o command= -p $PPID | grep -q dev/bin/queue.py && kill -TERM $PPID; sleep 30")
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    start = git(f.checkout, "rev-parse", "main")
    said, _ = f.run("queue.py", "gap/a", fails=True)
    assert said == ["gap.queued"] and f.item("gap/b")["state"] == "approved"    # b never left approved
    assert git(f.checkout, "rev-parse", "main") == start                       # main as it was
    assert "running" not in json.loads((f.model / "run" / "queue.json").read_text())


# ---- batches of up to 8, and the run's time allowance (dev/records/queue-batches-larger.md)

ANY_BAD = ("echo run >> {runs}; if ls bad*.txt >/dev/null 2>&1; then echo 'FAILED tests/test_b.py::test_b - boom'; "
           "exit 1; fi; git write-tree >> {greens}")                          # (each green run's tree in greens)
EIGHT = {n: i for i, n in enumerate("abcdefgh", 1)}
CLOCKED = """\
import sys, threading, time
sys.path[:0] = [sys.argv[1]]
import queue
now, cost = [time.time()], float(sys.argv[2]) * 60
time.time = lambda: now[0]                         # a clock each suite run, named run or round moves by `cost`
def costs(fn):
    def call(*a, **k):
        got = fn(*a, **k)
        if threading.current_thread() is threading.main_thread():   # (a round's two halves: one cost, for the round)
            now[0] += cost
        return got
    return call
queue.suites, queue.named, queue.halves.run_all = costs(queue.suites), costs(queue.named), costs(queue.halves.run_all)
sys.exit(queue.main())
"""


def eight(tmp: Path, minutes: float | None = None, **gaps) -> Factory:
    """Eight approved gaps a..h (ranked so), the batch and its most 8, ``minutes`` the run's allowance."""
    f = Factory(tmp, unit=ANY_BAD.format(runs=tmp / "runs", greens=tmp / "greens"))
    text = f.config.read_text().replace("batch_max = 4", "batch_max = 8")
    f.config.write_text(text.replace("batch_max = 8", f"batch_max = 8\nbatch_minutes = {minutes}") if minutes else text)
    approved_gaps(f, EIGHT, batch=8, **gaps)
    return f


def clocked(f: Factory, gid: str, minutes_a_run: float) -> tuple[list[str], list[dict]]:
    """The queue's run of ``gid``, each suite run costing ``minutes_a_run`` on the run's clock."""
    driver = f.tmp / "clocked.py"
    driver.write_text(CLOCKED)
    return f.run(str(driver), gid, argv=(str(BIN), str(minutes_a_run)))


def counts(f: Factory, gid: str) -> tuple:
    run = f.item(gid)["fields"]["queue_runs"][-1]
    return run["tried"], run["landed"], run["given_back"]


def test_the_batch_s_most_is_batch_max_default_8(tmp_path):
    f = Factory(tmp_path)
    def put(n: int) -> int:
        r = subprocess.run([sys.executable, str(BIN / "pools.py"), "set", "batch", str(n), "test"], cwd=f.model,
                           env=f.env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads((f.model / "run" / "pools.json").read_text())["batch"]
    assert put(9) == 4                                                          # [pools] batch_max = 4: held to it
    f.config.write_text(f.config.read_text().replace("batch_max = 4", "batch_max = 12"))
    assert put(12) == 12                                                        # no constant below it
    f.config.write_text(f.config.read_text().replace("batch_max = 12\n", ""))
    assert put(20) == 8 and put(3) == 3                                         # unset: 8
    f.config.write_text(f.config.read_text().replace("[pools]", "[pools]\nbatch_max = 1000"))
    assert put(1000) == 32                                                      # the sanity ceiling
    assert 'batch_max = 8 ' in (ROOT / "dev" / "factory.toml").read_text()


def test_a_batch_of_8_all_green_lands_in_one_run(tmp_path):
    f = eight(tmp_path)
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued"] + ["gap.merged"] * 8 + ["gap.push-asked"] * 8
    assert suite_runs(f) == 1 and merges(f) == list("abcdefgh")
    assert all(f.item(f"gap/{g}")["fields"]["batch_size"] == 8 for g in "abcdefgh")
    assert counts(f, "gap/a") == (8, 8, 0) and len(f.db()["acts"]) == 1


def test_one_bad_commit_of_8_is_found_and_the_other_7_land(tmp_path):
    f = eight(tmp_path, bad="e")
    said, _ = f.run("queue.py", "gap/a")
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 7
    # all 8 red; a..d green, e..h red; e, f red, g, h green; e red, f green
    assert suite_runs(f) == 7 and merges(f) == list("abcdghf") and not (f.checkout / "bad.txt").exists()
    assert f.item("gap/e")["state"] == "queue-failed" and counts(f, "gap/a") == (8, 7, 0)
    assert git(f.checkout, "rev-parse", "main^{tree}") in (tmp_path / "greens").read_text().split()


def test_a_run_past_its_allowance_lands_only_what_is_proven_and_gives_back_the_rest(tmp_path):
    # 25 minutes a run, 85 allowed: all 8 red (25), the named check on them (50), on main (75), the first round: a..d
    # green, e..h red (100); no second round
    f = eight(tmp_path, minutes=85, bad="g")
    said, lines = clocked(f, "gap/h", 25)                                      # the run's own gap is among the rest
    assert merges(f) == list("abcd") and suite_runs(f) == 3                    # (the named check is not the unit suite)
    assert said.count("gap.merged") == 4 and "gap.queue-failed" not in said and "gap.sent-back" not in said
    head = git(f.checkout, "rev-parse", "main")
    assert git(f.checkout, "rev-parse", "main^{tree}") in (tmp_path / "greens").read_text().split()   # proven green
    assert [a for a in f.db()["acts"] if f"sha={head}" in a] == f.db()["acts"] and len(f.db()["acts"]) == 1
    for g in "efgh":                                                           # back, uncounted
        it = f.item(f"gap/{g}")
        assert it["state"] == ("queued" if g == "h" else "approved")           # (h: the run's own, given back below)
        assert "failed_gates" not in it["fields"] and "findings" not in it["fields"]
    nacks = [x["nack"] for x in lines if "nack" in x]
    assert len(nacks) == 1 and nacks[0]["count"] is False and "allowance" in nacks[0]["why"]   # the own gap's lease
    assert counts(f, "gap/h") == counts(f, "gap/e") == (8, 4, 4)
    db = f.db()
    db["items"]["gap/h"]["state"] = "approved"                                 # (the engine's nack, uncounted)
    f.record.write_text(json.dumps(db))
    set_action(f, "ran")
    assert settle(f)[1] is None
    said, _ = f.run("queue.py", "gap/e")                                       # the next run takes them
    assert merges(f) == list("abcdefh") and f.item("gap/g")["state"] == "queue-failed"
    # a round past the allowance never starts: 70 allowed, the round's turn comes at 75
    (tmp_path / "late").mkdir()
    h = bisect_stand_ins(tmp_path / "late")
    h.config.write_text(h.config.read_text().replace("batch_max = 4", "batch_max = 8\nbatch_minutes = 70"))
    approved_gaps(h, EIGHT, bad="g", batch=8)
    said, _ = clocked(h, "gap/a", 25)
    assert len(reruns(h)) == 2 and "gap.queue-failed" not in said and counts(h, "gap/a") == (8, 0, 8)


def test_a_batch_of_8_every_merge_failing_stays_inside_the_block_s_timeout(tmp_path):
    f = eight(tmp_path, edits={n: f"bad-{n}.txt" for n in EIGHT})             # each merge breaks the suite
    said, _ = clocked(f, "gap/a", 25)                                          # the default allowance, 120 minutes
    assert "gap.merged" not in said and merges(f) == []
    assert f.item("gap/a")["fields"]["queue_runs"][-1]["minutes"] <= 120 + 25 < 180
    tried, landed, back = counts(f, "gap/a")
    assert (tried, landed) == (8, 0) and back + said.count("gap.queue-failed") == 8 and back > 0


def test_a_run_out_of_time_before_its_first_finding_halves_the_next_batch(tmp_path):
    # the top-ranked gap bad, 45 minutes a run, 120 allowed: all 8 red (45), test_b alone on them (90), on main (135):
    # out of time before the first round, nothing found, all 8 back
    f = eight(tmp_path, bad="a")
    said, _ = clocked(f, "gap/a", 45)
    assert "gap.merged" not in said and "gap.queue-failed" not in said and counts(f, "gap/a") == (8, 0, 8)
    queue_json = f.model / "run" / "queue.json"
    assert json.loads(queue_json.read_text())["cap"] == 4
    db = f.db()
    db["items"]["gap/a"]["state"] = "approved"                                 # (the engine's nack, uncounted)
    f.record.write_text(json.dumps(db))
    # the next: a..d red (28), alone (56), main (84), a, b red and c, d green (112), a red and b green (140)
    said, _ = clocked(f, "gap/b", 28)                                          # (b's lease: a's outcome is said at once)
    assert f.item("gap/a")["state"] == "queue-failed" and counts(f, "gap/a") == (4, 3, 0)
    assert all(f.item(f"gap/{g}")["state"] == "approved" for g in "efgh") and merges(f) == ["c", "d", "b"]
    assert "cap" not in json.loads(queue_json.read_text())                    # a gap settled: the cap is cleared
    save = json.loads(queue_json.read_text())
    queue_json.write_text(json.dumps({**save, "cap": "x"}))                     # a cap that is not a count: 1
    set_action(f, "ran")
    assert settle(f)[1] is None
    said, _ = f.run("queue.py", "gap/e")
    assert said.count("gap.merged") == 1 and merges(f) == ["c", "d", "b", "e"] and counts(f, "gap/e") == (1, 1, 0)


UNREADABLE_AFTER_CHECKS = """\
import sys
sys.path[:0] = [sys.argv[1]]
import queue
first = queue.up_to_date
def then_unreadable(cfg, repo):                     # the checks pass, then run/queue.json turns unreadable
    why = first(cfg, repo)
    (queue.fac.run_dir(cfg) / "queue.json").write_text("[]")
    return why
queue.up_to_date = then_unreadable
sys.exit(queue.main())
"""


def test_a_queue_state_unreadable_at_the_cap_read_takes_no_gap(tmp_path):
    f = eight(tmp_path)
    driver = f.tmp / "unreadable.py"
    driver.write_text(UNREADABLE_AFTER_CHECKS)
    said, lines = f.run(str(driver), "gap/a", argv=(str(BIN),))
    assert said == [] and suite_runs(f) == 0                                    # gap.queued never said
    why = next(x["nack"] for x in lines if "nack" in x)
    assert "queue.json" in why["why"] and why["count"] is False


def test_a_time_allowance_out_of_range_is_refused(tmp_path):
    for bad in ("0", "151", "nan", "-5"):
        (tmp_path / bad).mkdir()
        f = eight(tmp_path / bad, minutes=bad)
        said, lines = f.run("queue.py", "gap/a")
        assert said == []                                                       # no gap taken
        why = next(x["nack"] for x in lines if "nack" in x)
        assert "batch_minutes" in why["why"] and why["count"] is False and suite_runs(f) == 0


def waiting(f: Factory) -> str:
    r = subprocess.run([sys.executable, str(BIN / "queue.py"), "waiting"], cwd=f.model, env=f.env, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_held_push_survives_later_runs(tmp_path):
    # the run's own gap (a) fails and b lands: the push is asked under a's lease; a waits at push-pending (not taken
    # by flake triage, the implementor) until the push settles
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.measured", "gap.push-asked", "gap.push-pending"]  # a's kept back
    assert f.item("gap/a")["state"] == "push-pending" and f.item("gap/b")["state"] == "merged"
    assert [e["event"] for e in json.loads((f.model / "run" / "queue.json").read_text())["pending"]["then"]] == [
        "gap.queue-failed"]
    assert waiting(f) == "1"                                                   # the queue's gate: it takes no gap
    approved_gaps(f, {"c": 3})
    said, lines = f.run("queue.py", "gap/c")                                  # a run attempted all the same
    assert said == [] and "is held" in next(x["nack"]["why"] for x in lines if "nack" in x)
    assert f.item("gap/a")["state"] == "push-pending"                          # still nothing takes a
    set_action(f, "ran")                                                       # the approval runs the push
    assert waiting(f) == "0"
    said, _ = settle(f)
    assert said == ["gap.pushed", "gap.queue-failed"] and f.item("gap/a")["state"] == "queue-failed"
    assert f.item("gap/a")["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert "pending" not in json.loads((f.model / "run" / "queue.json").read_text())


PUSH_MODEL = """
name: t
items:
  gap:
    id: gap/*
    states: [approved, queued]
    on: {gap.approved: approved, gap.queued: queued}
stocks:
  approved:
    sensor: {items: gap, state: approved, every: 5s}
actions:
  push-main:
    run: "echo pushed >> pushed.txt"
    in: .
    fenced: false
  note:
    run: "echo noted >> noted.txt"
    in: .
blocks:
  merge-queue:
    type: program
    run: "true"
    actions: [push-main, note]
    every: 1h
"""


def test_an_approved_push_runs_after_its_run_lease_moved(tmp_path):
    from ergostat import model as mdl
    from ergostat.actions import gate, program
    from ergostat.leases import TAKEN
    from ergostat.store import Project
    spec, _ = read(ROOT / "ergostat.yaml")                                   # the factory's own model
    assert spec.actions["push-main"].fenced is False
    assert [n for n, a in spec.actions.items() if not a.fenced] == ["push-main"]   # every other action stays fenced
    (tmp_path / "ergostat.yaml").write_text(PUSH_MODEL)
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    p = Project(m)
    p.events.add("gap.approved", item="gap/a", source="t", data={})

    def lease(fence: int, run: str) -> None:                               # a queue run's lease, nacked at its end
        p.events.add(TAKEN, item="gap/a", source="ergostat", data={"item": "gap/a", "run": run, "block": "merge-queue",
                     "fence": fence, "ttl": 300, "max": 3, "back": "approved", "tier": "program", "attempt": 1})
        p.events.add("ergostat.lease.ended", item="gap/a", source="ergostat", causedby=run,
                     data={"run": run, "fence": fence, "how": "nack", "why": "the run ended", "count": False})
    lease(1, "r1")
    given = {"block": "merge-queue", "run": "r1", "item": "gap/a", "lease": 1, "workdir": str(tmp_path),
             "branch": "", "actions": ["push-main", "note"], "runner": "here"}
    push = program.ask(p, m.spec, given, "push-main", {})
    note = program.ask(p, m.spec, given, "note", {})
    assert push["state"] == note["state"] == "requested"
    lease(2, "r2")                                                           # the next run leased the gap again
    assert gate.approve(p, m.spec, push["id"])["state"] == "ran"            # runs all the same
    assert (tmp_path / "pushed.txt").read_text() == "pushed\n"
    late = gate.approve(p, m.spec, note["id"])
    assert late["state"] == "failed" and "the lease now is 2: not run" in late["output"]   # fencing still holds
    assert not (tmp_path / "noted.txt").exists()
    y = tmp_path / "ergostat.yaml"
    y.write_text(PUSH_MODEL.replace("fenced: false", "fenced: no-thanks"))
    with pytest.raises(mdl.ModelError, match="push-main.fenced: true"):    # (a value it cannot take is an error)
        mdl.load(tmp_path)


def test_no_gap_is_leased_while_a_push_is_pending(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    lock = str(tmp_path / "queue.lock")
    said, _ = f.run("queue.py", "gap/a", FAKE_PROBE_LOCK=lock)
    assert said[-2:] == ["gap.push-asked"] * 2 and f.db()["lock_held_at_act"] is True   # asked and written in one hold
    head, runs = git(f.checkout, "rev-parse", "main"), suite_runs(f)
    approved_gaps(f, {"c": 3, "d": 4}, batch=2)
    said, lines = f.run("queue.py", "gap/c")                                 # the push waits: no gap is taken
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert said == [] and nack["count"] is False and "is held" in nack["why"]
    assert f.item("gap/c")["state"] == f.item("gap/d")["state"] == "approved"
    assert git(f.checkout, "rev-parse", "main") == head and suite_runs(f) == runs and len(f.db()["acts"]) == 1
    q = f.model / "run" / "queue.json"
    q.write_text("{not json")                                                # cannot be read: the same
    said, lines = f.run("queue.py", "gap/c")
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert said == [] and nack["count"] is False and "cannot be read" in nack["why"]
    assert git(f.checkout, "rev-parse", "main") == head and waiting(f) == "1"
    q.write_text("[]")
    assert f.run("queue.py", "gap/c")[0] == [] and waiting(f) == "1"


def queue_when(pushing: float) -> float:
    """block.queue-when of the factory's own model, as the engine computes it: gaps approved, the machine quiet."""
    from ergostat.spec.blocks import Expr
    spec, _ = read(ROOT / "ergostat.yaml")
    b = spec.blocks["queue-when"]
    vals = {"auxiliary.push-waiting": pushing, "goal.approved-gaps-landed.off": 1.0}
    return Expr(b, spec).compute(lambda r: vals.get(str(r), 0.0), time.time())


def nacked(lines: list[dict]) -> dict:
    return next(x["nack"] for x in lines if "nack" in x)


def test_a_waiting_push_puts_gaps_off_for_a_minute(tmp_path):
    from ergostat.spec.engine import nack_of
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    f.run("queue.py", "gap/a")                                                # a and b landed, their push asked
    approved_gaps(f, {"c": 3}, batch=2)
    for now in ("held", "requested", "approved"):                            # leased before the sensor saw the push
        set_action(f, now)
        said, lines = f.run("queue.py", "gap/c")
        nack = nacked(lines)
        assert said == [] and f"is {now}" in nack["why"]
        assert nack["after"] == "1m" and nack["count"] is False                # a minute, and not an attempt
        assert nack_of(nack)["after"] == 60
        assert waiting(f) == "1" and queue_when(1.0) == 0                     # meanwhile the sensor holds it shut: no spin
    assert f.item("gap/c")["state"] == "approved" and len(f.db()["acts"]) == 1


def test_a_blocked_queue_still_puts_gaps_off_for_ten_minutes(tmp_path):
    f = Factory(tmp_path)
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    f.run("queue.py", "gap/a")
    approved_gaps(f, {"c": 3}, batch=2)
    set_action(f, "failed")                                                  # the push failed: the queue blocked
    said, lines = f.run("queue.py", "gap/c")
    assert "intervention.recorded" in said and nacked(lines)["after"] == "10m" and nacked(lines)["count"] is False
    said, lines = f.run("queue.py", "gap/c")                                 # blocked, read again
    assert said == [] and "blocked until" in nacked(lines)["why"] and nacked(lines)["after"] == "10m"
    q = f.model / "run" / "queue.json"
    q.write_text("{not json")                                                # any other reason: ten minutes too
    said, lines = f.run("queue.py", "gap/c")
    assert said == [] and "cannot be read" in nacked(lines)["why"] and nacked(lines)["after"] == "10m"


def test_the_next_batch_starts_once_the_push_has_run(tmp_path):
    from ergostat.spec.engine import nack_of
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    f.run("queue.py", "gap/a")
    approved_gaps(f, {"c": 3, "d": 4}, batch=2)                             # approved while the push waits
    set_action(f, "requested")
    _, lines = f.run("queue.py", "gap/c")
    put_off = nack_of(nacked(lines))["after"]
    set_action(f, "ran")                                                     # the approval runs the push
    assert waiting(f) == "0" and queue_when(0.0) == 1                       # the sensor (every 1m) opens the block
    assert put_off + 60 <= 120                                               # due again, and seen, within 2 minutes
    said, lines = f.run("queue.py", "gap/c")                                 # no gap newly approved
    assert not [x for x in lines if "nack" in x] and "gap.queued" in said
    assert f.item("gap/c")["state"] == f.item("gap/d")["state"] == "merged"


def test_a_gap_that_did_not_land_waits_for_the_push(tmp_path):
    from types import SimpleNamespace

    from ergostat.leases.dispatch import moved_on
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    said, lines = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.measured", "gap.push-asked", "gap.push-pending"]
    assert not any("nack" in x for x in lines)
    a = f.item("gap/a")
    assert a["state"] == "push-pending" and "failed_tests" not in a["fields"]   # its outcome kept back
    block = read(ROOT / "ergostat.yaml")[0].blocks["merge-queue"]
    assert moved_on(block, SimpleNamespace(state="push-pending"))           # its lease ends there (ack), not approved
    assert not moved_on(block, SimpleNamespace(state="queued"))             # (a run killed part way: given back)
    assert settle(f) == ([], f"the push of {git(f.checkout, 'rev-parse', 'main')[:12]} (gap/b) is held")
    assert f.item("gap/a")["state"] == "push-pending"
    set_action(f, "denied")                                                  # settled: the outcome said, then
    said, why = settle(f)
    assert why is None and said == ["gap.sent-back", "gap.queue-failed"]
    assert f.item("gap/a")["state"] == "queue-failed" and f.item("gap/b")["state"] == "fix"
    assert f.item("gap/a")["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]


def settler(f: Factory) -> list[str]:
    """One run of the block push-settler (`queue.py settle`): the events it said."""
    return f.run("queue.py", argv=["settle"])[0]


def settleable(f: Factory) -> str:
    """The sensor push-settleable (`queue.py settleable`), which commands push-settler."""
    r = subprocess.run([sys.executable, str(BIN / "queue.py"), "settleable"], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_push_settles_with_no_gap_approved(tmp_path):
    import fcntl
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    assert settleable(f) == "0"                                                # nothing pending: not commanded
    assert f.run("queue.py", "gap/a")[0][-1] == "gap.push-pending"               # a failed, b landed, the push held
    assert f.item("gap/a")["state"] == "push-pending" and f.item("gap/b")["state"] == "merged"
    assert settleable(f) == "0" and waiting(f) == "1"                          # held: nothing to settle yet
    assert settler(f) == [] and f.item("gap/a")["state"] == "push-pending"
    set_action(f, "ran")                                                       # approved and run: no gap is approved
    assert settleable(f) == "1" and waiting(f) == "0"                          # commanded exactly when it has work
    with open(tmp_path / "queue.lock", "a") as lock:                          # a run starting holds the queue's lock
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert settler(f) == [] and "a run holds the queue's lock" in f.stderr  # it settles the push itself
        assert f.item("gap/a")["state"] == "push-pending"
    assert settler(f) == ["gap.pushed", "gap.queue-failed"]                    # the held outcome, applied
    assert f.item("gap/a")["state"] == "queue-failed" and settleable(f) == "0"
    assert f.item("gap/a")["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert "pending" not in json.loads((f.model / "run" / "queue.json").read_text())
    assert settler(f) == [] and settle(f) == ([], None)                        # once: neither applies it again
    approved_gaps(f, {"c": 3})
    assert f.run("queue.py", "gap/c")[0] == ["gap.queued", "gap.merged", "gap.push-asked"]   # nothing said twice
    d = Factory(tmp_path / "d", unit=RED.format(runs=tmp_path / "d-runs"))    # denied: b sent back, a's outcome said
    approved_gaps(d, {"a": 1, "b": 2}, bad="a", batch=2)
    d.run("queue.py", "gap/a")
    set_action(d, "denied")
    assert settleable(d) == "1"
    assert settler(d) == ["gap.sent-back", "gap.queue-failed"] and d.item("gap/b")["state"] == "fix"
    assert settleable(d) == "0"
    x = Factory(tmp_path / "x", unit=RED.format(runs=tmp_path / "x-runs"))    # failed: blocked, a's outcome said
    approved_gaps(x, {"a": 1, "b": 2}, bad="a", batch=2)
    x.run("queue.py", "gap/a")
    set_action(x, "failed")
    assert settleable(x) == "1"
    assert settler(x) == ["intervention.recorded", "gap.queue-failed"] and x.item("gap/a")["state"] == "queue-failed"
    assert "then" not in json.loads((x.model / "run" / "queue.json").read_text())["pending"]
    assert settleable(x) == "0"                                                # blocked, not remedied: nothing to do
    iid = next(i for i in x.db()["items"] if i.startswith("intervention/"))
    x.fold([{"event": "intervention.remedied", "item": iid, "data": {"remedy": "pushed by hand"}}], None)
    assert settleable(x) == "1"
    assert settler(x) == ["gap.push-settled"]                                  # (the outcome not said a second time)
    assert settleable(x) == "0"


def test_push_settler_is_commanded_by_push_settleable():
    spec, _ = read(ROOT / "ergostat.yaml")                                    # the factory's own model
    block = spec.blocks["push-settler"]
    assert [(r.kind, r.name) for r in block.inputs.values()] == [("auxiliary", "push-settleable")]
    assert block.params["run"] == "python3 dev/bin/queue.py settle"
    assert [s.run for s in spec.auxiliaries["push-settleable"].sensors.values()] == [
        "python3 dev/bin/queue.py settleable"]                                 # (its readings: the test above)


def test_an_unreadable_push_is_read_again_before_it_blocks(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    f.run("queue.py", "gap/a")
    set_action(f, "")                                                          # its action's state cannot be read
    assert settleable(f) == "1"
    assert settler(f) == [] and settler(f) == []                               # read again, twice, nothing said
    assert f.item("gap/a")["state"] == "push-pending"
    set_action(f, "ran")                                                       # the read works again: settled
    assert settler(f) == ["gap.pushed", "gap.queue-failed"]
    x = Factory(tmp_path / "x", unit=RED.format(runs=tmp_path / "x-runs"))
    approved_gaps(x, {"a": 1, "b": 2}, bad="a", batch=2)
    x.run("queue.py", "gap/a")
    set_action(x, "")
    assert settler(x) == [] and settler(x) == []
    assert settler(x) == ["intervention.recorded", "gap.queue-failed"]         # the third: worst case, blocked


def test_a_settler_killed_while_saying_says_nothing_twice(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    f.run("queue.py", "gap/a")
    set_action(f, "ran")
    code = ("import sys; sys.path[:0] = [sys.argv[1]]; import fac, queue\n"
            "def killed(*a, **k): raise SystemExit(143)\n"              # SIGTERM (stop_on_term) at its first event
            "fac.say = killed; queue.settle_alone(fac.config())")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    assert r.returncode == 143, r.stderr
    assert "pending" not in json.loads((f.model / "run" / "queue.json").read_text())   # saved before it said
    assert settler(f) == [] and settle(f) == ([], None)                        # at most once: nothing said again


def test_a_gap_pending_with_no_push_is_stuck(tmp_path):
    f = pipe(tmp_path)
    q = tmp_path / "instance" / "run"
    q.mkdir(exist_ok=True)
    aid = "ergostat.action/0000000001"
    (q / "queue.json").write_text(json.dumps({"pending": {"sha": "a" * 40, "gap": "gap/b", "gaps": ["gap/b"],
                                                          "action": aid, "then": [{"event": "gap.queue-failed",
                                                                                   "item": "gap/a", "data": {}}]}}))
    f.put("gap/a", "push-pending", branch="a")                                 # 10 h, past its 4 h
    db = f.db()
    db["actions"] = {aid: "held"}
    f.record.write_text(json.dumps(db))

    def handled_long_ago(s: dict) -> None:                                    # (answered, and the schedule due again)
        f.fold([{"event": "situation.handled", "item": s["id"], "data": {"prints": s["prints"]}}], None)
        db = f.db()
        db["items"][s["id"]]["fields"]["raised_at"] = f.now - 3 * 3600
        f.record.write_text(json.dumps(db))

    def stuck(s: dict) -> set[str]:
        return {t["subject"] for t in s["triggers"] if t["trigger"] == "stuck"}

    s = f.watch()
    assert stuck(s) == set()                                                   # its push held: a wait explained
    handled_long_ago(s)
    db = f.db()
    db["actions"][aid] = "ran"                                                 # the push ran, nothing settled it
    f.record.write_text(json.dumps(db))
    s = f.watch()
    assert stuck(s) == {"gap/a"}                                               # no longer explained
    handled_long_ago(s)
    f.put("gap/c", "push-pending", ago=600, branch="c")                        # no pending push carries it
    s = f.watch()
    assert stuck(s) == {"gap/c"}                                               # stuck at once, not after 4 h


def test_a_stale_push_is_refused_as_not_a_fast_forward(tmp_path):
    f = Factory(tmp_path)
    start = git(f.origin, "rev-parse", "main")

    def push(sha: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(BIN / "queue.py"), "push", sha], cwd=f.model, env=f.env,
                              capture_output=True, text=True)
    (f.checkout / "merged.txt").write_text("the approved merge\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "the merge")
    approved = git(f.checkout, "rev-parse", "HEAD")
    other = tmp_path / "elsewhere"                                           # main pushed by hand meanwhile
    subprocess.run(["git", "clone", "-q", str(f.origin), str(other)], check=True, capture_output=True, env=f.env)
    (other / "hand.txt").write_text("by hand\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "by hand")
    git(other, "push", "-q", "origin", "main")
    moved = git(f.origin, "rev-parse", "main")
    assert moved != start
    r = push(approved)                                                       # the approval came late: refused
    assert r.returncode != 0 and git(f.origin, "rev-parse", "main") == moved
    assert push("main").returncode != 0                                      # only an exact commit id
    git(f.checkout, "fetch", "-q", "origin")
    git(f.checkout, "reset", "-q", "--hard", "origin/main")                 # (a fast-forward of it is pushed)
    (f.checkout / "next.txt").write_text("next\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "next")
    nxt = git(f.checkout, "rev-parse", "HEAD")
    assert push(nxt).returncode == 0 and git(f.origin, "rev-parse", "main") == nxt


def test_a_killed_batch_strands_nothing(tmp_path):
    # SIGKILL mid-batch, during the suites (no finally runs): main holds both merges, b is still approved
    once = tmp_path / "killed"
    f = Factory(tmp_path, unit=f"if [ ! -e {once} ]; then touch {once}; ps -o command= -p $PPID | grep -q "
                              "dev/bin/queue.py && kill -KILL $PPID; sleep 1; exit 1; fi; echo run >> "
                              f"{tmp_path / 'runs'}")
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    start = git(f.checkout, "rev-parse", "main")
    said, _ = f.run("queue.py", "gap/a", fails=True)
    assert said == ["gap.queued"] and f.item("gap/b")["state"] == "approved"
    assert merges(f) == ["a", "b"]                                             # left behind on the checkout's main
    assert json.loads((f.model / "run" / "queue.json").read_text())["running"]["pre"] == start
    said, _ = f.run("queue.py", "gap/a")                                       # a's lease gave it back; the next run
    assert said == ["gap.queued", "gap.merged", "gap.merged", "gap.push-asked", "gap.push-asked"]
    assert merges(f) == ["a", "b"] and suite_runs(f) == 1                            # main put back first: each merged once
    assert git(f.checkout, "rev-parse", "main~2") == start
    assert f.item("gap/a")["state"] == f.item("gap/b")["state"] == "merged"
    assert "running" not in json.loads((f.model / "run" / "queue.json").read_text())


def test_a_run_killed_while_landing_blocks_the_queue(tmp_path):
    f = Factory(tmp_path)
    approved_gaps(f, {"a": 1})
    (f.model / "run").mkdir(exist_ok=True)
    (f.model / "run" / "queue.json").write_text(json.dumps({"running": {
        "pre": git(f.checkout, "rev-parse", "main"), "gaps": ["gap/a"], "landing": ["gap/a"]}}))
    said, lines = f.run("queue.py", "gap/a")
    assert said == ["intervention.recorded"] and f.item("gap/a")["state"] == "approved"   # (not taken)
    assert "saying gap/a merged" in next(x["nack"]["why"] for x in lines if "nack" in x)
    said, lines = f.run("queue.py", "gap/a")                                   # blocked once, not again each run
    assert said == [] and "blocked until intervention/queue-" in next(x["nack"]["why"] for x in lines if "nack" in x)


def test_the_queue_runs_unit_and_browser_at_once_and_reports_the_first_failure(tmp_path):
    t = tmp_path / "t"
    f = Factory(tmp_path, unit=f"echo unit-start >> {t}; sleep 1; echo unit-end >> {t}; echo 'FAILED tests/test_u.py::test_u'; exit 1")
    f.config.write_text(f.config.read_text().replace(
        'browser = "true"', f'browser = "echo browser-start >> {t}; sleep 5; echo browser-end >> {t}; exit 1"').replace(
        'demo = "true"', f'demo = "echo demo >> {t}"'))
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    got = t.read_text().split()
    assert sorted(got[:2]) == ["browser-start", "unit-start"] and "demo" not in got    # together; demo not after red
    fields = f.item("gap/a")["fields"]
    assert said[1] == "gap.queue-failed" and fields["failed_suite"] == "unit"           # the first to fail
    assert fields["failed_tests"] == ["tests/test_u.py::test_u"]
    assert fields["suites_queue"]["unit"]["rc"] == 1 and fields["suites_queue"]["browser"]["stopped_by"] == "unit"
    assert "browser-end" not in got                                                     # stopped by unit's failure
    f.config.write_text(f.config.read_text().replace("exit 1", "exit 0").replace("sleep 5", "sleep 1"))
    t.unlink()
    approved_gaps(f, {"b": 1})
    said, _ = f.run("queue.py", "gap/b")
    got = t.read_text().split()
    assert said[1] == "gap.merged" and got[-1] == "demo" and {"unit-end", "browser-end"} <= set(got[:-1])  # demo after


def test_the_tuner_asks_for_a_bigger_batch_while_the_queue_waits(tmp_path):
    f = Factory(tmp_path)
    now = time.time()
    f.fold([{"event": "gap.merged", "item": "gap/slow", "data": {"merged_at": now, "queue_wait_hours": 5, "queue_runs": [
        {"run": "x", "minutes": 30, "at": now}]}}], None)
    pools = lambda: subprocess.run([sys.executable, str(BIN / "pools.py"), "tune"], cwd=f.model, env=f.env,  # noqa: E731
                                   capture_output=True, text=True)
    r = pools()
    assert r.returncode == 0, r.stderr
    act = next(a for a in f.db()["acts"] if "role=batch" in a)
    assert act[:2] == ["act", "raise-pool"] and "to=2" in act
    got = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    measured = next(x for x in got if x.get("item") == "pool/batch" and x["event"] == "pool.measured")
    assert measured["data"]["merges_per_hour"] == 2.0 and measured["data"]["pool"] == 1
    db = f.db()
    db["items"]["gap/slow"]["fields"]["queue_wait_hours"] = 1                   # (the record sums it, per attempt)
    db["acts"] = []
    f.record.write_text(json.dumps(db))
    assert pools().returncode == 0 and not [a for a in f.db().get("acts", []) if "role=batch" in a]   # in its goal


def test_the_drops_main_is_main_as_pushed_never_the_checkouts_own(tmp_path):
    f = Factory(tmp_path)
    pushed = git(f.checkout, "rev-parse", "origin/main")
    (f.checkout / "unpushed.txt").write_text("a merge the queue has not pushed\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "merged, not pushed")
    code = "import sys; sys.path[:0] = [sys.argv[1]]; import fac, agents; print(agents.drop(fac.config()))"
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    assert git(tmp_path / "live" / "drop.git", "rev-parse", "main") == pushed


def test_the_queue_merges_onto_main_as_pushed_and_waits_on_unpushed_commits(tmp_path):
    f = Factory(tmp_path)
    other = tmp_path / "elsewhere"                                              # another queue pushes from elsewhere
    subprocess.run(["git", "clone", "-q", str(f.origin), str(other)], check=True, capture_output=True, env=f.env)
    (other / "theirs.txt").write_text("pushed from elsewhere\n")
    git(other, "add", "-A")
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "theirs"], check=True, env=f.env)
    git(other, "push", "-q", "origin", "main")
    theirs = git(other, "rev-parse", "HEAD")
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said[1] == "gap.merged"
    assert git(f.checkout, "rev-parse", "main^1") == theirs                     # merged onto main as pushed
    (tmp_path / "two").mkdir()
    f = Factory(tmp_path / "two")
    (f.checkout / "mine.txt").write_text("not pushed\n")                      # the checkout ahead of the remote
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "unpushed")
    other = tmp_path / "two" / "elsewhere"
    subprocess.run(["git", "clone", "-q", str(f.origin), str(other)], check=True, capture_output=True, env=f.env)
    (other / "more.txt").write_text("more\n")
    git(other, "add", "-A")
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "more"], check=True, env=f.env)
    git(other, "push", "-q", "origin", "main")                                  # diverged: no fast-forward
    head = git(f.checkout, "rev-parse", "main")
    approved_gaps(f, {"b": 1})
    said, lines = f.run("queue.py", "gap/b")
    nack = next(x["nack"] for x in lines if "nack" in x)
    assert said == [] and nack["count"] is False and "cannot fast-forward" in nack["why"]   # (not taken)
    assert git(f.checkout, "rev-parse", "main") == head                         # nothing merged


def test_the_pool_tuner_is_paused_and_never_lowers_the_owners_pools(tmp_path):
    import tomllib
    assert tomllib.loads((BIN.parent / "factory.toml").read_text())["pools"]["hold"] is True     # the operator's pause
    f = Factory(tmp_path)
    (f.model / "run").mkdir(exist_ok=True)
    pool = lambda: json.loads((f.model / "run" / "pools.json").read_text())                      # noqa: E731
    tune = lambda: subprocess.run([sys.executable, str(BIN / "pools.py"), "tune"], cwd=f.model, env=f.env,  # noqa: E731
                                  capture_output=True, text=True)
    (f.model / "run" / "pools.json").write_text(json.dumps({"implementor": 3, "reviewer": 2, "since": 0}))
    f.fold([{"event": "gap.parked", "item": "gap/hurt-by-main", "data": {"parked_at": time.time()}}], None)
    f.config.write_text(f.config.read_text().replace("probation = 3\n", "probation = 3\nhold = true\n"))
    r = tune()
    assert r.returncode == 0, r.stderr
    assert pool()["implementor"] == 3 and pool()["reviewer"] == 2 and "pool.lowered" not in r.stdout
    assert not [a for a in f.db().get("acts", []) if "role=implementor" in a or "role=reviewer" in a]
    said = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{") and "pool.measured" in x]
    assert {x["data"]["held"] for x in said if x["item"] == "pool/implementor"} == {"lower"}   # said, not done
    f.config.write_text(f.config.read_text().replace("hold = true\n", ""))
    assert tune().returncode == 0 and pool()["implementor"] == 2      # unheld: 3 was never run, its bound is too wide


def test_a_dead_letter_on_main_broken_tests_says_so(monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", sys.modules.get("fac") or module("fac"))
    monkeypatch.setitem(sys.modules, "review", type(sys)("review"))     # (its park is not called here)
    dead = module("dead")
    f = {"suites_fast": {"tests": [T]}, "main_broken_tests": [T], "built_main": "a" * 40}
    assert "fail on main too" in dead.on_main(f) and "aaaaaaaaaaaa" in dead.on_main(f)
    assert dead.on_main({**f, "suites_fast": {"tests": [T, "tests/test_z.py::test_own"]}}) == ""   # one is the gap's
    assert dead.on_main({"suites_fast": {}}) == ""


# ---- switch-without-draining: an approved switch starts at once, leaving the runs under way, and older switch
# requests are withdrawn

NOON = time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))              # today 12:00, local


def versions(f: Factory, n: int) -> list[str]:
    """n commits on the checkout's main, oldest first, the first running."""
    out = [git(f.checkout, "rev-parse", "HEAD")]
    for i in range(1, n):
        (f.checkout / f"v{i}.txt").write_text(f"{i}\n")
        git(f.checkout, "add", "-A")
        git(f.checkout, "commit", "-q", "-m", f"v{i}")
        out.append(git(f.checkout, "rev-parse", "HEAD"))
    live = f.tmp / "live"
    live.mkdir(exist_ok=True)
    (live / "current").symlink_to(out[0])
    return out


def asked(f: Factory, sha: str, action: str) -> str:
    """An upgrade installed and its switch asked for, its action ``action`` (held, ran, denied)."""
    db = f.db()
    aid = f"ergostat.action/{len(db.get('actions', {})) + 1:010x}"
    db.setdefault("actions", {})[aid] = action
    f.record.write_text(json.dumps(db))
    uid = f"upgrade/{sha[:12]}"
    f.fold([{"event": "upgrade.opened", "item": uid, "data": {"sha": sha}},
            {"event": "upgrade.installed", "item": uid, "data": {"check": "ok"}},
            {"event": "upgrade.switch-asked", "item": uid, "data": {"switch": action, "switch_action": aid}}], None)
    return uid


def held(f: Factory, *gids: str, block: str = "implementor") -> None:
    """These gaps' runs under way (their leases held by ``block``); every other gap's run ended."""
    db = f.db()
    for g in [*gids, *[i for i in db["items"] if i.startswith("gap/")]]:
        it = db["items"].setdefault(g, {"id": g, "kind": "gap", "state": "building", "fields": {}})
        it["fields"]["lease"] = {"block": block, "holder": f"run-{g[4:]}" if g in gids else None, "fence": 3}
    f.record.write_text(json.dumps(db))


def switcher(f: Factory, now: float) -> tuple[list[str], str, list[str]]:
    """One step of the switcher at ``now``: (the events it said, why, the switches it started)."""
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, live, drain; cfg = fac.config(); "
            "live.detach = lambda cfg, sha: print(json.dumps({'detached': sha})); "
            "print(json.dumps({'why': drain.step(cfg, float(sys.argv[2]))}))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), repr(now)], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return (f.fold([x for x in lines if "event" in x], None), lines[-1]["why"],
            [x["detached"] for x in lines if "detached" in x])


def test_an_approved_switch_starts_at_once_and_leaves_the_runs_under_way(tmp_path):
    """switch-without-draining: no quiet moment, no drain: the step that sees the approval starts the switch, with
    three runs under way, none given back; the AI blocks go on taking items."""
    f = Factory(tmp_path)
    a, b = versions(f, 2)
    uid = asked(f, b, "ran")                                                     # approved
    held(f, "gap/one", "gap/two", "gap/three")
    said, why, started = switcher(f, NOON)
    assert said == ["upgrade.switch-approved", "upgrade.switch-begun"] and started == [b], (said, why)
    assert "the runs under way carry on" in why and f.db().get("nacks") is None  # none waited for, none given back
    flag = f.model / "run" / "switch.json"
    assert json.loads(flag.read_text()) == {"sha": b, "switch_started": NOON} and f.item(uid)["state"] == "approved"
    assert f.item(uid)["fields"]["switch_begun_at"] == NOON
    gid = ready(f)                                                               # an AI run takes its item as ever
    assert not any("nack" in x for x in f.run("implement.py", gid)[1])
    assert switcher(f, NOON + 60)[1:] == (f"switching to {b[:12]}", [])         # started once
    said, why, started = switcher(f, NOON + 30 * 60)                             # its process never cleared the flag
    assert said == ["upgrade.failed", "intervention.recorded"] and started == []
    assert f.item(uid)["state"] == "failed" and not flag.exists() and "no outcome recorded" in f.item(uid)["fields"]["why"]
    assert switcher(f, NOON + 31 * 60)[::2] == ([], [])                          # never begun again
    for gone in ("drain_holds", "draining"):                                     # (nothing of the drain is left)
        assert not hasattr(module("fac"), gone), gone
    assert "[upgrade]" not in (BIN.parent / "factory.toml").read_text()


def test_an_installed_switch_waits_only_for_its_approval(tmp_path):
    f = Factory(tmp_path)
    _, b = versions(f, 2)
    uid = asked(f, b, "held")
    said, why, started = switcher(f, NOON)
    assert said == [] and started == [] and why == f"{uid} waits for its switch to be approved"
    f.fold([{"event": "upgrade.installed", "item": uid, "data": {"drained_at": NOON - 9999}}], None)  # (an earlier
    db = f.db()                                                                  # switch of it, installed again)
    db["actions"][f.item(uid)["fields"]["switch_action"]] = "ran"
    f.record.write_text(json.dumps(db))
    assert switcher(f, NOON + 60)[::2] == (["upgrade.switch-approved", "upgrade.switch-begun"], [b])
    assert f.item(uid)["fields"]["drained_at"] is None and f.item(uid)["fields"]["switch_begun_at"] == NOON + 60


def test_an_upgrade_the_draining_switcher_left_is_read_as_before(tmp_path):
    """The record the switcher before this one wrote still reads: an upgrade it left draining whose switch began
    (drained_at) and recorded nothing is failed; one still draining, its switch not begun, is switched at once."""
    f = Factory(tmp_path)
    _, b, c = versions(f, 3)
    u_b = asked(f, b, "ran")
    f.fold([{"event": "upgrade.draining", "item": u_b, "data": {"drain_began_at": NOON - 600, "drained_at": None}},
            {"event": "upgrade.drained", "item": u_b, "data": {"drained_at": NOON - 60}}], None)
    assert f.item(u_b)["state"] == "draining"
    said, _, started = switcher(f, NOON)
    assert said == ["upgrade.failed", "intervention.recorded"] and started == []
    u_c = asked(f, c, "ran")
    f.fold([{"event": "upgrade.switch-approved", "item": u_c, "data": {}},
            {"event": "upgrade.draining", "item": u_c, "data": {"drain_began_at": NOON, "drained_at": None}}], None)
    assert switcher(f, NOON + 60)[::2] == (["upgrade.switch-begun"], [c])


def test_the_switch_the_draining_switcher_runs_onto_this_version_is_under_way_not_failed(tmp_path):
    """The handover: the first switch onto this version is run by the switcher and live.py before it, which mark it
    under way in run/drain.json (switch_started) and record upgrade.drained, then start this version's engine, whose
    switcher steps at once, before that live.py records upgrade.switched. That switch is under way, not failed."""
    f = Factory(tmp_path)
    _, b = versions(f, 2)
    uid = asked(f, b, "ran")
    old = f.model / "run" / "drain.json"
    old.parent.mkdir(exist_ok=True)
    f.fold([{"event": "upgrade.switch-approved", "item": uid, "data": {"approved_at": NOON - 900}},
            {"event": "upgrade.draining", "item": uid, "data": {"drain_began_at": NOON - 600, "drained_at": None}},
            {"event": "upgrade.drained", "item": uid, "data": {"drained_at": NOON - 20}}], None)
    old.write_text(json.dumps({"sha": b, "since": NOON - 600, "switch_started": NOON - 20}))
    assert switcher(f, NOON) == ([], f"switching to {b[:12]}", [])               # the new engine's first step
    assert f.item(uid)["state"] == "draining" and old.exists()
    old.unlink()                                                                 # live.py before: switched, its flag
    f.fold([{"event": "upgrade.switched", "item": uid, "data": {}}], None)       # removed
    assert switcher(f, NOON + 60)[::2] == ([], []) and f.item(uid)["state"] == "switched"
    # one whose live.py never ended it: given up 30 minutes on, as this switcher's own
    old.write_text(json.dumps({"sha": b, "since": NOON - 600, "switch_started": NOON - 20}))
    f.fold([{"event": "upgrade.draining", "item": uid, "data": {"drained_at": None}},
            {"event": "upgrade.drained", "item": uid, "data": {"drained_at": NOON - 20}}], None)
    assert switcher(f, NOON + 25 * 60)[::2] == ([], [])
    said, _, started = switcher(f, NOON + 30 * 60)
    assert said == ["upgrade.failed", "intervention.recorded"] and started == [] and not old.exists()
    old.write_text("not json")                                                   # unreadable: begun when written
    assert switcher(f, time.time())[1].startswith("switching to")
    old.write_text(json.dumps({"sha": b, "since": NOON}))                        # only draining: no switch under way
    assert switcher(f, NOON + 31 * 60)[1] == "no switch waiting"


def test_a_switch_that_records_no_outcome_is_failed_and_never_begun_again(tmp_path):
    f = Factory(tmp_path)
    a, b = versions(f, 2)
    uid = asked(f, b, "ran")
    held(f, "gap/long", block="reviewer")
    assert switcher(f, NOON)[::2] == (["upgrade.switch-approved", "upgrade.switch-begun"], [b])
    flag = f.model / "run" / "switch.json"
    r = subprocess.run([sys.executable, str(BIN / "live.py"), "switch", b], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.returncode != 0 and "not installed" in r.stderr and not flag.exists()   # its flag goes, whatever
    # becomes of it; one that recorded no outcome is failed, asked of the coordinator, and not begun again
    said, why, started = switcher(f, NOON + 60)
    assert said == ["upgrade.failed", "intervention.recorded"] and started == [] and f.item(uid)["state"] == "failed"
    assert switcher(f, NOON + 120)[::2] == ([], []) and not flag.exists() and f.db().get("nacks") is None
    flag.write_text("not json")                                                  # unreadable: begun when written
    assert switcher(f, time.time())[1].startswith("switching to")


def test_an_older_switch_request_is_withdrawn(tmp_path):
    f = Factory(tmp_path)
    old, running, mid, new, newer = versions(f, 5)
    (f.tmp / "live" / "current").unlink()
    (f.tmp / "live" / "current").symlink_to(running)
    u_old, u_mid, u_new = asked(f, old, "held"), asked(f, mid, "ran"), asked(f, new, "held")
    held(f)
    said, why, started = switcher(f, NOON)
    assert said == ["upgrade.withdrawn", "upgrade.withdrawn"] and started == [] and "waits for its switch" in why
    assert f.item(u_old)["fields"]["superseded_by"] == f"the running {running[:12]}"
    assert f.item(u_mid)["fields"]["superseded_by"] == u_new                      # approved, but older: withdrawn
    assert [f.item(u)["state"] for u in (u_old, u_mid, u_new)] == ["withdrawn", "withdrawn", "installed"]
    db = f.db()
    aid_old, aid_mid, aid_new = (f.item(u)["fields"]["switch_action"] for u in (u_old, u_mid, u_new))
    assert db["actions"][aid_old] == "denied" and f"superseded by the running {running[:12]}" in db["notes"][aid_old]
    assert db["actions"][aid_mid] == "ran" and db["actions"][aid_new] == "held"  # (an action that ran is not undone)
    assert switcher(f, NOON + 60)[0] == []                                       # only the newest waits
    db = f.db()
    db["actions"][aid_new] = "ran"
    f.record.write_text(json.dumps(db))
    said, _, started = switcher(f, NOON + 120)
    assert said == ["upgrade.switch-approved", "upgrade.switch-begun"] and started == [new]
    u_newer = asked(f, newer, "held")                                            # installed while the switch runs
    said, why, started = switcher(f, NOON + 180)
    assert said == [] and why == f"switching to {new[:12]}" and started == []   # nothing withdrawn meanwhile
    assert f.item(u_new)["state"] == "approved" and f.item(u_newer)["state"] == "installed"
    f.fold([{"event": "upgrade.switched", "item": u_new, "data": {"switch": "ran"}},      # the switch as live.py
            {"event": "upgrade.kept", "item": u_new, "data": {}}], None)                 # makes it
    (f.tmp / "live" / "current").unlink()
    (f.tmp / "live" / "current").symlink_to(new)
    (f.model / "run" / "switch.json").unlink()
    said, why, started = switcher(f, NOON + 240)
    assert said == [] and started == [] and f.item(u_newer)["state"] == "installed"   # it waits, its request open


ALLOWED = ["Bash(git rm:*)", "Bash(git mv:*)", "Bash(git restore:*)", "Bash(rm:*)",
           "Bash(uv run python scripts/named_tests.py:*)",
           "Bash(uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py:*)"]
IMPLEMENTOR = {"ai": {"implementor_model": "opus", "implementor_session_usd": 1.0}}


def agents_module():
    sys.modules.setdefault("fac", module("fac"))                                 # (agents.py imports fac beside it)
    return module("agents")


def test_the_implementor_may_remove_files_and_run_the_watched_suite():
    agents = agents_module()
    args = agents.claude_args(IMPLEMENTOR, "implementor")
    allowed = args[args.index("--allowedTools") + 1].split(",")
    assert set(ALLOWED) <= set(agents.TOOLS["implementor"]) and set(ALLOWED) <= set(allowed)
    for role in ("reviewer", "planner", "librarian", "researcher"):              # only the implementor writes
        assert not set(ALLOWED) & set(agents.TOOLS[role]), role
    prompt = (BIN.parent / "prompts" / "implementor.md").read_text()
    assert "under `/tmp`" in prompt and "If a command is refused, say which one" in prompt


def test_the_deny_list_still_holds():
    agents = agents_module()
    assert agents.DENY == ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(git stash:*)",
                           "Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)", "Bash(gh:*)", "WebFetch", "WebSearch"]
    args = agents.claude_args(IMPLEMENTOR, "implementor")
    assert args[args.index("--disallowedTools") + 1].split(",") == agents.DENY   # every one still refused to it
    words = lambda t: t.removeprefix("Bash(").removesuffix(":*)")  # noqa: E731   (a tool, or a command's words)
    denied = tuple(words(d) for d in agents.DENY)
    assert not [t for t in agents.TOOLS["implementor"] if words(t).startswith(denied)]   # nor a narrower form of one


def test_refused_tool_calls_are_recorded_on_the_session(tmp_path, monkeypatch, capsys):
    import yaml
    monkeypatch.chdir(tmp_path)
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    monkeypatch.setitem(sys.modules, "sessions", module("sessions"))
    monkeypatch.setenv("ERGOSTAT_ITEM", "gap/alpha-thing")
    cfg = {"paths": {"run": str(tmp_path / "run"), "live": str(tmp_path / "live")},
           "ai": {"mode": "container", "implementor_model": "opus", "implementor_session_usd": 5.0}}
    fake = type(sys)("agents")
    tok = "s3cr3t-" + "x" * 200                                                  # (longer than a summary's cut)
    fake.token = lambda cfg: tok
    answers = [{"permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "rm x.py"}},
                                       {"tool_name": "Bash", "tool_input": {"command": "uv run python scripts/a.py"}}]},
               {},                                                              # a result with no denials field
               {"permission_denials": []},
               {"permission_denials": [{"tool_name": "Bash", "tool_input": {"command": f"curl -H 'X: {tok}' h"}},
                                       {"tool_name": "Edit", "tool_input": {"old_string": "a" * 120 + tok}},   # (cut at 160)
                                       f"odd {tok}"]},
               None]                                                            # a timeout: no result at all (out=None)

    def session(cfg, role, brief, work, keep=None):
        keep.copy.tok = tok                                                      # (as agents.session does)
        answer = answers.pop(0)
        if answer is None:
            raise RuntimeError("the implementor session ran past 5400s and was killed")   # (as agents.py does)
        return {"type": "result", "subtype": "success", "is_error": False, "result": "Done", "total_cost_usd": 0.1,
                "num_turns": 1, **answer}
    fake.session = session
    monkeypatch.setitem(sys.modules, "agents", fake)
    lines = []
    for _ in range(5):
        try:
            fac.session(cfg, "implementor", "brief", tmp_path)
        except RuntimeError:
            pass
        lines.append([json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"event"')])
    timed_out = lines.pop()
    err = next(x["data"] for x in timed_out if x["event"] == "session.errored")
    assert err["tool_denials_unknown"] == 1 and "tool_denials" not in err and "ran past" in err["error"]
    end = [next(x["data"] for x in got if x["event"] == "session.ended") for got in lines]
    on_gap = [[(x["item"], x["data"]) for x in got if x["event"] == "gap.measured"] for got in lines]
    assert end[0]["tool_denials"] == 2 and end[0]["denied"] == ["Bash: rm x.py", "Bash: uv run python scripts/a.py"]
    assert on_gap[0] == [("gap/alpha-thing", {"tool_denials": 2, "denied": end[0]["denied"]})]
    assert end[1]["tool_denials_unknown"] == 1 and "tool_denials" not in end[1]          # unknown, never 0
    assert on_gap[1] == [("gap/alpha-thing", {"tool_denials_unknown": 1})]
    assert end[2]["tool_denials"] == 0 and end[2]["denied"] == [] and on_gap[2] == []  # none: nothing more on the gap
    assert end[3]["tool_denials"] == 3 and end[3]["denied"][0] == "Bash: curl -H 'X: [token]' h"
    said = json.dumps(lines[3])                                                  # the token, nor a prefix of it, kept
    assert "s3cr3t" not in said and all("[token]" in d for d in end[3]["denied"]), end[3]["denied"]
    lines.pop()                                                       # (the folds below count the first three, the timeout)
    lines.append(timed_out)

    (tmp_path / "f").mkdir()
    f = Factory(tmp_path / "f")                                                  # the gap and sessions, by the model's folds
    measure = lambda name: subprocess.run([sys.executable, str(BIN / "measure.py"), name], cwd=f.model,  # noqa: E731
                                          env=f.env, capture_output=True, text=True)
    f.fold([x for x in lines[1] + lines[3]], None)                     # only sessions whose refusals are unknown
    r = measure("tool-denials")
    assert r.returncode != 0 and "no value" in r.stderr and not r.stdout.strip()    # unknown, never 0
    f.fold([x for got in (lines[0], lines[2]) for x in got], None)
    g = f.item("gap/alpha-thing")["fields"]
    assert g["tool_denials"] == 2 and g["tool_denials_unknown"] == 2 and len(g["denied"]) == 2
    r = measure("tool-denials")
    assert r.returncode == 0 and float(r.stdout) == 2.0, r.stderr     # the 2 refused; the timeout and the silent one
    assert "2 session(s) whose refusals are unknown" in r.stderr              # left out, said, not counted as refused
    r = measure("tool-denials-unknown")
    assert r.returncode == 0 and float(r.stdout) == 2.0, r.stderr
    goal = yaml.safe_load((BIN.parent / "model" / "measures.yaml").read_text())["goals"]["no-tool-denials"]
    assert (goal["auxiliary"], goal["hold"], goal["tolerance"]) == ("tool-denials", "<= 0", 0)


# ---- switcher-actually-runs (docs/roadmap/overnight/switcher-actually-runs.md): the timed blocks on the engine's clock

def instance_engine(f: Factory):
    """The real engine on the factory's model in a disposable instance (``f.model``: dev/ linked, a record of its own),
    its loop not started: (the engine, the blocks its clock starts on their own: its plan, as ``_schedule`` reads it)."""
    from ergostat import model as mdl
    from ergostat.spec.engine import Engine
    from ergostat.store import Project
    (f.model / "ergostat.yaml").write_text((ROOT / "ergostat.yaml").read_text())
    e = Engine(Project(mdl.load(f.model)), say=lambda s: None)
    _, timed_blocks, _, crons, _ = e._plan(e.spec, {}, {})
    return e, {b.name for b in timed_blocks} | {k.split("/", 1)[1] for k in crons if k.startswith("block/")}


def on_the_clock(tmp_path, name: str, goal: str) -> None:
    from ergostat.spec.ir import Ref
    e, scheduled = instance_engine(Factory(tmp_path))
    b = e.spec.blocks[name]
    assert b.every and name in scheduled                                       # the clock starts it
    assert e.spec.commanders_of(name) == [] and e.command_of(b) == (None, {})  # and nothing commands it: whether the
    assert Ref("goal", goal) in b.reads() and name in e.spec.loop(goal).controllers   # goal holds or not; it is read


def test_the_switcher_is_on_the_engines_schedule(tmp_path):
    on_the_clock(tmp_path, "switcher", "upgrades-switched-to")


def test_the_pipeline_watch_is_on_the_engines_schedule(tmp_path):
    on_the_clock(tmp_path, "pipeline-watch", "no-stuck-gaps")


def in_times_yaml(part) -> bool:
    return part.where is not None and Path(part.where.file).name == "times.yaml"


def test_the_time_goals_have_no_check_findings(tmp_path):
    """state-times-in-the-loop: check's missing-feedback, auxiliary-without-causes and collector-undescribed say
    nothing of dev/model/times.yaml (the reader check runs, before the extremes, which say none of the three); each
    goal left in it is read by the pipeline watch, its loop closes, and the watch's own reading of the file finds
    exactly these goals (a goal it could not parse would never be acted on)."""
    spec, problems = read(ROOT / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.level == "error"] == []
    codes = ("missing-feedback", "auxiliary-without-causes", "collector-undescribed")
    assert [f"{p.code}@{p.about}" for p in problems if p.code in codes and in_times_yaml(p)] == []
    goals = {n for n, g in spec.goals.items() if in_times_yaml(g)}
    assert 0 < len(goals) <= 16                                                # fewer goals: no p90 beside each median
    assert not [n for n in goals if n.endswith("-p90")]
    assert goals <= {r.name for r in spec.blocks["pipeline-watch"].reads() if r.kind == "goal"}
    assert [n for n in goals if not spec.loop(n).closes] == []
    # each closes through the manager's sessions (what they do moves the time), not by a path that merely exists
    assert [n for n in goals if "flow.situations-handled" not in spec.loop(n).through] == []
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import watch, times; "
            "print(json.dumps(sorted(m[0] for m in watch.TIME_GOAL.findall(times.GOALS.read_text()))))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == sorted(goals)
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import watch, times, pathlib; p = pathlib.Path(sys.argv[2]); "
            "p.write_text(times.GOALS.read_text().replace('ready-short: {auxiliary: in-ready-hours, hold: \"<=', "
            "'ready-short: {auxiliary: in-ready-hours, hold: \"<')); times.GOALS = p; "
            "off, read = watch.time_goals({}, 0); print(json.dumps([off, read]))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(tmp_path / "times.yaml")], capture_output=True,
                       text=True, check=False)
    assert r.returncode == 0, r.stderr
    off, got = json.loads(r.stdout)                       # a goal reworded past the watch's pattern: never on target
    assert "ready-short" not in got and [t["why"] for t in off if "ready-short" in t["why"]]
    measures = {a for a, x in spec.auxiliaries.items() if in_times_yaml(x)} - {spec.goals[n].of.name for n in goals}
    header = (ROOT / "dev" / "model" / "times.yaml").read_text().split("\ndefaults:")[0]
    assert "-p90" in header and all(m.endswith("-p90") or m in header for m in measures)   # each plain measure said
    # closing the loops draws no new boundary findings: times, the manager and the load interlock stay separable
    from ergostat.spec import architecture
    said: list[str] = []
    architecture.findings(spec, lambda code, msg, _, about: said.append(f"{code}@{about}: {msg}"))
    near = ("system.times", "system.managing", "system.load")
    found = [x for x in said if x.split(":")[0].split("@")[1] in near and not x.startswith("time-scales")]
    assert found == [], "\n".join(found)

def test_a_time_goal_off_reaches_the_managers_session(tmp_path):
    """state-times-in-the-loop: a time goal off past its tolerance is a trigger of the watch's next session and is in
    the pipeline manager's brief; one on target is read and not raised; one with no gap in its window is unknown (None
    on the situation), never on target and never 0; answered, the same reading is not raised again, a worse one is.
    One that cannot be read (a malformed or NaN time_in, a measure times.py does not know) is None and a trigger."""
    f = pipe(tmp_path)
    left = f.now - 3600

    def slow(i: int, hours: float) -> None:
        f.put(f"gap/slow-{i}", "merged", branch=f"slow-{i}", merged_at=left,
              time_in={"ready": {"hours": hours, "visits": 1, "left": left}, "queued": {"hours": 0.25, "visits": 1,
                                                                                       "left": left}})
    for i, h in enumerate((4.0, 5.0, 6.0)):                                    # ready-short: <= 2, tolerance 0.5
        slow(i, h)
    s = f.watch()
    (t,) = [t for t in s["triggers"] if t["trigger"] == "time"]
    assert t["subject"] == "goal.ready-short" and "reads 5 " in t["why"]
    assert s["times"]["ready-short"] == 5.0 and s["times"]["queued-short"] == 0.25   # (queued: read, on target)
    assert "planned-short" in s["times"] and s["times"]["planned-short"] is None     # nothing left planned: unknown
    answer = {"calls": [], "answers": {t["print"]: "asked the researcher why ready waits"}, "summary": "ready waits"}
    said, _ = f.run("manager.py", s["id"], FACTORY_STANDIN_PIPELINE_MANAGER="```json\n" + json.dumps(answer) + "\n```")
    f.drain()
    assert said == ["situation.handled"]
    done = f.item(s["id"])
    text = (f.model / done["fields"]["context"]["brief"].removeprefix("file:")).read_text()
    assert t["print"] in text and "goal ready-short is off" in text

    def again() -> list[dict]:
        db = f.db()
        for x in db["items"].values():
            if x["kind"] == "situation":                                       # each answered, the schedule due again
                x["state"], x["fields"]["raised_at"] = "handled", f.now - 3 * 3600
        f.record.write_text(json.dumps(db))
        got = f.watch()
        return [x for x in (got or {}).get("triggers", []) if x["trigger"] == "time"]
    f.put("gap/other", "ready", ago=60, branch="other")                       # (the pipeline changed)
    assert again() == []                                                       # answered, the same reading
    slow(3, 20.0)
    slow(4, 20.0)                                                              # median 6h: further off
    (t2,) = again()
    assert t2["subject"] == "goal.ready-short" and t2["print"] != t["print"]
    assert again() == []                                                       # (answered: not again)

    def ready(hours: float | str) -> None:                                     # every ready time made the same
        for i in range(5):
            f.put(f"gap/slow-{i}", "merged", branch=f"slow-{i}", merged_at=left,
                  time_in={"ready": {"hours": hours, "visits": 1, "left": left}})
    ready(1.0)
    assert again() == []                                                       # back on target: the episode ends
    ready(6.0)                                                                 # off again by as much as t2 was
    (t3,) = again()
    assert t3["subject"] == "goal.ready-short" and t3["print"] not in (t["print"], t2["print"])
    ready("soon")                                                              # (lesson-5) unreadable, answered,
    (u,) = again()                                                             # read again, then the same error:
    assert "cannot be read" in u["why"] and again() == []                      # a new episode, raised again
    ready(1.0)
    assert again() == []
    ready("soon")
    (u2,) = again()
    assert u2["why"] == u["why"] and u2["print"] != u["print"]
    # (lesson-3) a reading that fails is a trigger naming the goal and the error; an empty window stays silent
    code = ("import sys, json, pathlib; sys.path[:0] = [sys.argv[1]]; import watch, times; p = pathlib.Path(sys.argv[2])"
            "; arg = json.loads(sys.argv[3]); p.write_text(times.GOALS.read_text().replace(*arg['swap']) "
            "if arg['swap'] else times.GOALS.read_text()); times.GOALS = p; "
            "print(json.dumps(watch.time_goals(arg['gaps'], arg['now'])))")

    def goals(gaps: dict, swap: list | None = None) -> tuple[dict, dict]:
        arg = json.dumps({"gaps": gaps, "now": f.now, "swap": swap})
        r = subprocess.run([sys.executable, "-c", code, str(BIN), str(tmp_path / "times.yaml"), arg],
                           capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr
        off, got = json.loads(r.stdout)
        return {x["subject"]: x["why"] for x in off}, got

    def gap(time_in) -> dict:
        return {"g": {"id": "gap/g", "state": "merged", "fields": {"time_in": time_in}}}
    assert goals({}) == ({}, goals({})[1]) and set(goals({})[1].values()) == {None}   # nothing in a window: silent
    off, got = goals(gap({"ready": {"hours": "soon", "visits": 1, "left": left}}))  # a malformed time_in
    assert got["ready-short"] is None and "goal ready-short cannot be read" in off["goal.ready-short"]
    off, got = goals(gap({"ready": {"hours": 1.0, "visits": 1}}))                   # its `left` missing
    assert got["ready-short"] is None and "cannot be read" in off["goal.ready-short"]
    off, got = goals(gap({"ready": {"hours": float("nan"), "visits": 1, "left": left},
                          "queued": {"hours": 0.25, "visits": 1, "left": left}}))   # one NaN among them
    assert got["ready-short"] is None and "not finite" in off["goal.ready-short"]
    assert got["queued-short"] == 0.25 and "goal.queued-short" not in off          # (the others still read)
    off, got = goals({}, ["auxiliary: in-ready-hours,", "auxiliary: in-nowhere-hours,"])   # a measure none knows
    assert got["ready-short"] is None and "in-nowhere-hours" in off["goal.ready-short"]
    off, got = goals({}, ["auxiliary: in-ready-hours,", "auxiliary: nowhere,"])     # one values() refuses
    assert got["ready-short"] is None and "nowhere" in off["goal.ready-short"]


def test_check_reports_a_schedule_a_goal_removes(tmp_path, capsys):
    from ergostat.cli import main
    model = textwrap.dedent("""\
        name: t
        stocks:
          q: {unit: jobs, sensor: {run: echo 0, every: 1m}}
        flows:
          done: {from: q}
        goals:
          short: {stock: q, hold: "<= 0"}
        blocks:
          sweep: {type: program, run: echo 1, every: 1m, goal: short, out: flow.done}
        """)

    def found(text: str, where: Path) -> list[str]:
        where.mkdir()
        (where / "ergostat.yaml").write_text(text)
        main(["-C", str(where), "check", "--json"])
        return [x["about"] for x in json.loads(capsys.readouterr().out)["found"] if x["code"] == "schedule-removed"]
    assert found(model, tmp_path / "goal") == ["block.sweep"]
    assert found(model.replace("goal: short", "in: goal.short"), tmp_path / "read") == []
    assert found(model.replace("every: 1m, goal", "goal"), tmp_path / "unscheduled") == []    # (paced by nothing)
    assert found(model.replace("every: 1m, goal", "cron: '0 4 * * *', goal"), tmp_path / "cron") == ["block.sweep"]
    old = tmp_path / "main"                                    # the factory's model as main had it: both caught
    (old / "dev").mkdir(parents=True)
    for x in (ROOT / "dev").iterdir():
        if x.name != "model":
            (old / "dev" / x.name).symlink_to(x)
    (old / "dev" / "model").mkdir()
    for x in (ROOT / "dev" / "model").iterdir():
        (old / "dev" / "model" / x.name).write_text(x.read_text().replace("in: goal.upgrades-switched-to    #", "goal: "
                                                    "upgrades-switched-to    #").replace("in: [goal.no-stuck-gaps,",
                                                                            "goal: no-stuck-gaps\n    in: ["))
    (old / "ergostat.yaml").write_text((ROOT / "ergostat.yaml").read_text())

    def noted(path: Path) -> set[str]:      # (a craft note, not an extremes finding: a second model's extremes, ~60 s
        return {p.about for p in read(path, extremes=False)[1] if p.code == "schedule-removed"}   # of a worker, not run)
    assert {"block.switcher", "block.pipeline-watch"} <= noted(old / "ergostat.yaml")
    # the factory's now: only plan-lint, whose every: is meant as a pace (it sweeps while plans wait in planned); the
    # modelling template's paced blocks are its own (parts a template made are not noted)
    assert noted(ROOT / "ergostat.yaml") == {"block.plan-lint"}


def test_a_paced_block_raises_no_modelling_request(tmp_path):
    """``schedule-removed`` is said by check, never sent to the modelling loop: a goal: with every: is also a meant pace
    (SPEC §9.1), so no tier (and above all not the ai tier) is asked to change it."""
    from ergostat import model as mdl
    from ergostat.numbers import requests as rq
    from ergostat.store import Project
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""\
        name: t
        stocks:
          q: {unit: jobs, sensor: {run: echo 0, every: 1m}}
        flows:
          done: {from: q}
        goals:
          short: {stock: q, hold: "<= 0"}
        blocks:
          sweep: {type: program, run: echo 1, every: 1m, goal: short, out: flow.done}
        """))
    p = Project(mdl.load(tmp_path))
    assert "schedule-removed" in {x.code for x in read(tmp_path / "ergostat.yaml", extremes=False)[1]}   # check says it
    rq.sync(p, coherence=False, extremes=False)
    got = rq.stored(p).values()
    assert any(r["code"] == "no-description" for r in got)          # the other notes still reach the loop
    assert [r for r in got if r["code"] == "schedule-removed"] == []


@pytest.mark.serial            # (each switcher run is ~43 CPU-s against its 120 s bound: it holds on a quiet machine)
def test_an_approved_switch_switches_through_the_engine(tmp_path, monkeypatch):
    from ergostat.actions import gate
    f = Factory(tmp_path)
    f.config.write_text(f.config.read_text().replace("[instance]\nport = 0\n", "[instance]\nport = 0\nhealth_wait = 1\n")
                        .replace('run = "run"', f'run = "{f.model / "run"}"'))   # (the switch runs in live/instance)
    monkeypatch.setenv("FACTORY_CONFIG", str(f.config))                        # (the engine's runs inherit it)
    a, b = versions(f, 2)
    live = tmp_path / "live"
    fake_version(live, a, starts=True)
    fake_version(live, b, starts=True)
    (live / "instance").mkdir()
    subprocess.run([sys.executable, str(BIN / "live.py"), "init"], cwd=live / "instance", env=f.env,
                   check=True, capture_output=True)
    e, scheduled = instance_engine(f)
    p, spec = e.p, e.spec
    held = gate.request(p, spec, "switch-instance", {"sha": b}, {"block": "upgrader"}, asker="program", key=b)
    assert held["state"] == "requested"
    uid = f"upgrade/{b[:12]}"
    for ev, data in [("upgrade.opened", {"sha": b}), ("upgrade.installed", {"check": "ok", "previous": a}),
                     ("upgrade.switch-asked", {"switch": "held", "switch_action": held["id"]})]:
        p.events.add(ev, item=uid, source="upgrader", data=data)      # the live order: asked, then approved
    assert gate.approve(p, spec, held["id"], by="coordinator")["state"] == "ran"   # approving runs drain.py approve
    sw = spec.blocks["switcher"]
    assert "switcher" in scheduled
    try:
        assert e.start(sw, "schedule")                         # one of its minutes: it switches (_schedule)
        deadline = time.monotonic() + 120
        while "switcher" in e.running and time.monotonic() < deadline:
            time.sleep(0.2)
        assert "switcher" not in e.running
        said = [x["type"] for x in p.events.query(n=None, item=uid)]
        assert said[-2:] == ["upgrade.switch-approved", "upgrade.switch-begun"], said
        runs = p.events.query(n=None, type="agent.started", item="switcher")
        assert len(runs) == 1 and runs[0]["data"]["trigger"] == "schedule"
        deadline = time.monotonic() + 90                       # the switch, in its own process (live.py switch)
        while (os.readlink(live / "current") != b or (f.model / "run" / "switch.json").exists()) \
                and time.monotonic() < deadline:
            time.sleep(0.5)
        assert os.readlink(live / "current") == b and not (f.model / "run" / "switch.json").exists()
    finally:
        e.close()


# ---- merges of the files many gaps edit at once (.gitattributes)


def merge_two(tmp: Path, rel: str, base: str, one: str, two: str, attributes: bool = True) -> tuple[int, str]:
    """``base`` committed at ``rel`` on main with its folder's .gitattributes from this repository (or none), ``one`` on
    a branch, ``two`` on main, and the branch merged in: (git merge's return code, the file after it)."""
    (tmp / rel).parent.mkdir(parents=True)
    git(tmp, "init", "-q", "-b", "main")
    if attributes:          # docs/.gitattributes, dev/knowledge/.gitattributes: each beside the file it merges
        attrs = Path(rel).parent / ".gitattributes"
        (tmp / attrs).write_text((ROOT / attrs).read_text())
    (tmp / rel).write_text(base)
    git(tmp, "add", "-A")
    git(tmp, "commit", "-qm", "base")
    git(tmp, "checkout", "-qb", "one")
    (tmp / rel).write_text(one)
    git(tmp, "commit", "-qam", "one")
    git(tmp, "checkout", "-q", "main")
    (tmp / rel).write_text(two)
    git(tmp, "commit", "-qam", "two")
    r = subprocess.run(["git", "-C", str(tmp), "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "-q",
                        "--no-edit", "one"], capture_output=True, text=True)
    return r.returncode, (tmp / rel).read_text()


MERGED_GAPS = """\
# Known gaps

## Things

- **Alpha** (open): a.
- **Beta** (open): b.
- **Gamma** (open): c.

## Done recently

- **Older** (done, 1111111): long ago.
"""


def test_two_gaps_editing_gaps_md_merge_cleanly(tmp_path):
    """Two gaps that each finish a different entry, moving it to the top of *Done recently*, merge without a conflict
    (they conflict without the union merge); two that edit entries side by side merge too, and the entries that
    leaves twice are the intake's to report (tests/test_backlog.py::test_a_duplicated_gaps_entry_is_reported)."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    intake = module("intake")
    one = MERGED_GAPS.replace("- **Alpha** (open): a.\n", "").replace(
        "## Done recently\n\n", "## Done recently\n\n- **Alpha** (done, 2222222): a.\n")
    two = MERGED_GAPS.replace("- **Gamma** (open): c.\n", "").replace(
        "## Done recently\n\n", "## Done recently\n\n- **Gamma** (done, 3333333): c.\n")
    assert merge_two(tmp_path / "a", "docs/GAPS.md", MERGED_GAPS, one, two, attributes=False)[0] != 0
    rc, text = merge_two(tmp_path / "b", "docs/GAPS.md", MERGED_GAPS, one, two)
    assert rc == 0 and "<<<<<<<" not in text
    assert {e["title"]: e["gaps_says"] for e in intake.gaps_md(text)} == {"Beta": "open"}
    assert "**Alpha** (done, 2222222)" in text and "**Gamma** (done, 3333333)" in text and intake.twice(text) == {}
    rc, text = merge_two(tmp_path / "c", "docs/GAPS.md", MERGED_GAPS, MERGED_GAPS.replace("(open): a.", "(open): a!"),
                         MERGED_GAPS.replace("(open): b.", "(done, 4444444): b."))
    assert rc == 0 and sorted(intake.twice(text)) == ["gap/alpha", "gap/beta"]


def test_two_lessons_editing_review_lessons_merge_cleanly(tmp_path):
    """Two gaps that each add to the review lessons (a line on the last lesson, a new lesson after it) merge without a
    conflict, keeping both; without the union merge they conflict."""
    base = (ROOT / "dev" / "knowledge" / "review-lessons.md").read_text()
    one = base.rstrip("\n") + "\nSeen as: one more case, from the first gap.\n"
    two = base + "\n## 99. A lesson from the second gap\nIts shape.\n**Check:** its check.\n"
    rel = "dev/knowledge/review-lessons.md"
    assert merge_two(tmp_path / "a", rel, base, one, two, attributes=False)[0] != 0
    rc, text = merge_two(tmp_path / "b", rel, base, one, two)
    assert rc == 0 and "<<<<<<<" not in text and text.startswith(base.rstrip("\n"))
    assert "one more case, from the first gap" in text and "## 99. A lesson from the second gap" in text


# ---- park-owns-resume (docs/roadmap/overnight/park-owns-resume.md): whoever parks says why and what would end it

def pipe(tmp: Path, **kw):
    """The pipeline manager's fixture (its fake ergostat records `event --add`)."""
    from tests.test_factory_manager import Pipe
    return Pipe(tmp, **kw)


def park_verdict(**verdict) -> str:
    return "The stand-in.\n```json\n" + json.dumps({"verdict": "park", "blocking": [], "where_it_stopped": "work done",
                                                    **verdict}) + "\n```"


def parked_by_review(tmp: Path, **verdict):
    """A gap built and parked by the reviewer with ``verdict`` (its park fields); (the fixture, the gap)."""
    f = pipe(tmp)
    gid = ready(f)
    f.run("implement.py", gid)
    assert f.run("review.py", gid, FACTORY_STANDIN_REVIEWER=park_verdict(**verdict))[0][-1] == "gap.parked"
    return f, gid


def resumed(f) -> list[str]:
    """One pass of the park resumer: the events it recorded."""
    f.tool("parks.py", "resume")
    return f.drain()


def test_a_park_waiting_on_a_gap_is_resumed_when_it_merges(tmp_path):
    f, gid = parked_by_review(tmp_path, parked_for="waits_on", waits_on="gap/carried")
    g = f.item(gid)["fields"]
    assert g["parked_for"] == "waits_on" and g["parked_until"] == {"gap": "gap/carried"}
    f.put("gap/carried", "approved", branch="carried")
    assert resumed(f) == []                                                   # not merged yet: still waits
    assert (f.watch() or {}).get("trigger") != "parked"                       # nor is the manager asked about it
    f.put("gap/carried", "merged", branch="carried", main_sha=git(f.checkout, "rev-parse", "origin/main"))
    assert resumed(f) == ["gap.requested", "gap.resumed"]
    c = f.item("gap/alpha-thing-continued")
    assert c["fields"]["continues"] == "alpha-thing" and c["fields"]["requested_by"] == "park-resume"
    r = f.item(gid)["fields"]
    assert r["resumed_as"] == "gap/alpha-thing-continued" and r["resumed_for"] == "waits_on"
    assert r["cleared"] == "gap/carried merged, on origin/main"
    assert [i for i in f.db()["items"].values() if i["kind"] == "intervention"] == []   # a loop, not an intervention
    assert resumed(f) == []                                                   # resumed once
    assert f.py("import measure; print(json.dumps([measure.reading(n, kind='waits_on') for n in "
                "('parks', 'resumes')]))") == [1.0, 1.0]


def test_a_park_needing_an_action_is_resumed_when_it_is_recorded(tmp_path):
    f = pipe(tmp_path)
    gid = ready(f)
    f.fold([{"event": "gap.need-met", "item": gid, "data": {"need_met": "an old measurement"}}], None)   # stale
    f.run("implement.py", gid)
    f.run("review.py", gid, FACTORY_STANDIN_REVIEWER=park_verdict(
        parked_for="needs", needs={"action": "measure the warm start", "who": "coordinator"}))
    g = f.item(gid)["fields"]
    assert g["parked_for"] == "needs" and g["parked_until"] == {"action": "measure the warm start", "who": "coordinator"}
    assert g["need_met"] is None and resumed(f) == []                         # the park cleared the old one
    f.fold([{"event": "gap.need-met", "item": gid, "data": {"need_met": "4.1 s warm"}}], None)
    assert resumed(f) == ["gap.requested", "gap.resumed"]
    assert f.item(gid)["fields"]["cleared"] == "needed measure the warm start (coordinator): done, 4.1 s warm"
    assert f.item("gap/alpha-thing-continued")["state"] == "open"


def test_a_defect_park_is_never_resumed_by_the_program(tmp_path):
    f, gid = parked_by_review(tmp_path)                                       # a park with no kind said: a defect
    assert f.item(gid)["fields"]["parked_for"] == "defect"
    unclear = [{"parked_for": "waits_on"}, {"parked_for": "waits_on", "waits_on": "../x"},
               {"parked_for": "needs", "needs": {"who": "x"}}, {"parked_for": "split"}, {"parked_for": "kill-rule"}]
    got = f.py("import parks; print(json.dumps([parks.of_verdict(v) for v in json.loads(sys.argv[1])]))",
               json.dumps(unclear + [{"parked_for": "waits_on", "waits_on": ["abc1234", "deadbeef00"]}]))
    assert got[:-1] == [{"parked_for": "defect", "parked_until": None}] * len(unclear)   # nothing that could clear
    assert got[-1] == {"parked_for": "waits_on", "parked_until": {"commits": ["abc1234", "deadbeef00"]}}
    f.put("gap/carried", "merged", branch="carried")                          # what a waits_on park would clear on
    f.put("gap/killed", "parked", branch="killed", parked_for="kill-rule", parked_until={"gap": "gap/carried"},
          parked_at=f.now - 3600)
    f.put("gap/flawed", "parked", branch="flawed", parked_for="defect", parked_until={"gap": "gap/carried"},
          parked_at=f.now - 3600, need_met="x")
    assert resumed(f) == []
    s = f.watch()                                                             # one session carries them all
    raised = {(t["trigger"], t["subject"]) for t in s["triggers"]}
    assert raised == {("parked", gid), ("parked", "gap/killed"), ("parked", "gap/flawed")}   # the manager's to look at
    k = Factory(tmp_path / "k")                                               # the kill rule's park says so
    kid = ready(k)
    for _ in range(k.gates["kill_after"]):
        k.run("implement.py", kid)
        k.run("review.py", kid, FACTORY_STANDIN_VERDICT="fix")
    assert k.item(kid)["state"] == "parked" and k.item(kid)["fields"]["parked_for"] == "kill-rule"


def test_a_waiting_park_past_its_hours_raises_a_situation(tmp_path):
    f = pipe(tmp_path, manager="park_wait_hours = 24\n")
    f.put("gap/carried", "open", branch="carried")
    f.put("gap/fresh", "parked", branch="fresh", parked_for="waits_on", parked_until={"gap": "gap/carried"},
          parked_at=f.now - 23 * 3600)
    f.put("gap/done", "parked", branch="done", parked_for="needs", parked_until={"action": "a", "who": "b"},
          parked_at=f.now - 30 * 3600, resumed_as="gap/done-continued")
    def handled_long_ago(s: dict) -> None:                                    # (answered, and the schedule due again)
        f.fold([{"event": "situation.handled", "item": s["id"], "data": {"prints": s["prints"]}}], None)
        db = f.db()
        db["items"][s["id"]]["fields"]["raised_at"] = f.now - 3 * 3600
        f.record.write_text(json.dumps(db))

    s = f.watch()
    assert s["triggers"] == []                                                # neither: within its hours, or resumed
    handled_long_ago(s)
    f.put("gap/fresh", "parked", branch="fresh", parked_for="waits_on", parked_until={"gap": "gap/carried"},
          parked_at=f.now - 25 * 3600)
    s = f.watch()
    (t,) = s["triggers"]
    assert t["trigger"] == "waiting" and t["subject"] == "gap/fresh" and "not cleared" in t["why"]
    handled_long_ago(s)
    f.put("gap/other", "ready", ago=60, branch="other")                      # (the pipeline changed)
    s = f.watch()
    assert s and "gap/fresh" not in [t["subject"] for t in s["triggers"]]     # raised once for the park


def test_a_split_park_is_resumed_when_its_stopped_sub_gaps_are(tmp_path):
    f = pipe(tmp_path)
    f.put("gap/whole", "parked", branch="whole", parked_for="split", parked_until={"gaps": ["gap/part"]},
          parked_at=f.now - 3600)
    f.put("gap/part", "parked", branch="part", parent=["gap/whole"], parked_for="defect")   # (a kind: not classified)
    assert resumed(f) == []
    f.put("gap/part", "parked", branch="part", parent=["gap/whole"], parked_for="defect",
          resumed_as="gap/part-continued")
    f.put("gap/part-continued", "open", continues="part")
    assert resumed(f) == ["gap.measured", "gap.measured", "gap.split", "gap.resumed"]
    assert f.item("gap/whole")["state"] == "split" and f.item("gap/part")["fields"]["parent"] == []
    assert f.item("gap/part-continued")["fields"]["parent"] == ["gap/whole"]


# ---- park-waits-clear-right (dev/records/park-waits-clear-right.md): a wait clears when its work is on pushed main

def test_a_wait_on_a_continued_gap_clears_when_the_continuation_lands(tmp_path):
    f, gid = parked_by_review(tmp_path, parked_for="waits_on", waits_on="gap/carried")
    pushed = git(f.checkout, "rev-parse", "origin/main")
    f.put("gap/carried", "parked", ago=60, branch="carried", parked_for="defect", resumed_as="gap/carried-continued")
    f.put("gap/carried-continued", "parked", ago=60, continues="carried", parked_for="defect",
          resumed_as="gap/carried-continued-2")                              # continued twice: the original stays parked
    f.put("gap/carried-continued-2", "approved", ago=60, continues="carried")
    assert resumed(f) == []                                                   # its last continuation not merged yet
    f.put("gap/carried-continued-2", "merged", ago=60, continues="carried", main_sha=pushed)
    assert resumed(f) == ["gap.requested", "gap.resumed"]
    assert f.item(gid)["fields"]["cleared"] == "gap/carried merged as gap/carried-continued-2, on origin/main"
    assert f.item("gap/alpha-thing-continued")["fields"]["continues"] == "alpha-thing"


def test_a_local_unpushed_merge_does_not_clear_a_wait(tmp_path):
    f, gid = parked_by_review(tmp_path, parked_for="waits_on", waits_on="gap/carried")
    (f.checkout / "carried.py").write_text("x = 1\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-qm", "the carried gap's merge, not pushed")
    local = git(f.checkout, "rev-parse", "HEAD")
    f.put("gap/other", "parked", ago=60, branch="other", parked_for="waits_on", parked_until={"commits": [local]},
          parked_at=f.now)
    f.put("gap/carried", "merged", ago=60, branch="carried")                  # no merge commit said: not cleared
    assert resumed(f) == []
    f.put("gap/carried", "merged", ago=60, branch="carried", main_sha=local)
    assert resumed(f) == []                                                   # on the checkout's main, not origin's
    git(f.checkout, "push", "-q", "origin", "main")
    assert resumed(f) == ["gap.requested", "gap.resumed"] * 2
    assert f.item(gid)["fields"]["cleared"] == "gap/carried merged, on origin/main"
    assert f.item("gap/other")["fields"]["cleared"] == f"{local[:12]} on origin/main"


def carry_a_merge(tmp: Path, into: str, of: str) -> None:
    """The drop's factory/<into> merges factory/<of>, a branch main lacks: a gap carrying another gap's merge."""
    drop, work = tmp / "live" / "drop.git", tmp / "carry"
    git(tmp, "clone", "-q", str(drop), str(work))
    git(work, "checkout", "-q", "-b", f"factory/{of}", "origin/main")
    (work / f"{of}.py").write_text("x = 1\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", f"{of}'s work")
    git(work, "checkout", "-q", "-b", f"factory/{into}", f"origin/factory/{into}")
    git(work, "merge", "-q", "--no-ff", "--no-edit", f"factory/{of}")
    git(work, "push", "-q", "origin", f"factory/{into}", f"factory/{of}")


def test_existing_parks_are_classified_and_deferred_ones_left_alone(tmp_path):
    f, gid = parked_by_review(tmp_path)
    carry_a_merge(tmp_path, "alpha-thing", "carried")
    old = {k: v for k, v in f.item(gid)["fields"].items() if k not in ("parked_for", "parked_until")}
    f.put(gid, "parked", **old)                                                # a park from before kinds
    f.put("gap/carried", "approved", ago=60, branch="carried")
    long_ago = f.now - 100 * 3600                                               # past parked_within_hours
    for name, by, more in (("killed", "implementor", {}), ("triaged", "queue run 4", {}), ("unclear", "review/x-2", {}),
                           ("deferred", "coordinator", {"deferred": True}), ("cancelled", "x", {"cancelled": True}),
                           ("by-manager", "pipeline-manager", {}), ("by-plan", "plan-review", {}),
                           ("kinded", "implementor", {"parked_for": "defect"}),
                           ("continued", "review/y-1", {"resumed_as": "gap/continued-continued"}),
                           ("was-unknown", "review/z-1", {"parked_for": "unknown", "resumed_as": "gap/was-unknown-2"})):
        f.put(f"gap/{name}", "parked", branch=name, parked_by=by, parked_at=long_ago, **more)
    for done in ("gap/continued-continued", "gap/was-unknown-2"):              # their continuations, landed
        f.put(done, "merged", ago=60, branch=done[4:], continues=done[4:])
    assert resumed(f) == ["gap.measured"] * 4                                  # each once, by a program
    kinds = {i: (f.item(i)["fields"].get("parked_for"), f.item(i)["fields"].get("parked_until"))
             for i in (gid, "gap/killed", "gap/triaged", "gap/unclear")}
    assert kinds == {gid: ("waits_on", {"gap": "gap/carried"}), "gap/killed": ("kill-rule", None),
                     "gap/triaged": ("kill-rule", None), "gap/unclear": ("unknown", None)}
    alone = ("gap/deferred", "gap/cancelled", "gap/by-manager", "gap/by-plan", "gap/continued")   # (continued: too)
    assert all("parked_for" not in f.item(i)["fields"] and "classified_by" not in f.item(i)["fields"] for i in alone)
    kinded = f.item("gap/kinded")["fields"]
    assert kinded["parked_for"] == "defect" and "classified_by" not in kinded
    assert resumed(f) == []                                                    # classified once; nothing cleared yet
    raised = {(t["trigger"], t["subject"]) for t in f.watch()["triggers"]}
    assert ("parked", "gap/unclear") in raised                                 # unknown: the manager's, whatever its age
    assert not {s for _, s in raised} & {*alone, gid, "gap/killed", "gap/triaged", "gap/kinded", "gap/was-unknown"}
    f.put("gap/carried", "merged", ago=60, branch="carried", main_sha=git(f.checkout, "rev-parse", "origin/main"))
    assert resumed(f) == ["gap.requested", "gap.resumed"]                      # the park that motivated it, resumed
    assert f.item(gid)["fields"]["resumed_as"] == "gap/alpha-thing-continued"


def test_an_unfetchable_continue_raises_a_situation(tmp_path):
    f = pipe(tmp_path)
    gid = continues(f)                                                         # the checkout has no branch warm
    assert f.item(gid)["state"] == "open" and f.item(gid)["fields"]["unfetched"] == "the checkout does not have"
    bad = continues(f, "../warm", "gap/escape")                                # a name the branch rule refuses
    assert f.item(bad)["state"] == "open" and f.item(bad)["fields"]["unfetched"] == "fails the branch rule"
    assert "gap.measured" not in f.run("intake.py")[0]                         # said once, as it changes
    s = f.watch()
    assert ("unfetched", gid) in {(t["trigger"], t["subject"]) for t in s["triggers"]}
    assert "which the checkout does not have" in next(t["why"] for t in s["triggers"] if t["subject"] == gid)
    assert "which fails the branch rule" in next(t["why"] for t in s["triggers"] if t["subject"] == bad)
    f.put("gap/holder", "approved", ago=60, branch="warm")                    # another gap holds the branch first
    f.run("intake.py")
    assert f.item(gid)["state"] == "open" and f.item(gid)["fields"]["unfetched"] is None   # the old cause cleared
    assert ("unfetched", gid) not in {(t["trigger"], t["subject"]) for t in (f.watch() or {}).get("triggers", [])}
    f.put("gap/holder", "merged", ago=60, branch="warm")
    behind_main(f)                                                             # there now, but the fetch fails
    drop = tmp_path / "live" / "drop.git"                                      # (factory/warm/x holds the name)
    git(drop, "update-ref", "refs/heads/factory/warm/x", git(drop, "rev-parse", "main"))
    f.run("intake.py")
    assert f.item(gid)["state"] == "open"
    assert f.item(gid)["fields"]["unfetched"] == "could not be fetched into the drop"
    f.fold([{"event": "situation.handled", "item": s["id"], "data": {"prints": s["prints"]}}], None)
    db = f.db()
    db["items"][s["id"]]["fields"]["raised_at"] = f.now - 3 * 3600             # (the schedule due again)
    f.record.write_text(json.dumps(db))
    s = f.watch()                                                              # a new cause: raised again
    assert "could not be fetched" in next(t["why"] for t in s["triggers"] if t["subject"] == gid)
    git(drop, "update-ref", "-d", "refs/heads/factory/warm/x")
    f.run("intake.py")
    assert f.item(gid)["state"] == "ready" and f.item(gid)["fields"]["unfetched"] is None


# ---- the implementor's small test set ([suites] build, scripts/affected_tests.py)

def affected(tmp: Path, change: dict[str, str | None], base: str = "main") -> subprocess.CompletedProcess:
    """scripts/affected_tests.py on a branch of a fixture repository that makes ``change`` (a path's new text, or None
    to delete it), the command it runs being `echo given`: what it would hand pytest, printed."""
    repo = tmp / "repo"
    start = {"ergostat/foo.py": "x = 1\n", "ergostat/sub/baz.py": "y = 1\n", "ergostat/lone.py": "z = 1\n",
             "tests/test_foo.py": "", "tests/test_bar.py": "", "tests/test_baz.py": "", "tests/test_gone.py": "",
             "docs/a.md": "a\n"}
    for rel, text in start.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    git(repo, "checkout", "-qb", "factory/x")
    for rel, text in change.items():
        if text is None:
            (repo / rel).unlink()
        else:
            (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}   # (git sees only the fixture, never /work)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "affected_tests.py"), "--base", base, "--", "echo",
                           "given", "--deselect", "tests/test_q.py::t"], cwd=repo, capture_output=True, text=True,
                          timeout=60, env=env)


def test_a_branch_changing_a_module_and_its_test_runs_only_those(tmp_path):
    r = affected(tmp_path, {"ergostat/foo.py": "x = 2\n", "tests/test_bar.py": "# more\n", "ergostat/lone.py": "z = 2\n",
                            "ergostat/sub/baz.py": "y = 2\n", "tests/test_gone.py": None})
    assert r.returncode == 0, r.stderr                         # (lone.py has no test; test_gone.py is deleted: neither
    given = r.stdout.splitlines()[-1]                          # is named, and the rest are still selected)
    assert given == "given --deselect tests/test_q.py::t tests/test_bar.py tests/test_baz.py tests/test_foo.py"


def test_a_non_ascii_test_file_is_selected(tmp_path):
    r = affected(tmp_path, {"tests/test_é.py": "# new\n"})    # (git's quoted "tests/test_\303\251.py" is no file)
    assert r.returncode == 0 and r.stdout.splitlines()[-1] == "given --deselect tests/test_q.py::t tests/test_é.py"


def test_a_docs_only_branch_runs_collection_only(tmp_path):
    r = affected(tmp_path, {"docs/a.md": "b\n"})
    assert r.returncode == 0 and r.stdout.splitlines()[-1] == "given --deselect tests/test_q.py::t --collect-only"


def test_an_unreadable_diff_runs_the_full_suite(tmp_path):
    r = affected(tmp_path, {"ergostat/foo.py": "x = 2\n"}, base="no-such-ref")
    assert r.returncode == 0 and r.stdout.splitlines()[-1] == "given --deselect tests/test_q.py::t"   # as given: all
    assert "cannot read the diff" in r.stderr


def with_build(f: Factory, build: str) -> None:
    f.config.write_text(f.config.read_text().replace("[suites]\n", f'[suites]\nbuild = "{build}"\n'))


def test_build_unset_runs_the_full_unit_suite_in_the_implementors_step(tmp_path):
    for case, build in (("unset", None), ("empty", "")):
        (tmp_path / case).mkdir()
        f = Factory(tmp_path / case, unit=str(suite_sh(tmp_path / case, "false")))
        if build is not None:
            with_build(f, build)
        gid = ready(f)
        assert f.run("implement.py", gid)[0] == ["gap.started", "gap.built"]
        fast = f.item(gid)["fields"]["suites_fast"]
        assert fast["unit"]["rc"] == 0 and "build" not in fast and len(runs(tmp_path / case)) == 1, case


def test_build_set_is_the_implementors_step_with_its_quarantine_and_triage(tmp_path):
    (tmp_path / "q").mkdir()
    (tmp_path / "f").mkdir()
    f = quarantined(tmp_path / "q", "PASSED x\n")             # unit.sh fails T unless T is deselected (main's list)
    with_build(f, str(tmp_path / "q" / "unit.sh"))
    f.config.write_text(f.config.read_text().replace(f'unit = "{tmp_path / "q" / "unit.sh"}"', 'unit = "false"'))
    gid = ready(f)
    assert f.run("implement.py", gid)[0][-1] == "gap.built"   # the full unit (`false`) never ran
    assert f.item(gid)["fields"]["suites_fast"]["build"]["rc"] == 0
    assert f"--deselect {T}" in (tmp_path / "q" / "runs.log").read_text()       # quarantined: deselected here too

    sh = suite_sh(tmp_path, f"[ ! -e {tmp_path}/once ] && touch {tmp_path}/once")    # a flake: fails its first run
    f = Factory(tmp_path / "f", unit="false", alone=str(sh))
    with_build(f, str(sh))
    gid = ready(f)
    assert f.run("implement.py", gid)[0] == ["gap.started", "gap.built"]       # run alone, then retried
    assert f.flakes_said() == ["flake.seen"]
    assert f.item(gid)["fields"]["flakes"] == [T] and len(runs(tmp_path)) == 3


def test_the_merge_queue_runs_the_full_suites_with_build_set(tmp_path):
    unit = tmp_path / "unit.sh"
    unit.write_text(f'#!/bin/sh\necho "unit $PWD" >> {tmp_path}/runs.log\necho "1 passed"\n')
    unit.chmod(0o755)
    f = Factory(tmp_path, unit=str(unit))
    with_build(f, "true")                                     # (the implementor's step: never the unit suite)
    gid = ready(f)
    f.run("implement.py", gid)
    assert f.item(gid)["fields"]["suites_fast"]["build"]["rc"] == 0 and not runs(tmp_path)
    f.run("review.py", gid)
    assert f.run("queue.py", gid)[0][:2] == ["gap.queued", "gap.merged"]
    assert [r for r in runs(tmp_path) if r.startswith("unit ")]                 # the full unit suite, in the queue
    queue = f.item(gid)["fields"]["suites_queue"]
    assert {"unit", "browser", "demo"} <= set(queue) and "build" not in queue


def test_the_shipped_build_setting_runs_the_small_set():
    import tomllib
    s = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    assert "scripts/affected_tests.py -- " in s["build"] and s["build"].endswith(s["unit"].split(" -- ", 1)[1])


# ---- pool-full-keeps-its-rank (docs/roadmap/overnight/pool-full-keeps-its-rank.md): given back for a full pool, a gap
# is put off under a minute, so it still holds its rank when room appears; the gates keep the give-backs from spinning

def pool_full_nack(f: Factory, program: str, block: str) -> dict:
    """What ``program`` prints when its pool is full (a pool of 1, and gap/second the later of two leases ``block``
    holds): its nack, as the engine reads it (``nack_of``)."""
    from ergostat.spec.engine import nack_of
    lease = lambda t: {"lease": {"block": block, "holder": f"run-{t}", "taken": t}}  # noqa: E731
    f.fold([{"event": "gap.requested", "item": "gap/first", "data": lease(1)},
            {"event": "gap.requested", "item": "gap/second", "data": {**lease(2), "branch": "second"}}], None)
    said, lines = f.run(program, "gap/second")
    (raw,) = [x["nack"] for x in lines if "nack" in x]
    assert said == [] and "pool is full" in raw["why"], (said, raw)
    return nack_of(raw)


class Slots:
    """The real engine on the factory's model and its real dispatch (``tick``: the gate, the pool, ``ready`` and the
    rank order), on a clock the test moves; each run is played: given back as ``program`` gives it back while
    ``full()``, else the gap moved on (``done``), as a finished run moves it."""

    def __init__(self, f: Factory, monkeypatch, block: str, program: str, done: str):
        from types import SimpleNamespace

        from ergostat.leases import dispatch
        self.nack = pool_full_nack(f, program, block)
        self.e, _ = instance_engine(f)
        self.p, self.block, self.done = self.e.p, block, done
        self.gate_name = f"{'implement' if block == 'implementor' else 'review'}-when"
        self.t0, self.at = time.time(), 0.0
        monkeypatch.setattr(dispatch, "time", SimpleNamespace(time=lambda: self.t0 + self.at, monotonic=time.monotonic))
        add = self.p.events.add                          # (the record on the same clock: a lease's put-off is from it)
        self.p.events.add = lambda type_, *a, **k: add(type_, *a, **{"at": self.t0 + self.at, **k})
        self.e.dispatch.pool_now = lambda b: 1 if b.name == block else 0          # (only this block takes, one at once)
        self.e.run_block = self.run_block
        # (no pass of the engine's own: a run's end pokes it, and with no loop that runs a whole pass of real sensors in
        # the run's thread, which outlived the tick under load and set the gate from the machine's real readings over
        # the test's; the test is the pass here, setting the gate at each tick)
        self.e.poke = lambda *blocks, now=True: None
        self.full = lambda: False
        self.gate = 1.0
        self.taken: list[tuple[float, str, str]] = []                          # (when, the gap, how its run ended)

    def run_block(self, b, why, *, item, run_id, outcome, **_):
        if self.full():
            outcome["nack"] = dict(self.nack)
            self.taken.append((self.at, item, "given back"))
        else:
            self.p.events.add(self.done, item=item, source=self.block, causedby=run_id)
            self.taken.append((self.at, item, "ran"))
        return []

    def gap(self, gid: str, event: str, **data) -> None:
        self.p.events.add(event, item=gid, source="test", data=data)

    def tick(self, at: float) -> None:
        self.at = at
        self.e.signals[f"block.{self.gate_name}"] = self.gate                  # (the gate's output, as a pass sets it)
        self.e.dispatch.tick()
        deadline = time.monotonic() + 20
        while (self.e.dispatch.going_items() or self.e.running) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not self.e.dispatch.going_items(), "a played run did not end"

    def gate_of(self, **given) -> float:
        """The gate's own expression (implement-when, review-when) on these inputs."""
        from ergostat.spec.blocks import compile_expr, eval_expr
        b = self.e.spec.blocks[self.gate_name]
        base = dict(ready=1, fixes=1, open=1, waiting=1, over=0, busy=0, pool=1, room=1, full=0, held=0) | given
        return float(eval_expr(compile_expr(b.params["expr"]), {k: base[k] for k in b.inputs}))

    def lease_of(self, gid: str) -> dict:
        from ergostat.spec import items as its
        return its.one(self.p.events, self.e.spec, gid).fields["lease"]

    def close(self) -> None:
        self.e.close()


@pytest.mark.parametrize("block, program, at, done", [("implementor", "implement.py", "gap.defined", "gap.built"),
                                                       ("reviewer", "review.py", "gap.built", "gap.approved")])
def test_a_pool_full_give_back_waits_under_a_minute(tmp_path, monkeypatch, block, program, at, done):
    s = Slots(Factory(tmp_path), monkeypatch, block, program, done)
    try:
        assert s.nack["count"] is False and 0 < s.nack["after"] <= 45          # as the program said it
        s.gap("gap/one", at, rank=1)
        s.full = lambda: True
        s.tick(0)
        lease = s.lease_of("gap/one")
        (h,) = lease["history"]
        assert (h["how"], h["counted"]) == ("nack", False) and lease["attempts"] == 0   # not counted as an attempt
        assert 0 < lease["not_before"] - h["ended"] <= 45                       # put off, under a minute
        s.full = lambda: False
        s.tick(10)                                                              # (10 s on: still put off)
        assert [g for _, g, _ in s.taken] == ["gap/one"]
        s.tick(46)                                                              # past 45 s: taken again, and it runs
        assert [(g, how) for _, g, how in s.taken] == [("gap/one", "given back"), ("gap/one", "ran")]
    finally:
        s.close()


def test_the_highest_ranked_gap_takes_the_next_free_slot(tmp_path, monkeypatch):
    """As seen on 2026-11-21: the gaps ranked 1 and 2 waiting in fix, unranked ones ready. The gate is open on a
    reading that still shows room, so the first taken (rank 1) finds the pool full and is given back; the next reading
    shuts the gate (the machine full) for a minute; then room. The next to run is rank 1, then 2, then the unranked."""
    s = Slots(Factory(tmp_path), monkeypatch, "implementor", "implement.py", "gap.built")
    try:
        for gid, rank in (("gap/u1", None), ("gap/r2", 2), ("gap/u2", None), ("gap/r1", 1)):
            s.gap(gid, "gap.defined", **({"rank": rank} if rank else {}))
        for gid in ("gap/r1", "gap/r2"):
            s.gap(gid, "gap.sent-back")
        s.full = lambda: s.at < 60
        assert s.gate_of() == 1.0 and s.gate_of(full=1) == 0.0 and s.gate_of(room=0) == 0.0
        s.tick(0)                                                               # open on the last reading: given back
        s.gate = s.gate_of(full=1)                                              # the next reading: no session fits
        for t in range(5, 60, 5):
            s.tick(t)
        s.gate = s.gate_of()                                                    # a minute on: room for one
        for t in range(60, 100, 5):
            s.tick(t)
        assert s.taken[0] == (0, "gap/r1", "given back") and all(t >= 60 for t, _, _ in s.taken[1:])
        ran = [g for _, g, how in s.taken if how == "ran"]
        assert ran[:2] == ["gap/r1", "gap/r2"] and set(ran[2:]) == {"gap/u1", "gap/u2"}   # (the unranked: either first)
        assert s.lease_of("gap/r1")["attempts"] == 0
    finally:
        s.close()


def test_a_full_machine_does_not_release_and_retake_in_a_loop(tmp_path, monkeypatch):
    """Twelve minutes of a full machine, looked at every two seconds: with the gate shut (implement-when, no session
    fits) nothing is leased; even with the gate open while the pool stays full (the worst case: the gate's reading and
    the run's disagree throughout), a gap is taken again at most once each put-off, not at each look."""
    s = Slots(Factory(tmp_path), monkeypatch, "implementor", "implement.py", "gap.built")
    try:
        s.gap("gap/r1", "gap.defined", rank=1)
        s.full = lambda: True
        s.gate = s.gate_of(full=1)
        for t in range(0, 720, 2):
            s.tick(t)
        assert s.taken == []                                                    # shut: nothing leased at all
        s.gate = s.gate_of()
        for t in range(720, 1440, 2):
            s.tick(t)
        assert 0 < len(s.taken) <= 720 / 45 + 1 and all(how == "given back" for _, _, how in s.taken), s.taken
        apart = [b - a for (a, _, _), (b, _, _) in zip(s.taken, s.taken[1:], strict=False)]
        assert apart and min(apart) >= 45                                       # never sooner than its put-off
        assert s.lease_of("gap/r1")["attempts"] == 0                            # none of them counted
    finally:
        s.close()


# ---- stacked gaps (merge-pipeline-stacked-gap-builds-on-its-base): built on their approved dependencies' heads

def base_gap(f: Factory, name: str, files: dict[str, str], rank: int, state: str = "approved") -> str:
    """A dependency's reviewed branch in the drop (factory/<name>: main and one commit of ``files``), its item in
    ``state`` with that commit as its reviewed head; (the commit)."""
    drop = f.tmp / "live" / "drop.git"
    if not (drop / "HEAD").exists():
        subprocess.run(["git", "init", "-q", "--bare", str(drop)], check=True)
    git(f.checkout, "checkout", "-q", "-b", name, "main")
    for p, text in files.items():
        (f.checkout / p).parent.mkdir(parents=True, exist_ok=True)
        (f.checkout / p).write_text(text)
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", f"{name}'s work")
    sha = git(f.checkout, "rev-parse", "HEAD")
    git(f.checkout, "push", "-q", str(drop), f"{name}:refs/heads/factory/{name}")
    git(f.checkout, "checkout", "-q", "main")
    db = f.db()
    db["items"][f"gap/{name}"] = {"id": f"gap/{name}", "kind": "gap", "state": state,
                                  "fields": {"branch": name, "rank": rank, "reviewed_head": sha}}
    f.record.write_text(json.dumps(db))
    return sha


def stacked(f: Factory, *deps: str) -> str:
    """gap/alpha-thing at ready, depending on ``deps``."""
    gid = ready(f)
    db = f.db()
    db["items"][gid]["fields"]["depends_on"] = sorted(deps)
    f.record.write_text(json.dumps(db))
    return gid


def holds(repo: Path, sha: str, head: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, head]).returncode == 0


def test_a_stacked_gap_starts_from_its_bases_reviewed_head(tmp_path):
    f = Factory(tmp_path)
    sha = base_gap(f, "beta-base", {"base.py": "print('base')\n"}, rank=1)
    gid = stacked(f, "gap/beta-base")
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    drop, gap = tmp_path / "live" / "drop.git", f.item(gid)
    main, head = git(drop, "rev-parse", "main"), gap["fields"]["head"]
    on = [x["data"]["stacked_on"] for x in lines if x.get("event") in ("gap.started", "gap.built")]
    assert on == [[{"gap": "gap/beta-base", "sha": sha}]] * 2 and gap["fields"]["stacked_on"] == on[0]
    stack = git(drop, "rev-parse", "refs/stack/factory/alpha-thing")
    assert git(drop, "log", "-1", "--format=%P", stack).split() == [main, sha]       # main, then the base, --no-ff
    line = git(drop, "log", "--first-parent", "--reverse", "--format=%P|%s", "main..factory/alpha-thing").splitlines()
    assert [x.split("|")[1] for x in line[:2]] == ["alpha-thing: the definition of done",
                                                    f"Merge main and its bases gap/beta-base ({stack[:12]}) into the branch"]
    assert line[1].split("|")[0].split()[1] == stack                                # the definition first, then the stack
    assert holds(drop, sha, head) and holds(drop, main, head)
    assert git(drop, "show", f"{head}:base.py") == "print('base')"
    assert gap["fields"]["built_main"] == main
    said, _ = f.run("implement.py", gid)                                            # a round more: the same stack, so
    assert said == ["gap.started", "gap.built"]                                     # no second merge of it
    assert git(drop, "rev-parse", "refs/stack/factory/alpha-thing") == stack
    assert git(drop, "log", "--format=%s", "factory/alpha-thing").count("Merge main and its bases") == 1
    git(f.checkout, "checkout", "-q", "beta-base")                                  # the base moves past its review
    git(f.checkout, "commit", "-q", "--allow-empty", "-m", "a fix round")
    git(f.checkout, "push", "-q", str(drop), "beta-base:refs/heads/factory/beta-base")
    git(f.checkout, "checkout", "-q", "main")
    said, lines = f.run("implement.py", gid)
    assert said == []                                                               # waits for the merge-forward
    (n,) = [x["nack"] for x in lines if "nack" in x]
    assert n["count"] is False and n["after"] == "30m" and "merge-forward" in n["why"] and "gap/beta-base" in n["why"]


def test_a_stacked_gaps_net_lines_count_only_its_own_commits(tmp_path):
    f = Factory(tmp_path)
    base_gap(f, "beta-base", {"base.py": "".join(f"x{i} = {i}\n" for i in range(50)), "tmp_base.txt": "x\n"}, rank=1)
    gid = stacked(f, "gap/beta-base")
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="own.py")
    assert said == ["gap.started", "gap.built"]                     # (tmp_base.txt is the base's, not a stray of its own)
    assert f.item(gid)["fields"]["net_lines"] == 2                  # standin/work.txt and own.py: not the base's 51


def test_two_bases_that_conflict_give_the_gap_back_uncounted(tmp_path):
    f = Factory(tmp_path)
    first = base_gap(f, "beta-base", {"beta.py": "b\n"}, rank=2)
    second = base_gap(f, "gamma-base", {"gamma.py": "g\n"}, rank=1)
    gid = stacked(f, "gap/beta-base", "gap/gamma-base")
    said, _ = f.run("implement.py", gid)                             # two that merge cleanly: both, in rank order
    assert said == ["gap.started", "gap.built"]
    drop = tmp_path / "live" / "drop.git"
    assert [b["gap"] for b in f.item(gid)["fields"]["stacked_on"]] == ["gap/gamma-base", "gap/beta-base"]
    stack = git(drop, "rev-parse", "refs/stack/factory/alpha-thing")
    assert git(drop, "log", "-1", "--format=%P", stack).split()[1] == first
    assert git(drop, "log", "-1", "--format=%P", f"{stack}^1").split()[1] == second
    head = f.item(gid)["fields"]["head"]
    assert holds(drop, first, head) and holds(drop, second, head)

    g = Factory(tmp_path / "two")                                    # two that conflict with each other
    base_gap(g, "beta-base", {"app.py": "print('beta')\n", "beta.py": "b\n"}, rank=1)
    base_gap(g, "delta-base", {"app.py": "print('delta')\n"}, rank=2)
    gid = stacked(g, "gap/beta-base", "gap/delta-base")
    said, lines = g.run("implement.py", gid)
    assert said == ["gap.started"]
    (n,) = [x["nack"] for x in lines if "nack" in x]
    assert n["count"] is False and n["after"] == "30m" and n["why"].endswith("conflict with each other (or with main "
                                                                             f"{git(g.checkout, 'rev-parse', 'main')[:12]}) in: app.py")
    drop = g.tmp / "live" / "drop.git"
    assert git(drop, "for-each-ref", "refs/heads/factory/alpha-thing", "refs/stack/") == ""   # nothing published
    assert g.item(gid)["fields"].get("build_failures") is None and g.item(gid)["state"] == "building"


def test_an_unstacked_gap_builds_as_before(tmp_path):
    for deps in ((), ("gap/beta-base",), ("gap/beta-base", "gap/gamma-base")):    # none; merged; one not reviewed
        (tmp_path / str(len(deps))).mkdir()
        f = Factory(tmp_path / str(len(deps)))
        base_gap(f, "beta-base", {"base.py": "print('base')\n"}, rank=1, state="merged")
        base_gap(f, "gamma-base", {"gamma.py": "g\n"}, rank=2, state="building")
        gid = stacked(f, *deps)
        said, lines = f.run("implement.py", gid)
        assert said == ["gap.started", "gap.built"]
        assert not [x for x in lines if "stacked_on" in (x.get("data") or {})]       # no stack said
        drop = f.tmp / "live" / "drop.git"
        assert git(drop, "for-each-ref", "refs/stack/") == ""
        first = git(drop, "log", "--reverse", "--format=%s", "main..factory/alpha-thing").splitlines()
        assert first == ["alpha-thing: the definition of done", "alpha-thing: work the session left uncommitted"]
        gap = f.item(gid)
        assert gap["fields"]["net_lines"] == 1 and gap["fields"]["built_main"] == git(drop, "rev-parse", "main")
        assert not holds(drop, git(drop, "rev-parse", "factory/beta-base"), gap["fields"]["head"])


def test_finish_refuses_a_head_that_no_longer_holds_a_base(tmp_path):
    f = Factory(tmp_path)
    sha = base_gap(f, "beta-base", {"base.py": "print('base')\n"}, rank=1)
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, agents; cfg = fac.config(); "
            "home, work = agents.clone(cfg, 'alpha-thing', 'implementor'); "
            "main = fac.git(work, 'rev-parse', 'origin/main'); "
            "fac.git(work, '-c', 'user.name=t', '-c', 'user.email=t@x', 'merge', '-q', '--no-ff', '-m', 'm', sys.argv[2]); "
            "was = agents.publish(cfg, work, 'alpha-thing'); "
            "fac.git(work, 'reset', '-q', '--hard', main); (work / 'own.txt').write_text('x')\n"   # (the base dropped)
            "try:\n    out = agents.finish(cfg, home, 'alpha-thing', main, main, main, sys.argv[2], was=was)\n"
            "except RuntimeError as e:\n    out = str(e)\n"
            "print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), sha], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    said = json.loads(r.stdout.strip().splitlines()[-1])
    assert said.startswith(f"the branch no longer holds main or a base, merged in before it {sha[:12]}: refused"), said


# ---- merge-pipeline-stacks-turned-on: a gap starts on approved dependencies and is reviewed against its base

def test_the_factory_takes_a_gap_whose_dependency_is_approved(tmp_path):
    """The engine's take (Dispatcher.ready's filter, then takes: unblocked) on a copy of the factory's model: a ready
    gap whose only dependency is approved, queued or push-pending is taken; one in fix or parked, or the same
    approved one on the model as it was (finish-to-start), is not."""
    from types import SimpleNamespace

    from ergostat import model as mdl
    from ergostat.leases.ready import unblocked
    from ergostat.spec import items as its
    from ergostat.store import Project
    fac = module("fac")

    def taken(where: Path, dep_at: str) -> list[str]:
        (where / "state").mkdir()
        p = Project(mdl.load(where), directory=where / "state")
        spec, ev, t = p.model.spec, p.events, time.time() - 3600
        assert spec.items["gap"].relations["depends_on"].starts_at in ([], None, list(fac.STACKABLE))
        steps = {"approved": ("gap.started", "gap.built", "gap.review-started", "gap.approved")}
        steps["queued"] = (*steps["approved"], "gap.queued")
        steps["push-pending"] = (*steps["queued"], "gap.push-pending")
        steps["fix"] = (*steps["approved"][:3], "gap.sent-back")
        steps["parked"] = (*steps["fix"], "gap.parked")
        for k, e in enumerate(("gap.found", "gap.defined", *steps[dep_at])):
            ev.add(e, item="gap/base", data={"rank": 1} if k == 0 else {}, at=t + k)
        ev.add("gap.found", item="gap/top", data={"rank": 2, "depends_on": ["gap/base"]}, at=t + 20)
        ev.add("gap.defined", item="gap/top", at=t + 21)
        b = spec.blocks["implementor"]
        got = [i for i in its.project(ev, spec, "gap") if i.state in b.takes.at and its.matches(i, b.takes.where)]
        assert {i.id: i.state for i in its.project(ev, spec, "gap")}["gap/base"] == dep_at
        return [i.id for i in unblocked(SimpleNamespace(p=p, spec=spec), b, got)]
    for dep_at in fac.STACKABLE:
        assert taken(factory_copy(tmp_path / dep_at), dep_at) == ["gap/top"], dep_at
    for dep_at in ("fix", "parked"):
        assert "gap/top" not in taken(factory_copy(tmp_path / dep_at), dep_at), dep_at  # (a base in fix: taken itself)
    assert taken(factory_copy(tmp_path / "before", without_stacking), "approved") == []    # as main had it


def test_a_stacked_gap_is_reviewed_against_its_base(tmp_path):
    """The reviewer of a stacked gap gets only its own diff (not its base's 50 lines), the same net lines as its
    implementor counted, within a budget its base alone would break, and a brief naming its bases; a head that does
    not hold its base is a blocking finding, judged against main (lesson-3)."""
    def built(f: Factory) -> str:
        base_gap(f, "beta-base", {"base.py": "".join(f"x{i} = {i}\n" for i in range(50))}, rank=1)
        gid = stacked(f, "gap/beta-base")
        (f.tmp / "instance" / "run" / "defs" / "alpha-thing.md").write_text(
            "# alpha thing\n\n## Definition of done\n\nIt works.\n\n## Size budget\n\n10 net lines.\n")
        said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="own.py")
        assert said == ["gap.started", "gap.built"] and f.item(gid)["fields"]["net_lines"] == 2
        assert f.item(gid)["fields"]["budget"] == 10
        return gid

    f = Factory(tmp_path / "one")
    gid = built(f)
    said, _ = f.run("review.py", gid)
    assert said[-1] == "gap.approved", f.item(gid)["fields"].get("findings")
    (rid,) = [i for i in f.db()["items"] if i.startswith("review/alpha-thing-")]
    assert f.item(rid)["fields"]["net_lines"] == f.item(gid)["fields"]["net_lines"] == 2
    text = (f.tmp / "instance" / "run" / "briefs" / "alpha-thing-reviewer-1.md").read_text()
    diff = text.split("```diff", 1)[1].split("```", 1)[0]
    assert "own.py" in diff and "base.py" not in diff and "x49 = 49" not in diff
    assert "# This gap is stacked" in text and "gap/beta-base at " in text
    sb = f.item(gid)["fields"]["stack_base"]                       # its base, said with its head (implement.py)
    assert sb == git(f.tmp / "live" / "drop.git", "rev-parse", "refs/stack/factory/alpha-thing")
    assert f"`git diff {sb}...HEAD`" in text

    g = Factory(tmp_path / "two")                                 # its base gone from the drop: never judged on main
    gid = built(g)                                                # as if it were the gap's own
    git(g.tmp / "live" / "drop.git", "update-ref", "-d", "refs/stack/factory/alpha-thing")
    g.fold([{"event": "gap.measured", "item": gid, "data": {"stack_base": ""}}], None)    # (built before stack_base)
    said, _ = g.run("review.py", gid)
    assert said[-1] == "gap.sent-back"
    found = g.item(gid)["fields"]["findings"]
    assert any(x.startswith("gate 1: stacked on gap/beta-base at ") and "judged against main" in x for x in found)
    (rid,) = [i for i in g.db()["items"] if i.startswith("review/alpha-thing-")]
    assert g.item(rid)["fields"]["net_lines"] == 52                # the worst case: its base's 50 lines counted too
    assert any(x.startswith("size: 52 net lines") for x in found), (g.item(rid)["fields"], found)

    h = Factory(tmp_path / "three")                 # its base approved again and merged forward while it is built: the
    gid = built(h)                                  # base it is judged against moves with it, so its diff stays its own
    drop, before = h.tmp / "live" / "drop.git", git(h.tmp / "live" / "drop.git", "rev-parse", "refs/stack/factory/alpha-thing")
    new = commit_on(h, "beta-base", {"base2.py": "".join(f"y{i} = {i}\n" for i in range(30))})
    taken = h.record.read_text()                    # the record as a reviewer that took the gap just before read it
    said, _ = h.run("stack.py")
    assert said == ["gap.measured"] and h.item(gid)["state"] == "built" and holds(drop, new, h.item(gid)["fields"]["head"])
    ref = git(drop, "rev-parse", "refs/stack/factory/alpha-thing")
    assert ref != before and parents(h, ref) == [before, new]              # its base made again, by the base's head
    assert parents(h, h.item(gid)["fields"]["head"])[1] == ref             # and merged into it in the base's place
    assert h.item(gid)["fields"]["stack_base"] == ref                      # said with the new head, in one event
    moved = h.record.read_text()
    h.record.write_text(taken)                      # lesson-1: the review taken in the window (its head and fields read
    said, _ = h.run("review.py", gid)               # before the merge forward, its clone made after the ref moved)
    assert said[-1] == "gap.approved", h.item(gid)["fields"].get("findings")
    assert [h.item(i)["fields"]["net_lines"] for i in h.db()["items"] if i.startswith("review/alpha-thing-")] == [2]
    h.record.write_text(moved)
    said, _ = h.run("review.py", gid)
    assert said[-1] == "gap.approved", h.item(gid)["fields"].get("findings")
    (rid,) = [i for i in h.db()["items"] if i.startswith("review/alpha-thing-")]
    assert h.item(rid)["fields"]["net_lines"] == h.item(gid)["fields"]["net_lines"] == 2
    text = (h.tmp / "instance" / "run" / "briefs" / "alpha-thing-reviewer-1.md").read_text()
    diff = text.split("```diff", 1)[1].split("```", 1)[0]
    assert "own.py" in diff and "base2.py" not in diff and "y29 = 29" not in diff

    k = Factory(tmp_path / "four")                  # merged forward but its base not made again with it: fails closed
    gid = built(k)
    stale = git(k.tmp / "live" / "drop.git", "rev-parse", "refs/stack/factory/alpha-thing")
    commit_on(k, "beta-base", {"base2.py": "".join(f"y{i} = {i}\n" for i in range(30))})
    said, _ = k.run("stack.py")
    k.fold([{"event": "gap.measured", "item": gid, "data": {"stack_base": stale}}], None)
    said, _ = k.run("review.py", gid)
    assert said[-1] == "gap.sent-back"
    found = k.item(gid)["fields"]["findings"]
    assert any("does not hold them all: judged against main" in x for x in found), found


# ---- merge-pipeline-stacks-merged-forward: a moved base merged forward into the gaps stacked on it (dev/bin/stack.py)

def commit_on(f: Factory, name: str, files: dict[str, str], approve: bool = True) -> str:
    """A commit of ``files`` on factory/<name> in the drop; ``approve``: its gap approved again at it. (the commit)"""
    drop = f.tmp / "live" / "drop.git"
    git(f.checkout, "fetch", "-q", str(drop), f"refs/heads/factory/{name}")
    git(f.checkout, "checkout", "-q", "--detach", "FETCH_HEAD")
    for p, text in files.items():
        (f.checkout / p).write_text(text)
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", f"{name} again")
    sha = git(f.checkout, "rev-parse", "HEAD")
    git(f.checkout, "push", "-q", str(drop), f"HEAD:refs/heads/factory/{name}")
    git(f.checkout, "checkout", "-q", "main")
    if approve:
        f.fold([{"event": "gap.approved", "item": f"gap/{name}", "data": {"reviewed_head": sha}}], None)
    return sha


def tip(f: Factory, name: str) -> str:
    return git(f.tmp / "live" / "drop.git", "rev-parse", f"refs/heads/factory/{name}")


def parents(f: Factory, sha: str) -> list[str]:
    return git(f.tmp / "live" / "drop.git", "log", "-1", "--format=%P", sha).split()


def stale_stacks(f: Factory) -> str:
    """The sensor stale-stacks' reading (`stack.py stale`)."""
    r = subprocess.run([sys.executable, str(BIN / "stack.py"), "stale"], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_moved_base_is_merged_forward_into_an_approved_descendant(tmp_path):
    f = Factory(tmp_path)
    old = stacked_gaps(f, {"a": 1, "b": 2})
    assert stale_stacks(f) == "0"
    new = commit_on(f, "a", {"a2.txt": "a's fix round"})                  # a re-approved at a new head
    assert stale_stacks(f) == "1"
    said, _ = f.run("stack.py")
    assert said == ["gap.measured"]
    b, head = f.item("gap/b"), tip(f, "b")
    assert parents(f, head) == [old["b"], new]                            # a merge of a's new head, --no-ff
    assert git(tmp_path / "live" / "drop.git", "log", "-1", "--format=%s", head) == \
        f"Merge gap/a ({new[:12]}) forward into the branch"
    assert b["state"] == "approved" and b["fields"]["reviewed_head"] == head
    assert b["fields"]["reviewed_by"] == "stack-forward" and b["fields"]["stacked_on"] == [{"gap": "gap/a", "sha": new}]
    assert stale_stacks(f) == "0"
    said, _ = f.run("stack.py")                                           # done: a pass more does nothing
    assert said == [] and tip(f, "b") == head
    f.fold([{"event": "gap.merged", "item": "gap/a", "data": {}}], None)  # a lands: nothing to do but stacked_on
    said, _ = f.run("stack.py")
    assert said == ["gap.measured"] and tip(f, "b") == head and f.item("gap/b")["fields"]["stacked_on"] == []
    assert f.item("gap/b")["fields"]["reviewed_head"] == head


def test_a_conflicting_merge_forward_sends_the_descendant_to_fix(tmp_path):
    f = Factory(tmp_path)
    stacked_gaps(f, {"a": 1, "b": 2})
    mine = commit_on(f, "b", {"a.txt": "b's own a"}, approve=False)
    f.fold([{"event": "gap.measured", "item": "gap/b", "data": {"reviewed_head": mine}}], None)
    new = commit_on(f, "a", {"a.txt": "a's fix round"})
    said, _ = f.run("stack.py")
    assert said == ["gap.sent-back"]
    b = f.item("gap/b")["fields"]
    assert f.item("gap/b")["state"] == "fix" and b["stack_conflict"] == ["a.txt"] and b["sent_back_by"] == "stack-forward"
    assert "failed_gates" not in b and "gap/a" in b["findings"][0] and "a.txt" in b["findings"][0]   # uncounted
    assert tip(f, "b") == mine and not holds(tmp_path / "live" / "drop.git", new, mine)              # aborted
    assert stale_stacks(f) == "0"                     # in fix: its next round merges the bases itself (implement.py)
    said, _ = f.run("stack.py")                       # a pass more: no clone, no second sent-back
    assert said == [] and f.item("gap/b")["fields"] == b
    review = ["a blocking finding of its review"]     # a fix gap with a review's findings, its base moved again
    f.fold([{"event": "gap.measured", "item": "gap/b", "data": {"findings": review}}], None)
    commit_on(f, "a", {"a3.txt": "a's next fix round"})
    said, _ = f.run("stack.py")
    assert said == [] and f.item("gap/b")["fields"]["findings"] == review and tip(f, "b") == mine


def test_a_leased_descendant_is_not_merged_forward(tmp_path):
    for state in ("leased", "building", "in-review"):
        (tmp_path / state).mkdir()
        f = Factory(tmp_path / state)
        old = stacked_gaps(f, {"a": 1, "b": 2})
        db = f.db()
        db["items"]["gap/b"]["state"] = state
        f.record.write_text(json.dumps(db))
        before = f.item("gap/b")
        commit_on(f, "a", {"a2.txt": "a's fix round"})
        said, _ = f.run("stack.py")
        assert said == [] and tip(f, "b") == old["b"] and f.item("gap/b") == before, state
        assert stale_stacks(f) == "0"


def test_a_stack_of_three_moves_forward_in_one_pass(tmp_path):
    f = Factory(tmp_path)
    old = stacked_gaps(f, {"c": 1, "b": 2, "a": 3})                       # c on b on a... named so the ids sort top-down
    new = commit_on(f, "c", {"c2.txt": "c's fix round"})                  # the bottom moves
    said, _ = f.run("stack.py")
    assert said == ["gap.measured"] * 2                                   # b, then a, in the one pass
    b, a = tip(f, "b"), tip(f, "a")
    assert parents(f, b) == [old["b"], new] and parents(f, a) == [old["a"], b]
    assert f.item("gap/a")["fields"]["stacked_on"] == [{"gap": "gap/b", "sha": b}]
    assert f.item("gap/a")["fields"]["reviewed_head"] == a and f.item("gap/a")["state"] == "approved"
    assert holds(tmp_path / "live" / "drop.git", new, a)


def test_a_branch_moved_during_the_merge_forward_is_refused_and_theirs_kept(tmp_path):
    f = Factory(tmp_path)
    stacked_gaps(f, {"a": 1, "b": 2})
    commit_on(f, "a", {"a2.txt": "a's fix round"})
    theirs = commit_on(f, "b", {"theirs.txt": "x"}, approve=False)        # made now, pushed during the merge
    git(tmp_path / "live" / "drop.git", "update-ref", "refs/heads/factory/b", f"{theirs}^")
    code = (f"import sys, subprocess; sys.path[:0] = [{str(BIN)!r}]; import agents, stack\n"
            "clone = agents.clone\n"
            "def moved(*a, **k):\n    got = clone(*a, **k)\n"
            f"    subprocess.run(['git', '-C', {str(tmp_path / 'live' / 'drop.git')!r}, 'update-ref', "
            f"'refs/heads/factory/b', {theirs!r}], check=True)\n    return got\n"
            "agents.clone = moved\nsys.exit(stack.main([]))")
    r = subprocess.run([sys.executable, "-c", code], cwd=f.model, env=f.env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    assert '"event"' not in r.stdout and "moved from" in r.stderr and "refused (theirs kept)" in r.stderr
    assert tip(f, "b") == theirs and "reviewed_by" not in f.item("gap/b")["fields"]


# ---- the suites' -r: pytest's -r replaces its default fE, so a -r without f and E prints no FAILED or ERROR line
#      and fac.failed_tests finds none (lesson-3: a red run that names no test is never excused, bisected whole, and
#      triaged as naming no test)

READ_BY_FAILED_TESTS = ("unit", "host", "build", "browser", "rerun", "alone")


def pytest_args(cmd: str) -> list[str]:
    """The arguments after ``-m pytest`` in a suite's command (none found: the test fails, never passes empty)."""
    words = shlex.split(cmd)
    at = [i for i in range(len(words) - 1) if words[i:i + 2] == ["-m", "pytest"]]
    assert len(at) == 1, f"no single `-m pytest` in {cmd!r}"
    return words[at[0] + 2:]


def report_chars(args: list[str]) -> str | None:
    """The last -r's characters (pytest keeps the last), or None where there is no -r (pytest's default fE)."""
    got = None
    for i, w in enumerate(args):
        if w == "-r" or w.startswith("--report-chars"):
            got = args[i + 1] if "=" not in w else w.split("=", 1)[1]
        elif w.startswith("-r"):
            got = w[2:]
    return got


def prints_failed_lines(args: list[str]) -> bool:
    chars = report_chars(args)
    return chars is None or (("f" in chars and "E" in chars) or bool({"a", "A"} & set(chars))) and "N" not in chars


def test_every_suite_fac_reads_prints_failed_lines():
    suites = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    for name in READ_BY_FAILED_TESTS:
        assert suites.get(name), f"[suites] {name} is gone: name the suites fac.failed_tests reads again"
        assert prints_failed_lines(pytest_args(suites[name])), f"[suites] {name}: its -r drops f or E"
    for bad in (["-q", "-rs"], ["-rfs"], ["-rEs"], ["-r", "s"], ["--report-chars=sE"], ["-rfEs", "-rs"], ["-rfEN"]):
        assert not prints_failed_lines(bad), bad                               # (the check itself can fail)
    for good in ([], ["-q"], ["-rfEs"], ["-rs", "-rfE"], ["-ra"], ["-r", "fE"]):
        assert prints_failed_lines(good), good


def test_a_failing_browser_test_is_named(tmp_path):
    """The browser suite's own pytest options, on a failing, an erroring, a skipped and a passing test: the failures
    are named by fac.failed_tests, and queue.suites's skip count and nowhere() read the same skip as under the old -rs."""
    sys.path.insert(0, str(BIN))
    try:
        spec = importlib.util.spec_from_file_location("factory_queue", BIN / "queue.py")   # (not the stdlib's queue)
        q = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(q)
    finally:
        sys.path.remove(str(BIN))
    suites = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    (tmp_path / "test_b.py").write_text(textwrap.dedent("""\
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("no page")

        def test_ok():
            pass

        def test_bad():
            assert False

        def test_broken(broken):
            pass

        def test_skipped():
            pytest.skip("needs a thing")
    """))
    env = {k: v for k, v in os.environ.items() if k not in QUEUE_ENV}

    def run(args: list[str]) -> str:
        args = [a for a in args if not a.endswith(".py")]                       # the browser files: ours instead
        r = subprocess.run([sys.executable, "-m", "pytest", *args, "-p", "no:cacheprovider", "test_b.py"],
                           cwd=tmp_path, capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == 1, r.stdout + r.stderr
        return r.stdout

    fac = module("fac")
    now = run(pytest_args(suites["browser"]))
    assert fac.failed_tests(now) == ["test_b.py::test_bad", "test_b.py::test_broken"]
    assert now.index("\nPASSED test_b.py::") < now.index("\nFAILED test_b.py::")  # (p first: the FAILED lines stay
    #                                                                              in the 2000-char tail a failure keeps)
    assert fac.outcomes(now, ["test_b.py::test_ok", "test_b.py::test_skipped", "test_b.py::test_bad"]) == {
        "test_b.py::test_ok": "pass", "test_b.py::test_skipped": "unknown", "test_b.py::test_bad": "fail"}
    assert report_chars(pytest_args(suites["unit"])) == report_chars(pytest_args(suites["browser"])) == "pfEs"
    old = run([("-rs" if a.startswith("-r") else a) for a in pytest_args(suites["browser"])])
    assert fac.failed_tests(old) == []                                          # what -rs gave: no test named
    unit = tmp_path / "unit.txt"
    unit.write_text(now)
    for text in (now, old):
        assert len(re.findall(r"^SKIPPED", text, re.M)) == 1                   # queue.suites's browser skip count
        assert q.nowhere(text, unit) == ["test_b.py:17: needs a thing"]


# ---- merge-pipeline-gaps-md-regenerated-on-land: the entries in the records, GAPS.md written from them as a batch lands

ENTRY_ONLY = "## Entry\n\nsection: Modelling\n\n- **Warm** (open): its entry, split from GAPS.md.\n"
GAPS_RECORDS = {                                                   # GAPS as gapsdoc split writes it into dev/records
    f"{NEW}/GAPS-head.md": "# Known gaps\n\n## Modelling\n\n@entry alpha-thing\n@entry beta\n@entry delta\n\n"
                           "## Done recently\n\n@entry gamma\n",
    f"{NEW}/alpha-thing.md": "## Entry\n\nsection: Modelling\n\n- **Alpha thing** (open; the first gap): what it "
                             "lacks.\n  More of it.\n",
    f"{NEW}/beta.md": "## Entry\n\nsection: Modelling\n\n- **Beta** (done, abc1234): landed.\n",
    f"{NEW}/delta.md": "## Entry\n\nsection: Modelling\n\n- **Delta** (parked on `delta`, *Where it stopped*): stopped.\n",
    f"{NEW}/gamma.md": "## Entry\n\nsection: Done recently\n\n- **Gamma**: done.\n",
}
EPSILON = "- **Epsilon** (open): no record has it."
CARRIED = GAPS.replace("stopped.\n", f"stopped.\n  *Left*: the carried line.\n{EPSILON}\n")


def test_a_definition_in_the_old_folder_resolves_past_a_record_that_is_only_its_entry(tmp_path):
    fac = module("fac")
    for d, text in ((OLD, f"# warm\n\n{DONE}"), (NEW, ENTRY_ONLY)):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "warm.md").write_text(text)
    plain = {"id": "gap/warm", "fields": {"branch": "warm"}}
    ref = {"id": "gap/warm-again", "fields": {"continues": "warm", "definition": f"factory/warm:{NEW}/warm.md"}}
    for g in (plain, ref):                                         # a continued gap's REF to the new path too
        assert fac.definition_file(g, tmp_path) == f"{OLD}/warm.md"
    (tmp_path / NEW / "warm.md").write_text(f"# warm\n\n{DONE}\n{ENTRY_ONLY}")    # a definition and its entry: its own
    assert [fac.definition_file(g, tmp_path) for g in (plain, ref)] == [f"{NEW}/warm.md"] * 2
    g = Factory(tmp_path / "f")                                    # end to end: intake, the build, its review
    behind_main(g)                                                 # (its definition in the old folder, on its branch)
    commit_files(g, {f"{NEW}/warm.md": ENTRY_ONLY})                # the split's record of it, on main
    gid = continues(g)
    assert g.item(gid)["fields"]["definition"] == f"factory/warm:{OLD}/warm.md"   # never the Entry
    built_and_approved(g, gid, "review/warm-1")
    head = g.item(gid)["fields"]["head"]
    assert git(tmp_path / "f" / "live" / "drop.git", "show", f"{head}:{NEW}/warm.md") == ENTRY_ONLY.strip()  # no 2nd


def test_a_record_that_is_only_its_entry_is_given_the_definition_before_it(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, {f"{NEW}/alpha-thing.md": ENTRY_ONLY})
    gid = ready(f)                                                 # (its definition in run/defs/, not the Entry)
    built_and_approved(f, gid, "review/alpha-thing-1")
    drop = tmp_path / "live" / "drop.git"
    assert git(drop, "log", "--reverse", "--format=%s", "main..factory/alpha-thing").splitlines()[0] == \
        "alpha-thing: the definition of done"
    text = git(drop, "show", f"{f.item(gid)['fields']['head']}:{NEW}/alpha-thing.md")
    assert text.startswith("# alpha thing\n\n## Definition of done") and text.endswith(ENTRY_ONLY.strip())


def test_a_branch_that_edits_gaps_md_is_refused_uncounted_before_the_suites(tmp_path):
    log = tmp_path / "suite-runs.log"
    f = Factory(tmp_path, unit=f"echo ran >> {log}")
    gid = ready(f)
    for _ in (1, 2):                                               # (suite_fix_rounds 0: no next round in a run)
        said, lines = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="docs/GAPS.md")
        assert said == ["gap.started", "gap.measured"] and not f.item(gid)["fields"].get("build_failures")
        nack = next(x["nack"] for x in lines if "nack" in x)
        assert nack["count"] is False and "docs/GAPS.md" in nack["why"]
    assert not log.exists()                                        # the suites never ran
    brief = (tmp_path / "instance" / "run" / "briefs" / "alpha-thing-implementor-2.md").read_text()
    assert "# docs/GAPS.md edited" in brief and f"`{NEW}/alpha-thing.md`" in brief   # the next try is told where


def test_a_stacked_gap_whose_base_edited_gaps_md_is_judged_by_its_own_commits(tmp_path):
    f = Factory(tmp_path)
    base_gap(f, "beta-base", {"docs/GAPS.md": "# Gaps\n\nthe base's entry, approved before the cutover\n"}, rank=1)
    gid = stacked(f, "gap/beta-base")
    said, _ = f.run("implement.py", gid)                           # the base's GAPS.md edit is not the gap's own
    assert said == ["gap.started", "gap.built"]
    g = Factory(tmp_path / "own")                                  # its own commits edit it too: refused, against the stack
    base_gap(g, "beta-base", {"docs/GAPS.md": "# Gaps\n\nthe base's entry\n"}, rank=1)
    gid = stacked(g, "gap/beta-base")
    said, lines = g.run("implement.py", gid, FACTORY_STANDIN_WRITES="docs/GAPS.md")
    assert said == ["gap.started", "gap.measured"] and next(x["nack"] for x in lines if "nack" in x)["count"] is False
    stack = git(g.tmp / "live" / "drop.git", "rev-parse", "refs/stack/factory/alpha-thing")
    brief = (g.tmp / "instance" / "run" / "briefs" / "alpha-thing-implementor-1.md").read_text()
    assert "# docs/GAPS.md edited" not in brief                    # (the first try's brief: the base's edit is no reason)
    said, _ = g.run("implement.py", gid, FACTORY_STANDIN_WRITES="docs/GAPS.md")
    brief = (g.tmp / "instance" / "run" / "briefs" / "alpha-thing-implementor-2.md").read_text()
    assert "as main and its bases gap/beta-base has it" in brief and f"git checkout {stack[:12]} --" in brief


def approved_editing(f: Factory, name: str, files: dict[str, str]) -> str:
    """A gap approved on a branch of its own in the drop that writes ``files`` (docs/GAPS.md, as one approved before
    the entries moved could): its reviewed commit."""
    drop = f.tmp / "live" / "drop.git"
    if not drop.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(drop)], check=True)
    commit_files(f, files, branch=name)
    sha = git(f.checkout, "rev-parse", name)
    git(f.checkout, "push", "-q", str(drop), f"{name}:refs/heads/factory/{name}")
    git(f.checkout, "branch", "-q", "-D", name)
    f.fold([{"event": "gap.approved", "item": f"gap/{name}", "data": {
        "branch": name, "reviewed_head": sha, "approved_at": time.time() - 3600, "rank": 0}}], None)
    return sha


def landed_head(f: Factory, name: str) -> tuple[str, dict]:
    """The queue run on gap/NAME, which lands: (main's head, the run as said on the gap), main_sha and the push both
    that head."""
    said, _ = f.run("queue.py", f"gap/{name}")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    head, it = git(f.checkout, "rev-parse", "main"), f.item(f"gap/{name}")["fields"]
    assert it["main_sha"] == head and f"sha={head}" in f.db()["acts"][0]
    assert git(f.checkout, "status", "--porcelain") == ""
    return head, it["queue_runs"][0]


def test_an_approved_branch_that_edited_gaps_md_lands_with_its_text_in_a_record(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, GAPS_RECORDS)
    approved_editing(f, "carried", {"docs/GAPS.md": CARRIED, "carried.txt": "x\n"})
    head, run = landed_head(f, "carried")
    assert git(f.checkout, "log", "-2", "--format=%s", "main").splitlines() == [
        "docs/GAPS.md from the records", "Merge branch 'factory/carried'"]
    assert "  *Left*: the carried line." in git(f.checkout, "show", f"{head}:{NEW}/delta.md")
    assert git(f.checkout, "show", f"{head}:{NEW}/epsilon.md") == f"## Entry\n\nsection: Modelling\n\n{EPSILON}"
    assert git(f.checkout, "show", f"{head}:docs/GAPS.md") == CARRIED.strip()   # the records' render, pushed
    assert "@entry delta\n@entry epsilon\n" in git(f.checkout, "show", f"{head}:{NEW}/GAPS-head.md")
    assert "gaps_md_unplaced" not in run and [c.split(":")[0] for c in run["gaps_md_carried"]] == [
        "delta", "epsilon", "GAPS-head.md"]


def test_an_approved_branch_that_deleted_a_gaps_md_entry_lands_with_it_gone_from_the_records(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, GAPS_RECORDS)
    gone = GAPS.replace("- **Delta** (parked on `delta`, *Where it stopped*): stopped.\n", "")
    assert gone != GAPS
    approved_editing(f, "deleted", {"docs/GAPS.md": gone})
    head, run = landed_head(f, "deleted")
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "docs/GAPS.md from the records"
    assert git(f.checkout, "show", f"{head}:docs/GAPS.md") == gone.strip()        # never drawn again on the push
    assert f"{NEW}/delta.md" not in git(f.checkout, "ls-tree", "-r", "--name-only", head, f"{NEW}/").splitlines()
    assert "@entry delta" not in git(f.checkout, "show", f"{head}:{NEW}/GAPS-head.md")
    assert run["gaps_md_carried"][0] == "delta: its Entry removed, as the batch removed it from GAPS.md"


def test_an_approved_branch_that_adds_an_entry_only_in_its_record_lands_with_it_drawn(tmp_path):
    # (the normal path after this gap: the entry in dev/records/<branch>.md, GAPS.md left alone)
    f = Factory(tmp_path)
    commit_files(f, GAPS_RECORDS)
    zeta = "# zeta: its definition\n\nDone means.\n\n## Entry\n\nsection: Modelling\n\n- **Zeta** (open): only its record.\n"
    approved_editing(f, "zeta", {f"{NEW}/zeta.md": zeta})
    head, run = landed_head(f, "zeta")
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "docs/GAPS.md from the records"
    assert git(f.checkout, "show", f"{head}:docs/GAPS.md") == GAPS.replace(
        "stopped.\n", "stopped.\n- **Zeta** (open): only its record.\n").strip()     # drawn on the pushed head
    assert git(f.checkout, "show", f"{head}:{NEW}/zeta.md") == zeta.strip()            # its Entry kept
    assert "gaps_md_carried" not in run and "gaps_md" not in run


def test_a_record_only_entry_whose_render_failed_is_drawn_by_the_next_landing(tmp_path):
    f = Factory(tmp_path)
    commit_files(f, GAPS_RECORDS)
    zeta = "# zeta: its definition\n\nDone means.\n\n## Entry\n\nsection: Modelling\n\n- **Zeta** (open): only its record.\n"
    approved_editing(f, "zeta", {f"{NEW}/zeta.md": zeta, f"{NEW}/bad.md": "## Entry\n\nsection: Modelling\n"})
    head, run = landed_head(f, "zeta")                                  # the render fails: GAPS.md as it was
    assert "bad: malformed Entry" in run["gaps_md"] and "Zeta" not in git(f.checkout, "show", f"{head}:docs/GAPS.md")
    approved_editing(f, "mend", {f"{NEW}/bad.md": "# bad: its definition\n"})
    set_action(f, "ran")                                                # the first push runs
    said, _ = f.run("queue.py", "gap/mend")
    assert "gap.merged" in said and "gap.push-asked" in said
    head, it = git(f.checkout, "rev-parse", "main"), f.item("gap/mend")["fields"]
    assert it["main_sha"] == head and any(f"sha={head}" in a for a in f.db()["acts"])  # the head pushed
    run = it["queue_runs"][0]
    assert git(f.checkout, "show", f"{head}:docs/GAPS.md") == GAPS.replace(
        "stopped.\n", "stopped.\n- **Zeta** (open): only its record.\n").strip()     # drawn on the pushed head
    assert git(f.checkout, "show", f"{head}:{NEW}/zeta.md") == zeta.strip()            # its Entry kept
    assert "gaps_md" not in run and not any("zeta" in c for c in run.get("gaps_md_carried", []))


def test_no_record_change_makes_no_commit_and_a_malformed_record_lands_without_one(tmp_path):
    for name, files in (("plain", {"plain.txt": "x\n"}),
                        ("bad", {"docs/GAPS.md": CARRIED, f"{NEW}/bad.md": "## Entry\n\nsection: Modelling\n"})):
        f = Factory(tmp_path / name)
        commit_files(f, GAPS_RECORDS)
        approved_editing(f, name, files)
        head, run = landed_head(f, name)
        assert git(f.checkout, "log", "-1", "--format=%s", "main") == f"Merge branch 'factory/{name}'"
        assert git(f.checkout, "show", f"{head}:docs/GAPS.md") == files.get("docs/GAPS.md", GAPS).strip()  # as merged
        if name == "plain":
            assert not [k for k in run if k.startswith("gaps_md")]
        else:
            assert "bad: malformed Entry" in run["gaps_md"] and "gaps_md_carried" not in run


# ---- the daily browser run on main (dev/records/merge-pipeline-browser-daily-on-main.md, dev/bin/browserday.py)

# the browser suite played: the commit it runs on, then red's text (exit 1), a skip, or a pass; with `hold`, it waits
# for `go` (its pid in browser-pid)
DAILY_BROWSER = r"""T=$(dirname "$0")
git rev-parse HEAD >> "$T/browser-heads"
if [ -e "$T/hold" ]; then
  echo $$ > "$T/browser-pid"; touch "$T/in-browser"; i=0
  while [ ! -e "$T/go" ] && [ $i -lt 600 ]; do sleep 0.1; i=$((i+1)); done
fi
if [ -e "$T/skip" ]; then echo "SKIPPED [1] tests/test_page_polling.py:9: no 3 free ports in range"; fi
if [ -e "$T/red" ]; then cat "$T/red"; exit 1; fi
echo "3 passed in 0.10s"
"""
# one test alone (`rerun`): PASSED when listed in `flaky`, or in `once` on its first rerun; else FAILED
DAILY_RERUN = r"""T=$(dirname "$0")
echo "$1 $2" >> "$T/reruns"
c="$T/count-$(printf %s "$1" | tr '/:.' '___')"; n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 )); echo $n > "$c"
if grep -qxF "$1" "$T/flaky" 2>/dev/null || { [ $n = 1 ] && grep -qxF "$1" "$T/once" 2>/dev/null; }; then
  echo "PASSED $1"; echo "1 passed in 0.01s"; exit 0
fi
echo "FAILED $1 - boom"; exit 1
"""
DAILY_A, DAILY_B, DAILY_C = (f"tests/test_items_page.py::test_{x}" for x in "abc")


def browser_daily(tmp_path) -> Factory:
    f = Factory(tmp_path)
    (tmp_path / "browser.sh").write_text(DAILY_BROWSER)
    (tmp_path / "rerun.sh").write_text(DAILY_RERUN)
    text = f.config.read_text().replace('\nbrowser = "true"', f'\nbrowser = "sh {tmp_path / "browser.sh"}"')
    f.config.write_text(text.replace('rerun = "echo again {tests}"', f'rerun = "sh {tmp_path / "rerun.sh"} {{tests}}"'))
    return f


def merged_on_origin(tmp_path, name: str) -> str:
    """A branch merged (--no-ff) into origin's main from a clone of its own, so the checkout's main never has it."""
    other = tmp_path / "other"
    if not other.exists():
        subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(other)], check=True, capture_output=True)
    git(other, "checkout", "-q", "-b", name)
    (other / f"{name}.txt").write_text(name)
    git(other, "add", f"{name}.txt")
    git(other, "commit", "-q", "-m", f"side {name}")
    git(other, "checkout", "-q", "main")
    git(other, "merge", "-q", "--no-ff", name, "-m", f"Merge {name}")
    git(other, "push", "-q", "origin", "main")
    return git(other, "rev-parse", "HEAD")


def daily_record(f: Factory) -> dict:
    return json.loads((f.model / "run" / "browser-daily.json").read_text())


def daily_green(f: Factory) -> tuple[int, str]:
    """The sensor browser-main-green: (exit, what it printed)."""
    r = subprocess.run([sys.executable, str(BIN / "browserday.py"), "green"], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout.strip()


def daily_clean(f: Factory) -> bool:
    """Its worktree gone, by name, and the checkout's the only one left."""
    return not (f.tmp / "wt" / "browser-daily").exists() and len(git(f.checkout, "worktree", "list").splitlines()) == 1


def daily_gone(pid: int, wait: float = 10) -> bool:
    """The suite's shell killed: gone, or a zombie (dead, its parent killed too, not yet reaped by init). Its own
    parent (`sh -c`) is the one suite() waits for, so a killed grandchild can still be listed for a moment under load."""
    until = time.time() + wait
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        try:                                                           # (no /proc, or unreadable: still alive)
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            state = "?"
        if state == "Z":
            return True
        if time.time() > until:
            return False
        time.sleep(0.05)


def test_browser_daily_green_records_main(tmp_path):
    f = browser_daily(tmp_path)
    assert daily_green(f)[0] == 1                                       # never run: no reading, not green (lesson-3)
    sha = merged_on_origin(tmp_path, "one")                            # on origin's main, not the checkout's
    said, _ = f.run("browserday.py")
    assert said == [] and f.flakes_said() == []
    rec = daily_record(f)
    assert rec["sha"] == sha and rec["green"] is True and rec["last_green"]["sha"] == sha and rec["at"] > 0
    assert (tmp_path / "browser-heads").read_text().split() == [sha]   # run on origin/main itself
    assert git(f.checkout, "log", "-1", "--format=%s", "main") == "start" and daily_clean(f)
    assert daily_green(f) == (0, "1")
    said, _ = f.run("browserday.py")                                   # the next day, nothing merged: it runs again
    assert said == [] and (tmp_path / "browser-heads").read_text().split() == [sha, sha] and daily_clean(f)
    (f.model / "run" / "browser-daily.json").write_text("{not json")
    assert daily_green(f)[0] == 1                                       # unreadable: no reading
    (f.model / "run" / "browser-daily.json").write_text("{}")
    assert daily_green(f)[0] == 1


def test_browser_daily_goal_closes_in_landing():
    """check's missing-feedback says nothing of goal.browser-main-green: the daily run reads it (read, not commanded)
    and sets its auxiliary, so the loop closes inside landing with no link across a boundary; it keeps its own
    schedule (nothing commands it), and no other block reads the goal."""
    spec, problems = read(ROOT / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.level == "error"] == []
    assert [f"{p.code}@{p.about}" for p in problems if p.about in ("goal.browser-main-green", "block.browser-daily",
                                                                    "auxiliary.browser-main-green")] == []
    assert spec.loop("browser-main-green").actuators == ["browser-daily"]
    readers = [b.name for b in spec.blocks.values() if any(r.kind == "goal" and r.name == "browser-main-green"
                                                            for r in b.reads())]
    assert readers == ["browser-daily"]
    assert spec.blocks["browser-daily"].every and not spec.commanders_of("browser-daily")


def test_browser_daily_flake_is_recorded_not_raised(tmp_path):
    f = browser_daily(tmp_path)
    (tmp_path / "red").write_text(f"FAILED {DAILY_A} - boom\n1 failed, 2 passed in 1.00s\n")
    (tmp_path / "flaky").write_text(DAILY_A + "\n")
    said, _ = f.run("browserday.py")
    assert said == [] and f.flakes_said() == ["flake.seen"]            # no intervention
    assert (tmp_path / "reruns").read_text().splitlines() == [f"{DAILY_A} -rA"] * 2   # alone, twice, -rA
    fl = f.item("flake/" + re.sub(r"[^a-z0-9]+", "-", DAILY_A.lower()).strip("-"))["fields"]
    assert fl["suite"] == "browser" and fl["run"].startswith("browser-daily-") and fl["log"].endswith(".txt")
    assert not [i for i in f.db()["items"] if i.startswith("intervention/")]
    rec = daily_record(f)
    assert rec["green"] is True and rec["flakes"] == [DAILY_A] and daily_clean(f)


def test_browser_daily_failure_names_tests_and_suspects(tmp_path):
    f = browser_daily(tmp_path)
    green_sha = merged_on_origin(tmp_path, "one")
    f.run("browserday.py")                                             # the last green
    two, sha = merged_on_origin(tmp_path, "two"), merged_on_origin(tmp_path, "three")
    (tmp_path / "red").write_text("".join(f"FAILED {t} - boom\n" for t in (DAILY_A, DAILY_B, DAILY_C)) +
                                  "3 failed in 1.00s\n")
    (tmp_path / "flaky").write_text(DAILY_C + "\n")                    # passes alone both times: a flake
    (tmp_path / "once").write_text(DAILY_B + "\n")                     # passes alone once, then fails: real
    said, _ = f.run("browserday.py")
    assert said == ["intervention.recorded"] and f.flakes_said() == ["flake.seen"]
    (iid,) = [i for i in f.db()["items"] if i.startswith("intervention/")]
    iv = f.item(iid)["fields"]
    assert iv["class"] == "queue" and iv["main"] == sha and iv["tests"] == [DAILY_A, DAILY_B]
    assert iv["suspects"] == [f"{sha} Merge three", f"{two} Merge two"] and iv["suspects_since"] == green_sha
    assert iv["suspects_more"] is False and iv["flakes"] == [DAILY_C] and sha[:12] in iv["reason"]
    reruns = (tmp_path / "reruns").read_text().splitlines()
    assert [r.split()[0] for r in reruns].count(DAILY_A) == 1 and [r.split()[0] for r in reruns].count(DAILY_B) == 2
    rec = daily_record(f)
    assert rec["green"] is False and rec["last_green"]["sha"] == green_sha and rec["intervention"] == iid
    assert daily_green(f) == (0, "0") and daily_clean(f)
    for crash, skip, said_why in ((f"FAILED {DAILY_C} - boom\nINTERNALERROR> the suite crashed\n", False,
                                   "crashed (INTERNALERROR>)"),                 # (a crash naming a flaky test)
                                  ("Traceback: the suite crashed\n", False, "exited 1"), (None, True, "skipped 1"),
                                  (f"FAILED {DAILY_C} - boom\n", True, "skipped 1")):    # (a flake beside a skip)
        (tmp_path / "red").unlink(missing_ok=True)                     # named no test: an intervention with the tail
        if crash:
            (tmp_path / "red").write_text(crash)
        if skip:
            (tmp_path / "skip").touch()
        before = {i for i in f.db()["items"] if i.startswith("intervention/")}
        flaked, reran = f.flakes_said(), (tmp_path / "reruns").read_text()
        said, _ = f.run("browserday.py")
        assert said == ["intervention.recorded"]
        if "INTERNALERROR" in (crash or ""):                           # its FAILED line not read: not rerun, no flake
            assert f.flakes_said() == flaked and (tmp_path / "reruns").read_text() == reran
        (new,) = {i for i in f.db()["items"] if i.startswith("intervention/")} - before
        iv = f.item(new)["fields"]
        assert iv["tests"] == [] and said_why in iv["reason"] and "named no failing test" in iv["reason"]
        assert ("SKIPPED" if skip else "the suite crashed") in iv["tail"] and iv["suspects_since"] == green_sha
        assert daily_green(f) == (0, "0") and daily_clean(f)


def test_browser_daily_holds_the_queue_lock(tmp_path):
    f = browser_daily(tmp_path)
    (tmp_path / "hold").touch()
    lock = tmp_path / "queue.lock"

    def started() -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, str(BIN / "browserday.py")], cwd=f.model, env=f.env, text=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        until = time.time() + 60
        while not (tmp_path / "in-browser").exists() and p.poll() is None and time.time() < until:
            time.sleep(0.05)
        assert (tmp_path / "in-browser").exists(), p.stderr.read() if p.poll() is not None else "not started"
        return p
    p = started()
    with open(lock, "a") as lk, pytest.raises(BlockingIOError):        # held while its suite runs
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    got = []

    def batch():                                                       # a batch waiting for the lock
        with open(lock, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            got.append((f.model / "run" / "browser-daily.json").exists())
            fcntl.flock(lk, fcntl.LOCK_UN)
    t = threading.Thread(target=batch, daemon=True)
    t.start()
    time.sleep(0.5)
    assert got == []                                                   # still waiting
    (tmp_path / "go").touch()
    assert p.wait(timeout=60) == 0, p.stderr.read()
    t.join(timeout=60)
    assert got == [True] and daily_clean(f)                            # it started after the daily run had ended
    (tmp_path / "go").unlink()
    (tmp_path / "in-browser").unlink()
    (f.model / "run" / "browser-daily.json").unlink()
    p = started()                                                      # stopped part way (a lease lost, a timeout)
    pid = int((tmp_path / "browser-pid").read_text())
    p.send_signal(signal.SIGTERM)
    assert p.wait(timeout=60) == 143
    assert daily_gone(pid)                                             # its suite went with it
    assert daily_clean(f) and not (f.model / "run" / "browser-daily.json").exists()
    with open(lock, "a") as lk:                                        # and so did the lock
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
