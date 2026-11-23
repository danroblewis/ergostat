# parts-belong-to-their-system: a part knows which system it belongs to, and is shown without the system's name where that system is known

depends-on: [remote-of-remotes-continued]

The owner, 2026-11-22: "systems should be namespaced, if a thing belongs to a system it should get prepended with the system name, we can remove the system name from the thing's name if we know the system's name."

Today composed names are made by joining strings (`f"{inst}-{bare}"` in `ergostat/library/expand.py:492,560`, `f"{remote}-{n}"` in `ergostat/remote/compose.py`). Nothing records the owner of a name, so a local `m-a-open` and remote `m`'s `a-open` can only be told apart by bookkeeping in each place, and a diagram inside system `m` repeats `m-` on every box.

## Definition of done
1. The compiled model records, for each part made by a library instance or a remote, the system it belongs to and its name within that system. A hand-written part in no such system records none.
2. Full names do not change: every existing model, event, record and reference keeps working, with no migration.
3. Where the system is known (a diagram or list inside that system's box, or its system page), the part is shown by its short name, with the full name on hover and in links. Where it is not, the full name is shown. Two parts shown side by side never read the same.
4. The short name is derived from the recorded owner, never by stripping text that happens to match.
5. SPEC says what a part's system and short name are.

## Files to touch
`ergostat/library/expand.py`, `ergostat/remote/compose.py`, the compiled model, the web payload and diagram labels, `docs/SPEC.md`, tests.

## Risks
- No new page or panel: only labels change.
- lesson-3: a part whose owner is unknown shows its full name.
- After any label change, run `tests/test_diagram_rendering.py`.

## Acceptance tests
- a library instance's part and a remote's part each record their system and short name
- a hand-written `m-a-open` beside remote `m`'s `a-open` keeps distinct owners
- inside a system's box the short name is shown, with the full name available; outside, the full name
- an existing example compiles to the same full names

## Size budget
200 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 127 net lines of code outside `tests/`, `docs/` and `dev/` (`git diff --numstat main HEAD`).

- The record: `ergostat/spec/belongs.py`. A library instance (`library/uses.py`, from `expand.py`'s new
  `Made.shorts`) and a remote (`remote/compose.py`, `parts()` now yields each part's name there) give each part a
  copy of its `where` carrying `Belongs(system, short)`. The compiler copies them into `Spec.belongs`, keyed
  `stock.NAME`. Name-making lines are unchanged, so full names are the same.
- The labels: `ergostat/shown.py` adds `shown` to nodes and to box rows and ports in the fold output (the Control
  and Dynamics views); `diagram.js` and `dynamics.js` draw `shown || label`. Clashing short names fall back to
  full names.
- Acceptance tests: `tests/test_parts_belong.py` (7 tests) and
  `tests/test_diagram_rendering.py::test_inside_its_own_systems_box_a_part_reads_by_its_short_name_with_its_full_name_on_hover`.
  Each guarded piece was broken in turn and the test caught it: owner check in `shown.py`, the clash rule, the
  remote record, the nested-use record, `nameOf`, and `fullOnHover`.

Choices made with nobody to ask, the most reversible taken each time:
- "Full name on hover": the page has a tested rule that no diagram part has a tooltip
  (`NO_TOOLTIPS`, `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip`). A first version that
  used `<title>` failed that test, so instead the part's own text switches to its full name while the pointer is on
  it. Its panel and every link still use the full name (`label` is unchanged).
- The Blocks and Process views are left as they were (full names): their labels are math symbols and item kinds,
  not part names. The title of an open system's outline still shows the system's full name.
- No owner is recorded for a remote's stand-in (a part it does not serve), a `once: true` template's parts, a
  name a parameter gives whole, or an instance's own system unless it is nested. All of these show full names
  (lesson-3).
- "Hand-written `m-a-open` beside remote `m`'s `a-open`": this clone's main has none of `remote-of-remotes-continued`
  (no record, no names-taken handling), so a remote part whose composed name a local part already took is still
  the existing defined-twice error. The test checks this at the loader: the hand-written part records no owner
  and the remote's other parts record `m`. It also compiles a hand-written `m-b-open` beside remote `m` and checks
  that it records no owner.
- No origin/main in the clone. Local `main` (5617e225) is the parent of the definition commit, so there was
  nothing to merge.

Tests run (serial, one file at a time): `tests/test_parts_belong.py`; `tests/test_templates.py`,
`tests/test_remote.py`, `tests/test_remote_box_measures.py`; `tests/test_remote_lines.py`,
`tests/test_library_trust.py`, `tests/test_library_provenance.py`; `tests/test_spec_systems.py`,
`tests/test_dynamics_view.py`, `tests/test_correspond.py`; `tests/test_graph_cli_web.py`,
`tests/test_remote_pair.py`, `tests/test_upkeep_template.py`: all pass. `tests/test_diagram_rendering.py` in full
under the watchdog with Playwright: 201 passed, rc 0, none skipped. An earlier full run (with the `<title>`
version) had one more failure, `test_every_lines_panel_links_to_the_parts_it_joins[coordinator]` ("link corrected
opened nothing", 5 s wait). It passed twice alone and in the full rerun, and both parts it links are hand-written,
so this change does not relabel them. It is not fixed here (lesson-13). Not run here: the whole unit suite, the
other three browser files, `demo_check` (no example changed).

## Where it stopped (round 2)

Main (2abe6348) merged in. 126 net lines of code outside `tests/`, `docs/` and `dev/` (`git diff --numstat 2abe6348 HEAD`).

The conflict in `ergostat/remote/compose.py`: main now holds a remote's parts in `info["pending"]` and `finish` puts
them after every file, each with a `RemoteVia` carrying its chain. The branch's `parts()` still returns (part, name
there); `one()` gives each pending part `own(RemoteVia(...chain...), remote, name there)`, so the part `finish` puts
records its system. A stand-in keeps main's `RemoteVia(stand_in=True)` and records no owner.

Each finding of review round 1:
- Depended on remote-of-remotes-continued, which was not on main: it is now. The test
  `test_a_hand_written_m_a_open_beside_remote_ms_a_open_keeps_distinct_owners` compiles the collision: the
  hand-written `m-a-open` stands with no owner, a `remote-name-taken` finding is about it, and the remote's other
  part (`m-a-rate`) records `m`.
- Outline titles were not in the clash check: `shown.py` now counts each open system's title as drawn.
  New test: `test_a_short_name_that_reads_like_an_open_outlines_title_is_drawn_by_its_full_name`.
- A `once: true` template's nested use records the instance (its name is prefixed): kept, since the record is true.
  SPEC is narrowed to match ("a part a `once: true` template keeps unprefixed" records none; its inner use does).
- `assert g is not None` replaced by a check on what `shorten` hands back. The browser hover check now covers a
  closed box's port too: `test_a_closed_boxs_port_reads_by_its_short_name_with_its_full_name_on_hover` (a hand-written
  flow out of `help-queue-waiting`, added in a copy of small-requests, gives the closed help-queue box a port).
  The page has only one systems view (Dynamics; "control" is its old name), so `diagram.js`'s box drawing is not
  reachable from the page and this test covers `dynamics.js`. SPEC now says "the Dynamics view (once called Control)".
  No example's box has measure rows, so rows are checked by the unit test only.
- No GAPS.md entry: added under Remote systems and libraries.

Broken in turn, and the test caught each: the remote's `own()` in `compose.py` (2 tests failed), the outline seed in
`shown.py` (1 failed), the port's `fullOnHover` in `dynamics.js` (the new browser test failed). Breaking the port's
`fullOnHover` in `diagram.js` did not fail it: that is how I found the page draws only Dynamics.

Tests run, serially: `tests/test_parts_belong.py` (8 passed); `test_remote.py`, `test_remote_chain.py`;
`test_remote_proposals.py`, `test_remote_lines.py`, `test_remote_box_measures.py`; `test_remote_pair.py`,
`test_templates.py`, `test_upkeep_template.py`; `test_library_trust.py`, `test_library_provenance.py`,
`test_spec_systems.py`; `test_dynamics_view.py`, `test_correspond.py`, `test_graph_cli_web.py`: all pass. Ruff clean.

`tests/test_diagram_rendering.py` in full, under the watchdog with Playwright: the first run was stopped at its
20-minute limit. The second finished: 5 failed, 197 passed, rc 1 (30 min). Both of this branch's browser tests passed.
The five, run again alone (6 failed of 23: image-squeeze's line-links failed too):
`test_every_part_opens_its_panel_when_clicked_even_mid_redraw` (`stock:passed-changes`, `stock:unanswered-requests`),
`test_every_lines_panel_links_to_the_parts_it_joins[coordinator|software-factory|ticket-factory|image-squeeze]`
("link ... opened nothing"), and `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`
(the Model page lacks "Nothing waiting."). I judge them unrelated to this branch, but I did not prove it on main.
Each failing part is hand-written with no recorded owner, so nothing on it is relabelled. Every page change here does
nothing when a part has no `shown`. Panels and links use `label`, which is unchanged, and `details.js` is untouched.
The Model page test does not touch part labels. Round 1's full run (before main was merged) had only the coordinator
line-links failure, and it passed when run again. So these more likely come from main's merge or from this machine's
load. I could not check this: exporting main to `/tmp` to run them there (`git archive 2abe6348 | tar -x -C
/tmp/mainsrc`) was refused. They are not fixed here (lesson-13). Not run here: the unit suite, the other three
browser files, `demo_check` (no example changed).

## Where it stopped (round 3)

Main (277a9c6c) merged in. The one conflict, `ergostat/library/uses.py`, is resolved by keeping both: main's
`given_on` (a nested use's `with:` values marked LIBRARY when its template is `named`) is what `plan` is now handed,
and the branch's `(inst, short)` still goes with it as `mine`, so a nested use's system still records its outer
instance. 126 net lines of code outside `tests/`, `docs/` and `dev/` (`git diff --numstat 277a9c6c HEAD`).
No review findings were given this round beyond the conflict.

Tests run, serially: `test_parts_belong.py`, `test_templates.py`, `test_library_trust.py` (91 passed);
`test_library_provenance.py`, `test_remote.py`, `test_upkeep_template.py` (80); `test_remote_box_measures.py`,
`test_remote_lines.py`, `test_remote_pair.py` (31); `test_spec_systems.py`, `test_dynamics_view.py`,
`test_correspond.py` (28); `test_graph_cli_web.py` (32). Ruff clean. Of `tests/test_diagram_rendering.py`, only this
branch's two browser tests, under the watchdog with Playwright: 2 passed, rc 0. The merge touched no page code, so
the full file (30 minutes in round 2, with 5 failures judged unrelated there) was not run again here, nor the unit
suite, the other three browser files, or `demo_check`.

## Where it stopped (round 4)

Main (bf6dbebf) merged in. 126 net lines of code outside `tests/`, `docs/` and `dev/` (`git diff --numstat bf6dbebf HEAD`).
The only finding was the merge conflict, in two files:
- `ergostat/web/static/dynamics.js`, `sdSystem`: main's box is kept as it is (upkeep dash, the description in up to
  two lines under the name, the upkeep line). The one change from the branch is that the title is drawn by
  `nameOf(n)`, not `n.label`. The branch's old loop-count subtitle is dropped, as main dropped it.
- `tests/test_diagram_rendering.py`: both sides only added tests (the branch's two hover tests, main's two Open-all
  tests). All four are kept, each closing its own page.

Tests run, serially: `test_parts_belong.py`, `test_dynamics_view.py`, `test_graph_cli_web.py` (63 passed). Ruff clean.
Under the watchdog with Playwright, from `tests/test_diagram_rendering.py`: this branch's two hover tests (2 passed,
rc 0), `test_each_closed_system_box_says_what_the_system_is`, `test_modelling_is_drawn_last_set_apart_and_labelled`
and `test_a_module_counts_its_loops_in_the_side_list_not_on_its_box_and_draws_no_port_squares` (5 passed, rc 0).
`test_the_guides_last_frame_draws_its_boxes_as_the_live_diagram_does_and_says_it_is_drawing` passed.
`test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip` failed on most examples (20 of 21). The
reason is "tooltip on title: Drawn alike here with B27 …", a `<title>` on a loop marker's "N alike" text. Main's
commit 1208bfab adds it (`dynamics.js:457`), the same line is in bf6dbebf's `dynamics.js`, and this branch's diff to
main does not touch it. So this fails on main and is not fixed here (lesson-13). Not run: the rest of the browser
file, the other three browser files, the unit suite, `demo_check` (no example changed).
