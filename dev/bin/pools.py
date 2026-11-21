"""The AI pools, ramped up on good results (the owner, 2026-11-20: start with one implementor, "the work from the first
agent might come back awful"). Each role's pool (implementor, reviewer) starts at 1 and lives in run/pools.json, read
by the stocks implementor-pool and reviewer-pool. The blocks take their pools from those stocks (`pool: {now:
stock.implementor-pool, most: 9}`): the engine holds each block to the pool now at every dispatch, never above its
most ([pools] in dev/factory.toml sets the most this file allows). The gates and each run (`my_turn`) also hold them to
the machine's headroom.

    pools.py read ROLE        the role's pool now (a sensor)
    pools.py streak           the good gaps in a row since the pools last changed (a sensor)
    pools.py tune             the controller (a block): after [pools] streak good gaps in a row (approved within one fix
                              round, and not reverted after merging), an increase of one is asked as the gated action
                              raise-pool, for the coordinator; a park, a second fix round or a reverted merge lowers
                              every pool by one at once, never below 1. PAUSED (operator, 2026-11-20): the role
                              pools are neither raised nor lowered (pool-control replaces it); only the batch is tuned
    pools.py set ROLE N WHY   the action's command: set it (within 1 and its most)

The merge queue's batch (`batch`: approved gaps it merges and tests together, dev/bin/queue.py) lives here too: [pools]
batch to start (1, a gap a run), at most [pools] batch_max and never past BATCH_MOST. The tuner asks to raise it by
one, the same gated action, while the goal queue-wait-short is off (dev/model/measures.yaml); it is not lowered on a
bad gap (it changes how gaps are tested, not how many are built), only by hand (`set batch N`)."""

from __future__ import annotations

import json
import re
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402

ROLES = ("implementor", "reviewer")
BATCH_MOST = 4         # a batch of 4 with every merge failing is at most 8 suite runs (~1.5 h; the 3 h timeout
                       # also covers the lock and quiet-machine waits)


def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "pools.json"
    got = json.loads(p.read_text()) if p.exists() else {}
    batch = int(got.get("batch") or cfg.get("pools", {}).get("batch", 1))
    return {"since": float(got.get("since") or 0), **{r: int(got.get(r) or 1) for r in ROLES},
            "batch": max(1, min(batch, most(cfg, "batch"))), "batch_since": float(got.get("batch_since") or 0)}


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "pools.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def most(cfg: dict, role: str) -> int:
    n = int(cfg.get("pools", {}).get(f"{role}_max", 1))
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
                           to=str(to), why=why)
        fac.say("pool.raise-asked", "pool/batch", pool=st["batch"], to=to, why=why,
                asked={0: "raised", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"))
    fac.say("pool.measured", "pool/batch", pool=st["batch"], most=most(cfg, "batch"), queue_wait_hours=wait,
            merges_per_hour=rate)


def outcomes(gaps: list[dict], upgrades: list[dict]) -> list[tuple[float, str, str]]:
    """Each gap's evidence, in time order: (when, good or bad, why). Good: approved with at most one fix round. Bad:
    parked, sent back a second time, or its merge reverted (by hand, gap.reverted; or its upgrade reverted)."""
    reverted = {u["fields"].get("gap") for u in upgrades if u["state"] == "reverted"}
    out = []
    for g in gaps:
        f = g["fields"]
        fixes = int(f.get("fix_rounds") or 0)
        if g["state"] == "parked":
            out.append((float(f.get("parked_at") or g.get("last") or 0), "bad", f"{g['id']} parked"))
        elif fixes >= 2:
            out.append((float(g.get("last") or 0), "bad", f"{g['id']} sent back {fixes} times"))
        elif f.get("reverted") or g["id"] in reverted:
            out.append((float(f.get("reverted_at") or g.get("last") or 0), "bad", f"{g['id']} reverted after merging"))
        elif f.get("approved_at"):
            out.append((float(f["approved_at"]), "good", f"{g['id']} approved in {fixes} fix round(s)"))
    return sorted(out)


def decide(evidence: list[tuple[float, str, str]], since: float, pools: dict, cfg: dict) -> tuple[str | None, str, int]:
    """(raise, lower or None; why; the good streak) from the evidence since the pools last changed."""
    streak, need = 0, int(cfg.get("pools", {}).get("streak", 3))
    for when, what, why in evidence:
        if when < since:
            continue
        if what == "bad":
            if any(pools[r] > 1 for r in ROLES):
                return "lower", why, 0
            streak = 0
        else:
            streak += 1
    if streak >= need and any(pools[r] < most(cfg, r) for r in ROLES):
        return "raise", f"{streak} good gaps in a row", streak
    return None, "", streak


PAUSED = True     # the role pools' tuning (operator, 2026-11-20): it lowered the owner's pools on parks caused by main;
                  # pool-control replaces it. The pools stay where `pools.py set` put them; the batch is still tuned.


def tune(cfg: dict) -> int:
    st = state(cfg)
    if PAUSED:
        tune_batch(cfg, st)
        return 0
    evidence = outcomes(fac.items("gap"), fac.items("upgrade"))
    what, why, streak = decide(evidence, st["since"], st, cfg)
    if what == "lower":
        for r in ROLES:
            if st[r] > 1:
                st[r] -= 1
                print(json.dumps({"out": f"flow.{r}-pool-steps", "moved": -1}), flush=True)
                fac.say("pool.lowered", f"pool/{r}", pool=st[r], why=why, lowered_at=time.time())
        st["since"] = time.time()
        save(cfg, st)
    elif what == "raise":
        role = next(r for r in ROLES if st[r] < most(cfg, r))     # the implementor first, then the reviewer
        to = st[role] + 1
        rc, said = fac.act("raise-pool", key=f"{role}-{to}-{int(st['since'])}", role=role, to=str(to), why=why)
        fac.say("pool.raise-asked", f"pool/{role}", pool=st[role], to=to, why=why,
                asked={0: "raised", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"))
    for r in ROLES:
        fac.say("pool.measured", f"pool/{r}", pool=st[r], most=most(cfg, r), streak=streak)
    tune_batch(cfg, st)
    return 0


def set_pool(cfg: dict, role: str, n: int, why: str) -> int:
    if role not in (*ROLES, "batch"):
        raise SystemExit(f"no pool {role!r}: {', '.join(ROLES)}, batch")
    st = state(cfg)
    st[role] = max(1, min(int(n), most(cfg, role)))
    st["batch_since" if role == "batch" else "since"] = time.time()   # a new pool: its evidence starts again
    save(cfg, st)
    print(f"{role} pool {st[role]} ({why})")
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


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[0] == "read":
        print(state(cfg)[argv[1]])
    elif argv[0] == "streak":
        st = state(cfg)
        print(decide(outcomes(fac.items("gap"), fac.items("upgrade")), st["since"], st, cfg)[2])
    elif argv[0] == "tune":
        return tune(cfg)
    elif argv[0] == "set":
        return set_pool(cfg, argv[1], int(argv[2]), " ".join(argv[3:]) or "by hand")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
