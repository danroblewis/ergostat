# How much review: a setting chosen from what review is measured to give

The owner: "when we do review cycles, we get a certain type of value out of them, and we should know what value we get
from review cycles and we should be able to manipulate how much review we do based on the value we get from it."

Today every gap gets the same review: an Opus session judges the built branch, every send-back is a fix round and
another review, and two failed reviews park it. This proposal settles how to **measure** what that buys, how to
**test** a lower amount on a random share of low-risk work, and how a model **declares** review levels by risk with
a controller that moves them from measured escapes and cost.

The proposal in one line: **a kind may declare levels, an ordered list its items are placed on by rules over their
fields (first match, the strictest when none matches), with an optional randomised trial and a controller that moves a
rule's level within declared bounds; the model's own blocks decide what each level means.** Core never knows what a
review is. It is off unless a model declares it. This factory is the first user: its levels are `none`, `after`,
`one` and `full`, declared in its own model.

Words: core text says *item*, *kind*, *field*, *level*, *rule*, *trial* and *arm*. *Gap*, *review*, *merge* and *main*
are the factory's.

## Where the numbers come from

The live instance was not read (the owner's boundary of 2026-11-23). Every number is from what this clone holds:

- **git history of main**: 590 merges on main's first-parent line, 454 of them `factory/` branches (the companion
  proposal's count, `docs/proposals/review-at-the-feature.md`); every commit whose message says `This reverts commit`
  or starts `Revert`; the paths each of the last 40 merges changed.
- **the gaps' records** (`dev/records/*.md`, 321 with a "Where it stopped"): rounds and findings, in the implementor's
  words.
- **the review lessons** as this round's implementor brief carries them: 13 lessons, 123 "Seen as" examples, each one
  a defect a review found and the librarian kept.
- **dev/factory.toml**: session caps (implementor $15, reviewer $5, librarian $0.25), `kill_after = 6`, the suites.
- **dev/bin/risk.py and escapes.py**: what the factory already counts as an escape.

Not in the clone: each session's real cost (`ai_cost_usd`), each gap's `reviews_n` and `fix_rounds`, every review's
full finding list (the `review/<branch>-N` items and the librarian's classes), `approved_at`, the `main-broken`
interventions and `caused_by` links. Money below is therefore **ceilings** (sessions times caps), never spend, and
counts from the records' text are **upper bounds**. Section 1d lists what replaces each.

## 1. What review is measured to give

### 1a. Findings by class

The 123 examples are curated (the librarian keeps one per new shape), so they show the **mix** of what review finds,
not its volume. By lesson (the librarian's class):

| Lesson | Examples | | Lesson | Examples |
|---|---|---|---|---|
| 3 fail-open on a missing input | 45 | | 7 two things merged | 11 |
| 8 claim wider than the code | 19 | | 6 work running after cancel | 6 |
| 5 stale state under a reused id | 13 | | 10 load-dependent flakes | 4 |
| 9 a test that cannot fail | 12 | | 13 outside the gap | 4 |
| 1 check-then-write, 2 order by time | 3 each | | 4 limit, 11 destructive path, 12 every finding | 1 each |

By the harm the defect would do if it landed (my reading of each example, one class each, so approximate):

| Harm class | Examples | What is in it |
|---|---|---|
| **severe**: machine, money, secrets, lost data, gates bypassed | 21 (17%) | lesson-4's 5,000 processes, lesson-6's six, lesson-11, lesson-1's three, and nine of lesson-3 (an uncapped `claude` call, a negative cost freeing budget, a token copied back unscrubbed, the only copy of a session deleted, two trust decisions, a library's words in an AI prompt, a budget unrecorded on timeout, a full node counted as headroom), and lesson-8's quarantine list read from the tree under test |
| **functional**: wrong numbers, wrong page, wrong state shown | 68 (55%) | most of lesson-3, all of lesson-2 and lesson-5, most of lesson-8 |
| **process**: no effect on what runs, but the net is weaker | 34 (28%) | lesson-9's 12, lesson-10's 4, lesson-13's 4, lesson-12, lesson-7's GAPS.md splices (6, impossible since entries moved into records) and its suites-never-run, and six lesson-8 claims made in records rather than code |

By where the code lives: about 28 of the 123 (23%) are in `ergostat/web/static/` (stale DOM rows, Deny handlers,
labels, browser tests that cannot fail); the rest are in the engine, the factory's `dev/bin/` and `scripts/`.

### 1b. How many would have reached main

Every finding was made on a branch whose own checks (ruff, the affected tests, new `check` findings, strays) had
passed: that is what sends it to review. Without review, what stands between it and main is the queue's full unit,
browser (on `browser_paths`), demo and host suites. By their nature most review findings pass those: an untested
missing-input path, a claim in the docs, a test that cannot fail, a race the tests never open. Of the 123, the queue
could plausibly have stopped only the 4 "two changes meeting" cases and the 4 flaky-timing ones; **the other 115
(93%) would have reached main.** That is an estimate from the classes, not a measurement; the trial (section 2)
measures it directly, as the share of after-merge reviews with a blocking finding.

### 1c. Escapes found later

- **Reverts on main** (what `escapes.py` counts): **0 gap merges reverted** in 454. The three reverts in main's
  history are a prototype reverted as planned (93553283), a change reverted on its own branch before merge (02089d9c,
  continue-branch's lease fix) and a commit made straight to main, not a gap (95e1a1fd, the light palette).
- **In the lessons themselves**: at least 2 of the 123 passed review and were found on main later (lesson-10: a test
  reading the real clock against fixed 2027 timestamps, and a fixed 12 CPU-s bound that went red as the tree grew).
- **Not in the clone**: `main-broken` interventions blamed on a gap, `broke_main`, and `caused_by` links, which
  `risk.py` also counts as escapes.

With 0 reverts in 454, the revert rate's 90% upper bound (Gamma, shape 0.5, as `risk.py`) is 1.35 / 454 = **0.3%
per merged gap**. That rate is under today's full review; nothing yet says what it is under less.

### 1d. The cost: time, rework and money

From the records' text (the companion proposal's count, upper bounds): of 320 records with a "Where it stopped", 72%
mention a round 2, 42% a round 3, 26% a round 4, 19% a fifth or later. So a gap has about 1 + 0.72 + 0.42 + 0.26 +
0.19 = **2.6 reviews and 1.6 fix rounds**.

| Per gap | Full review (today) | Basis |
|---|---|---|
| money | 2.6 × $5 + 1.6 × $15 = **$37** ceiling | reviewer and implementor caps |
| rework | 1.6 fix rounds | records' text |
| time on the critical path | about **90 min**: about 20 min a review, about 45 min a review and fix (34 and 51 min in the two cases git times, review-at-the-feature section 8) | two gaps, so rough |

What replaces each number, all already in the live record or one reading away: `ai_cost_usd` per session (money);
`reviews_n`, `fix_rounds` (rework); `gate-review-minutes` and `approved_at` (time); the `review/*` items' findings
with the librarian's lesson class (findings by class, all of them, not the curated 123); `gate-catches-review` and
`gate-catches-queue` (what each gate stops); `regression-escapes-from-reverts`, `risk.py`'s escapes (escapes).
**What cannot be known yet, from any record:** whether a finding would have done harm had it landed. Review stops
the defect, so its harm is never observed. Only an arm that lets some defects land (section 2) measures it.

**Readings to add** (the first build, section 6): per reviewed item, its blocking findings by lesson class and by
harm class (the librarian assigns the harm class from the three above, an allowlist; an unclassed finding is
**severe**, lesson-3), and per level and rule, cost per item and harm escapes per item.

## 2. The controlled experiment

**Question.** For low-risk gaps, what does reviewing **after** merge instead of before cost in harm, and what does it
save in money and time?

**Population.** Gaps placed by a low-risk rule (section 3c: `records-and-proposals`, `pages`). Placement happens when
the gap is `built`, since the changed paths and net lines are known only then, and before any review is read.

**Assignment.** A gap is in the treatment arm when `sha256(seed + item id)` read as a fraction is below `share`.
Nobody chooses (no selection bias), the same id always gets the same arm (so a gap built again keeps its arm, and the
fold clears the old level and arm on a remake, lesson-5), and anyone can recompute it. The arm is recorded on the item
(`arm: trial` or `control`) with the seed. Start: `share: 0.3`, ceiling 0.5; `most_per_day: 20`, ceiling 100
(lesson-4: exposure bounded). A gap in a feature group (section 5) takes its group's arm.

**Treatment.** The gap goes to the queue on its light checks, with no review. Once merged, the **same** reviewer, with
the same prompt, model and cap, reviews its merge commit (the block `post-review`). A blocking finding becomes a fix
gap (`found_after: gap/X`, rank first). A severe one is reverted (section 4). The push and the instance's upgrade wait
for every post-review in their range (section 4, *Staging*).

**Control.** Review before merge as the gap's level says (one blocking pass or full).

**Outcomes**, per gap, over a window of 7 days after its merge. Only gaps whose window has closed are counted (an
open window is not zero escapes, lesson-3):

| | Outcome | Control | Treatment |
|---|---|---|---|
| E1 | blocking findings of the **first** review, by lesson and harm class | before merge | after merge |
| E2 | reached main | 0 by construction | E1's blocking findings (all landed) |
| E3 | **harm escapes**: reverted, `broke_main`, a `main-broken` blamed on it, or a later gap or intervention's `caused_by` (`risk.py`'s rules, matched by `reviewed_head` before `main_sha`) | yes | yes |
| C | cost: the gap's `ai_cost_usd` plus its `found_after` fix gaps'; hours from built to merged | yes | yes |

**How escapes are compared.**

1. **E1 is a balance check.** Same instrument, randomised arms: the two rates should agree. If, with 30 gaps in each
   arm, the two 90% intervals do not overlap, the instrument or the assignment is broken, and the trial pauses itself.
2. **E2** is section 1b's estimate measured: the share of treated gaps whose after-merge review blocks.
3. **E3**: each arm's harm escapes per gap is a Gamma posterior (shape 0.5 prior, mean `prior_escape: 0.05`, one in
   20, deliberately pessimistic). The treatment's 90% upper bound with k escapes in n gaps is
   Q₀.₉(Gamma(0.5 + k, 10 + n)): 1.353 / (10 + n) with none, 3.126 / (10 + n) with one. Its mean is
   (0.5 + k) / (10 + n).
4. **The decision rule** weighs harm against saving: `H`, what one harm escape is worth in dollars (the owner's, one
   question below; **$1,000** until answered, high so that review is kept), and `S`, the measured saving per gap
   (control's mean cost minus treatment's, over gaps whose windows closed). At the ceilings S is about
   $37 − ($5 + 0.72 × $20) = **$18** and 90 min off the critical path. Treatment wins for the rule when its bound × H
   < S: with no harm escape, 1353 / (10 + n) < 18 first holds at **n = 66 treated gaps** with closed windows. One
   non-severe escape before then stops the trial instead (the mean test below: 1500 / (10 + n) > 18 for every n up to
   73), so 66 clean windows is the shortest way to a decision and the only one at the ceilings' S.
5. Batch merges share `main_sha`, so a `main-broken` matched only by `main_sha` blames every gap of the batch, in both
   arms; such blames are kept and flagged `shared`, and the result is said with and without them.

**Stopping, by itself.** The trial sets its share to 0 (`levels.trial-stopped`, with why) at once on: any severe
harm escape in the treatment arm; E1's balance check failing; the treatment's posterior **mean** × H above S (the
same test that raises a level, section 3d), applied only once at least `least` (30) treated gaps have closed windows.
Each is a trigger of the pipeline manager. A new trial needs a new seed.

The mean test waits for `least` because before any data it is the prior's: 0.05 × $1,000 = $50, above any S near $18,
so applied from the first pass it would stop every trial at once. Worked check, H = $1,000, S = $18:

| Closed treated windows n | Mean × H, no escape | Mean × H, one escape | Bound × H, no escape |
|---|---|---|---|
| 0 | $50 (test not applied) | | $135 |
| 18 | $17.9 (test not applied) | | $48 |
| 30 | $12.5: runs on | $37.5: stops | $34 |
| 66 | $6.6: runs on | $19.7: stops | $17.8: **decision, treatment wins** |

So with no harm escape the mean test never fires (it is $12.5 when first applied and falls), and the trial reaches its
decision at 66. If the measured S is under $12.5 when first read, the mean test stops the trial at its 30th closed
window: that is the rule's answer (the saving is too small for the risk at H), not a fault.

**S unreadable.** S needs at least `least` closed gaps in each arm whose cost is a finite number. Before the
treatment has `least` closed windows, S is not used (the mean test is not applied yet). From then on, while S cannot
be read (too few costed gaps in an arm, or a cost missing or not finite), the trial is **held**: share 0 for new
placements, gaps already treated keep their arm and post-reviews, the stops on a severe escape and on balance still
apply, and no decision is taken (lesson-3: an unread S is never read as a saving). It resumes when S reads again; held
past 7 days, it stops (`levels.trial-stopped`, why: `saving unreadable`).

**Length.** In the 40 merges sampled, 7 (18%) changed only `docs/`, `dev/records/`, `tests/`, `examples/` and
`ergostat/web/static/`. At the recent 116 to 198 merges a day that is about 20 to 35 eligible gaps a day, so at share
0.3 (and at most 20 a day) 6 to 11 treated a day: 66 treated in 6 to 11 days, plus the 7-day window: **two to three
weeks** to the first decision, if no harm escape stops it first (the worked check above).

**Hands.** None of the owner's: the coordinator applies the model change that declares the trial (the boundary);
assignment, the post-reviews, the fix gaps, the readings, the stops and the bound are all programs and blocks. What
the result **does** is the controller's (section 3d): a lowering is asked for in the inbox, as the pool tuner asks for
a raise.

## 3. Review levels by risk, and the controller

### 3a. The core option (general; off unless declared)

```yaml
items:
  change:
    states: [todo, built, approved, merged, done]
    levels:
      field: care                  # the item field it writes
      at: built                    # placed on entering this state, once per entry
      order: [none, after, one, full]   # least to most; an item no rule matches is the last
      rules:                       # first match wins
        - name: notes
          level: one
          lowest: after            # the controller never moves it below this
          where: {paths: {all: ["docs/**"]}, lines: {most: 400}}
      trial: {rules: [notes], to: after, share: 0.3, most_share: 0.5, most_per_day: 20, seed: t1}
      control: {harm: escapes, cost: cost, worth: parameter.escape-worth, prior: 0.05, least: 30, probation: 10}
```

What core does, and nothing more:

1. **Placement.** On an item's entry into `at`, the first rule whose `where` matches gives its level; none, the last
   of `order`. `where` is a field match as in `takes` (value or list), plus `{all: [globs]}` and `{any: [globs]}` on a
   list field and `{most: N}`, `{least: N}` on a number. A field that is missing or of the wrong type does not match
   (so the item falls to the strictest, never to a lower level, lesson-3). Placement is an event
   (`<kind>.levelled`: level, rule, arm, seed), so it is in the record and `takes: {where: {care: [one, full]}}` routes
   on it like any field. A remade item is placed afresh (lesson-5).
2. **Trial.** As section 2: the hash, the share, the ceilings, the arm on the event; its mean stop uses `control`'s
   `least`, and a trial without a `control` stops only on its model's own triggers.
3. **Moves.** A rule's level now is its declared level moved by its recorded `levels.moved` events (by `seq`,
   lesson-2), held within `lowest` and the top of `order`. The default (no rule) never moves.
4. **Measures.** Per rule and level: items placed, harm per item (the sum of the field `control.harm` names over items
   whose window closed), cost per item (the field `control.cost`). These are readings a goal may hold.
5. **`check` refuses** (`bad-levels`): an unknown state, a level not in `order`, a `lowest` above `level`, a glob on a
   field not declared as a list, a share outside 0 to `most_share` or `most_share` above 0.5, `most_per_day` outside
   1 to 100, a trial naming no rule, a `control` without `worth`, a `least` or `probation` not a whole number from 1
   to 1000. A missing or non-number limit is refused at its key,
   never read as 0 or unlimited.

Core never knows what a level means: the model's blocks take items by it.

### 3b. What each level means in this factory

| Level | Before merge | After merge | Ceiling per gap |
|---|---|---|---|
| `none` | light checks (ruff, `build`, new findings, strays, section 4's programs) | 1 in 5 audited by `post-review` (to keep measuring) | $1 audit share + fix gaps |
| `after` | light checks | `post-review`; blocking findings become a fix gap; severe ones are reverted | $5 + 0.72 × $20 = $19 |
| `one` | one blocking review; its findings fixed in one round, which goes to the queue unreviewed | | $5 + 0.72 × $15 = $16, about 50 min |
| `full` | today: review until approved, parked after `kill_after` | | $37, about 90 min |

### 3c. The factory's first declaration (its own model)

```yaml
levels:
  field: care
  at: built
  order: [none, after, one, full]
  rules:
    - name: records-and-proposals
      level: one
      lowest: after
      where: {paths: {all: ["docs/**", "dev/records/**"]}}
    - name: pages
      level: full
      lowest: after
      where: {paths: {all: ["ergostat/web/static/**", "tests/**", "docs/**", "dev/records/**", "examples/**"]},
              net_lines: {most: 250}, escapes_in_paths_30d: {most: 0}}
  trial: {rules: [records-and-proposals, pages], to: after, share: 0.3, most_share: 0.5, most_per_day: 20,
          seed: review-trial-1}
  control: {harm: harm_escapes, cost: review_cost_usd, worth: parameter.escape-worth, prior: 0.05, least: 30,
            probation: 10}
```

The rules are allowlists (lesson-8): everything else, the engine, leases, the budget, the sandbox, `dev/bin/`,
`scripts/`, the record's writers, is `full` and never moves, because the 21 severe examples of section 1a live
there. `pages` starts at `full`, not lower: 23% of the curated findings are in `ergostat/web/static/`, so its value
is not known to be low; the trial finds out. The four fields the rules read (`paths`, `net_lines`,
`escapes_in_paths_30d`, `review_cost_usd`) are written by the implementor's finish when the gap is built (it already
measures net lines and strays). `harm_escapes` is `risk.py`'s count for the gap. `escapes_in_paths_30d` is the harm
escapes of gaps that changed any of the same files in the last 30 days, the "history" input.

### 3d. The controller

A rule-rung controller, `levels-tune`, one pass an hour, per rule r at level L, with L₋ the next level down (not below
`lowest`) and L₊ the next up:

- **Lower by one step (asked, never done alone):** when at L₋ there are at least `least` (30) items with closed
  windows (from the trial, or from an earlier stay at L₋), the 90% bound of harm per item at L₋ times `worth` is below
  the measured saving S(L → L₋), no severe escape at L₋ in 30 days, and `probation` (10) items were placed since the
  last move. It asks `lower-level` in the inbox with the evidence, and checks it all again when approved (lesson-1).
- **Raise by one step at once:** on any severe escape at L; or when the **mean** harm per item at L times `worth`
  exceeds S(L₊ → L), a test applied only when at least `least` items at L have closed windows (the trial's count, so
  it applies from the first pass after a lowering, which needs `least` at L₋). Below `least` the mean is mostly the
  prior's (0.05 × $1,000 = $50 against an S near $18) and would raise every rule at once; with `least` = 30 and no
  escape it is $12.5 or less. Lowering on the bound and raising on the mean leaves a band between them, so the level
  does not flip each pass.
- **Unreadable** (a measure missing, a cost not a finite number): no lowering; after 24 h unread, the rule returns to
  its declared level and says so (lesson-3).

This is the pool tuner's shape (`risk.py`): Gamma posteriors, a bound for the risky direction, a request for more
risk, an immediate step for less. Each move is a `levels.moved` event with its evidence, read on the kind's row and
the Items tab; no new page.

## 4. What makes lower review safe

| Means | Today | What this proposal adds or requires |
|---|---|---|
| **Fast reverts** | each gap lands as one `--no-ff` merge, so `git revert -m 1` undoes it in one commit; `escapes.py` finds reverts; `live.py revert` puts the instance back on the previous version at once | a **revert gap** (`care: none`, rank first) made by `post-review` for a severe finding or by triage for a `main-broken` blamed on an `after` gap: one queue run (unit about 2 min, browser about 6 min, each stopped past `wall_minutes = 45`), not the queue's line (about 2 h in review-at-the-feature section 8) |
| **Feature flags** | core options are off unless a model declares them, so new core code is dark until declared; the factory's own `dev/` code is live on upgrade | not a rule input: "dark until declared" cannot be checked by a program, and a rule on an unchecked claim would be a denylist (lesson-8) |
| **Staging** | main is merged locally, then pushed by a gate, and the instance switched by `live.py` with a health check and an automatic revert | the push and the upgrade **wait** until every `after` gap in their range has its post-review, and every blocking finding of it is fixed or reverted (the owner's second question; this is the default). A post-review not done in 4 h is a pipeline manager trigger, never a pass |
| **Tests by changed path** | `[suites] build` runs `affected_tests.py`; the queue runs browser on `browser_paths` and always the full unit and demo | unchanged; every level keeps them. No level skips the queue's suites |
| **Programs before review** | ruff, new `check` findings, strays, the size budget | two programs, each required below `one`: **new tests fail on the base** (the branch's new or changed tests run against main's code must fail; aimed at lesson-9's 12, a test that cannot fail), and **record against diff** (the files a record's "Where it stopped" says were built must be in the diff; lesson-8's two "marked built with nothing built"). With strays and the GAPS.md move, the shapes programs are aimed at cover about 21 of the 123 (17%); how many they catch is not known until they run (most of lesson-9's are tests that pass with one guard removed, which a run on the base does not see) |

None of these makes `full`'s paths safe to lower, and none is claimed to: they bound the cost of an escape in the
paths a rule already calls low-risk.

## 5. How this composes with review at the feature

`docs/proposals/review-at-the-feature.md` reviews a group of members once. In levels:

- **One list, not two.** That proposal's `[features] light_paths` becomes these rules: a member is light (integrated
  after light checks) when its level is `none` or `after`; one placed `one` or `full` is reviewed on its own first,
  as that proposal's section 6 says for risky paths. Until the controller has moved a rule, `records-and-proposals`
  and `pages` are `one` and `full`, so no member is light: groups still integrate, but every member is reviewed
  (that proposal's "path rule" case), until the trial says otherwise.
- **The group's level** is the strictest of its members' and is placed when the group is built; the group review is
  `one` or `full` accordingly.
- **The trial's unit is the group** when there is one: all members take the group's arm (hash on the group's id), so
  a treatment group lands on light checks and is post-reviewed as a whole, member by member. Escapes are counted per
  member (`merged_with`), and compared per group (a cluster), so a group of six counts as one draw, not six.
- **Measures compose.** That proposal's switch is judged by `gate-catches-review`, `gate-catches-queue` and escapes
  per merged net line; here the same readings are per rule and level. A group's post-merge findings are E2 for each
  member they name (`member: gap/X`).

## 6. The build split

Nothing here is built by this gap. In order, each a gap of at most 250 net lines:

1. **Measure first (factory, no behaviour change, about 120 lines).** The readings of section 1d: per review its
   blocking findings by lesson and harm class (the librarian's step gains the harm class, an allowlist, unclassed
   severe); per gap `review_cost_usd`, `reviews_n`, `fix_rounds`, hours built to approved; `measure.py review-value`
   over a window. This replaces every ceiling above with spend.
2. **Core levels: placement and trial (about 220 lines).** `levels:` on a kind, the `where` matchers, the
   `levelled` event, the hash and arm, `bad-levels` refusals; SPEC §5a. Tests: first match; missing field falls to
   the strictest; the same id gets the same arm and a remake is placed afresh; each refusal; the share and per-day
   ceilings.
3. **Core levels: moves and the controller (about 200 lines).** `levels.moved` by `seq`, the per-rule measures, the
   rule-rung controller and its `lower-level` request. Tests: a lowering only with `least` closed items and the
   bound under the saving; a raise at once on a severe escape; no mean raise, and no trial stop on the mean, below
   `least` closed items (a fresh trial with no data is not stopped); a trial held, not stopped, while the saving is
   unreadable; unreadable holds then returns to declared; an approval re-checked when stale.
4. **Factory: the fields, the levels in shadow (about 150 lines).** The finish writes `paths`, `net_lines`,
   `escapes_in_paths_30d`; the model declares section 3c with `share: 0` and every rule at `full`, so placement is
   recorded and shown and nothing changes. A week of it gives section 2's eligible share measured, not sampled.
5. **Factory: `after` and `one` (about 230 lines).** The `post-review` block, `found_after` fix gaps, revert gaps,
   the push and upgrade waiting for post-reviews, the reviewer's `takes` on `care`, the `one` level's unreviewed fix
   round.
6. **Factory: the two programs before review (about 150 lines).** New tests fail on the base; record against diff.
7. **Turn on the trial**: the coordinator sets `share: 0.3` and the rules' declared levels (section 3c). A change of
   the model, no code.

Review at the feature's build (its section 7) goes after step 5, so its light members are read from levels.

## Questions for the owner

1. What is one harm escape (a revert, a broken main, or a later fix you have to step in for) worth in dollars of AI
   spend, so the controller can weigh it against review's cost ($1,000 until you say)?
2. May main be pushed while a gap reviewed after merge still has a non-severe blocking finding open as a fix gap, or
   must the push wait for the fix or a revert (it waits until you say)?
