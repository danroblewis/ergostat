"""The YAML model compiles: the spec's examples load, each broken file is refused by the compiler
for its own reason with the file and line, includes merge, and the derived parts (roles, loops,
findings) are what the spec says."""

import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import SpecError, load, read

ROOT = Path(__file__).parent.parent
REFUSED = {                                   # each broken file, and what it must be refused for
    "bad-inferred": "bad-inferred",
    "bad-setpoint": "bad-setpoint",
    "builtin-with-agent": "builtin-with-machine",
    "external-with-run": "external-with-run",
    "flow-names-a-machine": "unknown-key",
    "flow-without-ends": "flow-without-ends",
    "goal-on-stock-and-flow": "goal-of",
    "goal-with-of": "unknown-key",
    "model-on-a-program": "model-not-ai",
    "two-sensor-kinds": "sensor-kind",
    "unknown-key": "unknown-key",
}


def write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))
    return p


@pytest.mark.parametrize("path", sorted((ROOT / "docs/spec-examples").glob("*.yaml")), ids=lambda p: p.stem)
def test_the_spec_examples_compile(path):
    spec, problems = read(path)
    assert not [p for p in problems if p.level == "error"], problems


@pytest.mark.parametrize("path", sorted((ROOT / "tests/spec-invalid").glob("*.yaml")), ids=lambda p: p.stem)
def test_each_broken_file_is_refused_for_its_reason(path):
    _, problems = read(path)
    codes = {p.code for p in problems if p.level == "error"}
    assert REFUSED[path.stem] in codes, problems
    assert all(p.where and p.where.line >= 1 for p in problems if p.level == "error")


def test_first_loop_derives_its_loop():
    spec = load(ROOT / "docs/spec-examples/first-loop.yaml")
    lp = spec.loop("inbox-short")
    assert lp.closes
    assert lp.sensors == ["stock.inbox.main"]
    assert lp.controllers == ["keep-inbox-short"]          # implied by the worker's goal:
    assert lp.actuators == ["worker"]
    assert lp.valves == ["processed"]
    assert lp.disturbances == ["arrivals"]
    assert spec.role(spec.blocks["keep-inbox-short"]) == "controller" and spec.blocks["keep-inbox-short"].implied
    assert spec.role(spec.blocks["worker"]) == "actuator"


def test_production_reports_missing_feedback_on_the_critical_goal():
    _, problems = read(ROOT / "docs/spec-examples/production.yaml")
    missing = [p for p in problems if p.code == "missing-feedback"]
    assert [p.about for p in missing] == ["goal.disk-headroom"]
    assert "critical" in missing[0].message


def test_includes_merge_and_a_name_defined_twice_names_both_places(tmp_path):
    main = write(tmp_path, "ergostat.yaml", """
        name: two
        include:
          - parts/*.yaml
        stocks:
          inbox:
            unit: files
    """)
    write(tmp_path, "parts/a.yaml", """
        defaults:
          system: intake
        goals:
          short:
            stock: inbox
            hold: "<= 5"
    """)
    spec = load(main)
    assert spec.goals["short"].system == "intake"
    assert len(spec.files) == 2
    write(tmp_path, "parts/b.yaml", """
        stocks:
          inbox:
            unit: files
    """)
    _, problems = read(main)
    twice = [p for p in problems if p.code == "defined-twice"]
    assert twice and "b.yaml" in str(twice[0]) and "ergostat.yaml:" in twice[0].message


def test_unknown_references_say_what_was_meant(tmp_path):
    p = write(tmp_path, "ergostat.yaml", """
        stocks:
          inbox:
            unit: files
        flows:
          out:
            from: inbx
        blocks:
          w:
            type: program
            run: "true"
            out: flow.ot
    """)
    _, problems = read(p)
    msgs = [str(x) for x in problems if x.level == "error"]
    assert any("did you mean inbox" in m and "ergostat.yaml:7" in m for m in msgs), msgs
    assert any("did you mean out" in m for m in msgs), msgs


def test_two_blocks_on_one_flow_and_algebraic_loops_are_refused(tmp_path):
    p = write(tmp_path, "ergostat.yaml", """
        stocks:
          s:
            unit: x
        flows:
          f:
            from: s
        blocks:
          a:
            type: program
            run: "true"
            out: flow.f
          b:
            type: program
            run: "true"
            out: flow.f
          x:
            type: limit
            in: block.y
            out: block.y
          y:
            type: limit
            in: block.x
    """)
    _, problems = read(p)
    codes = {x.code for x in problems if x.level == "error"}
    assert {"two-actuators", "algebraic-loop"} <= codes


def test_yaml_one_point_one_booleans_are_not_booleans(tmp_path):
    p = write(tmp_path, "ergostat.yaml", """
        stocks:
          no:
            unit: on
    """)
    spec = load(p)
    assert spec.stocks["no"].unit == "on"


def test_a_key_written_twice_is_an_error(tmp_path):
    p = write(tmp_path, "ergostat.yaml", """
        stocks:
          s:
            unit: a
            unit: b
    """)
    with pytest.raises(SpecError) as e:
        load(p)
    assert "written twice" in str(e.value)


def test_the_yaml_wins_over_the_toml_and_shows_as_the_old_model(tmp_path):
    (tmp_path / "ergostat.toml").write_text('name = "old"\n')
    (tmp_path / "ergostat.yaml").write_text((ROOT / "docs/spec-examples/first-loop.yaml").read_text())
    m = mdl.load(tmp_path)
    assert m.name == "first-loop" and m.spec is not None
    assert m.controllers["inbox-short"].drives == ["worker"]
    assert m.flows["arrivals"].disturbance is False          # drop sets it
    assert m.loop("inbox-short").closes
    assert all(lv != "error" for lv, _ in mdl.check(m))


def test_every_old_example_converts_to_a_model_that_compiles(tmp_path):
    """The twelve examples as they were in TOML (tests/fixtures/toml): each converts, compiles, and
    keeps one goal per controller."""
    from ergostat.spec.convert import convert
    for toml in sorted((ROOT / "tests/fixtures/toml").glob("*.toml")):
        m = mdl.parse(__import__("tomllib").loads(toml.read_text()), toml, default_name=toml.stem)
        text, _ = convert(m)
        out = tmp_path / toml.stem / "ergostat.yaml"
        out.parent.mkdir()
        out.write_text(text)
        _, problems = read(out)
        assert not [p for p in problems if p.level == "error"], (toml.stem, problems)
        assert len(m.controllers) == len(load(out).goals)


def test_inferred_says_which_model_change_added_a_part_or_a_link(tmp_path):
    """``inferred:`` (SPEC §12e): on a stock, flow, auxiliary, parameter or link a model change added; the change's
    item, or true where it is not known; anything else written is declared."""
    path = write(tmp_path, "m.yaml", """\
        name: m
        stocks:
          queue:
            unit: jobs
          held:
            unit: jobs
            inferred: ergostat.model-change/ab12cd34
        flows:
          served:
            from: queue
            equation: queue-share * stock.queue
            driven-by: [+stock.queue, {cause: +stock.held, inferred: ergostat.model-change/ab12cd34}]
            inferred: true
        auxiliaries:
          ratio:
            unit: "1"
            exogenous: true
            inferred: false
        parameters:
          queue-share:
            value: 2
            unit: 1/h
            inferred: ergostat.model-change/ab12cd34
        """)
    spec, problems = read(path)
    assert not [p for p in problems if p.level == "error"], problems
    assert spec.stocks["held"].inferred == "ergostat.model-change/ab12cd34" and spec.stocks["queue"].inferred is None
    assert spec.flows["served"].inferred == "true" and spec.auxiliaries["ratio"].inferred is None
    assert spec.parameters["queue-share"].inferred == "ergostat.model-change/ab12cd34"
    assert spec.flows["served"].inferred_links == {"stock.held": "ergostat.model-change/ab12cd34"}
    from ergostat.web.server import inferred_of
    assert inferred_of(spec, "stock", "held") == {"from": "ergostat.model-change/ab12cd34"}      # the side panel's words
    assert inferred_of(spec, "flow", "served") == {"from": None} and inferred_of(spec, "stock", "queue") is None
    assert inferred_of(spec, "stock", "ratio") is None                                          # an auxiliary, opened as a level
