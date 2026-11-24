# item-metrics-from-the-log: Item counts, transitions and durations become log-derived metrics

depends-on: [metrics-store-with-labels]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. A job maintains these from the item index, never replaying the log per request, and never copying individual events:
- `ergostat_items{kind,state}` gauge (a stock);
- `ergostat_item_transitions_total{kind,from,to}` counter (a flow);
- `ergostat_item_time_in_state_seconds_bucket{kind,state,le}` histogram (a delay);
- `ergostat_item_field_total{kind,field}` counter;
- `ergostat_events_total{type,source}` counter.
- `ergostat_item_last_transition_timestamp_seconds{kind,from,to}` gauge, so a person can ask how long since something last happened, for example the owner's "how long since the last successful merge": `time() - max(ergostat_item_last_transition_timestamp_seconds{kind="gap",to="merged"})`. A test answers exactly that query.
Labels are bounded. An item id, branch, session or commit is never a label, enforced by a guard with a cardinality limit. Milestone may be a label where the kind has one. History is backfilled from the index, and a restart neither loses nor double counts.

Definition of done.
1. On a hand-worked record, each metric equals the count from the index at every minute.
2. Ten items in and ten out between two samples shows in the counter though the gauge is unchanged.
3. Backfill then live updates produce no gap or double count.
4. A field with unbounded values is refused as a label.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Name the system's two edges with reserved states: an arrival (a move with no `from` in the index) is `from="(new)"`, and an item the index forgets is `to="(gone)"`, so the gauge's change equals net transitions. Backfill states what pruned history it cannot recover. `time_in_state` is observed at exit, so it cannot see stuck work: say so in its help text.

## Where it stopped

Round 1: built, 2026-11-24. About 308 net lines of code outside tests, docs and dev (budget 600):
`ergostat/itemmetrics.py` (new, 271), with smaller changes to `spec/itemindex.py`, `victoria.py`, `spec/engine.py` and
`cli/record.py`.

What was built:
- **The job** (`itemmetrics.keep`). The engine's lead calls it from its sweep, every few seconds, and it writes the
  minutes not yet written. All six metrics come from one pass over the item index: its moves, `number_log`, and two
  new tables. The pass reads through a read-only connection, one moment of the index, and never touches the log. Each
  value is the index as of the minute. `itemmetrics.json` holds the last minute written. It is read and written under
  a flock, so a restart writes on from it. A write the server refuses leaves the checkpoint as it was. A checkpoint
  that cannot be read stops the job rather than backfill again (lesson 3). A pass writes at most 1,440 minutes or
  500,000 samples (lesson 4), and a backfill goes on at the next pass.
- **The index**: VERSION goes to 8, so existing indexes are rebuilt and their event history is counted.
  - `event_counts` holds the events per type, source and minute, folded in `_fold`. Snapshots are not counted.
  - `carried` is written by `_reconcile`. It keeps what forgotten items had counted, plus each one's move to `(gone)`.
- **The edges, as amended.** An arrival is `from="(new)"` and a forgotten item is `to="(gone)"`. The tests check that
  each gauge's change equals its net transitions across a prune. A backfill names what it cannot recover in
  `backfill.not recovered`, which is also said on the engine's output. The help text (`itemmetrics.HELP`) says that
  `time_in_state` is observed at exit and cannot see stuck work, and so do SPEC §4b and docs/DASHBOARDS.md §6a.
- **The guard.**
  - Labels come from an allowlist. Any other label name raises `Refused`, so an id, branch, session or commit can never
    be one.
  - Above 100 values in a kind's metric, a label is left out and its series are summed. The checkpoint's `refused`
    names it.
- **The store.** `Victoria.put` sends samples under their own labels, plus `project`. The store's own listing
  (`series`, `first_time`, `count()`) now reads only series that have a `series` label, so the item metrics stay out
  of it. `ergostat reset` forgets the checkpoint, and its `drop()` already deletes every `ergostat_.+` series.

Choices taken without asking (the most reversible):
- **`ergostat_item_field_total{kind,field}`** is the sum of what items' numeric fields went *up* by. A counter cannot
  fall, so a fall is not counted. The definition does not say what the counter counts. Counting changes instead would
  be a one-line change in `Tally`.
- **`milestone`** is a label on the gauge only, taken from the kind's group relation named `milestone` (replace fold),
  as the field holds it now. On a counter, a gap moved to another milestone would make that counter fall.
- **`ergostat_events_total`** counts the events the index folds: those about items, without transcript lines or
  roll-up snapshots. "From the item index" rules out reading the whole log. An event with no source has no `source`
  label.
- **Carried rows** count from the first minute not yet written, not from when the items were forgotten. Their moves
  are already gone from the index by then, so this keeps the counters monotone while a backfill is catching up.
- **Over SQLite nothing is written**, because those readings have no labels and PromQL answers only from
  VictoriaMetrics.
- **A kind without states** has no moves, so it is in no gauge.
- **Each pass reads the whole index**, rather than following it by row numbers. Snapshots re-insert moves under new
  row numbers, so following by row would double count them, while a pure pass cannot. The cost grows with the index,
  and it runs at most once a minute, on the sweep's thread. It was **not measured** on a factory-sized index.

Acceptance tests (`tests/test_item_metrics.py`, 9):
- Done 1: `test_on_a_hand_worked_record_each_metric_is_the_index_count_at_every_minute`. It checks the values worked by
  hand at four minutes for every metric. At every minute it also checks the gauge and the transitions against the
  index's own counts (`tally`, and `moves`).
- Done 2: `test_ten_in_and_ten_out_between_two_samples_shows_in_the_counter_not_the_gauge`.
- Done 3: `test_a_backfill_then_live_minutes_a_refused_write_and_a_restart_leave_no_gap_or_double_count`. The
  stand-in store fails the test on any minute written twice. Every series is present at every minute from its first,
  and the values equal one run from the start, both before and after a late event.
- Done 4: `test_a_field_with_unbounded_values_is_refused_as_a_label`, which also covers `id`, `item`, `branch`,
  `session` and `commit` refused as label names.
- The amendment: `test_an_item_the_index_forgets_moves_to_gone_and_the_counters_never_fall`.
- The owner's query: `test_how_long_since_the_last_successful_merge` answers `time() - max(...{kind="gap",
  to="merged"})` from the samples as written, with PromQL's five-minute lookback written into the test.
  `test_how_long_since_the_last_merge_in_a_real_victoriametrics` asks a real server. **No VictoriaMetrics binary is
  in this container, so the real-server test skipped and has never run.**
- Also: the import format and the series listing, and an unreadable checkpoint and a store without labels.

Seen to fail when the code they guard was broken, each put back after:
- carried rows counted from their own time: the prune test failed (a counter fell from 5 to 1);
- no carry in `_reconcile`: the prune test failed the same way;
- the checkpoint ignored: done 2, done 3 and the prune test failed ("written twice");
- the milestone refusal off: done 4 failed (105 milestone series);
- `from` left empty for an arrival: done 1 and done 3 failed.

Run here, one file at a time (three at most per call):
- test_item_metrics, test_item_index and test_metrics_store_labels: 82 passed, 6 skipped (the real-server tests).
- test_counts, test_rollup and test_index_projections: 112 passed.
- test_item_search, test_item_about and test_sql_source: 37 passed.
- test_graph_cli_web, test_empty_install and test_query_engine: 112 passed.
- test_dashboards_doc, test_spec_structure and test_daemon_docs: 74 passed.
- ruff is clean.

`main` is an ancestor of HEAD. Not run: the whole unit suite and the four browser files (no page changed), and
`demo_check` (no example touched). Left: the real-server test should be run with `ERGOSTAT_TEST_VM_BIN` set before
landing. No lock test puts a competing writer between the read and the write; only the lead runs the job.

Round 2, 2026-11-24. The merge of main conflicted on the index's `VERSION`: both main and this branch had taken 8, so
the merged layout is 9. About 371 net lines of code outside tests, docs and dev now (budget 600). Both review findings
are answered:
- **An index made again no longer makes the counters fall** (finding 1, lesson 8 and done 3). The checkpoint now keeps
  the index's `epoch` (from its `meta`, new whenever `_reset` makes the index again) and every series as last written
  (`written`). A pass over another epoch first sweeps the minute last written. It raises each counter to what was
  written there, keeps each last-move time no earlier, and keeps each gauge series at nothing added (`itemmetrics.hold`).
  The rise is kept in the checkpoint's `held`, and every later pass adds it from the start. This covers a kind edited, a
  new layout, a damaged file healed, and `compact --reindex`, which all start a new epoch. SPEC §4b no longer says that a
  reindex resets the counters, and it names every cause. A smaller point: a prune now keeps each gauge series its
  forgotten items were in, at nothing added (`carry` writes a zero row), so a gauge series has no gap either.
  - Test: `test_an_index_made_again_after_a_prune_holds_every_counter`, run for each of the three causes. No series
    falls and none has a gap. The next move after the rebuild counts once (open to building goes from 1 to 2, and
    `gap.started` from 1 to 2), and the hold lasts into the next pass.
  - What it cannot do: a late event (stamped before the last minute written) that arrives between the last pass and the
    rebuild may be absorbed into a held counter. SPEC says so.
- **Backoff** (finding 2, lesson 4). `itemmetrics.kept` keeps, per project folder, when the next pass may run.
  - After a pass, the next one is not before the next minute, so "at most once a minute" now holds. A backfill goes on
    at one day of minutes per minute.
  - After a fault, the wait is a minute, then doubles with each fault in a row, up to `MOST_WAIT` (an hour). The fault
    is said once per try, with the wait.
  - Test: `test_a_refused_write_is_not_tried_again_until_its_wait_is_over`. A minute of 5-second sweeps against a
    refusing store tries once and says it once. The second try comes a minute later and waits two. After the store
    comes back, nothing runs again within the minute. Faults in a row stop at the ceiling.

Seen to fail when broken, each put back after:
- the re-base switched off: all three rebuild cases failed (a counter's series missing, then falling);
- the wait ignored in `kept`: the backoff test failed (12 tries in a minute).

Run here:
- test_item_metrics, test_item_index and test_metrics_store_labels: 86 passed, 6 skipped (real-server tests, no
  binary).
- test_item_search, test_sql_source and test_counts: 69 passed.
- test_rollup, test_index_projections and test_item_about: 83 passed.
- test_spec_structure, test_dashboards_doc and test_daemon_docs: 74 passed.
- ruff is clean.

Not run: the whole unit suite and the four browser files (no page changed), and `demo_check` (no example touched).
Left, as in round 1: the real-server test has still never run here, and a pass's cost on a factory-sized index is not
measured. The backoff is kept in memory, so a restarted lead tries at once; it runs in one process, so nothing races on it.

Round 3, 2026-11-24. There was one review finding, and it was blocking. No non-blocking finding was raised.
- **Undoing a kind edit no longer double counts what was pruned** (lesson 5, lesson 9, done 3).
  - The bug: the re-base on an epoch change started the tally from the old `held` and only raised it. A prune, then a
    kind edit (index B, held up to what A carried), then the edit undone reopens A's kept file, which still has its
    `carried` rows and its `event_counts`, so what was pruned counted twice.
  - The fix: `sweep` now puts the old `held` aside on an epoch change. `hold(v, written)` works the hold out afresh:
    max(0, written − what this index alone counts) at the minute last written, and the latest written last-move time.
    Back on A, that is nothing, and the stale hold is dropped. SPEC §4b says so.
  - Test: `test_a_kind_edited_then_undone_reopens_the_old_index_without_counting_twice` goes A → B → A after a prune,
    with a move on B and another back on A. It checks that A's file and epoch are reopened with its carry. Across both
    passes after the return, it checks that no counter falls and every series is written once at every minute. It also
    checks the values: 4 gone moves, 5 `gap.found`, a cost total of 4, 5 arrivals, 2 open→building, 1 building→merged,
    and 2 open stays.
  - Seen to fail with the old re-base (the tally seeded from the old hold, and the rise added to it): gone moves went
    from 4 to 8, as the finding said. The fix was put back after.
- About 375 net lines of code outside tests, docs and dev (budget 600).

Run here:
- test_item_metrics, test_item_index and test_metrics_store_labels: 87 passed, 6 skipped (real-server tests, no
  binary).
- test_spec_structure, test_dashboards_doc and test_daemon_docs: 74 passed.
- ruff is clean.

Not run: the whole unit suite and the four browser files (no page changed), and `demo_check` (no example touched).
Left, as before: the real-server test has never run here, and a pass's cost on a factory-sized index is not measured.

## Entry

section: Runtime, scale and latency

- **Item counts, transitions and durations as PromQL metrics** (done, on `item-metrics-from-the-log`; SPEC §4b, *Item
  metrics*; docs/DASHBOARDS.md §6a). On VictoriaMetrics, the engine's lead writes, once a minute from the item index:
  `ergostat_items{kind,state,milestone}`; `ergostat_item_transitions_total{kind,from,to}`, with `(new)` and `(gone)`
  as the edges; `ergostat_item_last_transition_timestamp_seconds`; the histogram `ergostat_item_time_in_state_seconds`,
  observed at exit; `ergostat_item_field_total{kind,field}`; and `ergostat_events_total{type,source}`. A first run
  backfills them and says what pruning lost. A checkpoint means a restart neither loses nor double counts, and an
  index made again (a kind edited, a new layout, a healed file, a reindex) holds each counter at what was written,
  worked out afresh at each change, so undoing an edit counts nothing twice.
  After a fault the next pass waits, doubling up to an hour. Labels come
  from an allowlist, and a label past 100 values is refused. Left: the real-server test has not been seen to pass (no
  binary where it was built), and a pass's cost on a large index is not measured.
