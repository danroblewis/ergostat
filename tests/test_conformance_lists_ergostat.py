"""ergostat's own conformance lists (dev/conformance/): the diagrams list read by the list reader, its unmet cases not
asked, and each met check shown able to fail when its view's builder draws nothing (conformance-diagrams-list)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ergostat.library.run.conformance_lists import read

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "dev" / "conformance" / "checks" / "diagrams.py"
MET = {"stock-and-flow": ("ergostat.dynamics", "dynamics"), "block-diagram": ("ergostat.blockdiagram", "diagram"),
       "process-map": ("ergostat.process", "process")}
UNMET = ["service-map", "sequence-diagram"]


def checks():
    spec = importlib.util.spec_from_file_location("diagrams_checks", CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_diagrams_list_parses_with_five_cases():
    got = read(ROOT / "dev" / "conformance", ["diagrams"])
    assert [c.name for c in got.cases] == [*MET, *UNMET]
    assert got.declared == 5
    for c in got.cases:
        assert c.check == f"python3 dev/conformance/checks/diagrams.py {c.name}"
        path, _, line = c.from_.partition(":")
        assert (ROOT / path).is_file() and line, c.from_
    assert set(checks().CASES) == {c.name for c in got.cases}


def test_diagrams_unmet_cases_not_asked():
    asked = {c.name: c.asked for c in read(ROOT / "dev" / "conformance", ["diagrams"]).cases}
    assert asked == {"stock-and-flow": True, "block-diagram": True, "process-map": True,
                     "service-map": False, "sequence-diagram": False}


@pytest.mark.parametrize("case", list(MET))
def test_each_met_diagram_check_fails_when_its_view_is_empty(case, monkeypatch):
    mod = checks()
    assert mod.main([case]) == 0                           # met as main is
    module, name = MET[case]
    real = getattr(importlib.import_module(module), name)
    monkeypatch.setattr(f"{module}.{name}", lambda *a, **k: {**real(*a, **k), "nodes": [], "edges": []})
    assert mod.main([case]) == 1                           # the view's builder drawing nothing: unmet, not broken


@pytest.mark.parametrize("case,drop", [("stock-and-flow", lambda g: {**g, "nodes": [n for n in g["nodes"]
                                                                              if not n["id"].startswith("flow:")]}),
                                       ("block-diagram", lambda g: {**g, "nodes": [n for n in g["nodes"]
                                                                             if n.get("role") != "comparator"]}),
                                       ("process-map", lambda g: {**g, "edges": []})])
def test_each_met_diagram_check_fails_on_one_part_missing(case, drop, monkeypatch):
    mod = checks()
    module, name = MET[case]
    real = getattr(importlib.import_module(module), name)
    monkeypatch.setattr(f"{module}.{name}", lambda *a, **k: drop(real(*a, **k)))
    assert mod.main([case]) == 1                           # the flows, the junctions, the lines: each is looked for


def test_a_check_error_is_broken_not_unmet(monkeypatch):
    mod = checks()
    assert mod.main(["no-such-case"]) == 2
    monkeypatch.setattr("ergostat.dynamics.dynamics", lambda *a, **k: 1 / 0)
    assert mod.main(["stock-and-flow"]) == 2


@pytest.mark.parametrize("case,rc", [*((c, 0) for c in MET), *((c, 1) for c in UNMET)])
def test_each_diagram_check_on_main_gives_its_recorded_result_within_60s(case, rc):
    t = time.monotonic()
    got = subprocess.run([sys.executable, str(CHECK), case], cwd=ROOT, capture_output=True, text=True, timeout=120)
    took = time.monotonic() - t
    assert (got.returncode, took < 60) == (rc, True), (case, got.returncode, round(took, 1), got.stdout, got.stderr)
