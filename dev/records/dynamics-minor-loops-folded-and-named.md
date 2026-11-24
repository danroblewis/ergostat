# dynamics-minor-loops-folded-and-named: Dynamics draws the named loops and one per goal; minor loops are listed and drawn when selected; a loop may be named in the model

depends-on: [dynamics-goals-and-loop-folding-proposal]

Problem (R5 pieces 4 and 5): on software-factory product all 18 elementary loops are drawn, named by their paths ('all-live via regressions and churn and asks'), markers and names piled on each other and on the users stock; '+1' on a marker is unexplained (shots/story-6-g4-R2.png, story-6-g4-B1.png, sdxb-annotated-product.png). A reader cannot find the two or three mechanisms that explain the system.
Change, as the proposal settles: (1) the drawing shows a marker only for loops named in the model and one loop per goal (the balancing loop through its gap); every other loop is 'minor': listed in the side list's folded 'minor loops (N)' and drawn (marker and lit path, in the accent as any trace) only while selected or hovered there. '+1' is removed. (2) a `loops:` entry in the model may name a loop by its parts (SPEC §12a); the diagram prints the name at the marker, the panel shows the path; an unnamed drawn loop is 'B3' with its goal's name. (3) the software-factory demo names product's main loops (e.g. 'word of mouth', 'support load'). (4) the loop that dominates now (/api/dominance) is named at the head of the list (R5 piece 8's second half).
Definition of done:
1. On :8796 ?system=product at most the named loops plus one per goal have markers (count asserted against the model), and no marker text contains '+'.
2. Selecting a minor loop in the list draws its marker and path; deselecting removes it.
3. A named loop shows its name on the diagram and its path in the panel.
4. The box's and list's loop counts agree (filed Q22) and say 'N named, M minor'.
Files: ergostat/dynamics.py, ergostat/spec/causal.py (names), ergostat/web/static/dynamics.js, demos/software-factory (loop names), docs/SPEC.md §12a, tests/test_dynamics_view.py, tests/test_diagram_rendering.py.
Acceptance tests: unit: naming and the minor flag; browser: 1-3 on :8796.
Budget: 150 net lines.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 pieces 4, 5. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: done items 1-4, change points (1)-(4), SPEC §12a. Size: 85 net lines outside tests, docs and dev
(`ergostat/dynamics.py` +35, `web/static/dynamics.js` +29, `keys.js` +1, `style.css` +1, `examples/software-factory/
product.yaml` +19), within the 150 budget.

What it does:
- `dynamics.py`: each loop gets `named` (a `loops:` entry names it), `goal` (`seeking()`: each goal's shortest
  balancing loop through `gap:<goal>` as drawn; ties go to a named loop, then the first flow's name, then the loop's
  name; a loop two goals would take is the first goal's), `minor` (neither), `shown` (its name if named, else its goal's
  name), and `systems` (every system any part is in). `counted()` is the one count, the loops with a part in a system,
  as named and minor. `finish()` puts it on each system node (`loopCount`) and on the graph for its `focus`. Labels now
  number the drawn loops before the minor ones, so the canvas reads B1-B5, not B21-B25.
- `dynamics.js`: only drawn loops crowd the placement. A minor loop's marker is drawn but hidden (CSS
  `.loop-marker.minor:not(.on)`). It shows, in the accent, while its row is pointed at or chosen, and has no name on the
  canvas. The marker's "N alike" text is gone. The side list's heading is "Feedback loops N named, M minor" and lists
  the drawn loops, then a folded "minor loops (N)", then "N of unknown polarity" (no '+'). The list holds the loops with
  a part in the system drawn alone, or every loop drawn from the top. A loop's panel gives its path (`.loop-path`) and
  says whether it is named, a goal's, or minor. A closed system's panel says "Feedback loops with a part in it: N named,
  M minor". "Dominant now: <label> <name> (at <stock>)" heads the list: of the list's loops, the one dominant in the
  last bucket at some stock with the highest |relative score|. It is asked once per address, never on a poll.
- `keys.js`: a minor marker is not a keyboard stop (its list row is its button). Without this, Shift+Arrow landed on a
  hidden marker and the focus fell to BODY. `style.css`: a minor marker has no pointer cursor.
- software-factory `product.yaml`: the proposal's five names (bug-fixing, regressions, features-shipped, users-won,
  long-tail). They make bug-fixing, features-shipped and users-won the three product goals' loops.

Measured (unit tests): software-factory has 34 loops, 11 named and 23 minor. Product has 18 (5 named, 13 minor), on its
box and in the list at `?system=product` alike. Markers at `?system=product`: 18 with the CSS rule removed (all
of them, as before); with it, the five named loops are among those shown and at most 14 (named plus goals) may be, as
asserted. The exact number shown was not printed.

Choices made alone (the most reversible):
- No cap of 9 markers and no dominance ranking of markers: the proposal adds them, but this definition does not ask
  for them. Ties between goal-seeking loops skip the proposal's "then by dominance": the graph has no replay, and the
  definition's done items do not need it.
- The definition calls the count "named". A drawn goal-seeking loop with no `loops:` entry counts as named, because
  it is shown by its goal's name. Unknown-polarity loops count in M (or in N when named), and are listed in their own
  fold.
- The panel keeps the loop's §12a name as its subtitle (tests and links key on it) and adds the path under it.
- A minor marker is placed as before (inside its loop) but takes no room from the drawn ones. Two drawn loops alike
  still share one marker, now with no count on it; their panel names the others.

Tests: unit `test_the_named_loops_and_one_per_goal_are_drawn_and_every_other_loop_is_minor` and
`test_a_system_s_box_and_the_list_drawing_it_alone_count_its_loops_alike` (tests/test_dynamics_view.py). Browser
`test_dynamics_marks_the_named_loops_and_one_per_goal_and_a_minor_loop_only_while_chosen` (done items 1-4, on
software-factory `?system=product` served on a free port, not on :8796). Each was seen to fail with the code it
guards broken: the CSS rule removed (18 markers shown), the named-first tie removed (users-won has no goal), and every
loop counted on each box (11/23 against 5/13). Existing tests changed to fit: the unknown fold's summary has no '+';
the drag test follows `long-tail` (`missing-ops` is now minor and hidden); the R2 test asserts no count on any marker;
the PNG export test's "shown" skips elements under an undisplayed group, because Chromium's `checkVisibility()` passes
them and the export already drops them.

Run here and passing: tests/test_dynamics_view.py (25), tests/test_daemon_docs.py (`check` on every example),
tests/test_guide.py, tests/test_export.py (unit), tests/test_correspond.py, tests/test_graph_cli_web.py,
tests/test_model.py, tests/test_spec_systems.py. Browser: the new test; the SD-symbols test (3 examples), markers inside
their loops, the closed box's description, marker drags with its system, R/B only when signed, leftover ellipsis, the
guide, marker lights its loop, a lit loop lets go, module counts, the off gap's red marker, a loop chosen in both
panes, markers hidden and remembered, one tab stop. Ruff clean. Local `main` merged (already up to date).

Failing here, not this gap's (lesson 13):
- `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`: the word "goal" in the
  side list, from the attention cards and the rows' "serves goal" that main already writes. Earlier records report
  the same failure on main. This branch's own new words avoid it.
- `test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode`: its Dynamics half now
  passes. Its Blocks half finds 6 legend rows where it wants more than 10, as earlier records report on main.
- `tests/test_export.py::test_the_export_menu_downloads_the_model_and_the_loops`: it waits for a visible `.looprow`
  and reads a `.side h3` "Feedback loops". Both have been stale since the list became a folded `details`.
- `test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard`: after the keys.js fix it passed 2 of
  5 runs alone. The other 3 failed at one step: after Enter opens factory, the focus is on BODY before 'Open intake' is
  stepped to. My reading: a second redraw replaces the focused element, and keyable's fallback refocuses only by the
  old key ('Open factory', now 'Close factory'). Earlier records report this test failing on main at other steps. Not
  proven: running main's files for comparison was refused here (`git checkout main -- ergostat/dynamics.py
  ergostat/web/static/dynamics.js ...`), so the factory's rerun on clean main should decide it.

Not run: the whole unit suite and the four browser files (the factory runs them), and `scripts/demo_check.py
software-factory`, which was refused here (`uv run python scripts/demo_check.py software-factory`, with and without
the watchdog and `--shots`). The new `loops:` entries pass `check` (test_daemon_docs).
Left, outside this definition: `/api/export`'s "drawn" column still means two parts drawn, not minor or not; the
proposal's marker cap and dominance ranking.

### Round 2: main (e8669794, with goals-and-loops-cross-referenced) merged

The only finding was the conflicts with main, in docs/SPEC.md, dynamics.js, style.css and tests/test_dynamics_view.py.
Each now keeps both sides:
- Main gives each loop `goal` (the goal it closes, from the graph). The branch had written over that field with the goal
  a loop seeks. That field is now `seeks` (dynamics.py, dynamics.js, the branch's tests, SPEC §12a), so main's "Serves
  goal X" link and the branch's "the loop seeking the desired level of X" both stand in a loop's panel.
- The list's summary keeps both counts: "Feedback loops 11 named, 23 minor, 28 close a goal" (`.sd-count`, then main's
  `.sd-loops-head`). The goals that close are counted over the list's loops. Main's cross-reference test now reads
  ", K close a goal", and checks that the named and minor counts add up to every loop.
- style.css: the minor rules are kept, and main's `--sd-ink-2` name tone too. `.marker-more` is gone with the count it
  styled.
- SPEC §12a: main's cross-reference paragraph, then the branch's "Drawn" paragraph, with the summary example updated.
- A merge break that main's own unit test found (`test_each_loop_through_a_gap_names_its_goal_and_the_goal_names_its_loops`,
  B2 against B1): `loops/NAME` numbered loops without the drawn-before-minor order, so a goal's panel and the diagram
  disagreed. Now `graph.goal_loops` takes `dynamics.drawn_labels` (+10 lines), the labels as the view prints them.

Run after the merge, passing: tests/test_dynamics_view.py (27), test_graph_cli_web, test_correspond, test_guide,
test_model, test_spec_systems, test_daemon_docs. Browser: this gap's acceptance test, main's goal↔loop link test, the
SD-symbols test, marker lights its loop, module counts, marker moves with its system, R/B only when signed, markers
inside their loops, a lit loop lets go, markers hidden and remembered, leftover ellipsis, both panes, "a goal is called a
goal", and the keyboard test (passed this run). Ruff clean.
Still failing, as in round 1 and not this gap's: the "speaks system dynamics" test (it matches "open · goal …" in main's
attention cards; this branch's summary words are stripped by main's own SD_GOAL_SAID), the PNG export's Blocks half (7
legend rows where it wants more than 10), and tests/test_export.py's export menu test (it waits for a visible
`.looprow`, which now sits in a folded list).
Not run: the whole unit suite, the four browser files, and demo_check.

### Round 3: 'Dominant now' kept across a redraw

The one finding (blocking): `sdDominant` filled its line only when /api/dominance answered, into the element of the
build that asked. Every later redraw (poll, `redrawSide`) patched the page from a new, still-empty element, so the line
was wiped after the first refresh. Now the answer is kept (`S.sdDom.value`, per address). The line is built from it on
every build, and the list is redrawn once when the answer first arrives. An answer that comes back after the address
changed is dropped. dynamics.js: +17/-12 lines.
New browser test `test_the_dominant_loop_heads_the_list_after_the_side_is_redrawn` (tests/test_diagram_rendering.py):
it fakes /api/dominance, waits for "Dominant now: B7 bug-fixing (at users)", calls `S.redrawSide()` three times and
asserts the line each time, and asserts the dominance was asked once. With the old function put back it failed on the
first redraw (line ''). With the fix it passes.
Run, passing: the new test, this gap's acceptance test, the R/B-only-when-signed test (browser);
tests/test_dynamics_view.py (27). Ruff clean. Local `main` (b20756c7) is already merged. Not run: the whole unit
suite, the four browser files, and demo_check. The round-1/2 failures listed above that are not this gap's were not
run again.

### Round 4: main (d0f95413) merged

The only finding was the conflict with main in dynamics.js. It sat at one place: the branch's `sdCount` and
`sdDominant` and main's new `FRAME_GLYPH` (the open-system frame legend glyph) were added in the same spot. Both are
kept, unchanged. Neither side's code changed.
Run after the merge, passing: tests/test_dynamics_view.py (27). Browser: this gap's acceptance test, the dominant-line
redraw test, the SD-symbols test (3 examples), the frame test (open system framed by its corners) and the exported
Blocks legend's frame glyph test. Ruff clean. Not run: the whole unit suite, the four browser files, and demo_check.
The failures named in rounds 1 and 2 that are not this gap's were not run again.
