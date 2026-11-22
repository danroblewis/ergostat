"""The code measures (dev/records/code-health-measures.md): dev/bin/measure.py's code-net-lines, code-long-functions,
code-duplicates, code-dead-candidates and code-coverage, summed from scripts/code_evidence.py's rows (the coverage
report for code-coverage), stamped with main's seq; their change over main's last 10 merges by seq; and the goals on
it, whose size goals off fire the simplifier through simplify-when's drift input."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from ergostat.spec import read
from ergostat.spec.blocks import compile_expr, eval_expr

ROOT = Path(__file__).resolve().parent.parent
MEASURE = ROOT / "dev" / "bin" / "measure.py"
SIZE = ("code-net-lines", "code-long-functions", "code-duplicates", "code-dead-candidates")

LONG = "def long_one(x):\n" + "".join(f"    x = x + {i}\n" for i in range(68)) + "    return x\n"
TWIN = "def {name}(items, limit):\n    out = []\n    for item in items:\n        if item > {k}:\n" \
       "            out.append(item * 2)\n    return out[:limit]\n"
FILES = {
    "ergostat/__init__.py": "",
    "ergostat/big.py": LONG + "\n\n# a comment\n\n" + TWIN.format(name="twin_a", k=1) + "\n\ndef unnamed_fn():\n"
                       "    return 1\n",
    "ergostat/other.py": TWIN.format(name="twin_b", k=7) + "\n\ndef helper():\n    return twin_b([], 1)\n",
    "dev/bin/tool.py": "def run():\n    return 0\n",
    "scripts/bench.py": "def bench():\n    return 0\n",
    "tests/test_s.py": "NAMES = ['long_one', 'run', 'bench']\n",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@localhost",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True).stdout.strip()


class Instance:
    """A checkout of main (the fixture files) and an instance folder, for measure.py run as the sensors run it."""

    def __init__(self, tmp: Path, checkout: Path | None = None):
        self.checkout = tmp / "checkout"
        self.checkout.mkdir()
        git(self.checkout, "init", "-q", "-b", "main")
        for name, text in FILES.items():
            (self.checkout / name).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / name).write_text(text)
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "fixture")
        self.model = tmp / "instance"
        self.model.mkdir()
        self.config = tmp / "factory.toml"
        self.config.write_text(textwrap.dedent(f"""\
            [paths]
            checkout = "{checkout or self.checkout}"
            run = "run"
            [git]
            base = "main"
            [code_health]
            coverage_floor = 0.6
            """))
        self.history = self.model / "run" / "code-measures.jsonl"

    def commit(self, n: int = 1) -> list[str]:
        out = []
        for _ in range(n):
            git(self.checkout, "commit", "-q", "--allow-empty", "-m", "a merge")
            out.append(git(self.checkout, "rev-parse", "HEAD"))
        return out

    def seq(self, sha: str = "HEAD") -> int:
        return int(git(self.checkout, "rev-list", "--count", "--first-parent", sha))

    def report(self, mods: dict[str, tuple[int, int]]) -> None:
        sha = git(self.checkout, "rev-parse", "HEAD")
        d = self.model / "run" / "coverage" / "r"
        d.mkdir(parents=True, exist_ok=True)
        (d / "coverage.json").write_text(json.dumps({"main": sha, "seq": self.seq(sha), "modules": {
            m: {"statements": s, "covered": c, "share": round(c / s, 3) if s else 0.0} for m, (s, c) in mods.items()}}))

    def readings(self, rows: list[tuple[str, int, float]], measure: str = "code-net-lines") -> None:
        """History lines in the order given, each stamped later in time than the one before."""
        self.history.parent.mkdir(parents=True, exist_ok=True)
        with self.history.open("a") as f:
            for i, (sha, seq, value) in enumerate(rows):
                f.write(json.dumps({"measure": measure, "seq": seq, "sha": sha, "value": value, "at": 1000.0 + i}) + "\n")

    def measure(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | {"FACTORY_CONFIG": str(self.config)}
        return subprocess.run([sys.executable, str(MEASURE), *args], cwd=self.model, env=env, capture_output=True,
                              text=True, timeout=120)


def value(r: subprocess.CompletedProcess) -> float:
    assert r.returncode == 0, r.stderr
    return float(r.stdout.strip())


def no_value(r: subprocess.CompletedProcess) -> bool:
    return r.returncode == 1 and r.stdout.strip() == "" and "no value" in r.stderr


def evidence_rows(repo: Path, tmp: Path) -> list[dict]:
    (tmp / "none.json").write_text("{}")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "code_evidence.py"), "--root", str(repo), "--coverage",
                        str(tmp / "none.json")], capture_output=True, text=True, timeout=60, check=True)
    return [json.loads(line) for line in r.stdout.splitlines()]


def test_measures_match_code_evidence(tmp_path):
    inst = Instance(tmp_path)
    rows = evidence_rows(inst.checkout, tmp_path)
    want = {"code-net-lines": sum(r["lines"] for r in rows),
            "code-long-functions": sum(len(r["long_functions"]) for r in rows),
            "code-duplicates": sum(len(r["duplicates"]) for r in rows),
            "code-dead-candidates": sum(len(r["dead_candidates"]) for r in rows)}
    assert want["code-long-functions"] == 1 and want["code-duplicates"] == 2 and want["code-dead-candidates"] >= 1
    for name in SIZE:
        assert value(inst.measure(name)) == want[name], name
    inst.report({"ergostat/big.py": (30, 27), "ergostat/other.py": (10, 1)})     # 28/40, not the mean share 0.5
    assert value(inst.measure("code-coverage")) == 0.7
    sha = git(inst.checkout, "rev-parse", "HEAD")
    stamped = [json.loads(line) for line in inst.history.read_text().splitlines()]
    assert [(s["measure"], s["seq"], s["sha"]) for s in stamped] == [(n, 1, sha) for n in (*SIZE, "code-coverage")]
    assert [s["value"] for s in stamped] == [*(want[n] for n in SIZE), 0.7]


def test_missing_inputs_have_no_value(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    gone = Instance(tmp_path / "a", checkout=tmp_path / "no-checkout")
    for name in SIZE:
        assert no_value(gone.measure(name)), name                                  # no checkout
    broken = Instance(tmp_path / "b")
    (broken.checkout / "ergostat" / "bad.py").write_text("def (:\n")
    git(broken.checkout, "add", "-A")
    git(broken.checkout, "commit", "-q", "-m", "a module that does not parse")
    for name in SIZE:
        r = broken.measure(name)
        assert no_value(r) and "code_evidence.py: exit 2" in r.stderr, (name, r.stderr)   # a failing evidence run
    assert no_value(broken.measure("code-coverage"))                               # no coverage report
    broken.report({"ergostat/big.py": (0, 0)})
    assert no_value(broken.measure("code-coverage"))                               # one with no statements
    assert not broken.history.exists() and not gone.history.exists()              # nothing stamped as a reading
    assert no_value(broken.measure("code-net-lines-change"))                       # and no history: no trend
    broken.history.write_text('{"measure": "code-net-lines", "seq": 1, "sha": "x", "value": 1}\n{"meas')
    assert no_value(broken.measure("code-net-lines-change"))                       # an unreadable history line


def test_trend_by_seq_counts_one_sha_once(tmp_path):
    inst = Instance(tmp_path)
    first, *_, a, b = [git(inst.checkout, "rev-parse", "HEAD"), *inst.commit(12)]
    assert (inst.seq(first), inst.seq(a), inst.seq(b)) == (1, 12, 13)
    git(inst.checkout, "checkout", "-q", "-b", "undone")
    undone = inst.commit()[0]                                                      # (a merge the queue undid)
    git(inst.checkout, "checkout", "-q", "main")
    inst.readings([(a, 12, 100)])
    assert no_value(inst.measure("code-net-lines-change"))                         # one sha: no change yet
    inst.readings([(a, 12, 100), (a, 12, 100)])
    assert no_value(inst.measure("code-net-lines-change"))                         # read three times: still one
    inst.readings([(first, 1, 0), (b, 13, 101), (a, 12, 100), (undone, 14, 500)])
    # one step (a to b), though a was read again after b and an undone sha has the highest seq; seq 1 is 12 merges back
    assert value(inst.measure("code-net-lines-change")) == 1
    inst.readings([(b, 13, 99)])                                                   # b read again: its last reading
    assert value(inst.measure("code-net-lines-change")) == -1


def test_drift_turns_simplify_when_on(tmp_path):
    inst = Instance(tmp_path)
    shas = [git(inst.checkout, "rev-parse", "HEAD"), *inst.commit(10)]
    inst.readings([(s, inst.seq(s), 1000 + 5 * i) for i, s in enumerate(shas)])   # rising over 10 merges
    rise = value(inst.measure("code-net-lines-change"))
    assert rise == 50

    spec, problems = read(ROOT / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], [p for p in problems if p.level == "error"]
    size = {"code-net-lines": "lines", "code-long-functions": "long", "code-duplicates": "dups",
            "code-dead-candidates": "dead"}
    for name in (*size, "code-coverage", *(f"{n}-change" for n in (*size, "code-coverage"))):
        aux = spec.auxiliaries[name]
        assert aux.sensors and all(s.every == 3600 and f"measure.py {name}" in s.run for s in aux.sensors.values())
    goal = spec.goals["code-net-lines-not-rising"]
    assert str(goal.of) == "auxiliary.code-net-lines-change"
    assert (goal.status(rise, False), goal.status(0, False), goal.status(-3, False)) == ("off", "holding", "holding")
    cov = spec.goals["code-coverage-not-falling"]
    assert (cov.status(-0.001, False), cov.status(0, False)) == ("off", "holding")

    drift, when = spec.blocks["code-drift"], spec.blocks["simplify-when"]
    assert {k: str(r) for k, r in drift.inputs.items()} == {v: f"goal.{n}-not-rising.off" for n, v in size.items()}
    assert str(when.inputs["drift"]) == "block.code-drift"
    asks = spec.blocks["code-health-off"]
    assert {str(r) for r in asks.inputs.values()} == {"block.code-drift", "goal.code-coverage-not-falling.off"}
    assert {r.name for r in asks.outputs["out"]} == {"improve-factory"}

    def run(b, **given) -> float:
        return eval_expr(compile_expr(b.params["expr"]), {k: given[k] for k in b.inputs})
    on = run(drift, lines=float(goal.status(rise, False) == "off"), long=0, dups=0, dead=0)
    assert on == 1 and run(drift, lines=0, long=0, dups=0, dead=0) == 0
    assert run(when, days=0, inflight=0, over=0, drift=on) == 1                  # drift fires it, not the 3 days
    assert run(when, days=0, inflight=1, over=0, drift=on) == 0                  # pool 1: not while one is in flight
    assert run(when, days=0, inflight=0, over=0, drift=0) == 0
    assert run(when, days=0, inflight=0, over=1, drift=on) == 0                  # nor on a spent day


def test_check_on_the_root_model_reports_no_errors():
    """`ergostat check --json --no-coherence` as the factory runs it ([suites] check, stderr in the same log): its JSON
    is read as implement.py reads it (fac.findings), with no error in it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")}
    r = subprocess.run([sys.executable, "-m", "ergostat", "check", "--json", "--no-coherence"], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    sys.path.insert(0, str(ROOT / "dev" / "bin"))
    import fac
    assert fac.findings(r.stdout, fac.RECORD_FINDINGS) is not None, (r.returncode, r.stdout[:3000], r.stdout[-3000:])
    got = json.JSONDecoder().raw_decode(r.stdout[r.stdout.index("{"):])[0]
    assert [x for x in got["found"] if x["level"] == "error"] == []
