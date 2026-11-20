"""The AI pools, sized by measured risk against the owner's risk tolerance (docs/roadmap/overnight/pool-control.md;
the owner, 2026-11-20: start with one implementor, "the work from the first agent might come back awful"). Each
role's pool (implementor, reviewer) starts at 1 and lives in run/pools.json, with the implementor pool's history (what
the evidence is attributed to); the blocks' `pool:` in the model is only its most ([pools] in dev/factory.toml, at
most HARD), and the engine's gate and each run hold the rest to the pool now. The risk itself is dev/bin/risk.py.

    pools.py read WHAT        a sensor: implementor, reviewer (the pools now), risk, bound, over (the bound less the
                              tolerance: interventions a day at the implementor pool now), target,
                              factory-interventions, escapes (counts)
    pools.py tune             the controller (a block): the target is the largest pool whose risk bound is within
                              risk-tolerance (dev/model/pools.yaml) and not above the demand (gaps ready, at fix or
                              building); a step up is asked as the gated action raise-pool once [pools] probation gaps
                              had a verdict since the last raise; down by one at once when the bound crosses the
                              tolerance (never for demand alone: an idle slot costs nothing). The reviewer pool follows
                              the implementor's, up to its most: up with an approved raise, down with each drop.
    pools.py raise ROLE FROM TO WHY   the action's command: TO only if the pool is still FROM, and (implementor) the
                              bound at TO still within the tolerance and the probation over; else it refuses
    pools.py set ROLE N WHY   by hand: set it (within 1 and its most)"""

from __future__ import annotations

import fcntl
import json
import sys
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
import fac  # noqa: E402
import risk  # noqa: E402

ROLES = ("implementor", "reviewer")
HARD = 8                                    # no pool above this, whatever [pools] says (each is AI sessions at once)
DEMAND = ("ready", "fix", "building")       # the implementor pool's work: waiting for it, and in its hands now


def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "pools.json"
    got = json.loads(p.read_text()) if p.exists() else {}
    return {"since": float(got.get("since") or 0), "raised_at": float(got.get("raised_at") or 0),
            "history": list(got.get("history") or []), **{r: int(got.get(r) or 1) for r in ROLES}}


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "pools.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


@contextmanager
def locked(cfg: dict):
    """Held across each read, decision and write of run/pools.json (the tuner's lowering, a raise, a set by hand)."""
    with open(fac.run_dir(cfg) / "pools.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def most(cfg: dict, role: str) -> int:
    return max(1, min(HARD, int(cfg.get("pools", {}).get(f"{role}_max", 1))))


def put(cfg: dict, st: dict, role: str, n: int) -> None:
    """The role's pool to n (within 1 and its most), its history and the times, saved. Call it under locked()."""
    n = max(1, min(int(n), most(cfg, role)))
    now = time.time()
    if n > st[role]:
        st["raised_at"] = now                       # the probation starts again
    st[role], st["since"] = n, now
    if role == "implementor":
        st["history"].append([now, n])
    save(cfg, st)


def cycle_hours(cfg: dict) -> float:
    """The measured cycle time; [pools] cycle_hours (short: more gaps a day, more risk) before any is measured."""
    import measure
    return measure.reading("cycle-hours") or float(cfg.get("pools", {}).get("cycle_hours", 2))


def measured(cfg: dict, st: dict, gaps: list[dict]) -> dict:
    """Everything a decision rests on, from the record: the risk table, the tolerance, the demand, the target."""
    ivs = fac.items("intervention")
    ev = risk.evidence(gaps, ivs, fac.items("upgrade"), st["history"])
    tab = risk.table(ev, most(cfg, "implementor"), cycle_hours(cfg))
    tol, demand = risk.tolerance(), sum(g["state"] in DEMAND for g in gaps)
    n = st["implementor"]
    return {"table": tab, "tolerance": tol, "demand": demand, "target": risk.target(tab, tol, demand),
            "now": tab.get(n) or tab[max(tab)], "since_raise": risk.processed_since(gaps, st["raised_at"]),
            "factory_interventions": sum(map(risk.factory_caused, ivs)), "escapes": sum(x[2] for x in ev.values())}


def probation(cfg: dict) -> int:
    return max(0, int(cfg.get("pools", {}).get("probation", 3)))


def lower(cfg: dict, st: dict, role: str, to: int, why: str, said: dict) -> None:
    """Down at once, ungated, with its event and its evidence. Call it under locked()."""
    moved = to - st[role]
    put(cfg, st, role, to)
    print(json.dumps({"out": f"flow.{role}-pool-steps", "moved": moved}), flush=True)
    fac.say("pool.lowered", f"pool/{role}", pool=st[role], why=why, lowered_at=time.time(), **said)


def tune(cfg: dict) -> int:
    gaps = fac.items("gap")
    with locked(cfg):
        st = state(cfg)
        m = measured(cfg, st, gaps)
        what, to, why = risk.step(st["implementor"], m["table"], m["tolerance"], m["demand"], m["since_raise"],
                                  probation(cfg))
        role = "implementor"
        said = {"risk": m["now"]["risk"], "risk_bound": m["now"]["bound"], "rates": m["now"]["rates"],
                "per_day": m["now"]["per_day"], "tolerance": m["tolerance"], "demand": m["demand"],
                "target": m["target"], "since_raise": m["since_raise"], "probation": probation(cfg)}
        if what == "lower":
            lower(cfg, st, role, to, why, said)
        follow = min(st["implementor"], most(cfg, "reviewer"))    # the reviewer pool follows the implementor's
        if st["reviewer"] > follow:
            lower(cfg, st, "reviewer", follow, f"the reviewer pool follows the implementor pool ({follow})", said)
        elif what is None and st["reviewer"] < follow and m["since_raise"] >= probation(cfg):
            what, role, to = "raise", "reviewer", st["reviewer"] + 1     # (an approved implementor raise brings it)
            why = f"the reviewer pool follows the implementor pool ({st['implementor']})"
    if what == "raise":                             # (outside the lock: an approval runs `raise`, which takes it)
        was = st[role]
        rc, _ = fac.act("raise-pool", key=f"{role}-{to}-{int(st['since'])}", role=role, was=str(was), to=str(to),
                        why=why)
        fac.say("pool.raise-asked", f"pool/{role}", pool=was, to=to, why=why,
                asked={0: "raised", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"), **said)
    for r in ROLES:
        fac.say("pool.measured", f"pool/{r}", pool=state(cfg)[r], most=most(cfg, r), decision=what or "hold",
                why=why, **said)
    return 0


def raise_pool(cfg: dict, role: str, was: int, to: int, why: str) -> int:
    """The approved raise, decided again under the lock: only if the pool is still what it was asked from (a lowering
    in between voids it), and for the implementor only if the risk bound at TO is still within the tolerance and the
    probation is over (an approval given late cannot raise into a crossed bound); the reviewer pool comes up with it.
    A reviewer raise only up to the implementor pool."""
    if role not in ROLES:
        raise SystemExit(f"no pool {role!r}: {', '.join(ROLES)}")
    with locked(cfg):
        st = state(cfg)
        if st[role] != was or to != was + 1:
            print(f"{role} pool is {st[role]}, not {was}: this raise to {to} is stale, nothing done", file=sys.stderr)
            return 1
        m = measured(cfg, st, fac.items("gap"))
        bound = (m["table"].get(to) or {}).get("bound", float("inf"))
        if role == "implementor" and (bound > m["tolerance"] or m["since_raise"] < probation(cfg)):
            print(f"no longer due: risk bound {bound}/day at {to} (tolerance {m['tolerance']:g}), {m['since_raise']} "
                  f"of {probation(cfg)} gaps since the last raise; nothing done", file=sys.stderr)
            return 1
        if role == "reviewer" and to > min(st["implementor"], most(cfg, role)):
            print(f"the reviewer pool follows the implementor pool ({st['implementor']}): nothing done", file=sys.stderr)
            return 1
        put(cfg, st, role, to)
        if role == "implementor" and st["reviewer"] < min(to, most(cfg, "reviewer")):
            put(cfg, st, "reviewer", st["reviewer"] + 1)
    print(f"{role} pool {state(cfg)[role]} ({why})")
    return 0


def set_pool(cfg: dict, role: str, n: int, why: str) -> int:
    if role not in ROLES:
        raise SystemExit(f"no pool {role!r}: {', '.join(ROLES)}")
    with locked(cfg):
        put(cfg, state(cfg), role, n)
    print(f"{role} pool {state(cfg)[role]} ({why})")
    return 0


def my_turn(cfg: dict, role: str, block: str, item: str) -> bool:
    """Whether this run's item is within the role's pool: the items its block's runs hold, by when their leases were
    taken, and this one among the first `pool` of them (so two runs taken at once never both go on)."""
    held = [g for g in fac.items("gap") if (g["fields"].get("lease") or {}).get("block") == block
            and (g["fields"].get("lease") or {}).get("holder")]
    order = sorted((float(g["fields"]["lease"].get("taken") or 0), g["id"]) for g in held)
    ids = [i for _, i in order]
    return item not in ids or ids.index(item) < state(cfg)[role]


READ = {"risk": lambda m: m["now"]["risk"], "bound": lambda m: m["now"]["bound"], "target": lambda m: m["target"],
        "over": lambda m: round(m["now"]["bound"] - m["tolerance"], 3),
        "factory-interventions": lambda m: m["factory_interventions"], "escapes": lambda m: m["escapes"]}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[0] == "read" and argv[1] in ROLES:
        print(state(cfg)[argv[1]])
    elif argv[0] == "read" and argv[1] in READ:
        print(READ[argv[1]](measured(cfg, state(cfg), fac.items("gap"))))
    elif argv[0] == "tune":
        return tune(cfg)
    elif argv[0] == "raise":
        return raise_pool(cfg, argv[1], int(argv[2]), int(argv[3]), " ".join(argv[4:]) or "approved")
    elif argv[0] == "set":
        return set_pool(cfg, argv[1], int(argv[2]), " ".join(argv[3:]) or "by hand")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
