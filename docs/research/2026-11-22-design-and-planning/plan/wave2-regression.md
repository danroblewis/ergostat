# Wave 2: regression guarantees (docs/proposals/regression-guarantees.md, section 7)

Planner's notes. The gaps themselves are in the structured result; this file keeps how they were cut and why.

## Line drift

The proposal cites main at 5617e225. Main has moved (277a9c6c at planning). Lines re-checked and cited as they are now:

- queue.py: the per-suite record is dev/bin/queue.py:111-114 (proposal: 104-105); `excused()` writes `flake.seen` at
  dev/bin/queue.py:241-242 (proposal: 206-208); `gap.merged` written at dev/bin/queue.py:842-843.
- measure.py: `flake-rate` is dev/bin/measure.py:174-176 (proposal: 167-169), and still reads 0.0 with no runs.
- triage.py writes `flake.seen` at dev/bin/triage.py:76 (proposal: 71).
- onmain.py: `flake.seen` at :74, `flake.main-broken` with a fresh `main_broken_at` at :92-94 (unchanged).
- manage.py `do_flake` at :228-233; fac.beside's release at dev/bin/fac.py:595-598, the `flake.measured` writes at :598
  and :610.
- The flake kind: ergostat.yaml:193-202 (states seen, main-broken, fixed; `flake.fixed` declared, nothing emits it).
- SPEC moved a lot: goals section 8 now starts at docs/SPEC.md:2199 (`on-stale` row 2229, missing feedback 2232,
  `per: item` 2241); changesets (`patch` with `test`, applied whole or not at all) docs/SPEC.md:1226-1243; the repair
  state table docs/SPEC.md:6708-6710 and parts table 6723.

## Choices made while cutting

1. **Gap 2 (flake-lifecycle) is four gaps.** As written it is well over 300 lines (four writers changed, a new event,
   a new re-check run, a counter of green runs, a hand command, the release event, the remake). Cut into: the writers'
   state guard and the remake (`regression-flake-writes-hold-state`), the way out of `main-broken`
   (`regression-flake-main-fixed`), the way out of `seen` (`regression-flake-fixed-after-green`), and the person's way
   out plus the release event (`regression-flake-fixed-by-hand`). The last three depend only on the first and run in
   parallel (separate modules: dev/bin/flakes.py is the first's; the re-check is dev/bin/mend.py).
2. **The re-check of `main-broken` tests is its own scheduled block, not a step of the queue.** The proposal puts it
   "after each landing" in the queue. That lengthens every queue run under the queue's lock. A program block
   `main-mend` every 30 minutes on the pushed main, waiting for a quiet machine as triage does, gives the same
   guarantee (main fixed is seen within one period) without slowing landing. Reversible: the same function can be
   called from the queue later.
3. **The race guard uses the record's own compare-and-set.** SPEC's changesets allow a JSON Patch `test` op and apply
   whole or not at all (docs/SPEC.md:1230-1243). `flake.main-fixed` is written as a patch that tests `/main` is the
   sha it checked, so a newer break written in between refuses it (lessons 1, 2). The writers of `flake.seen`, which
   must look at the item's *state* (not a field), go through one helper under one lock file and write synchronously
   (`fac.add`), so check and write are one step.
4. **The repair clock is read from the item's moves, by record order**, not a stamped field. `ergostat item ID --json`
   already gives the moves in record order (dev/bin/times.py:1-2, dev/bin/watch.py:92-101). The writer keeps the first
   `main_broken_at` for display only.
5. **"Passed in a green run" needs evidence the test ran.** The unit and browser commands print no PASSED lines
   (dev/factory.toml:158, :170: `-rfEs`, `-rs`), so a deleted or renamed flake would count as passing: a fail-open.
   `regression-flake-fixed-after-green` adds `p` to their `-r` and reads `fac.outcomes` (dev/bin/fac.py:582-588) over
   the whole log: pass only on a PASSED line, anything else unknown.
6. **Goals land before their loops; one gap wires them.** Every measure gap writes its own model file
   (dev/model/guarantees-<area>.yaml, taken in by `include: dev/model/*.yaml`, ergostat.yaml:18-19) so parallel gaps do
   not edit the same lines (a queue conflict is a failed gate). Their goals are missing feedback until
   `regression-guarantees-wired` puts them all into one `guarantees-off` expr feeding `factory-off`, names the loops,
   and makes `check` clean. The proposal itself expects this ("building the goals before their loops shows up as a
   finding and not as silence"). Only `main-green` is wired at once (critical), in the skeleton.
7. **Escapes become items for the learning loop.** "Only once" for the librarian's escape step is a lease on an
   `escape/<gap>` item, the way every other once-only step in the factory is held (an item is a fold of events, not a
   ticket).
8. **Two small test gaps from section 2** (untested guarantees named there, not in section 7): the `build_hours` park
   (dev/bin/implement.py:190-193) and "an empty install runs nothing" (CLAUDE.md:52-53). Cheap, and each is a
   regression guarantee with no test.
9. **The owner's question** (hold the queue while `main-green` is off) is asked in `regression-guarantees-model`'s
   definition and not built. It slows landing, so it waits for the owner.

## Overlap with filed gaps

- `flake-quarantine-continued` (state fix) changes the quarantine and fac.beside. `regression-quarantine-goals` and
  `regression-flake-fixed-by-hand` touch the same code, so they depend on it.
- `bisect-tests-main-itself` (approved) is the queue's own blame of main; nothing here duplicates it.
- `repair-verify` (merged) built the `regressed` state the template's goal reads.
- No filed gap measures escapes, test counts, flake lifetimes or the quarantine's size.

## Order (waves)

- Wave A (no dependencies): queue-test-counts, flake-writes-hold-state, flake-rate-counts-excused,
  escapes-from-reverts, fixes-hold-goal, test-build-hours-park, test-empty-install-idle.
- Wave B: flake-main-fixed, flake-fixed-after-green, flake-fixed-by-hand; regressions-template.
- Wave C: guarantees-model; escape-rate-goal.
- Wave D: tests-passing-goal, flake-measures, quarantine-goals, gate-catches, lessons-recurring, escape-learning;
  template-docs-demo.
- Wave E: guarantees-wired; then guarantees-on-diagrams.
