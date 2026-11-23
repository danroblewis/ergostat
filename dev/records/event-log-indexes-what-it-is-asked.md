# event-log-indexes-what-it-is-asked: no routine event-log question reads the whole log

The event log's sealed segments index events by item and by type, but not by what caused them. `Events.caused_by(run)` therefore decompresses and parses every segment, on a log of about a million events, and its cost grows with the record. The lease dispatcher calls it for each overdue lease, so one stall with many overdue leases kept the single dispatcher thread scanning and stopped all new work. About a dozen other callers use the same query.

Change.
1. Index `causedby` in each segment and in the live head, so `caused_by` reads only the matching rows. Existing segments must work without being rewritten, for example through an index built once beside them.
2. List every query in `segments.py` that still falls through to a full scan (a `test=` predicate, `item_test`, or no selective filter). Index it or bound it, and name any left unbounded with the reason.
3. The dispatcher must not let reading one lease's activity delay taking work for other blocks.
4. Add a query-cost check: a test that counts segments or rows read, so a new full scan on a routine path fails a test instead of showing up as a slowdown in production.

Keep the JSONL-and-segments record as the source of truth. Do not replace the storage engine in this gap. If the measured query mix shows the format cannot serve it, write that up with numbers as a proposal.

Definition of done.
1. `caused_by` on a synthetic log of 1,000,000 events reads only segments holding matches, and its time does not grow with unrelated events.
2. Answers are identical to the old scan, including events still in the head and across a segment seal.
3. Old segments with no index still answer correctly.
4. A test shows many overdue leases do not delay a take.
5. Do not measure the live instance in the session.

## Where it stopped

Built, round 1: all four changes and all five done items. 144 net lines in `ergostat/segments.py` (145 added, 17
removed) and `ergostat/leases/dispatch.py` (30 added, 14 removed), within the 600 budget. SPEC §4b (*Events*) and §9.5
(the watchdog's paragraph) say what changed.

What changed:
1. **`causedby` indexed** (and `source`: see 2). Beside each segment, `seg-<...>.cby` (and `.src`) is a `Keys` index:
   a JSON header line, then the values' 64-bit hashes sorted, each hash's first row, and the rows ordered by hash then
   row. `write_segment` writes them before the `.idx`, so a segment that can be seen has them. The hashes and starts are
   kept in memory per segment (8 + 4 bytes per distinct value). A hit reads only that hash's rows from the file. The
   head keeps `by_key` dicts as it keeps `by_item`/`by_type`. `_rows` and `_scan` take `key=(field, value)`, and the
   scan always compares the event's own field too, so two values sharing a hash are told apart. `caused_by` is
   `_scan(key=("causedby", id))`. A segment rewritten by a roll-up or a prune has its `.cby`/`.src` removed with it.
   **Old segments are not rewritten:** a segment with no index file, or one that is not whole (wrong length, bad
   header), has both indexes built once, from its blocks, the first time it is asked. They are written beside it
   (tmp, then rename) and kept. When the folder cannot be written, the index is kept in memory and still answers
   (it never fails open to "no match").
2. **The full-scan inventory of `segments.py`:**
   - Indexed now: `caused_by` (was `test=` over every event) and `query(source=...)` (was `test=`; with `n=1` and a
     source that never acted, as `actions/operating.py:91` asks, it read the whole log; `decisions/fromrecord.py:37`
     asks `n=None, source=OWNER`, a full read every time).
   - Bounded already, and left as they are:
     - `last_opening`'s run: `item=` plus a `test=` on `causedby`, bounded by the item's index.
     - `unvoided=True`: one `type="ergostat.forgotten"` read (type index) per call, so it costs as many events as
       `ergostat forget` has written; the rest goes by the item and type indexes.
     - `of_items(ids=/globs=)`: an `item_test`. It tests each segment's header item list, then reads only the
       matching items' rows (or the item column when more than a quarter match), so its cost is the size of its
       answer, bounded by `after_seq`/`limit` where the item index's follow asks.
     - `items`, `item_ids`, `last_times`, `counted`, `times`, `moments`, `_tally` (`opened`, `decided`, `runs`):
       headers and columns only, and an event parsed only for a snapshot's count.
     - `known` and `get(id)` with a full id: Bloom filter, then one `.ids` file.
   - Left unbounded, with the reason:
     - `query(machine=...)`: a source *prefix*, which a hash index cannot answer. Only the Record page and
       `ergostat record --source` ask it, a person's question bounded by its `n` (newest first, so it stops at `n`
       matches) and the page's window (`since`).
     - `get(id)` with a short prefix (under 32 characters): reads every `.ids` file. Only a person typing a short id
       asks it.
     - `query(n=None)` with no filter, `of_items()` with no globs: the whole record because the whole record is
       asked for (export, the item index's first build).
     - `_prunable`, `prune`, `replace`: read every segment's columns (and rewrite the touched ones). This is the
       hourly upkeep, and its answer is every row it touches.
   Proposal: none needed. The measured mix (the routine questions in the cost test below) is served by the format
   with an index beside it.
3. **The dispatcher.** A watchdog pass looks at held leases for at most `SLICE` (0.2 s), and always at least one.
   It remembers which leases this round has looked at (`passed`), and when it is cut short (`behind`) the loop runs
   the next pass at its next look, after a `tick`, not a second later. So the dispatch takes work between slices,
   and a round still reaches every lease. A lease not reached keeps its first look (its `overdue` stamp), so its
   grace is not restarted. `watched` (the engine's first whole read) is set only when a round completes.
4. **The query-cost check.** `Segments.reads` counts the blocks unpacked, the events parsed and the indexes built.
   `test_routine_questions_read_only_what_matches` asks 16 routine questions over 24 segments: `caused_by`, `source`,
   item+type `n=1`, type `n`, `unvoided`, `opened`, `runs`, `last_opening`, `times`, `moments`, `counted`, `known`.
   Each may parse no more events than it answers with and unpack no more blocks than hold them. A new full scan parses
   thousands and fails there.

Acceptance tests, each passing (`tests/test_segments_keyed.py`, `tests/test_lease_watch_slices.py`):
- Done 1: `test_caused_by_on_a_million_events_reads_only_the_segments_holding_it` (marked slow). The record is
  1,000,000 events, 31 sealed segments and a head of 1,000. `caused_by` parses 3 events and unpacks at most 3
  blocks, exactly the same as on a 100,000-event record. "Its time does not grow" is shown by these counts, not by a
  time bound (lesson-10). No timing number is claimed here.
- Done 2: `test_caused_by_and_source_answer_as_the_old_scan_across_the_head_and_a_seal`. The answers match the old
  `test=` scan and SQLite's `caused_by`, for events in the head, across a seal that falls between one run's events,
  and when read by another reader. Also `test_a_shared_hash_is_told_apart_by_the_event` (every value under one hash).
- Done 3: `test_old_segments_with_no_index_still_answer_and_build_it_once`. The index files are deleted and one is
  replaced with a torn file. The answers are the same, the indexes are built once per segment, and a second reader
  builds none. Also `test_an_index_that_cannot_be_written_is_kept_in_memory` and
  `test_a_rewritten_segment_takes_its_index_with_it`.
- Done 4: `test_many_overdue_leases_do_not_delay_a_take`. 120 overdue leases, each look's activity slowed to 50 ms
  (a 6 s pass): a job for another block is taken within 2 s, and the round still reaches all 120. Also
  `test_a_round_cut_into_slices_keeps_each_first_look`.
- Done 5: nothing was measured on the live instance.

Seen to fail with what they guard broken:
- `caused_by` put back to the `test=` scan: the cost test (24,000 parsed), the million test, and the old-segments
  test (nothing built).
- The scan's own field comparison removed: the shared-hash test.
- `.cby`/`.src` left out of `_edit`'s removal: the rewritten-segment test.
- `SLICE` set to 1e9: the take test (taken after 6.3 s).
- Skipped leases counted as looked: the first-look test (1 stamp kept of 6).

Choices made alone (the most reversible):
- Hashed keys, not the values. 64-bit hashes keep the in-memory part at 12 bytes per distinct value per segment;
  collisions cost only a wasted row read. The files sit beside the segments and the record is unchanged, so deleting
  every `.cby`/`.src` returns to the state on main, and they are built again on the next question.
- `source` is indexed too, by the same file kind, since item 2 asks for each fall-through to be indexed or bounded and
  two routine callers ask by source alone. `machine=` (a prefix) is left as said.
- An old segment's first `caused_by` after the upgrade reads that segment's blocks once (as every call did before).
  So the first dispatcher pass after an upgrade on a large old record is slow once. It is not built in the
  background.
- A builder racing a roll-up can leave a `.cby`/`.src` whose segment was just removed. It is never read (its
  segment's unique name is not reused) and only counts toward `size()`. No sweep of such files was added
  (lesson-11).
- The watchdog's slice is 0.2 s, one `LOOK`. Expiry under many overdue leases is therefore later, never earlier.

Not run here: the whole unit suite, the four browser files (no page changed) and demo_check (no example touched): the
factory runs them. Run here, each passing: `tests/test_segments_keyed.py` (7), `tests/test_lease_watch_slices.py` (2),
`tests/test_store_conformance.py`, `tests/test_segments_item_span.py`, `tests/test_lease_gone.py`, `tests/test_leases.py`,
`tests/test_lease_kill.py`, `tests/test_lease_end_turns.py`, `tests/test_leased_workspaces.py`,
`tests/test_resilience.py`, `tests/test_runs_adopted.py`, `tests/test_storage.py`, `tests/test_mirror.py`,
`tests/test_item_numbers.py`, `tests/test_query_spread.py`, `tests/test_query_engine.py`, `tests/test_repair_verify.py`;
ruff clean. Local `main` merged (already up to date). Refused here, as given:
`timeout 900 uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py ...` (the same files were then
run with `named_tests.py` alone), and a `python3 - <<EOF` edit of a source file (done with the editor instead).

### Entry

section: Done recently

- **No routine event-log question reads the whole log**: what a run caused and a query by source are indexed beside
  each segment and in the head (an old segment's index built once), the watchdog looks in 0.2 s slices so overdue
  leases never hold up a take, and a cost test counts what each routine question reads
  (`event-log-indexes-what-it-is-asked`).
