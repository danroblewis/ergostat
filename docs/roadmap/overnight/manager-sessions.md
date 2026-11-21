# manager-sessions: the pipeline manager sees the whole pipeline, on a schedule and when the merge pipeline breaks

depends-on: []

Branch `manager-sessions`, from main. The owner, after watching the pipeline manager one situation at a time: "The
pipeline manager shouldn't work one gap at a time. The pipeline manager should probably be on a schedule, or it should
be triggered by events (when the merge pipeline is broken somehow for a long enough time). The pipeline manager can
also routinely review the current pipeline and research potential ways we can speed up the merge pipeline."

## Definition of done

1. **One session sees the whole pipeline.** The watch (`dev/bin/watch.py`) no longer raises one trigger at a time:
   each session's `situation/*` carries every standing trigger (parks, dead letters, stuck gaps, the queue blocked,
   aging defects), less those an earlier session already handled (by fingerprint). The brief shows them all; the
   session acts on all of them through manage.py (at most `[manager] most_actions` calls a session) and says, per
   trigger, what it did or why it left it (`answers` on the situation).
2. **When it runs.** On a schedule (`[manager] every`, 2h by default), and at once when the merge pipeline is broken
   for longer than `[manager] broken_minutes` (30): the queue blocked, a pending push older than that, no merge in that
   long while approved gaps have waited as long, the same test failing on two different main commits, or the load
   interlock holding the queue that long while approved gaps wait. The watch keeps when each condition began
   (`run/manager.json`). No session when nothing changed since the last (no new trigger, no new broken condition, the
   pipeline the same), whatever the schedule says. The watch is a plain `every: 5m` block (no `goal:`).
3. **Routine review and research.** Every scheduled session's brief carries the velocity record: queue wait, minutes
   per merge and per batch, batch size and batch failures (bisected batches), time in each state, first-pass yield,
   merges per hour, each queue goal's reading against its setpoint and the binding constraint (the goal furthest off),
   and the answers to the researcher's questions it asked before. It either proposes a change (`propose`, a gap with
   a definition: at most one of its proposals open at a time) or asks the researcher (`ask`, a `research.asked`: at
   most one of its questions open) how to speed up the merge pipeline.
4. **Kept:** the gated asks (close, park, pool, change), the intervention per action, the knowledge brief. Parks that
   are `deferred` or `cancelled` are not triggers (the instance's edit), and the brief carries the owner's decisions
   (dev/knowledge/decisions.md: continue, don't rebase; deferred stays deferred).
5. **The model** (`dev/model/manager.yaml`): the schedule (`minutes-since-manager`, with a goal at `every`) and the
   broken-pipeline condition (`pipeline-broken-minutes`, with a goal at `broken_minutes`) driving the situations the
   watch raises; the manager's sessions in the AI spend; the measures `manager-triggers-per-session` and
   `manager-actions-per-session`.

## Acceptance tests

`tests/test_factory_manager.py`, with the stand-in AI:

- `test_one_session_carries_every_standing_trigger_and_answers_each`: several triggers in one situation, handled in
  one session, each with its answer; handled ones are not carried again.
- `test_a_broken_pipeline_starts_a_session_at_once`: a pending push older than `broken_minutes` raises a session before
  the schedule is due; one younger does not.
- `test_nothing_changed_means_no_session`: the schedule due and nothing new: no session.
- `test_the_review_proposes_at_most_one_gap_and_asks_at_most_one_question`.
- `test_deferred_and_cancelled_parks_are_not_triggers`.
- each broken condition (blocked, push, no merge, main twice, interlock) and the batch measures in the velocity record.
- The tools' tests as before (continue, reapprove, flake, file-gap, remedy, the gated asks, interventions).

## Size budget

450 net lines of the programs in `dev/bin/` (the model, the prompt, tests and docs apart), most of it rewritten.

## Where it stopped

Built by a coordinator's agent and handed to the factory unmerged. Items 1 to 4 of the definition are built; item 5 is
built but for the goal named in "Left to do" 3. It has run only on fixtures with the stand-in AI: never on the live
instance, a real session or the real load probe.

**Suites** (on the work commit, based on main 0ecf249, 14 commits behind origin/main when this was written, with
`ergostat.yaml` changed on both sides):

- factory and manager tests: 120 passed;
- unit suite: **1 failed**, 2083 passed, 14 skipped, 1 xfailed;
- ruff: clean. `ergostat check`: ok, 43 of 43 goals closed by a loop.

**The failure, not fixed:** `tests/test_factory_manager.py::test_a_trigger_left_unanswered_or_a_failed_session_comes_back`
fails about one run in three, alone too. Cause, measured over 8 runs (3 collisions, and the same 3 failures): `raise_one`
names a situation by the second (`situation/<reason>-YYYYmmdd-HHMMSS`), so two raised within one second are one item,
and the later overwrites the earlier's `prints`. The ids need something unique; the test's bound should not be loosened.

**Left to do, found on reading the code (none has a test yet):**

1. `main-twice` reads every `main-broken` intervention, remedied ones too, so once a test has failed on two main commits
   the condition never clears: `pipeline-broken-minutes` grows and `merge-pipeline-flowing` stays off for good. It should
   read only unremedied ones, or a recent window.
2. Situations already in the live record carry `print`, not `prints`, so they do not count as handled: the first session
   after the switch is given every standing trigger again. One left `raised` by the old code would be taken with no
   `triggers`. The switch needs both handled.
3. The definition's goal on `minutes-since-manager` at `every` is **not built**: that reading rightly grows while nothing
   changes, so such a goal would sit off. Decide whether to drop it from the definition's intent or hold it differently.
4. `manage-when`'s `max(1, stuck, broken)` always equals 1: it only draws those goals into the loop. The hold of 30 on
   `merge-pipeline-flowing` repeats `[manager] broken_minutes` and will not follow a change to it.
5. The earlier cap `interventions_per_hour` is gone, as each session now takes all triggers at once. The limits are now
   `most_actions` (8) and the 6 gaps given in full; a trigger left unanswered returns at the next session.

**The coordinator's decisions for the implementor (2026-11-21):**
- Fix the flaky test in the code: give each situation a unique id. Leave `test_a_trigger_left_unanswered_or_a_failed_session_comes_back` as it is.
- `main-twice` counts only unremedied `main-broken` interventions, with a test that it clears once remedied.
- Read old situations (`print`, no `prints`) without raising every standing trigger again; an old one still `raised` is closed as superseded, never run with no triggers.
- Drop the goal on `minutes-since-manager` and keep it as a measure: it rightly grows while nothing changes.
- Make `manage-when` depend on what it claims to read, or remove the `max(1, ...)` and draw the triggers honestly. The hold on `merge-pipeline-flowing` follows `broken_minutes`.
- This has run only on fixtures: say so in the report. Main has moved and `ergostat.yaml` changed on both sides, so keep both when merging.

**The implementor, round 1 (2026-11-21): each decision, as built.**
- *Unique ids:* a situation's id is `situation/<reason>-<UTC second>-<6 hex>` (`secrets.token_hex(3)`), so two raised in
  one second are two items. Test: `test_each_situation_raised_has_its_own_id`. The flaky test is unchanged and passed
  5 runs of 5 here (3 alone, 2 in the whole file).
- *`main-twice`* reads only open `main-broken` interventions with no `remedy` or `remedied_at`.
  `test_each_broken_condition` now has both open, then remedies one and sees the condition clear.
- *Old situations:* an old one (`print`, no `prints`) that was handled or failed counts its `print` as looked at (the
  fingerprints are the same function, `watch.sit`, so they match). One still `raised` is closed with the new event
  `situation.superseded` (a new state `superseded` of the kind in `ergostat.yaml`, in its `done` list and the block's
  `takes.to`) before any clone or session. Its trigger is not counted as handled, so if it still stands it goes to the
  next session. Test: `test_situations_of_the_one_trigger_watch_are_read_and_an_old_raised_one_is_superseded`.
- *No goal on `minutes-since-manager`:* left as a measure. Its description says why. Definition item 5's "with a goal at
  `every`" is therefore not built, by the coordinator's decision. The model test asserts that no goal is on it.
- *`manage-when`* now reads only what its expression uses: `waiting * min(open, 1) * (1 - over)`. The goals
  `no-stuck-gaps` and `merge-pipeline-flowing` are now read by `pipeline-watch` (`in:`), which is honest because the
  watch is what finds them. No block commands the watch, so the engine keeps it on its own `every: 5m` schedule
  (`engine.due`: a block with `every` and no commander runs on its schedule), and it stays a plain block with no
  `goal:`. The model test asserts that all three manager goals are still closed by a loop (`spec.loop(g).closes`).
  This is the reversible choice, since the `in:` is drawing only. `ergostat check` itself was refused by this session's
  shell and was not run.
- *The hold follows `broken_minutes`:* `watch.py broken` now reads the minutes **past** `broken_minutes` (`main-twice`
  from its start, as it counts at once), and `merge-pipeline-flowing` holds `<= 0`. Test:
  `test_the_broken_reading_is_the_minutes_past_broken_minutes`, with `broken_minutes = 20`.
- *Only on fixtures:* this round too ran only on fixtures with the stand-in AI. It never ran on the live instance, a
  real session or the real load probe. Local `main` was already merged (4cabb2e). This clone has no `origin/main`, so
  merging origin/main is left to the merge queue.
- *Size:* 149 net lines in `dev/bin/` against main, within 450.

**The implementor, round 2 (2026-11-21).**
- *Merge of main 24756e5:* conflicts in `dev/bin/measure.py` (the docstring: both the manager's measures and main's
  time-in-state measures kept, "the last three" now "the last four") and `ergostat.yaml` (`messages.done`: the branch's
  `situation: superseded` and main's `lesson: denied` both kept).
- *The review's finding (first-pass-yield's `off`):* `manager.off(direction, setpoint, reading)` reads the goal's own
  direction from its `hold` in `measures.yaml` (the same pattern as `watch.HOLD`), not the measure's name. For a `>=`
  goal it is `setpoint / max(reading, 0.01)`, so a yield of 0 is the worst case (0.6 / 0.01 = 60), never on target; for
  a `<=` goal `reading / max(setpoint, 0.01)`. A goal's `hold` in the record now reads with its direction (`">= 0.6"`).
  Test: `test_a_first_pass_yield_of_zero_is_the_worst_case_and_binds`: a yield of 0 binds over a queue wait off by 2.5;
  0.5 reads off 1.2 and binds when the queue wait is on target; 1.0 reads 0.6 (the right side). With the old formula
  put back, the test failed (yield 0 read off 0.0); with the fix it passes.
- *Only on fixtures:* still never run on the live instance, a real session or the real load probe.
- *The fast suites after round 2:* the `unit` run stopped at 64% with no failing test, error or traceback in its tail,
  as main's own run did for lesson-denied-settles (24b1c81e). That points to a killed or timed-out run, not a failing
  test. No code was changed for it. Re-run here one file at a time, all pass: `tests/test_factory_manager.py` (26),
  `tests/test_factory.py` (59, 2 skipped), `tests/test_factory_times.py` (7), `tests/test_factory_knowledge.py` (52),
  and `tests/test_interventions.py`, `test_gated_actions.py`, `test_leases.py`, `test_backlog.py` (62 together, as they
  read the kinds in `ergostat.yaml`). Ruff is clean. No conflict markers are left from the merge. The whole unit suite
  was not run here (it is the factory's to run under the watchdog), so if it stops again the factory should rerun it.

**The implementor, round 3 (2026-11-21): every finding of review/manager-sessions-2.**
- *Merge of main 278666f:* conflicts in `dev/bin/watch.py`, `dev/bin/measure.py`, `dev/factory.toml` and
  `dev/README.md`. Main's park kinds (`parks.py`) are kept: a `waiting` trigger for a `waits_on` / `needs` park past
  `park_wait_hours`, and a `parked` trigger only for a kind no program resumes. The branch's `deferred` / `cancelled`
  fields stay excluded too. Main's `heartbeat_minutes` / `interventions_per_hour` and its velocity-watch paragraph are
  dropped, because the branch replaced them with the schedule and the routine review. Main's two park tests in
  `tests/test_factory.py` (`test_a_defect_park_is_never_resumed_by_the_program`,
  `test_a_waiting_park_past_its_hours_raises_a_situation`) read the one-trigger shape (`s["trigger"]`). They now read
  the session's `triggers`, and they check the same things: the three parks are carried in one session, and a waiting
  park is raised once.
- *`most_actions` (blocking, lesson-4):* held to 1..12 (`watch.MOST_ACTIONS`) at read time. Test:
  `test_most_actions_has_a_floor_and_a_ceiling` (-5 and 0 give 1, 500 gives 12, 8 stays 8). With the clamp removed,
  it failed (`-5 == 1`).
- *A goal not found (blocking, lesson-3):* if an interlock goal (`watch.INTERLOCK`) has no hold in `interlock.yaml`,
  that is itself the broken condition `interlock` ("... have no hold"). It is never read as within its limit, and it
  holds whether or not gaps wait. If a review goal has no hold in `measures.yaml`, it is in the record with
  `unknown` and `off: null`, and it is the binding constraint. Test:
  `test_a_goal_the_watch_or_the_review_cannot_find_never_passes_silently`. With either guard removed, it failed (the
  watch on its own, then the review on its own).
- *"At once" wording (non-blocking):* the README and the watch's docstring now say that a broken-pipeline session
  starts before the schedule, but never sooner than `broken_minutes` after the last session of any kind.
- *From park-owns-resume-1, on this file:* `park_wait_hours` now has a floor of 1h. The README says that a `split` park
  is never a trigger, because each stopped sub-gap raises its own.
- *Not run (the review's fourth finding):* this round ran these, one file at a time: `tests/test_factory_manager.py`
  (28 passed), `tests/test_factory.py` (66 passed, 2 skipped), `tests/test_factory_times.py` (7),
  `tests/test_factory_knowledge.py` (52), and `test_interventions/gated_actions/leases/backlog` together (62).
  Ruff is clean. The whole unit suite and the four browser files were **not** run here. The factory runs them under
  the watchdog.
- *Only on fixtures:* this round too ran only with the stand-in AI. It never ran on the live instance, a real session
  or the real load probe.
- *Size:* 168 net lines in `dev/bin/` against main, within 450.

**The implementor, round 4 (2026-11-21): the `unit` run that stopped at 83%.**
- *The merge of main 278666f* was already committed (ab8fe4bb), with no conflict markers left. Nothing was left to
  resolve.
- *What the tail shows:* the run ends partway through a line of dots. No test failed, there is no error, no xdist
  "worker crashed" line, and suite_watch printed no closing JSON line, so suite_watch itself was ended from outside.
  `fac.suite` has no timeout, and `resources.sampled` never kills a container. That points to the suite container
  being killed (by memory, or by whoever stopped the run), as in round 2 (64%) and in main's own lesson-denied-settles
  run. No test fails here, so this round changes no code (lesson-13).
- *Ruled out by measuring:* the slowest thing in the branch's tests is `read(ergostat.yaml)`, about 60 s in a fresh
  process. Profiled, nearly all of that time is the extreme-conditions run (`extremes_cache.background`), stopped at
  its `BOUND` of 60 s. This is the same on main: main's model has 457 conditions, with 73 skipped at the bound; the
  branch's has 466 conditions, with 89 skipped in a cold process. The branch adds 9 conditions, which does not change
  the cost. The test fixtures (`Pipe`, `Instance`) start only short-lived subprocesses (`subprocess.run`), and nothing
  is left running.
- *Ran this round, one file at a time:* `tests/test_factory_manager.py` 28 passed; `tests/test_factory.py` 66 passed,
  2 skipped. Ruff is clean. The whole unit suite was not run here: the factory runs it under the watchdog and should run
  it again. If it stops again with no failure shown, the cause is the container, not a test.
- *A stray file:* `tests/test_zz_profile_tmp.py`, an untracked diagnostic, was emptied to a comment because this
  session's shell refused `rm`. It is not committed. Delete it.
- *Only on fixtures:* still never run on the live instance, a real session or the real load probe.
