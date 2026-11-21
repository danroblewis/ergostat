"""The AI pools, sized by measured risk against the owner's risk tolerance (docs/roadmap/overnight/pool-control.md;
the owner, 2026-11-20: start with one implementor, "the work from the first agent might come back awful"). Each
role's pool (implementor, reviewer) starts at 1 and lives in run/pools.json, with the implementor pool's history (what
the evidence is attributed to), read by the stocks implementor-pool and reviewer-pool. The blocks take their pools
from those stocks (`pool: {now: stock.implementor-pool, most: 9}`): the engine holds each block to the pool now at
every dispatch, never above its most ([pools] in dev/factory.toml sets the most this file allows, at most HARD). The
gates and each run (`my_turn`) also hold them to the machine's headroom. The risk itself is dev/bin/risk.py.

    pools.py read WHAT        a sensor: implementor, reviewer, batch (the pools now), risk, bound, over (the bound
                              less the tolerance: interventions a day at the implementor pool now), target,
                              factory-interventions, escapes (counts)
    pools.py tune             the controller (a block): the target is the largest pool whose risk bound is within
                              risk-tolerance (dev/model/pools.yaml) and not above the demand (gaps ready, at fix or
                              building); a step up is asked as the gated action raise-pool once [pools] probation gaps
                              had a verdict since the last raise; down by one at once when the bound crosses the
                              tolerance (never for demand alone: an idle slot costs nothing). The reviewer pool follows
                              the implementor's, up to its most: up with an approved raise, down with each drop.
    pools.py raise ROLE FROM TO WHY   the action's command: TO only if the pool is still FROM, and (implementor) the
                              bound at TO still within the tolerance and the probation over; else it refuses
    pools.py set ROLE N WHY   by hand: set it (within 1 and its most)

The merge queue's batch (`batch`: approved gaps it merges and tests together, dev/bin/queue.py) lives here too: [pools]
batch to start (1, a gap a run), at most [pools] batch_max and never past BATCH_MOST. The tuner asks to raise it by
one, the same gated action (`raise batch FROM TO`), while the goal queue-wait-short is off (dev/model/measures.yaml);
it is not lowered on risk (it changes how gaps are tested, not how many are built), only by hand (`set batch N`)."""

from __future__ import annotations

import fcntl
import json
import re
import sys
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
import fac  # noqa: E402

ROLES = ("implementor", "reviewer")
POOLS = (*ROLES, "batch")
HARD = 9                                    # no pool above this, whatever [pools] says (each is AI sessions at once)
DEMAND = ("ready", "fix", "building")       # the implementor pool's work: waiting for it, and in its hands now
BATCH_MOST = 4         # a batch of 4 with every merge failing is at most 8 suite runs (~1.5 h; the 3 h timeout
                       # also covers the lock and quiet-machine waits)


def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "pools.json"
    got = json.loads(p.read_text()) if p.exists() else {}
    batch = int(got.get("batch") or cfg.get("pools", {}).get("batch", 1))
    return {"since": float(got.get("since") or 0), "raised_at": float(got.get("raised_at") or 0),
            "history": list(got.get("history") or []), **{r: int(got.get(r) or 1) for r in ROLES},
            "batch": max(1, min(batch, most(cfg, "batch"))), "batch_since": float(got.get("batch_since") or 0)}


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
    n = max(1, min(HARD, int(cfg.get("pools", {}).get(f"{role}_max", 1))))
    return min(n, BATCH_MOST) if role == "batch" else n


WAIT_GOAL = re.compile(r"^\s*queue-wait-short:\s*$.*?^\s*hold:\s*\"<=\s*([\d.]+)\"\s*$\s*tolerance:\s*([\d.]+)",
                       re.M | re.S)


def wait_off(hours: float) -> str | None:
    """Why the goal queue-wait-short is off (its hold plus its tolerance passed), or None; None too when the goal
    cannot be read (raising the batch is the step that needs a reason)."""
    m = WAIT_GOAL.search((fac.HERE / "model" / "measures.yaml").read_text())
    if not m or hours <= float(m.group(1)) + float(m.group(2)):
        return None
    return f"queue wait {hours:g} h, over its goal of {m.group(1)} h (tolerance {m.group(2)})"


def tune_batch(cfg: dict, st: dict) -> None:
    """The queue's batch: measured (its size, the queue wait, merges per hour of the queue's running) and, while the
    queue wait goal is off, a raise of one asked of the coordinator."""
    import measure
    wait, rate = measure.reading("queue-wait-hours"), measure.reading("merges-per-hour")
    why = wait_off(wait)
    if why and st["batch"] < most(cfg, "batch"):
        to = st["batch"] + 1
        rc, said = fac.act("raise-pool", key=f"batch-{to}-{int(st.get('batch_since') or 0)}", role="batch",
                           was=str(st["batch"]), to=str(to), why=why)
        fac.say("pool.raise-asked", "pool/batch", pool=st["batch"], to=to, why=why,
                asked={0: "raised", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"))
    fac.say("pool.measured", "pool/batch", pool=st["batch"], most=most(cfg, "batch"), queue_wait_hours=wait,
            merges_per_hour=rate)


def put(cfg: dict, st: dict, role: str, n: int) -> None:
    """The role's pool to n (within 1 and its most), its history and the times, saved. Call it under locked()."""
    n = max(1, min(int(n), most(cfg, role)))
    now = time.time()
    if role == "batch":                             # (the queue's: no risk evidence, its own since)
        st["batch"], st["batch_since"] = n, now
        return save(cfg, st)
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
    import risk
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


def held(cfg: dict) -> bool:
    """[pools] hold (the operator, 2026-11-20: the role pools' tuning paused): the role pools are neither raised nor
    lowered by the tuner, which still measures and says what it would do; the batch is still tuned."""
    return cfg.get("pools", {}).get("hold", False) is not False


def tune(cfg: dict) -> int:
    import risk
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
        if held(cfg):                               # the operator's hold: decided and said, never done
            said["held"], what = what or "hold", None
        elif what == "lower":
            lower(cfg, st, role, to, why, said)
        follow = min(st["implementor"], most(cfg, "reviewer"))    # the reviewer pool follows the implementor's
        if held(cfg):
            pass
        elif st["reviewer"] > follow:
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
    tune_batch(cfg, state(cfg))
    return 0


def raise_pool(cfg: dict, role: str, was: int, to: int, why: str) -> int:
    """The approved raise, decided again under the lock: only if the pool is still what it was asked from (a lowering
    in between voids it), and for the implementor only if the risk bound at TO is still within the tolerance and the
    probation is over (an approval given late cannot raise into a crossed bound); the reviewer pool comes up with it.
    A reviewer raise only up to the implementor pool; the queue's batch only from WAS."""
    if role not in POOLS:
        raise SystemExit(f"no pool {role!r}: {', '.join(POOLS)}")
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
    if role not in POOLS:
        raise SystemExit(f"no pool {role!r}: {', '.join(POOLS)}")
    with locked(cfg):
        put(cfg, state(cfg), role, n)
    print(f"{role} pool {state(cfg)[role]} ({why})")
    return 0


def my_turn(cfg: dict, role: str, block: str, item: str) -> bool:
    """Whether this run's item is within the role's pool: the items its block's runs hold, by when their leases were
    taken, and this one among the first `pool` of them (so two runs taken at once never both go on). The pool is the
    risk target held to what the machine fits: min(pool, the role's sessions running + the headroom)."""
    held = [g for g in fac.items("gap") if (g["fields"].get("lease") or {}).get("block") == block
            and (g["fields"].get("lease") or {}).get("holder")]
    order = sorted((float(g["fields"]["lease"].get("taken") or 0), g["id"]) for g in held)
    ids = [i for _, i in order]
    import resources
    fits = resources.room(cfg, role)
    return item not in ids or ids.index(item) < min(state(cfg)[role], fits if fits is not None else 10**6)


READ = {"risk": lambda m: m["now"]["risk"], "bound": lambda m: m["now"]["bound"], "target": lambda m: m["target"],
        "over": lambda m: round(m["now"]["bound"] - m["tolerance"], 3),
        "factory-interventions": lambda m: m["factory_interventions"], "escapes": lambda m: m["escapes"]}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[0] == "read" and argv[1] in POOLS:
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
