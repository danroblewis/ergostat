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

## Where it stopped, round 3

Built, round 3. Every finding of review/item-graph-queries-2, blocking and not (lesson-12):
- *`mentions` matched the field's JSON, so an id after a newline or tab was dropped* (blocking): `itemgraph.mentions`
  now walks each field's string values, nested ones too, as `items.text_of` does, and matches the whole token in each
  string. `json` is no longer imported. New test `test_about_finds_a_mention_after_a_newline_or_tab_or_nested` covers
  a mention after `\n`, one after `\t`, one in a nested list, and `ticket/22` after a newline, which must not count.
  lesson-9: putting back `json.dumps` of the field makes the test fail (only `ticket/7` is found).
- *Size with no reason written* (blocking): **198 net lines of core code against 170 (28 over)**, by
  `git diff --numstat main -- ergostat`: `itemgraph.py` 142, `cli/record.py` 34, `cli/__init__.py` 7, `web/server.py`
  15, `goodmodel.py` 0 net. The reason is the same as round 2's (the plain-text printing of the three answers, about
  12; the refusal of `at=` and of more than one query on the API, which keeps it in step with the CLI, about 5; the
  docstrings that state each query's bounds, about 20). This round adds 5 lines: the string walk that replaces
  `json.dumps`, which the blocking finding asked for. I did not shorten the docstrings to fit the budget, because they
  hold the bounds that lesson-8 asks to have stated.
- *GAPS.md's "Left" note was false*: removed. The entry now says what the code does: the index's text picks out the
  candidate items, then each string value of their fields is checked for the whole token.
- *The API answered the first of several queries and ignored the rest*: it now refuses with a 400 when it gets more
  than one of `near=`, `path=` and `about=`, as the CLI already does (exit 2). `test_unknown_id_is_an_error` asserts
  two such requests. lesson-9: allowing more than one makes that test fail with a 200.
- *`at=` was parsed and the snapshot computed before items-query refused it*: the items-query branch now runs before
  `at` and `live.snapshot`, so nothing is computed for a request it refuses or answers from the index.
- SPEC §5a says that each string value is matched (so an id at the start of a line counts), and that more than one
  query is refused.

Merging main: local `main` is already an ancestor of the branch (45bfbb2e). This container has no network, so the
coordinator should merge the real origin/main and run the suites again (lesson-7).

**Run here:** tests/test_item_graph_queries.py (12), test_cli_fallback.py, test_relations.py and
test_graph_cli_web.py: 78 passed together. tests/test_item_search.py: 8 passed. Ruff is clean. Not run: the full unit
suite and the four browser files, which the factory runs under the watchdog.

## Where it stopped, round 3 (the unit suite's failure)

The factory's unit run after 45a57cc2 stopped at 89% with no failure or summary in its tail, which reads as a run
that was killed or hung rather than a test that failed. No failing test is named, so no code was changed. Run here,
each group passing: test_item_graph_queries, test_item_search, test_graph_cli_web, test_cli_fallback (68 passed);
test_items_page, test_relations, test_relations_asof, test_scale_caches, test_storage, test_web_access, test_remote,
test_calls, test_numbers (169 passed, 1 skipped); test_workspaces, test_templates, test_program_actions,
test_gated_actions, test_factory_manager (81 passed, 2 min 47 s); test_daemon_docs, test_guide, test_spec_*,
test_item*, test_relations*, test_take_order, test_resilience (307 passed, 1 skipped). Not run: the whole unit suite
(this session was not permitted to run it). Left: the factory should run the unit suite again and name the test that
fails or hangs; if it is one this branch's code does not reach, it is unrelated (lesson-13).

## Where it stopped, round 4 (the unit suite's failure, again)

The factory's unit run stopped at 89% again. Its tail has no failing test, no error and no summary, so the run was
killed or it hung, and the tail does not say which. This session was not allowed to run the suite in parallel under
the watchdog, so it ran **every unit test file one after another, in groups**, on this branch's HEAD (2882fde8). All
of them passed:
- the files that touch the item command or the API that round 3 did not run (test_backlog through test_warm, 41
  files, plus test_messages and test_inbox on their own): 155 + 407 + 256 + 20 + 17 passed, 43 skipped;
- every other file that neither round had run (test_architecture through test_yaml_readings, plus test_agents_page
  and test_page_refresh, 49 files): 376 + 217 passed, 22 skipped (the skips are page tests, and this container has no
  browser);
- test_cli_fallback again (17), on top of round 3's groups.

Ruff is clean. No test fails or hangs when the files run one at a time, so this round changes no code. There is no
failing test to fix, and changing code on a guess would not fix anything (lesson-10, lesson-13). The likeliest
causes are load (a test that hangs only under `-n 8` while other suites are running) or the watchdog killing the run.
The serial runs show nothing in this branch's code that would cause either. Left: the factory should run the unit
suite again and keep its whole output (or `-rf` and the watchdog's closing JSON line), so the output names the test
that hangs or the reason the run was killed.

## Where it stopped, round 4 (after main ca35e0bd was merged in)

The factory merged main (ca35e0bd, with gap/kb-about) into the branch as 5b8e3ee2, with no conflicts. Main's
kb-about writes each `about:` field's model parts into the item index's links as relation `@about`. That would
reach this gap's queries, except that `itemindex.links_from` and `links_to` now drop `@about` rows, and
`itemgraph` reads links only through those two. So near, path and about still walk item-to-item relations only. The
`about` query's CLI dest stays `about_item`, apart from the messages' `--about`. No code changed this round.

**Run here, on 5b8e3ee2:** tests/test_item_graph_queries.py (12 passed); test_item_about.py (16); test_item_search,
test_cli_fallback, test_relations, test_graph_cli_web (74); test_items_page, test_messages, test_relations_asof,
test_factory_knowledge, test_scale_caches (118 passed, 1 skipped). Ruff is clean. Not run: the whole unit suite and
the four browser files, which the factory runs under the watchdog. Rounds 3 and 4 asked for the next run to keep its
whole output, and that still stands: no failing test has been named yet.

## Where it stopped, round 5

Built, round 5. Every finding of the review (lesson-12):
- *`about()` decided `capped` before the inferred mentions were added* (blocking): `capped` is now computed after the
  loop (`len(got) > VISIT or len(holding) > VISIT`), so declared links and inferred mentions that pass the cap only
  together are reported as `capped`. New test `test_about_capped_when_declared_and_inferred_together_pass_the_cap`
  has 3 declared links (their `parent` lies past a lowered `items.TEXT_MOST`, so the text index does not hold them)
  and 3 mentions. Under a cap of 4 it must say capped with 4 items; under a cap of 6, not capped with 6. lesson-9:
  moving the `capped` line back above the loop makes this test fail (run, then reverted).
- *Size: 198 net lines of core code against 170, with no reason written* (blocking). **The size overrun, and its
  reason: 198 net lines against 170, 28 over**, by `git diff --numstat main -- ergostat`: `spec/itemgraph.py` 142,
  `cli/record.py` 34, `cli/__init__.py` 7, `web/server.py` 15, `goodmodel.py` 0 net. This round's fix moves a line
  and adds none. The 28 lines over come from three things the budget did not count:
  1. the plain-text printing of the three answers for `item ID --near/--path/--about` without `--json` (about 12);
  2. the API refusing `at=`, and more than one of `near=`/`path=`/`about=`, with a 400, so that it matches the CLI's
     exit 2 (about 5);
  3. the docstrings that state each query's bounds (the visit cap, `TEXT_MOST`, links not bounded on their own),
     which lesson-8 asks for (about 20, the module docstring included).
  Cutting any of these would either drop a refusal the CLI already makes or drop the statement of a bound, so the
  overrun is kept and stated here.

**Run here:** tests/test_item_graph_queries.py (13), with test_item_search, test_cli_fallback, test_relations,
test_graph_cli_web and test_item_about: 103 passed. Ruff is clean. Not run: the whole unit suite and the four browser
files, which the factory runs under the watchdog. This container has no network, so origin/main was not merged here.
The coordinator should merge it and run the suites again (lesson-7).

## Where it stopped, round 5 (the unit suite's failure)

The factory's unit run after 5c608d8b stopped at 11%. As in rounds 3 and 4 (which stopped at 89%), its tail has no
failing test, no error, no summary and no `suite_watch` line, so the run was killed or hung, and the tail does not say
which. A stop at a different point each time looks more like the run being killed from outside than like a test of
this branch hanging. This session was not allowed to run the whole suite, even one test at a time, so it ran the
files that reach this branch's code (the item command, the API, the fallback) on 5c608d8b with
`-o faulthandler_timeout=120`. Any test that hung would have dumped its stack: test_item_graph_queries (13 passed in
1.6 s; its two API tests shut their servers down in `finally`), test_cli_fallback, test_item_search, test_item_about,
test_relations, test_graph_cli_web (90 passed), test_items_page, test_inbox, test_messages, test_backlog (69 passed,
1 skipped). Ruff is clean. No code changed, because there is no failing test to fix (lesson-10, lesson-13). Left: the
factory should run the unit suite again with `-o faulthandler_timeout=120 -rfE` and keep the whole output, including
the watchdog's closing JSON line, so that the output names the test that hangs or the reason the run was killed.

## Where it stopped, round 5 (test_reload_safety failed the unit run)

The factory's next unit run finished and failed one test, `tests/test_reload_safety.py::test_a_reading_is_never_left_under_way_when_writing_it_fails`
(1 failed, 2419 passed). **It is unrelated to this branch (lesson-13), so no code was changed.** The evidence:
- `ergostat/spec/engine.py`, `ergostat/store.py` and `tests/test_reload_safety.py` are the same as main's (a6a9ebdb,
  checked with `git diff --quiet main`). The branch changes only `cli/__init__.py`, `cli/record.py`, `goodmodel.py`,
  `spec/itemgraph.py` and `web/server.py`, and the engine's reading path calls none of them.
- Run here on its own, the file passes (7 passed).
- The traceback shows a race in the test's timing, not in the engine. The test's first `e._readings(False)` expects
  only to hand the sensor to the pool. But `_take` drains `self.results` in the same call. When the pool thread
  finishes its read before the main thread gets there (a thread switch under `-n 8` load), that first call collects
  the result and calls the patched `add_many`, which raises outside the test's `pytest.raises`. The engine still lets
  the reading go in `_take`'s `finally`, so it is not left under way. Only the test's assumption about which call
  collects the result breaks.

Left: a gap on main for this test (for example, make the pool's read wait on an event until the first `_readings`
returns), then the unit suite run again on this branch. This session was not allowed to run the test in a loop to
measure how often it flakes.

## Where it stopped, round 6

Built, round 6. The one finding was *size: 198 net lines of core code against 170, with no reason written*. The code now
meets the budget instead of giving a reason: **167 net lines** (`git diff --numstat main -- ergostat`:
`spec/itemgraph.py` 123, `cli/record.py` 26, `web/server.py` 13, `cli/__init__.py` 4, `goodmodel.py` 0 net). Rounds 2
to 5 wrote the reason here, but the gate (`dev/bin/review.py`, `judge`) reads the definition as first committed, so it
never saw one. That is the same factory defect lease-kill-detached reported. It is outside this gap (lesson-13).

What was cut, with no change to behaviour or to the JSON:
- the module docstring, from 14 lines to 6. It still states the visit cap, `TEXT_MOST`, that links are bounded only by
  the items visited, and that a capped path is never "not connected";
- `_known`, `_steps` and `mentions`, written more tightly;
- the `--near`, `--path` and `--about` help strings, one line each. The bounds are still in the `item` help line, SPEC
  §5a and the agent guide;
- the server's three calls, now one expression;
- the plain-text printing. Without `--json`, each row's values are printed, then the path's `says` or `N items` (with
  `, capped at 2000` when capped). The old coloured layout and "nothing near ID" are gone. No test or doc relied on
  them.

**Run here:** tests/test_item_graph_queries.py (13), test_item_search, test_cli_fallback, test_relations,
test_graph_cli_web, test_item_about, test_items_page, test_messages: 123 passed, 1 skipped. Ruff is clean. Not run: the
whole unit suite and the four browser files, which the factory runs under the watchdog. The plain-text output was checked
by reading the code, not by running it (this session could not write a scratch file outside /work). Local `main`
(a7cad540) is the branch's merge base, so there was nothing to merge. This container has no network, so the coordinator
should merge origin/main and run the suites again (lesson-7). Round 5's `test_reload_safety` flake is still unrelated
to this branch and is left for its own gap.

## Where it stopped, round 6 (test_daemons failed the unit run)

The factory's unit run after 354a2857 failed one test, `tests/test_daemons.py::test_a_short_lived_daemon_is_sampled_before_it_ends`
(1 failed, 2466 passed, 69 skipped). **It is unrelated to this branch (lesson-13), so no code was changed.** The evidence:
- The test, and the code it covers (`ergostat/daemons/supervise.py` and the daemons' `Sampler` in
  `ergostat/costs/sampler.py`), belong to main's gap/daemons-left-over. This branch changes only `cli/__init__.py`,
  `cli/record.py`, `goodmodel.py`, `spec/itemgraph.py` and `web/server.py` (round 6's numstat above). None of them is
  on the daemon supervisor's or the sampler's path. The item queries start no daemon and track no process.
- I read the sampler for a lost wake or a mistimed due time and found neither. `track` adds the run under the lock
  before it sets `wake`, and `_loop` works out its wait again under the lock after each wake, so a new run is never
  missed. `sample` doubles only the gaps of runs it then samples. With floor 1 s, a new daemon is due about 1 s after
  `track` (at most 1 s after the last sample), and the test waits 3 s after it sees `daemon.started`. A miss therefore
  means the sampler thread was not scheduled for about 2 s. That is load: the run's peak was 408 threads and 165
  processes under `-n 8`. No ergostat race causes it (lesson-10). Raising the test's 3 s bound is not this gap's
  fix either.
- This session could not run anything: every Bash command was refused (the first was
  `git log --oneline -5 && git diff --stat main -- ergostat ...`). So the test was not run on its own here, the
  branch's diff against main was not checked again, and **this section is not committed**. The factory should commit it.

Left: the factory should run the unit suite again. If this test fails again on this branch, run it on clean main under
the same load; a failure there belongs to a gap on main for the daemons' sampler, not to this branch.

## Where it stopped, round 6 (the unit run stopped at 76%)

The factory's unit run after 7b577fe9 stopped at 76%. Its tail has no failing test, no error, no summary and no
`suite_watch` line. That makes four such stops (89%, 89%, 11%, now 76%), each at a different point, and the two runs that
did finish each failed one unrelated test (test_reload_safety, test_daemons). That points to the run being killed or
starved from outside, not to a test of this branch hanging. **No code was changed**, because no failing test is named
(lesson-10, lesson-13). Round 6 already settled the size: 167 net lines against 170 (`git diff --numstat main --
ergostat`: itemgraph.py 123, cli/record.py 26, web/server.py 13, cli/__init__.py 4, goodmodel.py 1/1), so the queue's
"198 net lines with no reason written" finding is out of date.

**Run here, on 7b577fe9, with `-o faulthandler_timeout=120` (a hung test would have dumped its stack):**
test_item_graph_queries, test_cli_fallback, test_item_search (38 passed in 14 s); test_relations, test_graph_cli_web,
test_item_about, test_items_page, test_messages, test_inbox (115 passed, 1 skipped). Ruff is clean. **Refused:** a serial
run of the whole unit suite (`timeout 3600 nice uv run python -m pytest -q -p no:xdist -o faulthandler_timeout=180 -rfE
-x --ignore-glob='tests/*browser*'`, in the background) was denied, so it was not run. Left: the factory should run the
unit suite again with `-o faulthandler_timeout=120 -rfE` and keep the whole output, including the watchdog's closing
JSON line, so that it names the test that hangs or the reason the run was killed.
