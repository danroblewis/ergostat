# a-kind-chosen-in-a-snapshot: a snapshot holds the Items page's answers for each kind chosen alone (its list, its list in each of its states, and its Graph), so choosing a kind or a state in a snapshot shows what the live page shows
depends-on: []

The gap (`docs/GAPS.md`, *A kind chosen in a snapshot*). When a kind is chosen in a snapshot, `pageItems` (`ergostat/web/static/pages.js`) asks for `items` with `kind` (and `state` when a chart's state is clicked). `ergostat/web/snapshot.py` holds only the `items` request with no kind chosen. So the page says "`items: not in this snapshot`". The Graph and Timeline it would then ask for (`items-graph?kinds=K`) are held only for kinds that have relations. A kind without relations (`note` in `related_project`) chosen in the Graph view is not held either. On main already, not to be rebuilt: `snapshot.key` and the page's `snapKey`, which agree; `_graphs`, for each system's related kinds together and each alone; and the search, which a snapshot filters on the page.

## Definition of done

1. For every kind in the snapshot's own `items` answer (its `kinds` list), the snapshot holds:
   - `items?kind=K`;
   - `items?kind=K&state=S` for each state `S` of that kind;
   - `items-graph?kinds=K`, whether or not the kind has relations.

   Each is under the key the page's `snapKey` makes for the request it actually sends in a snapshot, with no `per_kind`, `shown` or `q`. Each holds what the live server answers to that request.
2. Opened from its file, a snapshot with a kind chosen (`#/items?kind=K`) shows that kind's items and no "not in this snapshot". Clicking one of the kind's states shows only the items in that state. The Graph and the Timeline with the kind chosen draw from `items-graph?kinds=K`.
3. If one of these answers cannot be got, it is left out, not stored as an empty list. The page then says "not in this snapshot" for it and does not show the kind as having no items (lesson-3). The rest of the snapshot is still written.
4. Still not held, and said so: a set (`where`, `moved`, a process map's `through`/`followed`/`caused`) chosen in a snapshot. SPEC §5a's sentence on what a snapshot holds says exactly what is held now, and names sets as not held. The GAPS entry is marked done on this branch, and sets are recorded as what is left (in that entry or in a new open one).
5. The existing `tests/test_graph_cli_web.py::test_a_snapshot_holds_the_items_graph_the_page_asks_for` checks the exact set of `items-graph` keys. It is updated to the new set, adding `items-graph?kinds=note`, and still passes. `tests/test_items_page.py::test_a_snapshot_draws_the_graph_and_timeline` still passes.

## Files to touch

- `ergostat/web/snapshot.py`
- `docs/SPEC.md` (§5a, the snapshot sentence), `docs/GAPS.md`
- `tests/test_graph_cli_web.py`, `tests/test_items_page.py`
- `ergostat/web/static/pages.js` only if the page's requests in a snapshot turn out not to match the keys in point 1. If it is touched, say why in the report.

## Risks

- lesson-3: an answer that cannot be got (or a kind built by filtering the no-kind list, which is cut at its newest per kind) stored as empty or short, so the page shows "no items" instead of "not in this snapshot".
- lesson-8: SPEC saying a snapshot holds "what the page asks for" while a chosen set is still not held.
- lesson-9: tests that open only the no-kind page, which passes on main. Each new test must fail on main as it is (say so in the report).

## Acceptance tests

- `tests/test_graph_cli_web.py::test_a_snapshot_holds_each_kind_chosen_and_each_of_its_states`: built from `related_project`, the snapshot holds every key in point 1 for `epic`, `goal`, `ticket` and `note`.
  - `items?kind=ticket` lists exactly `ticket/a` and `ticket/b`.
  - `items?kind=ticket&state=active` lists exactly `ticket/a`.
  - `items-graph?kinds=note` holds `note/n`.
  - Each held answer equals the live `api` answer to the same request.
  - Fails on main: the keys are missing.
- `tests/test_graph_cli_web.py::test_a_kind_whose_list_cannot_be_answered_is_left_out_of_the_snapshot`: with the server's answer to `items` with `kind=ticket` made to raise (monkeypatched), the key is absent, not empty. The other kinds' keys and the no-kind `items` are still held. Fails if a failure is stored as empty or built from the no-kind list.
- `tests/test_items_page.py::test_a_snapshot_lets_a_kind_and_its_state_be_chosen` (browser): the snapshot of `related_project` opened from its file.
  - `#/items?kind=ticket` lists `ticket/a` and `ticket/b` and not `epic/e1`.
  - Clicking the `active` state leaves `ticket/a` alone.
  - `#/items?kind=ticket&view=graph` draws `.rg-graph[data-drawn]` with `ticket/a` and `ticket/b`.
  - `#/items?kind=note&view=graph` shows no error.
  - The page text never holds "not in this snapshot", and there are no page errors.
  - Fails on main with "items: not in this snapshot".

## Size budget

30 net lines (in `ergostat/web/snapshot.py`; 0 in `pages.js` unless point "Files to touch" applies).

## Notes from the plan review (answer each)

- Say where each kind's states come from (the kind's own answer, not the no-kind list, which is cut at its newest per kind); a state missed there is a silent short snapshot (lesson-3).
- Say whether `items?kind=K` is held only as its first page (shown/per_kind dropped) and what 'show more' does in a snapshot; the claim 'holds what the live server answers' must match that.
- Extend the left-out test to a failing `items-graph?kinds=K` and a failing `items?kind=K&state=S`: each key absent, not empty, and the rest of the snapshot still written.
- In the browser test, `#/items?kind=note&view=graph` must assert `.rg-graph[data-drawn]` contains `note/n`, not only 'no error', which passes if nothing is drawn.
- Point 2 claims the Timeline with a kind chosen draws from the snapshot; add a browser assertion for the Timeline view with `kind=ticket`.
- Lesson-8: back the SPEC sentence that sets are not held with a test (a set chosen in a snapshot says 'not in this snapshot' rather than showing wrong items), or narrow the sentence.
