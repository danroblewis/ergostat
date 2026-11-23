# Wave 2: conformance lists as a stock (docs/proposals/conformance-stock.md, section 7)

The proposal's four milestone gaps are each too big for one session (gap 1 alone is a list reader, a runner with
process-group timeouts and a time budget, withdrawals, a template, SPEC and guide text: well over 300 lines with its
tests). Split into 11 gaps, as wide as the real dependencies allow:

```
conformance-list-files ──┬─ conformance-runner-runs-cases ──┬─ conformance-runner-withdraws ──┐
                         │                                  └─ conformance-template ─────────┤
                         ├─ conformance-diagrams-list ───────────────────────────────────────┤
                         ├─ conformance-model-formats-list ──────────────────────────────────┤
                         └─ conformance-discovery-list ──────────────────────────────────────┤
                                                                                             └─ conformance-factory-model
                                                       ┌─ conformance-gap-requester ── conformance-loop-wiring
                                    conformance-factory-model ─┤
                                                       └─ conformance-regressions-ask
```

Width: after `conformance-list-files`, four gaps run in parallel (runner, three lists); after the runner, two more
(withdrawals, template). The three lists depend only on the list format, not on the runner: a check is a plain
command with an exit code, and each list gap validates its file with the reader.

## Decisions taken (each reversible, each the proposal's own assumption)

- The goal form is `every-wish: <= 0` (no hand-raised floor). Diagram cases that are unmet are `asked: false`
  (the owner's 2026-11-16 hold on new diagrams). A lost case only asks the coordinator; holding the merge queue is
  asked in `conformance-regressions-ask`'s record, not built. Lists live in `dev/conformance/`.
- When the runner runs: a generic `--when CMD` (a command whose output is the key; ergostat's factory passes
  `git rev-parse main`) plus a hash of the list files, so editing a list re-runs it. Not "main moved" baked in.
- The runner's whole-run budget is a template parameter (`timeout`, default 30m) passed as `--budget`, so the
  sensor's timeout and the runner's budget cannot drift apart.

## Overlaps with filed gaps (checked against all-gaps.json)

- `gap/export-dynamics-xmile` (ready) builds the XMILE export. The `xmile-export` case is not a duplicate: its check
  asks whether the export exists and is valid; the case is unmet on main and should flip to met when that gap
  merges. That flip is the first real `conformance-gained`. No dependency either way: the list must exist and say
  unmet before the export lands.
- `gap/finding-structure-from-residuals` merged (a83ef734) after the proposal was drafted from GAPS.md:293: it finds a
  missing delay on an inflow (DELAY3, a stock in transit), `ergostat/numbers/structural.py`. The proposal expected
  `structure-from-residuals` unmet; `conformance-discovery-list` must write the check for what the case says ("a
  model missing a stock; the residuals propose it") and record the real result, expected now met or partly met.
- `gap/conformance-stock-proposal` merged: the proposal itself. Nothing else in the filed list names conformance,
  cases or wishes.

## Left out on purpose

- No new page or panel: the count is a stock (drawn where stocks are), the stacked graph is the Items tab's
  cumulative flow diagram for kind `case`. A dashboard panel for it belongs to the dashboard gaps, which can read
  the stock like any other.
- `docs/DISCIPLINES.md:57` ("19 drawn today", hand-kept) is not rewritten here: the diagrams list covers 5 of its 34
  rows, so it cannot replace the count yet. Once the owner adds more diagram cases it can.
- More lists for ergostat (the CLI, the remote API, the item kinds' tools) are the owner's to name.

## Owner questions (one sentence each, carried in the gaps' records)

1. Keep diagram cases closed to the loop (`asked: false`) until the user flows are decided? (assumed yes)
2. Should a lost case also hold the merge queue, as image-squeeze's rollout refuses a candidate that loses one?
   (asked in conformance-regressions-ask; not built)

The gap definitions are in the structured result.
