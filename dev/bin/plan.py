"""The planner and the plan lint: a gap is planned before it is built, and its plan is its definition at once.

    plan.py           the planner: takes a gap at open (or replan). In a read-only clone of main, given the task graph
                      (brief.graph), a session writes its definition of done (acceptance tests by name, a budget, the
                      review lessons that apply as risks, the files to touch). Or it splits the gap into sub-gaps
                      (`depends-on` among them, `parent:` the gap, which waits in split until every one is merged; each
                      at most 250 net lines, its <coverage> block saved as run/plans/<parent>.md), or
                      asks research questions and waits for their answers (a question dead, or unanswered after 12
                      waits, is planned without, and the brief says so). Each definition is linted (lint: no AI): one
                      that fails goes back with the findings (the 6th lint failure parks: a planner that cannot write
                      the format); a lint-clean one becomes run/defs/<branch>.md and the gap is ready at once (the
                      owner, 2026-11-20: the plan review is never a gate). Some are marked for the advisory plan review
                      ([plan] review = off marks none). A gap whose definition the coordinator wrote is made ready as
                      the intake does. By the size class on the gap before it is planned (size_path; dev/README.md,
                      *Planning by size*): S has no session (its title and text with the house rules, unreviewed), M
                      one session under [ai] planner_m_session_usd (unreviewed), L the full planner, reviewed on a
                      sample ([planning] l_review_share, per gap), XL must split; no class, or one not trusted, and
                      every replan and sub-gap, take the full planner, marked for review. Each session's cost is also
                      recorded as planning_cost_usd (the whole reservation when it fails).
    plan.py splits    a split gap whose sub-gap parked (or died) parked too, saying which (a program, every 5m)
    plan.py lint      the plan lint's sweep, every 5m: a plan left in planned, or sent back by the old plan review, made
                      the definition once it is lint-clean (the old review's findings appended as notes)"""

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
SIZE = re.compile(r"\bsize:\s*([A-Za-z]+)\s*\(confidence:\s*([A-Za-z]+)\s*\)")
CLASSES, CONFIDENCES = ("S", "M", "L", "XL"), ("low", "medium", "high")
SUB_GAP_MOST_LINES = 250                                 # a sub-gap's budget at most (a single plan: plan_budget_most)
COVER = re.compile(r"<coverage>(.*?)</coverage>", re.S)
BY = re.compile(r"\(by:([^()]*)\)\s*$")
TRUST = {"low": 0.25, "medium": 0.5, "high": 0.75}       # a confidence against [planning] min_size_confidence
SMALL = """# {branch}: {title}

depends-on: [{deps}]

## Definition of done

{title}

{text}

Written from the gap's own title and text by the size path (an S gap: no planner session, no review). Done means the
house rules: the acceptance tests exist and pass, the unit suite and the browser files pass, ruff is clean, origin/main
is merged in and the suites run again.

## Files to touch

(not planned: the implementor names them)

## Risks

(not planned: check the branch against every review lesson)

## Acceptance tests

- the implementor names each test it writes as `tests/...py::test_name`

## Size budget

size: S (confidence: {confidence})

50 net lines.
"""


def size_settings(cfg: dict) -> tuple[float, float, float]:
    """[ai] planner_m_session_usd (above 0, at most planner_session_usd), [planning] l_review_share and
    min_size_confidence (each in [0, 1]); unset: the planner's own cap, every L plan reviewed, no class trusted (1.0
    is above TRUST's high). One out of bounds or not a number stops the run before any session (SystemExit)."""
    ai, p, full = cfg["ai"], cfg.get("planning") or {}, float(cfg["ai"]["planner_session_usd"])
    got = {"[ai] planner_m_session_usd": ai.get("planner_m_session_usd", full),
           "[planning] l_review_share": p.get("l_review_share", 1.0),
           "[planning] min_size_confidence": p.get("min_size_confidence", 1.0)}
    if bad := [f"{k} = {v!r} is not a number" for k, v in got.items() if type(v) not in (int, float)]:
        raise SystemExit("plan.py: " + "; ".join(bad))
    m, share, bar = (float(v) for v in got.values())
    bad = [] if 0 < m <= full else [f"[ai] planner_m_session_usd = {m:g}: above 0 and at most planner_session_usd "
                                    f"({full:g})"]
    bad += [f"{k} = {v:g}: outside [0, 1]" for k, v in list(zip(got, (m, share, bar)))[1:] if not 0 <= v <= 1]
    if bad:
        raise SystemExit("plan.py: " + "; ".join(bad))
    return m, share, bar


def size_path(gap: dict, bar: float) -> str | None:
    """The gap's size class, when trusted: planned_size exactly S, M, L or XL with a size_confidence whose TRUST is at
    or above ``bar``; else None (the full planner, reviewed). A replan (its state, which the fold sets by seq from the
    send-back, never by time) is None too, but for XL, which must split whatever."""
    cls, conf = gap["fields"].get("planned_size"), gap["fields"].get("size_confidence")
    if type(cls) is not str or cls not in CLASSES or type(conf) is not str or TRUST.get(conf, -1) < bar:
        return None
    return cls if cls == "XL" or gap["state"] != "replan" else None


def sampled(gid: str, share: float) -> bool:
    """An L plan picked for review: by the gap's id alone, so a retry picks the same."""
    return int(sha(f"l-review:{gid}"), 16) / 16 ** 40 < share


def wanted(cfg: dict, needed: bool) -> bool:
    return needed and (cfg.get("plan") or {}).get("review", "sample") != "off"


def small(cfg: dict, gap: dict, branch: str) -> int:
    """An S gap: its definition from its own title and text, no session, no review, a planning cost of 0."""
    f = gap["fields"]
    body = SMALL.format(branch=branch, title=" ".join(str(f.get("title") or branch).split()),
                        deps=", ".join(d.removeprefix("gap/") for d in fac.ids(f.get("depends_on"))),
                        text=str(f.get("text") or f.get("description") or "").strip(), confidence=f["size_confidence"])
    define(cfg, gap["id"], branch, body, "size-s", review=False, planned_at=time.time(), planning_cost_usd=0)
    return 0


def coverage(said: str, names: list[str]) -> tuple[str, list[str]]:
    """A split's one `<coverage>` block (what the parent must do, a `- ` point per line ending `(by: name, name)`),
    and what makes it unusable: not exactly one block, a point naming no sub-gap or one not of this split, a sub-gap
    no point names. Names are matched exactly."""
    blocks = COVER.findall(said)
    if len(blocks) != 1:
        return "", [f"a split needs exactly one <coverage>...</coverage> block, not {len(blocks)}"]
    points = [x.strip()[2:] for x in blocks[0].splitlines() if x.strip().startswith("- ")]
    out, named = [] if points else ["the <coverage> block has no `- ` point"], set()
    for p in points:
        by = [n.strip() for n in m[1].split(",") if n.strip()] if (m := BY.search(p)) else []
        out += [] if by else [f"coverage point {p[:80]!r} names no sub-gap: end it `(by: name, name)`"]
        out += [f"coverage point {p[:80]!r} names {n!r}, not a sub-gap of this split" for n in by if n not in names]
        named |= set(by)
    return blocks[0].strip(), out + [f"sub-gap {n!r}: no coverage point names it" for n in names if n not in named]


def size_of(body: str) -> dict | str:
    """The size line of a definition's `## Size budget`: {planned_size, size_confidence}, or why it cannot be taken
    (never a default class: a guess would be scored as the planner's). Never `size`: that is the groomer's field
    (backlog.py), on its own scale, and the solver ranks by it."""
    m = re.search(r"^## Size budget.*?$(.*?)(?=^## |\Z)", body, re.M | re.S)
    got = SIZE.search(m.group(1)) if m else None
    if not got:
        return "no size line `size: S|M|L|XL (confidence: low|medium|high)` in its ## Size budget"
    if got[1] not in CLASSES or got[2] not in CONFIDENCES:
        return f"size {got[1]!r} (confidence {got[2]!r}): the class is one of S, M, L, XL, the confidence low, medium, high"
    return {"planned_size": got[1], "size_confidence": got[2]}


def send_back(cfg: dict, gap: dict, why: list[str], **record) -> int:
    """A plan that failed the lint (its format, or a planner's answer that cannot be taken) back to the planner with
    why; the MOST_LINT-th parks it (a planner that cannot write the format)."""
    n = int(gap["fields"].get("plan_lint_failures") or 0) + 1
    if n >= MOST_LINT:
        import review
        fac.say("gap.measured", gap["id"], plan_findings=why, **record)
        review.park(cfg, gap, f"Its plan failed the lint {n} times:\n" + "\n".join(f"- {w}" for w in why),
                    "plan-lint", where="plan", kind="kill-rule")
    else:
        fac.say("gap.plan-sent-back", gap["id"], plan_findings=why, plan_sent_back_by="lint", plan_lint_failures=n,
                **record)
    return 0


def review_wanted(cfg: dict, gid: str) -> bool:
    """Whether the advisory plan review reads this gap's plan: [plan] review = all, off, or sample (1 in
    [plan] sample_every, 3, chosen by the gap's id)."""
    p = cfg.get("plan") or {}
    mode = p.get("review", "sample")
    return mode == "all" or (mode == "sample" and int(sha(gid), 16) % int(p.get("sample_every", 3)) == 0)


def define(cfg: dict, gid: str, branch: str, body: str, by: str, notes: list[str] = (), review: bool | None = None,
           **data) -> None:
    """A lint-clean plan made the gap's definition (run/defs/<branch>.md, created exclusively: never over one the
    coordinator wrote meanwhile, which is kept) and the gap ready; ``notes``: appended for the implementor to answer;
    ``review``: whether it is marked for the plan review (None: review_wanted, the sweep's)."""
    target = fac.run_dir(cfg, "defs") / f"{branch}.md"
    text = body + ("\n## Notes from the plan review (answer each)\n\n" + "".join(f"- {n}\n" for n in notes)
                   if notes else "")
    try:
        with target.open("x") as fh:
            fh.write(text)
    except FileExistsError:                              # the coordinator's definition: not the planner's size
        by = "coordinator"
        data |= {"planned_size": None, "size_confidence": None} if "planned_size" in data else {}
    fac.say("gap.defined", gid, definition=fac.rel(target), ready_at=time.time(), branch=branch, defined_by=by,
            plan_sha=sha(body), risks=sorted(set(re.findall(r"\blesson-\d+\b", body))),
            plan_review="wanted" if by != "coordinator" and (review_wanted(cfg, gid) if review is None else
                                                             wanted(cfg, review)) else None, **data)


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
    as a gap that exists (its id reused would merge old fields in), a name that is not lowercase words and dashes, a
    sub-gap whose budget is over SUB_GAP_MOST_LINES or names no number (counted as over), a dependency on a later
    sub-gap or on no gap, or a size line missing or not understood."""
    sizes = [f"{name!r}: {why}" for name, _, body in defs if isinstance(why := size_of(body), str)]
    if len(defs) == 1:
        return sizes + ([] if defs[0][0] == branch else [f"a single definition must be for {branch}, not {defs[0][0]!r}"])
    names = [d[0] for d in defs]
    out = [] if defs else ["the planner wrote no <definition>"]
    out += [f"sub-gap {name!r}: its size budget is {n} net lines, at most {SUB_GAP_MOST_LINES} (split it further)"
            if n >= 0 else f"sub-gap {name!r}: its size budget names no number of net lines (counted as over "
            f"{SUB_GAP_MOST_LINES})" for name, _, body in defs
            if not 0 <= (n := fac.budget_of(body, default=-1)) <= SUB_GAP_MOST_LINES]
    out += [f"a split into {len(defs)} sub-gaps: at most {MOST_SPLIT}"] if len(defs) > MOST_SPLIT else []
    for i, (name, _, body) in enumerate(defs):
        if name == branch or not fac.SAFE.match(name) or f"gap/{name}" in known or name in names[:i]:
            out.append(f"sub-gap {name!r}: not a new name of lowercase words and dashes")
        out += [f"sub-gap {name!r} depends on {d}, neither an earlier sub-gap nor a gap" for d in deps_of(body)
                if d[4:] not in names[:i] and d not in known]
    return out + sizes


def planner(cfg: dict, gap: dict) -> int:
    m_cap, share, bar = size_settings(cfg)              # before anything: no session under a bad setting
    f, branch, now = gap["fields"], fac.branch_of(gap), time.time()
    import intake
    import research as rs
    if where := intake.definition(cfg, gap):
        fac.say("gap.defined", definition=where, ready_at=now, branch=branch, defined_by="coordinator")
        return 0
    if (path := size_path(gap, bar)) == "S":
        return small(cfg, gap, branch)
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
    capped = cfg if path != "M" else {**cfg, "ai": {**cfg["ai"], "planner_session_usd": m_cap}}
    usd = float(capped["ai"]["planner_session_usd"])
    try:
        got = fac.attempt(capped, "planner", text, work)
    except BaseException:                                # a timeout, an error, a cancel: the whole reservation
        fac.say("gap.measured", ai_cost_usd=usd, planning_cost_usd=usd, sessions=1)
        raise
    if got is None:
        return 0
    said, cost = str(got.get("result", "")), got.get("total_cost_usd")
    cost = round(usd if cost is None else float(cost), 4)          # (no cost told: the reservation was kept)
    record = dict(contexts=[context], ai_cost_usd=cost, planning_cost_usd=cost, sessions=1)
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
    known = {g["id"] for g in gaps} | {f"gap/{g['fields'].get('branch')}" for g in gaps}
    cover, uncovered = coverage(said, [d[0] for d in defs]) if len(defs) > 1 else ("", [])
    whole = path == "XL" and len(defs) == 1 and defs[0][0] == branch
    xl = [f"an XL gap must split: not one definition for {branch} (sub-gaps of at most {SUB_GAP_MOST_LINES} lines)"]
    if wrong := problems(defs, branch, known) + uncovered + (xl if whole else []) or linted(cfg, defs):
        return send_back(cfg, gap, wrong, **record)
    if cover:                                            # the parent's plan, over any earlier split's (lesson-5)
        (fac.run_dir(cfg, "plans") / f"{branch}.md").write_text(f"<coverage>\n{cover}\n</coverage>\n")
    for name, title, body in defs:
        sized = dict(size_of(body), merged_lines=None, merged_lines_error=None)  # never scored on old lines
        if name != branch:
            fac.say("gap.requested", f"gap/{name}", title=title or name, source="plan", branch=name,
                    parent=[gap["id"]], depends_on=deps_of(body), requested_at=now)
            define(cfg, f"gap/{name}", name, body, "plan-split", review=True, planned_at=now, planning_cost_usd=0,
                   **sized)                              # (no class: reviewed; its planning paid on the parent)
        else:
            review = path is None or (path == "L" and sampled(gap["id"], share))
            define(cfg, gap["id"], name, body, "plan" if review else "plan-unreviewed", review=review, planned_at=now,
                   replanned=gap["state"] == "replan", **sized, **record)
    if defs[0][0] != branch:                             # a split parent merges nothing: no size of its own
        fac.say("gap.split", children=[f"gap/{d[0]}" for d in defs], split_at=now, planned_size=None,
                size_confidence=None, **record)
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
                for c in stopped), "split-watch", where="split", kind="split",
                until={"gaps": sorted(c["id"] for c in stopped)})
    return 0


def sweep(cfg: dict) -> int:
    """The plan lint's sweep: each gap not held by a run whose plan (run/plans/) waits in planned, or was sent back to
    replan by the old plan review (never by the lint: the planner writes those again): lint-clean, made the definition
    (the review's findings appended as notes); a planned one that fails the lint goes back to the planner."""
    for g in fac.items("gap"):
        f, p = g["fields"], fac.run_dir(cfg, "plans") / f"{fac.branch_of(g)}.md"
        old = g["state"] == "replan" and f.get("plan_sent_back_by") != "lint"
        if (f.get("lease") or {}).get("holder") or not p.is_file() or not (g["state"] == "planned" or old):
            continue
        body = p.read_text()
        if COVER.search(body):                           # a split parent's coverage: never a definition
            continue
        if not (found := lint(cfg, body)):
            define(cfg, g["id"], fac.branch_of(g), body, "plan-lint", notes=list(f.get("plan_findings") or []) if old
                   else [], released_from=g["state"])
        elif g["state"] == "planned":
            send_back(cfg, g, found)
    return 0


if __name__ == "__main__":
    fac.stop_on_term()
    if sys.argv[1:] in (["splits"], ["lint"]):
        sys.exit((splits if sys.argv[1] == "splits" else sweep)(fac.config()))
    cfg, item = fac.config(), fac.read_input()["item"]
    sys.exit(0 if fac.drain_holds(cfg) else planner(cfg, item))
