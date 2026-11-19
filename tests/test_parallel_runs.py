"""The parallel run (pytest-xdist; CLAUDE.md, Testing): a test marked ``serial`` runs with nothing else of the run
alongside it."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

INNER = '''
import json, os, time
import pytest


def note(name, began):
    with open(os.environ["RUNS_LOG"], "a") as f:
        f.write(json.dumps([name, began, time.time()]) + "\\n")


@pytest.mark.serial
def test_alone():
    began = time.time()
    time.sleep(1.0)
    note("serial", began)


@pytest.mark.parametrize("i", range(8))
def test_alongside(i):
    began = time.time()
    time.sleep(0.4)
    note(f"other{i}", began)
'''


def run_inner(tmp_path: Path, n: int) -> list:
    shutil.copy(Path(__file__).with_name("conftest.py"), tmp_path / "conftest.py")
    (tmp_path / "test_inner.py").write_text(INNER)
    log = tmp_path / "runs.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "ERGOSTAT_SUITE"))}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", str(n), str(tmp_path)],
                       cwd=tmp_path, env={**env, "RUNS_LOG": str(log)}, capture_output=True, text=True, timeout=120)
    assert "9 passed" in r.stdout, r.stdout + r.stderr
    return [json.loads(x) for x in log.read_text().splitlines()]


def test_a_serial_test_runs_with_nothing_alongside(tmp_path):
    runs = run_inner(tmp_path, 3)
    (_, a, b), = [x for x in runs if x[0] == "serial"]
    others = [x for x in runs if x[0] != "serial"]
    assert len(others) == 8
    assert not [x for x in others if x[1] < b and a < x[2]], (a, b, others)       # none overlaps it
