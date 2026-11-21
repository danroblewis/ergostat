# relations-as-of: the Items page's Graph and Timeline at a moment travelled to, and in a snapshot
depends-on: []

## The gap

`GET /api/items-graph` (`ergostat/web/relations_api.py` → `precedence.build`) reads the item index as it stands
now, even when the page has travelled to a past moment. The cache key in `relations_api.graph` already separates
moments (`live or snap["at"]`), but `build` ignores the moment. SPEC §5a, *Relations*, says this
(docs/SPEC.md:821, "Relations are read as they stand now ...") and GAPS.md lists it under "Relations, what is
left". `ergostat snapshot` (`web/snapshot.py::_requests`) does not ask for `items-graph` at all, so a snapshot's
Graph and Timeline say "not in this snapshot". This branch closes both. It does not touch Jira's links, which are
the other half of that GAPS entry and gap/ticket-factory-jira-links.

## Definition of done

1. **`precedence.build(events, spec, kinds, now, since, ix=None, until=None)`.** With `until=None`, the code path
   and the answer are as on main: no as-of view is built (test 7). With `until` given, every read `build` makes of
   the index goes through a view of the index as it stood at `until`, a new module `ergostat/spec/asof.py`
   (class `AsOf`). The view has the same methods `build` and `Kinds` call: `lock`, `items(kind, states, n=, ids=)`,
   `count`, `links_from`, `links_to`, `left`, `stays`. A moment includes events with `time <= until`, the same
   boundary as `EventStore.query(until=)` and `ItemIndex.late` (`newest > until`). An event exactly at `until`
   counts as before it.
2. **The per-item mode** is used when few items changed since `until`. Each `AsOf` read:
   (a) reads the index's rows (`ix.items(..., until=until)`, `ix.links_from`, `ix.links_to`);
   (b) calls `self._between(op)`, a no-op named step (`op` in `"items"`, `"links_from"`, `"links_to"`), so a test
   can put a competing write in the gap;
   (c) reads the late set again (`ix.late(until, limit=cap + 1)`). The ids in it are kept in `late_ids` (a set,
   including ids with no event by `until`). Ids not seen before are folded from `events.query(item=id,
   until=until, skip=(TRANSCRIPT_TYPES,))`; an id with no events by then is absent at that moment, not an empty
   item;
   (d) merges. Every row, and every link whose source is in `late_ids`, is dropped. The folded late items that
   match the read are added: for `items`, those of the kind, states or ids asked, sorted by `last` descending and
   cut to `n`. For `links_from`, `relations.links_of(kind, folded.fields)` for the late ids asked. For `links_to`,
   every folded late item's links that name an asked id.

   Order matters. Rows are read first and the late set after (lesson-1). Any item a writer changes after the rows
   were read is then in the late set and replaces its row, whatever another process writes into the index file
   meanwhile. The docstring of `AsOf` says so. `ix.lock` is held across the whole build, as now. That covers this
   process's threads; the order covers other processes.
3. **The whole mode.** The view is built with `cap = max(50, ix.total() // 10)`, the rule
   `spec/items.py::_late` uses, taken from one shared function rather than copied. When the first late read holds
   more than `cap` ids, the view folds every item of the record up to `until`, through the existing fold path in
   `spec/items.py::project`'s fallback, extracted as `fold_all(events, spec, kind, until, transcript)` with
   `project` calling it. From then on it answers `items`, `count`, `links_from` and `links_to` from memory: links by
   `links_of` on each item's folded fields. It makes no `ix.items`, `ix.count`, `ix.links_from` or `ix.links_to`
   call after that. If a later read in per-item mode finds the late set past `cap`, the view switches to the whole
   mode for the rest of the build. The build is not restarted: every earlier answer was already as of `until`.
4. **Items of no kind.** An item of no kind (its id matches no kind's glob), or of a kind with no relations, has no
   links (`links_of(None, …) == []`). It may still appear as an item another item's relation names, with
   `kind: None` and a status, and the rest of the answer is given. There is no exception.
5. **Durations as of then.** `ItemIndex.stays(kind, most, finished, until=None)`: with `until`, only moves with
   `m.t <= until` count. The candidate items are the `most` latest with `first <= until`. An item counts as
   finished for the visit weights when its last move by `until` is into a finished state, not by its state now.
   With `until=None` it behaves as on main. `AsOf.stays` passes `until`. `AsOf.left` delegates to `ix.left`
   unchanged: a kind's finished states are judged from the record now, and SPEC says so.
6. **The web.** `relations_api.graph` passes `until=None` when `live`, else `until=snap["at"]`.
   `server._estimates` stays as it is: no completion estimates at a moment travelled to, and SPEC says so.
7. **The snapshot.** `web/snapshot.py::build` adds the `items-graph` answers the Items page would ask for, keyed
   with `key()` exactly as `snapKey` in `static/util.js` keys them. For each group in the `items` answer's
   `systems` (`spec/items.py::listing`), it adds `{kinds: the group's kinds that have relations or are named by
   one, joined by ","}` when that list is non-empty, as `pages.js` builds `want` with no kind chosen. It also adds
   `{kinds: K}` for each such kind K (a kind chosen). An answer that raises is left out, as for every other request.
8. **Docs.** docs/SPEC.md:821 is rewritten. It says the Graph and Timeline at a moment travelled to show items,
   their states, segments and links as they stood then, and that a snapshot holds them. It says what stays of now:
   a kind's finished states, the completion estimates (none at a moment), and the status's list of relation cycles
   (`state.relation_cycles`, unchanged). The GAPS.md "Relations, what is left" entry loses its first clause and
   keeps the Jira half. The `ergostat snapshot` help text or docs mention the Graph where they list what a
   snapshot holds, if they list it.
9. Done also means everything in the house rules: the unit suite and the four browser files pass with rc 0 and no
   page test skipped for want of a port; ruff is clean; origin/main is merged in and the suites run again. Each new
   test is broken on purpose once, and the report says how and that it failed.

## Files to touch

- `ergostat/spec/asof.py` (new)
- `ergostat/precedence.py` (`build`'s `until`, the view built when it is given)
- `ergostat/spec/itemindex.py` (`stays(..., until=None)`)
- `ergostat/spec/items.py` (`fold_all` extracted from `project`; the late cap as one function shared with `asof`)
- `ergostat/web/relations_api.py`
- `ergostat/web/snapshot.py`
- `docs/SPEC.md`, `docs/GAPS.md`
- `tests/test_relations_asof.py` (new), `tests/test_graph_cli_web.py`, `tests/test_items_page.py`

## Risks

- **lesson-1.** Each read of the index's rows and the later late-set read are separate SQL statements. Another
  process's catch-up can fold an event after `until` for item b between them. If the late set were read first, b
  would leave the rows (its `newest > until`) without being in the late set, so it would vanish, or its current
  links would leak into the past. The order (rows, then late) and the merge rule (anything in `late_ids` replaces
  its rows and links) are what prevent it. Test 2 puts the write in the gap for each of the three reads.
- **lesson-2.** The boundary at `until` must be the same everywhere: rows `newest <= until`, late `newest > until`,
  refold `time <= until`. An event stamped exactly `until` that lands on different sides in different reads gives
  an item that is both a row and late, or neither. Test 1 has an event exactly at `until`. No ordering by time is
  added: within an item, the fold keeps the record's order.
- **lesson-3.** Inputs that can be missing:
  - No index: the existing `note`, unchanged.
  - A late id with no events by `until`: the item is absent. It is not an empty item, and its index row is not
    kept: test 1 has an item created after `until`.
  - An item of no kind: no links, and the rest answered (test 4, both modes).
  - A whole-mode fold, or a refold query, that raises: the error propagates. The web answer fails; it does not
    give an empty graph.
  - A snapshot request that fails: left out, so the page says "not in this snapshot", which is honest.
- **lesson-4.** Refolds in per-item mode are bounded by `cap`, and the whole mode takes over past it. The whole
  mode reads the record up to `until`, as `items.project` already does for a long-past moment. No processes,
  threads or calls multiply. The snapshot adds one request per group plus one per related kind, bounded by the
  model's kinds.
- **lesson-5.** An item made again under the same id after `until` must show its earlier self. The refold reads
  only events by `until`. Folded late items are kept per view (per build), never in a module-level cache. The web
  cache key already includes the record's `seq` and the moment. Test 1 remakes an id after `until`.
- **lesson-8.** SPEC says "as they stood then". A kind's finished states (`left`) and the status page's cycles stay
  of now, and estimates are absent at a moment: all three are stated in SPEC, not claimed. The `AsOf` docstring
  claims correctness under a concurrent writer only in the sense test 2 checks.
- **lesson-9.** A whole-mode test where both runs use the per-item path would agree trivially, so test 3 makes the
  index reads raise in the whole run, and checks that the per-item run had a non-empty late set. A race test where
  the reads are swapped must fail (test 2; the report shows it). An as-of test that would pass with `until`
  ignored is ruled out: test 1 asserts the answer differs from `until=None`.
- **lesson-7, lesson-13.** Merge origin/main and run the suites again. A failure in an unrelated test is named in
  the report, not fixed here.

## Acceptance tests

All in `tests/test_relations_asof.py` unless named otherwise. The record is built with `p.events.add(..., at=)`
around a fixed `until`.

1. **`test_the_graph_at_a_moment_shows_items_and_links_as_they_stood`**
   - Before `until`: tickets a and b, with b `blocked_by: a` and `parent: epic/e`, and the epic e. a is started at
     exactly `until`.
   - After `until`: b's `blocked_by` is set to `[c]` (c is created after `until`); a is done; a new ticket d,
     `blocked_by: a`, is created; ticket x, which existed before `until`, is remade under its id with new fields.
   - `build(..., now=until, since=..., until=until)` shows: a in `doing` (the event at `until` counts); b `blocked`,
     with links `{blocked_by: [a], parent: [e]}`; a's `inverse` holds `blocks: [b]`; no c and no d; x with its
     fields before `until`; every segment ending by `until`.
   - The same through `relations_api.graph(p, m, {"at": until, "window": …}, q)`.
   - The same build with `until=None` differs: b `blocked_by: [c]`, a done.
   - Fails if `until` is ignored, if the boundary is `<`, or if the remade x shows its new fields.
2. **`test_a_change_in_the_gap_between_the_index_read_and_the_late_read_is_seen[items|links_from|links_to]`**
   - Monkeypatches `AsOf._between` so that, the first time it is called with the parametrized `op`, it adds an
     event for b at `until + 10` that sets b's `blocked_by` to `[c]`, then calls `ix.catch_up(p.events)`. It then
     asserts b's index row now has `newest > until` (`b in ix.late(until)`).
   - The answer still has b, in its state at `until`, with `blocked_by: [a]`, and a's `inverse.blocks == [b]`. The
     parameters cover the `links_to` read as well as `items` and `links_from`.
   - The report states that with the reads in `AsOf` swapped (late read before the rows) this test fails for each
     parameter, and how.
3. **`test_the_whole_fold_when_most_items_changed_agrees_with_the_per_item_read`**
   - A record where several items, including linked ones, changed after `until`.
   - Run 1, per-item: the late cap is forced high. Assert the view was in per-item mode with a non-empty set of
     refolded items.
   - Run 2, whole mode: the late cap is forced to 0 by monkeypatching the shared cap function, and `ix.items`,
     `ix.count`, `ix.links_from` and `ix.links_to` are monkeypatched to raise `AssertionError` after the first late
     read. The run completes, which shows the whole mode ran for every call.
   - Both answers are equal, field for field (items, links, edges, statuses, segments, critical).
4. **`test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers[per_item|whole]`**
   - `misc/1`, whose id matches no kind, holds `blocked_by: ticket/a` and changes after `until`. Ticket a has
     `blocked_by: misc/1`.
   - The answer has `misc/1` as an item with `kind: None`, no `links` and no `inverse` from it. Ticket a has its
     link to `misc/1` and is `blocked` with `waiting == ["misc/1"]`. The other tickets are answered. Nothing
     raises.
   - Fails if a kindless item raises (`kind.relations`), or is given links read off its fields.
5. **`test_stays_at_a_moment_count_only_the_moves_by_then`**
   - Several tickets of one kind finish `doing` in 100 s before `until`, and in 1000 s after it.
   - `ix.stays("ticket", until=until)` medians and visit weights use only the first group. A ticket now finished
     that was still in `doing` at `until` counts as unfinished for the weights.
   - `stays()` with no `until` is unchanged (the existing tests in `tests/test_relations.py` still pass).
6. **`tests/test_graph_cli_web.py::test_a_snapshot_holds_the_items_graph_the_page_asks_for`**
   - A model with related kinds, in two systems. The snapshot's data holds `key("items-graph", {"kinds": …})` for
     each group's related kinds and for each related kind alone, each with its items.
   - The keys are computed from the snapshot's own `items` answer, the way `pages.js` does.
7. **`test_the_graph_now_does_not_build_a_view`**
   - Monkeypatch `asof.AsOf.__init__` to raise. `relations_api.graph` with `snap["at"] = time.time()` (live)
     answers as before, and `build(..., until=None)` answers as before.
   - Fails if the live path pays for the view.
8. **`tests/test_items_page.py::test_a_snapshot_draws_the_graph_and_timeline`** (browser)
   - The snapshot of a model with relations, opened from its file. The Graph view draws the related items, and
     the Timeline their bars. No "not in this snapshot" error appears.
   - Fails if the snapshot's keys differ from `snapKey`'s.

For each risk: lesson-1 → test 2; lesson-2 → test 1 (the event at `until`); lesson-3 → tests 1 (created after
`until`) and 4; lesson-5 → test 1 (x remade); lesson-9 → tests 2 (swapped), 3 (index raises) and 1 (differs
from now); lesson-8 → the SPEC sentences each map to tests 1, 5 and 6/8, and what stays of now is said, not
claimed.

## Size budget

230 net lines of code outside `tests/` and `docs/`: `asof.py` about 130, `precedence.py` about 10,
`itemindex.stays` about 20, `items.py` about 10 (an extraction, mostly moved), `relations_api.py` about 5,
`snapshot.py` about 25, plus margin. An overrun needs a written reason.

## Notes from the plan review (answer each)

- `count` is in AsOf's method list but item 2 defines no per-item rule for it. Specify it: rows counted with newest <= until, read before the late set, minus the counted rows whose ids are in late_ids, plus the folded late items that match. Cover it in test 1 or test 3, or count will be wrong at a moment without any test failing.
- Whole mode: `fold_all(events, spec, kind, until, transcript)` folds one kind at a time, but test 4[whole] needs `misc/1`, which has no kind, folded with a status. Say how the whole mode folds items of no kind (for example kind=None means every item) and what status an id named by a relation but absent at `until` gets.
- Test 2 calls `ix.catch_up` from `_between` while the build holds `ix.lock`. If that lock is not reentrant, or catch_up takes it, the test deadlocks. It also does not model 'another process'. Do the competing write through a second ItemIndex opened on the same file.
- lesson-4: `cap = max(50, total//10)` has a floor and no ceiling, so per-item mode can make up to `cap` per-id event queries. Either add a hard ceiling to the shared cap function, past which the whole mode takes over, or say in Risks why `cap` queries never cost more than the whole fold.
- Item 5: say what 'the `most` latest with `first <= until`' are ordered by (first? last move by until?) and on which side of `until` it falls. A move exactly at `until` counts, as everywhere else.
- Test 6 works out the expected keys in Python, so it checks the snapshot against a Python copy of the rule, not against what pages.js and snapKey do. Test 8 is the real check of the keys. Make sure it covers a model with two systems, and a kind chosen as well as no kind chosen.
