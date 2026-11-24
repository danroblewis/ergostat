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

## Where it stopped

Round 1, built. All four done items are in the branch, and everything is off until the coordinator switches it on.

What was built:
- `dev/bin/verify.py` (new):
  - `quick()`: the check a batch lands on with `[verify] after`. It runs `[suites] imports`, then the changed test files plus `[verify] smoke` through `[suites] rerun`.
  - The lane `verify.py run`, the block `verifier`, every 10 min. It decides when main is due (`due()`: verify-lines, verify-hours, after a revert, or `--now`).
  - It runs the full suites in `run/verify-half/` on half the queue's CPUs, in `suite-verify-*` containers. It moves the ref `verified` only on green, with a compare-and-swap.
  - On red it handles flakes and main's own failures as the queue does. Otherwise it bisects in parallel rounds (`first_red`, `halves.run_all`) and tries the culprit alone on the verified commit.
  - It reverts the culprit and its stacked gaps under the queue's lock, sends the culprit to flake triage (`gap.queue-failed`) and the stacked gaps back to approved (`gap.retried`). It asks for the reverts' push as the queue does and verifies again.
  - `reapplied()` and `taken_out()` let a reverted gap and its stack come back whole.
  - It also has `replay()`, the four dashboard series (`reading()`), and the commands `start`, `verified` and `replay`.
- Hooks in other files:
  - `queue.py`: the quick check in `land.full`, the reapply before each dry merge, `stack()` reading `taken_out`, a `box` parameter for `suites()` and `named()`, and no gap events for a revert push.
  - `halves.py`: a `where` folder, so the lane's sweep never touches the queue's.
  - `upgrade.py watch`: opens versions of the verified commit only, when the lane is on.
  - `measure.py`: the four series.
- Model and settings: in `dev/model/landing.yaml`, the parameters verify-lines (1500) and verify-hours (2h), the block, and the series on the merge-pipeline chart. In `dev/model/measures.yaml`, the four auxiliaries. In `dev/factory.toml`, `[verify]` with `after = false` and `[suites] imports`.
- Docs: dev/README.md (*Merge first, verify after*) and SPEC (*Merge first, verify after*).

Tests, in `tests/test_verify_after.py`, 16 passing:
- Landing:
  - A batch lands with no full suite run.
  - A red quick check keeps its gap off main.
- Triggers:
  - Due on lines, including that a removal adds to the count.
  - Due on hours and on `90m`.
  - Never due when main is verified.
  - Settings that cannot be read mean verifying at once.
  - The model's parameters are the defaults.
- Bisect and revert:
  - Bisected by name: the culprit `a` is reverted with `b`, which is stacked on it. `x` and `c` stay. The ref does not move while main is red, and moves on the green run after.
  - Bisected by full runs when the named tests cannot tell.
  - Two culprits in one window are found one after the other.
  - Main's own failure reverts nothing and holds the lane.
  - A dependent does not land while its reverted base is away.
  - A reverted gap and its stack come back whole.
- Other: `first_red`, the replay, the series, and `switchable`.
- Seen to fail when the code was broken:
  - the quick check switched off;
  - the dependents search removed;
  - `reapplied` emptied;
  - `taken_out` forced to false;
  - `green` taken on red;
  - the standing reverts ignored.

Other suites run, all passing:
- `tests/test_factory.py`: 251 passed, 2 skipped because Docker is absent.
- `test_queue.py`, `test_queue_halves.py`, `test_queue_batch_item.py`: one playwright skip.
- `test_landing_goal.py`, `test_queue_host.py`, `test_dashboard_merge_queue.py` (skipped: no playwright), `test_shell_rule.py`, `test_factory_measure_runs.py`, `test_gaps_doc.py`.
- ruff is clean.
- Not run here: the full unit suite and the four browser files (the merge queue runs those).

Choices and changes to the design, each the most reversible reading I could find:
- Off by default (`[verify] after = false`): the queue behaves as before until the coordinator switches it on, as done item 4 says. The block `verifier` does nothing while it is off.
- "Net lines" are summed per merge as absolute values. Otherwise a removal could cancel an addition and put off verification. This errs toward verifying more often.
- The smoke set is in `dev/factory.toml` `[verify] smoke`, not in the model, because model parameters are numbers. The two files in it (`tests/test_model.py`, `tests/test_spec_compile.py`) have not been timed in the queue's container, so the "under 2 minutes" is not yet checked.
- "Push the reverts" goes through the same gated `push-main` the queue uses, not a direct push.
- A gap stacked on the culprit goes back to approved, as the queue gives back a stacked gap today, rather than to fix. The design's "send the gaps back with the failing tests" applies to the culprit.
- The lane verifies main as pushed, so the verified ref is always on the remote.
- Landing never waits for a verification's suites. It can wait for the queue's lock while the lane writes reverts, which is short. Both lanes count against the load interlock's slots.
- The replay (done item 2) is `verify.py replay [--days 7]`, an estimate with its assumptions stated. It is tested on fixture batches only. It was not run on the live record, which done item 4 forbids.

Left for the coordinator, or depending on other work:
- Switch over: run `python3 dev/bin/verify.py start`, set `[verify] after = true` in factory.local.toml, and point the publish job at `verify.py verified`.
- Lint: the gap lint-in-a-pre-commit-hook is not on main. Until it lands, ruff is caught only by verification, which runs it first. The coordinator may want that gap merged before switching over.
- The revert and reapply commits use `git merge-tree --merge-base`, which needs git 2.40 or later. The container's git passed the tests; the Mac's git version was not checked here.
- No `## Entry` was written: this file may only gain this section.
- Size: 0 net lines outside tests/, docs/ and dev/. All the code is under dev/bin/: `verify.py` (new) and small edits to `queue.py`, `halves.py`, `upgrade.py` and `measure.py`.
