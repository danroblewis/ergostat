"""The advisory plan review (the owner, 2026-11-20: "getting everything right the first time is less important than
improving the workflow itself"): never a gate. A gap the planner marked (`plan_review: wanted`, plan.review_wanted)
is already ready; this reads its definition against main's code and the task graph, and:

- appends its findings to the definition (run/defs/<branch>.md) as notes the implementor answers (a gap already
  building has its definition committed: the notes are recorded, too late for it);
- records them as a review item (`review/<branch>-plan`, stage plan, round 0, never counted as a code review), each
  finding with its class (a lesson's id, or feasibility, design, graph, tests), for the loop that turns recurring
  classes into lessons, prompt guidance or lint rules (the librarian takes review.written too);
- for "this should not be built", asks the coordinator for `park-gap` (held in the inbox); never parks by itself.

    planreview.py             one marked gap, oldest ready first (a program, while plans wait and money is left)
    planreview.py park GAP WHY   the gated action, once approved: the gap parked with why
    planreview.py waiting     the gaps still marked
    planreview.py agreement   of plan reviews in 14 days, the share with no blocking finding
    planreview.py value fix-rounds|parks flagged|clean   of gaps merged or parked in 14 days whose plan was reviewed,
                              those it flagged (blocking findings) or not: their mean code-review fix rounds, or the
                              share parked: what the stage is worth"""

from __future__ import annotations

import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402

CLASS = re.compile(r"^\s*\[([\w-]+)\]\s*")
WINDOW = 14 * 86400


def classed(findings: list[str]) -> list[dict]:
    """Each finding as {class, text}: its leading `[class]` tag, or `none`."""
    return [{"class": m[1] if (m := CLASS.match(x)) else "none", "text": CLASS.sub("", x, 1)} for x in findings]


def coverage(cfg: dict, gap: dict) -> str:
    """A sub-gap's parent's coverage (run/plans/<parent-branch>.md, saved by plan.py at the split), or `(none)`."""
    parents = fac.ids(gap["fields"].get("parent"))
    gaps = {g["id"]: g for g in fac.items("gap")} if parents else {}
    for p in (gaps[p] for p in parents if p in gaps):
        if (f := fac.run_dir(cfg, "plans") / f"{fac.branch_of(p)}.md").is_file():
            return f"(of {p['id']})\n\n{f.read_text().strip()}"
    return "(none)"


def review_one(cfg: dict) -> int:
    marked = [g for g in fac.items("gap") if g["fields"].get("plan_review") == "wanted"]
    if not marked or fac.ai_held(cfg):                  # (the AI held: next turn)
        return 0
    gap = sorted(marked, key=lambda g: (g["state"] != "ready", float(g["fields"].get("ready_at") or 0)))[0]
    if why := fac.may_spend(cfg, float(cfg["ai"]["plan_reviewer_session_usd"])):
        print(f"plan review waits: {why}", file=sys.stderr)
        return 0
    gid, branch, began = gap["id"], fac.branch_of(gap), time.time()
    target = fac.run_dir(cfg, "defs") / f"{branch}.md"
    fac.say("gap.measured", gid, plan_review="started")              # (taken once, whatever happens next)
    _, work = agents.clone(cfg, branch, "plan_reviewer", at=f"origin/{cfg['git']['base']}")
    text, context = brief.assemble(cfg, "plan_reviewer", gap, work, definition=target.read_text(), branch=branch,
                                   graph=brief.graph(cfg, gap), coverage=coverage(cfg, gap))
    context["brief"] = brief.save(cfg, "plan_reviewer", gap, text)
    import review
    got = None
    try:
        got = fac.session(cfg, "plan_reviewer", text, work, item=gid)
        v = review.verdict(str(got.get("result", "")))
    except fac.OverBudget as e:                         # (the cap reached meanwhile: it waits again)
        fac.say("gap.measured", gid, plan_review="wanted", last_error=f"budget: {e}"[:500])
        return 0
    except BaseException as e:                          # a timeout, an error, a cancel: the whole reservation
        usd = float(cfg["ai"]["plan_reviewer_session_usd"])     # (unless the session ended and told its cost)
        usd = round(float(got["total_cost_usd"]) if got and got.get("total_cost_usd") is not None else usd, 4)
        fac.say("gap.measured", gid, plan_review="failed", last_error=f"{type(e).__name__}: {e}"[:500],
                ai_cost_usd=usd, planning_cost_usd=usd, sessions=1)
        raise
    found = classed(v["blocking"]) + classed(v["non_blocking"])
    if found and gap["state"] in ("ready", "open", "replan", "planned"):
        with target.open("a") as fh:
            fh.write("\n## Notes from the plan review (answer each)\n\n" + "".join(f"- {x['text']}\n" for x in found))
    cost = got.get("total_cost_usd")                    # (no cost told: the reservation was kept)
    cost = round(float(cfg["ai"]["plan_reviewer_session_usd"]) if cost is None else float(cost), 4)
    rid = f"review/{branch}-plan"
    fac.say("review.written", rid, gap=gid, stage="plan", round=0, written_at=time.time(), **v, context=context,
            classes=sorted({x["class"] for x in found} - {"none"}), findings=found, ai_cost_usd=cost)
    fac.say("gap.measured", gid, plan_review="done", plan_flagged=bool(v["blocking"]), plan_findings_n=len(found),
            plan_reviews=[{"verdict": v["verdict"], "blocking": len(v["blocking"]), "at": time.time()}],
            plan_notes_late=bool(found) and gap["state"] not in ("ready", "open", "replan", "planned"),
            contexts=[context], ai_cost_usd=cost, planning_cost_usd=cost, sessions=1,
            plan_review_hours=round((time.time() - began) / 3600, 3))
    if v["verdict"] == "park":
        fac.act("park-gap", key=gid, gap=gid, why=(v["where_it_stopped"] or "; ".join(v["blocking"]))[:1500])
    return 0


def park(gid: str, why: str) -> int:
    """The gated action, once the coordinator approved it (outside a run: recorded with `event --add`)."""
    fac.add("gap.parked", gid, parked_at=time.time(), parked_by="plan-review", parked_in="plan", parked_for="cancelled",
            parked_until=None, resumed_as=None, resumed_at=None, need_met=None,
            where_it_stopped=f"The plan review asked that it not be built, and the coordinator agreed:\n{why}"[:4000])
    return 0


def reading(name: str, *args: str, now: float | None = None) -> float:
    since = (now or time.time()) - WINDOW
    gaps = fac.items("gap")
    if name == "waiting":
        return float(sum(g["fields"].get("plan_review") == "wanted" for g in gaps))
    if name == "agreement":
        last = [r for g in gaps for r in g["fields"].get("plan_reviews") or [] if float(r.get("at") or 0) >= since]
        if not last:
            raise SystemExit("plan-review-agreement: no value yet (no plan review in the window)")
        return round(sum(not r.get("blocking") for r in last) / len(last), 3)
    what, group = args
    done = [g["fields"] for g in gaps if g["state"] in ("merged", "parked") and g["fields"].get("plan_review") == "done"
            and max(float(g["fields"].get(k) or 0) for k in ("merged_at", "parked_at")) >= since
            and bool(g["fields"].get("plan_flagged")) == (group == "flagged")]
    if not done:
        raise SystemExit(f"plan-{group}-{what}: no value yet (no such gap finished in the window)")
    if what == "parks":
        return round(sum(bool(f.get("parked_at")) and not f.get("merged_at") for f in done) / len(done), 3)
    return round(sum(float(f.get("fix_rounds") or 0) for f in done) / len(done), 3)


if __name__ == "__main__":
    fac.stop_on_term()
    if sys.argv[1:2] == ["park"]:
        sys.exit(park(sys.argv[2], " ".join(sys.argv[3:])))
    if sys.argv[1:2] and sys.argv[1] in ("waiting", "agreement", "value"):
        print(reading(*sys.argv[1:]))
        sys.exit(0)
    sys.exit(review_one(fac.config()))
