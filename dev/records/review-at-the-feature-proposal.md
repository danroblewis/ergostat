# review-at-the-feature-proposal: Proposal: review and full testing once per feature, not once per task

The owner: "we don't need to do reviews for every change. In Jira, a ticket may have multiple tasks. We may have several tasks that contribute to a feature branch, and only the feature branch needs to go through review and testing." Write `docs/proposals/review-at-the-feature.md`.

Settle:
1. A group of items (a feature, milestone or epic) with its own integration branch: tasks merge into it with light checks; the group is reviewed and fully tested once before it reaches main. As a general core option for any group relation, not only gaps.
2. What checks a task still gets on its way into the feature branch (lint, targeted tests, a build), and what only the feature gets.
3. Keeping a feature branch current with main, conflicts between features, and how long a feature may stay open.
4. Review effort and findings at the feature level against per-task review, using this factory's record: cost, rework, and what per-task review caught.
5. How this fits the merge queue, stacking and the dashboard's pipeline row.
6. When per-task review is still worth it (risky paths), so the choice is per group or per path.
7. The build split.

Definition of done.
1. The proposal settles all seven, with numbers from the record.
2. A worked example on three recent related gaps shows the time and review cost each way.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: written. `docs/proposals/review-at-the-feature.md` settles the seven points: a core relation key
`integrates` on a group relation (section 1a: a scoped start among members, progress, two limits with ceilings,
`check` refusals), the factory's `feature` relation and `integrated` state with the group being a gap (1b); the
checks a member gets and what only the group gets (2); forward merges of main, conflicts, `most_open: 24h` and
`most_lines: 1200` (3); review effort and findings from the record (4); the queue, stacking and the pipeline row (5);
per group and per path, by an allowlist `light_paths` (6); the planner's split as the first group and the suite split
unchanged (7). Section 8 is the worked example on agent-show-page, agent-names-link-to-their-page and
agent-page-narrow-ai-and-decision, three ways. Two owner questions, one sentence each.

Decisions taken without the owner, each easy to undo:
- "The build split" (point 7) is read as both the planner's split (a split parent as the group) and the suite split
  (`[suites] build` against `unit`); the proposal settles both.
- The numbers are from what this clone holds (git history, the records, the review lessons in the brief,
  dev/factory.toml), as the boundary forbids measuring the live instance. Costs are therefore ceilings (sessions
  times the caps), never spend; the review-round shares are mentions in the records' text, said as an upper bound;
  the worked example's approval times after round 2 are not in git and are estimated from the record's own
  durations, said as such. The proposal names the live readings (`ai_cost_usd`, `reviews_n`, `fix_rounds`,
  `approved_at`) that replace them.
- No code: the definition asks for the proposal only. 0 net lines outside tests, docs and dev.

Run here: ruff (clean); tests/test_gaps_doc.py (9 passed: it renders every record's entry, this one included). Not
run: the unit suite and the browser files (no code or test changed).

Round 2: both blocking findings answered (there were no others).
- A member leaving a group (past `most_open`, section 3) no longer has its `stacked_on` cleared: it keeps the group
  as its base, is judged on its own commits against `stack_base`, is reviewed only once the group is approved, and the
  queue lands the two bottom-up, whole or none; a member with no commits yet is rebuilt from main. A new paragraph,
  *Dissolving a group* (fewer than two light members, section 6's bullet now points to it): the group branch is never
  landed, a member carrying no other member's merge is rebuilt from main, any other is stacked on the members it
  carries as reviewed bases. Chosen as the most reversible: it reuses today's stacking and changes no member's history.
- Section 8, the path-rule case: the dependants start at 02:35, so narrow-ai is built about 02:51, reviewed and fixed
  about 03:25, approved and integrated about 03:45, and the group approved about 04:55 (was 05:50); the table and the
  bullet now say 04:55 against about 04:40 per-gap (04:19 plus about 20 minutes, the per-gap row now says so instead
  of "after 04:19"), some 15 minutes later.

Run here in round 2: ruff; tests/test_gaps_doc.py.

## Entry

section: The factory (ergostat on ergostat)
done: 2026-11-24 The proposal for review and full testing once per group: docs/proposals/review-at-the-feature.md.

- **Review and full testing once per feature, not once per task** (proposal written, `review-at-the-feature-proposal`;
  `docs/proposals/review-at-the-feature.md`): a group relation may declare `integrates`, so its members merge into the
  group's branch after light checks (ruff, affected tests, new findings) and the group is reviewed and fully tested
  once; risky paths keep a review of their own. Left: building it (core key, then the factory's `feature` relation,
  split parents first), after the owner's two questions.
