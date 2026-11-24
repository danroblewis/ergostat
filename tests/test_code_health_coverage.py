"""The coverage measure (docs/roadmap/overnight/code-health-coverage.md): the line tracer (tests/coverage_lines.py),
the report (scripts/coverage_report.py) and the sensor (dev/bin/measure.py coverage-below-floor)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import coverage_lines

ROOT = Path(__file__).resolve().parent.parent
MEASURE = ROOT / "dev" / "bin" / "measure.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


report = load(ROOT / "scripts" / "coverage_report.py", "coverage_report_under_test")


def git(repo: Path, *args: str) -> str:
    who = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    return subprocess.run(["git", "-C", str(repo), *who, *args], check=True, capture_output=True, text=True).stdout.strip()


def repo_with(tmp: Path, files: dict[str, str]) -> Path:
    root = tmp / "repo"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(textwrap.dedent(text))
    git(root.parent, "init", "-q", "-b", "main", str(root))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return root


def worker_file(d: Path, worker: str, lines: dict[str, list[int]], workers: int, run: str = "r1") -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"lines-{worker}.json").write_text(json.dumps({"worker": worker, "workers": workers, "run": run,
                                                        "lines": lines, "imported": sorted(lines)}))


PICK = '''\
"""The module's docstring."""


def pick(x):
    """pick's docstring."""
    if x:
        y = 1
    else:
        y = 2
    return y
'''


def free_tool() -> int:
    """A sys.monitoring tool id nobody holds (the suite's own tracer may hold COVERAGE_ID)."""
    return next(i for i in range(6) if sys.monitoring.get_tool(i) is None)


def test_tracer_counts_executed_statement_lines(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "ergostat").mkdir(parents=True)
    (root / "ergostat" / "pick.py").write_text(PICK)
    t = coverage_lines.Tracer(root=root, tool=free_tool()).start()
    try:
        load(root / "ergostat" / "pick.py", "pick_fixture").pick(True)
    finally:
        t.stop()
    owner = report.statements(PICK)
    assert sorted(set(owner.values())) == [4, 6, 7, 9, 10]          # the def, if, y = 1, y = 2, return: no docstring
    assert {owner[n] for n in t.lines["ergostat/pick.py"] if n in owner} == {4, 6, 7, 10}    # the else not taken
    assert set(t.lines) == {"ergostat/pick.py"}                     # nothing outside the roots
    for k in ("PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        monkeypatch.delenv(k, raising=False)
    t.dump(tmp_path / "cov", "main")
    assert report.combine(tmp_path / "cov", root)["ergostat/pick.py"] == {"statements": 5, "covered": 4, "share": 0.8}


def test_workers_combine_into_one_report(tmp_path):
    root = repo_with(tmp_path, {"ergostat/pick.py": PICK})
    d = tmp_path / "cov"
    worker_file(d, "gw0", {"ergostat/pick.py": [6, 7]}, workers=2)
    with pytest.raises(report.NoReport, match="gw1"):              # a worker's file missing: no report, not a part
        report.combine(d, root)
    worker_file(d, "gw1", {"ergostat/pick.py": [9, 10]}, workers=2)
    assert report.combine(d, root)["ergostat/pick.py"] == {"statements": 5, "covered": 4, "share": 0.8}
    worker_file(d, "gw1", {"ergostat/pick.py": [9, 10]}, workers=2, run="r2")
    with pytest.raises(report.NoReport, match="more than one run"):
        report.combine(d, root)


def test_below_floor_lists_worst_first(tmp_path, capsys):
    ten = "".join(f"x{i} = {i}\n" for i in range(10))
    root = repo_with(tmp_path, {"ergostat/a.py": ten, "ergostat/m.py": ten, "ergostat/z.py": ten})
    d = tmp_path / "cov"
    worker_file(d, "main", {"ergostat/z.py": [1, 2], "ergostat/m.py": [1, 2, 3, 4, 5],
                            "ergostat/a.py": list(range(1, 10))}, workers=0)
    assert report.main([str(d), "--below", "0.6", "--root", str(root)]) == 0
    listed = [line.split()[-1] for line in capsys.readouterr().out.splitlines()]
    assert listed == ["ergostat/z.py", "ergostat/m.py"]            # 0.2, then 0.5; a.py's 0.9 is above
    got = json.loads((d / "coverage.json").read_text())
    assert got["main"] == git(root, "rev-parse", "HEAD") and got["seq"] == 1
    assert {m: r["share"] for m, r in got["modules"].items()} == {"ergostat/a.py": 0.9, "ergostat/m.py": 0.5,
                                                                  "ergostat/z.py": 0.2}


class Instance:
    """A checkout of main and an instance folder whose run/coverage/ holds reports, for measure.py."""

    def __init__(self, tmp: Path):
        self.checkout = repo_with(tmp, {"app.py": "x = 1\n"})
        self.model = tmp / "instance"
        self.model.mkdir()
        self.config = tmp / "factory.toml"
        self.config.write_text(textwrap.dedent(f"""\
            [paths]
            checkout = "{self.checkout}"
            run = "run"
            [git]
            base = "main"
            [code_health]
            coverage_floor = 0.6
            """))

    def commit(self, n: int = 1) -> str:
        for _ in range(n):
            git(self.checkout, "commit", "-q", "--allow-empty", "-m", "a merge")
        return git(self.checkout, "rev-parse", "HEAD")

    def report(self, name: str, shares: dict[str, float], sha: str | None = None) -> Path:
        sha = sha or git(self.checkout, "rev-parse", "HEAD")
        seq = int(git(self.checkout, "rev-list", "--count", "--first-parent", sha))
        d = self.model / "run" / "coverage" / name
        d.mkdir(parents=True, exist_ok=True)
        mods = {m: {"statements": 10, "covered": round(s * 10), "share": s} for m, s in shares.items()}
        (d / "coverage.json").write_text(json.dumps({"main": sha, "seq": seq, "modules": mods}))
        return d / "coverage.json"

    def measure(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | {"FACTORY_CONFIG": str(self.config)}
        return subprocess.run([sys.executable, str(MEASURE), *args], cwd=self.model, env=env, capture_output=True,
                              text=True, timeout=60)


def no_value(r: subprocess.CompletedProcess) -> bool:
    return r.returncode == 1 and r.stdout.strip() == "" and "no value" in r.stderr


def test_missing_or_stale_report_has_no_value(tmp_path):
    inst = Instance(tmp_path)
    assert no_value(inst.measure("coverage-below-floor"))                       # no report at all
    bad = inst.report("corrupt", {"ergostat/a.py": 0.2})
    bad.write_text('{"main": ')
    assert no_value(inst.measure("coverage-below-floor"))                       # an unreadable one
    inst.report("r", {"ergostat/a.py": 0.2, "ergostat/b.py": 0.9})
    assert no_value(inst.measure("coverage-below-floor"))                       # one beside it (it may be the latest)
    bad.unlink()
    inst.commit(20)
    r = inst.measure("coverage-below-floor")
    assert (r.returncode, r.stdout.strip()) == (0, "1.0"), r.stderr            # 20 merges old: still read
    assert inst.measure("coverage", "ergostat/b.py").stdout.strip() == "0.9"
    assert no_value(inst.measure("coverage", "ergostat/none.py"))
    inst.commit()
    assert no_value(inst.measure("coverage-below-floor"))                       # 21: stale
    assert no_value(inst.measure("coverage", "ergostat/b.py"))


def test_a_report_of_a_commit_not_on_main_is_not_read(tmp_path):
    inst = Instance(tmp_path)
    git(inst.checkout, "checkout", "-q", "-b", "undone")
    gone = inst.commit()                                                       # (a merge the queue undid)
    git(inst.checkout, "checkout", "-q", "main")
    inst.report("r", {"ergostat/a.py": 0.2}, sha=gone)
    assert no_value(inst.measure("coverage-below-floor"))


def test_latest_report_by_seq_not_mtime(tmp_path):
    inst = Instance(tmp_path)
    old = inst.report("z-older", {"ergostat/a.py": 0.2, "ergostat/b.py": 0.3})   # (last by name too)
    inst.commit()
    inst.report("a-newer", {"ergostat/a.py": 0.8, "ergostat/b.py": 0.9})
    later = old.stat().st_mtime + 3600
    os.utime(old, (later, later))                                              # the older one touched last
    r = inst.measure("coverage-below-floor")
    assert (r.returncode, r.stdout.strip()) == (0, "0.0"), r.stderr


def test_the_queue_keeps_the_last_reports_by_seq(tmp_path):
    inst = Instance(tmp_path)
    top = inst.model / "run" / "coverage"
    for seq in range(1, 7):                                                    # (names in the reverse order)
        d = top / f"gap-{'fedcba'[seq - 1]}-20261101T00000{seq}Z"
        d.mkdir(parents=True)
        (d / "coverage.json").write_text(json.dumps({"main": "x", "seq": seq, "modules": {}}))
    (top / "not-the-queues").mkdir()
    (top / "gap-torn-20261101T000009Z").mkdir()
    (top / "gap-torn-20261101T000009Z" / "coverage.json").write_text("{not json")     # unreadable: it would hold the
    kept = Kept(inst)                                                                    # measure at no value
    assert kept("red", 1) == "not reported: the unit suite failed"
    got = kept("partial", 0, "gw0", workers=2)
    assert got.startswith("no report:") and "gw1" in got
    green = top / "gap-green-20261102T000000Z"
    assert kept("green", 0) == "reported"
    assert sorted(d.name for d in top.iterdir()) == sorted(
        ["not-the-queues", green.name] + [f"gap-{'fedcba'[s - 1]}-20261101T00000{s}Z" for s in (3, 4, 5, 6)])
    assert json.loads((green / "coverage.json").read_text())["seq"] > 6


class Kept:
    """queue.coverage_kept for one queue run's unit suite, in a child (dev/bin's queue.py shadows the stdlib's)."""

    CODE = ("import sys, subprocess; sys.path[:0] = [sys.argv[1]]; import fac, queue; from pathlib import Path\n"
            "run = subprocess.run\n"
            "def slow(cmd, *a, **k):\n"
            "    if sys.argv[6] == 'slow' and cmd[0] == sys.executable: raise subprocess.TimeoutExpired(cmd, 600)\n"
            "    return run(cmd, *a, **k)\n"
            "subprocess.run = slow\n"
            "print(queue.coverage_kept(fac.config(), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), sys.argv[5]))")

    def __init__(self, inst: Instance, repo: Path = ROOT):
        self.inst, self.repo = inst, repo

    def __call__(self, name: str, rc: int, worker: str = "main", workers: int = 0, pre: str = "HEAD",
                 slow: bool = False) -> str:
        d = self.inst.model / "run" / "coverage" / f"gap-{name}-20261102T000000Z"
        worker_file(d, worker, {}, workers=workers)
        env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | {
            "FACTORY_CONFIG": str(self.inst.config)}
        r = subprocess.run([sys.executable, "-c", self.CODE, str(ROOT / "dev" / "bin"), str(self.repo), str(d), str(rc),
                            pre, "slow" if slow else "-"], cwd=self.inst.model, env=env, capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()


def test_the_queue_scores_with_mains_script_and_survives_a_timeout(tmp_path):
    """review/code-health-coverage-1: the report is made by main's copy of the script (before the merge), never the
    branch's; a report that times out is a "no report", not an error that undoes the merge."""
    inst = Instance(tmp_path / "instance-side")
    repo = repo_with(tmp_path, {"scripts/coverage_report.py": (ROOT / "scripts" / "coverage_report.py").read_text(),
                                "ergostat/a.py": "x = 1\n"})
    pre = git(repo, "rev-parse", "HEAD")
    (repo / "scripts" / "coverage_report.py").write_text("raise SystemExit('the branch scores itself')\n")
    git(repo, "commit", "-q", "-am", "a branch's own scoring")
    kept = Kept(inst, repo)
    assert kept("mains", 0, pre=pre) == "reported"
    assert kept("branchs", 0, pre="HEAD") == "no report: the branch scores itself"
    assert kept("slow", 0, pre=pre, slow=True) == "no report: timed out"
    assert sorted(d.name for d in (inst.model / "run" / "coverage").iterdir()) == ["gap-mains-20261102T000000Z"]


SUITES = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac, queue; from pathlib import Path\n"
          "ran, kept = {}, []\n"
          "def suite(cfg, name, cwd, log, slot=True, command=None, **k):\n"
          "    ran[name] = command; log.write_text(''); return 0, 1.0\n"
          "fac.suite = suite\n"
          "queue.coverage_kept = lambda cfg, repo, cov, rc, pre: kept.append([str(cov), rc, pre]) or 'reported'\n"
          "logs = Path('logs'); logs.mkdir()\n"
          "got = queue.suites(fac.config(), Path('.'), sys.argv[2], logs, 'PRE')\n"
          "print(json.dumps({'ran': ran, 'kept': kept, 'got': got, 'named': bool(queue.COVERAGE_RUN.match(sys.argv[2]))}))")


@pytest.mark.parametrize("on", [True, False])
def test_the_queue_traces_only_its_unit_run(tmp_path, on):
    """[suites] queue_coverage: the queue's unit run alone gets ERGOSTAT_COVERAGE, into run/coverage/<the run's tag>
    (a bisecting run's -N tag too, so it is pruned by name), scored with the run's pre-merge main; off, nothing."""
    inst = Instance(tmp_path)
    with inst.config.open("a") as f:
        f.write(f'[suites]\nunit = "UNIT"\nqueue_coverage = {"true" if on else "false"}\n')
    tag = "gap-x-20261102T000000Z-2"
    env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | {"FACTORY_CONFIG": str(inst.config)}
    r = subprocess.run([sys.executable, "-c", SUITES, str(ROOT / "dev" / "bin"), tag], cwd=inst.model, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert set(out["ran"]) == {"unit", "browser", "demo"}                     # no lint step: `[suites] ruff` unset
    assert [out["ran"][n] for n in ("browser", "demo")] == [None, None]
    if not on:
        assert out["ran"]["unit"] is None and out["kept"] == [] and "coverage" not in out["got"]["unit"]
        return
    cov = out["kept"][0][0]
    assert Path(cov).parts[-3:] == ("run", "coverage", tag) and out["kept"][0][1:] == [0, "PRE"]
    assert out["ran"]["unit"] == f"ERGOSTAT_COVERAGE={cov} UNIT"
    assert out["got"]["unit"]["coverage"] == "reported" and out["named"]


PROBE = """\
import json, sys
import ergostat.durations

def test_probe():
    print("TOOL", json.dumps(sys.monitoring.get_tool(sys.monitoring.COVERAGE_ID)))
"""


def probe(tmp: Path, **env: str) -> str:
    """A pytest run in a child process with this suite's conftest as a plugin: the tool it found registered."""
    (tmp / "probe").mkdir(exist_ok=True)
    (tmp / "probe" / "test_probe.py").write_text(PROBE)
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("ERGOSTAT_", "PYTEST_"))}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s", "-p", "tests.conftest", "-p", "no:cacheprovider",
                        "-p", "no:randomly", str(tmp / "probe" / "test_probe.py")], cwd=ROOT, env=clean | env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return next(line.split(" ", 1)[1] for line in r.stdout.splitlines() if line.startswith("TOOL "))


def test_tracer_off_without_the_variable(tmp_path):
    assert probe(tmp_path) == "null"                                           # unset: no tool, no file
    cov = tmp_path / "cov"
    assert probe(tmp_path, ERGOSTAT_COVERAGE=str(cov)) == json.dumps(coverage_lines.NAME)
    got = json.loads((cov / "lines-main.json").read_text())                   # set: the tracer ran, and wrote
    assert got["lines"].get("ergostat/durations.py") and "ergostat/durations.py" in got["imported"]
