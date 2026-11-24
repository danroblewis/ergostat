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

Round 2. The one finding (blocking): a conflicted merge of main that the session finishes with `git commit --no-edit`
ran the hook on every Python file main changed since the fork. Fixed: the hook does nothing on a merge commit (`git
rev-parse -q --verify MERGE_HEAD` succeeds, so it exits 0 before listing anything). This was taken over limiting the list
to files that also differ from MERGE_HEAD because skipping is narrower and simpler: even in a conflicted file, the hook
would otherwise reformat main's lines as well as the session's. The cost is that a session's conflict resolutions go in
unformatted, which is acceptable because lint is no gate. The docstring, the hook's comment, dev/README.md,
dev/factory.toml and the implementor prompt now say merge commits are skipped. New test:
`test_a_conflicted_merge_the_session_commits_leaves_mains_files_as_main_had_them`. In it, main changes a badly
formatted .py file and both sides change one other file. After the session resolves the conflict and commits, the .py
file is byte-for-byte main's and does not differ from main. The session's next commit is formatted again. With the
MERGE_HEAD line removed, the test was seen to fail: the file came back reformatted. The doc comment in
dev/bin/queue.py that round 1 made too long is rewrapped. Other commits that are not the session's own, such as a
cherry-pick or a revert, still run the hook; neither the brief nor the factory makes a session do them.

Run in round 2: tests/test_lint_hook.py (8 passed), tests/test_agents.py, tests/test_shell_rule.py, tests/test_queue.py
(53 passed), tests/test_factory_knowledge.py, tests/test_plan.py, tests/test_knowledge.py (120 passed). Also run:
`uv run ruff check ergostat tests scripts`, which was clean. main is already merged in (no change since the clone). The
unit suite and the browser files were not run here; they are the factory's.

Round 3. The one finding (blocking): main (49a47c01) conflicted with the branch in dev/bin/plan.py, in the S-gap
definition text. Resolved by keeping both changes: main's (it dropped ", no review" when plan review was removed) and
the branch's (it dropped "ruff is clean"). Merge committed; nothing else changed. After the merge no prompt, house rule
or factory setting main brought asks for ruff again (searched dev/ for "ruff"). Run after the merge:
tests/test_lint_hook.py, tests/test_plan.py and tests/test_agents.py (43 passed), tests/test_queue.py,
tests/test_factory_knowledge.py and tests/test_shell_rule.py (126 passed), tests/test_knowledge.py and
tests/test_cleanup_finished.py (12 passed); `uv run ruff check ergostat tests scripts` clean. The unit suite and the
browser files were not run here; they are the factory's.

Round 4. The one finding (blocking): in a batch of 10 and again alone,
tests/test_code_health_coverage.py::test_the_queue_traces_only_its_unit_run[True] and [False] failed. That test came
from main's code-health-coverage gap and expected the queue to run a ruff step. Its instance takes the factory's
dev/factory.toml, where this branch sets `ruff = ""`, so `queue.suites` runs unit, browser and demo with no ruff step.
The queue's change is what this gap asks for (done item 2), so the test changed, not the code: it now expects
{unit, browser, demo}, and each of browser and demo still gets no command. Nothing else changed. Searched tests/ for
other tests that expect "ruff" in the queue's steps: the rest set their own suites or do not run `queue.suites`, and
the queue named no other failure. Run: tests/test_code_health_coverage.py (11 passed; the two cases failed in the queue
before the change); `uv run ruff check ergostat tests scripts` clean. main is unchanged since the clone, so no merge
was needed. The unit suite and the browser files were not run here; they are the factory's.
