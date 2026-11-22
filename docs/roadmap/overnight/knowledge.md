# knowledge: the factory's knowledge and planning subsystem

depends-on: []

Branch `knowledge`, from main (358dde9), on the seed knowledge base (3032472: `dev/knowledge/{README,house-rules,
review-lessons,decisions}.md`). The owner, 2026-11-20: "some of this triviality and some of this laziness might be
caused by a dearth of contextual information... it would be good if we had some sort of research or planning subsystem
that you [the coordinator] would find useful... think of this ergostat instance as a resource for you." First attempts
kept failing reviews on the same classes of mistake (`dev/knowledge/review-lessons.md`) that a better brief would have
prevented. `factory2` (turn-on fixes, the gaps' dependencies) is in flight and touches `dev/bin`: brief.py changes stay
small, and origin/main is merged in once it lands.

## Definition of done

**Briefs carry knowledge.** `dev/bin/brief.py` assembles every brief (implementor, reviewer, and the new roles) with a
knowledge section built by `dev/bin/knowledge.py`: the house rules and the review lessons always; each decision whose
areas the gap touches; the definitions and "Where it stopped" of related gaps (what it depends on, its parent and
siblings, its GAPS.md section); past review findings that name the files the gap touches; and a module map (each
package's modules with the first line of their docstrings, generated from the checkout's main and cached by its sha, so
a merge refreshes it). Everything but the rules and lessons is bounded by a size budget (`[knowledge]` in
`dev/factory.toml`), in priority order, and each brief's recorded context lists the knowledge entry ids it carried
(`lesson-3`, `decision-...`, `rules-process`, `modules@<sha>`, `gap/...`, `review/...`) and what it dropped.

**A planner** (an `ai` block on Opus, pool 1) takes a gap at `open` that has no definition, reads the code, docs and
knowledge in a read-only clone of main, and writes its definition of done (acceptance tests by name, a size budget,
the review-lessons risks that apply, the files to touch, `depends-on:`) to `run/plans/<branch>.md`: the gap goes to
`planned`. A gap too large for one branch is split into sub-gaps (at most 6, each its own definition, `depends-on`
among them, `parent:` the gap), which go to `planned` themselves while the parent waits in `split` until every child is
merged (a join). At the join a judge says whether the parent is covered: that is the planner's coverage mapping (each
point of the parent named to the sub-gaps that build it) plus an AI judgment against main, not a proof. A sub-gap it
cannot read is never covered, and the second `short` parks the parent. Two measures say how well splits work:
`splits-covered` (the share of parents covered on their first judgment) and `split-budgets-held` (the share of merged
sub-gaps within their own size budget). gap/plan-by-size gates XL auto-split on `splits-covered ≥ 0.7` over at least
5 joins. It may open research questions (at most 3) first, and waits for their answers. **A plan review** (the
reviewer in plan mode: a cheap session given the definition and the lessons only) approves the plan, which is copied as
reviewed into `run/defs/` and the gap made `ready`, or sends it back to the planner with its findings; a second
failure parks it.

**A researcher** (an `ai` block on Opus, pool 1) takes `research` items (asked, answered): it reads the code, docs, the
record and the web where its session allows, writes a report with its sources to `run/research/<name>.md`, and its
summary on the item. Questions come from the coordinator (`dev/bin/ask.py "question"`, or `research.asked`) or a
planner.

**The librarian** (a program started by each `review.written`, with one small AI step that classifies the findings
against the lessons) proposes a "seen as" line for a new shape of a known class, and a new entry for a class found
twice that is not listed. A proposal is a `lesson` item and the gated action `knowledge-change`; approved, it becomes a
gap whose definition is the exact edit, built and landed through the normal pipeline.

**For the coordinator:** `dev/bin/status.py` (one screen: in flight, blocked and on what, failed and why, the queue,
spend today, first-pass yield, research), `dev/bin/ask.py`, `dev/bin/request.py` (a gap with `--depends-on`), and
`dev/bin/lesson.py` (a lesson by hand, as a knowledge gap).

**Modelled:** `dev/model/knowledge.yaml`: knowledge entries as a stock, lessons proposed, added and retired as flows,
the briefs' carried lessons related to first-pass yield; plan quality measured as the share of planned gaps whose
acceptance tests caught a failure before review, and the share of sub-gaps that merged on their first review.

## Acceptance tests

`tests/test_factory_knowledge.py`:

- `test_brief_carries_knowledge_within_budget`: an implementor brief carries the rules and lessons, a relevant
  decision and not an irrelevant one, stays within its budget with a small budget dropping lower-priority sections, and
  records the entry ids it carried.
- `test_module_map_from_main_cached_by_sha`: the map lists modules with their docstrings' first lines, is cached by
  main's sha, and a new commit on main makes a new one.
- `test_related_gaps_and_past_findings`: a dependency's "Where it stopped" and a past finding on a touched file reach
  the brief.
- `test_planner_writes_plan_and_review_makes_ready`: the planner (stand-in) writes the plan, the gap goes to planned,
  the plan review approves it and the gap is ready with the reviewed text in `run/defs/`.
- `test_plan_review_sends_back_then_parks`: a failed plan review sends the gap back to open with findings; a second
  parks it.
- `test_planner_splits_into_sub_gaps`: sub-gaps requested with `depends_on` and `parent`, the parent in `split`; an
  existing id or an unsafe name is refused; more than the limit is refused.
- `test_researcher_answers`: a research item answered with a report file and a summary.
- `test_librarian_proposes_from_a_finding`: a new shape of a known class proposes a "seen as" line; a new class found
  twice proposes an entry; once does not.
- `test_cli_tools_on_a_fixture_instance`: `status.py`, `ask.py`, `request.py` and `lesson.py` against a fixture
  instance.
- `ergostat check` on the root model reports no errors (`test_the_factory_model_loads` and the knowledge kinds).
- The unit suite and the four browser files under `scripts/suite_watch.py`, rc 0.

## Size budget

500 net lines of code in `dev/bin` and ergostat's core (outside `tests/`, `docs/`, `dev/model`, `dev/prompts` and
`dev/knowledge`).
