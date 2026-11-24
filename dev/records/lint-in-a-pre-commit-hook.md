# lint-in-a-pre-commit-hook: Linting is fixed by a pre-commit hook and never tested or reviewed

The owner: "we don't really care about linters at all, this is AI generated code ... just do a pre-commit hook, we don't need to ever test for linting." Add a hook in every build session's checkout that formats and auto-fixes (`ruff format`, `ruff check --fix`) before each commit. Remove ruff from the merge queue's suites and from the builder's gates, and tell reviewers not to raise lint or style.
Done: 1. A test proves a commit with fixable lint lands formatted. 2. The queue no longer runs ruff, and a batch is never red for lint. 3. The reviewer prompt says lint and style are out of scope.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Built, round 1. All three done items are in the code, with acceptance tests in `tests/test_lint_hook.py`:

1. `test_a_commit_with_fixable_lint_lands_formatted`: a repository given ergostat's ruff settings (its pyproject.toml)
   and the hook `agents.precommit` writes from the factory's own `[suites] precommit`; a commit of badly formatted
   Python with an unused import lands formatted and fixed, a non-Python file as written, and a file with lint ruff
   cannot fix (F821) is committed anyway. `test_a_failing_precommit_command_never_refuses_the_commit`,
   `test_no_precommit_setting_writes_no_hook`, and `test_an_implementor_round_runs_no_ruff_and_its_clone_has_the_hook`
   (a stand-in round writes the hook into its clone and runs no ruff).
2. `test_a_batch_with_lint_is_never_red_for_it` (a queue run on a gap adding Python with lint lands, runs unit,
   browser and demo, and `suites_queue` has no ruff) and `test_the_factory_runs_no_lint_gate` (dev/factory.toml's
   `ruff = ""` turns the step off in `queue.lint_on` and `onmain.fast`; set again, it comes back).
3. `test_the_reviewer_and_the_builders_are_told_lint_is_out_of_scope`: dev/prompts/reviewer.md says lint and style are
   out of scope; the implementor and simplify prompts, the house rules and plan.py's S-gap definition no longer ask
   for ruff. CLAUDE.md's "ruff before every commit" line is changed to match (the reviewer reads CLAUDE.md).

Each test was seen to fail when the code it guards was broken: the queue's `lint_on` filter removed, `onmain.fast`
always naming ruff, the `agents.precommit` call removed from implement.py, and the hook's re-stage line removed.

Choices taken alone (no one to ask; the most reversible each):

- Everything is in the factory (`dev/`), nothing in ergostat's core: a git pre-commit hook in a build session's
  clone and the queue's suite list are factory machinery, not something a model declares. Both are settings that
  are off unless set (`[suites] precommit` empty: no hook; `[suites] ruff` set again: the gate is back), so undoing
  it is one line each in dev/factory.toml.
- The hook is written after implement.py's own commits (the definition, main merged in), so it runs only on the
  session's commits, inside its container; never on the Mac. `agents.finish` still commits what a session left
  uncommitted with hooks off (it disables them on purpose: a session could plant one), so that one commit is not
  formatted. Lint is checked nowhere, so it can never turn anything red.
- The hook stages each fixed file whole again, so hunks a session left unstaged in a file it commits go in too. It
  never refuses a commit: the formatter failing, ruff missing or unfixable lint all let the commit through.
- No regression path was added: lint does not change behaviour, and the unit, browser and demo suites still run in
  full in the queue.
- No `## Entry` was added to this record: the definition is never changed except for this section, and the brief
  found no entry for this gap.

For the coordinator, before applying it: the tree is not `ruff format`-formatted (about 4,200 aligned inline
comments under `ergostat/` alone, which the formatter cuts to two spaces). With the hook on, each Python file a session
commits is reformatted whole, so diffs grow, two gaps touching one file are likelier to conflict, and the net-lines
gate may count the reflowed lines. A one-time `ruff format` of main before turning the hook on (the coordinator's
change, not this branch's), or dropping `ruff format` from `[suites] precommit`, would avoid that.

Not run here: the whole unit suite and the four browser files (the factory's). Run: tests/test_lint_hook.py,
tests/test_agents.py, tests/test_plan.py, tests/test_factory_knowledge.py, tests/test_queue.py,
tests/test_shell_rule.py, tests/test_knowledge.py, all passing (test_shell_rule.py after its expected implementor
commands dropped the ruff line, which this gap removes from the brief).
