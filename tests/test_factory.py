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
    pass
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
    assert spec.blocks["implementor"].takes.at == ["fix", "ready"] and spec.blocks["implementor"].pool == 4
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
    assert said == ["gap.queued", "gap.queue-failed"] and f.item(gid)["fields"]["failed_tests"] == [
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


T = "tests/test_x.py::test_y"


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
    assert gate("") == ["gate 1: docs/roadmap/overnight/warm2.md is not the branch's first commit"]   # (without it)
    (wt / "docs" / "roadmap" / "overnight" / "later.md").write_text("# later\n")  # a file the branch added later
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "a later file")
    assert gate("docs/roadmap/overnight/later.md") == [
        "gate 1: docs/roadmap/overnight/later.md is not the branch's first commit"]


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


def test_a_dead_letter_on_main_broken_tests_says_so(monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", sys.modules.get("fac") or module("fac"))
    monkeypatch.setitem(sys.modules, "review", type(sys)("review"))     # (its park is not called here)
    dead = module("dead")
    f = {"suites_fast": {"tests": [T]}, "main_broken_tests": [T], "built_main": "a" * 40}
    assert "fail on main too" in dead.on_main(f) and "aaaaaaaaaaaa" in dead.on_main(f)
    assert dead.on_main({**f, "suites_fast": {"tests": [T, "tests/test_z.py::test_own"]}}) == ""   # one is the gap's
    assert dead.on_main({"suites_fast": {}}) == ""
