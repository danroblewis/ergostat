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
