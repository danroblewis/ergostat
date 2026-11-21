"""ergostat on ergostat: the factory's model at the repository's root, and its programs (dev/bin/), run against a
fixture repository with the free stand-ins (no AI, no push). docs/roadmap/overnight/factory.md names these tests.

The engine is played by a small harness: each program is run as ergostat runs a block that takes an item (its input on
standard input, the item's environment, $ERGOSTAT_CMD), and the event lines it prints are folded into the record by
the kinds the root model declares, so a line the model does not know fails here."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ergostat.spec import read

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"

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
elif args[0] == "lease":
    if "--nack" in args:                                           # (a lease given back, as its run would: drain.py)
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
            streak = 3
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
            demo = "true"
            rerun = "echo again {{tests}}"
            alone = "{alone} {{tests}}"
            """))
        self.fake = tmp / "fake_ergostat.py"
        self.fake.write_text(FAKE)
        self.record = tmp / "record.json"
        self.record.write_text(json.dumps({"items": {}}))
        spec, problems = read(ROOT / "ergostat.yaml")
        assert not [p for p in problems if p.level == "error"]
        self.kinds = spec.items
        self.env = {**os.environ, "FACTORY_CONFIG": str(self.config), "ERGOSTAT_CMD": f"{sys.executable} {self.fake}",
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
            iid = line.get("item") or about
            kind = next(k for k in self.kinds.values() if Path(iid).match(k.id) or iid.startswith(k.id[:-1]))
            assert line["event"] in kind.on or line["event"].endswith((".measured", ".push-asked", ".switch-asked", ".pushed",
                                                                                ".dependencies", ".push-settled", ".groomed")), line
            it = db["items"].setdefault(iid, {"id": iid, "kind": kind.name, "state": kind.states[0], "fields": {}})
            for k, v in (line.get("data") or {}).items():
                rule = "relation" if k in kind.relations else kind.fold.get(k, "replace")
                was = it["fields"].get(k)
                if rule == "relation":                                 # (SPEC 5a: a set of ids, or set/add/remove)
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
            if not line["event"].startswith("session."):          # (each AI session's own item: sessions.py)
                said.append(line["event"])
        self.record.write_text(json.dumps(db))
        return said

    def run(self, program: str, iid: str | None = None, argv: tuple = (), lease: dict | None = None, fails: bool = False,
            **env) -> tuple[list[str], list[dict]]:
        """A run of a block: (the events it said, every JSON line it printed). ``lease``: more of its lease (its
        attempt); ``fails``: it is expected to exit non-zero (a counted attempt)."""
        it = self.item(iid) if iid else None
        given = {"trigger": "item", "item": it,
                 "lease": {"fence": 1, "back": it["state"], **(lease or {})} if it else None}
        r = subprocess.run([sys.executable, str(BIN / program), *argv], input=json.dumps(given), cwd=self.model,
                           capture_output=True, text=True, timeout=120,
                           env={**self.env, **({"ERGOSTAT_ITEM": iid, "ERGOSTAT_LEASE": "1"} if iid else {}), **env})
        assert (r.returncode != 0) == fails, r.stderr
        self.stderr = r.stderr
        lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        return self.fold(lines, iid), lines


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
    assert spec.blocks["merge-queue"].pool == 1
    assert set(spec.items["upgrade"].states) >= {"installed", "switched", "healthy", "reverted"}


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
                     "factory/alpha-thing:docs/roadmap/overnight/alpha-thing.md")
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
    assert said == ["flake.seen", "gap.retried"] and f.item(gid)["state"] == "approved"
    assert f.item("flake/tests-test-x-py-test-y")["fields"]["times"] == 1
    said, _ = f.run("queue.py", gid)
    assert said[:2] == ["gap.queued", "gap.merged"]


def pools_module():
    sys.modules.setdefault("fac", module("fac"))       # (pools.py imports fac from beside it)
    return module("pools")


def gap(n: int, state: str = "approved", fixes: int = 0, at: float = 100.0, **f) -> dict:
    return {"id": f"gap/g{n}", "state": state, "last": at + n,
            "fields": {"approved_at": at + n, "fix_rounds": fixes, **f}}


def test_pools_raise_only_after_the_streak():
    pools = pools_module()
    cfg = {"pools": {"implementor_max": 4, "reviewer_max": 2, "streak": 3}}
    one = {"since": 0, "implementor": 1, "reviewer": 1}
    two_good = pools.outcomes([gap(1), gap(2, fixes=1)], [])
    assert pools.decide(two_good, 0, one, cfg)[0] is None                       # two in a row: not yet
    three = pools.outcomes([gap(1), gap(2, fixes=1), gap(3)], [])
    assert pools.decide(three, 0, one, cfg)[:1] == ("raise",)
    assert pools.decide(three, 102.5, one, cfg)[0] is None                      # only what came since the last change
    broken = pools.outcomes([gap(1), gap(2, state="parked", parked_at=101.5), gap(3), gap(4)], [])
    assert pools.decide(broken, 0, one, cfg)[0] is None                         # a park at 1: the streak starts again
    reverted = pools.outcomes([gap(1), gap(2), gap(3)], [{"state": "reverted", "fields": {"gap": "gap/g2"}}])
    assert pools.decide(reverted, 0, one, cfg)[0] is None                       # a merge reverted is not good
    full = {"since": 0, "implementor": 4, "reviewer": 2}
    assert pools.decide(three, 0, full, cfg)[0] is None                         # the cap


def test_pools_drop_on_a_park_and_keep_the_cap(tmp_path):
    pools = pools_module()
    cfg = {"pools": {"implementor_max": 4, "reviewer_max": 2, "streak": 3}}
    two = {"since": 0, "implementor": 2, "reviewer": 1}
    bad = pools.outcomes([gap(1), gap(2, state="parked", parked_at=101.5)], [])
    assert pools.decide(bad, 0, two, cfg)[0] == "lower"
    assert pools.decide(pools.outcomes([gap(1, fixes=2)], []), 0, two, cfg)[0] == "lower"   # a second fix round
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


T ="tests/test_x.py::test_y"


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
    git(f.checkout, "add", "broken")
    git(f.checkout, "commit", "-q", "-m", "main breaks a test")
    git(f.checkout, "push", "-q", "origin", "main")
    main = git(f.checkout, "rev-parse", "main")
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "flake.main-broken", "intervention.recorded", "gap.measured"]
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
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert not f.item(gid)["fields"].get("waits_on_main") and "flake/tests-test-x-py-test-y" not in f.db()["items"]
    assert [r for r in runs(tmp_path) if "-main-" in r and r.endswith(T)]   # it was run on main, and passed there
    for _ in range(f.gates["build_failures"] - 1):
        said, _ = f.run("implement.py", gid)
    assert said[-1] == "gap.parked"                                         # counted, as before


def test_a_flake_in_the_fast_suites_is_retried(tmp_path):
    sh = suite_sh(tmp_path, f"[ ! -e {tmp_path}/once ] && touch {tmp_path}/once")   # fails its first run only
    f = Factory(tmp_path, unit=str(sh), alone=str(sh))
    gid = ready(f)
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "flake.seen", "gap.built"]
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
    assert gate("") == ["gate 1: docs/roadmap/overnight/warm2.md is not on the branch"]   # (without it)
    (wt / "docs" / "roadmap" / "overnight" / "later.md").write_text("# later\n")  # a definition the branch added
    git(wt, "add", "-A")                                                        # later: its place in history is
    git(wt, "commit", "-q", "-m", "a later file")                               # not checked
    assert gate("docs/roadmap/overnight/later.md") == []
    (wt / "docs" / "roadmap" / "overnight" / "later.md").write_text("# later, changed\n")
    git(wt, "commit", "-qam", "the definition changed")                         # changed after it: still refused
    assert gate("docs/roadmap/overnight/later.md") == [
        "gate 1: docs/roadmap/overnight/later.md was changed after its first commit (other than a 'Where it "
        "stopped' section)"]


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


def approved_gaps(f: Factory, ranks: dict[str, int], bad: str = "", batch: int | None = None) -> dict[str, str]:
    """Gaps approved on branches of their own in the drop (each adds NAME.txt; ``bad`` adds bad.txt too, which fails the
    unit suite), ranked as given; the queue's batch set when ``batch``. {name: its reviewed commit}."""
    drop = f.tmp / "live" / "drop.git"
    if not drop.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(drop)], check=True)
    out = {}
    for name, rank in ranks.items():
        git(f.checkout, "checkout", "-q", "-b", name, "main")
        (f.checkout / f"{name}.txt").write_text(name)
        if name == bad:
            (f.checkout / "bad.txt").write_text("breaks the suite")
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
    # all four red; p, q green; p, q, r red: r. Then s merged again onto p, q and run alone: green.
    assert suite_runs(f) == 4
    r = f.item("gap/r")
    assert r["state"] == "queue-failed" and r["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert merges(f) == ["p", "q", "s"] and not (f.checkout / "bad.txt").exists()
    onto = r["fields"]["pre"]                                                  # what r was merged onto: main with p, q
    assert git(f.checkout, "log", "--first-parent", "--format=%s", "-1", onto) == "Merge branch 'factory/q'"
    assert git(f.checkout, "rev-parse", "main~1") == onto                      # and the rest landed on it
    assert all(f.item(f"gap/{g}")["state"] == "merged" for g in "pqs")
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
    assert {x.get("item") for x in lines if "event" in x} <= {None, "gap/a"}


def test_a_stopped_batch_puts_its_other_gaps_back(tmp_path):
    # the run stopped during its suites: only ever the queue's own process (never whatever else $PPID could be)
    f = Factory(tmp_path, unit="ps -o command= -p $PPID | grep -q dev/bin/queue.py && kill -TERM $PPID; sleep 30")
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    start = git(f.checkout, "rev-parse", "main")
    said, _ = f.run("queue.py", "gap/a", fails=True)
    assert said == ["gap.queued"] and f.item("gap/b")["state"] == "approved"    # b never left approved
    assert git(f.checkout, "rev-parse", "main") == start                       # main as it was
    assert "running" not in json.loads((f.model / "run" / "queue.json").read_text())


def waiting(f: Factory) -> str:
    r = subprocess.run([sys.executable, str(BIN / "queue.py"), "waiting"], cwd=f.model, env=f.env, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_held_push_survives_later_runs(tmp_path):
    # the run's own gap (a) fails and b lands: the push is asked under a's lease, so a must not be taken again (by
    # flake triage, the implementor) before the approval runs the push, or the push is fenced out
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    approved_gaps(f, {"a": 1, "b": 2}, bad="a", batch=2)
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.measured", "gap.push-asked"]   # a's queue-failed kept back
    assert f.item("gap/a")["state"] == "queued" and f.item("gap/b")["state"] == "merged"
    assert [e["event"] for e in json.loads((f.model / "run" / "queue.json").read_text())["pending"]["then"]] == [
        "gap.queue-failed"]
    assert waiting(f) == "1"                                                   # the queue's gate: it takes no gap
    approved_gaps(f, {"c": 3})
    said, lines = f.run("queue.py", "gap/c")                                  # a run attempted all the same
    assert said == ["gap.queued"] and "is held" in next(x["nack"]["why"] for x in lines if "nack" in x)
    assert f.item("gap/a")["state"] == "queued"                                # still nothing takes a
    set_action(f, "ran")                                                       # the approval runs the push
    assert waiting(f) == "0"
    said, _ = settle(f)
    assert said == ["gap.pushed", "gap.queue-failed"] and f.item("gap/a")["state"] == "queue-failed"
    assert f.item("gap/a")["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert "pending" not in json.loads((f.model / "run" / "queue.json").read_text())


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
    assert said == ["gap.queued", "intervention.recorded"] and f.item("gap/a")["state"] == "queued"
    assert "saying gap/a merged" in next(x["nack"]["why"] for x in lines if "nack" in x)
    said, lines = f.run("queue.py", "gap/a")                                   # blocked once, not again each run
    assert said == ["gap.queued"] and "blocked until intervention/queue-" in next(x["nack"]["why"] for x in lines if "nack" in x)


def test_the_queue_runs_unit_and_browser_at_once_and_reports_the_first_failure(tmp_path):
    t = tmp_path / "t"
    f = Factory(tmp_path, unit=f"echo unit-start >> {t}; sleep 1; echo unit-end >> {t}; echo 'FAILED tests/test_u.py::test_u'; exit 1")
    f.config.write_text(f.config.read_text().replace(
        'browser = "true"', f'browser = "echo browser-start >> {t}; sleep 1; echo browser-end >> {t}; exit 1"').replace(
        'demo = "true"', f'demo = "echo demo >> {t}"'))
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    got = t.read_text().split()
    assert sorted(got[:2]) == ["browser-start", "unit-start"] and "demo" not in got    # together; demo not after red
    fields = f.item("gap/a")["fields"]
    assert said[1] == "gap.queue-failed" and fields["failed_suite"] == "unit"           # the first, in order
    assert fields["failed_tests"] == ["tests/test_u.py::test_u"]
    assert fields["suites_queue"]["browser"]["rc"] == 1 and fields["suites_queue"]["unit"]["rc"] == 1
    f.config.write_text(f.config.read_text().replace("exit 1", "exit 0"))
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
    assert said == ["gap.queued"] and nack["count"] is False and "cannot fast-forward" in nack["why"]
    assert git(f.checkout, "rev-parse", "main") == head                         # nothing merged


def test_the_pool_tuner_is_paused_and_never_lowers_the_owners_pools(tmp_path):
    f = Factory(tmp_path)
    (f.model / "run").mkdir(exist_ok=True)
    (f.model / "run" / "pools.json").write_text(json.dumps({"implementor": 3, "reviewer": 2, "since": 0}))
    f.fold([{"event": "gap.parked", "item": "gap/hurt-by-main", "data": {"parked_at": time.time()}}], None)
    r = subprocess.run([sys.executable, str(BIN / "pools.py"), "tune"], cwd=f.model, env=f.env, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr
    got = json.loads((f.model / "run" / "pools.json").read_text())
    assert got["implementor"] == 3 and got["reviewer"] == 2 and "pool.lowered" not in r.stdout
    assert not [a for a in f.db().get("acts", []) if "role=implementor" in a or "role=reviewer" in a]


def test_a_dead_letter_on_main_broken_tests_says_so(monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", sys.modules.get("fac") or module("fac"))
    monkeypatch.setitem(sys.modules, "review", type(sys)("review"))     # (its park is not called here)
    dead = module("dead")
    f = {"suites_fast": {"tests": [T]}, "main_broken_tests": [T], "built_main": "a" * 40}
    assert "fail on main too" in dead.on_main(f) and "aaaaaaaaaaaa" in dead.on_main(f)
    assert dead.on_main({**f, "suites_fast": {"tests": [T, "tests/test_z.py::test_own"]}}) == ""   # one is the gap's
    assert dead.on_main({"suites_fast": {}}) == ""


# ---- switch-drain: an approved switch drains the runs under way, and older switch requests are withdrawn

NOON = time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))              # today 12:00, local (no 04:00 near)


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


def switcher(f: Factory, now: float, **upgrade) -> tuple[list[str], str, list[str]]:
    """One step of the switcher at ``now``: (the events it said, why, the switches it started)."""
    if upgrade:
        with f.config.open("a") as c:
            c.write("[upgrade]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in upgrade.items()))
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, live, drain; cfg = fac.config(); "
            "live.detach = lambda cfg, sha: print(json.dumps({'detached': sha})); "
            "print(json.dumps({'why': drain.step(cfg, float(sys.argv[2]))}))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), repr(now)], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return (f.fold([x for x in lines if "event" in x], None), lines[-1]["why"],
            [x["detached"] for x in lines if "detached" in x])


def test_a_switch_waits_for_the_runs_under_way(tmp_path):
    f = Factory(tmp_path)
    a, b = versions(f, 2)
    uid = asked(f, b, "ran")                                                     # approved
    held(f, "gap/one", "gap/two")
    said, why, started = switcher(f, NOON, quiet_runs=1)
    assert said == ["upgrade.switch-approved"] and "waits" in why and started == []
    flag = f.model / "run" / "drain.json"
    assert not flag.exists() and f.item(uid)["state"] == "approved"
    held(f, "gap/one")                                                           # a quiet moment: one run under way
    said, why, started = switcher(f, NOON + 60)
    assert said == ["upgrade.draining"] and "drains" in why and started == [] and flag.exists()
    gid = ready(f)                                                               # the AI blocks take no new item
    said, lines = f.run("implement.py", gid)
    assert said == [] and lines == [{"nack": {"why": lines[0]["nack"]["why"], "count": False, "after": "5m"}}]
    f.fold([{"event": "gap.built", "item": gid, "data": {}}], None)
    said, lines = f.run("review.py", gid)
    assert said == [] and lines[0]["nack"]["count"] is False
    held(f, "gap/one")
    said, why, started = switcher(f, NOON + 120)
    assert said == [] and started == [] and "1 run(s) under way" in why        # gap/one still runs
    held(f)                                                                      # it finished
    said, why, started = switcher(f, NOON + 180)
    assert said == ["upgrade.drained"] and started == [b] and f.db().get("nacks") is None
    assert f.item(uid)["fields"]["given_back"] == [] and f.item(uid)["state"] == "draining"
    assert switcher(f, NOON + 240)[1:] == (f"switching to {b[:12]}", [])        # started once
    said, why, started = switcher(f, NOON + 180 + 30 * 60)                       # its process never cleared the flag
    assert said == ["upgrade.failed", "intervention.recorded"] and started == []
    assert f.item(uid)["state"] == "failed" and not flag.exists() and "no outcome recorded" in f.item(uid)["fields"]["why"]
    assert switcher(f, NOON + 181 + 30 * 60)[::2] == ([], [])                    # never begun again
    r = subprocess.run([sys.executable, "-c", "import sys, json; sys.path[:0] = [sys.argv[1]]; import drain; "
                        "print(json.dumps(drain.AI))", str(BIN)], cwd=f.model, env=f.env, capture_output=True, text=True)
    spec, _ = read(ROOT / "ergostat.yaml")
    own = {"improver", "modeller", "redesigner"}         # (ergostat's own modelling, the template's: not drained)
    assert set(json.loads(r.stdout)) == {n for n, x in spec.blocks.items() if x.type == "ai"} - own   # every other


def test_a_drain_past_its_bound_gives_the_runs_back_uncounted(tmp_path):
    f = Factory(tmp_path)
    a, b = versions(f, 2)
    uid = asked(f, b, "ran")
    held(f, "gap/long", block="reviewer")
    said, why, _ = switcher(f, NOON, drain_minutes=45)
    assert said == ["upgrade.switch-approved", "upgrade.draining"]
    said, why, started = switcher(f, NOON + 44 * 60)
    assert said == [] and started == [] and "44 of 45 minutes" in why
    said, why, started = switcher(f, NOON + 45 * 60)                             # the bound
    assert said == ["upgrade.drained"] and started == [b]
    assert f.db()["nacks"] == [{"item": "gap/long", "lease": "3", "run": "run-long", "count": False}]
    assert f.item(uid)["fields"]["given_back"] == ["gap/long"] and f.item(uid)["fields"]["drain_minutes"] == 45
    flag = f.model / "run" / "drain.json"
    assert json.loads(flag.read_text())["switch_started"] == NOON + 45 * 60
    r = subprocess.run([sys.executable, str(BIN / "live.py"), "switch", b], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.returncode != 0 and "not installed" in r.stderr and not flag.exists()   # a switch ends the drain,
    # whatever becomes of it; one that recorded no outcome is failed, asked of the coordinator, and not begun again
    said, why, started = switcher(f, NOON + 46 * 60)
    assert said == ["upgrade.failed", "intervention.recorded"] and started == [] and f.item(uid)["state"] == "failed"
    assert switcher(f, NOON + 47 * 60)[::2] == ([], []) and not flag.exists() and len(f.db()["nacks"]) == 1
    sensor = [sys.executable, "-c", "import sys; sys.path[:0] = [sys.argv[1]]; import drain; print(drain.gone("
              "{'since': 0, 'switch_started': 60}, 3600), drain.gone({'since': 0}, 3600), drain.gone(None, 3600))", str(BIN)]
    assert subprocess.run(sensor, cwd=f.model, env=f.env, capture_output=True, text=True).stdout.split() == [
        "0.0", "60.0", "0.0"]                                                    # the switch's own time is not the drain's


def test_an_older_switch_request_is_withdrawn(tmp_path):
    f = Factory(tmp_path)
    old, running, mid, new, newer = versions(f, 5)
    (f.tmp / "live" / "current").unlink()
    (f.tmp / "live" / "current").symlink_to(running)
    u_old, u_mid, u_new = asked(f, old, "held"), asked(f, mid, "ran"), asked(f, new, "held")
    held(f)
    said, why, started = switcher(f, NOON)
    assert said == ["upgrade.withdrawn", "upgrade.withdrawn"] and started == [] and why == "no switch approved"
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
    assert said == ["upgrade.switch-approved", "upgrade.draining"] and started == []   # never in the same step
    said, _, started = switcher(f, NOON + 180)
    assert said == ["upgrade.drained"] and started == [new]
    u_newer = asked(f, newer, "held")                                            # installed while the switch runs
    said, why, started = switcher(f, NOON + 240)
    assert said == [] and why == f"switching to {new[:12]}" and started == []   # nothing withdrawn meanwhile
    assert f.item(u_new)["state"] == "draining" and f.item(u_newer)["state"] == "installed"


def test_a_switch_waits_for_a_quiet_moment_or_the_daily_window(tmp_path, monkeypatch):
    f = Factory(tmp_path)
    a, b = versions(f, 2)
    uid = asked(f, b, "ran")
    held(f, "gap/one", "gap/two", "gap/three")
    day = time.localtime(NOON)
    five = time.mktime(day[:3] + (5, 0, 0, 0, 0, -1))                           # today 05:00, past today's window
    said, why, _ = switcher(f, five, quiet_runs=2, daily_at="04:00")
    assert said == ["upgrade.switch-approved"] and "waits for at most 2 run(s) under way (3 now) or 04:00" in why
    before = time.mktime((day.tm_year, day.tm_mon, day.tm_mday + 1, 3, 59, 0, 0, 0, -1))
    assert switcher(f, before)[0] == []                                          # tomorrow 03:59: still waits
    said, why, _ = switcher(f, before + 120)                                     # tomorrow 04:01: the window
    assert said == ["upgrade.draining"] and f.item(uid)["fields"]["runs_at_drain"] == 3
    g = Factory(tmp_path / "g")
    _, b = versions(g, 2)
    asked(g, b, "ran")
    held(g, "gap/one", "gap/two")
    assert switcher(g, five, quiet_runs=2)[0] == ["upgrade.switch-approved", "upgrade.draining"]   # quiet enough
    monkeypatch.setitem(sys.modules, "fac", sys.modules.get("fac") or module("fac"))
    monkeypatch.setitem(sys.modules, "live", sys.modules.get("live") or module("live"))
    drain = module("drain")
    assert drain.settings({}) == (1, (4, 0), 45.0)
    for bad in ({"quiet_runs": 11}, {"quiet_runs": -1}, {"drain_minutes": 0}, {"drain_minutes": 241},
                {"daily_at": "24:00"}, {"daily_at": "4am"}):
        with pytest.raises(SystemExit):
            drain.settings({"upgrade": bad})


ALLOWED = ["Bash(git rm:*)", "Bash(git mv:*)", "Bash(git restore:*)", "Bash(rm:*)",
           "Bash(uv run python scripts/suite_watch.py:*)"]
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
                                       f"odd {tok}"]}]

    def session(cfg, role, brief, work, keep=None):
        keep.copy.tok = tok                                                      # (as agents.session does)
        return {"type": "result", "subtype": "success", "is_error": False, "result": "Done", "total_cost_usd": 0.1,
                "num_turns": 1, **answers.pop(0)}
    fake.session = session
    monkeypatch.setitem(sys.modules, "agents", fake)
    lines = []
    for _ in range(4):
        fac.session(cfg, "implementor", "brief", tmp_path)
        lines.append([json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"event"')])
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
    lines.pop()                                                                  # (the folds below count the first three)

    (tmp_path / "f").mkdir()
    f = Factory(tmp_path / "f")                                                  # the gap and sessions, by the model's folds
    f.fold([x for got in lines for x in got], None)
    g = f.item("gap/alpha-thing")["fields"]
    assert g["tool_denials"] == 2 and g["tool_denials_unknown"] == 1 and len(g["denied"]) == 2
    r = subprocess.run([sys.executable, str(BIN / "measure.py"), "tool-denials"], cwd=f.model, env=f.env,
                       capture_output=True, text=True)
    assert r.returncode == 0 and float(r.stdout) == 3.0, r.stderr                # 2 refused, and 1 unknown as one
    goal = yaml.safe_load((BIN.parent / "model" / "measures.yaml").read_text())["goals"]["no-tool-denials"]
    assert (goal["auxiliary"], goal["hold"], goal["tolerance"]) == ("tool-denials", "<= 0", 0)
