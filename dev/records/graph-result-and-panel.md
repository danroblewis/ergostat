# graph-result-and-panel: `graph`, the three producers adapted, named kinds, ELK in a worker, budgets and aggregation, matrix fallback

depends-on: [fix-process-rework-flag, result-frames-and-verdicts]

From the chart catalog, `docs/research/2026-11-23-charts/catalog.md`: read section 7 for this item, and the sections it cites (result shapes in section 2, guardrails in section 6, workflows in section 5, and the source reports beside it).

The owner's decisions (2026-11-23): data sources are like Grafana's, each with its own text language; PromQL is primary and read-only SQL is only for what PromQL cannot do; metrics hold aggregates over bounded labels and anything with a generated ID stays in the event log; stocks are gauges, flows are counters, delays are histograms; no visual query builder; result shapes decide which charts apply. VictoriaMetrics is the default metrics store for new installs. Rework means an item repeated a step. The new diagram kinds named in the catalog are allowed (update `docs/proposals/diagram-options.md`), limited to those named kinds. The service map is built from caller and callee labels in metrics first. No new pages: charts are Dashboard panels or live on existing pages, and the Blocks and Dynamics views stay separate and true to their disciplines.

This is item B6.

Delivers: `graph`, the three producers adapted, named kinds, ELK in a worker, budgets and aggregation, matrix fallback

Unlocks charts: 74, 75, 77 (section 3.2).

Definition of done.
1. Everything this item delivers in the catalog works on a hand-worked record, with its numbers checked by a test.
2. Each guardrail the catalog assigns to this item refuses or warns as stated, with a test that tries the misuse.
3. A chart that cannot be trusted on its data says so, and does not draw as if it could.
4. Decision logic is in pure functions with fast in-memory tests. Anything the catalog marks `[unsure]` is measured or left visibly unsure, never assumed.
5. It works at factory size within the budgets the catalog states, and reads neither the event log per request nor a raw internal table from the page.

## Where it stopped

Built, round 1. This gap's own work is 548 net lines outside tests, docs and dev (`git diff --shortstat 32ba2b47`: 567
added, 19 removed), within the 600. Against `main` the count is 945 added and 68 removed, because
`result-frames-and-verdicts`, which this gap depends on, is merged into the branch and is not on `main` yet.
Overrun reason: measured against main, the diff includes the merged base gap result-frames-and-verdicts (about 330 net lines, not yet on main); this gap's own change since that merge (32ba2b47) is 548 net lines, under the 600.

What was built:
- `ergostat/query/graphs.py` (new): the three producers adapted to the `graph` frame of a named kind.
  - `{"source": "graph", "diagram": "dependency" | "process" | "service", "kind"?}`.
  - `dependency` comes from `precedence.py` through `web/relations_api.graph`. Edges are `blocks`, or `met` once the
    item waited on is finished (G40). Each node has its slack, duration and critical flag. The answer says the critical
    path's end beside the levelled end (G42). Charts 74 and 75.
  - `process` comes from `process.py`. Its routes are not real (`paths_real: false`).
  - `service` comes from `graph.wiring`. Its evidence is `observed`, `declared` or `both`, with `last_seen`.
  - Then come the checks of `_frames._graph`, G43 (a graph cut by its maker, or with `omitted` not empty: `acyclic`
    is null, `graph-truncated`) and G44 (a cycle is said by kind: `graph-cycle` warns for dependency, wait_for and
    lineage; otherwise a sentence).
  - A maker's answer is kept 30 s for each graph asked.
- `ergostat/query/graphfit.py` (new, pure): the budgets and aggregation.
  - The panel's 40 nodes and 100 edges. Over them: collapse by group, then type, then weight into `other`; then the
    lightest edges are left out, with `omitted` and its weight share.
  - Aggregation stays honest: `holds`; counts and rates summed; every other field the worst member's, named in `worst`
    (G45); one unhealthy member marks its group; `paths_real` false once collapsed.
  - The matrix (chart 77): fitted to 300 rows, in group order.
- `datasources`: a data source's graph is fitted the same way. `_frames` takes a node's `health`. `verdicts` has three
  new reasons. `parse` has the query form, refused as an X, input or output, or with other keys.
- The page:
  - `plots-graph.js`, the graph family. ELK runs in a Web Worker (`graph-layout.js`), with one layout per set of nodes
    and edges, so a refresh moves nothing (G39 within one structure). It draws a heavy critical path, unhealthy nodes,
    dashed declared-only edges, muted met waits, `×N` on aggregates, and hover words. The legend says "A route through
    two lines is not evidence" when `paths_real` is false (G35).
  - The heatmap draws `matrix`. `panels.js` draws one graph per panel and says so when there are more. Each graph's
    sentences are said under it.
  - The default dashboard has a process-map example, so every family has a panel there.
- SPEC §4e: *Ergostat's own graphs*, *A graph on a panel*, *Drawing a graph*, and *Which charts apply*.
  `docs/proposals/diagram-options.md` has a dated note.

Choices taken without asking (the most reversible):
- The query form is a source of ergostat's own query language, not the catalog's `model` source with its call syntax.
  `model-data-source` is not on main, and data source types get no project to read. When it lands, it can call
  `graphs.answer`.
- The event log's wiring is drawn as the `service` kind. It is the closest of the eight: what talks to what. The
  metrics service map is still B15's.
- The panel never decides between worker and page by the catalog's "about 200 ms": every layout goes to the worker.
  The page's own thread is used only if no worker can start, or the worker does not answer in 10 s. So ND's ELK
  timings (`[unsure]` in Appendix A) are not relied on.
- 300 matrix rows is ND §12.3's `[unsure]` budget. It is used and called unsure in the code and in SPEC, and it was not
  measured. The server bound stays the 5,000 nodes and edges of `_frames`, over which a graph is refused (`limit`), not
  ND's 50,000.
- The page budgets (60 and 160 for maps, 200 and 600 for dependencies) are not applied. No page changed. The Process
  view keeps its own caps of 60 and 160.
- A `sequence` graph is not drawn: the panel says so. `impact` is set to ELK's radial algorithm, but there is no impact
  maker yet, so it was not drawn by any test.
- G37 (betweenness) is not offered: no field role is a centrality. Nothing was built for it.
- Not this gap's: G36 and G41 (B10, B11), and G46 to G48 (B10, B15). The fixed layout over the union of a window, its
  frames and ghosted edges are B15's, and so are the wait-for, impact, conformance and lineage makers.

Acceptance tests, `tests/test_graph_result_and_panel.py` (unit, 20) and `tests/test_graph_result_page.py` (browser, 3):
- Done 1 (hand-worked records in the docstrings):
  - `test_the_dependency_graph_and_its_critical_path_beside_the_levelled_end`: slack 0, 0, then 1,200 s each; critical
    a and b; ends 40 min against 1 h; f to g `met`.
  - `test_the_process_map_is_a_process_graph_whose_routes_are_not_evidence`: lines 3, 4, 2, 1, 2 and two returns.
  - `test_the_wiring_is_a_service_graph_with_its_evidence`.
  - `test_the_matrix_orders_by_group_and_sums_the_cells`.
  - Page: `test_a_dependency_graph_is_laid_out_in_a_worker_and_draws_its_critical_path` and
    `test_an_over_budget_graph_collapses_says_so_and_its_matrix_is_drawn_by_the_heatmap`.
- Done 2 (each misuse tried):
  - `test_latency_is_never_averaged_across_an_aggregated_edge` (G45)
  - `test_over_the_budget_nodes_collapse_by_group_and_what_they_hold_is_said`
  - `test_then_by_type_then_by_weight_into_other` and `test_over_the_edge_budget_the_lightest_edges_are_left_out_and_their_share_said`
  - `test_an_over_budget_graph_warns_and_offers_the_matrix`
  - `test_a_graph_read_only_in_part_says_whether_it_has_a_cycle_is_not_known` (G43)
  - `test_what_a_cycle_means_is_said_by_kind` (G44)
  - `test_a_graph_is_asked_only_in_its_own_form` (5 cases) and `test_a_kind_not_in_the_model_and_a_kind_on_the_wiring_are_refused`
- Done 3: `test_what_the_graph_panel_cannot_draw_it_says`. It covers a sequence diagram, two graphs in one panel, and
  every other shape refused in one sentence. Also the G35 legend note and the over-budget warning on the page.
- Done 4: the decisions are pure functions (`graphfit.fit`, `graphfit.matrix`, `graphs.dependency`, `graphs.process`,
  `graphs.service`, `graphs.panel`). The unit file runs in about 0.5 s. The `[unsure]` items are as above.
- Done 5:
  - `test_the_record_is_read_once_for_a_graph_however_many_ask`: one read for two asks, and another after 30 s.
  - `test_fitting_a_graph_at_its_bound_is_quick`: 5,000 nodes and 5,000 edges, fitted and made a matrix, under a 5 s
    bound. The whole file took 0.5 s. That run is not a measure of the factory's own record.
  - The page reads only `/api/query`. The dependency graph reads the item index, not the event log.

Seen to fail when the code they guard was broken (then restored; `git status` clean):
- Latency summed: the G45 test failed. The truncation check off: the G43 test failed.
- Layout kept off the worker: the worker assertion failed. The one-graph check off: the done-3 page test failed.

Also changed: `tests/test_result_shapes.py` (a data source's graph sample is fitted as `datasources.query` fits it) and
`tests/test_result_shapes_page.py` (the heatmap now takes a graph).

Run here, at most three files at a time, browser files under the watchdog, none skipped:
- Unit, all passed: test_graph_result_and_panel, test_result_frames_and_verdicts and test_result_shapes (69);
  test_data_sources, test_query_engine and test_web_access (96); test_graph_cli_web, test_dashboards and test_process
  (108).
- Browser, all passed with rc 0: test_graph_result_page, test_result_shapes_page and test_result_frames_page (16);
  test_dashboard_page, test_plot_forms and test_panel_editor (196); test_panels, test_data_source_panels and
  test_dashboards_doc (62).
- ruff is clean. `git merge main` said "Already up to date."

Not run here: the whole unit suite and the four browser files (the factory's); `demo_check` (no example touched); a
demo walk with screenshots (not done in this session).

Refused in this session: writing a scratch test under `/tmp` (the file tools are confined to /work). A scratch test was
written under `tests/`, run, and deleted before any commit.

## Entry

section: Done recently

- **Graph result and panel** (B6 of the chart catalog). Ergostat's own three graphs now reach a Dashboard panel as
  `graph` answers of named kinds: the precedence network as `dependency` (the critical path, with the end levelled by
  capacity said beside it), the process map as `process`, and the event log's wiring as `service`. A new graph chart
  draws them, laid out by ELK in a Web Worker, with one layout per structure. Every graph, a data source's too, is
  fitted to 40 nodes and 100 edges, collapsed by group, type, then weight. What an aggregate holds is said, and latency
  is never averaged. The matrix is offered, and the heatmap draws it. A cycle is worded by kind, and a graph read in
  part says that whether it has a cycle is not known.

## Where it stopped (round 2)

Built, round 2: the three findings of round 1's review, each answered (all three were blocking; there were no others).
This gap's own work is now about 568 net lines outside tests, docs and dev: against `main` it is 965 added and 68
removed (897 net), of which the merged base `result-frames-and-verdicts` is 388 added and 59 removed (329 net,
`git diff --shortstat main e30ee5e4^2`).
Overrun reason: measured against main, the diff includes the merged base gap result-frames-and-verdicts (329 net lines, not yet on main); this gap's own change is about 568 net lines, under the 600.

1. `graphs.py` `CYCLE` had no `sequence` entry (a KeyError for a data source's sequence graph with a reply). It now has
   one ("a message back is a reply, not a defect": a note, not a warning). Any kind with no words of its own gets
   `UNSAID`, a `graph-cycle` warning in a generic sentence, so a miss fails safe and says it. Test:
   `test_a_cycle_in_a_kind_with_no_words_of_its_own_is_said_and_never_fails` (a sequence a > b > a; then with
   `sequence` removed from `CYCLE`).
2. Graph reads were outside the request's budget. `engine.Work.charge` now takes them: no graph read starts past the
   request's deadline (`REQUEST_SECONDS`), and a read of the event log (process map, wiring) is one of the request's
   `LOG_READS`, keyed like an event chart's. The dependency graph reads the item index, so it is held to the deadline only.
   A kept answer (30 s) is still answered with no charge, as `_one` and `_shaped` do. So a request of many graph queries,
   or one scrubbing past windows, makes at most four log reads, none started late. Each scrubbed moment still reads
   once (an answer depends on its `until`), the same as event charts. Test:
   `test_graph_reads_are_charged_to_the_request_and_none_starts_late`.
3. `met` read only `status == "done"`. `precedence.build` now marks each precedence edge `met` by its own `finished`
   (done, or in a state the relation's `starts_at` names), and `graphs.dependency` reads that. Test:
   `test_a_start_to_start_wait_whose_state_is_reached_is_met` (h doing; k `after` h with `starts_at: [doing]` is `met`,
   m `blocked_by` h is `blocks`). SPEC §4e was updated for 1 to 3.

Seen to fail when broken (each restored): `CYCLE.get` back to `CYCLE[kind]` gave a KeyError in the first test. The
`work.charge` call removed let the second process graph read (no error). `met` not set in `precedence.py` drew h > k
as `blocks`.

Run here:
- Unit, all passed: test_graph_result_and_panel, test_precedence and test_query_engine (85); test_graph_parts,
  test_result_shapes and test_data_sources (41); test_relations, test_relations_asof and test_graph_cli_web (92).
- Browser, under the watchdog: test_graph_result_page passed (3). test_items_page had 4 failures and 83 passed.
  Among them were `test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel`,
  `test_the_graph_and_the_timeline_left_open_change_nothing` (`[graph]` in one run, `[timeline]` in the other), and the
  goals-upkeep heading test at line 3151 ("Goals ·" where "Loops ·" is expected). The fourth failure's name was cut off
  in the output. The file failed 4 the same way with this round's `precedence.py` change reverted, so these failures
  are not this change's (lesson 13). They are left alone.
- ruff is clean. `git merge main` said "Already up to date."

Not run here: the whole unit suite and the four browser files (the factory's); `demo_check` (no example touched); a demo
walk.
