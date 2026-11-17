"""Suggested tuning, by Skogestad's SIMC rules (Skogestad, "Simple analytic rules for model reduction
and PID controller tuning", J. Process Control 13, 2003), from the process identified for a loop.

One choice, the closed-loop time constant τc; the rules' own default is τc = θ, "tight control" that
stays robust (gain margin about 3, phase margin about 60°, Ms about 1.6). A block run every T adds
T/2 to the dead time it sees (its sampler and hold).

- **PI** on P(s) = K e^(−θs)/(τs + 1): Kc = τ / (K (τc + θ)), τI = min(τ, 4 (τc + θ)).
- **PI** on an integrator, P(s) = k e^(−θs)/s (or a lag so long it acts as one, k = K/τ):
  Kc = 1 / (k (τc + θ)), τI = 4 (τc + θ).
- **I** only: the SIMC PI with τI = τ in the limit of a lag small beside the delay, the lag taken as
  delay (the half rule's coarse form, which errs on the safe side): C(s) = K_I/s,
  K_I = 1 / (K (τc + θ + τ)), with τc = θ + τ. Sampled every T as C(z) = g/(z − 1), g = K_I T.
- **P** only (a proportional block): Kc = τ / (K (τc + θ)), the PI's gain without its integral.

A suggestion is checked before it is offered: its margins and its closed-loop step are worked out
(lti.py) and shown beside those of the controller as it is."""

from __future__ import annotations

import math

from . import lti

TIGHT = 1.0        # τc as a multiple of the effective dead time: SIMC's own default


def effective_delay(p: dict, T: float | None) -> float:
    return p.get("theta", 0.0) + (T or 0.0) / 2


def simc(p: dict, form: str, T: float | None = None, tc: float | None = None) -> dict | None:
    """The SIMC controller of a form (I, PI, P) for a process, with τc (default: the effective dead
    time, at least a tenth of the lag) and why."""
    th = effective_delay(p, T)
    K = p["K"]
    if not K:
        return None
    if p["form"] == "integrating":
        tc = tc if tc is not None else max(th, 1e-3)
        if form == "PI":
            kc = 1 / (K * (tc + th))
            return {"form": "PI", "Kc": kc, "Ti": 4 * (tc + th), "T": T, "tc": tc,
                    "rule": "SIMC, integrating process: Kc = 1/(k(τc + θ)), τI = 4(τc + θ), τc = θ"}
        if form == "P":
            return {"form": "P", "Kc": 1 / (K * (tc + th)), "T": T, "tc": tc,
                    "rule": "SIMC, integrating process, P only: Kc = 1/(k(τc + θ)), τc = θ"}
        return None                                  # an I controller on an integrator cannot be stable
    tau = p["tau"]
    if form == "I":
        eff = th + tau
        tc = tc if tc is not None else eff
        ki = 1 / (K * (tc + eff))
        if not T:
            return None
        return {"form": "I", "g": ki * T, "Ki": ki, "T": T, "tc": tc,
                "rule": "SIMC, I only: K_I = 1/(K(τc + θ + τ)), τc = θ + τ; the lag taken as delay; g = K_I T"}
    tc = tc if tc is not None else max(th, 0.1 * tau)
    kc = tau / (K * (tc + th))
    if form == "P":
        return {"form": "P", "Kc": kc, "T": T, "tc": tc, "rule": "SIMC, P only: Kc = τ/(K(τc + θ)), τc = θ"}
    return {"form": "PI", "Kc": kc, "Ti": min(tau, 4 * (tc + th)), "T": T, "tc": tc,
            "rule": "SIMC: Kc = τ/(K(τc + θ)), τI = min(τ, 4(τc + θ)), τc = θ"}


def judged(p: dict, c: dict) -> dict:
    """What a controller does with a process: margins and closed-loop step."""
    m = lti.margins(p, c)
    st = lti.closed_step(p, c, n=160)
    return {"margins": m, "step": st}


def worth(current: dict | None, new: dict, key: str = "g") -> bool:
    """A suggestion is a change worth making when it moves the gain by more than a fifth."""
    if current is None or current.get(key) in (None, 0):
        return True
    return abs(new[key] - current[key]) > 0.2 * abs(current[key])


def finite(x) -> float | None:
    return None if x is None or (isinstance(x, float) and (math.isinf(x) or math.isnan(x))) else x
