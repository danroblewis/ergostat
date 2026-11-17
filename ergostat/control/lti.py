"""A loop as a linear system: the process identified (first order plus dead time, or an integrator
plus dead time), the controller as its block says it is, and what follows from the two: the step
response of each, the frequency response (Bode), and the stability margins (Åström & Murray,
*Feedback Systems*, ch. 9-11; Åström & Wittenmark, *Computer-Controlled Systems*, ch. 2, 3 and 8;
Skogestad & Postlethwaite, ch. 2 and 7).

Time is in seconds here, frequency in rad/s. A process is a dict:

- ``{"form": "fopdt", "K": gain, "tau": s, "theta": s}``: P(s) = K e^(−θs) / (τs + 1);
- ``{"form": "integrating", "K": gain per second, "theta": s}``: P(s) = K e^(−θs) / s.

A controller is a dict too:

- ``{"form": "I", "g": step per unit of error, "T": s}``: integral action in velocity form, run every
  T and acting at once on the error it has just read: u_k = u_(k−1) + g e_k, C(z) = g z / (z − 1);
- ``{"form": "PI", "Kc": gain, "Ti": s, "T": s}``: PI in velocity form, u_k = u_(k−1) + Kc (e_k −
  e_(k−1)) + Kc (T/τI) e_k; with ``T`` None, the continuous PI;
- ``{"form": "P", "Kc": gain, "T": ...}``: u_k = Kc e_k.

Any of them may carry ``delay``: the controller's own delay, how old the reading it acts on is plus
how long its run takes before the move is made (Åström & Wittenmark §8.3, the computational delay).
It adds to the process's dead time; it is never taken as a whole period.

A controller run every T is analysed exactly in discrete time: the process sampled through the
zero-order hold (its dead time split into whole periods and a fraction, the modified z-transform),
L(z) = C(z) P(z) evaluated on the unit circle up to the Nyquist frequency π/T, and the closed loop
stable when every root of 1 + L(z) = 0 lies inside the unit circle (the Schur–Cohn test). A
continuous controller is judged by the Nyquist criterion on L(jω): with no open-loop poles in the
right half-plane, stable when the gain margin is past 1 and the phase margin past 0.

What a block does that is not linear (a dead band on the error, a setting rounded to its
resolution, a clamp at its limits) is left out of the linear numbers and said beside them
(``nonlinear``)."""

from __future__ import annotations

import cmath
import math

MAX_STEPS = 40000
MAX_ORDER = 800                     # past this many periods of delay, the Nyquist criterion instead of the roots


def effective(p: dict, c: dict | None) -> dict:
    """The process as the controller sees it: its dead time and the controller's own delay."""
    d = (c or {}).get("delay") or 0.0
    return {**p, "theta": (p.get("theta") or 0.0) + d} if d else p


def process_at(p: dict, w: float) -> complex:
    s = 1j * w
    delay = cmath.exp(-s * p.get("theta", 0.0))
    if p["form"] == "integrating":
        return p["K"] * delay / s
    return p["K"] * delay / (p["tau"] * s + 1)


# ---- discrete time: polynomials in q = z^(−1), lowest power first

def _mul(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def _add(a: list[float], b: list[float]) -> list[float]:
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else 0.0) + (b[i] if i < len(b) else 0.0) for i in range(n)]


def _at(poly: list[float], q: complex) -> complex:
    v = 0j
    for x in reversed(poly):
        v = v * q + x
    return v


def sampled(p: dict, T: float) -> tuple[list[float], list[float]]:
    """The process seen from a zero-order hold and a sampler every T, exactly: (numerator,
    denominator) in q. Its dead time θ = dT + εT, 0 ≤ ε < 1, delays the input by d whole periods and
    splits each period's input over two samples (Åström & Wittenmark §2.3)."""
    th = max(p.get("theta") or 0.0, 0.0)
    d = int(th // T)
    eps = th / T - d
    if eps > 1 - 1e-9:
        d, eps = d + 1, 0.0
    if p["form"] == "integrating":
        b0, b1 = p["K"] * T * (1 - eps), p["K"] * T * eps
        den = [1.0, -1.0]
    else:
        a = math.exp(-T / p["tau"])
        a1 = math.exp(-(1 - eps) * T / p["tau"])
        b0, b1 = p["K"] * (1 - a1), p["K"] * (a1 - a)
        den = [1.0, -a]
    num = [0.0] * (d + 1) + [b0, b1]
    return num, den


def controller_poly(c: dict) -> tuple[list[float], list[float]]:
    """A sampled controller's law as (numerator, denominator) in q."""
    if c["form"] == "I":
        return [c["g"]], [1.0, -1.0]
    if c["form"] == "PI":
        return [c["Kc"] * (1 + c["T"] / c["Ti"]), -c["Kc"]], [1.0, -1.0]
    return [c["Kc"]], [1.0]


def controller_at(c: dict, w: float) -> complex:
    """The controller's frequency response: C(e^(jωT)) for a sampled one, C(jω) for a continuous one."""
    T = c.get("T")
    if T:
        num, den = controller_poly(c)
        q = cmath.exp(-1j * w * T)
        return _at(num, q) / _at(den, q)
    s = 1j * w
    if c["form"] == "I":
        return c.get("Ki", c.get("g", 0.0)) / s
    if c["form"] == "PI":
        return c["Kc"] * (1 + 1 / (c["Ti"] * s))
    return c["Kc"] + 0j


def loop_at(p: dict, c: dict, w: float) -> complex:
    """The loop opened, L = C P, at ω: in discrete time for a sampled controller."""
    pe = effective(p, c)
    T = c.get("T")
    if T:
        num, den = sampled(pe, T)
        q = cmath.exp(-1j * w * T)
        return controller_at(c, w) * _at(num, q) / _at(den, q)
    return controller_at(c, w) * process_at(pe, w)


def characteristic(p: dict, c: dict) -> list[float]:
    """The closed loop's characteristic polynomial in q, Dc Dp + Nc Np (sampled controllers)."""
    nc, dc = controller_poly(c)
    np_, dp = sampled(effective(p, c), c["T"])
    return _add(_mul(dc, dp), _mul(nc, np_))


def schur_stable(a: list[float]) -> bool:
    """Whether every root z of Σ a_i z^(−i) = 0 lies inside the unit circle (Schur–Cohn): the
    polynomial in z has a_0 leading and a_n constant; each step takes out the reflection
    coefficient k = a_n/a_0, which must be inside (−1, 1)."""
    c = list(a)
    while len(c) > 1 and abs(c[-1]) < 1e-15 * max(abs(x) for x in c):
        c.pop()                                    # a zero root (a pure delay's): inside
    while len(c) > 1:
        if c[0] == 0:
            return False
        k = c[-1] / c[0]
        if abs(k) >= 1 - 1e-12:
            return False
        c = [(c[i] - k * c[-1 - i]) for i in range(len(c) - 1)]
    return True


def nyquist(c: dict | None) -> float:
    T = (c or {}).get("T")
    return math.pi / T if T else math.inf


def grid(p: dict, c: dict | None = None, n: int = 240) -> list[float]:
    """Frequencies to draw: from well below the slowest corner to the Nyquist frequency (or well past
    the fastest), evenly on a log scale."""
    th = (p.get("theta") or 0.0) + ((c or {}).get("delay") or 0.0)
    slow = max(p.get("tau") or 0.0, th, (c or {}).get("Ti") or 0.0, (c or {}).get("T") or 0.0, 1e-3)
    fast = min([x for x in (p.get("tau"), th, (c or {}).get("T")) if x] or [slow])
    lo = 0.01 / slow
    hi = min(nyquist(c) * 0.999, 30.0 / max(fast, 1e-3))
    hi = max(hi, lo * 100)
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def _unwrapped(vals: list[complex]) -> list[float]:
    """Phases in degrees, continuous: a delay's phase falls without bound, never wrapped back."""
    out, last = [], None
    for v in vals:
        ph = math.degrees(cmath.phase(v))
        if last is not None:
            while ph - last > 180:
                ph -= 360
            while ph - last < -180:
                ph += 360
        out.append(ph)
        last = ph
    return out


def bode(p: dict, c: dict | None = None, n: int = 240) -> dict:
    """The process's frequency response, and with a controller the loop's L = CP and the closed
    loop's T = L/(1 + L): magnitude (as a ratio, drawn on a log axis) and phase (degrees). A sampled
    loop's L is the discrete one, up to the Nyquist frequency."""
    ws = grid(p, c, n)
    P = [process_at(p, w) for w in ws]
    out = {"w": ws, "process": {"mag": [abs(x) for x in P], "phase": _unwrapped(P)}}
    if c is not None:
        L = [loop_at(p, c, w) for w in ws]
        Tc = [x / (1 + x) for x in L]
        out["loop"] = {"mag": [abs(x) for x in L], "phase": _unwrapped(L)}
        out["closed"] = {"mag": [abs(x) for x in Tc], "phase": _unwrapped(Tc)}
        out["nyquist"] = nyquist(c) if c.get("T") else None
    return out


def margins(p: dict, c: dict, n: int = 1200) -> dict:
    """Gain margin (how much more gain before it oscillates without end), phase margin and delay
    margin (how much more dead time), and the peak of the sensitivity Ms = max |1/(1 + L)|: the
    textbooks' robustness numbers (Åström & Murray §10.3: Ms between 1.2 and 2; Skogestad's SIMC aims
    at Ms ≈ 1.6-1.7)."""
    ws = grid(p, c, n)
    L = [loop_at(p, c, w) for w in ws]
    mag = [abs(x) for x in L]
    ph = _unwrapped(L)
    wc = gm = w180 = pm = None
    for i in range(1, len(ws)):
        if wc is None and (mag[i - 1] - 1) * (mag[i] - 1) <= 0 and mag[i - 1] != mag[i]:
            f = (1 - mag[i - 1]) / (mag[i] - mag[i - 1])
            wc = ws[i - 1] * (ws[i] / ws[i - 1]) ** f
            pm = 180 + (ph[i - 1] + f * (ph[i] - ph[i - 1]))
        if w180 is None and (ph[i - 1] + 180) * (ph[i] + 180) <= 0 and ph[i - 1] != ph[i]:
            f = (-180 - ph[i - 1]) / (ph[i] - ph[i - 1])
            w180 = ws[i - 1] * (ws[i] / ws[i - 1]) ** f
            m180 = mag[i - 1] * (mag[i] / mag[i - 1]) ** f if mag[i - 1] > 0 else 0
            gm = 1 / m180 if m180 > 0 else math.inf
    ms = max(abs(1 / (1 + x)) for x in L)
    dm = math.radians(pm) / wc if pm is not None and wc and pm > 0 else None
    return {"gain_margin": gm, "phase_margin": pm, "crossover": wc, "phase_crossover": w180,
            "delay_margin": dm, "ms": ms, "stable": _stable(p, c, gm, pm)}


def _stable(p: dict, c: dict, gm: float | None, pm: float | None) -> bool:
    """Whether the closed loop settles: for a sampled controller, the roots of its characteristic
    polynomial (Schur–Cohn); for a continuous one, or a delay too long for the roots, the Nyquist
    criterion on the margins (no open-loop poles in the right half-plane: the process is stable or
    integrating, the controller at most integrating)."""
    if c.get("T"):
        a = characteristic(p, c)
        if len(a) <= MAX_ORDER:
            return schur_stable(a)
    return (gm is None or gm > 1) and (pm is None or pm > 0)


def closed_stable(p: dict, c: dict) -> bool:
    return margins(p, c, n=600)["stable"]


def process_step(p: dict, t_end: float | None = None, n: int = 160) -> dict:
    """The process's response to a unit step in u at 0."""
    th = p.get("theta", 0.0)
    if t_end is None:
        t_end = th + (5 * p["tau"] if p["form"] == "fopdt" else 5 * max(th, 1.0))
        t_end = max(t_end, 1e-3)
    ts = [t_end * i / (n - 1) for i in range(n)]
    ys = []
    for t in ts:
        if t <= th:
            ys.append(0.0)
        elif p["form"] == "integrating":
            ys.append(p["K"] * (t - th))
        else:
            ys.append(p["K"] * (1 - math.exp(-(t - th) / p["tau"])))
    return {"t": ts, "y": ys}


def closed_step(p: dict, c: dict, t_end: float | None = None, n: int = 200) -> dict:
    """The closed loop's response to a unit step in r at 0, simulated: the process continuous (exact
    over each small step), its dead time and the controller's own delay a delay line, the controller
    sampled every T and acting at once (or every small step when it is continuous). With the
    overshoot, the settling time (into 2% for good) and the rise time (10% to 90%)."""
    pe = effective(p, c)
    th = pe.get("theta", 0.0)
    T = c.get("T") or 0.0
    tau = pe.get("tau") or 0.0
    scale = max(th + tau, T, 1e-3)
    t_end = t_end or max(20 * scale, 40 * T, 10 * (c.get("Ti") or 0.0))
    dt = min(x for x in (T / 8 if T else None, tau / 20 if tau else None, th / 10 if th else None, t_end / 2000) if x)
    steps = min(MAX_STEPS, int(t_end / dt) + 1)
    dt = t_end / (steps - 1)
    lag = int(round(th / dt))
    buf = [0.0] * lag                                # what u was θ ago: popped as each new u goes in
    a = math.exp(-dt / tau) if pe["form"] == "fopdt" else None
    x = 0.0
    u = 0.0
    integ = 0.0
    e_last = 0.0
    every = max(1, int(round(T / dt))) if T else 1
    ts, ys, us = [], [], []
    stride = max(1, steps // n)
    blew = False
    for k in range(steps):
        y = x
        if k % every == 0:
            e = 1.0 - y
            if T:                                    # velocity form, acting on the error it has just read
                if c["form"] == "I":
                    u = u + c["g"] * e
                elif c["form"] == "PI":
                    u = u + c["Kc"] * (e - e_last) + c["Kc"] * T / c["Ti"] * e
                else:
                    u = c["Kc"] * e
                e_last = e
            elif c["form"] == "PI":
                integ += e * dt
                u = c["Kc"] * (e + integ / c["Ti"])
            elif c["form"] == "I":
                integ += e * dt
                u = c.get("Ki", 0.0) * integ
            else:
                u = c["Kc"] * e
        buf.append(u)
        ud = buf.pop(0)
        if pe["form"] == "integrating":
            x = x + pe["K"] * ud * dt
        else:
            x = a * x + (1 - a) * pe["K"] * ud
        if k % stride == 0:
            ts.append(k * dt)
            ys.append(y)
            us.append(u)
        if abs(y) > 1e6:
            blew = True
            break
    out = {"t": ts, "y": ys, "u": us}
    out.update(step_numbers(ts, ys, 1.0) if not blew else {"unstable": True})
    return out


def step_numbers(ts: list[float], ys: list[float], final: float, band: float = 0.02) -> dict:
    """Overshoot (past the final value, as a share of it), settling time (the last time it was
    outside the band around the final value) and rise time (10% to 90% of the final value)."""
    if not ts or not final:
        return {}
    peak = max(ys) if final > 0 else min(ys)
    over = max(0.0, (peak - final) / final)
    settle = None
    for t, y in zip(ts, ys, strict=True):
        if abs(y - final) > band * abs(final):
            settle = t
    t10 = next((t for t, y in zip(ts, ys, strict=True) if y / final >= 0.1), None)
    t90 = next((t for t, y in zip(ts, ys, strict=True) if y / final >= 0.9), None)
    settled = abs(ys[-1] - final) <= band * abs(final)
    return {"overshoot": over, "settling": settle if settled else None, "rise": (t90 - t10) if t10 is not None and
            t90 is not None else None, "settled": settled}


# ---- how sure: the margins over what the process could be

def corners(p: dict, se: dict, k: float = 2.0) -> list[dict] | None:
    """The process at the corners of its uncertainty: K ± kσ, θ + kσ (a longer delay is the danger)
    and τ ± kσ, each kept positive. None when K's sign is not told apart (K − kσ past 0)."""
    K, sK = p["K"], se.get("K") or 0.0
    if sK and abs(K) - k * sK <= 0:
        return None
    sgn = 1 if K > 0 else -1
    Ks = sorted({K, sgn * (abs(K) - k * sK), sgn * (abs(K) + k * sK)})
    ths = sorted({p.get("theta") or 0.0, (p.get("theta") or 0.0) + k * (se.get("theta") or 0.0)})
    taus = [None]
    if p["form"] == "fopdt":
        st = se.get("tau") or 0.0
        taus = sorted({p["tau"], max(p["tau"] - k * st, 0.05 * p["tau"]), p["tau"] + k * st})
    return [{**p, "K": a, "theta": b, **({"tau": c} if c is not None else {})} for a in Ks for b in ths for c in taus]


def robust(p: dict, c: dict, se: dict, k: float = 2.0) -> dict:
    """The worst margins over the process's uncertainty (Skogestad & Postlethwaite ch. 7): the least
    gain and phase margin, the largest Ms, and whether every corner is stable."""
    cs = corners(p, se, k)
    if cs is None:
        return {"known": False, "why": "the record does not tell the sign of K apart (K ± 2σ spans 0): the margins cannot be bounded"}
    worst = {"gain_margin": math.inf, "phase_margin": math.inf, "ms": 0.0, "stable": True}
    at = None
    for q in cs:
        m = margins(q, c, n=400)
        if not m["stable"]:
            worst["stable"] = False
            at = at or q
        if m["gain_margin"] is not None and m["gain_margin"] < worst["gain_margin"]:
            worst["gain_margin"] = m["gain_margin"]
            at = q if worst["stable"] else at
        if m["phase_margin"] is not None and m["phase_margin"] < worst["phase_margin"]:
            worst["phase_margin"] = m["phase_margin"]
        worst["ms"] = max(worst["ms"], m["ms"])
    return {"known": True, **{x: (None if v == math.inf else v) for x, v in worst.items()}, "worst": at, "k": k,
            "corners": len(cs)}


# ---- what the linear numbers leave out

def nonlinear(p: dict, c: dict, m: dict) -> list[str]:
    """What the block does that is not linear, and what that means for the loop (describing
    functions, Åström & Hägglund, *Advanced PID Control*, §3.5 and ch. 7)."""
    out = []
    db = c.get("deadband")
    if db:
        out.append(f"its dead band (±{db:.3g} of error, where it does not move) is left out of the linear numbers: inside it the "
                   "loop is open, so y may rest anywhere within ±dead band of r; a dead zone's describing function is at most 1, "
                   "so with the loop stable it adds no limit cycle")
    res = c.get("resolution")
    if res:
        gm = m.get("gain_margin")
        lim = 4 / math.pi
        cyc = gm is not None and gm < lim
        out.append(f"its setting is rounded to steps of {res:.3g}: a quantizer's describing function peaks at 4/π ≈ 1.27, so "
                   + (f"with a gain margin of {gm:.3g} a limit cycle of about one step is predicted"
                      if cyc else "with a gain margin past it, no limit cycle is predicted from the rounding"))
    lim = c.get("limits")
    if lim:
        out.append(f"its setting is clamped to [{lim[0]:g}, {lim[1]:g}]: in velocity form the clamp does not wind up, "
                   "but at a limit the loop is open")
    return out
