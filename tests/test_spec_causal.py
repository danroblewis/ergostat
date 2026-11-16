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
    assert ls["bugs"].polarity is None and ls["bugs"].unknown   # fixing: its sign is not written
    # the third shares its head (bugs) with fixing: named for what only it runs through
    assert ls["bugs via signups"].polarity == "B"                 # more users find more bugs, which put users off
    assert {lp.name for lp in loops(s)} == {"users", "bugs via signups", "bugs"}


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


QUEUE = """
stocks:
  failures:
    sensor:
      manual: true
  queue:
    sensor:
      manual: true
flows:
  failing:
    to: failures
    driven-by: +stock.queue
  cleared:
    from: failures
  served:
    from: queue
  arriving:
    to: queue
goals:
  no-failures:
    stock: failures
    hold: "<= 0"
blocks:
  janitor:
    type: program
    run: echo 1
    in: stock.failures
    out: flow.cleared
  server:
    type: program
    run: echo 1
    in: {READ}
    out: flow.served
"""


def test_a_block_s_reading_takes_the_sign_written_on_it(tmp_path):
    s = spec(tmp_path, QUEUE.replace("{READ}", "-stock.failures"))
    assert s.blocks["server"].signs == {"in": -1}
    signs = {(x.source, x.target): x.sign for x in links(s)}
    assert signs[("stock.failures", "block.server")] == -1
    lp = next(lp for lp in loops(s) if "block.server" in lp.parts)
    assert lp.polarity == "R"         # failures → server − → served → queue − → failing + → failures: + · − · + = −·−: R


def test_a_block_s_unsigned_reading_of_what_its_goal_is_about_takes_the_gap_s_sign(tmp_path):
    s = spec(tmp_path, QUEUE.replace("{READ}", "stock.queue"))
    signs = {(x.source, x.target): x.sign for x in links(s)}
    # the janitor names no goal, but the loop of no-failures (≤ 0) closes through it: it acts the more, the more failures
    assert signs[("stock.failures", "block.janitor")] == 1
    assert by_name(s)["failures"].polarity == "B"
    # the server reads the queue, which no goal it serves is about: not known, and check names it
    assert signs[("stock.queue", "block.server")] is None
    from ergostat.spec.findings import find
    found = [p for p in find(s) if p.code == "unsigned-link"]
    assert [p.about for p in found] == ["block.server"] and "stock.queue" in found[0].message


def test_a_sign_on_a_reading_of_a_goal_or_on_a_built_in_block_is_refused(tmp_path):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(QUEUE.replace("{READ}", "-goal.no-failures.error")))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any(p.level == "error" and "server" in p.message for p in problems)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(QUEUE.replace("{READ}", "stock.queue") + """
  gate:
    type: compare
    in: -stock.queue
    above: 3
    out: block.server
"""))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any(p.level == "error" and "gate" in p.message and "sign" in p.message for p in problems)


def test_the_model_names_its_loops_and_the_rest_are_named_for_a_member_no_sibling_has(tmp_path):
    s = spec(tmp_path, """
stocks:
  backlog:
    sensor:
      manual: true
  review:
    sensor:
      manual: true
flows:
  submitted:
    from: backlog
    to: review
  rejected:
    from: review
    to: backlog
  merged:
    from: review
goals:
  backlog-clear:
    stock: backlog
    hold: "<= 0"
  reviews-done:
    stock: review
    hold: "<= 0"
blocks:
  developer:
    type: program
    run: echo 1
    goal: backlog-clear
    out: flow.submitted
  reviewer:
    type: program
    run: echo 1
    goal: reviews-done
    out:
      merged: flow.merged
      rejected: flow.rejected
loops:
  rework:
    through: [flow.rejected, stock.backlog]
""")
    ls = by_name(s)
    assert ls["rework"].polarity == "R" and "flow.rejected" in ls["rework"].parts and "stock.backlog" in ls["rework"].parts
    assert ls["backlog-clear"].polarity == "B"
    assert {"reviews-done", "reviews-done via merged"} <= set(ls) or {"reviews-done", "reviews-done via rejected"} <= set(ls)
    for name in ls:
        assert "+" not in name and not name[-1].isdigit(), name
    # a name the model gives: by a goal too; and it must name parts that exist
    from ergostat.spec import read
    text = (tmp_path / "ergostat.yaml").read_text().replace("through: [flow.rejected, stock.backlog]", "goal: reviews-done")
    (tmp_path / "ergostat.yaml").write_text(text)
    s2, _ = read(tmp_path / "ergostat.yaml")
    assert "goal.reviews-done" in by_name(s2)["rework"].parts
    (tmp_path / "ergostat.yaml").write_text(text.replace("goal: reviews-done", "through: [flow.nothing]"))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any(p.level == "error" and "loop rework" in p.message for p in problems)
