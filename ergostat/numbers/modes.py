"""The stocks' modes at the model's start and each link's eigenvalue elasticity (Forrester 1982; Kampmann 1996/2012;
Saleh, Oliva, Kampmann and Davidsen 2010): the eigenvalues of the stocks' Jacobian, from one evaluation of the
equations at the start (the same point and the same forward differences ``extremes.time_constants`` uses), no run.

Each entry a_ij of the Jacobian (∂ net inflow of stock i / ∂ level of stock j, per hour) is a link: off the diagonal
"stock.j → stock.i", on it the stock's own drain or growth. A mode λ's elasticity to a link is ε_ij = (a_ij/λ)·∂λ/∂a_ij,
with ∂λ/∂a_ij = w_i v_j / (wᵀv), v and w its right and left eigenvectors; over all links Σε = 1. The eigenvalues come
from the Hessenberg form by complex single-shift QR (Wilkinson's shift), the vectors by inverse iteration. Only the
stocks are states here: a delay's stages are not. Where a number would not mean anything (λ = 0, a repeated eigenvalue,
a fault in the equations, a non-finite entry, QR that does not converge) the reason is said instead."""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

MOST = 40                 # stocks at most: pure-Python eigenvectors are O(n³) a mode
ITERS = 30                # QR iterations a stock, in all: 30·n
SHOWN = 8                 # modes listed by explain
EPS = 2.220446049250313e-16
HEAD = ("Modes at the start (eigenvalues of the stocks' Jacobian, one evaluation of the equations, no run; a delay's "
        "stages are not states here: its time is in time-scales):")
NO_FEEDBACK = "the stocks do not feed back through any equation: no modes"
ZERO = "no decay (a conserved quantity, or a stock nothing drains): elasticities are not defined at λ = 0"
REPEATED = "repeated eigenvalue: not differentiable there; elasticities not given"
LOST = "eigenvector not found"


@dataclass
class Mode:
    value: complex                                        # λ, per hour (one of a conjugate pair: Im > 0)
    tau_h: float | None
    period_h: float | None
    links: dict[tuple[str, str], complex] | None          # (row ref, column ref) → ε, strongest first
    why: str | None
    most_in: str | None


@dataclass
class Modes:
    why: str | None
    stocks: list[str]
    modes: list[Mode]


def _norm(A) -> float:
    return max((sum(abs(x) for x in row) for row in A), default=0.0)


def _hessenberg(A: list[list[complex]]) -> list[list[complex]]:
    """A similar upper Hessenberg matrix, by elimination with partial pivoting (EISPACK's elmhes), in place."""
    n = len(A)
    for m in range(1, n - 1):
        p = max(range(m, n), key=lambda i: abs(A[i][m - 1]))
        if p != m:
            A[p], A[m] = A[m], A[p]
            for r in A:
                r[p], r[m] = r[m], r[p]
        x = A[m][m - 1]
        for i in range(m + 1, n):
            y = A[i][m - 1]
            if not x or not y:
                continue
            y /= x
            for j in range(m - 1, n):
                A[i][j] -= y * A[m][j]
            for r in A:
                r[m] += y * r[i]
            A[i][m - 1] = 0j
    return A


def _step(H, lo: int, hi: int, mu: complex) -> None:
    """One shifted QR step on the active block lo..hi: H − μI = QR (Givens), H ← RQ + μI."""
    for k in range(lo, hi + 1):
        H[k][k] -= mu
    rot = []
    for k in range(lo, hi):
        x, y = H[k][k], H[k + 1][k]
        r = math.hypot(abs(x), abs(y))
        c, s = (x / r, y / r) if r else (1 + 0j, 0j)
        rot.append((c, s))
        for j in range(k, hi + 1):
            p, q = H[k][j], H[k + 1][j]
            H[k][j], H[k + 1][j] = c.conjugate() * p + s.conjugate() * q, c * q - s * p
        H[k + 1][k] = 0j
    for k, (c, s) in zip(range(lo, hi), rot, strict=True):
        for i in range(lo, min(k + 2, hi) + 1):
            p, q = H[i][k], H[i][k + 1]
            H[i][k], H[i][k + 1] = p * c + q * s, q * c.conjugate() - p * s.conjugate()
    for k in range(lo, hi + 1):
        H[k][k] += mu


def _eigenvalues(H, most: int) -> list[complex] | None:
    """The eigenvalues of Hessenberg H (changed in place), or None when QR took more than ``most`` iterations."""
    hi, its, stuck, scale = len(H) - 1, 0, 0, _norm(H)
    out: list[complex] = []
    while hi >= 0:
        lo = hi
        while lo > 0 and abs(H[lo][lo - 1]) > EPS * ((abs(H[lo][lo]) + abs(H[lo - 1][lo - 1])) or scale):
            lo -= 1
        if lo == hi:
            out.append(H[hi][hi])
            hi, stuck = hi - 1, 0
            continue
        if its >= most:
            return None
        its, stuck = its + 1, stuck + 1
        a, b, c, d = H[hi - 1][hi - 1], H[hi - 1][hi], H[hi][hi - 1], H[hi][hi]
        r = cmath.sqrt((a - d) ** 2 / 4 + b * c)
        mu = min((a + d) / 2 + r, (a + d) / 2 - r, key=lambda m: abs(m - d))      # Wilkinson's shift
        if stuck % 10 == 0:                              # an exceptional shift, out of a cycle (EISPACK)
            mu = d + 0.75 * abs(c)
        _step(H, lo, hi, mu)
    return out


def vector(J, lam: complex, left: bool = False) -> list[complex] | None:
    """λ's right eigenvector (left: of Jᵀ, unconjugated), by 3 steps of inverse iteration shifted by
    δ = 1e-10·‖J‖∞; a pivot still exactly 0 is taken as 1e-14·‖J‖∞ (LAPACK's practice). None when the residual
    ‖Av − λv‖∞ stays above 1e-8·‖J‖∞·‖v‖∞."""
    n, norm = len(J), _norm(J)
    A = [list(r) for r in zip(*J, strict=True)] if left else [list(r) for r in J]
    M = [[complex(A[i][j]) - (lam + 1e-10 * norm if i == j else 0) for j in range(n)] for i in range(n)]
    perm = list(range(n))
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(M[i][k]))
        M[k], M[p], perm[k], perm[p] = M[p], M[k], perm[p], perm[k]
        if M[k][k] == 0:
            M[k][k] = complex(1e-14 * norm)
        for i in range(k + 1, n):
            f = M[i][k] = M[i][k] / M[k][k]
            for j in range(k + 1, n):
                M[i][j] -= f * M[k][j]
    x = [1 + 0j] * n
    for _ in range(3):
        y = [x[perm[i]] for i in range(n)]
        for i in range(n):
            y[i] -= sum(M[i][j] * y[j] for j in range(i))
        for i in reversed(range(n)):
            y[i] = (y[i] - sum(M[i][j] * y[j] for j in range(i + 1, n))) / M[i][i]
        big = max(y, key=abs)
        if not big or not cmath.isfinite(big):
            return None
        x = [v / big for v in y]
    if lam.imag == 0:
        x = [complex(v.real) for v in x]
    res = max(abs(sum(A[i][j] * x[j] for j in range(n)) - lam * x[i]) for i in range(n))
    return None if res > 1e-8 * norm * max(abs(v) for v in x) else x


def elasticities(J, lam: complex, w, v, refs: list[str]) -> tuple[dict[tuple[str, str], complex] | None, str | None]:
    """Each nonzero link's ε = a_ij·w_i·v_j / (λ·wᵀv), strongest |ε| first (to 9 decimals, then by name); None and
    why when wᵀv is too near 0 (a defective eigenvalue)."""
    wv = sum(a * b for a, b in zip(w, v, strict=True))
    if abs(wv) <= 1e-8 * math.sqrt(sum(abs(a) ** 2 for a in w)) * math.sqrt(sum(abs(b) ** 2 for b in v)):
        return None, REPEATED
    n = len(refs)
    got = {(refs[i], refs[j]): J[i][j] * w[i] * v[j] / (lam * wv) for i in range(n) for j in range(n) if J[i][j]}
    return dict(sorted(got.items(), key=lambda kv: (-round(abs(kv[1]), 9), kv[0]))), None


def _mode(J, lam: complex, others: list[complex], refs: list[str], norm: float) -> Mode:
    zero = norm == 0 or abs(lam) <= 1e-9 * norm
    lam = 0j if zero else lam
    slow = abs(lam.real) <= 1e-9 * max(1.0, norm)
    v = w = None
    if not zero:
        v, w = vector(J, lam), vector(J, lam, left=True)
    share = [abs(a * b) for a, b in zip(w, v, strict=True)] if v and w else []
    most = refs[max(range(len(refs)), key=lambda k: share[k])] if share and sum(share) > 0 else None
    links, why = None, ZERO if zero else None
    if why is None and any(abs(lam - x) <= 1e-6 * norm for x in others):
        why = REPEATED
    elif why is None and (v is None or w is None):
        why = LOST
    elif why is None:
        links, why = elasticities(J, lam, w, v, refs)
    return Mode(lam, None if slow else 1.0 / abs(lam.real), 2 * math.pi / lam.imag if lam.imag else None, links, why, most)


def _link(key: tuple[str, str]) -> str:
    i, j = key
    return f"{i} (its own)" if i == j else f"{j} → {i}"


def of_matrix(J, refs: list[str]) -> Modes:
    """The modes of J (J[i][j] = ∂ net inflow of refs[i] / ∂ level of refs[j], per hour), slowest first."""
    n = len(refs)
    if not n:
        return Modes(NO_FEEDBACK, [], [])
    for i in range(n):
        for j in range(n):
            if not math.isfinite(J[i][j]):
                return Modes(f"{_link((refs[i], refs[j]))} is {J[i][j]}", list(refs), [])
    norm = _norm(J)
    lams = _eigenvalues(_hessenberg([[complex(x) for x in row] for row in J]), ITERS * n)
    if lams is None:
        return Modes(f"the QR iteration did not converge within {ITERS * n} iterations: no eigenvalues are given",
                     list(refs), [])
    lams = [complex(x.real) if abs(x.imag) <= 1e-9 * max(1.0, norm) else x for x in lams]
    got = [_mode(J, x, lams[:k] + lams[k + 1:], refs, norm) for k, x in enumerate(lams) if x.imag >= 0]
    return Modes(None, list(refs), sorted(got, key=lambda m: (abs(m.value.real), m.value.imag)))


def at_start(spec) -> Modes:
    """The model's modes at its start (the module's docstring); ``why`` instead of numbers that would mislead."""
    from . import extremes as ex
    from . import simulate as sim
    pl = sim.plan(spec)
    if len(pl.integrate) > MOST:
        return Modes(f"{len(pl.integrate)} stocks move by equations, more than {MOST}: modes are not worked out "
                     f"(pure-Python eigenvectors are O(n³) a mode)", [], [])
    st, state = ex._at_start(spec, pl, ex.Condition("usual", "with everything as usual", usual=True), None)
    live = [s for s in st.stocks if state.get(s) is not None]
    refs = [f"stock.{s}" for s in live]
    if not [s for s in st.felt if state.get(s) is not None]:
        return Modes(NO_FEEDBACK, refs, [])
    try:
        st.evaluate()
        bad = st.faults()
        J, faulted = st.jacobian(state) if not bad else ({}, [])
    except (ArithmeticError, ValueError) as e:
        return Modes(f"the equations fail at the start: {e}", refs, [])
    if bad:
        return Modes("the equations fault at the start: " + "; ".join(bad), refs, [])
    if faulted:
        return Modes("the equations fault when a stock is moved a little from the start (the difference step): "
                     + ", ".join(faulted) + ", each fault taken as 0", refs, [])
    return of_matrix([[J[(i, j)] for j in live] for i in live], refs)


def _h(hours: float) -> str:
    from ..durations import human
    return human(round(hours * 3600, 3))


def line(m: Mode) -> str:
    """One mode: λ per hour, its time constant (or growth) and period, its 3 strongest links, where it lives most."""
    lam = m.value
    v = "0" if lam == 0 else f"{lam.real:.3g}" + (f" ± {lam.imag:.3g}i" if lam.imag else "")
    when = ([f"grows, e-folding every {_h(m.tau_h)}" if lam.real > 0 else f"τ {_h(m.tau_h)}"] if m.tau_h else [])
    when += [f"period {_h(m.period_h)}"] if m.period_h else []
    if m.links is None:
        body = m.why
    else:
        body = "; ".join(f"{_link(k)} " + (f"ε {e.real:.2f}" if not lam.imag else f"|ε| {abs(e):.2f} ({e.real:.2f}{e.imag:+.2f}i)")
                         for k, e in list(m.links.items())[:3])
    return f"λ {v}/h" + (f" ({', '.join(when)})" if when else "") + f": {body}" + (f"; most in {m.most_in}" if m.most_in else "")


def said(ms: Modes, head: str = HEAD, keep=None, indent: str = "  ") -> list[str]:
    """The lines ``explain`` prints: up to SHOWN modes (those ``keep`` takes), slowest first; or why not."""
    if ms.why:
        return [f"{indent[2:]}Modes: not worked out: {ms.why}"]
    got = [m for m in ms.modes if keep is None or keep(m)]
    if not got:
        return []
    more = [f"{indent}and {len(got) - SHOWN} more"] if len(got) > SHOWN else []
    return [indent[2:] + head, *(indent + line(m) for m in got[:SHOWN]), *more]
