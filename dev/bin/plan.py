"""The planner and the plan review: a gap is planned before it is built.

    plan.py           the planner: takes a gap at open (or replan). In a read-only clone of main, a session writes its
                      definition of done (acceptance tests by name, a budget, the review lessons that apply as risks,
                      the files to touch) to run/plans/<branch>.md: planned. Or it splits the gap into sub-gaps (each
                      planned, `depends-on` among them, `parent:` the gap, which waits in split until every one is
                      merged), or asks research questions and waits for their answers (a question dead, or unanswered after 12
                      waits, is planned without, and the brief says so). A gap whose definition the
                      coordinator wrote is made ready as the intake does.
    plan.py splits    a split gap whose sub-gap parked (or died) parked too, saying which (a program, every 5m)
    plan.py review    the plan review: takes a gap at planned; a cheap session given the plan and the lessons only.
                      Approved, the plan as it read it becomes run/defs/<branch>.md and the gap is ready; sent back,
                      the planner takes it again with the findings; a second failure, or a park, parks it."""

from __future__ import annotations

import hashlib
import re
import sys
import time
import uuid

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402

MOST_SPLIT, MOST_RESEARCH, KILL, MOST_WAITS = 6, 3, 2, 12      # 12 waits of 30 minutes
TAG = re.compile(r'<definition branch="([^"]*)"(?: title="([^"]*)")?>\n?(.*?)</definition>', re.S)
DEPS = re.compile(r"^depends-on:\s*\[([^\]]*)\]", re.M)
SIZE = re.compile(r"\bsize:\s*([A-Za-z]+)\s*\(confidence:\s*([A-Za-z]+)\s*\)")
CLASSES, CONFIDENCES = ("S", "M", "L", "XL"), ("low", "medium", "high")


def size_of(body: str) -> dict | str:
    """The size line of a definition's `## Size budget`: {size, size_confidence}, or why it cannot be taken (never a
    default class: a guess would be scored as the planner's)."""
    m = re.search(r"^## Size budget.*?$(.*?)(?=^## |\Z)", body, re.M | re.S)
    got = SIZE.search(m.group(1)) if m else None
    if not got:
        return "no size line `size: S|M|L|XL (confidence: low|medium|high)` in its ## Size budget"
    if got[1] not in CLASSES or got[2] not in CONFIDENCES:
        return f"size {got[1]!r} (confidence {got[2]!r}): the class is one of S, M, L, XL, the confidence low, medium, high"
    return {"size": got[1], "size_confidence": got[2]}


def send_back(cfg: dict, gap: dict, why: list[str], park: bool = False, **record) -> int:
    """A failed plan (its review, or a planner's answer that cannot be taken) back to the planner with why; parked on
    the second failure (the kill rule) or a park verdict."""
    if park or int(gap["fields"].get("plan_failures") or 0) + 1 >= KILL:
        import review
        fac.say("gap.measured", plan_findings=why, **record)
        review.park(cfg, gap, "Its plan failed its review twice, or was parked:\n" + "\n".join(f"- {w}" for w in why),
                    "plan-review", where="plan")
    else:
        fac.say("gap.plan-sent-back", gap["id"], plan_findings=why, plan_failures=1, **record)
    return 0


def deps_of(body: str) -> list[str]:
    m = DEPS.search(body)
    names = [d.strip().strip("`'\"") for d in m[1].split(",") if d.strip()] if m else []
    return [n if n.startswith("gap/") else f"gap/{n}" for n in names]


def problems(defs: list[tuple[str, str, str]], branch: str, known: set[str]) -> list[str]:
    """What makes a planner's definitions unusable: none, too many, one not for the gap, a sub-gap named as the gap or
    as a gap that exists (its id reused would merge old fields in), a name that is not lowercase words and dashes, or
    a dependency on a later sub-gap or on no gap, or a size line missing or not understood."""
    sizes = [f"{name!r}: {why}" for name, _, body in defs if isinstance(why := size_of(body), str)]
    if len(defs) == 1:
        return sizes + ([] if defs[0][0] == branch else [f"a single definition must be for {branch}, not {defs[0][0]!r}"])
    names = [d[0] for d in defs]
    out = [] if defs else ["the planner wrote no <definition>"]
    out += [f"a split into {len(defs)} sub-gaps: at most {MOST_SPLIT}"] if len(defs) > MOST_SPLIT else []
    for i, (name, _, body) in enumerate(defs):
        if name == branch or not fac.SAFE.match(name) or f"gap/{name}" in known or name in names[:i]:
            out.append(f"sub-gap {name!r}: not a new name of lowercase words and dashes")
        out += [f"sub-gap {name!r} depends on {d}, neither an earlier sub-gap nor a gap" for d in deps_of(body)
                if d[4:] not in names[:i] and d not in known]
    return out + sizes


def planner(cfg: dict, gap: dict) -> int:
    f, branch, now = gap["fields"], fac.branch_of(gap), time.time()
    import intake
    import research as rs
    if where := intake.definition(cfg, gap):
        fac.say("gap.defined", definition=where, ready_at=now, branch=branch, defined_by="coordinator")
        return 0
    research = {r["id"]: r for r in fac.items("research")}
    asked = list(f.get("research") or [])
    waiting = [r for r in asked if research.get(r, {}).get("state") not in ("answered", "dead", None)]
    if waiting and int(f.get("research_waits") or 0) < MOST_WAITS:
        fac.say("gap.measured", research_waits=1)
        fac.nack(f"waits for its research: {', '.join(waiting)}", after="30m", count=False)
        return 0
    unanswered = lambda r: "(no answer: the question " + ("is a dead letter or not recorded" if r not in waiting  # noqa: E731
                                                         else f"was not answered in {MOST_WAITS} waits") + ")"
    _, work = agents.clone(cfg, branch, "planner", at=f"origin/{cfg['git']['base']}")
    reports = [rs.report(cfg, research[r])[:4000] if r in research else "" for r in asked]
    text, context = brief.assemble(cfg, "planner", gap, work, definition="", branch=branch, plan_findings=brief.
                                   findings_text(f.get("plan_findings") or []), research="\n\n".join(
                                       f"### {r}\n\n{x or unanswered(r)}" for r, x in zip(asked, reports, strict=True))
                                   or "(none)")
    context["brief"] = brief.save(cfg, "planner", gap, text)
    got = fac.attempt(cfg, "planner", text, work)
    if got is None:
        return 0
    said = str(got.get("result", ""))
    record = dict(contexts=[context], ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4), sessions=1)
    if questions := [" ".join(q.split()) for q in re.findall(r"<research>(.*?)</research>", said, re.S) if q.strip()]:
        if len(asked) + len(questions) > MOST_RESEARCH:
            return send_back(cfg, gap, [f"{len(asked) + len(questions)} research questions: at most {MOST_RESEARCH}"],
                             **record)
        ids = [f"research/{fac.slug(q, 40)}-{uuid.uuid4().hex[:6]}" for q in questions]
        for rid, q in zip(ids, questions, strict=True):
            fac.say("research.asked", rid, question=q, gap=gap["id"], asked_by="planner", asked_at=now)
        fac.say("gap.measured", research=ids, **record)
        fac.nack("waits for its research", after="30m", count=False)
        return 0
    defs = [(n.strip(), t.strip(), b.strip() + "\n") for n, t, b in TAG.findall(said)]
    gaps = fac.items("gap")                              # a sub-gap's name is never another gap's id or branch
    if wrong := problems(defs, branch, {g["id"] for g in gaps} | {f"gap/{g['fields'].get('branch')}" for g in gaps}):
        return send_back(cfg, gap, wrong, **record)
    for name, title, body in defs:
        p = fac.run_dir(cfg, "plans") / f"{name}.md"
        p.write_text(body)
        if name != branch:
            fac.say("gap.requested", f"gap/{name}", title=title or name, source="plan", branch=name,
                    parent=[gap["id"]], depends_on=deps_of(body), requested_at=now)
        fac.say("gap.planned", gap["id"] if name == branch else f"gap/{name}", plan=fac.rel(p), planned_at=now, risks=sorted(set(re.findall(
            r"\blesson-\d+\b", body))), replanned=name == branch and bool(f.get("plan_failures")),
            **(s := size_of(body)), planned_size=s["size"],  # planned_size: the planner's own, no groomer regrades it
            merged_lines=None, merged_lines_error=None,          # a new size, never scored on old lines
            **(record if name == branch else {}))
    if defs[0][0] != branch:                             # a split parent merges nothing: no size of its own
        fac.say("gap.split", children=[f"gap/{d[0]}" for d in defs], split_at=now, size=None, size_confidence=None,
                planned_size=None, **record)
    return 0


def review_plan(cfg: dict, gap: dict) -> int:
    f, branch = gap["fields"], fac.branch_of(gap)
    p = fac.run_dir(cfg, "plans") / f"{branch}.md"
    if not p.is_file():
        return send_back(cfg, gap, [f"its plan {fac.rel(p)} is missing"])
    plan = p.read_text()                                 # what is reviewed is what becomes the definition
    work = agents.scratch(cfg, branch, "plan_reviewer") / "work"
    work.mkdir()
    text, context = brief.assemble(cfg, "plan_reviewer", gap, work, definition=plan, branch=branch)
    context["brief"] = brief.save(cfg, "plan_reviewer", gap, text)
    got = fac.attempt(cfg, "plan_reviewer", text, work)
    if got is None:
        return 0
    import review
    v = review.verdict(str(got.get("result", "")))
    record = dict(contexts=[context], ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4), sessions=1,
                  plan_reviews=[{"verdict": v["verdict"], "blocking": v["blocking"], "at": time.time()}])
    if v["verdict"] != "merge":
        return send_back(cfg, gap, v["blocking"] or [v["where_it_stopped"] or "parked"], v["verdict"] == "park",
                         **record)
    target, by = fac.run_dir(cfg, "defs") / f"{branch}.md", "plan"
    try:
        with target.open("x") as fh:                     # never over a definition the coordinator wrote meanwhile
            fh.write(plan)
    except FileExistsError:
        by = "coordinator"
    fac.say("gap.defined", definition=fac.rel(target), ready_at=time.time(), branch=branch, defined_by=by,
            plan_sha=hashlib.sha1(plan.encode()).hexdigest(), plan_failures=-int(f.get("plan_failures") or 0), **record)
    return 0


def splits(cfg: dict) -> int:
    """Each split gap one of whose sub-gaps parked: parked too, saying which and where it stopped (the join only moves
    it on once every sub-gap is merged)."""
    import review
    gaps = fac.items("gap")
    for g in (g for g in gaps if g["state"] == "split"):
        stopped = [c for c in gaps if g["id"] in fac.ids(c["fields"].get("parent")) and c["state"] in ("parked", "dead")]
        if stopped:
            review.park(cfg, g, "Its sub-gaps stopped:\n" + "\n".join(
                f"- {c['id']} ({c['state']}): {str(c['fields'].get('where_it_stopped') or '').strip()[:600]}"
                for c in stopped), "split-watch", where="split")
    return 0


if __name__ == "__main__":
    fac.stop_on_term()
    if sys.argv[1:] == ["splits"]:
        sys.exit(splits(fac.config()))
    sys.exit((review_plan if sys.argv[1:] == ["review"] else planner)(fac.config(), fac.read_input()["item"]))
