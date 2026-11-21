# upkeep-index-files: a built-in `use: upkeep` template whose first loop holds ergostat's item-index files under a goal, tidied by a rule-tier controller instead of the constant `KEPT_FILES`
depends-on: []

## Definition of done

Today the engine tidies item-index files by itself. `index_for` calls `_tidy` whenever it makes a new file (`ergostat/spec/itemindex.py`, `KEPT_FILES = 6`, `TIDY_AGE = 3600`), and nothing about it is visible in the model. When this branch is done:

1. **The template.** `ergostat/library/templates/upkeep/template.yaml` exists:
   - It has `template: upkeep` and `once: true`. Its parts keep the names written in it, in a system named for the use (`upkeep` by convention).
   - It has a `description:`, a `reading:` (system dynamics and control, in the style of `modelling/template.yaml`) and an `example:` (`uses: {upkeep: {use: upkeep}}`).
   - `test_every_built_in_template_checks_with_its_example` (existing, parametrised) passes for it, with no finding from its own parts.
2. **The index-files loop.** The template's parts are:
   - stock `index-files` (unit `files`), read by `builtin: ergostat.upkeep.index-files`;
   - stock `retired-index-files`, read by `builtin: ergostat.upkeep.retired-index-files`;
   - inflow `index-files-made` (`changes: rises`): made on each change to the model's item kinds;
   - outflow `index-files-tidied` (`changes: falls`);
   - goal `index-files-few`: `index-files <= ${index-files}`, default 6;
   - goal `no-retired-index-files`: `<= 0`;
   - controller `index-tidier`: `type: program` (the rule rung), `goal: index-files-few`, `run: ${lib} upkeep tidy --keep ${index-files}`, `every: ${tidy-every}` (default 10m), `out: flow.index-files-tidied`.
3. **The measures.** `ergostat.upkeep.index-files` counts the live `<hash>[.n].db` files under `<state>/items`, leaving out retired ones. `ergostat.upkeep.retired-index-files` counts the retired ones.
   - Both are registered beside the other families: `UPKEEP` regex and `UPKEEP_MEASURES` in `spec/ir.py`, `is_measure`, `numbers/measures.measure`, and the `bad-measure` message in `spec/compile.py`.
   - When the record is kept nowhere on disk, or `<state>/items` cannot be listed, a measure gives no reading (`None`, said in the sensor's log). It never gives 0.
4. **The controller never reads what it manages.** `python -m ergostat.library.run upkeep tidy --keep N` works from the state directory alone (`run/common.state_dir()`):
   - It never calls `project()` or `index_for`, and never opens an index database. It only takes each file's lock file without waiting, as `_tidy` does.
   - It removes retired files no process has open. It then removes the least recently changed live files, down to `N`.
   - It prints one result line: removed, left, and skipped as held or young.
   - `--keep` outside 1..64 is refused, with exit 2. The `index-files` value outside 1..64 is an error when the model loads, naming the use and the parameter. That makes two checks, one at config time and one at run time (lesson-4).
   - It removes only files whose names match `^[0-9a-f]{16}(\.[0-9]+)?\.db$` (with their `-wal`, `-shm` and `.lock`), and only when the path resolves under `<state>/items` (lesson-11).
5. **The interlock stays in the code.** Whether a delete is safe is still decided only in `itemindex.py`: the exclusive lock taken without waiting, and no change within `TIDY_AGE`. Neither the goal nor the template can change it.
   - `_tidy` takes `keep` as a parameter (default `KEPT_FILES`).
   - It checks a file's age again **after** taking the exclusive lock, before it deletes. Today it checks only before.
6. **The engine stands down from that loop.** In a model whose `uses:` has an entry with `template: upkeep`, `index_for` no longer calls `_tidy` when it makes a file; the `index-tidier` block does that work.
   - In a model without it, behaviour is exactly as on main (invariant 12: an empty install runs nothing new).
   - If the block stops, files only pile up. Every index still opens and folds right.
7. **Docs.**
   - SPEC: a subsection *Upkeep* under §2a, or beside §4b. It says what the template draws, that `use: upkeep` hands index tidying to its controller, that the delete interlock stays in the code, and the fail-safe rule. It names only what this branch builds, and says the other loops are still to come.
   - SPEC §6's `builtin` row lists `ergostat.upkeep.*`.
   - The agent guide mentions `use: upkeep` wherever it lists the built-in templates.
   - The GAPS entry says this part is done and names the two sub-gaps still to come.

## Files to touch

- `ergostat/library/templates/upkeep/template.yaml` (new)
- `ergostat/library/run/upkeep.py` (new)
- `ergostat/library/run/__main__.py`
- `ergostat/library/run/__init__.py` (its docstring list)
- `ergostat/upkeep_measures.py` (new; or `ergostat/spec/` beside `itemindex.py`; one small module)
- `ergostat/spec/ir.py`
- `ergostat/spec/compile.py`
- `ergostat/numbers/measures.py`
- `ergostat/spec/itemindex.py`
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_upkeep_template.py` (new)

## Risks

- **lesson-1.** `_tidy` reads a file's age, decides, then takes the lock and deletes. A process can open, write and close the file between the age check and the take. *The fix:* check the age again inside the exclusive lock.
- **lesson-3.** A missing or unlistable `<state>/items` read as 0 files would show the goal met. *The fix:* no reading. A lock file that cannot be opened counts as held, never as free.
- **lesson-4.** `--keep` and `index-files` need a hard ceiling (64) and floor (1), at load and at run.
- **lesson-8.** Three claims need tests that would fail if they were false:
  - "no controller reads what it manages";
  - "fails safe";
  - "the delete interlock stays in the code".
- **lesson-9.** Each test below has to be watched failing against broken code.
- **lesson-11.** The tidy program deletes files. It must delete only names it recognises, under the resolved items folder, never a symlink's target and never an all-but-keep list of arbitrary files.
- **lesson-7.** Merge origin/main and run the suites again.

## Acceptance tests

- `tests/test_upkeep_template.py::test_upkeep_expands_to_the_index_files_loop`: `use: upkeep` gives exactly the stocks, flows, goals and block named above, in system `upkeep`, and the goal holds `<= 6` by default.
- `tests/test_upkeep_template.py::test_the_index_files_measure_counts_live_and_retired_files`: 3 live and 1 retired file give 3 and 1. A record with no state directory gives `None`, not 0 (lesson-3).
- `tests/test_upkeep_template.py::test_tidy_keeps_n_and_removes_retired_files`: with 9 old files and one retired file, `upkeep tidy --keep 6` leaves 6 and removes the retired one.
- `tests/test_upkeep_template.py::test_tidy_never_opens_an_index`: run in-process with `itemindex.Index.__init__`, `index_for` and `common.project` patched to raise. It succeeds and no new `.db`, `-wal` or `-shm` file appears. Fails if the program goes through the project (lesson-8).
- `tests/test_upkeep_template.py::test_tidy_checks_age_again_inside_the_lock`: `_take` is monkeypatched to touch the file just before returning the lock. The file is not deleted. Fails on main's order (lesson-1).
- `tests/test_upkeep_template.py::test_tidy_deletes_only_index_names_under_items`: a `notes.db`, a symlink `aaaaaaaaaaaaaaaa.db` pointing outside, and a file in a subfolder all survive (lesson-11).
- `tests/test_upkeep_template.py::test_keep_out_of_range_is_refused_at_load_and_at_run`: `index-files: 0` and `index-files: 500` are load errors, and `--keep 65` exits 2 (lesson-4).
- `tests/test_upkeep_template.py::test_with_upkeep_the_engine_does_not_tidy_and_without_it_does`: in a model with `use: upkeep`, making an eighth fold leaves 8 files; in one without, the count is cut as on main. Fails if the stand-down is missing, or if it applies to every model (invariant 12).
- `tests/test_upkeep_template.py::test_tidying_stopped_piles_files_up_and_nothing_breaks`: with `use: upkeep` and the block never run, 10 changes of kinds give 10 files. Each `index_for` still folds the record to the same items as a fresh fold (lesson-8, fail-safe).
- Existing: `tests/test_index_files.py` (all), `tests/test_templates.py::test_every_built_in_template_checks_with_its_example`.
- The report says which code each new test was run against when broken, and that it failed (lesson-9).

## Size budget

300 net lines outside `tests/` and `docs/` (the template YAML counts).

## Notes from the plan review (answer each)

- test_with_upkeep_the_engine_does_not_tidy_and_without_it_does: _tidy skips files younger than TIDY_AGE, so with fresh files main cuts nothing and the test cannot fail on a missing stand-down. Backdate the earlier files with os.utime past TIDY_AGE; the same applies to test_tidying_stopped_piles_files_up_and_nothing_breaks.
- Define 'retired' (how a file is known to be retired) in SPEC and use one function for it in both the measures and the tidy program.
- State how index_for learns the model has use: upkeep (reload or a passed flag) and test the path the engine actually uses.
- With the engine stood down there is no limit on file count: either keep an engine backstop at the 64 ceiling under use: upkeep, or narrow the SPEC 'fails safe' claim to say nothing limits the count (lesson-4/lesson-8).
- Name which number on the tidy output line feeds out: flow.index-files-tidied (removed) and its format.
- If <state>/items is missing or can't be listed, upkeep tidy must exit non-zero with a message, never report a clean result (lesson-3).
- Put the filename allowlist and the resolve-under-items check inside _tidy itself, so the engine's own tidy is protected too, not only the program (lesson-11).
- The age re-check after the lock should use lstat, the same TIDY_AGE, and include the -wal file's mtime, since a write may touch only the WAL.

## Where it stopped

Built: every point of the definition, with the acceptance tests passing. Net lines outside tests and docs: 230
(budget 300). Nothing is left inside this gap. Choices made without anyone to ask (each the more reversible one):

- **One part beyond the list.** The goal `no-retired-index-files` needs a flow its controller moves; without one
  `test_with_every_default_each_runs_on_stand_ins` (existing) fails with `missing-feedback`. So the template also has
  the outflow `retired-index-files-removed` (`changes: falls`), `index-tidier` reads both stocks
  (`in: [+stock.index-files, +stock.retired-index-files]`), and its `out:` is
  `[flow.index-files-tidied, flow.retired-index-files-removed]`. `goal:`, `run:`, `every:` and `type:` are as written.
- **The load-time range** needed a floor and ceiling for template parameters, which the library did not have:
  `least:` and `most:` on a number parameter (`library/templates.py`, `library/expand.py`; 5 lines, files not on the
  list). The error reads `use upkeep: with.index-files: from 1 to 64 (not 0)`.
- **"Built-in" only.** The stand-down applies to a `uses:` entry of ergostat's own `upkeep` template
  (`template: upkeep` and not an owner's template of that name). An owner's look-alike keeps the engine's tidy.
- **`itemindex.files(d)`** is the one listing of index files (name allowlist, regular file, resolves directly
  under the resolved folder), used by `_tidy`, the measures and the tidy program. `reindex` still globs `*.db`
  (not in this gap).

Answers to the plan review:

- Both pile-up tests backdate every file past `TIDY_AGE` with `os.utime` after each fold, and close the indexes
  (`_cold`) so no shared lock keeps a file.
- *Retired*: the mark `<hash>[.n].retired` beside the file; `itemindex.retired(p)`, used through `itemindex.files`
  by the measures and the tidy (SPEC §2a, *Upkeep*).
- `index_for` reads it from the spec it is given (`itemindex.upkept(spec)`, from `spec.uses`), so a reload that
  adds or drops `use: upkeep` takes effect on the next new file. The tests pass `mdl.load(root).spec`, the path
  the engine uses.
- No backstop: point 6 says `index_for` no longer calls `_tidy`. SPEC's fail-safe paragraph is narrowed instead:
  nothing else limits the count while the tidier is stopped (one file per change of kinds).
- The output line is `{"value": REMOVED, "removed": R, "left": L, "held": H, "young": Y}`. The engine reads
  `value` (the files removed) as the block's output.
- Missing or unlistable `<state>/items`: `upkeep tidy` prints a message and exits 1 (in
  `test_tidy_keeps_n_and_removes_retired_files`).
- The allowlist and the resolve check are in `itemindex.files`, which `_tidy` uses, so the engine's tidy is
  covered too (the last assertion of `test_tidy_deletes_only_index_names_under_items`).
- The re-check uses `_touched`, now on `lstat`, over the file, `-wal` and `-shm`, with the same `TIDY_AGE`.

Each new test, watched failing against broken code (lesson-9), then restored:

- stand-down removed (`and not upkept(spec)` dropped): `..._does_not_tidy_..._does[True]` and
  `test_tidying_stopped_piles_files_up_and_nothing_breaks` fail;
- stand-down for every model (`and False`): `[False]` fails;
- the re-check under the lock removed: `test_tidy_checks_age_again_inside_the_lock` fails. `_touched` reading
  only the `.db`: the same test fails on its WAL half. It first passed, because the file it touched was not the
  one due to go. Fixed;
- `files` taking any `*.db`: `test_tidy_deletes_only_index_names_under_items` and the measure test fail. Name
  check without the regular-file test: the first passed, because the symlink was young. The link itself is now
  backdated, and it fails;
- the tidy calling `common.project()`: `test_tidy_never_opens_an_index` fails;
- the `--keep` bound removed, or `least`/`most` ignored at load: `test_keep_out_of_range_...[0]` and `[500]` fail;
- the measure giving 0 for an unlistable folder: the measure test fails; retired files never removed:
  `test_tidy_keeps_n_and_removes_retired_files` fails;
- a lock that cannot be taken treated as free: `test_a_lock_file_that_cannot_be_opened_counts_as_held` (added for
  SPEC's claim) fails;
- `test_upkeep_expands_to_the_index_files_loop` fails on main (no such template).

Not done here: this clone has no `origin` remote. The branch already contains local `main` (05c6dc9), so the
lesson-7 merge had nothing to take; the factory's merge of the real origin/main is still to run. The full unit
and browser suites were not run here (the factory runs them under the watchdog). Run: `tests/test_upkeep_template.py`,
`tests/test_index_files.py`, `tests/test_templates.py` (55 passed), and ruff (clean).

### Round 2 (answering review/upkeep-index-files-1)

- **The tidier's output was refused (blocking).** The round-1 answer above ("the engine reads `value` ... as the
  block's output") was false: with two outputs and no `out`, the engine refused the line. `upkeep tidy` now prints
  one line per flow, `{"out": "flow.index-files-tidied", "moved": LIVE, "left": L, "held": H, "young": Y}` and
  `{"out": "flow.retired-index-files-removed", "moved": RETIRED}`. `_tidy` counts the two apart (`removed`, live;
  `retired`, retired). New test `test_the_tidier_block_moves_its_two_flows_through_the_engine` runs the block
  through `Engine.run_block` and finds each valve opened by its own count and no `agent.refused`. Watched failing
  on round 1's line (`agent.refused`) and on retired files counted into the live flow (amounts 3 and 1, not 2 and
  1); `test_tidy_keeps_n_and_removes_retired_files` now asserts both lines exactly and fails on both breaks too.
  SPEC's sentence on the output is rewritten to match.
- **SPEC's age claim was wider than the code.** SPEC (*Upkeep*, the interlock), the template's `reading:` and
  `_tidy`'s docstring now say a retired file goes once its lock is taken, whatever its age, and only live files
  need the `TIDY_AGE` test, before the lock and again under it.

Net lines outside tests and docs: 233. Run: `tests/test_upkeep_template.py`, `tests/test_index_files.py`,
`tests/test_templates.py` (56 passed), ruff clean. The origin/main merge and the full suites are still the
factory's to run (no `origin` here).

### The unit suite after round 2

The factory's unit run stopped at 29% with no failing test in its tail (a stall or a kill, not an assertion). I
could not run the whole suite here, so I could not name the test. The likeliest cause is in this branch's tests, and
it is fixed: `test_tidy_never_opens_an_index` patched `sqlite3.connect` for the whole worker process, and `_cold()`
closed every open index in the worker. Under xdist, threads left running by other tests in the same worker (engines,
page servers) could fail or stall while either was in effect. Now the test patches only the three things the
definition names (`Index.__init__`, `index_for`, `common.project`), and it still checks that no new
`.db`/`-wal`/`-shm` appears. `_cold(d)` closes only this test's own indexes, under `_OPEN_LOCK`. No change to the
code under test. If the unit suite still stalls, that is not explained here, and the next step is to find the test
that hangs.

### The unit suite after the fix to the tests

The factory's next unit run (`-n 8 --dist worksteal`) showed one `F` at about 40%, and its tail stopped at 50%
without naming the test. Here, every unit test file was run serially, in batches, one file list at a time
(`-p no:randomly`, about 2,000 tests over 128 files, the page tests skipped for want of a browser): all passed,
none failed. That includes this branch's tests and every file that reaches `itemindex`, the measures, the
templates, the library's programs, `compile` and the docs. The whole suite, any `-n` run and `--collect-only` were
refused in this session, so I could not reproduce the load or map the 40% position to a file. The failure is
unexplained, and no code changed in this round: a change made without knowing the failing test would be a guess
(lesson-10, lesson-13). Next step: run the unit suite again with `-rf` (or read its full log) to name the test,
then run it alone on this branch and on main (`alone`, `onmain.py`) to see whether this branch causes it.

### Round 3 (after the factory merged main, 2b101c6)

No code changed. Main's merge touched `spec/compile.py` and `spec/ir.py` (`messages: paused:`, `takes: order:`) far
from this branch's lines (the `bad-measure` message, `UPKEEP`), and the two fit. Run after the merge, all passing:
`tests/test_upkeep_template.py`, `tests/test_index_files.py`, `tests/test_templates.py` (56 passed); the files
that check the docs or were changed by the merge, `test_backlog`, `test_factory`, `test_factory_knowledge`,
`test_spec_schema`, `test_parity` (110 passed, 2 skipped); and every file that reaches `itemindex`, in one process
so they share its module state as tests in one xdist worker do (`test_upkeep_template`, `test_index_files`,
`test_item_index`, `test_counts`, `test_reload_safety`, `test_relations`, `test_resilience`: 170 passed). Ruff clean.
`pytest-randomly` is not installed, so the order is fixed and a shuffled order is not the cause. The one `F` of the
earlier `-n 8` run is still not named: this clone has no log of that run, and running the suite under `-n` is the
factory's job. If it shows again, `-rf` names it. Then run that test alone on this branch and on main to decide
whether it belongs to this gap (lesson-10, lesson-13).

### Round 4 (answering review/upkeep-index-files-2)

- **Size, 374 against 300 (blocking): the reason.** The 374 is not this gap's code. Round 3's "Merge main
  (2b101c6)" brought in `Merge branch 'backlog'` (2b101c6, with 67c673e, 600535d, ff49649, d61e27e), and `main`
  (now 7093853) does not contain it. So `git diff main HEAD` counts the backlog feature too. Counted by
  `git diff --numstat` (added minus removed, outside `tests/`, `docs/`, `dev/`):
  - this gap's own lines: 233 (`library/templates/upkeep/template.yaml` 98, `spec/itemindex.py` 49,
    `library/run/upkeep.py` 43, `upkeep_measures.py` 24, `spec/ir.py` 7, `numbers/measures.py` 6,
    `library/expand.py` 2, `library/templates.py` 2, `library/run/__init__.py` 2, `library/run/__main__.py` 0,
    `spec/compile.py` 0). That is within the 300 budget;
  - the backlog merge's lines in `ergostat/`: 141 (`numbers/etamodel.py` 45, `leases/ready.py` 23,
    `cli/spec_cmds.py` 21, `numbers/eta.py` 16, `web/static/pages.js` 12, `leases/compile.py` 8, `precedence.py` 4,
    `web/static/relations.js` 4, `web/static/style.css` 4, `spec/ir.py` 3, `leases/dispatch.py` 1), plus 5 in
    `ergostat.yaml`. 233 + 141 = 374.
- **The branch's base still holds that backlog merge (the same problem as review/gap-size-1).** Merging this
  branch as it stands would land the backlog feature on main. It is not fixed in this round. The clean fix is to
  rebuild the branch as `main` plus this gap's own commits (cherry-pick 8919bac..4c7f0bd and eeda24e onto
  7093853; they were made on 05c6dc9, before the backlog merge). Rewriting the branch was refused in this session.
  I did not make a commit that reverts the backlog changes either. The backlog commits would stay ancestors of the
  branch, so if main later takes `backlog`, merging this branch would delete it from main. That is harder to
  undo than leaving the base for the factory to rebuild. The branch head before this round is d69299a.
- **`reindex` still globs `*.db` (non-blocking).** It stays as it is: `reindex` is outside this gap's definition
  (lesson-13). The follow-up is to send its listing through `itemindex.files()` as well (lesson-11).

No code changed in this round, so no test was run again.

### Round 5 (the unit suite, `-n 8`, two `F`s at about 36% and 86%)

The tail names neither test. The whole suite, and a quarter of it under `-n 4`, were refused in this session, so I
could not name them either. These ran and passed: `tests/test_upkeep_template.py` (13), `tests/test_index_files.py`
(8), `tests/test_templates.py` (35), and the files that reach `itemindex` together under `-n 4` (205). Ruff is clean.
One hazard of this branch's own under xdist is fixed: `test_tidy_never_opens_an_index` patched `Index.__init__`,
`index_for` and `common.project` for the whole worker process, so another thread of the same worker that opened an
index meanwhile would have raised. The patches now raise only in the test's own thread, where the tidy runs. Any
other thread gets the real function. The test was watched failing again with the tidy calling `common.project()`,
then restored. No code under test changed. Whether this explains the two `F`s is not known. If they show again,
`-rf` names them; then run each alone on this branch and on main (lesson-10, lesson-13). The size and the
backlog-merge base stand as round 4 left them: main still lacks 2b101c6.
