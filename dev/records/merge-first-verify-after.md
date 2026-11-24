# merge-first-verify-after: approved work lands on main at once; main is fully tested per amount of change, then bisected and reverted if red

The owner, 2026-11-23: "if you can think of a reasonable way to merge everything first and verify after, then yes we do that ... we don't want regressions, but we can test regressions less frequently. maybe we can do regressions per lines of code added or something?"

Design (build this; amend only with a stated reason):
1. **Land fast.** An approved gap merges onto main after a quick check only: it merges cleanly, it imports, and the test files it added or changed pass (plus a smoke set of under 2 minutes, listed in the model). No full suite before merging. Lint is handled by the pre-commit hook (lint-in-a-pre-commit-hook), never tested here.
2. **Verify by amount of change.** Main's full suites run on its tip when the net lines merged since the last verified commit reach a threshold (start at 1,500), or 2 hours have passed, whichever is first; and always before a version switch or a publish. Both values are model parameters, so a controller (error-budget-sets-check-level) can move them. Verification runs in its own lane beside landing, within the machine's resource bounds, and landing never waits for it.
3. **Red: find and revert.** On a red verification, bisect the merges since the last verified commit (the parallel rounds in dev/bin/halves.py), confirm the culprit alone on its base, revert it and any merge that depends on it (stacked gaps), push the reverts, and send the gaps back with the failing tests. Re-verify after the revert. A failure that is main's own or a flake is handled as the queue does today.
4. **Verified is a ref.** The last verified commit is recorded (a `verified` ref and an event). The public publish job and version switches take only verified commits. Unverified main is never published.
5. **Measured.** Escapes caught by verification, reverts, time from merge to verified, and suite runs per merged gap are dashboard series, compared against today's numbers.

Definition of done.
1. Tests on a fixture repo: gaps land without a full suite; verification triggers on the line threshold and on the time limit; a red window is bisected to the culprit, which is reverted with its dependents and sent back; the verified ref moves only on green.
2. A replay of the last week's batches reports suite runs per merged gap and time to main, before and after.
3. dev/README.md and SPEC describe the flow.
4. Do not measure or change the live instance in the session: the coordinator switches the factory over and points the publish job at the verified ref.
