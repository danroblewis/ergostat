"""The simplifier (docs/roadmap/overnight/code-health-simplifier.md): the evidence of scripts/code_evidence.py, the
pick and the request of dev/bin/simplify.py, pool 1 under its lock, the removals recorded, and the simplify-when gate,
on a fixture repository with the record faked in memory."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ergostat.spec import read
from ergostat.spec.blocks import compile_expr, eval_expr

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
DAY = 86400.0
NOW = time.mktime((2026, 11, 21, 12, 0, 0, 0, 0, -1))


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@localhost",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True).stdout.strip()


LONG = "def long_one(x):\n" + "".join(f"    x = x + {i}\n" for i in range(68)) + "    return x\n"
TWIN = """def {name}(items, limit):
    out = []
    for item in items:
        if item > {k}:
            out.append(item * 2)
    return out[:limit]
"""
FILES = {
    "ergostat/__init__.py": "",
    "ergostat/big.py": LONG + "\n\n" + TWIN.format(name="twin_a", k=1) + "\n\ndef unnamed_fn():\n    return 1\n\n\n"
                       "def yaml_named():\n    return 2\n\n\ndef string_named():\n    return 3\n",
    "ergostat/other.py": TWIN.format(name="twin_b", k=7) + "\n\ndef helper():\n    return twin_b([], 1)\n",
    "ergostat/small.py": "def tiny():\n    return 0\n",
    "dev/bin/tool.py": "def run():\n    return 0\n",
    "scripts/bench.py": "def bench():\n    return 0\n",
    "ergostat.yaml": "blocks:\n  b:\n    run: python3 -c 'from ergostat.big import yaml_named'\n",
    "tests/test_s.py": "NAMES = ['string_named', 'long_one', 'tiny', 'run', 'bench']\n",
}


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "checkout"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for name, text in FILES.items():
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text(text)
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "fixture")
    return r


def coverage(tmp: Path, **shares) -> Path:
    mods = ["ergostat/__init__.py", "ergostat/big.py", "ergostat/other.py", "ergostat/small.py", "dev/bin/tool.py",
            "scripts/bench.py"]
    p = tmp / "coverage.json"
    p.write_text(json.dumps({m: {"statements": 10, "covered": 9, "share": shares.get(m.split("/")[-1][:-3], 0.9)}
                             for m in mods}))
    return p


class Record:
    """The gap items, folded as the record folds them: an event about an id that exists merges into its fields."""

    def __init__(self, gaps=()):
        self.gaps, self.added = [dict(g) for g in gaps], []

    def items(self, kind, state=None):
        return json.loads(json.dumps([g for g in self.gaps if state in (None, g["state"])]))

    def add(self, event, item, **data):
        self.added.append((event, item, data))
        old = next((g for g in self.gaps if g["id"] == item), None)
        if old:
            old["fields"].update(json.loads(json.dumps(data)))
            old["state"] = "open"
        else:
            self.gaps.append({"id": item, "state": "open", "fields": json.loads(json.dumps(data))})


@pytest.fixture
def simp(monkeypatch, tmp_path, repo):
    """simplify.py against a fac of its own. The dev/bin modules it imports (measure, parks, times, brief, knowledge)
    bind that fac, so each one new in sys.modules is taken out after the test: left there, a later test on the same
    worker would import them bound to a fac it never patched."""
    before = set(sys.modules)
    yield from _simp(monkeypatch, tmp_path, repo)
    for name in set(sys.modules) - before:
        if str(getattr(sys.modules[name], "__file__", "") or "").startswith(str(BIN)):
            del sys.modules[name]


def _simp(monkeypatch, tmp_path, repo):
    monkeypatch.syspath_prepend(str(BIN))
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    monkeypatch.setattr(fac, "MODEL", tmp_path)
    monkeypatch.delitem(sys.modules, "measure", raising=False)                    # imported again against this fac
    s = module("simplify")
    rec = Record()
    monkeypatch.setattr(fac, "items", rec.items)
    monkeypatch.setattr(fac, "add", rec.add)
    s.rec = rec
    s.cfg = {"paths": {"checkout": str(repo), "run": str(tmp_path / "run"), "live": str(tmp_path / "live")},
             "git": {"base": "main"},
             "code_health": {"coverage": str(coverage(tmp_path)), "coverage_floor": 0.6, "size": 1.0, "churn": 0.25,
                             "duplicates": 1.0, "dead": 0.5}}
    yield s


def evidence_rows(repo: Path, cov: Path) -> dict[str, dict]:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "code_evidence.py"), "--root", str(repo), "--coverage",
                        str(cov)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "candidates only" in r.stderr
    return {row["module"]: row for row in map(json.loads, r.stdout.splitlines())}


def test_evidence_finds_size_duplicates_and_dead_candidates(repo, tmp_path):
    rows = evidence_rows(repo, coverage(tmp_path, big=0.7))
    big, other = rows["ergostat/big.py"], rows["ergostat/other.py"]
    assert set(rows) == {"ergostat/__init__.py", "ergostat/big.py", "ergostat/other.py", "ergostat/small.py",
                         "dev/bin/tool.py", "scripts/bench.py"}
    assert big["long_functions"] == ["long_one"] and big["lines"] > 70
    assert big["duplicates"] == ["twin_a"] and other["duplicates"] == ["twin_b"]   # names and constants differ
    assert "unnamed_fn" in big["dead_candidates"]
    assert "yaml_named" not in big["dead_candidates"]                            # named only in a run: line
    assert "string_named" not in big["dead_candidates"]                          # named only in a string
    assert "helper" in other["dead_candidates"] and "twin_b" not in other["dead_candidates"]
    assert big["churn"] == 1 and big["coverage"] == 0.7


def test_evidence_reads_this_repository(tmp_path):
    (tmp_path / "coverage.json").write_text("{}")
    rows = evidence_rows(ROOT, tmp_path / "coverage.json")
    assert "dev/bin/fac.py" in rows and "scripts/suite_watch.py" in rows and "ergostat/cli/__init__.py" in rows
    assert all(r["coverage"] is None for r in rows.values())                   # not in the report: unknown, not covered
    assert not {"git", "say", "items"} & set(rows["dev/bin/fac.py"]["dead_candidates"])


def test_pick_skips_under_floor_in_flight_and_recent(simp, tmp_path):
    cfg = simp.cfg
    row, s, _ = simp.choose(cfg, [], NOW)
    assert row["module"] == "ergostat/big.py" and s > 0                          # the best, with nothing in the way

    cfg["code_health"]["coverage"] = str(coverage(tmp_path, big=0.5))
    row, _, passed = simp.choose(cfg, [], NOW)
    assert row["module"] != "ergostat/big.py" and "under the floor" in passed["ergostat/big.py"]
    report = json.loads(coverage(tmp_path).read_text())
    del report["ergostat/big.py"]                                                 # not in the report: not covered
    (tmp_path / "partial.json").write_text(json.dumps(report))
    cfg["code_health"]["coverage"] = str(tmp_path / "partial.json")
    assert simp.choose(cfg, [], NOW)[2]["ergostat/big.py"] == "coverage None under the floor 0.6"

    cfg["code_health"]["coverage"] = str(coverage(tmp_path))
    defs = tmp_path / "run" / "defs"
    defs.mkdir(parents=True)
    (defs / "other-work.md").write_text("# other-work\n\n## Files to touch\n\n`ergostat/big.py`, `tests/x.py`.\n")
    busy = {"id": "gap/other-work", "state": "in-review",
            "fields": {"source": "request", "branch": "other-work", "definition": str(defs / "other-work.md")}}
    row, _, passed = simp.choose(cfg, [busy], NOW)
    assert row["module"] != "ergostat/big.py" and passed["ergostat/big.py"] == "a gap in flight touches it"

    old = {"id": "gap/simplify-ergostat-big-20261111", "state": "merged",
           "fields": {"source": "simplifier", "module": "ergostat/big.py", "requested_at": NOW - 10 * DAY}}
    row, _, passed = simp.choose(cfg, [old], NOW)
    assert row["module"] != "ergostat/big.py" and "picked in the last 30 days" in passed["ergostat/big.py"]
    old["fields"]["requested_at"] = NOW - 31 * DAY
    assert simp.choose(cfg, [old], NOW)[0]["module"] == "ergostat/big.py"


def test_no_pick_when_evidence_is_missing(simp, tmp_path, capsys):
    cfg = simp.cfg
    cfg["code_health"]["coverage"] = str(tmp_path / "no-report.json")             # no coverage report
    assert simp.request(cfg, NOW) == 0
    assert not simp.rec.added and "no pick" in capsys.readouterr().out

    cfg["code_health"]["coverage"] = str(coverage(tmp_path))
    bare = tmp_path / "bare"
    bare.mkdir()
    git(bare, "init", "-q", "-b", "main")                                         # no git history
    cfg["paths"]["checkout"] = str(bare)
    assert simp.request(cfg, NOW) == 0
    assert not simp.rec.added and "no pick" in capsys.readouterr().out

    cfg["paths"]["checkout"] = str(tmp_path / "checkout")
    simp.rec.gaps.append({"id": "gap/lost", "state": "building",                   # a definition it cannot read
                          "fields": {"source": "request", "branch": "lost", "definition": "run/defs/lost.md"}})
    assert simp.request(cfg, NOW) == 0
    assert not simp.rec.added and "gap/lost's definition cannot be read" in capsys.readouterr().out

    simp.rec.gaps.clear()                                                         # and with all of it, a request
    assert simp.request(cfg, NOW) == 0 and len(simp.rec.added) == 1


def test_pick_reads_mains_latest_coverage_report(simp, repo, tmp_path, capsys):
    """With no report file named, the pick reads main's latest coverage report under run/coverage/ by its seq, as the
    coverage measure does; none there means no pick."""
    cfg = simp.cfg
    del cfg["code_health"]["coverage"]
    assert simp.request(cfg, NOW) == 0
    assert not simp.rec.added and "no pick" in capsys.readouterr().out             # no report yet
    sha, top = git(repo, "rev-parse", "HEAD"), tmp_path / "run" / "coverage"
    mods = json.loads(coverage(tmp_path).read_text())
    for tag, seq, big in (("gap-a-20261120T000000Z", 2, 0.5), ("gap-b-20261101T000000Z", 1, 0.9)):
        (top / tag).mkdir(parents=True)
        report = {"main": sha, "seq": seq, "modules": {**mods, "ergostat/big.py": {**mods["ergostat/big.py"],
                                                                                    "share": big}}}
        (top / tag / "coverage.json").write_text(json.dumps(report))
    row, _, passed = simp.choose(cfg, [], NOW)                                    # seq 2 wins, though named later
    assert row["module"] != "ergostat/big.py" and "under the floor" in passed["ergostat/big.py"]
    (top / "gap-a-20261120T000000Z" / "coverage.json").write_text("{not json")
    assert simp.request(cfg, NOW) == 0
    assert not simp.rec.added and "unreadable report" in capsys.readouterr().out


def test_the_factory_settings_read_as_one_code_health_table():
    """dev/factory.toml parses (a second [code_health] table, as a merge once left it, does not) and holds what the
    pick reads; with no `coverage` file named, the pick reads main's latest report."""
    import tomllib
    hc = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["code_health"]
    assert {"coverage_floor", "size", "churn", "duplicates", "dead"} <= set(hc) and "coverage" not in hc


def test_pool_one_under_a_racing_request(simp, monkeypatch):
    cfg, real, racers = simp.cfg, simp.choose, []

    def racing_choose(*a):
        got = real(*a)                                       # read and decided; before the write, a second run
        if not racers:
            t = threading.Thread(target=simp.request, args=(cfg, NOW + DAY))     # (another id: only the lock stops it)
            racers.append(t)
            t.start()
            t.join(2)                                        # it waits on the lock (without one, it writes now)
        return got
    monkeypatch.setattr(simp, "choose", racing_choose)
    assert simp.request(cfg, NOW) == 0
    racers[0].join(30)
    assert not racers[0].is_alive()
    opened = [g for g in simp.rec.gaps if g["fields"].get("source") == "simplifier"]
    assert len(opened) == 1 and len(simp.rec.added) == 1

    for state in ("queued", "in-review", "fix", "ready"):                         # in flight, every state but done
        opened[0]["state"] = state
        assert simp.request(cfg, NOW + 5 * DAY) == 0 and len(simp.rec.added) == 1, state
    opened[0]["state"] = "merged"
    opened[0]["fields"]["requested_at"] = NOW - 40 * DAY
    assert simp.request(cfg, NOW + 5 * DAY) == 0 and len(simp.rec.added) == 2


def test_same_module_on_another_day_starts_clean(simp):
    cfg = simp.cfg
    simp.rec.gaps.append({"id": "gap/simplify-ergostat-big-20261010", "state": "parked",
                          "fields": {"source": "simplifier", "module": "ergostat/big.py", "requested_at": NOW - 42 * DAY,
                                     "verdict": "park", "findings": ["old"], "failed_gates": 2}})
    assert simp.request(cfg, NOW) == 0
    (event, gid, data), = simp.rec.added
    assert event == "gap.requested" and gid == "gap/simplify-ergostat-big-20261121"
    new = next(g for g in simp.rec.gaps if g["id"] == gid)
    assert new["state"] == "open" and not {"verdict", "findings", "failed_gates"} & set(new["fields"])
    assert new["fields"]["source"] == "simplifier" and new["fields"]["module"] == "ergostat/big.py"
    assert new["fields"]["evidence"]["long_functions"] == ["long_one"]
    text = (Path(cfg["paths"]["run"]) / "defs" / "simplify-ergostat-big-20261121.md").read_text()
    assert "`ergostat/big.py`" in text and "Removed: <class> <path>[::<name>] <lines>" in text
    assert "net lines over the whole diff (tests and docs aside) are below 0" in text


def test_removals_recorded_by_class(simp, repo, monkeypatch, capsys):
    pre = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "factory/simplify-ergostat-big-20261121")
    (repo / "ergostat" / "big.py").write_text(LONG)
    git(repo, "commit", "-q", "-am", "remove two\n\nRemoved: dead ergostat/big.py::unnamed_fn 2\n"
                                     "Removed: duplicate ergostat/big.py::twin_a 6")
    (repo / "ergostat" / "small.py").write_text("")
    git(repo, "commit", "-q", "-am", "tidy\n\nRemoved: tidy ergostat/small.py 2")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "factory/simplify-ergostat-big-20261121", "-m", "Merge")
    merged = git(repo, "rev-parse", "HEAD")
    fac = sys.modules["fac"]
    gaps = {"gap/simplify-ergostat-big-20261121": {"source": "simplifier", "branch": "simplify-ergostat-big-20261121"},
            "gap/plain": {"source": "request", "branch": "plain"}}
    monkeypatch.setattr(fac, "ergostat", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(
        {"id": a[1], "kind": "gap", "state": "merged", "fields": gaps[a[1]]}), ""))
    event = {"type": "gap.merged", "data": {"main_sha": merged, "pre": pre}}

    assert simp.removals(simp.cfg, {"event": {**event, "item": "gap/plain"}}) == 0
    assert capsys.readouterr().out == ""                                          # not the simplifier's: nothing
    assert simp.removals(simp.cfg, {"event": {**event, "item": "gap/simplify-ergostat-big-20261121"}}) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x["item"] for x in lines] == [f"removal/simplify-ergostat-big-20261121-{n}" for n in (1, 2, 3)]
    assert all(x["event"] == "removal.recorded" for x in lines)
    d = [x["data"] for x in lines]
    assert [x["class"] for x in d] == ["dead", "duplicate", "unclassified"]
    assert (d[0]["path"], d[0]["name"], d[0]["lines"]) == ("ergostat/big.py", "unnamed_fn", 2)
    assert (d[2]["path"], d[2]["name"], d[2]["trailer"]) == ("ergostat/small.py", "", "tidy ergostat/small.py 2")
    assert {x["merge"] for x in d} == {merged} and {x["gap"] for x in d} == {"gap/simplify-ergostat-big-20261121"}


@pytest.mark.slow                                                                 # (the model's checks: about 20 s)
def test_simplify_when_fires_on_age_and_not_in_flight():
    spec, problems = read(ROOT / "ergostat.yaml", extremes=False)   # (those findings are never errors, and run 60 s)
    assert not [p for p in problems if p.level == "error"], [p for p in problems if p.level == "error"]
    assert {"simplify-when", "simplifier", "simplify-removals"} <= set(spec.blocks) and "removal" in spec.items
    b = spec.blocks["simplify-when"]
    assert {r.name for r in b.outputs["out"]} == {"simplifier"}

    def fires(**given) -> float:
        return eval_expr(compile_expr(b.params["expr"]), {k: given[k] for k in b.inputs})
    assert fires(days=3, inflight=0, over=0) == 1
    assert fires(days=3, inflight=1, over=0) == 0
    assert fires(days=2.9, inflight=0, over=0) == 0
    assert fires(days=9999, inflight=0, over=1) == 0
