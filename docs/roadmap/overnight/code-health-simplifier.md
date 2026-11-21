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
