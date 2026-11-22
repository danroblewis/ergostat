# item-search-join-1: close gap/item-search, whose two halves have both merged
depends-on: [item-text-search, item-graph-queries]

## Definition of done
Everything in the gap's "Not built" list is already on main. Nothing is rebuilt:
- `ergostat/spec/itemgraph.py` answers near, path and about, with the cap and the error for an unknown id (merged in c5eb54e6).
- The CLI flags `--near`, `--path` (dest `path_to`) and `--about` (dest `about_item`) are in `goodmodel.READ_FLAGS`. They are refused with `--at` and skip the engine's `item ID --json` shortcut.
- `/api/items-query` returns 404 for an unknown id and 400 for a bad depth or a missing `to=`.
- `tests/test_item_graph_queries.py` covers every point in the gap's list.
- SPEC §5a *Graph queries*, the AGENT-GUIDE and the `item` help text describe near, path and about.

What is left, and what done means here:
1. In `docs/GAPS.md`, the `gap/item-search` entry under *Interface* is marked **done** as a whole, no longer "split in two" with nothing said about the parent.
2. The *near, path and about* sub-point names its merge commit `c5eb54e6` in place of "the coordinator fills in the merge commit". The *Search* sub-point names `512f08ef`.
3. No file outside `docs/GAPS.md` and the branch's own definition changes. No code, test, SPEC or guide text changes, because they are already correct.
4. The acceptance tests below pass on the branch as they stand on main, and ruff stays clean.

## Relation to other work
- item-graph-queries (merged): built everything this gap lists; this branch only records it as done.
- item-text-search (merged): the search half of gap/item-search; its merge commit is named in the entry.

## Files to touch
- `docs/GAPS.md`

## Risks
- lesson-8: the entry could claim more than main has (MCP, `--at`, the Items page box). The edit keeps the existing "Not the Items page's own box, not MCP, not `--at`" limits word for word, and the tests below check every claim the entry makes.
- lesson-13: if a suite fails on something unrelated, the branch reports it and does not fix it, because the branch changes no code.

## Acceptance tests
- `tests/test_item_graph_queries.py::test_near_by_depth_both_directions`: near is answered at each depth, links walked both ways, each item with its distance and relation.
- `tests/test_item_graph_queries.py::test_path_names_inverse_steps`: a backward step is named by its inverse.
- `tests/test_item_graph_queries.py::test_path_capped_is_not_unconnected`: a capped path says "none within the cap", not "no path".
- `tests/test_item_graph_queries.py::test_about_declared_and_inferred_whole_token`: declared links vs. whole-token inferred mentions (`ticket/1` does not match `ticket/12`).
- `tests/test_item_graph_queries.py::test_unknown_id_is_an_error`: an unknown id gives exit 2 / HTTP 404, never an empty answer.
- `tests/test_item_graph_queries.py::test_the_queries_with_at_or_a_bad_depth_are_refused`: the queries are refused with `--at` or a bad depth.
- `tests/test_item_graph_queries.py::test_queries_under_fallback_and_engine`: READ_FLAGS classification, no `about` dest, the last-good fallback, and the engine shortcut skipped for all three flags.
- `tests/test_item_graph_queries.py::test_cli_and_api_agree`: the CLI's `--json` and `/api/items-query` give the same answer.

## Size budget
0 net lines
size: S (confidence: high)
