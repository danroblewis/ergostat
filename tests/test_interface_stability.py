"""Interface stability over the model's recorded history (interface_history.py, SPEC §4a): each system's interface as a
signature on every model.changed, counted in seq order, failing closed, said by explain system.NAME and status --since."""

from __future__ import annotations

import random
import textwrap

import pytest

from ergostat import history
from ergostat import interface_history as ih
from ergostat import model as mdl
from ergostat.cli import main
from ergostat.spec import chains
from ergostat.spec.explain import explain
from ergostat.store import Project

MODEL = """
name: ifs
systems:
  a: {description: takes the work in}
  b: {description: does the work}
stocks:
  qa: {unit: items, system: a, sensor: {manual: true}}
  qb: {unit: items, system: b, sensor: {manual: true}}
  outside: {unit: items, sensor: {manual: true}}
flows:
  fa: {to: qa, system: a}
  mid: {from: qa, to: qb, system: b}
  done: {from: qb, system: b}
goals:
  ga: {stock: qa, hold: '<= 5', system: a}
  gb: {stock: qb, hold: '<= 5', system: b}
blocks:
  wa: {type: program, run: 'echo 1', goal: ga, out: flow.fa, system: a}
  wb: {type: program, run: 'echo 1', goal: gb, out: flow.done, system: b}
"""
# the crossing the edit adds: wa (in a) reads stock.outside (in no system), so only a's interface changes
EDITED = MODEL.replace("  wa: {type: program,", "  wa: {in: [+stock.outside], type: program,")


def yaml_project(tmp_path, text=MODEL) -> Project:
    d = tmp_path / "m"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    chains._CACHE.clear()
    return Project(mdl.load(d))


BASE = [{"dir": "in", "kind": "signal", "part": "block.w", "peers": ["stock.x", "stock.y"]},
        {"dir": "out", "kind": "material", "part": "flow.f", "peers": ["stock.z"]}]


def _with(i, **kw):
    ports = [dict(p, peers=list(p["peers"])) for p in BASE]
    ports[i].update(kw)
    return ports


def test_signature_changes_with_each_field():
    base = ih.signature(BASE)
    sigs = [ih.signature(_with(0, dir="out")), ih.signature(_with(0, kind="setpoint")),
            ih.signature(_with(0, part="block.v")), ih.signature(_with(0, peers=["stock.x", "stock.q"])),
            ih.signature(_with(0, peers=["stock.x", "stock.y", "stock.q"]))]
    assert base not in sigs and len(set(sigs)) == len(sigs)
    assert len(base) == 16 and int(base, 16) >= 0
    with pytest.raises(KeyError):                                  # a port missing a field is not defaulted
        ih.signature([{"dir": "in", "kind": "signal", "part": "block.w"}])


def test_signature_ignores_order_and_is_unambiguous():
    shuffled = [dict(p, peers=list(reversed(p["peers"]))) for p in reversed(BASE)]
    assert ih.signature(shuffled) == ih.signature(BASE)
    for _ in range(5):
        random.shuffle(shuffled)
        assert ih.signature(shuffled) == ih.signature(BASE)
    one = [{"dir": "in", "kind": "signal", "part": "stock.a,b", "peers": []}]
    two = [{"dir": "in", "kind": "signal", "part": "stock.a", "peers": ["b"]}]
    assert ih.signature(one) != ih.signature(two)
    assert ih.signature([]) == ih.signature([])


def test_note_records_each_systems_interface(tmp_path):
    p = yaml_project(tmp_path)
    ev = history.note(p)
    spec = p.model.spec
    assert set(ev["data"]["interfaces"]) == {"a", "b"} and ev["data"]["interfaces"] == ih.signatures(spec)
    assert spec.interface("a") and ev["data"]["interfaces"]["a"] == ih.signature(spec.interface("a"))   # real ports
    assert "baseline" not in ev["data"] and "interfaces_changed" not in ev["data"]
    assert history.note(p) is None


def test_note_records_an_interface_only_change(tmp_path, monkeypatch):
    p = yaml_project(tmp_path)
    first = history.note(p)
    real = ih.signatures
    monkeypatch.setattr(ih, "signatures", lambda spec: {**real(spec), "b": "0" * 16})
    ev = history.note(p)
    assert ev is not None and ev["data"]["interfaces_changed"] == ["b"]
    assert ev["data"]["parts"] == first["data"]["parts"] and ev["data"]["version"] == first["data"]["version"]
    assert [e["id"] for e in history.changes(p, 0)] == [ev["id"]]
    monkeypatch.setattr(ih, "signatures", real)
    back = history.note(p)
    assert back["data"]["interfaces_changed"] == ["b"]
    assert history.note(p) is None


def test_an_old_record_gets_one_baseline_and_it_is_not_a_change(tmp_path):
    p = yaml_project(tmp_path)
    p.events.add("model.changed", item=p.model.name, source="ergostat",
                 data={"added": [], "removed": [], "changed": [], "parts": history.fingerprints(p.model),
                       "version": history.version(p.model), "first": True})
    ev = history.note(p)
    assert ev["data"]["baseline"] is True and ev["data"]["interfaces"] == ih.signatures(p.model.spec)
    assert "interfaces_changed" not in ev["data"]
    assert history.changes(p, 0) == []
    assert history.note(p) is None


def test_a_parts_change_after_an_old_record_lists_no_interface_change(tmp_path):
    p = yaml_project(tmp_path)
    p.events.add("model.changed", item=p.model.name, source="ergostat",
                 data={"added": [], "removed": [], "changed": [], "parts": {"stock:gone": "x"}, "version": "old",
                       "first": True})
    ev = history.note(p)
    assert "interfaces_changed" not in ev["data"] and "baseline" not in ev["data"] and ev["data"]["interfaces"]


def test_a_toml_model_records_no_interfaces_and_no_baseline(project):
    assert getattr(project.model, "spec", None) is None
    ev = history.note(project)
    assert history.note(project) is None
    (only,) = project.events.query(n=None, type="model.changed")
    assert only["id"] == ev["id"] and "interfaces" not in only["data"] and "baseline" not in only["data"]


def _events(*entries):
    """Synthetic model.changed events, in seq order: each (version, interfaces) or (version, interfaces, at)."""
    out = []
    for i, x in enumerate(entries):
        v, ifs, at = (*x, 1000 + i) if len(x) == 2 else x
        data = {"version": v} if ifs is ... else {"version": v, "interfaces": ifs}
        out.append({"seq": i + 1, "time": at, "type": "model.changed", "data": data})
    return out


A, B = "a" * 16, "b" * 16


def test_counts_changes_and_the_unchanged_run():
    got = ih.stability(_events(("v1", {"s": A}), ("v2", {"s": B}), ("v3", {"s": B}), ("v4", {"s": B})), "s", B)
    assert got == {"recorded": True, "versions": 4, "changed": 1, "unchanged": 3, "since": 1001}


def test_an_event_without_interfaces_starts_the_count_over():
    got = ih.stability(_events(("v1", {"s": A}), ("v2", {"s": B}), ("v3", ...), ("v4", {"s": B})), "s", B)
    assert (got["versions"], got["changed"], got["unchanged"]) == (1, 0, 1)
    got = ih.stability(_events(("v1", {"s": A}), ("v2", ...), ("v3", {"s": A})), "s", A)
    assert (got["versions"], got["unchanged"]) == (1, 1)


def test_a_system_removed_and_made_again_starts_over():
    got = ih.stability(_events(("v1", {"s": A}), ("v2", {"t": A}), ("v3", {"s": A})), "s", A)
    assert got["versions"] == 1
    for bad in (7, [A], {"s": 7}, {"s": [A]}):
        got = ih.stability(_events(("v1", {"s": A}), ("v2", bad), ("v3", {"s": A})), "s", A)
        assert got["versions"] == 1, bad
    assert ih.stability([{"seq": 1, "time": 1, "data": None}], "s", A) == {"recorded": False}


def test_order_is_by_seq_not_time():
    evs = _events(("v1", {"s": A}, 200), ("v2", {"s": B}, 100))
    got = ih.stability(list(reversed(evs)), "s", B)
    assert (got["changed"], got["unchanged"], got["since"]) == (1, 1, 100)
    assert ih.stability(evs, "s", A) == {"recorded": False}         # the newest by seq is B


def test_a_duplicate_record_is_one_version():
    got = ih.stability(_events(("v1", {"s": A}), ("v1", {"s": A}), ("v2", {"s": B})), "s", B)
    assert (got["versions"], got["changed"]) == (2, 1)
    got = ih.stability(_events(("v1", {"s": A}), ("v1", {"s": B})), "s", B)
    assert (got["versions"], got["changed"]) == (2, 1)


def test_the_model_as_it_is_now_unrecorded_is_said_not_counted(tmp_path, monkeypatch):
    assert ih.stability([], "s", A) == {"recorded": False}
    assert ih.stability(_events(("v1", {"s": A})), "s", B) == {"recorded": False}
    p = yaml_project(tmp_path)
    line = "Interface over the model's recorded history: the interface as it is now is not recorded yet."
    assert line in explain(p.model.spec, "system.a", p)
    monkeypatch.setattr(ih, "signatures", lambda spec: {"a": A, "b": B})
    history.note(p)                                                   # recorded, but not as the model is now
    out = explain(p.model.spec, "system.a", p)
    (got,) = [x for x in out.splitlines() if "Interface over" in x]
    assert got.strip() == line and "unchanged over" not in out


def test_explain_system_says_its_interface_history(tmp_path):
    p = yaml_project(tmp_path)
    history.note(p)
    p = yaml_project(tmp_path, EDITED)
    ev = history.note(p)
    assert ev["data"]["interfaces_changed"] == ["a"]
    out = explain(p.model.spec, "system.a", p)
    (line,) = [x for x in out.splitlines() if "Interface over" in x]
    assert "unchanged over the last 1 of 2 recorded versions (since " in line and line.endswith("); 1 change.")
    lines = out.splitlines()
    assert lines.index(line) > max(i for i, x in enumerate(lines) if x.startswith(("  Out", "  In:", "    ")))
    b = explain(p.model.spec, "system.b", p)
    assert "unchanged over the last 2 of 2 recorded versions (since " in b and "); 0 changes." in b
    assert "Interface over" not in explain(p.model.spec, "system.a")


def test_status_since_lists_an_interface_change(tmp_path, capsys):
    p = yaml_project(tmp_path)
    first = {**history.note(p)["data"], "added": []}
    p.events.add("model.changed", item=p.model.name, source="ergostat",
                 data={**first, "first": False, "interfaces": {**first["interfaces"], "a": A}, "interfaces_changed": ["a"]})
    p.events.add("model.changed", item=p.model.name, source="ergostat",          # a baseline, its parts differing
                 data={**first, "first": False, "added": ["stock:zz"], "parts": {**first["parts"], "stock:zz": "x"},
                       "baseline": True, "interfaces_changed": ["b"]})
    assert main(["-C", str(tmp_path / "m"), "--since", "1h"]) == 0
    out = capsys.readouterr().out
    said = out[out.index("the model, since"):].split("\n\n")[0].splitlines()
    assert said[0] == "the model, since 1h ago: 1 change" and len(said) == 2, said
    assert said[1].endswith("  ~interface:a"), said
