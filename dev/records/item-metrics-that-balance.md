# item-metrics-that-balance: Arrivals and forgotten items counted as transitions, a test that gauge change equals net transitions

depends-on: [item-metrics-from-the-log, metrics-store-with-labels]

From the chart catalog, `docs/research/2026-11-23-charts/catalog.md`: read section 7 for this item, and the sections it cites (result shapes in section 2, guardrails in section 6, workflows in section 5, and the source reports beside it).

The owner's decisions (2026-11-23): data sources are like Grafana's, each with its own text language; PromQL is primary and read-only SQL is only for what PromQL cannot do; metrics hold aggregates over bounded labels and anything with a generated ID stays in the event log; stocks are gauges, flows are counters, delays are histograms; no visual query builder; result shapes decide which charts apply. VictoriaMetrics is the default metrics store for new installs. Rework means an item repeated a step. The new diagram kinds named in the catalog are allowed (update `docs/proposals/diagram-options.md`), limited to those named kinds. The service map is built from caller and callee labels in metrics first. No new pages: charts are Dashboard panels or live on existing pages, and the Blocks and Dynamics views stay separate and true to their disciplines.

This is item B4.

Delivers: Arrivals and forgotten items counted as transitions, a test that gauge change equals net transitions

Unlocks charts: 17 (section 3.2).

Definition of done.
1. Everything this item delivers in the catalog works on a hand-worked record, with its numbers checked by a test.
2. Each guardrail the catalog assigns to this item refuses or warns as stated, with a test that tries the misuse.
3. A chart that cannot be trusted on its data says so, and does not draw as if it could.
4. Decision logic is in pure functions with fast in-memory tests. Anything the catalog marks `[unsure]` is measured or left visibly unsure, never assumed.
5. It works at factory size within the budgets the catalog states, and reads neither the event log per request nor a raw internal table from the page.

## Where it stopped

Round 1: built, 2026-11-24. 60 lines added and 3 removed, all in `ergostat/itemmetrics.py`, against a budget of 600.

The dependency `item-metrics-from-the-log` had already taken the catalog's amendment (§7.3). An arrival is
`from="(new)"`, a forgotten item is `to="(gone)"`, and its prune test compared one gauge's change with its net
transitions. This item makes that balance hold in the cases where it did not, says where it cannot hold, and checks it:
- **The edges survive a refused label.** A kind with more than `MOST_VALUES` states had `state`, `from` and `to` left
  out entirely, so its arrivals and forgotten items became one unlabelled series and the kind could not balance at
  all. `Tally.key` now keeps the values `(new)` and `(gone)` when it drops a refused label, so the kind still balances
  as a whole.
- **An index made again is marked.** A kind edited, a new layout, a damaged file or a reindex gives a new epoch. The
  counters are held at what was written, but the gauge is counted afresh, so a kind edit that changes states moves
  items between gauge series with no transition. Each pass over another epoch now adds one to a new counter,
  `ergostat_item_index_rebuilds_total`. It has no labels, is written at 0 from the first minute (so `increase()` sees
  its first rise), and is held like the other counters (an undone edit, A→B→A, counts 2).
- **`itemmetrics.balance(before, after)`** is a pure function of two minutes' values as written. For each kind and
  state, it checks that the gauge's change, added over `milestone`, equals moves in less moves out. For each kind as a
  whole, it checks the change against arrivals less forgotten items. A kind whose state is refused on either side is
  checked only as a whole. The verdict is `balanced`, `unbalanced` with each residual, or `unsure` with why: nothing
  written before, or the rebuild counter changed between the two minutes. `keep` runs it on every pass between the
  minute last written and its own last minute. The verdict goes in the checkpoint's `balance`, and an imbalance is said
  on the engine's output. Nothing is ever added to close a gap (G18).
- SPEC §4b and docs/DASHBOARDS.md §6a say all of this, including the per-kind form and the rebuild window to read no
  leak into.

Choices taken without asking (the most reversible):
- **Chart 17 (cumulative flow) is not drawn here.** The item's "Delivers" names the transitions and the balance test.
  The chart is what that unlocks. As a typed panel it needs B3's result shapes, and its trust layer needs B8's
  conservation ledger (LG, `reconcile`). So done item 3 is met at the data level: across a rebuild the balance says
  `unsure` rather than claiming either way, and the counter lets a PromQL panel see that window. No chart in this item
  draws as if it could be trusted.
- **Guardrails.** §6 assigns none to B4 by name. The two this item touches are tried by tests: G18 (a gauge that does
  not balance is reported and never plugged) and G24, the cardinality guard on states (the edges kept). G25 (the CFD's
  horizontal readout) belongs to the chart and is left to it.
- **A balance failure is said, not raised.** The pass still writes, as the metrics stay true to the index. Only the
  verdict and the output line show it.
- One dependency test changed: `test_a_kind_edited_then_undone_reopens_the_old_index_without_counting_twice` expected
  nothing but last-move times in `held`. The rebuild count is now held on purpose, so the test allows it and checks it
  is 2.

Acceptance tests (`tests/test_item_metrics_balance.py`, 4):
- Done 1: `test_on_a_hand_worked_record_each_gauge_change_is_its_net_transitions`. Five gaps: one forgotten by a
  prune, one that changes milestone while building, and one stamped before the last minute written. Each minute's
  states, arrivals and forgotten items are worked by hand. At every minute it checks that the stock is arrivals less
  forgotten and that each state is in less out. From the first minute to the last it checks the hand values: open −1
  against −1, building +1 against +1, merged +1 against +1, the kind +1 against +1. Every pair of minutes balances, and
  the checkpoint's verdict is `balanced` with 4 checked.
- Done 2: `test_a_kind_whose_state_label_is_refused_keeps_its_edges_and_balances_whole` (G24 on states) and
  `test_a_gauge_that_does_not_balance_is_said_and_never_made_up_by_a_flow` (G18: one written gauge series one too
  high gives residuals of −1 against 0 for `open` and for the kind, said once, with no series or counter added).
- Done 3 and 4: `test_across_an_index_made_again_no_balance_is_claimed`. A kind edited renames `open` to `queued`. The
  rebuild counter goes from 0 to 1. With the mark removed, the same values read `unbalanced`. With it, they read
  `unsure`, and the next pass is `balanced` again. With nothing written before, the verdict is `unsure`.

Seen to fail when the code they guard was broken, each put back after: the edges dropped under refusal (test 2 failed),
the rebuild not counted (test 3), the per-kind edge sign flipped in `balance` (test 1), and the imbalance not said
(test 4).

Run here, one file at a time (three at most per call):
- test_item_metrics_balance, test_item_metrics and test_metrics_store_labels: 32 passed, 6 skipped. The skips are the
  real-server tests: `ERGOSTAT_TEST_VM_URL` is not set and no binary is here.
- test_dashboards_doc, test_spec_structure and test_item_index: 104 passed.
- test_counts, test_rollup and test_index_projections: 115 passed.
- ruff is clean. `main` is an ancestor of HEAD, so there was nothing to merge.

Not run: the whole unit suite and the four browser files (no page changed), and `demo_check` (no example touched).

Left:
- **Done item 5 is only half shown.** `balance` is pure, reads only the values a pass already holds, costs one walk
  over the series, and runs nowhere per request. But a pass's cost on a factory-sized index is still not measured, as
  the dependency also left it. The catalog states no budget for B4. A scratch measuring script could not be run here:
  writing `/tmp/b4size/b4size.py` was refused as outside the working folder, and so was
  `uv run python scripts/suite_watch.py -- uv run python /tmp/b4size/b4size.py 5000`.
- **The PromQL form of the balance on VictoriaMetrics is `[unsure]`** (catalog §7.4 item 2). `balance` works on the
  values as written, so it is exact. The `increase()` form in SPEC relies on VictoriaMetrics not extrapolating, and
  this has not been seen against a real server.

## Entry

section: Runtime, scale and latency

- **Item metrics that balance** (done, on `item-metrics-that-balance`; SPEC §4b, *Item metrics*; docs/DASHBOARDS.md
  §6a). Arrivals (`from="(new)"`) and items the index forgets (`to="(gone)"`) are transitions, kept even when a kind's
  `state` label is refused. Each pass checks that every gauge's change is its net transitions, by state and for each
  kind (`itemmetrics.balance`). The verdict goes in the checkpoint, and an imbalance is said, never plugged. An index
  made again is counted in `ergostat_item_index_rebuilds_total`, and a balance across one is `unsure`. Left: a pass's
  cost on a factory-sized index is not measured, and the `increase()` form has not been checked on a real
  VictoriaMetrics.
