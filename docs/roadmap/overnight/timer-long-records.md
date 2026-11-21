# timer-long-records: The state timer works on a long record

depends-on: []

Audit 2026-11-21 (reproduced): above 500 events `dev/bin/times.py` calls `ergostat events`, which is not a command (exit 2), and its bookmark is saved only at the end, so every later run fails on the same gap. The largest gap has 326 events. The test mocks that call. `times.py setpoints` was also never run, so the time goals' holds are guesses.

## Definition of done
The timer reads a gap of any length through a real command, and one unreadable gap does not stop the rest. Setpoints are derived from the record once and recorded.

## Files to touch
`dev/bin/times.py`, `dev/model/times.yaml`, `tests/test_factory.py`.

## Risks
- lesson-9: the test must run the real command.

## Acceptance tests
- `tests/test_factory.py::test_the_timer_reads_a_gap_past_500_events`
- `tests/test_factory.py::test_one_unreadable_gap_does_not_stop_the_timer`

## Size budget
30 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, by the implementor (headless, no one to ask).

Done:
- A long record (past the 500 events `ergostat item --json` carries) is read whole through the real command,
  `ergostat event --item ID --type gap.*,ergostat.item.snapshot --json -n N`, with N its record_total + 1,000. A page
  that comes back full (it may be cut) and a gap past `LONGEST` (100,000 events) count as unreadable, not as read
  (lessons 3 and 4).
- `write`: a gap that cannot be read (the command fails, its output is not JSON, its timing cannot be made) keeps its
  bookmark, the other gaps are still timed, the bookmark is saved, and then the run fails (SystemExit, exit 1) naming
  each unreadable gap. A gap that stays unreadable is tried again every run and fails each one, which is loud on
  purpose: skipping it quietly would fail open (lesson 3).
- `times.py setpoints` now rewrites a `# setpoints:` line in dev/model/times.yaml (the date, how many gaps, how many
  holds were set), so the holds show whether they were ever derived. The line is committed as "first guesses, never
  derived from the record".
- Tests, in tests/test_factory.py, against a real project and `python -m ergostat` (no fake command):
  the two acceptance tests, plus `test_setpoints_record_when_they_were_derived`. Broken on purpose to watch them fail
  (lesson-9): the command put back to `events` fails `test_the_timer_reads_a_gap_past_500_events`; the per-gap
  `except` turned into a re-raise fails `test_one_unreadable_gap_does_not_stop_the_timer`.

Left: the setpoints were not derived from the record. The factory's record (its instance's folder) is not in this
container, so `python3 dev/bin/times.py setpoints` cannot be run from here; the holds in dev/model/times.yaml are still
the first guesses, and its `# setpoints:` line says so. The most reversible choice was to leave them as they were rather
than invent numbers. Someone with the instance has to run it once, in the instance's folder, and commit the
rewritten times.yaml. Until then, the last sentence of the definition of done is not met.

Not run: the whole unit suite and the four browser files (the factory runs them under the watchdog). There is no origin
remote in this clone; local `main` (3e006736) is already an ancestor of the branch.

## Where it stopped

Parked by the factory (review/timer-long-records-1, 2026-11-21 04:42).

Done: a long record (past the 500 events `ergostat item --json` carries) is read through the real `ergostat event --item ID --type gap.*,ergostat.item.snapshot --json -n N`, with a ceiling (LONGEST) and a full page counted as unreadable. One unreadable gap keeps its bookmark, the others are timed, the bookmark is saved, and the run fails naming it. `times.py setpoints` stamps a `# setpoints:` line in dev/model/times.yaml. The two acceptance tests run the real command. Left: the definition's last sentence, setpoints derived from the record once and committed. This needs `python3 dev/bin/times.py setpoints` run in the instance's folder, which no implementor container has, so another fix round cannot finish it. Either someone with the instance runs it on this branch and commits the rewritten times.yaml (then it can be reviewed for merge), or the owner moves that sentence to its own gap done in the instance and this branch is judged on the timer part alone.

**The coordinator's decision (2026-11-21):** the definition's last sentence ("Setpoints are derived from the record once and recorded") is out of this gap's scope. It needs the live instance's record, which no implementor session or reviewer has, so asking for it here was the coordinator's mistake. Judge this branch on the timer alone: it reads a gap of any length through a real command, and one unreadable gap does not stop the rest. The coordinator runs `times.py setpoints` in the instance once this version is live.

## Where it stopped

Round 2, by the implementor (headless), answering every finding of review/timer-long-records-1 (lesson-12):

- dev/model/times.yaml:7, setpoints not derived: out of scope by the coordinator's decision above. The holds and the
  `# setpoints: first guesses` line stay as they are, for the coordinator to run in the instance.
- The full-page and LONGEST guards untested: `test_a_long_gap_past_its_ceiling_or_a_full_page_is_unreadable_not_half_read`
  (LONGEST monkeypatched below the gap's 602 events; then 1,000 events said between `ergostat item` and the real
  `ergostat event`, so the page comes back full). Broken on purpose: `>=` made `>` fails it, and LONGEST*10 fails it.
- KeyError and TypeError in the per-gap except: removed. Only a failed read (RuntimeError from a failed command,
  ValueError from bad JSON or a guard, OSError, SubprocessError) counts as unreadable; a bug in timing() is a traceback.
- The stamp quietly skipped when the `# setpoints:` line is gone: `setpoints` now fails (SystemExit) and writes
  nothing (`test_setpoints_refuse_a_model_with_no_stamp_line`; broken on purpose, the check made `if False`, it fails).

Size: 27 net lines in dev/ (times.py +33/-7, times.yaml +1), within the 30.
Run: tests/test_factory.py whole, 102 passed and 2 skipped (they need Docker and the agent image, which this branch
doesn't touch); ruff on ergostat, tests, scripts and dev/bin/times.py, clean. Not run: the whole unit suite and the
four browser files (the factory runs them under the watchdog). No origin remote to merge; main (4c21667b) is already
merged in.
