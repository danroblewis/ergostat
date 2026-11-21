# code-health-simplifier: a simplifier block that picks one area by evidence and asks for a branch that removes code

depends-on: [code-health-coverage]

Sub-gap 2 of 5 of `code-health` (its definition: `docs/roadmap/overnight/code-health.md`). Branch
`code-health-simplifier`, from main, once `code-health-coverage` has merged. Its coverage report is part of the
evidence, and a module under the floor is never picked.

**How "AI, pool 1" is read.** The owner asked for an AI simplifier in pool 1. Choosing the area is arithmetic on
evidence, so a program does it (rung 4, the refactor path). The AI part is the session that does the removing, and
that session is the ordinary implementor: the simplifier asks for a gap whose definition names the area, its evidence
and the rules of a simplification, and the gap goes through the normal build, review and queue. "Pool 1" is then a
hard rule: at most one simplification gap that has not merged or parked. This is the reversible reading: if the owner
wants a dedicated AI block, the same definition is handed to that block instead of to the request.

## Definition of done

1. **Evidence.** `scripts/code_evidence.py` prints one JSON row per module of `ergostat/`, `dev/bin/` and `scripts/`:
   - net lines and functions longer than 60 lines;
   - churn, as commits touching the module in the last 60 days (`git log --since`);
   - duplication, as function bodies whose normalised AST (names and constants replaced) hashes the same as another's;
   - dead-code candidates: top-level functions and classes that nothing names. The pass looks at `ergostat/`,
     `dev/`, `scripts/`, `tests/`, `pyproject.toml`'s entry points and the model YAML's `run:` lines, and also counts
     a name that appears in a string;
   - coverage share, from `code-health-coverage`'s report.

   "Dead" here means "nothing names it", a candidate only. The output and the docs say so.
2. **The pick.** `dev/bin/simplify.py pick` scores each module from its evidence and takes the highest. The score is
   size over the 75th percentile, plus churn, plus duplicate bodies, plus dead candidates, with weights in
   `[code_health]` of `dev/factory.toml`. It skips modules under the coverage floor, modules a gap in flight touches
   (from the module lists in their definitions), and modules picked in the last 30 days. It prints the module and the
   evidence that chose it.
3. **The request.** `dev/bin/simplify.py` (the block) asks for a gap `gap/simplify-<module-slug>-<yyyymmdd>`, with
   `source: simplifier`, the evidence on the item, and a definition written from `dev/prompts/simplify.md`, which
   holds:
   - the area;
   - the rules: remove and simplify only, without changing behaviour; every test green; no test deleted unless the
     code it tests is deleted; a net lines budget below 0;
   - one commit trailer per removal: `Removed: <class> <path>[::<name>] <lines>`, where class is one of `dead`,
     `duplicate`, `over-general`, `wrong-layer`, `speculative` (an allowlist).
4. **Every few days, or on drift.** In `dev/model/code-health.yaml`, a `simplify-when` expr block fires when it has
   been 3 days since the last simplification gap was requested, or when a measure's drift flag is on (point 5 of
   `code-health-measures` adds that flag; until then the term reads 0). The block does not fire while a
   simplification gap is in flight, or while the day's AI money is spent (`goal.ai-budget.off`).
5. **Pool 1, held.** `simplify.py` takes an flock on `run/simplify.lock` (as `fac.reserve` does on `costs.lock`), re-reads the open simplification gaps and asks for a new
   one only if there are none, all inside the lock. A second run in the same window asks for nothing.
6. **Removals recorded.** `dev/bin/simplify.py removals` is a program block, run on each `gap.merged` whose source is
   the simplifier. It reads the merged commits' `Removed:` trailers and adds one `removal/<gap>-<n>` item for each,
   holding class, path, name, lines, gap and main's merge sha. A trailer whose class is not in the allowlist is
   recorded as `unclassified`, never dropped.
7. `dev/README.md` gets a short section on the block, and SPEC is untouched (this is factory, not product).

## Files to touch

`scripts/code_evidence.py` (new), `dev/bin/simplify.py` (new), `dev/prompts/simplify.md` (new),
`dev/model/code-health.yaml` (new; `ergostat.yaml` includes `dev/model/*.yaml`),
`dev/factory.toml`, `dev/README.md`, `tests/test_code_health_simplifier.py` (new).

## Risks

- lesson-1: two runs both see no open simplification gap and both ask for one. Point 5's lock fixes this, and a test
  puts the competing request in the gap.
- lesson-4: pool 1 read from config with no ceiling. The cap is fixed at 1 in code (the factory starts small, owner's
  decision), and the in-flight count includes gaps queued, in review and in fix.
- lesson-5: an id reused for the same module, so an old park or verdict merges into the new run. The date in the id
  prevents this, and a test remakes the same module on another day.
- lesson-3: `git log` failing, the coverage report missing, or a definition unreadable, read as "no churn", "covered"
  or "touches nothing". Each one means no pick (the run says why and asks for nothing).
- lesson-8: "dead" claimed for names reached by `getattr`, the CLI table, YAML `run:` lines or tests. The pass counts
  strings and those files, and the claim stays "candidate".
- lesson-11: a module path from the evidence used to build a branch name. The slug is checked against `fac.SAFE`, and
  the path is resolved under the checkout.

## Acceptance tests

`tests/test_code_health_simplifier.py`, on a fixture repository:
- `test_evidence_finds_size_duplicates_and_dead_candidates`: a planted duplicate pair, a 70-line function and an
  unnamed function are found. A function named only in a YAML `run:` line, and one named only in a string, are not
  dead candidates.
- `test_pick_skips_under_floor_in_flight_and_recent`: the best-scoring module is passed over when it is under the
  coverage floor, then when a gap in flight touches it, then when it was picked 10 days ago.
- `test_no_pick_when_evidence_is_missing`: no git history, or no coverage report, means no request (lesson-3).
- `test_pool_one_under_a_racing_request`: a second request monkeypatched in between the read and the write leaves
  exactly one open simplification gap (lesson-1).
- `test_same_module_on_another_day_starts_clean`: a parked run of a module, then a new run, gives a new id with no old
  fields (lesson-5).
- `test_removals_recorded_by_class`: a merged run whose commits carry three trailers (one of them with a class not on
  the allowlist) gives three removal items, the third `unclassified`.
- `test_simplify_when_fires_on_age_and_not_in_flight`: the expr block's output is 1 at 3 days with none in flight, and
  0 with one in flight.
- `ergostat check` on the root model reports no errors. The unit suite and the four browser files, rc 0, ruff clean.

## Size budget

250 net lines of code outside `tests/`, `docs/` and `dev/` (`scripts/code_evidence.py`). `dev/bin/simplify.py` and
the model are factory code, kept under about 200 lines.

## Where it stopped

Built: points 1 to 7, with every acceptance test named above (and one more, `test_evidence_reads_this_repository`, the
evidence run over this repository's own HEAD). Nothing is left to build. In practice the block picks nothing until
`code-health-coverage` merges and its report exists: a missing report means no pick (lesson-3), which is the intended
behaviour.

Choices made without an answer, each the more reversible reading:

- **The dependency is parked, not merged.** `code-health-coverage` stopped before its point 3, so main has no
  coverage report. The evidence reads the report in the format that definition names
  (`{module: {"statements", "covered", "share"}}`, or the same under a `"modules"` key) from
  `[code_health] coverage = "run/coverage/coverage.json"`. That path is a setting, to be pointed at wherever the
  coverage gap writes its report. Not checked: the report's main sha or seq against the checkout. A stale report
  is read as it stands; the coverage gap's own measure already refuses stale reports.
- **"Gaps in flight" for what they touch.** Every gap not merged, parked or closed that has a `definition` (or, before
  that, a `plan` under `run/plans/`) is read for module paths (`ergostat/…`, `dev/bin/…`, `scripts/…`; a folder ending
  in `/` touches all of it). A gap whose definition or plan cannot be read stops the pick. An open gap with neither
  counts as touching nothing yet. Otherwise any open GAPS.md entry would stop every pick for as long as it waits, and
  its plan will be written against the main that has the simplification on it.
- **The pool count** is every state but merged, parked and closed (open, planned, ready, fix, building, built, in
  review, approved, queued, queue-failed, dead). The cap is `POOL = 1` in `dev/bin/simplify.py`, not in config.
- **Evidence from main, not the working files.** `code_evidence.py` reads files at `[git] base` with `git ls-tree` and
  one `git cat-file --batch`, so a merge in progress in the queue's checkout cannot change what it sees.
- **The score.** The size term is `max(0, lines / p75 - 1)` (a share over the 75th percentile, so it is on the scale
  of the other terms). Weights default to size 1, churn 0.25 per commit, duplicates 1, dead candidates 0.5. Only
  functions of 5 lines or more count as duplicates.
- **The drift term** is the literal `0` in `simplify-when`'s expr until `code-health-measures` adds the flag. An input
  that is never read would make the expr unknown, and the block would never fire.
- **Pacing.** The simplifier block is `every: 6h` as well as commanded. A pick that finds nothing does not reset the
  3 days, so without that pacing it would run again on every reading.
- **Removals.** These come from the merged commits `pre..main_sha` of `gap.merged`, in topo order. A trailer that
  does not parse is recorded as `unclassified` with its text in `trailer`. The `removal` item kind is declared in
  `dev/model/code-health.yaml`, so the root `ergostat.yaml` is untouched.

Size: `scripts/code_evidence.py` is 157 lines (budget 250). `dev/bin/simplify.py` (210 lines with its docstrings) and
`dev/model/code-health.yaml` (80) come to 290 lines against "about 200". The extra is the sensors' subcommands (`age`,
`in-flight`), the item kind and the system the model needed to pass `check`, and docstrings.

Not run by the implementor: the full unit suite and the four browser files (left to the factory's watchdogged run).
Run: this file's tests, `tests/test_factory.py`, `tests/test_factory_resources.py` and
`tests/test_factory_knowledge.py`, each alone and all green, and ruff clean. Break checks, each failing its test: the
flock removed (the race test requested two gaps); the date left out of the id (the same-module test merged the old
fields); the allowlist bypassed (the removals test); `tests/` and `ergostat.yaml` left out of the naming pass (the
evidence test).

### Round 2: after main (with code-health-coverage) was merged in

The merge of main (71a54d51) brought `code-health-coverage`, merged, and left `dev/factory.toml` with two
`[code_health]` tables. That is invalid TOML, so every factory program would have failed to read its settings. No
test read the real file. Fixed, each the more reversible reading:

- **One table.** `[code_health]` holds the coverage gap's `coverage_floor` and the simplifier's weights. The
  simplifier's own `floor` is gone: the pick uses `coverage_floor`, so the two never disagree.
- **The report as the coverage gap writes it.** The fixed `coverage = "run/coverage/coverage.json"` is gone. That gap
  keeps reports under `run/coverage/<tag>/coverage.json`, so the fixed path would never have existed. With no
  `coverage` set, `simplify.py` reads main's latest report through `measure.coverage_report`, the measure's own
  choice: by `seq`, only a commit on main, refused past 20 merges, and any unreadable report refused. It writes the
  shares to `run/simplify-coverage.json` for `code_evidence.py`. A refusal there is a no-pick (lesson-3). This
  replaces round 1's "not checked: the report's sha or seq". `coverage = "FILE"` still names one report file (the
  tests use it).
- New tests: `test_pick_reads_mains_latest_coverage_report` (no report means no pick; seq 2 is chosen over seq 1; an
  unreadable report means no pick) and `test_the_factory_settings_read_as_one_code_health_table` (the real
  `dev/factory.toml` parses and holds the keys). Break check: the default pointed back at the fixed path fails the
  first. By reading, the second fails on 71a54d51's file (tomllib refuses a table declared twice). That was not run.

Run here, one file at a time: this file's tests (10 passed), `tests/test_code_health_coverage.py` (11 passed),
`tests/test_factory.py` (102 passed, 2 skipped), and ruff clean. Not run: the full unit suite and the four browser files.

### After the factory's unit run failed

The factory's unit run failed with two tests, but its tail did not name them, and the shell was refused for most of
this session. By reading, the likely cause was this file's `simp` fixture. It loads a `fac` of its own, and the
dev/bin modules that `simplify.py` imports (`measure`, `parks`, `times`, `brief`, `knowledge`) stayed in
`sys.modules` bound to that `fac`. A later test on the same xdist worker (`pools.py`'s `import measure`, or
`manager.py`) would then import them bound to a `fac` it never patched. Fixed: the fixture removes each dev/bin module
that it brought into `sys.modules`. Run: this file (10 passed), and in one process this file followed by
`tests/test_factory_resources.py`, `tests/test_factory_manager.py` and `tests/test_factory_sessions.py` (43 passed),
and ruff clean. Not shown: that the old fixture fails that same combination (the run was refused). The two failing
tests are therefore not confirmed, and the factory's unit run is the check.

### After the second unit run

The second unit run's log stops after 22 dots, with no failure, no summary and no `suite_watch` line. The run was
stopped from outside rather than failing a test. One cost found here: reading the root model with its
extreme-conditions tests takes 60 s in a fresh process. It runs to `extremes_cache.BOUND`, and `faulthandler` shows the
time spent in `extremes.failures`. `test_the_factory_model_loads` in `tests/test_factory.py` pays the same 60 s. Not
measured: whether main pays it too (no main checkout could be made here). The gate test,
`test_simplify_when_fires_on_age_and_not_in_flight`, now reads the model with `extremes=False`. Those findings are
never errors, so what it asserts is unchanged, and this file runs in 13 s instead of 67 s. Run: this file (10 passed)
and ruff clean. The factory's unit run is the check.

### Round 3

No review findings to answer, and the branch already has main (505a93e9, still main's head) merged in. No code
changed in this round. Run on the merged tree, one command at a time: this file (10 passed in 7 s),
`tests/test_factory.py` (112 passed, 2 skipped), and in one process this file followed by
`tests/test_code_health_coverage.py`, `tests/test_factory_resources.py`, `tests/test_factory_manager.py`,
`tests/test_factory_sessions.py` and `tests/test_factory_knowledge.py` (129 passed), so the `simp` fixture's clean-up
of `sys.modules` holds against the files that run after it. Ruff clean. Not run: `ergostat check` on the root model
(the shell refused it; `test_the_factory_model_loads` and the gate test read the same model and passed), the full unit
suite and the four browser files (left to the factory's watchdogged run).

### After the third unit run

The third unit run's tail ends at `uv`'s install lines, before pytest printed anything: no dot, no failure, no
summary and no `suite_watch` line. No test failed in it, so there was nothing in the code to fix. As in the second
run, it was most likely stopped from outside. Checked here: the whole suite collects (2439 tests in 21 s). In one
process, this file with `tests/test_code_health_coverage.py`, `tests/test_factory_resources.py`,
`tests/test_factory_manager.py`, `tests/test_factory_sessions.py` and `tests/test_factory_knowledge.py` (129 passed),
and this file followed by `tests/test_factory.py` (122 passed, 2 skipped). Ruff clean. No code changed. Not run: the
full unit suite under xdist and the four browser files. The factory's run is the check.

### After the fourth unit run

The fourth unit run got to its summary: 2 failed, 2373 passed, 69 skipped, at a peak of 402 threads and 165
processes. Both failures are timing tests of the engine. This branch changes nothing they run, so no code was changed
for them (lesson-13):

- `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`: the lease, `ttl: 1s`,
  expired once before its ack (`['expired', 'ack']`). That is the lease watchdog in `ergostat/leases/` against a
  1 s ttl, under load.
- `tests/test_daemons.py::test_a_short_lived_daemon_is_sampled_before_it_ends`: the daemon was not sampled within
  3 s of its start. That is the engine's daemon sampler, under load.

Why they are unrelated: the branch's diff against main (505a93e9, still main's head) touches only `dev/`,
`scripts/code_evidence.py`, `docs/` and `tests/test_code_health_simplifier.py`, and nothing in `ergostat/`. Both tests
build their own project in `tmp_path` from an inline model, and neither reads `dev/`, `dev/factory.toml` or
`dev/model/code-health.yaml` (searched). The simplifier's tests start no engine, daemon or lease. Both look like load
flakes of the engine (lesson-10), to be run again on clean main. A fix for either belongs in its own gap. Not run here:
the two tests alone, on this branch or on main (the shell refused pytest in this session), so "they pass alone" is not
shown. No code changed in this round. Not committed by the implementor either, if the shell also refused `git commit`.
