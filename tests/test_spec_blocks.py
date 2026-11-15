"""The built-in blocks compute what SPEC §9.2 says, step by step."""

import textwrap

import pytest

from ergostat.spec import blocks as bl
from ergostat.spec import load
from ergostat.spec.ir import Ref


def spec_of(tmp_path, blocks: str, goals: str = ""):
    p = tmp_path / "ergostat.yaml"
    p.write_text(textwrap.dedent("""
        stocks:
          s:
            unit: x
            sensor:
              manual: true
        goals:
          g:
            stock: s
            hold: "<= 20"
            tolerance: 5
    """) + textwrap.indent(textwrap.dedent(goals), "  ") + "blocks:\n" + textwrap.indent(textwrap.dedent(blocks), "  "))
    return load(p)


class Signals(dict):
    def get_ref(self, r: Ref):
        return self.get(str(r))


def stepper(spec, name):
    b = bl.make(spec.blocks[name], spec)
    sig = Signals()
    return b, sig


def test_onoff_turns_on_when_the_goal_is_off_and_off_at_until(tmp_path):
    spec = spec_of(tmp_path, """
        k:
          type: onoff
          goal: g
          until: "<= 15"
    """)
    b, sig = stepper(spec, "k")
    run = lambda y, off: (sig.update({"stock.s": y, "goal.g.off": off, "goal.g": 20}), b.step(sig.get_ref, 0))[1]  # noqa: E731
    assert run(10, 0) == 0
    assert run(26, 1) == 1
    assert run(18, 0) == 1          # holding again, but not yet back to until
    assert run(15, 0) == 0


def test_onoff_min_on_keeps_it_on(tmp_path):
    spec = spec_of(tmp_path, """
        k:
          type: onoff
          goal: g
          min-on: 60
    """)
    b = bl.make(spec.blocks["k"], spec)
    s = {"stock.s": 30, "goal.g.off": 1}
    assert b.step(lambda r: s.get(str(r)), 0) == 1
    s.update({"stock.s": 10, "goal.g.off": 0})
    assert b.step(lambda r: s.get(str(r)), 30) == 1
    assert b.step(lambda r: s.get(str(r)), 61) == 0


def test_compare_with_hysteresis(tmp_path):
    spec = spec_of(tmp_path, """
        c:
          type: compare
          in: stock.s
          above: 10
          back-below: 5
    """)
    b = bl.make(spec.blocks["c"], spec)
    vals = [3, 11, 8, 6, 4, 12]
    got = [b.step(lambda r, v=v: v, i) for i, v in enumerate(vals)]
    assert got == [0, 1, 1, 1, 0, 1]


def test_proportional_is_gain_times_the_size_of_the_error_clamped(tmp_path):
    spec = spec_of(tmp_path, """
        p:
          type: proportional
          goal: g
          gain: 0.5
          max: 4
    """)
    b = bl.make(spec.blocks["p"], spec)
    assert b.step(lambda r: -6.0, 0) == 3.0
    assert b.step(lambda r: -20.0, 0) == 4.0
    assert b.step(lambda r: 0.0, 0) == 0.0


@pytest.mark.parametrize("expr,env,want", [
    ("min(50, max(5, backlog / 20))", {"backlog": 400}, 20),
    ("min(50, max(5, backlog / 20))", {"backlog": 10}, 5),
    ("a * 2 + b", {"a": 1, "b": 3}, 5),
    ("1 if a > 2 else 0", {"a": 3}, 1),
])
def test_expr(expr, env, want):
    assert bl.eval_expr(bl.compile_expr(expr), env) == want


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b", "[1]", "'x'", "open(1)", "lambda: 1"])
def test_expr_refuses_anything_but_arithmetic(bad):
    with pytest.raises(bl.ExprError):
        bl.compile_expr(bad)


def test_lookup_interpolates_and_clamps():
    t = bl.read_table("lookup", {0: 0, 100: 10})
    assert bl.lookup_value(t, 50) == 5
    assert bl.lookup_value(t, -5) == 0
    assert bl.lookup_value(t, 500) == 10


def test_schedule_by_time_of_day():
    import time
    t = bl.read_table("schedule", {"00:00": 1, "09:00": 5, "18:00": 2})
    noon = time.mktime((2026, 11, 16, 12, 0, 0, 0, 0, -1))
    night = time.mktime((2026, 11, 16, 20, 0, 0, 0, 0, -1))
    assert bl.schedule_value(t, noon) == 5
    assert bl.schedule_value(t, night) == 2


def test_delay_timer_counter_select(tmp_path):
    spec = spec_of(tmp_path, """
        d:
          type: delay
          in: stock.s
          delay: 10
        t:
          type: timer
          in: stock.s
          after: 5
        n:
          type: counter
          in: stock.s
        m:
          type: select
          pick: max
          in: [stock.s, goal.g]
    """)
    d, t, n, m = (bl.make(spec.blocks[x], spec) for x in "dtnm")
    assert d.step(lambda r: 1.0, 0) is None
    assert d.step(lambda r: 2.0, 5) is None
    assert d.step(lambda r: 3.0, 11) == 1.0
    assert t.step(lambda r: 1.0, 0) == 0 and t.step(lambda r: 1.0, 6) == 1
    for i, v in enumerate([0, 1, 1, 0, 1]):
        got = n.step(lambda r, v=v: v, i)
    assert got == 2
    vals = {"stock.s": 3.0, "goal.g": 20.0}
    assert m.step(lambda r: vals.get(str(r)), 0) == 20.0


def test_order_puts_each_block_after_what_it_reads(tmp_path):
    spec = spec_of(tmp_path, """
        a:
          type: limit
          in: block.b
          max: 3
        b:
          type: compare
          in: stock.s
          above: 1
    """)
    o = bl.order(spec)
    assert o.index("b") < o.index("a")
