# Wave 2: the merge pipeline (trunk development at scale)

The area: the owner's direction on the merge pipeline. These were filed already and are not proposed again:
`bisect-tests-main-itself` (approved) and `queue-runs-what-its-container-skips` (merged). Also related and not
duplicated: `gaps-md-no-collisions` (merged: union merge on docs/GAPS.md, intake `twice()`), `gap-records-out-of-docs`
(merged), `red-batch-fast` (merged: named-test bisect), `queue-takes-all-ready` (parked), `flake-quarantine-continued`
(fix).

## What the record says (2026-11-22, read from the live factory's record and run/queue/)

- **GAPS.md still costs merges after the union merge.** The union merge removed textual conflicts. It made splices
  instead: three reviewer send-backs today cite lesson-7 splices of docs/GAPS.md (relative-gain-array 06:28,
  remote-items-record 06:30, remote-process-lines 06:57). Two queue failures came from tests that pin GAPS.md text:
  upkeep-record-loops 06:24 (`tests/test_gaps_doc.py`), item-search-join-2 07:22 (`tests/test_item_search_gaps.py`).
  Fix rounds were spent on it as well (commit ec398175 "conflicts and GAPS splice resolved"). The cause is a rule:
  `dev/knowledge/house-rules.md:33-34` tells every gap to keep GAPS current, and umbrella entries (Remote systems,
  docs/GAPS.md:9-45) collect one "done on X" sentence from each sub-gap, so parallel branches all edit one paragraph.
  Readers of the file: intake.py:218 (gap.found and closing), deps.py:44-70 (Depends-on tables and phrases),
  brief.py:42-54 (the brief's entry), plan.py:133,422, knowledge.py:231.
- **Serial bisect: the cost is the full runs, not the named ones.** operating-states-20261122T094631Z ran 23 suite
  runs from 09:46 to 11:01. Each round was a full run (about 9 min), then three serial named runs (about 1 min each),
  then a full run on what was left (queue.py:705-722). That is one full run per failing merge. queue-runs-what-its-
  container-skips-20261122T083445Z did the same from 08:34 to 09:46. In both, the named tests were what decided. So
  the gain is to remove every merge that fails on the named tests in cheap parallel rounds, and to finish with one
  full run, rather than one full run for each failing merge.
- **Browser failures are anonymous.** `browser` runs `-q -rs` (dev/factory.toml:170), and `-r` replaces pytest's
  default `fE`, so no FAILED line is printed and `fac.failed_tests` (fac.py:556-561) returns none. Every browser red
  in the record (5 queue-failed events, 11-20 to 11-22) carries a tail and no test names. So it is never excused
  (queue.py:217-222), never bisected by name, and triage says "named no test" and sends it to fix (triage.py:60).
  `rerun` has the same `-rs` (factory.toml:180).
- **Every batch pays for the browser suite** (queue.py:156): about 9-10 min of 4 CPUs, whatever the batch touched.
- **Dependencies wait for the merge.** The implementor takes `unblocked: true` (dev/model/building.yaml:209), and
  precedence is finish-to-start on `merged/closed` (ergostat.yaml:115, 291). A dependent waits for review, the queue
  and the push of its base. agents.clone (agents.py:282-296) always branches from main.

## The plan

Four tracks, wide. A gap depends on another only where its code needs that gap's code, or where both edit the same
function.

```
(a) GAPS.md from records:
    gaps-entries-in-records ─► gaps-readers-read-records ─► gaps-md-regenerated-on-land
(b) speculative bisect:
    prefix-runs-in-parallel ─┐
    [bisect-tests-main-itself]┴► bisect-in-parallel-rounds ◄─ stacks-land-bottom-up
(c) stacked branches:
    relation-starts-at ───────────────────┐
    stacked-gap-builds-on-its-base ──┬────┼─► stacks-turned-on
    [bisect-tests-main-itself] ─► stacks-land-bottom-up ┘
                                     └─► stacks-merged-forward
(d) browser trigger:
    browser-names-its-failures ─► browser-daily-on-main ─► browser-only-on-its-paths
```

Choices made, each one easy to undo:
- **(a)** An entry lives in the record of the gap it names: `dev/records/<branch>.md`, where branch is the intake's
  `slug(title, 32)`. It goes in an `## Entry` section with a `section:` line. A sub-gap's record gives one `done:`
  sentence and `entry-of: <umbrella branch>`, so no two branches edit one paragraph. The queue regenerates
  docs/GAPS.md on the landed head, as its own commit, and a branch that edits docs/GAPS.md is refused before its
  suites. dev/records/ is outside the size gate (fac.py:249-258), so the migrated text costs no budget.
- **(b)** Speculation runs on the cheap checks only: the named failing tests, and ruff. Each check runs on every
  prefix at once, each prefix in its own detached worktree and its own queue container. A full suite per prefix would
  need 12 CPUs per prefix. The only full run is the last one, on the survivors.
- **(c)** Stacking is a generic engine option: a precedence relation's `starts_at:` names the target states, besides
  finished, at which a dependent may start. The CPM estimates stay finish-to-start, which is conservative and said
  so. The factory names `starts_at: [approved, queued, push-pending]`, and only in the last gap, once the
  implementor, the reviewer and the queue all handle a stacked base. A stacked gap brings its unlanded base into its
  own queue batch, below it. When a base fails in the queue, its descendants are given back uncounted and are never
  merged again without it. A clean merge-forward of an approved descendant keeps its approval: the merge brings only
  reviewed commits, and the queue tests the result. A merge-forward that conflicts sends the descendant to fix.
- **(d)** The daily main run takes the queue's lock and runs on the queue's CPUs, so it never overlaps a batch. A
  failure that passes alone twice is recorded as a flake. A real failure is a `queue` intervention, which names the
  tests and the merges since the last green day as suspects. The path trigger turns on only once the daily run
  exists.

Not planned, and left to the owner: speculation over full suites (it needs more CPUs than the queue has), stacking a
gap on more than its approved bases' merge (a base still in review), and restacking onto main when a base is parked
(the descendant waits, `waits_on_parked`, as today).
