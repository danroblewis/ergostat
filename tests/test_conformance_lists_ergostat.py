"""ergostat's own conformance lists (dev/conformance/), read by the list reader: model-formats.yaml, its checks shown
both able to say met and able to fail (conformance-model-formats-list); and the diagrams list, its unmet cases not
asked, and each met check shown able to fail when its view's builder draws nothing (conformance-diagrams-list)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
import time
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ergostat.library.run.conformance_lists import read

ROOT = Path(__file__).resolve().parent.parent
CHECKS = ROOT / "dev/conformance/checks/formats.py"
NS = "http://docs.oasis-open.org/xmile/ns/XMILE/v1.0"
FIVE = ["ergostat-yaml", "ergostat-toml", "served-model", "xmile-export", "xmile-import"]
CHECK = ROOT / "dev" / "conformance" / "checks" / "diagrams.py"
MET = {"stock-and-flow": ("ergostat.dynamics", "dynamics"), "block-diagram": ("ergostat.blockdiagram", "diagram"),
       "process-map": ("ergostat.process", "process")}
UNMET = ["service-map", "sequence-diagram"]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def formats():
    return load(CHECKS, "conformance_formats")


def checks():
    return load(CHECK, "diagrams_checks")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKS), *args], capture_output=True, text=True, cwd=ROOT, timeout=300)


def test_model_formats_list_parses_with_five_cases(formats):
    got = read(ROOT / "dev/conformance", ["model-formats"])
    assert [c.name for c in got.cases] == FIVE and got.declared == 5
    assert all(c.asked for c in got.cases)
    for c in got.cases:
        assert c.check == f"python3 dev/conformance/checks/formats.py {c.name}", c
        assert c.from_ and c.description
    assert list(formats.CASES) == FIVE


def hide_xmile(monkeypatch) -> None:
    """Hide the XMILE export and every importer name the check looks for, inside this process only, so the test
    holds whether or not the export gap's ergostat/xmile.py is on main (lesson-7)."""
    monkeypatch.setitem(sys.modules, "ergostat.xmile", None)        # find_spec gives None, import raises
    from ergostat.spec import discover
    monkeypatch.delattr(discover, "from_xmile", raising=False)


def test_xmile_checks_exit_1_without_the_feature(formats, monkeypatch, capsys):
    from ergostat.spec import discover
    # as if the export and an importer had both merged, then hidden: the hiding is what makes them unmet
    fake(monkeypatch, "ergostat.xmile", export=exporter()[0], draft=lambda text: (DRAFT, []))
    monkeypatch.setattr(discover, "from_xmile", lambda text: DRAFT, raising=False)
    assert formats.main(["xmile-export"]) == 0 and formats.main(["xmile-import"]) == 0
    hide_xmile(monkeypatch)
    assert importlib.util.find_spec("ergostat.xmile") is None
    for case, word in (("xmile-export", "no XMILE export"), ("xmile-import", "no XMILE importer")):
        assert formats.main([case]) == 1, case
        assert word in capsys.readouterr().out


def importer_present(formats) -> bool:
    for mod, names in formats.IMPORTS:
        if importlib.util.find_spec(mod) is not None:
            m = importlib.import_module(mod)
            if any(callable(getattr(m, n, None)) for n in names):
                return True
    return False


def test_checks_on_main_give_the_recorded_results(formats):
    """Definition item 2: the results recorded in dev/records/conformance-model-formats-list.md. The XMILE cases are
    unmet while their feature is absent and met once it lands (the first conformance-gained), never broken."""
    export = 0 if (ROOT / "ergostat/xmile.py").is_file() else 1
    imp = 0 if importer_present(formats) else 1
    for case, rc in zip(FIVE, (0, 0, 0, export, imp), strict=True):
        r = run(case)
        assert r.returncode == rc, (case, r.stdout, r.stderr)


def test_a_bad_case_or_a_failing_check_is_broken_not_unmet(formats, monkeypatch, tmp_path):
    assert run("no-such-case").returncode == 2
    assert formats.main(["ergostat-yaml", str(tmp_path)]) == 2       # no examples at all: nothing was checked
    assert formats.main(["ergostat-toml", str(tmp_path)]) == 2


def test_each_met_format_check_fails_on_a_broken_copy(formats, monkeypatch, tmp_path):
    good, bad = tmp_path / "good", tmp_path / "bad"
    for root in (good, bad):
        (root / "examples/first-loop").mkdir(parents=True)
        shutil.copy(ROOT / "examples/first-loop/ergostat.yaml", root / "examples/first-loop/ergostat.yaml")
        (root / "tests/fixtures/toml").mkdir(parents=True)
        shutil.copy(ROOT / "tests/fixtures/toml/first-loop.toml", root / "tests/fixtures/toml/first-loop.toml")
    y = bad / "examples/first-loop/ergostat.yaml"
    y.write_text(y.read_text().replace("out: flow.processed", "out: flow.nowhere"))
    t = bad / "tests/fixtures/toml/first-loop.toml"
    t.write_text(t.read_text().replace('flow = "processed"', 'flow = "nowhere"'))
    assert run("ergostat-yaml", str(good)).returncode == 0
    r = run("ergostat-yaml", str(bad))
    assert r.returncode == 1 and "first-loop" in r.stdout, (r.stdout, r.stderr)
    assert run("ergostat-toml", str(good)).returncode == 0
    r = run("ergostat-toml", str(bad))
    assert r.returncode == 1 and "first-loop" in r.stdout, (r.stdout, r.stderr)

    from ergostat.remote import serve
    assert formats.main(["served-model"]) == 0
    monkeypatch.setattr(serve, "FORMAT", "ergostat-model/2")
    assert formats.main(["served-model"]) == 1
    monkeypatch.undo()
    real = serve.document

    def dropped(doc, instance):
        out = real(doc, instance)
        out["sections"]["stocks"].pop(next(iter(out["sections"]["stocks"])))
        return out
    monkeypatch.setattr(serve, "document", dropped)
    assert formats.main(["served-model"]) == 1


def fake(monkeypatch, name: str, **fns) -> None:
    mod = types.ModuleType(name)
    mod.__spec__ = importlib.machinery.ModuleSpec(name, None)
    for k, v in fns.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)


def xmile(spec, eqn: str = "1", ns: str = NS, extra: str = "", reverse: bool = False) -> str:
    stocks = [f'<stock name="{n.replace("-", "_")}"><eqn>0</eqn></stock>' for n in spec.stocks]
    flows = [f'<flow name="{n.replace("-", " ")}">\n   <eqn>{eqn}</eqn></flow>' for n in spec.flows]
    parts = (flows + stocks)[::-1] if reverse else stocks + flows
    return f'<xmile xmlns="{ns}" version="1.0">{extra}<model><variables>{"".join(parts)}</variables></model></xmile>'


def exporter(**layout):
    """A stand-in with the export gap's own signature, ``export(p, snap, system=None) -> str`` (it reads p.model
    and a snapshot), so the check is tested calling the export the way it is built."""
    seen = []

    def export(p, snap: dict, system=None):
        assert isinstance(snap, dict) and "stocks" in snap and system is None
        seen.append(p.model.name)
        return xmile(p.model.spec, **layout)
    return export, seen


def test_xmile_export_check_reads_structure_not_bytes(formats, monkeypatch):
    """Definition item 4: any layout passes; a wrong namespace, a missing flow or ergostat syntax in an eqn does not."""
    for layout in ({}, {"reverse": True, "extra": '<header><vendor>x</vendor></header><isee:prefs xmlns:isee="i"/>'}):
        export, seen = exporter(**layout)
        fake(monkeypatch, "ergostat.xmile", export=export)
        assert formats.main(["xmile-export"]) == 0, layout
        assert seen == ["image-squeeze"]
    fake(monkeypatch, "ergostat.xmile",
         export=lambda p, snap, system=None: ET.fromstring(xmile(p.model.spec, eqn="MAX(0, 2) * 3")))
    assert formats.main(["xmile-export"]) == 0
    for wrong in ({"ns": "http://example.org/not-xmile"}, {"eqn": "stock.quality * 2"}, {"eqn": "window-time / 2"},
                  {"eqn": "${rate}"}):
        fake(monkeypatch, "ergostat.xmile", export=exporter(**wrong)[0])
        assert formats.main(["xmile-export"]) == 1, wrong
    fake(monkeypatch, "ergostat.xmile", export=lambda p, snap, system=None: xmile(p.model.spec)
         .replace("<flow ", "<aux ", 1).replace("</flow>", "</aux>", 1))
    assert formats.main(["xmile-export"]) == 1
    fake(monkeypatch, "ergostat.xmile", something_else=lambda p, snap, system=None: "")
    assert formats.main(["xmile-export"]) == 2                     # the module is there, its call unknown: broken


DRAFT = """\
stocks:
  backlog: {unit: tasks}
  done: {unit: tasks}
flows:
  work:
    from: backlog
    to: done
    driven-by: [+stock.backlog, -stock.done]
"""


def test_xmile_import_check_reads_the_draft(formats, monkeypatch):
    seen = []
    fake(monkeypatch, "ergostat.xmile", draft=lambda text: seen.append(text) or (DRAFT, []))
    assert formats.main(["xmile-import"]) == 0
    assert "<stock name=\"backlog\">" in seen[0]
    for wrong in (DRAFT.replace("-stock.done", "+stock.done"), DRAFT.replace("-stock.done", "stock.done"),
                  DRAFT.replace("to: done", "to: backlog"), DRAFT.replace("  done: {unit: tasks}\n", "")):
        fake(monkeypatch, "ergostat.xmile", draft=lambda text, wrong=wrong: wrong)
        assert formats.main(["xmile-import"]) == 1, wrong


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
