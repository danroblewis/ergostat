"""The architecture measures (spec/architecture.py, docs/proposals/architecture.md): planted models for each note
(two clusters in one system, two chatty systems, a ten-times gap in time constants, bad interfaces, missing
purposes), each system's size in ``explain`` and the system's panel, no notes on the clean examples, and fast."""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

from ergostat.spec import architecture as arch
from ergostat.spec import read
from ergostat.spec.explain import explain

ROOT = Path(__file__).resolve().parent.parent
CODES = ("system-splits", "systems-merge", "interface", "time-scales", "purpose")
CLEAN = ["backups", "coordinator", "disk-space", "file-queue", "first-loop", "git-hygiene", "ops", "plain-crontab",
         "software-factory", "talking-scripts", "this-mac", "ticket-factory"]


def _write(d: Path, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    return d / "ergostat.yaml"


def _notes(path: Path) -> dict:
    spec, problems = read(path, extremes=False)
    assert not [p for p in problems if p.level == "error"], [str(p) for p in problems if p.level == "error"]
    return {f"{p.code}@{p.about}": p for p in problems if p.code in CODES}


def _chain(prefix: str, n: int, system: str) -> str:
    """A chain of n queues, each held short by a worker that passes its items on: one cohesive piece."""
    out = {"stocks": [], "flows": [f"  {prefix}-in: {{to: {prefix}1, system: {system}}}"], "goals": [], "blocks": []}
    for i in range(1, n + 1):
        nxt = f", to: {prefix}{i + 1}" if i < n else ""
        out["stocks"].append(f"  {prefix}{i}: {{unit: items, system: {system}, sensor: {{manual: true}}}}")
        out["flows"].append(f"  {prefix}{i}-out: {{from: {prefix}{i}{nxt}, system: {system}}}")
        out["goals"].append(f"  {prefix}{i}-short: {{stock: {prefix}{i}, hold: '<= 5', system: {system}}}")
        out["blocks"].append(f"  {prefix}{i}-work: {{type: program, run: 'echo 1', goal: {prefix}{i}-short, "
                             f"out: flow.{prefix}{i}-out, system: {system}}}")
    return out


def _model(systems: dict[str, str], *chains: dict, extra: str = "") -> str:
    head = "name: planted\nsystems:\n" + "".join(f"  {s}: {{description: {d}}}\n" for s, d in systems.items())
    body = "".join(f"{k}:\n" + "\n".join(x for c in chains for x in c[k]) + "\n" for k in ("stocks", "flows", "goals", "blocks"))
    return head + body + extra


def test_a_system_of_two_clusters_is_said_to_split_naming_them(tmp_path):
    two = _write(tmp_path / "two", _model({"plant": "keeps both queues short"}, _chain("a", 3, "plant"), _chain("b", 3, "plant")))
    got = _notes(two)
    x = got["system-splits@system.plant"]
    assert x.level == "note"
    assert "2 clusters with 0 links between them" in x.message
    assert "goal.a1-short" in x.message and "goal.b1-short" in x.message
    one = _write(tmp_path / "one", _model({"plant": "keeps the queue short"}, _chain("a", 5, "plant")).replace(
        "  a1-work: {", "  a1-work: {in: [+stock.a3, +stock.a5], ").replace(
        "  a3-work: {", "  a3-work: {in: [+stock.a1, +stock.a5], ").replace(
        "  a5-work: {", "  a5-work: {in: [+stock.a1, +stock.a3], "))
    assert "system-splits@system.plant" not in _notes(one)          # one piece, its stages tied together


def test_a_system_of_independent_subsystems_is_said_to_be_several(tmp_path):
    text = _model({"job": "the whole job", "left": "the left queues", "right": "the right queues"},
                  _chain("a", 3, "left"), _chain("b", 3, "right")).replace(
        "  left: {description: the left queues}", "  left: {description: the left queues, within: job}").replace(
        "  right: {description: the right queues}", "  right: {description: the right queues, within: job}")
    x = _notes(_write(tmp_path, text))["system-splits@system.job"]
    assert "independent systems held in one" in x.message and "[system.left]" in x.message


CHATTY = """
name: chatty
systems:
  a: {description: takes the work in}
  b: {description: does the work}
stocks:
  qa: {unit: items, system: a, sensor: {manual: true}}
  qb: {unit: items, system: b, sensor: {manual: true}}
flows:
  fa: {to: qa, system: a}
  mid: {from: qa, to: qb, system: b}
  done: {from: qb, system: b}
goals:
  ga: {stock: qa, hold: '<= 5', system: a}
  gb: {stock: qb, hold: '<= 5', system: b}
blocks:
  wa: {type: program, run: 'echo 1', goal: ga, out: flow.mid, system: b}
  wb: {type: program, run: 'echo 1', goal: gb, in: [+stock.qa], out: flow.done, system: b}
"""


def test_two_chatty_systems_are_said_to_merge(tmp_path):
    got = _notes(_write(tmp_path, CHATTY))
    x = got["systems-merge@system.a"]
    assert "b (3 links between them; 2 inside a" in x.message
    assert not [k for k in got if k.startswith("systems-merge")][1:]


TIMES = """
name: times
systems:
  plant: {description: a fast tank and a slow one}
parameters:
  fast-time: {value: 6m}
  slow-time: {value: 2h}
stocks:
  fast: {unit: litres, initial: 10, system: plant, sensor: {manual: true}}
  slow: {unit: litres, initial: 10, system: plant, sensor: {manual: true}}
flows:
  fill: {to: fast, rate: 1, system: plant}
  pass: {from: fast, to: slow, equation: stock.fast / fast-time, driven-by: [+stock.fast], system: plant}
  drain: {from: slow, equation: stock.slow / slow-time, driven-by: [+stock.slow], system: plant}
goals:
  slow-full: {stock: slow, hold: '>= 5', system: plant}
"""


def test_a_ten_times_gap_in_time_constants_is_a_candidate_for_a_hierarchy(tmp_path):
    x = _notes(_write(tmp_path / "gap", TIMES))["time-scales@system.plant"]
    assert "20 times apart" in x.message and "fast [stock.fast 6m], slow [stock.slow 1h59m]" in x.message
    near = _write(tmp_path / "near", TIMES.replace("slow-time: {value: 2h}", "slow-time: {value: 30m}"))
    assert "time-scales@system.plant" not in _notes(near)


BAD_INTERFACE = """
name: boundaries
systems:
  up: {description: makes parts}
  down: {description: assembles them}
stocks:
  made: {unit: parts, system: up, sensor: {manual: true}}
  stocked: {unit: parts, system: down, sensor: {manual: true}}
  kits: {unit: parts, system: down, sensor: {manual: true}}
flows:
  making: {to: made, system: up}
  shipped: {from: made, system: up}
  received: {to: stocked, driven-by: [+flow.shipped], system: down}
  kitting: {from: stocked, to: kits, system: down}
  used: {from: kits, system: down}
goals:
  stock-low: {stock: stocked, hold: '<= 50', system: down}
  made-low: {stock: made, hold: '<= 50', system: up}
blocks:
  kitter: {type: program, run: 'echo 1', goal: stock-low, out: flow.kitting, system: down}
  boss: {type: program, run: 'echo 1', goal: made-low, out: block.kitter, system: up}
  shipper: {type: program, run: 'echo 1', in: [+stock.made], out: flow.shipped, system: up}
"""


def test_a_bad_interface_is_flagged(tmp_path):
    got = _notes(_write(tmp_path / "bad", BAD_INTERFACE))
    x = got["interface@system.down"].message
    assert "material crosses through clouds on both sides: flow.shipped leaves for a cloud and flow.received" in x
    assert "block.boss (outside) commands block.kitter, which its own goals' loops use: it reaches into its internals" in x
    wide = BAD_INTERFACE.replace("  shipper: {type: program, run: 'echo 1', in: [+stock.made],",
                                 "  shipper: {type: program, run: 'echo 1', in: [+stock.made, +stock.stocked, +stock.kits, "
                                 "+flow.kitting, +flow.used, +flow.received, goal.stock-low],") + \
        "  watch: {type: program, run: 'echo 1', in: [+stock.stocked, +stock.kits, +flow.received], out: flow.making, system: up}\n"
    w = _notes(_write(tmp_path / "wide", wide))["interface@system.down"].message
    assert "information links cross it: a wide interface" in w
    good = BAD_INTERFACE.replace("  shipped: {from: made, system: up}", "  shipped: {from: made, to: stocked, system: up}") \
        .replace("  received: {to: stocked, driven-by: [+flow.shipped], system: down}\n", "") \
        .replace("out: block.kitter, system: up", "out: flow.making, system: up")
    assert not [k for k in _notes(_write(tmp_path / "good", good)) if k.startswith("interface")]


def test_purpose_names_systems_without_one_and_goals_traced_to_none(tmp_path):
    text = CHATTY.replace("  a: {description: takes the work in}", "  a: {}").replace(
        "  b: {description: does the work}", "  b: {description: does the work}\n  idle: {description: nothing yet}").replace(
        "  gb: {stock: qb, hold: '<= 5', system: b}", "  gb: {stock: qb, hold: '<= 5', system: b}\n  gc: {stock: qb, hold: '>= 0'}")
    got = _notes(_write(tmp_path / "p", text))
    assert "says nothing of what it is for" in got["purpose@system.a"].message
    assert "no goal inside it holds anything" in got["purpose@system.idle"].message
    assert got["purpose@model"].message.startswith("goals ga, gc: in no system that says what it is for")
    traced = _notes(_write(tmp_path / "q", "purpose: keep the work moving\n" + text))
    assert "purpose@model" not in traced and "purpose@system.a" in traced


def test_a_purpose_belongs_to_the_main_file(tmp_path):
    main = _write(tmp_path, "name: m\npurpose: keep it short\ninclude: [more.yaml]\n")
    (tmp_path / "more.yaml").write_text("purpose: another\n")
    spec, problems = read(main, extremes=False)
    assert spec.purpose == "keep it short"
    assert [p.code for p in problems if p.level == "error"] == ["purpose-in-include"]


def test_system_size_in_explain_and_the_panel(tmp_path, monkeypatch):
    path = _write(tmp_path / "m", _model({"plant": "keeps the a queues short", "other": "keeps the b queues short"},
                                         _chain("a", 3, "plant"), _chain("b", 2, "other")))
    spec, _ = read(path, extremes=False)
    assert arch.size(spec, "plant") == {"parts": 13, "loops": 3, "through": 0, "depth": 0}
    assert "Size: 13 parts, 3 feedback loops inside." in explain(spec, "system.plant")
    assert "- plant: 0 in, 0 out; 13 parts, 3 feedback loops inside" in explain(spec)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(path.parent)))
    for view in ({}, {"view": ["dynamics"]}):                  # the box the system's panel opens on, in both views
        box = next(n for n in api(live, "graph", view)["nodes"] if n["id"] == "system:plant")
        assert box["size"] == "13 parts, 3 feedback loops inside"


def test_the_clean_examples_have_no_architecture_notes_and_every_example_is_fast():
    for ex in sorted(p for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists()):
        from ergostat.spec.compile import compile_doc
        from ergostat.spec.load import load
        spec, _ = compile_doc(load(ex / "ergostat.yaml"))
        found: list = []
        t = time.perf_counter()
        arch.findings(spec, lambda *a, found=found: found.append(a))
        took = time.perf_counter() - t
        assert took < 0.5, (ex.name, took)
        if ex.name in CLEAN:
            assert found == [], (ex.name, found)
