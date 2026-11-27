"""What a system contains (SPEC §4a, *What a system contains*): worked out from the graph of the model. A thing is in
the system it is defined in; an edge whose ends are defined in different systems is in each system on the way from
them up to their lowest common ancestor, and so are its ends (ancillary where they are not defined); what stays
inside a subsystem is not in its parent."""

import json
import textwrap

from ergostat import model as mdl
from ergostat.spec import read
from ergostat.spec.explain import explain
from ergostat.spec.scope import TOP, lines, scope
from ergostat.store import Project


def spec_of(tmp_path, text):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], [p.message for p in problems if p.level == "error"]
    return spec


def has(sc, system, kind, name):
    """The thing's status in the system (defined, ancillary), or None when the system does not contain it."""
    row = next((r for r in sc[system]["contains"].get(kind, []) if r["name"] == name), None)
    return row and row["status"]


def why(sc, system, kind, name):
    return next(r["why"] for r in sc[system]["contains"][kind] if r["name"] == name)


FACTORY = """
systems:
  factory: {description: makes things}
  intake: {within: factory, description: takes work in}
  qa: {within: factory, description: checks the work}
  delivery: {within: factory, description: ships it}
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [new, checking, done]
    system: factory
  qa-note:
    query: key.startswith('qa-note/')
    fields:
      state:
        type: one of [open, closed]
    system: qa
  shared-ref:
    query: key.startswith('ref/')
    fields:
      state:
        type: one of [open]
    system: factory
  unused-parent:
    query: key.startswith('unused/')
    fields:
      state:
        type: one of [open]
    system: factory
stocks:
  arrived:
    system: intake
    unit: tickets
    sensor: {projection: ticket, state: new}
  checking:
    system: qa
    unit: tickets
    sensor: {projection: ticket, state: checking}
  notes-open:
    system: qa
    unit: notes
    sensor: {projection: qa-note, state: open}
  refs-in:
    system: intake
    unit: refs
    sensor: {projection: shared-ref, state: open}
  refs-out:
    system: delivery
    unit: refs
    sensor: {projection: shared-ref, state: open}
  shipped:
    system: delivery
    unit: tickets
flows:
  to-qa:
    system: intake
    from: arrived
    to: checking
  notes-closed:
    system: qa
    from: notes-open
  ship:
    system: qa
    from: checking
    to: shipped
"""


def test_a_subsystem_s_own_projection_is_in_it_and_not_in_its_parent(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY))
    assert has(sc, "qa", "projections", "qa-note") == "defined"
    assert has(sc, "qa", "stocks", "notes-open") == "defined"
    assert has(sc, "qa", "flows", "notes-closed") == "defined"
    for other in ("factory", "intake", "delivery", TOP):
        assert has(sc, other, "projections", "qa-note") is None
        assert has(sc, other, "stocks", "notes-open") is None


def test_a_flow_between_two_siblings_is_in_both_and_in_their_parent(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY))
    assert has(sc, "intake", "flows", "to-qa") == "defined"
    assert has(sc, "qa", "flows", "to-qa") == "ancillary"
    assert has(sc, "factory", "flows", "to-qa") == "ancillary"
    assert has(sc, TOP, "flows", "to-qa") is None                 # it stays inside factory
    assert has(sc, "delivery", "flows", "to-qa") is None
    # both its ends come with it, each ancillary where it is not defined
    assert has(sc, "intake", "stocks", "checking") == "ancillary"
    assert has(sc, "qa", "stocks", "arrived") == "ancillary"
    assert has(sc, "factory", "stocks", "arrived") == "ancillary" and has(sc, "factory", "stocks", "checking") == "ancillary"
    assert why(sc, "qa", "flows", "to-qa") == ["flow to-qa (intake) runs from stock arrived (intake) to stock checking (qa)"]
    # the sensors on a part come with it
    assert has(sc, "intake", "sensors", "stock.checking.main") == "ancillary"


def test_a_parent_s_projection_is_given_only_to_the_child_that_uses_it(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY + """
  done-notes:
    system: delivery
    to: shipped
"""))
    assert has(sc, "factory", "projections", "ticket") == "defined"
    assert has(sc, "intake", "projections", "ticket") == "ancillary"
    assert "sensor stock.arrived.main on stock arrived (intake) counts projection ticket (factory)" in \
        why(sc, "intake", "projections", "ticket")
    # the parent's projection that nothing in a child uses stays the parent's alone
    assert has(sc, "factory", "projections", "unused-parent") == "defined"
    for child in ("intake", "qa", "delivery"):
        assert has(sc, child, "projections", "unused-parent") is None
    # and the child's stock counting it is the parent's business too (the edge is in both)
    assert has(sc, "factory", "stocks", "arrived") == "ancillary"


def test_a_projection_is_not_given_to_a_child_that_does_not_use_it(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  plant: {}
  a: {within: plant}
  b: {within: plant}
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        type: one of [open]
    system: plant
stocks:
  queue:
    system: a
    unit: jobs
    sensor: {projection: job, state: open}
  other:
    system: b
    unit: jobs
    sensor: {manual: true}
"""))
    assert has(sc, "a", "projections", "job") == "ancillary"
    assert has(sc, "b", "projections", "job") is None


def test_the_items_a_crossing_flow_carries_come_with_it(tmp_path):
    """ship runs from qa's checking to delivery's shipped: checking (and its sensor, and the tickets it counts) are in
    delivery; qa's own notes, which nothing outside qa touches, are not."""
    sc = scope(spec_of(tmp_path, FACTORY))
    assert has(sc, "delivery", "stocks", "checking") == "ancillary"
    assert has(sc, "delivery", "sensors", "stock.checking.main") == "ancillary"
    assert why(sc, "delivery", "projections", "ticket") == [
        "sensor stock.checking.main on stock checking (qa) counts projection ticket (factory)"]
    assert has(sc, "delivery", "projections", "qa-note") is None


def test_a_subsystem_s_projection_leaves_it_only_with_a_part_used_outside(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY + """
blocks:
  foreman:
    system: factory
    type: program
    run: echo 1
    in: stock.notes-open
"""))
    assert has(sc, "factory", "stocks", "notes-open") == "ancillary"
    assert why(sc, "factory", "stocks", "notes-open") == ["block foreman (factory) reads stock notes-open (qa)"]
    assert has(sc, "factory", "projections", "qa-note") == "ancillary"
    assert has(sc, "qa", "blocks", "foreman") == "ancillary"
    assert has(sc, "factory", "flows", "notes-closed") is None           # what drains it stays inside qa
    assert has(sc, "intake", "projections", "qa-note") is None


def test_siblings_share_a_projection_through_the_parent(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY))
    assert has(sc, "intake", "projections", "shared-ref") == "ancillary"
    assert has(sc, "delivery", "projections", "shared-ref") == "ancillary"
    assert has(sc, "qa", "projections", "shared-ref") is None


def test_siblings_share_a_projection_one_of_them_defines(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  plant: {}
  a: {within: plant}
  b: {within: plant}
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        type: one of [open]
    system: a
stocks:
  queue:
    system: a
    unit: jobs
    sensor: {projection: job, state: open}
  mirror:
    system: b
    unit: jobs
    sensor: {projection: job, state: open}
"""))
    assert has(sc, "a", "projections", "job") == "defined"
    assert has(sc, "b", "projections", "job") == "ancillary"
    assert has(sc, "plant", "projections", "job") == "ancillary"       # between two of its parts: the parent's too
    assert has(sc, "plant", "stocks", "mirror") == "ancillary"
    assert has(sc, "plant", "stocks", "queue") is None                  # a's own use of a's projection stays in a


GOAL_ACROSS = """
systems:
  plant: {}
  room: {within: plant}
  heater: {within: plant}
stocks:
  temperature:
    system: room
    unit: degrees
    sensor: {manual: true}
flows:
  heat-in:
    system: heater
    to: temperature
  heat-out:
    system: room
    from: temperature
goals:
  warm:
    system: room
    stock: temperature
    hold: ">= 20"
blocks:
  thermostat:
    system: heater
    type: program
    run: echo 1
    in: goal.warm
    out: flow.heat-in
agents:
  claude: {kind: ai, system: heater}
  ops: {kind: program}
"""


def test_a_goal_whose_loop_crosses_a_boundary_is_in_both_and_their_parent(tmp_path):
    sc = scope(spec_of(tmp_path, GOAL_ACROSS))
    assert has(sc, "room", "goals", "warm") == "defined"
    assert has(sc, "heater", "goals", "warm") == "ancillary"
    assert has(sc, "plant", "goals", "warm") == "ancillary"
    assert has(sc, TOP, "goals", "warm") is None
    assert "block thermostat (heater) reads goal warm (room)" in why(sc, "heater", "goals", "warm")
    assert "goal warm (room)'s loop runs through block thermostat (heater)" in why(sc, "heater", "goals", "warm")
    assert has(sc, "room", "blocks", "thermostat") == "ancillary"
    assert has(sc, "heater", "flows", "heat-out") is None                # the room's own drain stays the room's


def test_an_agent_is_in_the_systems_of_the_blocks_it_fills_and_never_brings_them_back(tmp_path):
    text = GOAL_ACROSS.replace("    out: flow.heat-in\n", "    out: flow.heat-in\n    agent: ops\n")
    sc = scope(spec_of(tmp_path, text))
    assert has(sc, TOP, "agents", "ops") == "defined"
    assert has(sc, "heater", "agents", "ops") == "ancillary"
    assert has(sc, "room", "agents", "ops") == "ancillary"            # the block is in room (it reads its goal)
    assert why(sc, "heater", "agents", "ops") == ["agent ops (the top level) fills block thermostat (heater)"]
    assert has(sc, TOP, "blocks", "thermostat") is None               # filling a role never moves the role
    assert has(sc, "heater", "agents", "claude") == "defined"         # defined in a system (agents: system:)
    assert has(sc, TOP, "agents", "claude") is None


def test_the_top_level_holds_what_is_defined_in_no_system_and_what_crosses_between_top_level_systems(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  sales: {}
  support: {}
stocks:
  leads:
    system: sales
    unit: leads
    sensor: {manual: true}
  cases:
    system: support
    unit: cases
    sensor: {manual: true}
  spare:
    system: sales
    unit: things
    sensor: {manual: true}
  budget:
    unit: dollars
    sensor: {manual: true}
flows:
  escalate:
    system: sales
    from: leads
    to: cases
"""))
    assert sc[TOP]["within"] is None and sc["sales"]["within"] == TOP
    assert sc[TOP]["systems"] == ["sales", "support"]
    assert has(sc, TOP, "stocks", "budget") == "defined"
    assert has(sc, TOP, "flows", "escalate") == "ancillary"
    assert has(sc, TOP, "stocks", "leads") == "ancillary" and has(sc, TOP, "stocks", "cases") == "ancillary"
    assert has(sc, TOP, "stocks", "spare") is None
    assert has(sc, "support", "flows", "escalate") == "ancillary"
    assert has(sc, "sales", "stocks", "budget") is None


def test_three_deep_an_edge_is_in_every_system_on_the_path_to_the_lowest_common_ancestor(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  org: {}
  eng: {within: org}
  team: {within: eng}
  ops: {within: org}
  pager: {within: ops}
stocks:
  backlog:
    system: team
    unit: tickets
    sensor: {manual: true}
  pages:
    system: pager
    unit: pages
    sensor: {manual: true}
  local:
    system: team
    unit: tickets
    sensor: {manual: true}
flows:
  page-to-ticket:
    system: pager
    from: pages
    to: backlog
  tidy:
    system: team
    from: local
    to: backlog
"""))
    for system in ("team", "eng", "org", "ops", "pager"):
        assert has(sc, system, "flows", "page-to-ticket") in ("defined", "ancillary"), system
    assert has(sc, TOP, "flows", "page-to-ticket") is None                # org is the lowest common ancestor
    assert has(sc, "eng", "stocks", "backlog") == "ancillary"
    assert has(sc, "eng", "flows", "tidy") is None and has(sc, "org", "stocks", "local") is None


def test_a_child_and_its_grandparent_put_the_edge_in_the_system_between(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  org: {}
  eng: {within: org}
  team: {within: eng}
stocks:
  backlog:
    system: team
    unit: tickets
    sensor: {manual: true}
  roadmap:
    system: org
    unit: tickets
    sensor: {manual: true}
flows:
  plan:
    system: org
    from: roadmap
    to: backlog
"""))
    assert has(sc, "eng", "flows", "plan") == "ancillary"
    assert has(sc, "team", "stocks", "roadmap") == "ancillary"
    assert has(sc, "org", "stocks", "backlog") == "ancillary"
    assert has(sc, TOP, "flows", "plan") is None


def test_relations_between_projections_are_edges(tmp_path):
    sc = scope(spec_of(tmp_path, """
systems:
  plan: {}
  build: {}
projections:
  epic:
    query: key.startswith('epic/')
    fields:
      state:
        type: one of [open]
    system: plan
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [open]
    system: build
    relations: {parent: epic}
"""))
    assert has(sc, "build", "projections", "epic") == "ancillary"
    assert has(sc, "plan", "projections", "ticket") == "ancillary"
    assert has(sc, TOP, "projections", "epic") == "ancillary"


def test_ergostat_s_own_projections_are_in_no_system_until_one_is_used(tmp_path):
    sc = scope(spec_of(tmp_path, FACTORY))
    every = {r["name"] for s in sc.values() for r in s["contains"].get("projections", [])}
    assert not any(n.startswith("ergostat.") for n in every)


def test_it_is_worked_out_once_per_version_of_the_model(tmp_path):
    spec = spec_of(tmp_path, FACTORY)
    assert scope(spec) is scope(spec)


def test_explain_says_what_each_system_contains(tmp_path):
    spec = spec_of(tmp_path, FACTORY)
    text = "\n".join(lines(spec))
    assert "System qa, within factory:" in text
    assert "Ancillary flow to-qa (defined in intake): flow to-qa (intake) runs from stock arrived (intake) to stock " \
           "checking (qa)." in text
    one = explain(spec, "system.qa")
    assert "Contains" in one and "qa-note" in one


def test_the_api_answers_what_each_system_contains(tmp_path):
    from ergostat.web.server import Live, api
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(FACTORY))
    p = Project(mdl.load(tmp_path))
    got = api(Live(p), "scope", {})
    json.dumps(got)
    assert got["top"] == TOP
    assert got["systems"]["qa"]["within"] == "factory"
    rows = {r["name"]: r for r in got["systems"]["qa"]["contains"]["flows"]}
    assert rows["to-qa"]["status"] == "ancillary" and rows["to-qa"]["defined_in"] == "intake"


def test_the_command_line_says_it(tmp_path, capsys):
    from ergostat.cli import main
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(FACTORY))
    main(["-C", str(tmp_path), "explain", "--contains"])
    out = capsys.readouterr().out
    assert out.startswith("The top level: 0 things") and "System qa, within factory: 12 things, 7 defined here" in out
    main(["-C", str(tmp_path), "explain", "--contains", "qa", "--json"])
    got = json.loads(capsys.readouterr().out)
    assert list(got["systems"]) == ["qa"]
    main(["-C", str(tmp_path), "check"])
    assert "What each system contains: the top level 0; factory 14 (11 ancillary); intake 9 (4 ancillary)" in \
        capsys.readouterr().out
