"""A loop as a linear system: the process identified (first order plus dead time, or an integrator
plus dead time), the controller as its block says it is, and what follows from the two: the step
response of each, the frequency response (Bode), and the stability margins (Åström & Murray,
*Feedback Systems*, ch. 9-11; Skogestad & Postlethwaite, ch. 2).

Time is in seconds here, frequency in rad/s. A process is a dict:

- ``{"form": "fopdt", "K": gain, "tau": s, "theta": s}``: P(s) = K e^(−θs) / (τs + 1);
- ``{"form": "integrating", "K": gain per second, "theta": s}``: P(s) = K e^(−θs) / s.

A controller is a dict too:

- ``{"form": "I", "g": step per unit of error, "T": s}``: integral action sampled every T, written as
  the blocks view writes it, C(z) = g / (z − 1) (u_(k+1) = u_k + g e_k);
- ``{"form": "PI", "Kc": gain, "Ti": s, "T": s or None}`` and ``{"form": "P", "Kc": gain, "T": ...}``:
  continuous laws, through a zero-order hold when the block runs every T.

A controller run every T acts through its sampler and hold: seen from the continuous loop, its
frequency response times (1 − e^(−jωT)) / (jωT), valid below the Nyquist frequency π/T."""

from __future__ import annotations

import cmath
import math

MAX_STEPS = 40000


def process_at(p: dict, w: float) -> complex:
    s = 1j * w
    delay = cmath.exp(-s * p.get("theta", 0.0))
    if p["form"] == "integrating":
        return p["K"] * delay / s
    return p["K"] * delay / (p["tau"] * s + 1)


def hold_at(T: float | None, w: float) -> complex:
    """The sampler and zero-order hold of a block run every T, as the continuous loop sees them."""
    if not T:
        return 1.0 + 0j
    x = 1j * w * T
    return (1 - cmath.exp(-x)) / x


def controller_at(c: dict, w: float) -> complex:
    s = 1j * w
    T = c.get("T")
    if c["form"] == "I":
        z = cmath.exp(s * T)
        return c["g"] / (z - 1) * hold_at(T, w)
    if c["form"] == "PI":
        return c["Kc"] * (1 + 1 / (c["Ti"] * s)) * hold_at(T, w)
    return c["Kc"] * hold_at(T, w)


def nyquist(c: dict | None) -> float:
    T = (c or {}).get("T")
    return math.pi / T if T else math.inf


def grid(p: dict, c: dict | None = None, n: int = 240) -> list[float]:
    """Frequencies to draw: from well below the slowest corner to the Nyquist frequency (or well past
    the fastest), evenly on a log scale."""
    slow = max(p.get("tau") or 0.0, p.get("theta") or 0.0, (c or {}).get("Ti") or 0.0, (c or {}).get("T") or 0.0, 1e-3)
    fast = min([x for x in (p.get("tau"), p.get("theta"), (c or {}).get("T")) if x] or [slow])
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
    loop's T = L/(1 + L): magnitude (as a ratio, drawn on a log axis) and phase (degrees)."""
    ws = grid(p, c, n)
    P = [process_at(p, w) for w in ws]
    out = {"w": ws, "process": {"mag": [abs(x) for x in P], "phase": _unwrapped(P)}}
    if c is not None:
        L = [controller_at(c, w) * x for w, x in zip(ws, P, strict=True)]
        Tc = [x / (1 + x) for x in L]
        out["loop"] = {"mag": [abs(x) for x in L], "phase": _unwrapped(L)}
        out["closed"] = {"mag": [abs(x) for x in Tc], "phase": _unwrapped(Tc)}
        out["nyquist"] = nyquist(c) if c.get("T") else None
    return out


def margins(p: dict, c: dict, n: int = 1200) -> dict:
    """Gain margin (how much more gain before it oscillates without end), phase margin and delay
    margin (how much more dead time), and the peak of the sensitivity Ms = max |1/(1 + L)|: the
    textbooks' robustness numbers (Åström & Murray §10.3; Skogestad's SIMC aims at Ms ≈ 1.6-1.7)."""
    ws = grid(p, c, n)
    L = [controller_at(c, w) * process_at(p, w) for w in ws]
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
    stable = closed_stable(p, c)
    return {"gain_margin": gm, "phase_margin": pm, "crossover": wc, "phase_crossover": w180,
            "delay_margin": dm, "ms": ms, "stable": stable}


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
    over each small step), its dead time a delay line, the controller sampled every T (or every
    small step when it is continuous). With the overshoot, the settling time (into 2% for good)
    and the rise time (10% to 90%)."""
    th = p.get("theta", 0.0)
    T = c.get("T") or 0.0
    tau = p.get("tau") or 0.0
    scale = max(th + tau, T, 1e-3)
    t_end = t_end or max(20 * scale, 40 * T, 10 * (c.get("Ti") or 0.0))
    dt = min(x for x in (T / 8 if T else None, tau / 20 if tau else None, th / 10 if th else None, t_end / 2000) if x)
    steps = min(MAX_STEPS, int(t_end / dt) + 1)
    dt = t_end / (steps - 1)
    lag = int(round(th / dt))
    buf = [0.0] * lag                                # what u was θ ago: popped as each new u goes in
    a = math.exp(-dt / tau) if p["form"] == "fopdt" else None
    x = 0.0
    u = nxt = 0.0
    integ = 0.0
    every = max(1, int(round(T / dt))) if T else 1
    ts, ys, us = [], [], []
    stride = max(1, steps // n)
    blew = False
    for k in range(steps):
        y = x
        if k % every == 0:
            e = 1.0 - y
            if c["form"] == "I":
                u, nxt = nxt, nxt + c["g"] * e          # u_(k+1) = u_k + g e_k: in effect from the next sample
            elif c["form"] == "PI":
                h = (T or dt)
                integ += e * h
                u = c["Kc"] * (e + integ / c["Ti"])
            else:
                u = c["Kc"] * e
        buf.append(u)
        ud = buf.pop(0)
        if p["form"] == "integrating":
            x = x + p["K"] * ud * dt
        else:
            x = a * x + (1 - a) * p["K"] * ud
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


def closed_stable(p: dict, c: dict) -> bool:
    """Whether the closed loop settles: simulated for a hundred of its slowest times, it neither blows
    up nor swings as much at the end as it did early on."""
    scale = max(p.get("theta", 0.0) + (p.get("tau") or 0.0), c.get("T") or 0.0, c.get("Ti") or 0.0, 1e-3)
    st = closed_step(p, c, t_end=100 * scale, n=800)
    if st.get("unstable"):
        return False
    ys = st["y"]
    q = len(ys) // 4
    tail, head = ys[-q:], ys[q:2 * q]
    swing = max(tail) - min(tail)
    return swing < 1e-3 or swing < 0.5 * (max(head) - min(head))
