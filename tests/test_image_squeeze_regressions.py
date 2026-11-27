"""examples/image-squeeze uses ``use: regressions`` (dev/records/regression-template-docs-demo.md): its claims: tests
command's failing count held at 0 (tests-green) and its regressed model changes at 0 (changes-hold), each served by a
person; and in the healthy demo (squeeze as it was handed over, nothing written to the model yet) both hold."""

from __future__ import annotations

import importlib.util
import json
import shutil
import threading
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import regressions
from ergostat.cli import main
from ergostat.spec.engine import Engine, read_sensor
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "image-squeeze"
GOALS = {"tests-green": ("tests-failing", "tests-fixer"), "changes-hold": ("regressed-changes", "changes-reviewer")}


def copy(tmp_path) -> Path:
    d = tmp_path / "image-squeeze"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    return d






def small(tmp_path) -> Path:
    d = tmp_path / "proj"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: t\nclaims:\n  tests: {run: \"echo '== 2 passed in 0.1s =='\", in: product}\n"
                                     "uses:\n  regressions: {use: regressions, with: {every: 1h}}\n")
    return d


def test_the_reader_waits_for_its_test_folder(tmp_path, monkeypatch):
    """A test folder the model's own first run makes (image-squeeze's run/product, made by its customers' first run)
    is waited for within the reader's time; one never made gives no value, never 0."""
    d = small(tmp_path)
    monkeypatch.chdir(d)
    t0 = time.monotonic()
    assert regressions.counts(1.0) == (None, "no folder product to run the tests in")
    assert time.monotonic() - t0 < 5
    later = threading.Timer(1.0, lambda: (d / "product").mkdir())
    later.start()
    try:
        assert regressions.counts(20.0) == (0, "")
    finally:
        later.join()


