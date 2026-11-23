# milestone-progress-per-group: each milestone shows how far along it is

depends-on: [milestone-every-gap-has-one]

Owner, 2026-11-23: "if we have milestones and groups of gap tasks, then I probably also want to see progress per group, right?"

Change.
- Each milestone reads as: done, in progress, waiting, stopped, of its total, with its state (active, waiting on another milestone, completed) and what it is waiting on. Closed gaps count as done only when they were finished; a gap closed as a duplicate or abandoned leaves the total.
- It is shown through what exists: a compact row per milestone with a progress bar in the Items overview for the gap kind and on its kind page, active milestones first, and each row opening that milestone's gaps in the list, graph and Timeline. No new page.
- The numbers come from the item index, never by replaying events, and are available to dashboard panels: gaps by milestone as a category, grouped by state group, and each milestone's completion over time.
- Gaps with no milestone appear as their own row, so the unassigned share stays visible.

Definition of done.
1. A hand-worked record gives the right counts per milestone, including split, closed-as-duplicate and parked gaps.
2. A milestone's row links to exactly its gaps.
3. Twenty-five milestones fit without pushing the item types below the fold (collapsed past the active ones).
4. A dashboard panel can chart gaps by milestone, stacked by state group, with no custom code.

Files: dev/bin/milestones.py, ergostat's items pages and query fields, tests.

## Where it stopped

Built, round 1. About 285 net lines outside tests, docs and dev (within 600).

- The counts: `ergostat/spec/grouptally.py`, generic (ergostat knows no gap or milestone): any group relation whose
  field folds by `replace` gets per-group counts from the item index (the folded items and their moves), as
  `/api/items-groups?kind=K&by=REL`, `ergostat item --kind K --groups REL [--json]`, and `progress` on each kind in
  the Items listing. `milestones.py status` prints each milestone's line, and one for the gaps in none, from
  `ergostat item --groups`. When that call cannot be read it prints "progress: not read (why)" once, never zeros.
- How "closed as a duplicate or abandoned" is known: a new relation key, `done_when` (SPEC §5a). ergostat.yaml
  declares `milestone: {..., done_when: {closed: {end: done}}}`. It is an allowlist: a closed gap counts as done only
  with `end: done`. A duplicate, any other end, or a close with no `end` field leaves the total and is counted as
  `left`. Decision taken alone (the reversible one): a close with no end said is not known to be done work, so it
  leaves the total rather than counting as done.
- A split gap (one another gap names as `parent`) is left out of the total and counted as `summaries`; its parts
  count wherever their own `milestone` puts them. A part with no milestone of its own is in the "no milestone" row:
  membership is the gap's own field only, so a row's link (`where=milestone:ID`; none: `milestone:null` and
  `milestone:`) is exactly what it counts. A gap whose `milestone` holds a list is in no row and is named.
- The page: a compact row per group under the kind's chart, on the overview and on the kind's own page. The active
  ones and the "no milestone" row are shown; the rest fold behind one button ("22 more (17 waiting, 5 completed)").
  A row's click sets the set's `where`, and the Graph and Timeline now narrow to a `where` on a relation (client
  side, in `rgModel`: those items and what they wait on). No new page.
- Done item 4, narrowed: ergostat has no Dashboard page yet (owner item 18 is not built), so "a dashboard panel"
  here means a panel that takes only query parameters. `/api/items-groups` answers with rows as categories, `stacks`
  (done, in progress, waiting, stopped) as the series, and each row's `done` over `times` for completion over time.
  The same call serves any model's group relation (tested on a ticket/epic model). Drawing the chart is that page's
  work.
- Completion over time reads membership and `done_when` as they are now, not as they were then (said in SPEC).

Tests: tests/test_group_progress.py (done items 1, 2, 4 and the status lines), tests/test_items_page.py
`test_twenty_five_milestones_fit_on_the_gap_card_without_pushing_the_kinds_below_the_fold` (item 3) and
`test_a_milestones_row_opens_exactly_its_gaps_in_the_list_graph_and_timeline` (item 2 on the page). Each was seen
to fail with its code broken: the split rule, the `done_when` rule, the Graph's `where` filter, and the fold.

Run here: tests/test_group_progress.py (8 passed), tests/test_milestones.py (41 passed), tests/test_relations.py,
tests/test_spec_schema.py and tests/test_milestone_frames.py (58 passed), and ruff (clean).
tests/test_items_page.py: 52 passed, 1 failed the same way in both runs:
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` times out at line 1647, waiting for the
header's project switcher to list a second ergostat site in the same home. This branch does not touch the header, the
switcher or project discovery. It was not run on clean main here because making a worktree of main was refused in
this session, so whether main fails it too is not known; the factory's rerun on clean main decides. Not run here: the
other three browser files and the whole unit suite (the factory's).

Round 2. The one finding (relations.py: `done_when` checked only when truthy, so null, `[]`, `false`, `0` or `""`
crashed model load with AttributeError) is fixed: the key is checked whenever it is present, and anything but a
non-empty map on a group relation is refused as bad-relation at `done_when`. An empty map `{}` is now refused too
(SPEC already said "an empty map" is refused). The test `test_done_when_is_a_groups_map_of_its_states` adds null,
`[]`, `false`, `0`, `""` and `{}` and asserts the refusal names `done_when`; with the old check it was seen to fail
(AttributeError at relations.py:116). SPEC §5a's sentence names the case. No other findings were raised.
Run here: tests/test_group_progress.py, tests/test_relations.py, tests/test_spec_schema.py (73 passed),
tests/test_milestones.py, tests/test_milestone_frames.py (42 passed), ruff clean. The browser file was not run again
(no page code changed this round).

Round 3. The one finding (conflicts with main in dev/bin/milestones.py and ergostat.yaml) is fixed: main
(7a44d730) is merged in, both sides kept. In milestones.py's docstring, main's shorter `pull` line and the branch's
`status` line naming the progress. In ergostat.yaml, the branch's `done_when` comment and main's
`waits_on_milestone` comment, one after the other.
Running the browser file after the merge found a real gap the round-2 merge had brought in, unseen because round 2
did not run the browser file: main's Items overview (`/items` is now kinds.js, from `/api/items-overview`) had no
milestone rows, so both page acceptance tests failed waiting for `.gp-row`. Fixed: the overview's cards name
`progress` (web/items_overview.py), and kinds.js asks `/api/items-groups` for those kinds and draws the same
`groupRows` (its card two columns wide). Redrawn only when the rows change, since the answer's `times` move with now.
A row's click opens the kind's own page, `/items/gap?where=milestone:ID`. SPEC §5a says so in both places.
Tests changed to fit main's routing. `test_a_milestones_row_opens_...` reopens the page the click led to (the path
now holds the kind). In `test_twenty_five_milestones_fit_...`, the "(the fold is why)" check said "unfolded, some
card starts past 1000px". On the overview's grid that no longer holds: unfolded, the next card wraps to 849px. It now
asserts that unfolding pushes the next row of cards down by at least twenty rows' height. With the fold broken (every
row shown), the test was seen to fail. tests/test_items_overview.py's pin that kinds.js asks only `items-overview`
now allows exactly `items-overview` and `items-groups`.
Run here: tests/test_group_progress.py, tests/test_milestones.py, tests/test_relations.py (84 passed),
tests/test_spec_schema.py, tests/test_milestone_frames.py (40 passed), tests/test_items_overview.py (7 passed), ruff
clean. tests/test_items_page.py: 58 passed, 2 failed, both again by name. One is
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (the project switcher, as in rounds 1 and 2).
The other is `test_actions_say_per_class_asked_approved_denied_and_whether_held`, at line 593. It opens `/items` and
waits for `.action-classes`, which only the kind's list page (pages.js) draws, while main's router sends a bare
`/items` to the overview. That routing is main's, and this branch leaves the actions and the router alone. Not run
on clean main here (a worktree of main was refused in round 1), so this rests on reading the code: the factory's
rerun on clean main decides. Not run: the other three browser files, the unit suite.

Round 4. The one finding (conflict with main in ergostat/web/static/pages.js) is fixed: main (f086f76e) is merged
in, both sides kept. In the list's `tick`, main's new lines (the page clamped past the end, the "N matches, M
finished" line) come first, then the branch's `flowsWere` that also holds the group rows (`[flows, gps]`), so a
change in a milestone's counts still redraws the list. No other code changed this round.
Run here: tests/test_group_progress.py, tests/test_items_overview.py, tests/test_milestones.py (65 passed),
tests/test_relations.py, tests/test_spec_schema.py, tests/test_milestone_frames.py (66 passed), ruff clean.
tests/test_items_page.py under the watchdog: 61 passed, 2 failed, the same two named in round 3, at the same places:
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (line 1874, the project switcher never lists
the second site) and `test_actions_say_per_class_asked_approved_denied_and_whether_held` (line 620, waits on bare
`/items` for `.action-classes`, which main's router sends to the overview). This branch touches neither the header,
the switcher, the actions nor the router; the factory's rerun on clean main decides. Not run: the other three
browser files, the unit suite.

Round 5. Main (28ad5c4a) merged in first. The conflict in pages.js's list `tick`: main's lines kept (the graph
answers asked with `signal`, `trust`/`classes` awaited, `gone()`, `loaded()`), with the branch's
`JSON.stringify([flows, gps])` check so a change in a milestone's counts still redraws.
The findings, both blocking (there were no others):
- Done item 4 was narrowed on a reason the tree disproves (dashboard.js, panels.js and the query engine are on main).
  The narrowing is withdrawn: a dashboard panel now charts gaps by milestone stacked by state group with no custom
  code. The query engine labels items by a group relation's field (`milestone`, already a field in the index) and by
  `state_group`, each item's stage as its progress counts it (`labels.stage`, from `grouptally.stages`: the same
  read, so a chart's counts are the progress's). `/api/query/fields` offers both in `group_by` (`_groupable`: group
  relations folded by replace, whatever their number of values, and `state_group` for a kind with states). The panel
  is a `bar` with `stack: stacked` of four `counts` queries, `x: {type: category, by: milestone}`, `where:
  {state_group: S}`, one per stage; plots-bar.js already stacks several queries' categories. An empty text label
  now reads as `none` (labels.word), as the progress's "no milestone" row does. Decision taken alone (the reversible
  one): no new query shape (a category X with a second `group_by` is still refused), only labels. Known limit, said in
  SPEC: like every category chart, at most 12 categories a query, the rest as `other`, and each query picks its own
  largest 12, so past 12 milestones a stack's `other` can hold different milestones from another's. The page's
  milestone rows are the view for 25.
  Test: `test_a_dashboard_panel_charts_gaps_by_milestone_stacked_by_state_group` sends the panel's own queries as
  panels.js sends them (id, label and hidden dropped) to `/api/query` and asserts each milestone's stack equals its
  progress row, the "no milestone" row as `none`, and that the fields offer both. With `state_group` read as the
  state instead, it was seen to fail. The old endpoint-only test is renamed
  `test_items_groups_answers_any_kind_by_its_group_as_a_category_by_stack_table` (it claims no panel now).
- Members were read with no waits, so "blocked" never occurred. Now each member's status gets what
  `precedence.build` reads: its precedence targets not finished (start-to-start by `starts_at`; a target not in the
  record is not known to be finished), plus its group when the group item is unstarted (`blocked` or `unblocked`: a
  milestone still in `waiting`). Decision taken alone: the group rule is model-neutral (ergostat knows no
  `waits_on_milestone` field), and an active member stays in progress whatever it waits on, since its work began.
  The hand-worked record gets a block taking gaps at `ready` and five gaps there: d1 behind a building gap (waiting),
  d2 behind a merged one (in progress), d3 behind one not in the record (waiting), b2 in waiting m-b (waiting), b3
  pulled and building in m-b (in progress). m-a is now 3/3/4/1 of 11, m-b 0/1/2/0 of 3. Seen to fail with the waits
  dropped (4 failed), with the group rule alone dropped (3 failed), and with a missing target read as finished (4
  failed).
Run here: tests/test_group_progress.py (9 passed), tests/test_query_engine.py (52), tests/test_query_fixes.py (19),
tests/test_query_axes.py, tests/test_query_spread.py, tests/test_items_overview.py (79), tests/test_milestones.py
(50), tests/test_precedence.py (10), tests/test_relations.py (26), tests/test_milestone_frames.py and
tests/test_spec_schema.py (40), tests/test_dashboards_doc.py (34), ruff clean. tests/test_items_page.py under the
watchdog: 67 passed, 1 failed, `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` at line 2013
(the project switcher, as in rounds 1 to 4; this branch touches neither the header nor the switcher). The
actions test of rounds 3 and 4 passes now. Refused in this session: a background run of that browser file with
its output sent to /tmp (`... > /tmp/items_page.log 2>&1`); it was run in the foreground instead. Not run: the other
three browser files (test_dashboard_page.py among them: no page code changed this round), the unit suite.

Round 6. The one finding (conflict with main in docs/SPEC.md) is fixed: main (8a27f9e3) is merged in, both sides
kept. In §4e's bullets, the branch's **Groups** line (group relation fields and `state_group`) replaces main's
shorter one, and main's new **Frequency responses** bullet follows it. No code changed this round.
Refused in this session: a python heredoc that edited SPEC.md and committed (`python3 - <<'EOF' ...`); the
conflict was resolved with the editor instead.
Run here after the merge: tests/test_group_progress.py, tests/test_query_engine.py, tests/test_query_fixes.py (80
passed), tests/test_query_axes.py, tests/test_query_spread.py, tests/test_items_overview.py (80), tests/test_milestones.py,
tests/test_precedence.py, tests/test_relations.py (86), tests/test_milestone_frames.py, tests/test_spec_schema.py,
tests/test_dashboards_doc.py (74), ruff clean. tests/test_items_page.py under the watchdog, twice: 67 passed, 1
failed, `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` at line 2013 (the project switcher,
as in rounds 1 to 5; this branch touches neither the header nor the switcher). Not run: the other three browser
files, the unit suite.

Round 7. The queue's finding (the merge in a batch of 3 failed, and alone
`tests/test_cli_fallback.py::test_every_flag_of_a_read_topic_is_called_acting_or_read_only` failed) is fixed. The
branch's new `ergostat item --groups` flag was not classified for the last-good-model fallback. It only reads (it
opens the project and folds the item index, writing nothing; `cli/record.py` `_item_groups`), so it is added to
`goodmodel.READ_FLAGS`. The test was seen to fail before the change (`['item --groups']` untold) and pass after.
No other findings were raised.
Run here: tests/test_cli_fallback.py (18 passed), tests/test_group_progress.py (9 passed), ruff clean. Refused in
this session: a shell command that grepped the CLI and edited goodmodel.py with `sed -i`; the editor was used
instead. Not run: the browser files (no page code changed this round), the unit suite.
