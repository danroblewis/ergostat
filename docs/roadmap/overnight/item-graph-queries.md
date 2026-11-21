# item-graph-queries: the items near an item, the path between two, and what is about one
depends-on: [item-text-search]

## Definition of done
1. A small module, `ergostat/spec/itemgraph.py`, answers three queries from the item index's links (both directions) and its text:
   - **near ID [depth]**: the items within `depth` relation hops (default 1, at most 4; a larger depth is refused), each with its distance and the relation it was reached by.
   - **path A B**: a shortest chain of relations between the two items, walked either way. A step walked backward is named by its inverse (`blocks`, `children`).
   - **about ID**: the items that link to the item by a declared relation (marked `declared`), plus the items whose fields mention its id as a whole token (marked `inferred`, so `ticket/1` never matches `ticket/12`).
2. Bounds (lesson-4): each query visits at most a fixed number of items (a constant of the module, about 2,000), and reports `capped` when it hits that limit. A path search that stops at the cap says "none within the cap", never "not connected". An unknown id is an error (exit 2 or HTTP 404), never an empty answer.
3. CLI: `ergostat item ID --near [N]`, `ergostat item A --path B`, `ergostat item ID --about`, each with `--json`. These flags skip the running engine's shortcut for `item ID --json`. None of them is stored under the argument name `about`, which `goodmodel.ACTS` reserves for messages. All three are classified as read flags in `goodmodel.READ_FLAGS`. With `--at`, they are refused.
4. API: `GET /api/items-query?near=ID&depth=N`, `?path=A&to=B`, `?about=ID`, returning the same JSON as the CLI.
5. SPEC §5a, AGENT-GUIDE, the `item` help text and the GAPS.md entry for gap/item-search say what each query returns and its bounds. The entry is marked done.

## Files to touch
`ergostat/spec/itemgraph.py` (new), `ergostat/spec/itemindex.py` (if a whole-token mention lookup is needed), `ergostat/cli/__init__.py`, `ergostat/cli/record.py`, `ergostat/goodmodel.py`, `ergostat/web/server.py`, `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`, `tests/test_item_graph_queries.py`

## Risks
- lesson-7: `--about` stored under the name `about` would be taken for the messages' acting flag, so the last-good fallback would refuse it; and the `item ID --json` shortcut would answer with the plain item.
- lesson-4: depth or a dense graph turns a walk into a full scan of a large record; depth and items visited need hard limits.
- lesson-3 and lesson-8: an unknown id, or a capped search, is reported as "nothing near" or "no path".

## Acceptance tests
- `tests/test_item_graph_queries.py::test_near_by_depth_both_directions`: on a chain epic←ticket/1→ticket/2 (`parent`, `blocked_by`), depth 1 and depth 2 give exactly the expected items and distances. Depth 5 is refused.
- `tests/test_item_graph_queries.py::test_path_names_inverse_steps`: the path from ticket/2 to the epic lists its steps, with the backward step named `blocks`.
- `tests/test_item_graph_queries.py::test_path_capped_is_not_unconnected` (lesson-3/8): with the visit cap monkeypatched to 2 on a longer chain, the answer is `capped`, not "no path"; two truly separate items give "no path" without `capped`.
- `tests/test_item_graph_queries.py::test_about_declared_and_inferred_whole_token`: a related item is marked `declared`, a mention in a field is marked `inferred`, and ticket/12's text does not count as about ticket/1.
- `tests/test_item_graph_queries.py::test_unknown_id_is_an_error`: CLI exits 2 and the API returns 404 for every query.
- `tests/test_item_graph_queries.py::test_queries_under_fallback_and_engine` (lesson-7): with a broken model, `item ID --about` answers from the last good model. With a running engine stubbed into `fast.call`, `item ID --near --json` gives the near answer, not the plain item.
- `tests/test_item_graph_queries.py::test_cli_and_api_agree`: the JSON from `--near`, `--path` and `--about` equals `/api/items-query`'s.

## Size budget
170 net lines

## Notes from the plan review (answer each)

- Definition 5 marks the GAPS.md entry for gap/item-search done, but this gap is gap/item-graph-queries. Built as written, it closes another gap's entry and leaves this one open. Name the right entry.
- lesson-4/8: add a test that lowers the visit cap so near (dense star) and about (many mentions) both report capped; only path's cap is tested now.
- lesson-7: run the fallback and engine-shortcut test for all three flags (--near, --path, --about, with --json), and assert each is in goodmodel.READ_FLAGS and none is stored as 'about'.
- Add a test that --near/--path/--about with --at is refused, and state the exit code.
- Say what a backward step is called for relations other than blocked_by and parent, and whether the inverse names are an allowlist.
- lesson-8: test 'shortest' on a graph with two routes of different lengths.
- A depth outside 1-4 or not a number, and a missing to= on the API, give exit 2 or HTTP 400, never a default depth.
- If the frontier runs out exactly at the cap, the answer is 'no path', not capped; say which and test it.
- lesson-9: the report says which code was broken to make each acceptance test fail.
- lesson-7: merge origin/main into the branch and run the suites again before calling it built.

## Where it stopped

Built, round 1. Points 1 to 5 are done; the factory's watched unit and browser suites are still to run.

**The dependency is not on main.** gap/item-text-search dead-lettered: main's item index has no text column and no
`--search`. Rather than build it here, which would be out of scope, `about`'s inferred part reads the items' fields
itself, a page of 500 at a time, newest first, and stops at the cap (`itemgraph.about`). This is the most reversible
choice: once the text index lands, that scan can become an index lookup and the answer keeps the same shape.
`itemindex.py` is not touched.

**Size: about 202 net lines against 170.** That is `itemgraph.py` at 144 lines (about 30 of them docstring) plus 58 in
the CLI, server and goodmodel. The overrun is the mention scan the missing text index would otherwise have provided
(about 20 lines), the API's refusal of `at=` (the CLI's `--at` is refused per point 3, and the API is refused the same
way so the two cannot disagree), and the plain-text printing of the three answers.

**Answers to the plan review:**
- GAPS.md: the new entry is **gap/item-graph-queries** under *Interface*, marked done on the branch. GAPS.md has no
  gap/item-search entry to close.
- Cap on near (a dense star) and on about (many mentions): `test_near_and_about_report_capped`.
- lesson-7: `test_queries_under_fallback_and_engine` runs all three flags with `--json`, both with `fast.call` stubbed to
  return a plain item and under a broken model with the last good one kept. It also checks that each flag's dest
  (`near`, `path_to`, `about_item`) is in `READ_FLAGS`, is not in `ACTS` and is not `about`.
- `--at`: refused with exit 2 (`test_the_queries_with_at_or_a_bad_depth_are_refused`). `at=` on the API gives 400
  (`test_unknown_id_is_an_error`).
- Backward step names: the kind's declared `inverse:`, else `relations.inverse_of` (`blocks`, `before`, `dependents`,
  `children`, `duplicated_by`, `related_from`, otherwise `NAME_of`). Any relation may be walked; the names are not an
  allowlist (SPEC §5a *Graph queries*).
- Shortest of two routes: `test_path_is_the_shortest_of_two_routes`.
- Depth 0, 5, `x`, `-1` or empty, and a missing `to=`: `Bad`, which gives exit 2 or 400, never a default. Only an
  absent depth means 1 (the API's `parse_qs` drops an empty `depth=`).
- A frontier that runs out exactly at the cap gives `no path`, not capped: `test_a_frontier_running_out_exactly_at_the_cap_is_no_path`.
- lesson-9, the code broken to make each test fail (each break was run, then reverted):
  - The backward step named by its own relation instead of the inverse fails near_by_depth and path_names_inverse_steps.
  - The whole-token lookahead dropped fails about_declared_and_inferred_whole_token.
  - The cap returning `capped=False` fails path_capped_is_not_unconnected and near_and_about_report_capped.
  - `capped` also set when `seen` fills exactly to the cap fails frontier_running_out_exactly_at_the_cap.
  - The graph flags handled after the engine's `item ID --json` shortcut fails queries_under_fallback_and_engine.
  - Not returning when the goal is first reached (so a later, longer route overwrites it) fails path_is_the_shortest.
  - The API answering `{}` for an unknown id fails unknown_id_is_an_error.
  - The API ignoring `depth=` fails cli_and_api_agree and unknown_id_is_an_error.
- Merging main: this container has no `origin` remote, and local `main` (a0dc0ec9) is the branch's base, so there was
  nothing to merge. The coordinator should merge the real origin/main and run the suites again.

**Not bounded:** `about` reads the declared links to the item with one indexed query (`links_to`) and no limit; if
there are more than the cap, the answer keeps the first 2,000 and says `capped`.

**Run here:** tests/test_item_graph_queries.py (11), test_cli_fallback.py, test_relations.py and
test_graph_cli_web.py: 75 passed. Ruff is clean. Not run: the full unit suite and the four browser files, which the
factory runs under the watchdog.

## Where it stopped, round 2

Built, round 2. Main (31cffd8f) is merged in. The conflicts in `docs/GAPS.md`, `ergostat/cli/__init__.py`,
`ergostat/cli/record.py` and `ergostat/goodmodel.py` were resolved by keeping both sides: `READ_FLAGS` has `search`
and the three graph flags, the `item` help line names `--search` and the queries, and `cmd_item` refuses `--search`
with NAME before it hands the graph flags to `_item_graph`.

**Size overrun, with its reason: 194 net lines of core code against a budget of 170 (24 over).** That is
`itemgraph.py` at 137 (14 of them the module docstring, 6 more other docstrings), plus 57 in `cli/record.py` (34),
`cli/__init__.py` (7), `web/server.py` (16) and `goodmodel.py` (0 net), as measured by `git diff --numstat main --
ergostat`. The overrun comes from three things the budget did not count: the plain-text printing of the three answers
(about 12 lines), the API's refusal of `at=`, which keeps it in step with the CLI's refused `--at` (about 4), and the
docstrings that state each query's bounds, as lesson-8 asks (about 20). Round 1's scan of every item's fields is gone,
which makes the code 8 lines shorter than round 1's 202.

**Round 1's review findings, every one (lesson-12):**
- *Size with no reason written* (blocking): the reason is the paragraph above.
- *The dependency is now on main, so GAPS.md's "Left" would be false*: the GAPS.md entry is now a sub-bullet of main's
  gap/item-search entry, marked **done**. `itemgraph.about` now asks the item index's text (`ix.items(words=(id,))`,
  from gap/item-text-search) for the items that hold the id at all, at most `VISIT + 1` of them. It then checks the
  whole token against their fields. A mention past the index's first `TEXT_MOST` characters is not found (stated in
  the module docstring). Breaking the lookup (searching a word no item holds) fails
  `about_declared_and_inferred_whole_token` and `near_and_about_report_capped`.
- *lesson-4, links read are not bounded by a constant*: unchanged. The cap is on items visited, so the links read are
  bounded only by the links of at most `VISIT` items. Capping the links too would need a limit argument on
  `itemindex.links_from`/`links_to`, which this gap does not need to touch. This is stated here, not claimed as
  bounded.
- *`_index` with no index on disk gave 404*: it now raises `Bad`, so the CLI exits 2 and the API answers 400. An unknown
  item is still `Unknown`, which gives 404.
- *Other item flags silently ignored*: `--history` with `--near`, `--path` or `--about` is now refused with exit 2
  (asserted in `test_the_queries_with_at_or_a_bad_depth_are_refused`). `--search` with an item id was already refused
  by main's check, which runs first.
- *Merge main and run again (lesson-7)*: the merge is done (fc60cb6c), and the suites below were run after it.

**Run here, after the merge:** tests/test_item_graph_queries.py (11), test_cli_fallback.py, test_relations.py and
test_graph_cli_web.py: 77 passed together. tests/test_item_search.py: 8 passed. Ruff is clean. Not run: the full unit
suite and the four browser files, which the factory runs under the watchdog.
