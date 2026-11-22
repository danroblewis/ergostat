# Regression guarantees in the feedback model: a proposal

For the owner. Status: a proposal, nothing built. It asks for no code change by itself; section 7 is the milestone that
would build it, one gap at a time.

Every `file:line` below is on main as this branch left it (5617e225; the branch adds only its definition,
`dev/records/regression-guarantees-proposal.md`, and this file).

## 1. The question

Before ergostat is given to people, the guarantees that keep main working should be **in the model**. That means
stocks, goals and loops that the diagrams draw, not only rules in tests, in `dev/bin/queue.py`, in
`dev/knowledge/review-lessons.md` and in `tests/quarantine.txt`.

A guarantee in the model has four parts, the same four any goal in ergostat has:

1. **a measured quantity**: a stock or auxiliary read by a sensor from the record;
2. **a setpoint**: a goal holding it (SPEC §8: one goal per stock, flow or auxiliary, docs/SPEC.md:2022-2023);
3. **a loop that acts** when it is off: a block that serves the goal (docs/SPEC.md:3474-3476), drawn as a balancing
   loop (docs/SPEC.md:3482-3485);
4. **a way to see it broken**: the goal off on the diagrams and in *needs attention*, with no new page or panel (the
   house rule; the owner's decision "One model, three drawings").

If a guarantee has a goal that nothing serves, ergostat already names it: that is **missing feedback**
(docs/SPEC.md:2053, docs/SPEC.md:3249). If a guarantee has no goal at all, nothing can say it broke. Most of today's
guarantees are in that second case.

## 2. The guarantees ergostat makes today

### 2a. To its own main (the factory)

| # | Guarantee | Where it is enforced | The test that fails if it is false |
|---|---|---|---|
| F1 | Nothing lands without a full green run of ruff, unit, browser and demo | dev/bin/queue.py:16-18, dev/bin/queue.py:24-31, dev/bin/queue.py:180 | tests/test_factory.py:2663 (`test_nothing_lands_without_a_full_green_run`), tests/test_factory.py:2339 |
| F2 | It merges exactly the commit the reviewer approved, and refuses a branch that moved after review | dev/bin/queue.py:40-41 | tests/test_factory.py:930 |
| F3 | A skipped browser test is a failure, and is never excused as a flake | dev/bin/queue.py:104-108, dev/bin/queue.py:183-188 | tests/test_agents.py:224 (the alone-rerun side) |
| F4 | A red run is excused as a flake only when 1 to 3 named tests each pass alone twice and the suites it did not finish pass | dev/bin/queue.py:25-27, dev/bin/queue.py:183-188, dev/bin/queue.py:201-210 | tests/test_factory.py:2562, tests/test_factory.py:2615 |
| F5 | On any error or stop, main is put back (`git reset --keep`) | dev/bin/queue.py:32, dev/bin/queue.py:644, dev/bin/queue.py:694, dev/bin/queue.py:712 | tests/test_factory.py:1526 (a denied push undoes its merge) |
| F6 | The quarantine is read from the base, never the branch under test; a quarantined test that is skipped or not collected counts as unknown, never as a pass; it never blocks | dev/bin/fac.py:564-569, dev/bin/fac.py:580-586, dev/bin/fac.py:589-610 | tests/test_factory.py:1355, tests/test_factory.py:1303, tests/test_factory.py:1290 |
| F7 | The definition of done does not change after its first commit, except for "Where it stopped"; a branch over its size budget needs a written `Overrun reason:` | dev/bin/review.py:5-7, dev/bin/review.py:34-62, dev/bin/review.py:91-99 | tests/test_review.py:753, tests/test_review.py:764, tests/test_review.py:788 |
| F8 | The kill rule: the `kill_after`-th failed gate parks a gap, and repeated build failures or too many build hours park it | dev/bin/review.py:10-12, dev/bin/fac.py:535-546, dev/bin/implement.py:22-26, dev/bin/triage.py:76-81 | tests/test_factory.py:484 (`test_fix_then_park`: the `kill_after`-th failed gate), tests/test_factory.py:947 and tests/test_factory.py:982 (failed builds park); no test parks a gap on `build_hours` (dev/bin/implement.py:190-192): that part is untested |
| F9 | A failure that names tests is triaged: one that passes alone is a flake (at most `RETRIES` = 2 retries), and one that fails on clean main too is main's, not the gap's | dev/bin/triage.py:1-7, dev/bin/triage.py:18, dev/bin/onmain.py:1-15 | tests/test_factory.py:505, tests/test_factory.py:1241, tests/test_factory.py:3380 |
| F10 | A suite that stops making progress is stopped as a stall; a gap is blamed only after it stalls alone `STALLS_MOST` = 3 times | dev/bin/queue.py:22-23, dev/bin/fac.py:435 | tests/test_queue.py:231, tests/test_queue.py:322 |
| F11 | An upgrade that does not show healthy in time is reverted to the version before it | dev/model/landing.yaml:169-180 | tests/test_factory.py:1427 |
| F12 | Every review lesson is carried into every implementor and reviewer brief | dev/knowledge/review-lessons.md:1-5, dev/bin/knowledge.py:268-272 | tests/test_factory_knowledge.py:1373 (`test_the_next_brief_carries_an_applied_lesson`: the implementor's, reviewer's and pipeline manager's briefs, and lessons kept when the brief is cut), tests/test_factory_knowledge.py:1402 |

The review lessons are not a gate. They are a list of the kinds of mistake that got past the implementor and were
found by a review (dev/knowledge/review-lessons.md:8-9). Each lesson is therefore a record of a guarantee that once
failed before the merge gate.

### 2b. To a user's model (the product)

| # | Guarantee | Where | Test |
|---|---|---|---|
| U1 | A block's claim ("tests pass") is checked by ergostat itself, never taken on the block's word; a claim no check can judge is never trusted | docs/SPEC.md:4912-4916, docs/SPEC.md:4956-4958 | tests/test_claims.py:60 (a pipe that hid a failing exit code) |
| U2 | Trust is a measure that a goal can hold: the share of a block's claims contradicted | docs/SPEC.md:5012-5024 | tests/test_claims.py:234 (`test_the_kind_is_built_in_and_trust_is_a_measure_a_sensor_reads`), tests/test_claims.py:217 |
| U3 | A repaired program's fix is verified by the runs after it; a failed run **regresses** it, and its revert is asked for as a gated action | docs/SPEC.md:6264-6276, docs/SPEC.md:6278-6293 | tests/test_repair_verify.py:101 (verified), tests/test_repair_verify.py:117 (a failed run regresses it and asks for the revert once), tests/test_repair_verify.py:227 (the approved revert) |
| U4 | A change written to the model is checked against the record after it: `verified`, or `regressed` with the edit that undoes it | docs/SPEC.md:4885-4891 | tests/test_bench.py:200 |
| U5 | The invariants: a residual is evidence and never silently ignored, and ergostat adds nothing of its own accord | CLAUDE.md:40-41, CLAUDE.md:52-53 | the residual half: tests/test_runner_and_state.py:78 (`test_with_no_disturbance_to_absorb_it_the_rest_is_unexplained`), tests/test_runner_and_state.py:114; the "nothing of its own accord" half: no test (none checks that an empty install runs nothing) |

## 3. What the model shows of them today

Some of these guarantees already have a part of the model behind them. Most have none.

| Guarantee | In the model now | What is missing |
|---|---|---|
| F1 main green | `gaps-queue-failed` held at 0 by `queue-failures-triaged`, served by flake triage (dev/model/landing.yaml:15-18, dev/model/landing.yaml:268-272, dev/model/landing.yaml:339-356). The pipeline manager's `merge-pipeline-flowing` counts an unremedied test that fails on two main commits (dev/model/manager.yaml:22-26, dev/model/manager.yaml:88-92) | No stock of **tests failing on main**: a goal of "main is green", in tests, read from main itself |
| Escapes (any F) | The stock `escapes`, counting merged gaps that were reverted, broke main, or were named as a later gap's cause (dev/model/pools.yaml:28-32, dev/bin/risk.py:8-11, dev/bin/risk.py:74-97). It feeds only the pools' risk (dev/model/pools.yaml:39-43) | **No goal** on escapes. Its inflow `escapes-found` has no sensor (dev/model/pools.yaml:66-69). A reverted merge or a broken main is entered by hand (dev/README.md:353-358), except for the `main-broken` interventions found by the implementor's triage |
| F4, F9 flakes | `flake-rate`, held by `flakes-rare` at ≤ 0.1 (dev/model/measures.yaml:53-57, dev/model/measures.yaml:115-119), which feeds `factory-off` and from there asks the coordinator (dev/model/measures.yaml:132-154) | `flake-rate` reads only the gaps' `retries` over their queue attempts (dev/bin/measure.py:167-169). Only triage writes `retries` (dev/bin/triage.py:72). The queue's own excused flakes write `flake.seen` (dev/bin/queue.py:206-208) and no `retries` (none appear in queue.py), so they are left out. The `flake` items themselves are counted by no sensor. Nothing emits `flake.fixed`: it appears only in the kind's declaration (ergostat.yaml:199), so no flake ever leaves `seen`. Nor does any event take an item out of `main-broken` when main is fixed: the kind's only other events are `seen` and `fixed` (ergostat.yaml:195-199), the only writer of `main-broken` is dev/bin/onmain.py:94, and the only way out is a later `flake.seen` (written at dev/bin/onmain.py:74, dev/bin/queue.py:207, dev/bin/triage.py:71, dev/bin/manage.py:231), which moves a test still failing on main into the flakes |
| F6 quarantine | Nothing. The list says it is "added and released by hand" (tests/quarantine.txt:1-3). The results of quarantined tests are written as `flake.measured` on flake items (dev/bin/fac.py:607-609) | A stock of quarantined tests, how long each has been held, and a goal that the quarantine drains |
| F7, F8 gates | `failed_gates` summed on each gap (ergostat.yaml:124). The kill rule's parks flow out of triage (dev/model/landing.yaml:117-122) | A gate that fails is a finding, not a measure. Nothing counts how often each gate catches something, so nobody can see a gate that never catches anything |
| F10 stalls | `stalls` summed on each gap (ergostat.yaml:127) | No measure |
| F11 upgrades | `revert-share` is a parameter (dev/model/landing.yaml:255-260), and `upgrades-reverted` is a flow with a sensor (dev/model/landing.yaml:175-180) | No goal |
| F12 lessons | Lesson items fold `times` (ergostat.yaml:277). `first-pass-with-lessons` compares the yield of gaps whose briefs carried lessons with the yield of all gaps (dev/model/knowledge.yaml:74-79) | No measure of **a lesson's class found again after it was carried**. That event is the lesson failing as a guarantee |
| Time to repair | Interventions of class `main-broken`, one per main commit (dev/bin/onmain.py:10-12), in `interventions-open` (dev/model/interventions.yaml:9-12) together with every other class | No measure of how long main stays broken, or a flake stays unfixed |
| U3 repair | The template has `regressed-fixes` and the flows `fixes-regressed` and `fixes-reverted` (ergostat/library/templates/repair/template.yaml:49, ergostat/library/templates/repair/template.yaml:63-64) | No goal on regressions: the template's goals are `no-open-failures` and `fixes-answered` (ergostat/library/templates/repair/template.yaml:66-68). SPEC's parts table leaves the stock out (docs/SPEC.md:6312). A goal on the stock itself could never recover: a denied `revert-fix` leaves the failure `regressed` for good (docs/SPEC.md:6293), and the failure records no denial (only `revert_key`, ergostat/repair/apply.py:121) |
| U1, U2 claims | Trust measures that any model can read as builtins (docs/SPEC.md:5021-5024); a contradicted claim is a finding that needs attention (docs/SPEC.md:5026-5028) | None is wired to a regression goal by default. That is correct under invariant 12; section 6 offers one opt-in |

So this already exists: one cumulative stock (`escapes`) with no goal, one measure of flakes that undercounts, and
several states that nothing ever reads.

## 4. Each guarantee as a measured stock or goal

These are the measures the owner asked for (passing counts, escapes, flake rate, time to repair), plus two that the
table above shows are needed (the quarantine, and the gates' catches). The names are proposals.

| Measure (part) | Kind, unit | Read from | Goal | Loop that acts when off |
|---|---|---|---|---|
| `tests-passing` | auxiliary, tests | the last green queue run's pytest summary on main (passed, failed, skipped, deselected) | `tests-not-falling`: its change over main's last 10 merges, by seq, `>= 0` (the shape of dev/model/code-health.yaml:120-124) | the reviewer and the coordinator: off asks for the gap that removed tests to justify it, through `factory-off` |
| `main-failing-tests` | stock, tests: `flake` items in `main-broken` | `items: flake, state: main-broken`. This is a true count only once milestone gap 2 gives the state its ways out (`flake.main-fixed`, and a `flake.seen` that no longer takes an item out of `main-broken`); until then it only rises, so gap 5 waits on gap 2 | `main-green`: `<= 0`, `tolerance: 0`, `critical: true` (docs/SPEC.md:2046), `on-stale: off` (docs/SPEC.md:2050) | the pipeline manager (already started by a broken pipeline: dev/model/manager.yaml:22-26) and the `remedy` block; whether the queue should also hold while it is off is a separate question to the owner (milestone gap 5) |
| `escapes` | the existing stock (dev/model/pools.yaml:28-32), plus a 14-day rate `escape-rate` (escapes per merged gap) | dev/bin/risk.py's evidence, unchanged | `escapes-rare`: `escape-rate <= 0.05` | the pool tuner already lowers the pool (dev/model/pools.yaml:113-121); in addition, the librarian asks for a lesson from each escape's cause, and the coordinator gets a gap that adds the test that would have caught it |
| `flakes-open` | stock, tests: `flake` items `seen` | `items: flake, state: seen` | `flakes-few`: `<= 3`, with `per: item` on their age (docs/SPEC.md:2066-2070) so the oldest is named | the coordinator asks for a gap that fixes the oldest flake (a race in ergostat or a fixed sleep in the test, lesson 10) |
| `flake-rate` | the existing auxiliary, corrected to count the queue's excused flakes as well as triage retries | dev/bin/measure.py | `flakes-rare`, unchanged (dev/model/measures.yaml:115-119) | unchanged: `factory-off` |
| `quarantined` | stock, tests | `tests/quarantine.txt` on main, cross-checked with the `flake` items marked `quarantined` | `quarantine-small`: `<= 3`; and `quarantine-fresh`: the oldest held `<= 7d`, `per: item` | the coordinator, asked to release a test that passes again (fac.beside already records every run: dev/bin/fac.py:607-609) or to fix it |
| `main-repair-hours` | auxiliary, hours: median, over 14 days, from the first `flake.main-broken` on a test's item, by `seq`, since the item was made or last left `fixed`, to its `flake.main-fixed` (gap 2). A later `flake.main-broken` on the same item does not restart the clock. Each later gap that hits the same failure on a newer main writes the event again, stamped with a new `main_broken_at` (dev/bin/onmain.py:92-94). Measured from the last of these, repair time would be undercounted (lessons 2 and 5), so gap 2 keeps the first stamp. Not from the intervention's `remedied`: that means the missing loop was built (dev/model/interventions.yaml:26-28), and it is marked by hand (dev/bin/manage.py:264) | flake items, by the `seq` of the two events | `main-repaired-fast`: `<= 24` | `remedy` (dev/model/interventions.yaml:52-66) |
| `flake-fix-hours` | auxiliary, hours: median from `flake.seen` to `flake.fixed` | flake items | none until `flake.fixed` is emitted (milestone gap 2) | |
| `gate-catches` | auxiliary per gate (queue red, triage red, size, definition, strays, review fix), a 14-day count | gap fields that already exist (`failed_gates`, `sent_back_by`, `reviews`) | none: a gate that is never off is not a regression. This one is **evidence** for removing or strengthening a gate (the refactor path, CLAUDE.md:35-37) | read by the simplifier and the coordinator |
| `lessons-recurring` | auxiliary, findings: review findings in the last 14 days of a class the brief carried | lesson items' `findings` (ergostat.yaml:277) | `lessons-hold`: `<= 2` | the librarian: rewrite the lesson's **Check**, or turn it into a test or a lint, which moves it down the ladder |

Rules every one of these follows (from the review lessons, applied to sensors):

- **Fail closed** (lesson 3). If a reading cannot be made (no queue run on main, an unreadable list, no pytest
  summary), there is no value, and every regression goal is `on-stale: off`. A missing summary never counts as zero
  failures. Today `flake-rate` reads 0.0 when there were no runs (dev/bin/measure.py:169), and that is a fail-open
  this milestone should not copy.
- **By sequence, never by wall time** (lesson 2). "Over main's last 10 merges" counts merges by `seq`, as the code
  measures already do (dev/model/code-health.yaml:73-76).
- **Allowlists** (lesson 8). Each gate in `gate-catches` and each intervention class that counts as an escape is named
  in a list, as risk.py's factory classes already are (dev/bin/risk.py:25-26).
- **A ceiling on every count read** (lesson 4). A sensor reads at most N items and says when it hit the limit.

## 5. How a guarantee breaking shows on the diagrams

There are no new pages or panels. Each guarantee appears through the parts it is made of, in the three drawings that
exist today:

- **Dynamics.** Each regression goal's stock gets its *desired* and *excess* drawn beside it
  (docs/MODELLING-WELL.md:106-108). A broken guarantee is a stock with an excess above zero, inside a named
  balancing loop. The milestone names each loop (`loops:`, docs/SPEC.md:3487-3497): `main-repair` (main failing tests
  → remedy → fixed), `flake-repair`, `quarantine-release`, `escape-learning` (escapes → lesson → brief → first-pass
  yield). A loop that comes out reinforcing is a controller pushing the wrong way (docs/SPEC.md:3482-3485), and
  `check` reports it.
- **Blocks.** Each goal is a comparator with its r and error, wired to its controller (docs/DESIGN.md:172-182). A
  goal that is off sends `loop.off` (docs/SPEC.md:2160). The block's chart marks the periods it was off in red
  (ergostat/web/static/charts.js:545). A regression goal with no block serving it is reported as missing feedback by
  `check`, so building the goals before their loops shows up as a finding and not as silence.
- **Process.** The `flake`, `intervention` and `gap` items move through their states on the process map. A flake
  that stays in `seen` for weeks shows as a state that items enter and never leave. That is the exact picture of
  "nothing emits `flake.fixed`".
- **The system box.** A new system `guarantees`, within `oversight`, `show:`s its stocks the way `measures` does
  (ergostat.yaml:55-58). Its box shows the goals that are off.
- **The Items tab.** With `per: item`, a goal names the items breaking it (docs/SPEC.md:2066-2070), so "which test is
  failing on main" and "which flake is oldest" are the item pages that already exist.

## 6. Applying it

### 6a. To ergostat's own factory first

All of this is model work and sensor work in `dev/`, which is the factory's own tooling:

1. **A new file `dev/model/guarantees.yaml`**, taken in by `include: dev/model/*.yaml` (ergostat.yaml:18-19). It
   holds the `guarantees` system, the stocks and goals of section 4, and the named loops. The `escapes` stock stays in
   `pools.yaml`, and the new file only puts a goal on it, so the pools' risk is unchanged.
2. **Sensors in `dev/bin/measure.py`** for the auxiliaries (`tests-passing`, `main-repair-hours`, `gate-catches`,
   `lessons-recurring`). The stocks of items are plain `items:` sensors and need no code.
3. **The record's missing events.** `flake.fixed` and a new `flake.main-fixed` must be emitted, and `flake.seen`
   must no longer take an item out of `main-broken` (milestone gap 2). The queue must also write the
   pytest summary of its green run (today it keeps `rc`, `seconds` and, for the browser suite only, a count of
   `skipped` lines: dev/bin/queue.py:104-105; no passed or failed counts).
4. **Wiring the loops.** `main-green` and `quarantine-*` feed `factory-off` (dev/model/measures.yaml:132-147), so
   the coordinator still has one commander (the pattern of dev/model/code-health.yaml:163-172). `escapes-rare` also
   reaches the librarian. Nothing new acts on the world: every loop ends in a person, an existing program, or a
   gated action.

What changes for the factory: when main breaks, it shows up as a red stock in a named loop, not only as an
intervention among the others. The quarantine stops being a file that only a reviewer reads. A flake has a lifetime
that can be measured.

### 6b. Then to any user's model

Ergostat adds nothing of its own accord (CLAUDE.md:52-53), so a user gets regression guarantees only by asking for
them. The proposal is a **library template, `regressions`**, used the way the factory uses `interventions`
(ergostat.yaml:318-319): `uses: {regressions: {use: regressions, with: {...}}}`. It builds on what a user's model
already has:

- **Passing counts** from the project's declared `claims: tests` command (docs/SPEC.md:4966-4975): a sensor that
  runs it on a schedule and reads the counts. A run that cannot be read gives no value.
- **Escapes** as contradicted claims: `builtin: ergostat.trust.contradicted@BLOCK` (docs/SPEC.md:5018-5024). A block
  that said "tests pass" when they did not has let a regression through.
- **Regressed fixes** from the repair template's flow `fixes-regressed`
  (ergostat/library/templates/repair/template.yaml:63), with a goal that none regressed in the last 14 days (gap 7).
  The goal is not on the stock `regressed-fixes` (ergostat/library/templates/repair/template.yaml:49), which a denied
  revert keeps up for good (docs/SPEC.md:6293). The same template change should add that stock to SPEC's parts table
  (docs/SPEC.md:6312-6314).
- **Regressed model changes** from `ergostat.model.regressed` (docs/SPEC.md:4900).
- **Flakes and quarantine** only when the user declares an item kind for them. The template gives the shape (kinds,
  states, stocks, goals) and the user's own tests fill it.

Every goal in the template is served by a person block by default (rung 0), as the approval ladder asks (the owner's
decision "Human approval is for a system's early stages"). The user moves it down the ladder.

### 6c. What this does not promise

- A goal on `main-failing-tests` holding means only that **the tests that ran** passed on main. It does not mean that
  nothing regressed. The test that would show that is the escape count, and it lags.
- `escape-rate` counts only the escapes someone recorded or the triage found (dev/README.md:353-358). An unrecorded
  revert is invisible to it. Gap 4 narrows that, but cannot close it.
- `gate-catches` is evidence for a decision about a gate, never a verdict on it.

## 7. Milestone: the gaps, in order

Each gap has its own definition of done. The order follows dependencies: the record first, then the measures, then
the goals, then the loops, then the users.

1. **regression-record-summary.** The merge queue writes each suite's pytest counts (passed, failed, skipped,
   deselected, errors) on the gap and on the queue run, next to `rc`, `seconds` and the browser suite's `skipped`
   count, the only fields kept today (dev/bin/queue.py:104-105), read
   from the suite's whole log, never a tail (the quarantine lesson, lesson 3). A log that cannot be read writes
   `counts: unknown`. Acceptance: a test that a run with 3 failed and 1 skipped records exactly those counts, and that
   a truncated log records unknown, never zero. Size: small, `dev/bin/` only.

2. **flake-lifecycle.** Each of the flake kind's states gets a way out that means what it says.
   - **Out of `seen`.** `flake.fixed` is emitted when a test that was seen as a flake passes in N consecutive green
     queue runs on main (N in `[gates]`, with a ceiling), counted by `seq`.
   - **Out of `main-broken`.** A new event, `flake.main-fixed`, is declared on the kind (ergostat.yaml:195-199) and
     moves the item to `fixed`. After each landing, the queue runs each test in `main-broken` alone, twice, on the new
     main, the way it already runs a test alone (dev/bin/onmain.py:46), at most M tests a pass (M with a ceiling, lesson 4).
     A test that passes both runs gets `flake.main-fixed` with the main sha it passed on. A test that is skipped, not
     collected, or quarantined, or whose run cannot be read, is unknown and stays `main-broken`, the way quarantine
     scoring already counts it (dev/bin/fac.py:580-586; lesson 3). The event is written only if, re-read under the
     item's lock, the sha it passed on is the item's `main` or a descendant of it, so a newer break written in
     between is not cleared (lessons 1 and 2).
   - **The repair clock starts once.** Today every `flake.main-broken` writes a fresh `main_broken_at`
     (dev/bin/onmain.py:92-94), so a second gap that hits the same failure on a newer main would restart the clock.
     The writer re-reads the item under its lock. For an item already in `main-broken`, it updates `main` to the
     newer sha, since `main-fixed` must then pass on that sha or a descendant. It leaves `main_broken_at` alone and
     records the event's `seq` as `main_broken_seq` only when the item enters the state. `main-repair-hours`
     measures from that first event, chosen by `seq` and never by comparing stamps (lesson 2), to `flake.main-fixed`.
   - **`seen` no longer clears `main-broken`.** Each writer of `flake.seen` (dev/bin/onmain.py:74, dev/bin/queue.py:207,
     dev/bin/triage.py:71, dev/bin/manage.py:231) checks the item's state first, and for an item in `main-broken`
     writes `flake.measured` instead, which counts `times` and moves no state. A test still failing on main therefore
     never moves into the flake count.
   - **A person's way out.** `manage.py` gets a `flake-fixed TEST --why W` command that writes `flake.fixed` from
     either state, recorded as an intervention. This covers a test that was deleted or renamed, which no run can
     clear, so the goal stays off until someone has looked: it fails closed.
   - **Release and remake.** The quarantine's release (fac.beside's `quarantined: false`, dev/bin/fac.py:594-596)
     becomes one event, `flake.released`. The same-id remake is tested: a flake seen or broken again after `fixed`
     starts a new count and a new `main_broken_at` and `main_broken_seq`, with its old `times` and `main_fixed_at` cleared (lesson 5).

   Acceptance: tests for fixed after N, and not fixed after N−1 with one failure between; `main-fixed` after main
   is fixed; still `main-broken` when the alone run is skipped or unreadable; a `main-broken` written between the
   check and the write is kept; a `flake.seen` on a `main-broken` item leaves it `main-broken`; a second
   `flake.main-broken` on a later main keeps the item's first `main_broken_at` and `main_broken_seq` and moves its
   `main`, so `main-repair-hours` runs from the first break; and the remake.

3. **flake-rate-counts-excused.** `flake-rate` counts the queue's excused flakes (dev/bin/queue.py:206-208) as well as
   triage's retries (dev/bin/measure.py:167-169), over all queue runs. A window with no runs gives no value, not 0.0.
   Acceptance: a test of a run excused in the queue that moves the rate, and a test of an empty window that exits
   without a value.

4. **escapes-recorded.** The sources of escapes get sensors: the inflow `escapes-found` gets one (it has none:
   dev/model/pools.yaml:66-69). A revert commit on main naming a merge (`This reverts commit`) is read by `main-watch`
   and recorded as `gap.reverted` by the gap whose `main_sha` it names. A revert that matches no gap is an escape at
   the pool size then, as risk.py already does for main-broken (dev/bin/risk.py:86-88). Acceptance: a revert commit
   on a test repository records the escape on its gap, and an unmatched one still counts.

5. **guarantees-model.** `dev/model/guarantees.yaml`: the `guarantees` system and the stocks, auxiliaries and goals of
   section 4, the sensors in `dev/bin/measure.py`, every goal `on-stale: off`, and the named loops. `ergostat check`
   is clean: no unsigned link, no missing feedback, every named loop balancing. Wiring into `factory-off`. It
   depends on gap 2: without `flake.main-fixed`, `main-failing-tests` never falls, so `main-green` would stay off
   after the first time main breaks. One part goes to the owner as its own question in the definition, because it
   slows landing: should `main-green` also hold the queue for any batch while main has a failing test that the batch
   does not touch (`queue-when`, dev/model/landing.yaml:309-319)? Such a hold lifts as soon as `main-fixed`, or a
   person's `flake-fixed`, empties the stock. Acceptance: `ergostat check` on the factory; a test per sensor of its
   fail-closed reading; and a test that a `flake.main-broken` followed by its `flake.main-fixed` sets `main-green`
   off and then holding again.

6. **escape-learning-loop.** On each escape, the librarian is given the escape's cause and asked for a lesson or a
   new test. `lessons-recurring` and its goal `lessons-hold` are read from the lesson items. Acceptance: a recorded
   escape starts one librarian step and only one (a lease, lesson 1), and a recurrence of a carried class moves the
   measure.

7. **regressions-template.** `ergostat/library/templates/regressions/`: the user's version of section 6b. Its passing
   counts come from the declared `claims: tests`, its escapes from trust, its regressed fixes from repair. It adds a
   goal to the repair template, `fixes-hold`: no fix regressed in the last 14 days, read from the flow
   `fixes-regressed` (ergostat/library/templates/repair/template.yaml:63) over that window, `<= 0`. The goal is not
   put on the stock `regressed-fixes`, because a denied revert leaves a failure `regressed` for good
   (docs/SPEC.md:6293), so a goal there could never recover. The goal recovers when a window passes with no new
   regression. Each regressed fix already has its revert asked in the inbox as a gated action (docs/SPEC.md:6278-6280).
   SPEC §12r's parts table catches up. SPEC gains a section on
   regression guarantees, and the agent guide a paragraph on when to offer the template. Acceptance: a demo model
   using it passes `demo_check`, a run with a failing test sets its goal off, and an unreadable test command leaves
   the goal stale and off, never holding.

8. **guarantees-on-the-diagrams.** No UI code is expected. This gap checks that section 5's claims hold: screenshots
   of each regression goal off, in Dynamics (its excess), Blocks (red on its chart) and Process (a flake stuck in
   `seen`), under the browser suite, and a browser test that fails when a goal that is off is drawn as holding (lesson
   9: broken once and seen to fail). A claim that does not hold is fixed in the model's layout, or narrowed in this
   proposal.

## 8. Choices taken without the owner

No one was available to ask. Each choice below is the most reversible option:

- **Proposed, not built.** No model file, sensor or test is added here. Each piece is a milestone gap that can be
  dropped or reordered.
- **A new file, not edits to the existing ones.** `guarantees.yaml` holds everything (gap 5). Taking it out takes the
  whole proposal out, and `pools.yaml`, `measures.yaml` and `landing.yaml` change only where they are wired in.
- **People close the loops.** Every new loop ends in the coordinator, the librarian, or a gated action. No guarantee
  breaking acts on the world by itself. Holding the queue while main is red (gap 5) is asked as a separate question,
  because it slows landing.
- **Every regression goal can recover.** A goal whose stock has no way out stays off for good and stops saying
  anything. `main-failing-tests` therefore gets `flake.main-fixed` (gap 2) rather than being read from the counts of
  main's latest queue run. A green run has no failures by definition, so it could not name which test was fixed.
  `fixes-hold` reads a window of the flow `fixes-regressed`, not the stock `regressed-fixes` (gap 7). Where no run
  can clear an item (a deleted test), a person's `flake-fixed` does, so the goal stays off until someone has looked.
- **Opt-in for users.** Users get a template, never a default, under invariant 12.
- **The setpoints are placeholders** (`<= 3`, `<= 24` h, `<= 0.05`). Each is a parameter that the owner sets, as
  `risk-tolerance` is (dev/model/pools.yaml:87-90).
