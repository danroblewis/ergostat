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
