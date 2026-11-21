# from-upkeep-s-fault-injection: close the gap's paperwork: its GAPS entry moves to *Done recently*, citing commits on main and no file main lacks
depends-on: []

## Definition of done

Main already has everything this gap asked for, so **this branch changes no code** (nothing under `ergostat/`, `dev/`, `scripts/`, `schema/` or `examples/`):

- The outer watcher and `status` for a dead engine, the watchdog's cause and back-off, alarms that show, and the caps are on main from `resilience-core` (`docs/roadmap/overnight/resilience-core.md`, tests in `tests/test_resilience.py`, cited as 3e106ee).
- The CLI's fallback to the last good model is on main from `cli-fallback` (merged at 75e7687, with 366241d and 6affe4f classifying `block --reset` and `block --check-warm` as acting; tests in `tests/test_cli_fallback.py`).

What is still wrong is in the docs and in what the factory reads from them. When this branch is done, all of the following holds:

1. **The entry leaves the open sections.** In `docs/GAPS.md`, the bullet `**From upkeep's fault injection**` and its five sub-bullets are removed from `## Runtime, scale and latency`. One entry under `## Done recently` takes their place, inserted first, above *Warm processes for blocks*. Its title starts `**From upkeep's fault injection**` and its first parenthesis starts `(done`. As a result, `dev/bin/intake.py`'s `gaps_md` on the new GAPS.md returns no entry whose title starts "From upkeep's fault injection". The intake code is not changed for this.
2. **Its content is what is on main, and nothing wider.**
   - The entry names the five problems in the old entry's wording, shortened if needed.
   - It says the first four came from `resilience-core` (`docs/roadmap/overnight/resilience-core.md`) and the fifth from `cli-fallback` (`docs/roadmap/overnight/cli-fallback.md`).
   - It gives each problem the commit hash that brought it to main.
   - Before writing a hash, the implementor checks it with `git merge-base --is-ancestor <hash> HEAD`. If 3e106ee or 75e7687 fails that check, the implementor finds the commit that actually merged that work (`git log --merges --oneline main | grep -E 'resilience|cli-fallback'`), cites that one, and says so in "Where it stopped".
   - The text claims no measured figure, and nothing beyond the two definitions' "Definition of done" (lesson-8).
   - The wording "done on branch `cli-fallback`" is gone: that work is on main, not only on a branch.
3. **No citation of a file main lacks.**
   - `docs/proposals/upkeep.md` is not on main. The new entry does not cite it. It says instead that the faults were found by upkeep's fault injection (`docs/roadmap/overnight-2026-11-19.md`, 01:30) and that the upkeep proposal was not merged to main.
   - In `tests/test_resilience.py`, the module docstring's first line cites `docs/roadmap/overnight-2026-11-19.md` instead of `docs/proposals/upkeep.md`. Only that docstring changes in that file.
   - `docs/roadmap/overnight/resilience-core.md` and `cli-fallback.md` are **not** edited: they belong to finished branches and change only by those branches appending to them.
4. **Nothing else in GAPS.md changes.** That includes the other entries, the "Last reviewed" date and the *ergostat's upkeep as a modelled system* idea. The latter is a separate gap (`gap/ergostat-s-upkeep-as-a-modelled-system`, leased elsewhere) and stays where it is, untouched.
5. **Its own definition file.** `docs/roadmap/overnight/from-upkeep-s-fault-injection.md` holds this definition, as the branch's first commit.
6. **The suites.** The unit suite and the four browser files pass with rc 0, with no page test skipped. Ruff is clean. No example is touched, so `demo_check` is not required. origin/main is merged in and the suites run again before the branch is called built.

## Files to touch

- `docs/roadmap/overnight/from-upkeep-s-fault-injection.md` (new: this definition, first commit)
- `docs/GAPS.md` (the entry moved and rewritten; nothing else)
- `tests/test_resilience.py` (module docstring, first line only)
- `tests/test_gaps_doc.py` (new: the acceptance tests below)

## Risks

- **lesson-8 (a claim wider than the code).** The entry could cite a hash that is not on main, say "done" for something only on a branch, or keep a citation to a missing file. A test fails for each of these: `test_upkeep_entry_cites_only_paths_that_exist` and `test_upkeep_entry_cites_only_commits_on_main` below.
- **lesson-9 (a test that can't fail).** A test that only greps for the string "Done recently" passes whatever happens to the entry. Each test below must be shown to fail on a deliberate break, and the report says so:
  - put the old entry back in its section → `test_upkeep_entry_is_not_found_open_by_intake` fails;
  - add `docs/proposals/upkeep.md` to the entry → `test_upkeep_entry_cites_only_paths_that_exist` fails;
  - change a hash to `deadbee` → `test_upkeep_entry_cites_only_commits_on_main` fails.

  Each test must also fail if the entry is missing altogether: no match is an assertion failure, never a vacuous pass (lesson-3 in miniature).
- **lesson-7 (two merges).** Another branch may edit GAPS.md near this entry, for example the leased `ergostat-s-upkeep-as-a-modelled-system`. The implementor merges origin/main, resolves keeping both, and runs the suites again.
- **lesson-13 (stay inside the gap).** A whole-file "every cited path exists" test could fail on other entries' citations. It is scoped to this one entry, and any other dead citation found is reported, not fixed. A suite failure in code this branch does not touch is reported by name, not fixed here.

## Acceptance tests

All in `tests/test_gaps_doc.py`. Each reads the repository's own `docs/GAPS.md`, which is found from `Path(__file__).parents[1]`. A helper `upkeep_entry(text)` returns the `## Done recently` bullet whose title starts "From upkeep's fault injection", together with its indented lines, and fails the test if there is none.

- `test_upkeep_entry_is_not_found_open_by_intake`
  - Runs `dev/bin/intake.py`'s `gaps_md` on the file, in a subprocess with `sys.path[:0] = [dev/bin]`, as `tests/test_factory.py` does at line 1061.
  - Asserts that no returned title starts "From upkeep's fault injection".
  - Asserts that `upkeep_entry` finds the entry under `## Done recently` and that its first parenthesis starts `(done`.
  - Guards item 1.
- `test_upkeep_entry_cites_only_paths_that_exist`
  - Every backticked token in the entry that contains `/` and ends in `.md`, `.py` or `.jsonl` exists under the repository root.
  - Asserts the entry names `docs/roadmap/overnight/resilience-core.md`, `docs/roadmap/overnight/cli-fallback.md` and `docs/roadmap/overnight-2026-11-19.md`.
  - Asserts `docs/proposals/upkeep.md` appears nowhere in GAPS.md.
  - Guards item 3 and lesson-8.
- `test_upkeep_entry_cites_only_commits_on_main`
  - Every 7-to-12 character hex word in the entry is a commit that `git merge-base --is-ancestor <hash> HEAD` accepts (rc 0).
  - At least two such hashes are present.
  - Guards item 2 and lesson-8.
- `test_resilience_docstring_cites_no_missing_file`
  - The module docstring of `tests/test_resilience.py` (read with `ast.get_docstring`) cites no `docs/` path that does not exist.
  - Guards item 3.

Plus the existing `tests/test_resilience.py` and `tests/test_cli_fallback.py` passing unchanged (apart from the docstring), the unit suite, the four browser files with rc 0 and no page test skipped, and ruff.

## Size budget

0 net lines of code outside `tests/` and `docs/`. Any line there is an overrun and fails the definition.

## Notes from the plan review (answer each)

- test_upkeep_entry_cites_only_paths_that_exist asserts docs/proposals/upkeep.md appears nowhere in GAPS.md. If another entry (e.g. 'ergostat's upkeep as a modelled system', which item 4 forbids touching) cites it, the test cannot pass. Scope that assertion to the upkeep entry, and report any other dead citation instead (lesson-13).
- test_upkeep_entry_cites_only_commits_on_main checks ancestry against HEAD, which includes this branch's own commits, so a branch-only hash passes. Check against origin/main (or main) when that ref exists and fall back to HEAD only when it doesn't. With no git history, fail rather than skip (lesson-3). Add a break that cites this branch's own first commit and show the test fails.
- The 7-12 hex-word regex also matches all-digit words (e.g. 1000000). Require at least one a-f letter, or match only hashes in backticks or after 'commit', so a stray number can't be read as an uncheckable hash.
- test_resilience_docstring_cites_no_missing_file passes vacuously if the docstring cites no docs/ path at all. Also assert that it names docs/roadmap/overnight-2026-11-19.md, and add a deliberate break (restore docs/proposals/upkeep.md in the docstring) to the lesson-9 list.
- In test_upkeep_entry_is_not_found_open_by_intake, assert that the subprocess returns rc 0 and that gaps_md returns a non-empty list (e.g. it still finds a known open entry). Otherwise an import failure or an empty parse reads as 'not found open'.
- Have the entry give each of the five problems its own hash (item 2), and check that the 'Where it stopped' note exists only when a substitute merge commit was cited.
