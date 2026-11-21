"""Modes and eigenvalue elasticity at the model's start (numbers/modes.py; docs/roadmap/overnight/eigenvalue-elasticity.md):
hand-computed elasticities of small matrices, the reasons given instead of numbers (λ = 0, repeated, faults, non-finite
entries, QR that does not converge, too many stocks), the one Jacobian shared with time constants, and `explain`."""

from __future__ import annotations

import cmath
import math
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ergostat.numbers import extremes as ex
from ergostat.numbers import modes as md
from ergostat.numbers import simulate as sim
from ergostat.spec import read
from ergostat.spec.explain import explain

ROOT = Path(__file__).resolve().parent.parent
XY = ["stock.x", "stock.y"]


def _spec(tmp_path: Path, text: str, name: str = "m"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, problems = read(d / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], [str(p) for p in problems if p.level == "error"]
    return spec


def _eps(m: md.Mode, refs=XY) -> list[list[complex]]:
    return [[m.links.get((i, j), 0) for j in refs] for i in refs]


def _close(got, want, tol=1e-9):
    for g, w in zip(got, want, strict=True):
        for a, b in zip(g, w, strict=True):
            assert abs(a - b) <= tol * max(1.0, abs(b)), (got, want)


def _by(ms: md.Modes, lam: complex, tol=1e-6) -> md.Mode:
    (m,) = [m for m in ms.modes if abs(m.value - lam) <= tol * max(1.0, abs(lam))]
    return m


def _finite(ms: md.Modes) -> None:
    for m in ms.modes:
        assert cmath.isfinite(m.value)
        for x in (m.tau_h, m.period_h):
            assert x is None or math.isfinite(x)
        for e in (m.links or {}).values():
            assert cmath.isfinite(e)


def test_a_coupled_pair_gives_hand_computed_elasticities():
    ms = md.of_matrix([[-1.0, 1.0], [-2.0, -4.0]], XY)
    assert ms.why is None and len(ms.modes) == 2
    two, three = _by(ms, -2), _by(ms, -3)
    _close(_eps(two), [[1, 1], [1, -2]])
    _close(_eps(three), [[-1 / 3, -2 / 3], [-2 / 3, 8 / 3]])
    for m in (two, three):
        assert abs(sum(m.links.values()) - 1) <= 1e-9
        assert next(iter(m.links)) == ("stock.y", "stock.y")
    assert md.line(two).startswith("λ -2/h (τ 30m): stock.y (its own) ε -2.00;")
    assert ms.modes[0] is two                                       # slowest first


def test_a_complex_pair_ranks_a_cross_link_first_by_modulus():
    ms = md.of_matrix([[-1.0, 2.0], [-1.0, -1.0]], XY)
    (m,) = ms.modes                                                 # the pair, listed once
    assert abs(m.value - complex(-1, math.sqrt(2))) <= 1e-9 and m.value.imag > 0
    own, cross = (1 + 1j * math.sqrt(2)) / 6, (2 - 1j * math.sqrt(2)) / 6
    _close(_eps(m), [[own, cross], [cross, own]])
    assert abs(abs(own) - math.sqrt(3) / 6) < 1e-12 and abs(abs(cross) - math.sqrt(6) / 6) < 1e-12
    assert list(m.links) == [("stock.x", "stock.y"), ("stock.y", "stock.x"), ("stock.x", "stock.x"), ("stock.y", "stock.y")]
    assert abs(m.period_h - 2 * math.pi / math.sqrt(2)) <= 1e-9 and abs(m.tau_h - 1) <= 1e-9
    text = md.line(m)
    assert text.startswith("λ -1 ± 1.41i/h (τ 1h, period 4h26m): stock.y → stock.x |ε| 0.41 (0.33-0.24i);"), text
    assert abs(sum(m.links.values()) - 1) <= 1e-9


def test_a_complex_pair_ranks_by_modulus_not_by_real_part():
    # The plan review's matrix: here the own link of x leads by |ε| (3/√21 against 2/√21), while the cross links lead
    # by Re ε (2/7 against 3/14). (For a 2×2 complex pair a cross link first by |ε| is always first by Re ε too:
    # Re ε(own) = ad/2|λ|², Re ε(cross) = −bc/2|λ|², and |ε(cross)| > |ε(own a)| exactly when −bc > a² ≥ ad.)
    ms = md.of_matrix([[-3.0, 2.0], [-2.0, -1.0]], XY)
    (m,) = ms.modes
    r3 = math.sqrt(3)
    assert abs(m.value - complex(-2, r3)) <= 1e-9
    xx, yy, cross = complex(3 / 14, 5 * r3 / 14), complex(3 / 14, r3 / 42), complex(2 / 7, -4 * r3 / 21)
    _close(_eps(m), [[xx, cross], [cross, yy]])
    assert list(m.links) == [("stock.x", "stock.x"), ("stock.x", "stock.y"), ("stock.y", "stock.x"), ("stock.y", "stock.y")]
    assert abs(sum(m.links.values()) - 1) <= 1e-9


ZERO = """
name: conserved
parameters:
  hour: {value: 1h}
  two: {value: 2h}
stocks:
  x: {unit: litres, initial: 10, sensor: {manual: true}}
  y: {unit: litres, initial: 10, sensor: {manual: true}}
flows:
  there: {from: x, to: y, equation: stock.x / hour, driven-by: [+stock.x]}
  back: {from: y, to: x, equation: stock.y / two, driven-by: [+stock.y]}
"""


def test_a_zero_eigenvalue_gives_no_elasticities_and_the_other_mode_does(tmp_path):
    ms = md.of_matrix([[-1.0, 0.5], [1.0, -0.5]], XY)
    zero, other = ms.modes
    assert zero.value == 0 and zero.links is None and zero.tau_h is None and "λ = 0" in zero.why
    assert abs(other.value + 1.5) <= 1e-9
    _close(_eps(other), [[4 / 9, 2 / 9], [2 / 9, 1 / 9]])
    _finite(ms)
    spec = _spec(tmp_path, ZERO)
    got = md.at_start(spec)
    assert got.why is None and got.modes[0].links is None and "λ = 0" in got.modes[0].why
    _finite(got)
    text = explain(spec)
    assert md.HEAD in text and "λ 0/h: no decay" in text and "λ -1.5/h (τ 40m)" in text
    assert not re.search(r"\b(nan|inf)\b", text, re.I)


def test_repeated_and_defective_eigenvalues_give_no_elasticities():
    for J in ([[-1.0, 0.0], [0.0, -1.0]], [[-1.0, 0.0], [1.0, -1.0]]):
        ms = md.of_matrix(J, XY)
        assert ms.why is None and len(ms.modes) == 2
        for m in ms.modes:
            assert m.links is None and "repeated" in m.why, (J, m)


def test_w_dot_v_near_zero_is_refused_on_its_own():
    links, why = md.elasticities([[-1.0, 0.0], [1.0, -1.0]], -1.0, [1.0, 0.0], [0.0, 1.0], XY)
    assert links is None and "repeated" in why


def test_inverse_iteration_at_an_exact_eigenvalue_finds_the_vector():
    J = [[-1.0, 0.0], [1.0, -3.0]]
    for lam, want in ((-1.0, [[1, 0], [0, 0]]), (-3.0, [[0, 0], [0, 1]])):
        v, w = md.vector(J, lam), md.vector(J, lam, left=True)
        assert v is not None and w is not None
        res = max(abs(sum(J[i][j] * v[j] for j in range(2)) - lam * v[i]) for i in range(2))
        assert res <= 1e-8 * 4 * max(abs(x) for x in v)
        links, why = md.elasticities(J, lam, w, v, XY)
        assert why is None
        _close([[links.get((i, j), 0) for j in XY] for i in XY], want)


def test_an_eigenvector_not_found_is_said(monkeypatch):
    monkeypatch.setattr(md, "vector", lambda J, lam, left=False: None)
    for m in md.of_matrix([[-1.0, 1.0], [-2.0, -4.0]], XY).modes:
        assert m.links is None and m.why == md.LOST and m.most_in is None


def test_qr_that_does_not_converge_says_why(monkeypatch):
    J = [[-1.0, 2.0, 0.5], [-1.0, -1.0, 1.0], [0.3, 1.0, -3.0]]
    refs = ["stock.a", "stock.b", "stock.c"]
    assert md.of_matrix(J, refs).why is None and len(md.of_matrix(J, refs).modes) == 2
    monkeypatch.setattr(md, "ITERS", 1)
    ms = md.of_matrix(J, refs)
    assert "did not converge" in ms.why and ms.modes == []


FAULT = """
name: fault
parameters:
  hour: {value: 1h}
stocks:
  x: {unit: litres, initial: 10, sensor: {manual: true}}
  y: {unit: litres, initial: 0, sensor: {manual: true}}
flows:
  out: {from: x, equation: stock.x / stock.y, driven-by: [+stock.x, -stock.y]}
  fill: {to: y, equation: stock.x / hour, driven-by: [+stock.x]}
"""


def test_equations_that_fault_at_the_start_say_which(tmp_path):
    ms = md.at_start(_spec(tmp_path, FAULT))
    assert "flow.out" in ms.why and "divided by 0" in ms.why and ms.modes == []


def test_equations_that_fault_only_when_a_stock_is_moved_say_which(tmp_path):
    spec = _spec(tmp_path, """
        name: edge
        stocks:
          x: {unit: litres, initial: 10, sensor: {manual: true}}
        flows:
          out: {from: x, equation: SQRT(10.0005 - stock.x), driven-by: [-stock.x]}
        """)
    ms = md.at_start(spec)                                          # fine at 10; the step (10 + 0.001) takes the root of < 0
    assert ms.why.startswith("the equations fault when a stock is moved a little from the start") and "flow.out" in ms.why
    assert ms.modes == []


BLOWS = """
name: blows
stocks:
  x: {{unit: litres, initial: {x}, sensor: {{manual: true}}}}
flows:
  out: {{from: x, equation: "{eq}", driven-by: [+stock.x]}}
"""


@pytest.mark.parametrize("x, eq", [
    (100, "EXP(stock.x)"),                                                       # 2.7e43: clamped to 1e12
    (700, "EXP(stock.x) * EXP(stock.x) - EXP(stock.x) * EXP(stock.x)"),          # inf - inf: NaN, taken as 0
], ids=["overflow", "nan"])
def test_an_equation_past_big_or_nan_at_the_start_is_said(tmp_path, x, eq):
    st, state = ex._at_start(spec := _spec(tmp_path, BLOWS.format(x=x, eq=eq)), sim.plan(spec),
                             ex.Condition("usual", "with everything as usual", usual=True), None)
    st.evaluate()
    assert st.faults() == [] and st.clamped == {"flow.out": 1}         # the stepper's faults alone would not say it
    ms = md.at_start(spec)
    assert ms.why.startswith("the equations fault at the start: flow.out: not a number or past ±1e+12")
    assert ms.modes == []


def test_an_equation_past_big_only_when_a_stock_is_moved_is_said(tmp_path):
    ms = md.at_start(_spec(tmp_path, BLOWS.format(x=0, eq="EXP(stock.x * 30000000)")))   # 1 at 0; e^30 at the step
    assert ms.why.startswith("the equations fault when a stock is moved a little from the start") and "flow.out" in ms.why
    assert ms.modes == []


PAIR = """
name: pair
parameters:
  hour: {value: 1h}
  quarter: {value: 15m}
  half: {value: 30m}
stocks:
  x: {unit: litres, initial: 10, sensor: {manual: true}}
  y: {unit: litres, initial: 10, sensor: {manual: true}}
flows:
  x-in: {to: x, equation: stock.y / hour, driven-by: [+stock.y]}
  x-out: {from: x, equation: stock.x / hour, driven-by: [+stock.x]}
  y-out: {from: y, equation: stock.y / quarter, driven-by: [+stock.y]}
  y-taken: {from: y, equation: stock.x / half, driven-by: [+stock.x]}
"""


def test_equations_that_raise_at_the_start_say_why(tmp_path, monkeypatch):
    spec = _spec(tmp_path, PAIR)

    def bad(self, dt=None):
        raise ValueError("no such thing")
    monkeypatch.setattr(sim._Stepper, "evaluate", bad)
    ms = md.at_start(spec)
    assert ms.why == "the equations fail at the start: no such thing" and ms.modes == []


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_a_non_finite_jacobian_entry_is_named(tmp_path, monkeypatch, bad):
    spec = _spec(tmp_path, PAIR)
    J = {("x", "x"): -1.0, ("x", "y"): bad, ("y", "x"): -2.0, ("y", "y"): -4.0}
    monkeypatch.setattr(sim._Stepper, "jacobian", lambda self, state: (J, []))
    ms = md.at_start(spec)
    assert ms.why == f"stock.y → stock.x is {bad}" and ms.modes == []


def test_no_equation_reading_a_stock_gives_why_not_an_empty_answer(tmp_path):
    spec = _spec(tmp_path, """
        name: open
        parameters:
          rate: {value: 2}
        stocks:
          x: {unit: litres, initial: 10, sensor: {manual: true}}
        flows:
          out: {from: x, equation: rate}
        """)
    ms = md.at_start(spec)
    assert ms.why == md.NO_FEEDBACK and ms.modes == []
    assert f"Modes: not worked out: {md.NO_FEEDBACK}" in explain(spec)


UNFITTED = """
name: unfitted
parameters:
  tau: {{estimate: true, unit: h}}
  hour: {{value: 1h}}
stocks:
  x: {{unit: litres, initial: 10, sensor: {{manual: true}}}}
{aux}flows:
  out: {{from: x, equation: {out}, driven-by: [+stock.x]}}
"""


@pytest.mark.parametrize("aux, out", [
    ("", "stock.x / tau"),                                                       # a stock's drain, not run
    ("auxiliary:\n  k: {equation: 1 / tau}\n", "stock.x * auxiliary.k"),           # feeds the drain, not run
], ids=["drain", "feeds-the-drain"])
def test_an_equation_with_an_unfitted_parameter_says_why_not_lambda_0(tmp_path, aux, out):
    spec = _spec(tmp_path, UNFITTED.format(aux=aux.replace("auxiliary:", "auxiliaries:"), out=out))
    ms = md.at_start(spec)                                          # the run holds it at 0: J = [[0]] would be "λ = 0"
    assert ms.why.startswith("an equation the stocks depend on is not run, a parameter has no value:")
    assert "tau has no value" in ms.why and ms.modes == []
    assert ("flow.out" if not aux else "auxiliary.k") in ms.why
    assert "λ 0/h" not in explain(spec) and "Modes: not worked out: an equation the stocks" in explain(spec)


def test_more_than_most_stocks_returns_before_the_jacobian(tmp_path, monkeypatch):
    n = md.MOST + 1
    stocks = "".join(f"  s{i}: {{unit: litres, initial: 10, sensor: {{manual: true}}}}\n" for i in range(n))
    flows = "".join(f"  f{i}: {{from: s{i}{f', to: s{i + 1}' if i + 1 < n else ''}, equation: stock.s{i} / hour, "
                    f"driven-by: [+stock.s{i}]}}\n" for i in range(n))
    spec = _spec(tmp_path, f"name: chain\nparameters:\n  hour: {{value: 1h}}\nstocks:\n{stocks}flows:\n{flows}")

    def boom(*a, **k):
        raise AssertionError("built before the cap")
    monkeypatch.setattr(ex, "_at_start", boom)
    monkeypatch.setattr(sim._Stepper, "jacobian", boom)
    ms = md.at_start(spec)
    assert ms.why.startswith("41 stocks move by equations, more than 40:") and ms.modes == []


def _spy(monkeypatch) -> list:
    got = []
    real = sim._Stepper.jacobian

    def jacobian(self, state, **kw):
        out = real(self, state, **kw)
        got.append((self, out[0]))
        return out
    monkeypatch.setattr(sim._Stepper, "jacobian", jacobian)
    return got


def test_the_model_pair_matches_its_matrix(tmp_path, monkeypatch):
    spec = _spec(tmp_path, PAIR)
    got = _spy(monkeypatch)
    ms = md.at_start(spec)
    (_, J), = got
    want = {("x", "x"): -1, ("x", "y"): 1, ("y", "x"): -2, ("y", "y"): -4}
    for k, v in want.items():
        assert J[k] == pytest.approx(v, rel=1e-6)
    _close(_eps(_by(ms, -2)), [[1, 1], [1, -2]], 1e-6)
    _close(_eps(_by(ms, -3)), [[-1 / 3, -2 / 3], [-2 / 3, 8 / 3]], 1e-6)
    text = explain(spec)
    assert "λ -2/h (τ 30m): stock.y (its own) ε -2.00" in text and "λ -3/h (τ 20m): stock.y (its own) ε 2.67" in text


TIMES = """
name: times
systems:
  a: {description: the fast tank}
  b: {description: the slow tank}
parameters:
  fast-time: {value: 6m}
  slow-time: {value: 2h}
stocks:
  fast: {unit: litres, initial: 10, system: a, sensor: {manual: true}}
  slow: {unit: litres, initial: 10, system: b, sensor: {manual: true}}
flows:
  fill: {to: fast, rate: 1, system: a}
  pass: {from: fast, to: slow, equation: stock.fast / fast-time, driven-by: [+stock.fast], system: a}
  drain: {from: slow, equation: stock.slow / slow-time, driven-by: [+stock.slow], system: b}
"""
NONLINEAR = TIMES.replace("equation: stock.slow / slow-time", "equation: stock.slow * stock.slow / slow-time")


def test_the_diagonal_is_exactly_what_time_constants_used(tmp_path, monkeypatch):
    spec = _spec(tmp_path, NONLINEAR)
    got = _spy(monkeypatch)
    ms = md.at_start(spec)
    assert ms.why is None and len(got) == 1
    taus = ex.time_constants(spec)
    assert len(got) == 2
    (_, J), (st, _) = got
    for s in ("fast", "slow"):
        assert -J[(s, s)] == st.diag[s]
        assert 1.0 / (-J[(s, s)]) == taus[f"stock.{s}"]
    assert J[("slow", "slow")] != -0.1                              # the nonlinear drain: 2·10/2h, plus the step's share


GROWS = """
name: grows
parameters:
  hour: {value: 1h}
stocks:
  x: {unit: litres, initial: 10, sensor: {manual: true}}
flows:
  more: {to: x, equation: stock.x / hour, driven-by: [+stock.x]}
"""


def test_rates_is_unchanged_by_the_shared_jacobian(tmp_path):
    for text in (PAIR, NONLINEAR, GROWS):                           # GROWS: an own link above 0, its drain 0
        spec = _spec(tmp_path, text, text.split()[1])
        pl = sim.plan(spec)
        st, state = ex._at_start(spec, pl, ex.Condition("usual", "as usual", usual=True), None)
        st.evaluate()
        J, faulted = st.jacobian(state)
        bound = st.rates(state)
        live = list(state)
        assert not faulted and set(J) == {(i, j) for i in live for j in live}
        assert bound == max(sum(abs(J[(i, j)]) for j in live) for i in live)
        assert st.diag == {i: max(0.0, -J[(i, i)]) for i in live}
        assert st.coupling == max((sum(abs(J[(i, j)]) for j in live if j != i) for i in live), default=0.0)


def test_a_growing_mode_is_said_to_grow(tmp_path):
    spec = _spec(tmp_path, GROWS)
    (m,) = md.at_start(spec).modes
    assert m.value == pytest.approx(1.0, rel=1e-6) and m.links[("stock.x", "stock.x")] == pytest.approx(1.0, rel=1e-6)
    assert "λ 1/h (grows, e-folding every 1h): stock.x (its own) ε 1.00; most in stock.x" in explain(spec)


def test_explain_system_lists_the_modes_most_in_it(tmp_path):
    spec = _spec(tmp_path, TIMES)
    ms = md.at_start(spec)
    assert {m.most_in for m in ms.modes} == {"stock.fast", "stock.slow"}
    a, b = explain(spec, "system.a"), explain(spec, "system.b")
    assert "λ -10/h" in a and "λ -0.5/h" not in a, a
    assert "λ -0.5/h" in b and "λ -10/h" not in b, b


CHECK = """
import contextlib, io, sys
from ergostat.cli import main
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        main(["-C", sys.argv[1], sys.argv[2]])
    except SystemExit:
        pass
print("ergostat.numbers.modes" in sys.modules, "ergostat.numbers.extremes" in sys.modules)
"""


def test_check_never_imports_modes(tmp_path):
    _spec(tmp_path, TIMES, "times")
    shutil.copytree(ROOT / "examples" / "first-loop", tmp_path / "first-loop")

    def run(d: str, what: str) -> list[str]:
        out = subprocess.run([sys.executable, "-I", "-c", CHECK, str(tmp_path / d), what], capture_output=True,
                             text=True, timeout=120, cwd=tmp_path)
        assert out.returncode == 0, out.stderr
        return out.stdout.split()
    assert run("times", "check") == ["False", "True"]                # it worked out time constants, and no modes
    assert run("first-loop", "check")[0] == "False"
    assert run("first-loop", "explain")[0] == "False"
    assert run("times", "explain")[0] == "True"                      # the probe can see it when it is imported
