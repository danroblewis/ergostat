# Review and full testing once per group, not once per member

The owner: "we don't need to do reviews for every change. In Jira, a ticket may have multiple tasks. We may have
several tasks that contribute to a feature branch, and only the feature branch needs to go through review and
testing."

Today every gap is its own unit from build to main: the implementor builds it, a reviewer judges it, the merge queue
lands it, and a fix round follows each review that sends it back. This proposal settles how a **group** of items (a
feature, a milestone, an epic, a split parent) can instead be integrated on a branch of its own, with light checks per
member and one review and one full test of the group before it reaches main.

The proposal in one line: **a group relation may declare that its members integrate into the group; ergostat's core
counts and orders them that way, and the model's own blocks do the branch, the checks and the review.** It is off
unless a model declares it. This factory is the first user, and only for groups it names (section 6); everything
else keeps per-gap review.

Words: core text says *item*, *group* and *member* (ergostat ships no unit of work, CLAUDE.md invariant 1). The
factory's members are gaps and its groups are gaps too (section 1b). "Task" appears only in the owner's words.

## Where the numbers come from

The live instance was not read (the owner's boundary of 2026-11-23). Every number here is from what this clone
holds, and says which:

- **git history of main**: commit and merge times, which gaps landed together. 589 merges on main's first-parent
  line, 454 of them `factory/` branches; 198 of those merges on 2026-11-23 (local time), 125 on 11-22, 116 on 11-21.
- **the gaps' records** (`dev/records/*.md`, 395 files, 320 with a "Where it stopped"): what each round found and
  changed, in the implementor's words.
- **the review lessons** as the implementor brief of this round carries them (13 lessons, 123 "Seen as" examples):
  what per-gap review has caught, curated by the librarian.
- **dev/factory.toml**: the session caps (implementor $15, reviewer $5, `[ai]`), the size limits.

What this clone does not hold: each session's real cost (`ai_cost_usd` on the gap, the run ledger), review hours
(`review_hours`), and approval times (`approved_at`). Costs below are therefore **ceilings** (sessions times caps),
never spend; section 4 names the readings that would replace them.

## 1. A group with its own integration branch

### 1a. The core option (general; off unless declared)

A group relation (`group: true`, SPEC §5a *Relations*) gains one key, `integrates`:

```yaml
items:
  part:
    states: [todo, doing, checked, integrated, done, dropped]
    relations:
      whole: {kind: whole, group: true, precedence: false,
              integrates: {at: [integrated], most_members: 8, most_open: 48h}}
      after: part                 # precedence among parts, as today
```

What core does with it, and nothing more:

1. **A member in an `at` state is integrated.** For a precedence relation between two members of the **same
   group**, it counts as finished: the member after it is unblocked (`takes: {unblocked: true}` may take it). For an
   item **outside** the group it still blocks until the group itself is in a finished state. This is `starts_at`
   (§5a, *Starting before a target finishes*) scoped to the group, so the critical path, slack and the completion
   estimates stay finish-to-start, as they do for `starts_at`.
2. **Progress per group** counts an integrated member as *in progress* while the group is unfinished, and as *done*
   once the group is finished (its `done_when` applies as today). Nothing moves the member: ergostat adds nothing of
   its own accord (invariant 12). A model that wants the member to reach `done` writes that event (the factory's queue
   does, section 5).
3. **Two limits with a ceiling** (lesson-4). `most_members` (1 to 50): an item naming the group past it is said on the
   group's row and in `check` (`integrates-full`), and `takes` with `where: {integrates_room: true}` does not take
   it. `most_open` (1 h to 30 d): the group row says `open_hours` (from its first member's move into an `at` state,
   by the record's `seq`, never by stamps, lesson-2) and `overdue` once past it. Both are readings a goal may hold; core
   acts on neither.
4. **`check` refuses** (`bad-integrates`): `integrates` on a relation that is not a group, on a remote's kind, or on
   one whose field folds by anything but `replace` (a member is in one group, as a milestone's are); an `at` state the
   member kinds lack, their first state, or a finished one; a limit outside its range or not a number (a missing or
   unreadable value is refused at the key, never read as 0 or unlimited, lesson-3).
5. **The Items API and the group row** give each member's `integrated` (true/false), and the row gains `integrated`
   and `open_hours`. No new page or panel: it is the existing group row and the Graph's group frame.

Everything else is the model's: which branch, which checks, who reviews and when the group is "built" are blocks
with `takes` on states, as any other work. Core never knows about git.

### 1b. The factory's choice (its own model; the first user)

- The **group is itself a gap** (`kind: gap`), as a split parent is today. So the merge queue, stacking, the time in
  each state, the kill rule and the dashboard's pipeline row all keep working on one kind. Its branch
  `factory/<group>` is the integration branch, made from main; its definition is the group's (the planner's
  coverage block for a split, or the owner's feature entry).
- The gap kind gains the state `integrated` and the relation
  `feature: {kind: gap, group: true, precedence: false, integrates: {at: [integrated], most_members: 6, most_open: 24h}}`
  (`most_open` from section 3).
- A member is built **on the group's branch head**, the way a stacked gap is built on its base today
  (`stacked_on: [{gap: GROUP, sha}]`, `stack_base`): its net lines, strays and new check findings are measured
  against that base, so the member is judged by its own commits only.
- The member's light checks (section 2) pass, then the program block `integrate` (no AI) merges it `--no-ff` into
  the group's branch under the drop's ref lock, moving the ref only from the value it read (as stack-forward does,
  lesson-1), and records `gap.integrated` with the merge sha. A refused ref move retries next pass; it is never
  written over.
- When every member is integrated, or `most_open` has passed (section 3), the group gap is `built` and goes to the
  reviewer like any gap.

## 2. What a member still gets, and what only the group gets

| Check | Member, on its way into the group | Group, before main |
|---|---|---|
| ruff | yes (`[suites] ruff`) | yes, again in the queue |
| targeted tests | yes: `[suites] build` (`scripts/affected_tests.py`: its changed tests and `tests/test_<module>.py` of its modules) | |
| new check findings | yes (`[suites] check`, branch against its base) | yes, the group against main |
| strays, size budget | yes, against its own definition | the group's total against `[features] most_lines` |
| failing test on main or on the base | as today (`onmain.py`; a test failing on the group branch's base is the group's, not the member's) | |
| definition of done, acceptance tests named | the member's implementor runs them, as today | the review checks every member's |
| full unit suite | no | yes, once before review (the group's `built`), and in the queue |
| the four browser files | no (`build_browser = false` as today) | yes, before review when the group's diff names a `browser_paths` path, and in the queue |
| demo_check, host suite | no | in the queue, as today |
| AI review | **no** (except section 6's paths) | **once**, the whole group against main |
| acceptance measurements (`measure-runs`) | no | on the group's head, as today on a gap's |

The full unit suite before the group's review is new: today the queue is a gap's first full run, and a red batch costs
one gap. A red group costs every member's work, and the review would be wasted on a branch that fails, so the run is
moved to before the review. It costs one unit run per group (the queue's own unit run stays).

The group's review reads the whole diff, but **member by member**: its brief lists each member's definition and its
merge commit on the group branch (the first-parent line), then the group's own definition. Findings name the member
they are about (`member: gap/X`, or `group` for one across members), so the librarian still classes each finding and
`lessons-recurring` still compares it with that member's brief. Section 4 says why it must still read every line.

## 3. Keeping current with main, conflicts, how long a group stays open

**Current with main.** A block `feature-forward` (the stack-forward pattern, `dev/bin/stack.py`) merges main into
each open group branch when main moves: never a rebase, so the members' merges stay on the first-parent line the
review reads. Main moved in six landings on 2026-11-23 between 16:28 and 22:14 local (about once every 70 minutes),
so a group open a day takes in the order of 20 merges of main. A member being built is never touched; its next round
merges the group head, as a stacked gap merges its base today.

**Conflicts.** A conflict merging main into a group sends the **group** to `fix` with the files (not counted as a
failed gate, as stack-forward's are not); the group's implementor session resolves it on the group branch. Two open
groups touching the same files meet only through main: the first to land wins, the second gets the conflict at its
next forward merge. To keep that rare, the planner, which is already given the files active gaps touch (the task
graph, 40 lines), places a new gap that touches an open group's files **in** that group when it is the same work, or
gives it `depends-on` the group otherwise. Nothing new is needed for that beyond saying it in the planner's prompt.

**How long.** `most_open: 24h` for this factory. The three related gaps of section 8 landed four hours after the
first one's definition was committed, all in one landing; a group of three to six members fits a day. A milestone
need not: the upkeep cycle is 7 days (`[milestones] upkeep_days`), and the records name 19 milestones with 1 to 8
gaps each (64 records). So a milestone is not a group by default (section 6). Past `most_open`, no new member joins (the take's `where`), members not yet built are
taken out of the group, and the group goes to review with what is integrated. A member taken out goes the per-gap
way (its own review), but **keeps `stacked_on: [{gap: GROUP, sha}]`**: its branch was made from the group head and
carries the other members' merges, so clearing the stack would let the queue land their unreviewed code with it and
put their lines in its diff against main (lesson-7). Stacked, it is judged against its base (`stack_base`) on its own
commits; its own review is taken only once the group is approved, so it is judged on a reviewed base as every stacked
gap is today (`starts_at: [approved, queued, push-pending]`); and the queue lands the two bottom-up, whole or not at
all (dev/README.md, *Stacked gaps*). A member that has no commits yet is instead rebuilt from
main (its branch made again from main, no stack). A group past `most_open` + 24 h is a trigger of the pipeline manager
(`overdue`, read from the group row), never an automatic park.

**Dissolving a group.** When a group is not reviewed as one (section 6: fewer than two light members), its branch is
never landed and each member is reviewed on its own; none is unstacked. A member whose branch carries no other
member's merge (its base held only main) is rebuilt from main. Any other member is stacked on the members whose merges
its branch carries (`stacked_on` lists each, by the merge sha on the group branch), as reviewed bases: its review is
taken once they are approved, and the queue lands them bottom-up, whole or not at all, so no member reaches main ahead of the review
of what it was built on.

**Size.** `[features] most_lines = 1200` net lines (twice `plan_budget_most`); a member whose merge would take the
group past it is not integrated and is sent back to the planner to move to another group, said on the gap.

## 4. Review effort and findings: group against per-gap, from the record

**What per-gap review costs.** Each send-back is one more review and one more implementor round: a ceiling of
$5 + $15 = $20 a round, and an hour or more of the gap's time. Of the 320 records with a "Where it stopped", 229 (72%)
mention a round 2, 135 (42%) a round 3, 84 (26%) a round 4 and 61 (19%) a fifth or later. These are mentions in the
text, so an upper bound on review rounds: some rounds were sent back by the queue or by stack-forward, and a few
mentions are of another gap's rounds. The exact count is each gap's `reviews_n` and `fix_rounds` in the live record.

**What per-gap review caught.** The 123 "Seen as" examples of the review lessons, by where the defect lives:

| Where the defect was | Examples | Lessons |
|---|---|---|
| inside one change's own diff | 113 (92%) | lesson-3 fail-open 45, lesson-8 claim wider than code 19, lesson-5 reused id 13, lesson-9 test that can't fail 12, lesson-6 cancel 6, lesson-1 lock 3, lesson-2 order by time 3, lesson-10 flakes 4, lesson-13 outside the gap 4, lessons 4, 11, 12 one each, and one of lesson-7 (suites never run) |
| two changes meeting (each passed alone) | 4 (3%) | lesson-7: a HEAD carrying another branch's merges, tests pinning a module another gap adds, a new query ignoring old filters, a batch-shared commit range |
| GAPS.md spliced by a merge | 6 (5%) | lesson-7; removed by structure since (entries in records, merge-pipeline-gaps-entries-in-records) |

So per-gap review has caught almost entirely **local** defects, and almost none of the kind only a group view sees.
Two consequences, both settled here:

1. **The group review must still read every member's diff.** The saving is fewer sessions and fewer round trips,
   never fewer lines read. A single session over up to 1,200 lines may well miss more of the local classes than five
   sessions over 250 lines each; nothing in the record says how much, because the factory has never reviewed a diff
   that large. So the switch is measured (below) and can be turned off per group.
2. **The group review gains what per-gap review lacks:** the members together (the 4 "two changes meeting" cases
   happened between gaps that were reviewed apart) and the definition's coverage across members (today a third
   session, the join judge, does that for splits; section 7).

**Rework.** Per-gap review finds a defect while its implementor's work is the newest thing and before anything is
built on it. Group review finds it after the other members are built on the same branch, so a fix can touch them too.
In section 8's example none did (the fixes were inside one member's files), but the record does not say how often
that holds. The fix round is one session on the group branch with every finding, so three findings in two members
cost one fix session, not two.

**How the switch is judged** (readings that already exist, compared over groups against unsplit gaps of the same
size class): `gate-catches-review` and `gate-catches-queue` per merged net line (a review that misses more shows as
more queue and triage catches); `regression-escapes-from-reverts` (a defect past both); `loop-hours` and the AI cost
per merged net line (`ai_cost_usd` over `net_lines`); `lessons-recurring`. A group whose members' later catches rise
past per-gap's is the evidence to narrow section 6's paths.

## 5. The merge queue, stacking and the dashboard's pipeline row

- **Merge queue.** The group is one approved gap in the queue's line (`waiting: {kind: gap, state: approved}` is
  unchanged), tested and landed as one: unit, browser on its paths, host and demo, as any gap. Its members never enter
  the queue. On landing, the queue writes `gap.merged` on each integrated member with the group's merge sha
  (`merged_with: gap/GROUP`), so `gaps-landed`, cycle hours and the backlog count them as today. A red group is
  blamed as one (the queue's bisection splits batches, not branches); triage's rerun and the fix path then go to the
  group. Today's landings already batch: on 2026-11-23 the queue landed 7, 8, 7, 5, 11 and 22 merges at a time, so a
  group of three is one entry in a batch, not three.
- **Stacking.** A member stacks on its group's branch (section 1b), which is unreviewed: that is the point of the
  option, and it is allowed only inside a group (`integrates.at` scoped to the group, section 1a.1). Across groups
  nothing changes: a group, or a gap, stacks on another group only once that group is approved
  (`starts_at: [approved, queued, push-pending]`), and the queue lands a stack bottom-up, whole or not at all.
- **The dashboard's pipeline row** (`batch` kind, `pipeline: {title: Merge queue, ...}`, SPEC §5a *Stages*). No
  change of shape: the row's waiting line shows the group as one approved gap, its title from the gap's `title`, and
  its member count from a new shown field `members`. The stages are the queue run's, unchanged. Integration is not a
  queue stage and does not appear there; it shows in the group's progress row on the Items page (members integrated
  of total) and in the Graph's group frame, which already draw a group relation.

## 6. When per-gap review is still worth it: per group and per path

**Per group.** The option is declared per relation, and the factory's model declares it only on `feature`, which a
gap names only when the owner or the planner puts it there. Milestones and every gap with no `feature` keep per-gap
review. That is the reversible start: deleting the relation key, or a group's members' `feature` field, returns them
to today's path.

**Per path.** Inside a group, a member is integrated after light checks only when **every** path its diff changes
matches `[features] light_paths`, an allowlist (lesson-8: a guard is an allowlist), first:

```toml
[features]
light_paths = ["ergostat/web/**", "docs/**", "examples/**", "tests/**", "dev/records/**"]
most_lines = 1200
review_session_usd = 10.0
```

A member touching anything else (the engine, leases, the budget, the sandbox, `dev/bin/`, `scripts/`, the record's
writers) is reviewed on its own as today, **then** integrated, and the group review reads its diff as already
reviewed (only for how it meets the others). A diff that cannot be read counts as not light (lesson-3). The reason is
the table in section 4: the classes that have done real harm when they landed (lesson-1 locks, lesson-4 limits, which
kernel-panicked the Mac, lesson-6 cancel, lesson-11 destructive paths) live in those paths, and are the ones a
dilute review must not miss. The record here does not say which paths each finding was in, so the list is a first
guess from the lessons' examples, to be narrowed or widened by section 4's readings.

## 7. The build split

Two splits already exist, and the option fits both.

**The planner's split** (dev/README.md, *Plans*): a gap too large for one branch becomes sub-gaps of at most 250 net
lines each, each reviewed and landed on its own; the parent waits in `split`, then `joined`, where the join judge (a
third AI session) reads every sub-gap's definition and last review against the parent's coverage block. A split
parent is already a group (`parent` is a group relation) and already a gap. Under the option it **is** the feature
(the planner writes `feature` as well as `parent` on each sub-gap; `parent` is not given `integrates`, so a split
made before, or one the owner keeps per-gap, is unchanged): its sub-gaps integrate into `factory/<parent>`, the parent is built once they are all integrated, and its one review
is also the join: the coverage block is in its brief, and `short` is one of the review's findings. That removes the
join judge's session and every sub-gap's review, and `split-overhead` (the parent's and its children's AI cost over
the median unsplit gap's of their class) is the reading that says whether it paid. This is the factory's first use:
split parents first, owner features second.

**The suite split** (`[suites] build` against `unit`): unchanged in kind. A member runs ruff and `build` (its
affected tests), never the whole unit suite, as every implementor round does today; the group runs the whole unit
suite before its review and every suite in the queue (section 2). `build_browser` stays false for members.

## 8. Worked example: the Agent page (three related gaps)

`agent-show-page`, `agent-names-link-to-their-page` and `agent-page-narrow-ai-and-decision`, all three in the
milestone `agent-show-page`, the second and third depending on the first. Times are from git (UTC, 2026-11-24);
rounds and findings from their records.

**As it happened (per-gap review).**

| Gap | Definition | Round 1 built | Review 1 | Round 2 | Net lines |
|---|---|---|---|---|---|
| agent-show-page | 02:09 | 02:31 | 2 blocking findings: the render sweep missed nested demos; `noSpec` removed more than the reference | 03:22, then approved | about 198 |
| agent-names-link-to-their-page | 03:27 (stacked on show-page's approved head) | 04:00 | approved | | +5 |
| agent-page-narrow-ai-and-decision | 03:29 (stacked) | 03:45 | 1 blocking finding: only the newest span's counts shown | 04:19, then approved | about 229 |

All three landed in one queue landing of 22 merges at 06:14. Sessions: 5 implementor (3 builds, 2 fixes) and 5
reviews: a ceiling of 5 × $15 + 5 × $5 = **$100**. The two dependants waited from show-page's first build (02:31) to
its approval after round 2 (by 03:27): **56 minutes** on the critical path, the review loop of the first member.

**As a group, every member light** (the owner's model, without section 6's path rule). Show-page passes its light
checks at about 02:35 and is integrated; the other two start then on the group branch, 52 minutes earlier, and with
their own build times (33 and 16 minutes) all three are integrated by about 03:10. The group (about 432 net lines)
gets one review. Assuming it finds the same three findings (the record cannot say; section 4), one fix session
answers all three, and a second review approves. Using the record's own durations (review and fix of show-page:
50 minutes from its build to its round-2 commit; narrow's: 34 minutes) and about 20 minutes for the second review,
the group is approved at about 04:20. Sessions: 4 implementor (3 builds, 1 fix) and 2 reviews at the group cap: a
ceiling of 4 × $15 + 2 × $10 = **$80**, three review sessions and one fix session fewer.

**As a group, with the path rule.** Show-page (`ergostat/web/**`) and names-link (`ergostat/web/static/`) are light.
Narrow-ai adds `ergostat/agent_means.py` and changes `ergostat/history.py`, which writes the record, so it is
reviewed on its own (its round-1 finding is found there, as it was) and integrated once approved. The dependants
start at 02:35 here too, so with the record's own durations narrow-ai is built at about 02:51 (16 minutes), reviewed
and fixed by about 03:25 (34 minutes), and approved and integrated at about 03:45 (20 minutes for its second review);
names-link is integrated at about 03:08. The group review then reads show-page and names-link fully and narrow-ai for
how it meets them; it starts once narrow-ai is integrated (03:45), so with the same durations as above (50 minutes to
review and fix, 20 for the second review) the group is approved at about 04:55. Sessions:
5 implementor (3 builds, narrow's fix, the group's fix) and 4 reviews (narrow 2 at $5, the group 2 at $10): a ceiling
of **$105**.

| Way | Reviews | Implementor sessions | Ceiling | Dependants start | All approved (about) | Landed |
|---|---|---|---|---|---|---|
| per-gap (as happened) | 5 | 5 | $100 | 03:27 | 04:40 (narrow-ai's round 2 at 04:19 plus about 20 minutes; the record's `approved_at` is not in git) | 06:14 |
| group, all light | 2 | 4 | $80 | 02:35 | 04:20 | 06:14 (same landing) |
| group, path rule | 4 | 5 | $105 | 02:35 | 04:55 | 06:14 (same landing) |

What the example shows, without stretching it:

- **The saving is sessions, not time.** The dependants start 52 minutes earlier, but the one review now waits for the
  last member, so the group is approved at about the time the per-gap way was, and the landing was the same queue
  run either way (the queue's wait, about two hours here, dominated).
- **The path rule took the saving away here.** With one of three members on a risky path, the group pays for that
  member's own reviews and still for two group reviews: $105 against $100 at the ceilings, and approved at about
  04:55 against about 04:40 per-gap (narrow-ai's round 2 at 04:19 plus about 20 minutes of review), some 15 minutes
  later. The two light
  members needed only 3 per-gap reviews between them ($15), less than two group reviews at $10. On the record's
  average they would need more: the mentions of section 4 give about 1 + 0.72 + 0.42 + 0.26 + 0.19 = 2.6 review
  sessions a gap (an upper bound), so two light members about 5.2 ($26). Settled for the factory's model: a group
  needs **at least two light members**, else the group is dissolved: no group review is held and its members go the
  per-gap way, each rebuilt from main or stacked on the members it carries (section 3, *Dissolving a group*; the
  `integrate` block checks it when the group would be built, and says so on the group); and the group's own rounds
  are measured (section 4) before the bar is lowered or raised.
- **What would have been lost:** nothing visible here. The three findings were each inside one member's files, and
  the one cross-member decision (names-link left the row link as show-page made it) was the implementor's own,
  written in its record. Whether one review of 432 lines finds all three is the open measurement of section 4.
- **The ceilings are not spend.** The real figures are each gap's `ai_cost_usd` in the live record
  (`ergostat item gap/agent-show-page` and the other two), which the coordinator can read; section 4's readings
  then replace the ceilings.

## What is built, in what order (not in this gap)

1. Core: `integrates` on a group relation (section 1a): compile and `check`, the scoped start in the relations'
   status, the group row's `integrated` and `open_hours`; SPEC §5a. Tests: a member after an integrated one is
   unblocked and an outsider is not; progress counts it in progress then done; each refusal; limits at and past
   their ceilings.
2. Factory: the `feature` relation and the `integrated` state on the gap kind; `integrate` and `feature-forward`
   blocks; implement.py building a member on its group head; review.py's group brief (members' definitions and
   merges, findings with `member:`); the queue writing `gap.merged` on members; `[features]` in dev/factory.toml with
   `light_paths`, `most_lines`, `review_session_usd`.
3. The planner's split as the first group (section 7), then owner features.

## Questions for the owner

1. Should the first groups be only the planner's splits, with an owner's feature declared by hand after the first
   five have been measured?
2. Is `ergostat/web/**`, `docs/**`, `examples/**`, `tests/**` and `dev/records/**` the right list of paths whose
   changes skip a review of their own inside a group?
