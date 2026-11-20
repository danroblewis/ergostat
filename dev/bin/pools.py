"""The AI pools, ramped up on good results (the owner, 2026-11-20: start with one implementor, "the work from the first
agent might come back awful"). Each role's pool (implementor, reviewer) starts at 1 and lives in run/pools.json;
the blocks' `pool:` in the model is only its most ([pools] in dev/factory.toml), and the engine's gate and each run
hold the rest to the pool now.

    pools.py read ROLE        the role's pool now (a sensor)
    pools.py streak           the good gaps in a row since the pools last changed (a sensor)
    pools.py tune             the controller (a block): after [pools] streak good gaps in a row (approved within one fix
                              round, and not reverted after merging), an increase of one is asked as the gated action
                              raise-pool, for the coordinator; a park, a second fix round or a reverted merge lowers
                              every pool by one at once, never below 1
    pools.py set ROLE N WHY   the action's command: set it (within 1 and its most)"""

from __future__ import annotations

import json
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402

ROLES = ("implementor", "reviewer")


def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "pools.json"
    got = json.loads(p.read_text()) if p.exists() else {}
    return {"since": float(got.get("since") or 0), **{r: int(got.get(r) or 1) for r in ROLES}}


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "pools.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def most(cfg: dict, role: str) -> int:
    return int(cfg.get("pools", {}).get(f"{role}_max", 1))


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


def tune(cfg: dict) -> int:
    st = state(cfg)
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
    return 0


def set_pool(cfg: dict, role: str, n: int, why: str) -> int:
    if role not in ROLES:
        raise SystemExit(f"no pool {role!r}: {', '.join(ROLES)}")
    st = state(cfg)
    st[role] = max(1, min(int(n), most(cfg, role)))
    st["since"] = time.time()                        # a new pool: its evidence starts again
    save(cfg, st)
    print(f"{role} pool {st[role]} ({why})")
    return 0


def my_turn(cfg: dict, role: str, block: str, item: str) -> bool:
    """Whether this run's item is within the role's pool: the items its block's runs hold, by when their leases were
    taken, and this one among the first `pool` of them (so two runs taken at once never both go on)."""
    held = [g for g in fac.items("gap") if (g["fields"].get("lease") or {}).get("block") == block
            and (g["fields"].get("lease") or {}).get("holder")]
    order = sorted((float(g["fields"]["lease"].get("taken") or 0), g["id"]) for g in held)
    ids = [i for _, i in order]
    return item not in ids or ids.index(item) < state(cfg)[role]


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
