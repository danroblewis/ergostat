"""The planner and the plan review: a gap is planned before it is built.

    plan.py           the planner: takes a gap at open (or replan). In a read-only clone of main, a session writes its
                      definition of done (acceptance tests by name, a budget, the review lessons that apply as risks,
                      the files to touch) to run/plans/<branch>.md: planned. Or it splits the gap into sub-gaps (each
                      planned, `depends-on` among them, `parent:` the gap, which waits in split until every one is
                      merged), or asks research questions and waits for their answers (a question dead, or unanswered after 12
                      waits, is planned without, and the brief says so). A gap whose definition the
                      coordinator wrote is made ready as the intake does.
    plan.py splits    a split gap whose sub-gap parked (or died) parked too, saying which (a program, every 5m)
                      Each definition is linted first (lint: no AI); one that fails goes back with the findings,
                      uncounted by the plan kill rule (the 6th lint failure parks).
    plan.py lint      the plan lint, every 5m, on each planned plan not yet linted as it is on disk
    plan.py review    the plan review: takes a gap at planned; a session in a read-only clone of main, given the plan,
                      the lessons and the task graph (brief.graph). Approved, the plan as it read it (its non-blocking
                      notes appended) becomes run/defs/<branch>.md and the gap is ready; sent back, the planner takes it
                      again with the findings; the [gates] plan_kill_after-th failure, or a park, parks it.
    plan.py yield     plan first-pass yield: of gaps first plan-reviewed in 14 days, the share approved then"""

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

MOST_SPLIT, MOST_RESEARCH, MOST_LINT, MOST_WAITS = 6, 3, 6, 12      # 12 waits of 30 minutes
SECTIONS = ("Definition of done", "Files to touch", "Risks", "Acceptance tests", "Size budget")
TEST = re.compile(r"\btests/[\w/.-]+\.py::\w+")
TAG = re.compile(r'<definition branch="([^"]*)"(?: title="([^"]*)")?>\n?(.*?)</definition>', re.S)
DEPS = re.compile(r"^depends-on:\s*\[([^\]]*)\]", re.M)


def kill_after(cfg: dict) -> int:
    """The plan reviews that park a gap (lint failures never count): [gates] plan_kill_after."""
    return int(cfg.get("gates", {}).get("plan_kill_after", 4))


def send_back(cfg: dict, gap: dict, why: list[str], park: bool = False, by: str = "review", **record) -> int:
    """A failed plan back to the planner with why: by its review (counted: parked at the plan kill rule, or on a park
    verdict), or by the lint (a plan's format, or a planner's answer that cannot be taken: never counted by the kill
    rule; the MOST_LINT-th parks, a planner that cannot write the format)."""
    f, review_ = gap["fields"], by == "review"
    n = int(f.get("plan_failures" if review_ else "plan_lint_failures") or 0) + 1
    if park or n >= (kill_after(cfg) if review_ else MOST_LINT):
        import review
        fac.say("gap.measured", gap["id"], plan_findings=why, **record)
        review.park(cfg, gap, f"Its plan failed its {'review' if review_ else 'lint'} {n} times, or was parked:\n"
                    + "\n".join(f"- {w}" for w in why), f"plan-{by}", where="plan")
    else:
        fac.say("gap.plan-sent-back", gap["id"], plan_findings=why, plan_sent_back_by=by,
                **({"plan_failures": 1} if review_ else {"plan_lint_failures": n}), **record)
    return 0


def lint(cfg: dict, body: str, siblings: tuple[str, ...] = ()) -> list[str]:
    """What makes a definition fail the plan lint (no AI): a section or the depends-on line missing, an acceptance
    test not named as tests/...py::test_name, a size budget with no number or over [gates] plan_budget_most, a lesson
    under Risks that is none, a dependency that is no gap, sub-gap of the same answer or merged branch, a file to
    touch neither on main nor marked new."""
    import deps
    import knowledge
    repo, base = fac.path(cfg, "checkout"), cfg["git"]["base"]
    out = [] if DEPS.search(body) else ["no `depends-on: [names]` line (`[]` for none)"]
    out += [f"no `## {s}` section" for s in SECTIONS if brief.section(body, s) is None]
    tests = [x for x in (brief.section(body, "Acceptance tests") or "").splitlines() if x.startswith(("- ", "* "))]
    out += [f"an acceptance test not named as `tests/...py::test_name`: {x[2:80]!r}" for x in tests if not TEST.search(x)]
    out += [] if tests or brief.section(body, "Acceptance tests") is None else ["no acceptance test listed"]
    most, budget = int(cfg.get("gates", {}).get("plan_budget_most", 600)), brief.section(body, "Size budget")
    n = fac.budget_of(body, default=-1) if budget is not None else 0
    out += [f"the size budget is {n} net lines: at most {most} (else split it)"] if n > most else []
    out += ["the size budget names no number of net lines (`N net lines`)"] if n == -1 else []
    lessons = {e["id"] for e in knowledge.entries() if e["kind"] == "lesson"}
    out += [f"{x} under Risks is no review lesson" for x in sorted(set(re.findall(
        r"\blesson-\d+\b", brief.section(body, "Risks") or ""))) if x not in lessons]
    gaps = {g["id"]: g for g in fac.items("gap")}
    find = deps.resolver(gaps, {})
    merged = set(fac.git(repo, "branch", "--format=%(refname:short)", "--merged", base, check=False).split())
    out += [f"depends-on {d[4:]!r}: no gap, sub-gap of this plan or branch merged into {base}" for d in deps_of(body)
            if not find(d[4:]) and d[4:] not in siblings and not {d[4:], f"factory/{d[4:]}"} & merged]
    files = brief.files_of(body)
    out += [] if files or brief.section(body, "Files to touch") is None else ["no file named under Files to touch"]
    out += [f"`{p}` under Files to touch is not on {base} and not marked new" for p, new in files
            if not new and not fac.git_ok(repo, "cat-file", "-e", f"{base}:{p}")]
    return out


def linted(cfg: dict, defs: list[tuple[str, str, str]]) -> list[str]:
    names = tuple(d[0] for d in defs)
    return [f"{name}: {x}" if len(defs) > 1 else x for name, _, body in defs for x in lint(cfg, body, names)]


def sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def deps_of(body: str) -> list[str]:
    m = DEPS.search(body)
    names = [d.strip().strip("`'\"") for d in m[1].split(",") if d.strip()] if m else []
    return [n if n.startswith("gap/") else f"gap/{n}" for n in names]


def problems(defs: list[tuple[str, str, str]], branch: str, known: set[str]) -> list[str]:
    """What makes a planner's definitions unusable: none, too many, one not for the gap, a sub-gap named as the gap or
    as a gap that exists (its id reused would merge old fields in), a name that is not lowercase words and dashes, or
    a dependency on a later sub-gap or on no gap."""
    if len(defs) == 1:
        return [] if defs[0][0] == branch else [f"a single definition must be for {branch}, not {defs[0][0]!r}"]
    names = [d[0] for d in defs]
    out = [] if defs else ["the planner wrote no <definition>"]
    out += [f"a split into {len(defs)} sub-gaps: at most {MOST_SPLIT}"] if len(defs) > MOST_SPLIT else []
    for i, (name, _, body) in enumerate(defs):
        if name == branch or not fac.SAFE.match(name) or f"gap/{name}" in known or name in names[:i]:
            out.append(f"sub-gap {name!r}: not a new name of lowercase words and dashes")
        out += [f"sub-gap {name!r} depends on {d}, neither an earlier sub-gap nor a gap" for d in deps_of(body)
                if d[4:] not in names[:i] and d not in known]
    return out


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
    text, context = brief.assemble(cfg, "planner", gap, work, definition="", branch=branch, graph=brief.graph(cfg, gap),
                                   plan_findings=brief.
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
                             by="lint", **record)
        ids = [f"research/{fac.slug(q, 40)}-{uuid.uuid4().hex[:6]}" for q in questions]
        for rid, q in zip(ids, questions, strict=True):
            fac.say("research.asked", rid, question=q, gap=gap["id"], asked_by="planner", asked_at=now)
        fac.say("gap.measured", research=ids, **record)
        fac.nack("waits for its research", after="30m", count=False)
        return 0
    defs = [(n.strip(), t.strip(), b.strip() + "\n") for n, t, b in TAG.findall(said)]
    gaps = fac.items("gap")                              # a sub-gap's name is never another gap's id or branch
    known = {g["id"] for g in gaps} | {f"gap/{g['fields'].get('branch')}" for g in gaps}
    if wrong := problems(defs, branch, known) or linted(cfg, defs):
        return send_back(cfg, gap, wrong, by="lint", **record)
    for name, title, body in defs:
        p = fac.run_dir(cfg, "plans") / f"{name}.md"
        p.write_text(body)
        if name != branch:
            fac.say("gap.requested", f"gap/{name}", title=title or name, source="plan", branch=name,
                    parent=[gap["id"]], depends_on=deps_of(body), requested_at=now)
        fac.say("gap.planned", gap["id"] if name == branch else f"gap/{name}", plan=fac.rel(p), planned_at=now, risks=sorted(set(re.findall(
            r"\blesson-\d+\b", body))), replanned=name == branch and bool(f.get("plan_failures")), plan_linted=sha(body),
            **(record if name == branch else {}))
    if defs[0][0] != branch:
        fac.say("gap.split", children=[f"gap/{d[0]}" for d in defs], split_at=now, **record)
    return 0


def review_plan(cfg: dict, gap: dict) -> int:
    f, branch = gap["fields"], fac.branch_of(gap)
    p = fac.run_dir(cfg, "plans") / f"{branch}.md"
    if not p.is_file():
        return send_back(cfg, gap, [f"its plan {fac.rel(p)} is missing"], by="lint")
    plan = p.read_text()                                 # what is reviewed is what becomes the definition
    if f.get("plan_linted") != sha(plan) and (found := lint(cfg, plan)):
        return send_back(cfg, gap, found, by="lint")     # no session for a plan that fails the lint
    _, work = agents.clone(cfg, branch, "plan_reviewer", at=f"origin/{cfg['git']['base']}")
    text, context = brief.assemble(cfg, "plan_reviewer", gap, work, definition=plan, branch=branch,
                                   graph=brief.graph(cfg, gap))
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
    notes = "".join(f"- {n}\n" for n in v["non_blocking"])
    try:
        with target.open("x") as fh:                     # never over a definition the coordinator wrote meanwhile
            fh.write(plan + (f"\n## Notes from the plan review (answer each)\n\n{notes}" if notes else ""))
    except FileExistsError:
        by = "coordinator"
    fac.say("gap.defined", definition=fac.rel(target), ready_at=time.time(), branch=branch, defined_by=by,
            plan_sha=sha(plan), plan_failures=-int(f.get("plan_failures") or 0), **record)
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


def sweep(cfg: dict) -> int:
    """The plan lint as its own step: each planned gap, not held by a run, whose plan on disk is not the one linted
    (planned before the lint, or changed since): linted, and sent back or marked linted."""
    for g in fac.items("gap", "planned"):
        p = fac.run_dir(cfg, "plans") / f"{fac.branch_of(g)}.md"
        if (g["fields"].get("lease") or {}).get("holder") or not p.is_file() or g["fields"].get(
                "plan_linted") == sha(p.read_text()):
            continue
        if found := lint(cfg, p.read_text()):
            send_back(cfg, g, found, by="lint")
        else:
            fac.say("gap.measured", g["id"], plan_linted=sha(p.read_text()))
    return 0


def first_pass(now: float | None = None) -> float:
    """Of gaps whose first plan review was in the last 14 days, the share it approved (none: no value, exit 1)."""
    since = (now or time.time()) - 14 * 86400
    first = [r[0] for r in (g["fields"].get("plan_reviews") or [] for g in fac.items("gap")) if r]
    first = [r for r in first if float(r.get("at") or 0) >= since]
    if not first:
        raise SystemExit("plan-first-pass: no value yet (no first plan review in the window)")
    return round(sum(r.get("verdict") == "merge" for r in first) / len(first), 3)


if __name__ == "__main__":
    fac.stop_on_term()
    if sys.argv[1:] == ["yield"]:
        print(first_pass())
        sys.exit(0)
    if sys.argv[1:] in (["splits"], ["lint"]):
        sys.exit((splits if sys.argv[1] == "splits" else sweep)(fac.config()))
    sys.exit((review_plan if sys.argv[1:] == ["review"] else planner)(fac.config(), fac.read_input()["item"]))
