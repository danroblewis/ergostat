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
