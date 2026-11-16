"""Causal loops (SPEC §12a): the feedback loops a system dynamics view names, found in the model,
each reinforcing (R), balancing (B) or of unknown sign."""

import textwrap

from ergostat.spec import read
from ergostat.spec.causal import links, loops


def spec(tmp_path, text):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    s, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
    return s


def by_name(s):
    return {lp.name: lp for lp in loops(s)}


def test_a_goal_on_a_queue_drained_by_its_worker_is_balancing(tmp_path):
    s = spec(tmp_path, """
stocks:
  inbox:
    sensor:
      manual: true
flows:
  arrivals:
    to: inbox
  processed:
    from: inbox
goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
blocks:
  worker:
    type: program
    goal: inbox-short
    run: echo 1
    out: flow.processed
""")
    ls = by_name(s)
    assert list(ls) == ["inbox-short"]
    lp = ls["inbox-short"]
    assert lp.polarity == "B" and lp.goals == ["inbox-short"]
    assert lp.parts == ["stock.inbox", "goal.inbox-short", "block.keep-inbox-short", "block.worker", "flow.processed"]
    signs = {(x.source, x.target): x.sign for x in links(s)}
    assert signs[("flow.processed", "stock.inbox")] == -1 and signs[("flow.arrivals", "stock.inbox")] == 1
    assert signs[("stock.inbox", "goal.inbox-short")] == -1


def test_a_floor_held_by_an_inflow_is_balancing_too(tmp_path):
    s = spec(tmp_path, """
stocks:
  ideas:
    sensor:
      manual: true
flows:
  proposed:
    to: ideas
goals:
  ideas-ready:
    stock: ideas
    hold: ">= 2"
blocks:
  researcher:
    type: program
    goal: ideas-ready
    run: echo 1
    out: flow.proposed
""")
    assert by_name(s)["ideas-ready"].polarity == "B"


def test_signed_influences_make_reinforcing_and_balancing_loops_and_unsigned_ones_unknown(tmp_path):
    s = spec(tmp_path, """
stocks:
  users: {}
  bugs: {}
flows:
  signups:
    to: users
    driven-by: [+stock.users, -stock.bugs]
  found:
    to: bugs
    driven-by: +stock.users
  fixed:
    from: bugs
    driven-by: stock.bugs
""")
    ls = by_name(s)
    assert ls["users"].polarity == "R"                         # word of mouth: users bring users
    assert ls["users"].parts == ["stock.users", "flow.signups"]
    assert ls["bugs+users"].polarity == "B"                     # more users find more bugs, which put users off
    assert ls["bugs"].polarity is None and ls["bugs"].unknown   # fixing: its sign is not written
    assert {lp.name for lp in loops(s)} == {"users", "bugs+users", "bugs"}


def test_an_integral_controller_through_a_two_way_flow_and_a_cascade(tmp_path):
    s = spec(tmp_path, """
auxiliaries:
  quality:
    sensor:
      manual: true
    driven-by: +stock.setting
stocks:
  setting: {}
  queue:
    sensor:
      manual: true
flows:
  steps:
    to: setting
    two-way: true
  served:
    from: queue
goals:
  quality-held:
    auxiliary: quality
    hold: "== 0.9"
  queue-short:
    stock: queue
    hold: "<= 10"
blocks:
  tuner:
    type: program
    run: echo 1
    in: goal.quality-held.error
    out: flow.steps
  on-off:
    type: onoff
    goal: quality-held
    out: block.server
  server:
    type: program
    run: echo 1
    in: block.on-off
    out: flow.served
  outer:
    type: compare
    in: stock.queue
    below: 3
    out: goal.quality-held
""")
    ls = by_name(s)
    assert ls["quality-held"].polarity == "B"
    assert ls["quality-held"].parts == ["auxiliary.quality", "goal.quality-held", "block.tuner", "flow.steps", "stock.setting"]
    # the queue's controller is set from outside: queue → compare (below: −) → the goal's setpoint (+) → onoff on an
    # "==" goal (not known which way) → the server → served (−)
    outer = next(lp for lp in loops(s) if "block.outer" in lp.parts)
    assert outer.polarity is None
