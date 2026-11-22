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
