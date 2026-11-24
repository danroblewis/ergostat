# feature-flags-for-unfinished-work: Work can land switched off behind a flag, so it skips the checks it does not affect

A general flag mechanism: a change declares a flag, its code paths are off by default, and tests for the flagged path run only when it is turned on. Useful where the owner says it really saves regression work (new pages, panels, isolated features), not for engine paths. Turning a flag on is its own gap with the full checks.
Done: 1. Tests: flagged-off code is unreachable by default; turning it on requires the full suite. 2. The guide says when a flag is worth it.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Built, round 1. Net lines outside tests, docs and dev: 143 (ergostat/flags.py 118, ergostat/flags.json 1,
scripts/affected_tests.py +24); in dev: dev/bin/queue.py +7, dev/prompts/planner.md +2. Budget 600.

- **The mechanism (core, off unless declared, naming no gap or software).** `ergostat/flags.json` declares flags as
  `{"NAME": {"on": false, "about": "..."}}`; it ships `{}`, so nothing is gated and an empty install is unchanged.
  `ergostat.flags.on(NAME)` is true only for a flag declared `"on": true`, or one declared and named in
  `ERGOSTAT_FLAGS` for one process. An undeclared name raises `UnknownFlag`. A file that cannot be read or parsed
  reads every flag as off (the flagged path stays unreachable). Tests marked `@pytest.mark.flag("NAME")` skip while it
  is off (tests/conftest.py); a marker that names an undeclared flag, or no single name, stops the run
  (`pytest.UsageError`), never a silent skip. The `home` fixture keeps `ERGOSTAT_FLAGS` so a test body sees what
  collection saw.
- **Turning on runs the full checks.** `flags.turned_on(before, after)` names each flag on after and not before, and
  each off flag whose declaration is gone. A file unreadable after the change is a reason in itself; one unreadable
  before counts as none declared. `scripts/affected_tests.py` then runs the whole unit suite, not the affected
  files. `dev/bin/queue.py` `browser_wanted` runs the four browser files whatever `browser_paths` says. Where git
  cannot say, or (in the queue) ergostat does not import, both run in full.
- **The flagged tests still run somewhere before landing.** The build of the branch that declares a flag runs its
  affected tests with its new flags in `ERGOSTAT_FLAGS`. Without this, a flagged path would land with tests that had
  never run.
- **The guide.** docs/DEVELOPMENT.md, *Feature flags*, explains the rules and when a flag is worth it: isolated
  work entered through one guard, whose own tests are slow or many. Never on an engine path, never for a small
  finished change, never to land failing tests. dev/prompts/planner.md has one sentence pointing there, so a planner
  can choose a flag for a fitting gap.

Decided alone (each a small change back): declarations in a JSON file in the package, not in a model's YAML.
Flags gate ergostat's own code, and the queue and the build step read the file at two git revisions without
importing the branch's code. The env override is for test runs. Nothing stops an operator from setting it on an
instance, and the guide says not to. The flags are read in Python only; a page's scripts see a flag through the
server's answers. Not built: skipping the browser step for changes that are only under an off flag's own files. The
definition does not ask for it, and the guide does not claim it.

Seen to fail (lesson-9), each then restored: `on()` always true failed
test_a_flagged_off_path_is_unreachable_by_default; the marker never skipping failed
test_a_flagged_test_is_skipped_while_off_and_runs_when_on; affected_tests ignoring a turn-on failed
test_turning_a_flag_on_requires_the_full_suite (it ran `--collect-only`); browser_wanted ignoring it failed
test_turning_a_flag_on_runs_browser_in_the_queue.

Run here: tests/test_flags.py (5 passed); in tests/test_factory.py
test_an_empty_browser_paths_runs_browser_always, test_a_batch_without_browser_paths_skips_browser_and_says_so,
test_a_branch_changing_a_module_and_its_test_runs_only_those, test_an_unreadable_diff_runs_the_full_suite,
test_a_docs_only_branch_runs_collection_only, test_a_non_ascii_test_file_is_selected (6 passed). ruff clean on
ergostat, tests, scripts (and dev/bin/queue.py). main merged: already up to date. Not run here: the unit suite and
the four browser files (the factory and the queue run them; tests/conftest.py changed, so every test's collection
passes through the new hook).

Round 2. The review's one finding, which blocked: a flagged browser test would skip while its flag is off, and the
queue and browserday count any skipped page test as a failure. No build runs page tests with a branch's flags on
either. Answered with the review's second option, the more reversible one: the mechanism and the guide are narrowed
to unit tests, and the narrowing is enforced, not only written down. tests/conftest.py `_flagged_off` now stops the
run (`pytest.UsageError`, exit 4) when a `flag(...)` marker sits on a test that drives a browser: one that asks for a
`browser` or `page` fixture, or whose file mentions playwright; a file that cannot be read counts as one. So a
flagged page test never reaches the queue's or browserday's skip count as a skip. It turns the run red with a reason
that names the rule. Neither dev/bin/queue.py nor dev/bin/browserday.py changed. The guide (docs/DEVELOPMENT.md,
Feature flags) has a new rule, "Only unit tests can be flagged": a flagged page or panel lands with unit tests of its
server side, and its browser tests come with the change that turns the flag on. "When a flag is worth it" now says
unit tests. dev/prompts/planner.md and the ergostat/flags.py docstring say the same. The detection reads a file's
text and its fixture names. A test that drives a browser some other way (a subprocess running walk.py from a file
that never names playwright) is not seen. The guide states the rule as those two signs, not as "every browser test".
New test: tests/test_flags.py test_a_flagged_browser_test_stops_the_run. It checks the hook on stand-in items (page
fixture, browser fixture, a playwright file, an unreadable file; a unit test and an unflagged page file pass as
before), then runs a real pytest on a flagged `page` test: exit 4, the reason given, no SKIPPED line. Seen to fail
(lesson-9): with the guard disabled it fails ("DID NOT RAISE UsageError"); restored. Lines outside tests, docs and
dev this round: ergostat/flags.py docstring only (net 0), total still 143 of 600.

Run here (round 2): tests/test_flags.py (6 passed); ruff clean on ergostat, tests, scripts and dev/bin/queue.py;
`git merge main`: already up to date. Not run here: the unit suite and the four browser files. No test in the tree
carries a flag marker, so the new check runs for none of them.

Round 3. The review's one finding, which blocked: tests/test_flags.py pinned the shipped ergostat/flags.json to `{}`,
so the first change declaring a flag (the guide's first step) would fail its own build. Now the test asserts only that
the shipped file parses (`flags.parse` raises on anything but the allowed form), so a malformed flags.json still fails
the suite rather than reading every flag as off and skipping every flagged test silently. Seen both ways (lesson-9):
with `board` declared off in the shipped file the test passes (it failed before this change); with a malformed
declaration (`{"board": {"on": false}}`) it fails with the parse's ValueError; the file was restored to `{}`. No code
outside tests changed; total still 143 of 600. The "Its entry" line in the review's brief reports other gaps'
records on main as unreadable (agent-show-page and six more); none is this gap's, and they are not touched here.

Run here (round 3): tests/test_flags.py (6 passed); ruff clean on ergostat, tests, scripts; `git merge main`:
already up to date. Not run here: the unit suite and the four browser files.

## Entry

section: The factory (ergostat on ergostat)

- **Work can land switched off behind a flag** (done, on `feature-flags-for-unfinished-work`; docs/DEVELOPMENT.md,
  Feature flags): `ergostat/flags.json` declares a flag off and the code asks `flags.on(NAME)`. Tests marked
  `flag(NAME)` skip while it is off, and the declaring branch's build runs them with the flag on; only unit tests
  can be flagged (the marker on a browser test stops the run). A change that
  turns a flag on runs the whole unit suite in the build and the browser files in the queue. The guide says when a
  flag is worth it (isolated pages, panels and features, never engine paths).
