# ergostat-s-upkeep-as-a-modelled: the start-up heartbeat keeps its stale limit, and restarts get a goal
depends-on: []

## Definition of done
The template `use: upkeep` and its index-file, record, watched, lease and pool loops are already on main (see the GAPS entry's three done lines). This gap closes the two open points in that entry's "Left" clause:
1. The `heartbeat.json` that `ergostat run` writes as it starts carries the previous `heartbeat.json`'s `stale` when that value passes `stale_ok` (60 to 3600). The outer watcher then uses the last model's limit, not 180, until the watchdog's first beat writes the current model's limit. Any of these leaves `stale` out (the watcher uses 180, as today) and does not raise: a missing or unreadable previous file, invalid JSON, or a `stale` that is missing, a bool, NaN, out of range or not a number. A shard engine's `heartbeat.SHARD.json` follows the same rule from its own file.
2. The template has a goal `few-restarts` on the stock `restarts`, `hold: "<= ${restarts-most}"`. The new integer parameter `restarts-most` has a default of 3, a min of 0 and a max of 100, and compile refuses a value outside that range. The owner is drawn as the goal's last layer: a `type: person` block, as `pool-keeper` is. Ergostat never acts on restarts itself, and no goal changes the watcher or the watchdog.
3. `ergostat check` on a model with `uses: {upkeep: {use: upkeep}}` is clean, with no warning beyond what main gives today.
4. SPEC §2a (Upkeep), the template's `reading:` and the GAPS entry are updated: the "Left" clause loses these two points and keeps only "the loops are drawn, not closed by ergostat".
5. Unit suite, four browser files, and ruff pass with origin/main merged in. The record `dev/records/ergostat-s-upkeep-as-a-modelled.md` is the first commit.

## Relation to other work
- merge-pipeline-gaps-md-regenerated-on-land: moves GAPS entries into records. Edit only this entry's Left line, and re-check it after merging main (lesson-7).
- operating-state-record: also edits docs/SPEC.md and docs/GAPS.md. The sections differ, so only a merge conflict risk; no wait.

## Files to touch
- `ergostat/cli/running.py`
- `ergostat/spec/watchdog.py`
- `ergostat/library/templates/upkeep/template.yaml`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `dev/records/ergostat-s-upkeep-as-a-modelled.md` (new)
- `tests/test_upkeep_watched.py`

## Risks
- lesson-3: a bad previous `stale` (a bool, NaN, a huge number or a string) gets carried into the new heartbeat, or a corrupt file crashes the start. Every bad input must drop `stale`.
- lesson-4: `restarts-most` without a ceiling. Compile must refuse anything over 100.
- lesson-9: a test that seeds the previous file and never runs the real start path, so deleting the carry-over leaves it green.

## Acceptance tests
- `tests/test_upkeep_watched.py::test_start_heartbeat_keeps_previous_stale`: writes a previous heartbeat with `stale: 900` and runs the start-up write. The new file has `stale` 900, a new pid, and the watcher's limit reads 900. The test fails if the carry-over is removed.
- `tests/test_upkeep_watched.py::test_start_heartbeat_drops_bad_stale`: covers the previous file being absent, holding invalid JSON, or giving `stale` as `true`, NaN, 30, 99999 or `"600"`. In each case the start heartbeat has no `stale`, the watcher uses 180, and nothing raises.
- `tests/test_upkeep_watched.py::test_shard_start_heartbeat_reads_its_own_file`: a shard's start heartbeat takes `stale` only from `heartbeat.SHARD.json`, never from the main file.
- `tests/test_upkeep_watched.py::test_few_restarts_goal_compiles`: the default model has the goal `few-restarts` at `<= 3` on `restarts`, served by a person block, and `check` is clean.
- `tests/test_upkeep_watched.py::test_restarts_most_bounded`: `restarts-most: 101` and `-1` are each refused at check.

## Size budget
40 net lines
size: S (confidence: medium)

## Where it stopped
Built, round 1: 29 net lines outside tests and docs (watchdog.py +12, template.yaml +17, running.py 0).
- The carry-over is `heartbeat(..., start=True)` in `spec/watchdog.py`. It reads `stale` from the file the call is about
  to replace, so a shard's start write reads `heartbeat.SHARD.json` and never `heartbeat.json`. No code on main writes a
  start heartbeat for a shard engine today (only `cli/running.py` writes one, for the main file), so the shard rule is
  covered at `heartbeat()` itself (`test_shard_start_heartbeat_reads_its_own_file`). Adding a shard start write would
  be outside this gap.
- Two guards drop a bad `stale`: `_last_stale` checks `stale_ok`, and so does the write itself. So
  `test_start_heartbeat_drops_bad_stale` fails when the exception handling is cut (it was seen to fail on the
  invalid-JSON, non-object and 100,000-deep `[` cases, a RecursionError) but stays green when only `_last_stale`'s
  `stale_ok` check is removed. `test_start_heartbeat_keeps_previous_stale` runs the real `cmd_run --foreground` start
  path, stopped at `startup`. It was seen to fail (KeyError on `stale`) with `start=True` removed from `running.py`.
- A choice made without anyone to ask: a person block must have an output, and `restarts-made` already has
  `outer-watcher` as its one setter (`two-actuators`). So `restarts-keeper` is drawn as `out: block.outer-watcher`:
  the owner's one real hold on restarts is the watcher, which obeys `ergostat run --stop` and `--service --uninstall`.
  This is a drawn command only. No goal and no code changes the watcher or the watchdog, and nothing runs. If that edge
  reads wrongly, the other choice is a flow of the owner's own.
- `tests/test_upkeep_template.py` lists the template's parts exactly, so it now includes `few-restarts` and
  `restarts-keeper`. docs/AGENT-GUIDE.md's line on `use: upkeep` now names the goal.
- "`check` clean, no warning beyond main": checked by `test_few_restarts_goal_compiles`. It allows no finding except
  `no-modelling-loop` and no check message about restarts. A side-by-side run of `ergostat check` against main's
  template was not run, because the sandbox refused the ad-hoc command.

Round 2 (answering the one review finding): 32 net lines outside tests and docs (watchdog.py +15, template.yaml +17).
- Change from the definition, done item 1: the start heartbeat carries the previous `stale` only when it passes
  `stale_ok` **and is at least the watcher's `STALE` (180 s)**. A carried 60 to 179 s would let the watcher stop a
  start still inside its own 120 s `STARTUP` deadline, losing the start-up watchdog's record of why it was slow, and
  every restart would carry the same short limit again. So a start only ever gets a longer limit than main gives. Of
  the two fixes the review offered, dropping such a `stale` was chosen over writing `max(previous, 180)`: the watcher
  reads both the same (180), and dropping writes nothing the model did not set. Once the watchdog's first beat writes
  the current model's `stale` (any 60 to 3600), the short limit holds as before; only the start write is affected.
  The 180 is read from `watcher.STALE`, not copied.
- Tests: `test_start_heartbeat_never_shortens_the_limit_inside_startup` (previous 60: no `stale`, watcher at 180;
  previous 180: carried), and `test_start_heartbeat_drops_bad_stale` gains 60 and 179.9. With the `>= STALE` check
  removed, both were seen to fail (the new test, and the 60 and 179.9 cases).
- SPEC §2a's start-heartbeat paragraph and the template's `reading:` now say 180 to 3600 and why.
