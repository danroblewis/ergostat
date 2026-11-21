# proposals-superseded-by-any-edit: a block's change, and one under test or passed, carried to a new version when its subject is unchanged; a structural change whose lines moved carried with the edit its finder finds again; every carry and every judging done under the proposals' lock against the model as its files are now
depends-on: []

## What is on main already (do not rebuild)

- `proposals._supersede` (`ergostat/numbers/proposals.py:168`) carries a change to the new version, or supersedes it saying which. It carries ergostat's own changes that are `checked`, not a block's and whose subject is unchanged (`revised` with `rebased`; a value's or an equation's edit is made again by `_edit_now`). It also carries descriptions, units and redesigns from anyone (`_carried`). `rebase` moves the lines of the waiting edits after an Accept. Loops' processes and gains are revised in place (`control/proposals.py::_made`).
- These tests pass on main and must still pass: `tests/test_churn.py` (all four churn tests), and `tests/test_modelling_core.py` / `tests/test_modelling_core2.py` (carrying words and redesigns, and the lock held in supersede, the judge and Accept).

## What is left, as found in the code

1. `_supersede` line 185 (`elif sub and x["state"] == "checked" and not candidate(x)`) supersedes on any version change three kinds of change: a change a block made (`improve.submit`; it records no `subject`), any change in `testing` or `passed`, and a structural change whose lines moved (`_edit_now` returns None for `structure`).
2. The structural pass (`review.refresh`) then makes that change again on the same id (`structural.Ctx.add` hashes the masked diff, so line numbers drop out). `save` then records a new `made` on an item whose fold still holds the old `why`, `version_now`, `verdict` and `looked` (lesson-5).
3. `review.refresh` and `proposals.make` read `stored`, run `admit` and `save` without the lock. `dismiss` also writes without it. A dismissal that lands between the read and `save` is reopened to `checked` (lesson-1).
4. `judge.run` takes `spec = p.model.spec` before the lock and judges `pending(p, spec)`. `_accept` compares versions with `p.model.spec`. If the files were edited by hand and the model is not reloaded yet, the judge can test, pass or write a change against a version that is no longer the files' version.

## Definition of done

1. **The model as its files are now.** Add `proposals.files_now(p) -> Spec | None`: the model compiled from its files as they are (`trial.compiled(p.model.path, {})`), or None when it has errors. Every read-decide-write below uses its version, taken under `proposals.locked(p)`.
   - If the files do not compile, the pass defers. Nothing is carried, superseded, tested, passed or written. This fails closed (lesson-3).
   - If the caller's `spec` has a different version from the files now, `_supersede` defers too and returns `[]`. The caller's model is stale and the next pass decides.
2. **A block's value, equation or structural change has a subject.**
   - `improve.validate` records `subject = proposals.subject(spec, refs)`. `refs` = `touched_refs(spec, after, parts, kind)`, plus the stocks that each added flow joins, plus the parts it removes, keeping only the parts in `spec`.
   - With no such part, no subject is recorded.
3. **`_supersede` carries any waiting change whose subject is unchanged, whoever made it and whatever its state** (`checked`, `testing`, `passed`; processes and tunings are left out as now). It is carried when its edit applies to the files now: as it stands, moved by `rebase`, or made again (`_edit_now` for a value, or an equation that has `equation`/`parameters`). The carry records `.revised` with `version`, `structure`, `edit` and `rebased: {from, to}`. Otherwise it is superseded with a `why` naming the cause:
   - `what it is about changed: <refs> removed` / `… edited since it was made`;
   - `its edit no longer applies (<error>)`. This covers a block's equation or structural edit whose lines a hand edit moved; it is the block's to make again;
   - `it was recorded without what it is about, so it cannot be held to the model as it is` when it has no `subject` (changes recorded before this branch, or a subject with no part). Fails closed (lesson-3);
   - `it is no longer a <kind> change on the model as it is` when `improve.kind_of(now, after, kind) != kind`;
   - `on the model as it is, it would change who decides (<what>)` when `improve.governs(now, after)` is not empty. A block never carries a change into the owner's decisions.
4. **A carried change judged on the old version is judged again.**
   - A carried `passed` change goes back to `testing`. A carried `testing` change stays `testing`.
   - Both have `verdict`, `undecided`, `more`, `not_exercised` and `looked` cleared to null in the same event, so the judge judges again on the version now before anything can write it.
   - `rewires` is recomputed (`structural.rewired(now, after)`) so `judge.owners` reads the change as it now is (lesson-5).
5. **A structural change whose lines moved is carried with the edit its finder finds again, never made again.**
   - `review.refresh` runs `structural.find` and computes the fits outside the lock, on `v = version(spec)`.
   - Under `proposals.locked(p)` it compares `v` with the version of `files_now(p)`. If they differ, it writes nothing (no carry, no supersede, no admit, no `STATE` file) and returns `not_made`; the next pass redoes it.
   - If they are equal, it calls `_supersede(p, spec, found=found)`. A structural change of ergostat's own whose subject is unchanged and whose edit does not apply is carried with the edit of the finding with the same id. If there is no such finding, it is superseded with `no longer found by the finder that made it`. Without `found` (the judge, the estimator, Accept), such a change is left as it is for the structural pass.
   - Then `stored`, letting go of what is not found, `admit` and `save` all run in the same lock.
6. **The estimator writes under the lock.** In `proposals.make`, the part from reading `stored` to `save` runs under `locked(p)`, behind the same version check as `refresh`. `dismiss` takes the lock.
7. **The judge never judges or advances a change whose version is not current.**
   - In `judge.run`, under the lock, if `files_now(p)` is None or its version differs from `version(spec)`, the pass judges nothing and writes nothing (`out["deferred"]` says why).
   - Otherwise it judges only changes with `x["version"] ==` that version.
   - `_accept` compares the change's version with `files_now(p)` and refuses when they differ ("the model has changed since it was proposed").
8. **A change made again on a superseded id starts clean.** In `save`, a `made` on an id whose fold exists (superseded) sets to null every field of the old fold that the new body lacks (LOCAL left aside). A remade change carries no old `why`, `verdict`, `looked`, `version_now` or `revisions`.
9. **Docs match the code.**
   - SPEC §12e, the "One change, whatever its numbers" paragraph: the sentence "A block's proposal is not carried yet (GAPS)" is replaced. It now says a block's changes are carried, under-test and passed changes go back to testing, structural changes are carried with the edit found again, and carries are deferred while the files differ from the loaded model.
   - SPEC bench §1 line 3707: "superseded and never written" becomes "never written on a verdict reached on another version: carried back to testing, or superseded".
   - GAPS entry: moved to done.
   - `docs/AGENT-GUIDE.md` line 541–542: one sentence on the reasons a change is superseded.

## Files to touch

- `ergostat/numbers/proposals.py` (`files_now`, `_supersede`, `save`, `make`, `dismiss`, `_accept`)
- `ergostat/numbers/review.py` (`refresh`)
- `ergostat/numbers/judge.py` (`run`)
- `ergostat/numbers/improve.py` (`validate`: `subject`)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`
- `tests/test_churn_carry.py` (new; reuses `test_improve`'s `long_queue`, `raw`, `made_ago`, `judge_block`, `item` and `test_review`'s `project`, `structural`, `reload`)
- `tests/test_improve.py`, `tests/test_bench.py` (two existing assertions that state the old behaviour, named below)

## Risks

- **lesson-1:** the finder or the estimator runs outside the lock, then writes under it. If a hand edit lands in between, a carried change could get the current version with an edit found on older files. A dismissal between `stored` and `save` could be reopened. The judge could judge on a `spec` it read before the lock. Handled by the version stamp compared under the lock (items 1, 5, 6, 7), by the whole read-to-save span under the lock, and by `dismiss` taking it.
- **lesson-2:** only version hashes compared for equality. No timestamps are compared to mean "newer".
- **lesson-3:** files that do not compile, or a change with no `subject`, must not count as "unchanged". Both defer or supersede, never carry.
- **lesson-5:** the same id is reused by a carry (an old `verdict`/`looked`/`rewires`) and by a remake after a supersede (an old `why`/`version_now`). Item 4 and item 8 clear them.
- **lesson-7:** branches touching `proposals.py` and `judge.py` are in flight (`proposals-drawn-dashed-in-both`, `modelling-improves-the-model`). Merge origin/main and run the suites again.
- **lesson-8:** the SPEC sentences in item 9 each name the test below that fails if they are false. No sentence says "never superseded".
- **lesson-9:** every new test below is written to fail on main or with its rule removed. Each is broken by hand once and the report says so.
- **lesson-12/13:** a suite failure outside these files is reported, not fixed here.

## Acceptance tests

In `tests/test_churn_carry.py`:

- `test_a_blocks_value_change_is_carried_when_its_subject_is_unchanged`
  - Setup: `im.submit` a value of `k`. Then a hand edit adds a parameter *above* `k` (version changes, `k` unchanged, its line moves). Reload.
  - Asserts: `pr.supersede` returns `[]`; the state is `checked`; the version is the version now; `made_by` is kept; the history is `made, checked, revised`; `tr.spec_after(p, tr.edits_of(x))` sets `k` to 3.
  - Fails on main (superseded).
- `test_a_blocks_change_is_superseded_when_its_subject_is_edited`: a hand edit to `k`'s value supersedes it, with `why` naming `parameter.k` and "edited".
- `test_a_change_recorded_without_a_subject_is_superseded` (lesson-3): a block change recorded through `pr.event` with no `subject` is superseded on an unrelated edit, with the "recorded without what it is about" reason. Fails if a missing subject counts as unchanged.
- `test_a_carried_change_that_would_change_who_decides_is_superseded` (the governs rule)
  - Monkeypatch `im.governs` to return `["the judge's policy"]` and record the arguments.
  - Asserts: the change is superseded with "who decides"; `governs` was called with the files-now spec and the spec after the edit.
  - Fails (carried) when the rule is removed.
- `test_a_carried_change_that_is_no_longer_its_kind_is_superseded` (the kind_of rule)
  - Monkeypatch `im.kind_of` to return `"control"`.
  - Asserts: superseded with "no longer a parameter change".
  - Fails when the rule is removed.
- `test_a_passed_change_carried_goes_back_to_testing_and_is_judged_again` (lesson-5)
  - Setup: a `made_ago` block value change passed by `jd.run`, with `accept: owner`. Then an unrelated edit.
  - Asserts after `supersede`: the state is `testing` and `verdict`, `looked` and `undecided` are None in `pr.changes`.
  - Asserts after the next `jd.run`: a new verdict event, recorded after the carry, on a change whose `version` is the version now.
  - Fails if the old verdict survives.
- `test_the_judge_never_moves_a_change_made_on_another_version`
  - Setup: `judge_block(accept="{parameter: auto}")`. One change `passed` and one `checked`. A hand edit appended at the *end* of the file, so the passed change's hunk still applies (the test asserts `tr.spec_after` succeeds on it). `p.model` is not reloaded, and `pr.supersede` is monkeypatched to `lambda *a, **k: []` (the edit landing between supersede and the lock).
  - Asserts after `jd.run`: the passed change is still `passed`, the checked one still `checked`, `out["accepted"] == 0`, `out["deferred"]` is set, and the file has the hand edit and not the change's value.
  - Fails on main, which writes it.
- `test_accept_refuses_when_the_files_moved_on_from_the_loaded_model`: the same stale setup. `pr.accept` by the owner raises "the model has changed", and the file is unchanged.
- `test_a_structural_change_whose_lines_moved_is_carried_with_the_edit_found_again`
  - Setup: `structural(p)` yields change `s`. A hand edit inserts lines above its hunk, with its subject unchanged. Reload, then `structural(p)` again.
  - Asserts: the same id; the history is `made, checked, revised` with `rebased` (no `superseded`, no second `made`); its edit applies to the files now.
  - Fails on main.
- `test_an_edit_between_the_finder_and_the_lock_defers_the_carry` (lesson-1)
  - Setup: monkeypatch `stc.find` to run the real finder and then write the line-moving hand edit without reloading.
  - Asserts after `rv.refresh(force=True)`: no event on `s` after the refresh began; the `STATE` file's `version` is not the stale `v`.
  - Then: reload and refresh, and `s` is carried with an edit that applies to the files now.
  - Fails if findings are carried without comparing versions.
- `test_a_dismissal_during_the_structural_pass_is_kept` (lesson-1)
  - Setup: monkeypatch `pr.admit` to start a thread that calls `pr.dismiss(s)` and waits up to 1 s for it.
  - Asserts after the refresh and joining the thread: `s` is `dismissed`.
  - Fails on main: `save` reopens it to `checked`.
- `test_a_dismissal_during_the_estimators_pass_is_kept`: the same through `pr.make` with the `test_churn.factory` model.
- `test_a_change_made_again_on_its_id_starts_clean` (lesson-5)
  - Setup: an id superseded with `why`, `version_now`, `verdict` and `looked` in its fold. `pr.save` then makes it again.
  - Asserts: none of those fields remain.
  - Fails on main.

Existing tests changed, each saying the new rule:

- `tests/test_improve.py::test_accepting_one_change_supersedes_the_others_made_against_the_old_version` is renamed `test_accepting_one_change_carries_or_supersedes_the_others_by_their_subject`.
  - A block's structural change on `flow.leaks` is carried, `checked`, at the new version.
  - A second block value change on `k` is superseded naming `parameter.k`.
- `tests/test_bench.py::test_a_change_made_against_values_since_rewritten_is_never_applied`: the state assertion becomes `in ("superseded", "failed", "testing")`, and with `testing` the verdict is None. The never-written assertions are unchanged.

All of `tests/test_churn.py`, `tests/test_modelling_core*.py`, `tests/test_review.py`, `tests/test_bench.py` and `tests/test_improve.py` pass, and so do the unit suite and the four browser files (rc 0), and ruff.

## Size budget

200 net lines of code outside `tests/` and `docs/`. The estimate is about 150: `_supersede` +60, `files_now` +10, `save` +8, `refresh` +15, `make`/`dismiss` +8, `judge.run` +12, `_accept` +3, `validate` +10.

## Notes from the plan review (answer each)

- lesson-3: add a test that a file that does not compile (hand edit with a syntax error, model not reloaded) makes _supersede, review.refresh, proposals.make and judge.run defer: no event and no STATE written. Break files_now's None check and show the test fails.
- The two dismissal tests count only if proposals.locked blocks between threads of the same process (flock on a newly opened fd, or a threading lock as well). With fcntl.lockf they pass without testing anything. Say which lock is used, and show the test failing on main because dismiss writes inside the gap.
- _accept: after it writes the files, _supersede must get the spec compiled from the files now (or the reloaded model), not the old p.model.spec. Otherwise the stale-spec rule in item 1 makes every carry after an Accept defer. Make the renamed test_improve test assert that the carry happens in the same Accept call.
- Item 6: add a test where proposals.make's estimator runs, then a hand edit lands before the lock. Assert nothing is admitted and no events are written. Today only refresh has this test.
- Item 4: add an assertion that a carried change that was testing stays testing, with verdict/looked cleared and rewires recomputed (for example, a structural change whose rewired set differs on the version now). The passed case alone does not cover the recompute of rewires.
- Item 3: say whether a carried 'checked' change also gets verdict/looked cleared (they should already be null). Make the event shape one rule for all states, so the fold has no leftover fields.

## Where it stopped

Built: every item of the definition of done, in 75 net lines of code (budget 200). No `origin` remote in this
clone; `main` is an ancestor of the branch, so there was nothing to merge (lesson-7: the coordinator merges with the
in-flight branches named in the risks).

Choices made alone (each the more reversible one):

- **The carry's event.** One rule for every state (`proposals._carry`): one event with `version`, `structure`, `edit`,
  `rebased`, `rewires` (recomputed) and `verdict`, `undecided`, `more`, `not_exercised`, `looked` all null, for a
  carried `checked` change too (already null there). The event is `.revised` for `checked` and `testing`. For `passed`
  it is `.testing` with the same fields, not `.revised` and then `.testing`. The fold takes the state from the event's
  type, so this is the only way the state and the clearing land in one event.
- **The judge writes only what is passed.** `_accept` with a `policy` (the judge's write) refuses a change no longer
  `passed`. The judge reads its list of changes to write outside the lock, and a carry in between moves a passed
  change back to testing (lesson-1).
- **Accept needs the loaded model to be the files' model.** `_accept` refuses unless the files compile to the loaded
  model's version and to the change's version. After writing, it reloads `p.model`, so `_supersede` gets the files'
  model and carries in the same call (`test_improve.py::test_accepting_one_change_carries_or_supersedes_the_others_by_their_subject`).
- **A deferred estimator pass returns `[]`**, not the changes pending on a model that is stale.
- **The lock.** `proposals.locked` is `fcntl.flock` on a file opened anew on each call. flock locks belong to the open
  file description, so two threads of one process block each other. This is why the dismissal tests test something.
  With `dismiss` unlocked (as on main) both fail: the dismissal lands in the pass and `save` reopens it.
- `review.refresh` reads `stored` outside the lock only to skip the fits of findings already made and not carried.
  Under the lock, a finding with no fit computed is not admitted, and the next pass makes it.

Each new test was seen to fail with its rule broken by hand: the governs and kind_of rules; the clearing; the
rewires recompute; the clean remake in `save`; the judge's deferral; `_accept`'s check against the files;
`current_now` (the finder's and the estimator's edit-in-the-gap tests); `_supersede`'s stale-caller check;
the missing-subject rule; `dismiss`'s lock; the structural carry's found edit; a block's changes left out of
the carry; and `files_now` failing open (it returns the loaded model when the files have errors).

Not run here: the whole unit suite under `-n 8`, the four browser files and `demo_check` (no example touched). The
brief leaves them to the factory. Run here, one invocation each: the seven named files (126 passed); 17 other files
that use proposals, the judge or review (334 passed); test_spec_compile, test_item_systems and test_blockdiagram (100
passed); ruff clean.

**After the factory's unit run failed.** Its tail stopped at 32% with no failing test, no traceback and no summary
line: the run was cut short from outside (the watchdog or a time limit), not failed by a test. Run again here as the
factory runs it (`pytest -q -n 8 --dist worksteal`, with `faulthandler_timeout=200` to dump any test that hangs):
1948 passed, 69 skipped, rc 0, in 6 min 24 s, with no hang dumped. I looked for a lock taken twice on one path
(`make`, `refresh`, `dismiss`, `accept`, the judge, the control proposals) and found none. No code was changed for
it. `scripts/suite_watch.py` could not be run in this session, so its peaks (threads, RSS) were not seen. If the
factory's run fails the same way again, those peaks are the next thing to read. One cost is new on this branch:
`files_now` compiles the model from its files on every supersede, judge pass and Accept.
