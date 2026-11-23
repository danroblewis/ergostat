# goal-row-one-renderer: One goal row: the server says a goal's word and columns once, and one function draws the row wherever a goal is listed

depends-on: [goal-state-says-its-system-and-upkeep, perf-goals-page-asks-once]

Problem: the same goal is about to be drawn as a row in four places by four gaps: the Goals page (ergostat/web/static/pages.js:20-63, whose columns perf-goals-page-asks-once now fills from one answer), the closed box's rows (R1), the Dashboard's goals panel (owner item 18) and the side list; and its state is about to be worded by the Dynamics gap mark, Blocks' e label, the header and the evidence panel's first line. Without one owner the surfaces will show different columns, status words and trend logic for one goal: the review's B2 and B3 failures ('agrees everywhere'), split across views.
Change: (1) server, in state.snapshot: each goal's entry gains `word`, the one word a reader sees for its state. Now: holding | off | open | unknown, straight from status (later gaps widen the set to approaching, falling behind, flapping, in grace; they change this function only). It also gains `row`: {measure (the stock's name), value, unit, bound_words (filed Q23's writing when landed, else today's), trend: null, expected: null}; trend and expected are filled by later gaps, never by page code. The loops answer of perf-goals-page-asks-once carries word, row, the points and the performance word. (2) page: a new ergostat/web/static/goalrow.js exports goalRow(goal, {columns}) returning the cells (status word with its mark, name as the link to the goal's evidence, measure, value, bound, sparkline from the points with the bound dashed, performance, expected) and goalWord(goal) for places that print only the word. pageLoops draws its rows with it (same columns as today, so no reader-facing change beyond the word coming from the server). (3) rule, enforced by a test: no page script maps status to a reader word or formats a goal's value against its bound itself; every surface that prints a goal's state calls goalWord or goalRow. The gaps that add surfaces (dynamics-box-goal-rows, dashboard-page-v1, blocks-status-without-colour, dynamics-off-status-on-the-part, goal-rows-say-approaching-and-expected, evidence-panel-reads-as-a-runbook) depend on this and fill fields rather than redrawing the row.
Definition of done:
1. /api/loops entries carry word and row on every demo; word equals the status mapping.
2. The Goals page's rows are drawn by goalRow and look as before (a screenshot comparison on a fixture within tolerance, or the existing page tests unchanged).
3. The side list's goal lines and the header's tooltip read goalWord.
4. A test greps the static scripts: no `status === 'off'` or `'holding'` literal used to make reader text outside goalrow.js (row styling by class excepted).
5. A snapshot file draws the same rows offline.
Files: ergostat/state.py, ergostat/web/server.py (loops answer), new ergostat/web/static/goalrow.js, ergostat/web/static/index.html (script tag), pages.js (pageLoops), diagram.js (side list lines), tests/test_runner_and_state.py, tests/test_graph_cli_web.py, a browser test.
Acceptance tests: unit: word and row for holding, off, open and unknown goals; browser: the Goals page on a fixture with one of each shows the four words, each equal to /api/loops.
Budget: 120 net lines.

Milestone: goals-not-loops. Owner items: Decision: goal, not loop (one row for the Goals page the owner renamed, the box rows of R1, the Dashboard's goals panel of item 18; R6 piece 8). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. What is in the branch:
- `state.goal_row` (ergostat/state.py), called in `snapshot` for every goal: `word` and `row` {measure, value, unit,
  bound_words, trend: null, expected: null}. /api/loops spreads the snapshot's entry, so it carries them with no
  change to server.py; the snapshot file's `loops` answers carry them the same way.
- ergostat/web/static/goalrow.js: `goalWord`, `goalRow(goal, {columns})`, `goalLine` (the side list's sub line),
  `goalRank` (the order: off first), `exceptional` (moved from util.js) and `GOAL_WORDS`. pageLoops draws its rows
  with goalRow, the same eleven columns as before.
- Callers moved to goalWord: the Blocks side list's lines (word and sub line), the diagram caption's off count, the
  suggestions' open-when-off, the header's off count, a goal's panel heading and status (details.js openLoop) and the
  comparator line's status (details.js). The header gains a tooltip naming each goal off by its word (item 3: the
  header had no goal tooltip before).
- blockdiagram.py passes `word` into the Blocks graph's loops, so the side list reads the server's word.

Choices made alone (the most reversible, each one place to change):
- `stale` is kept as a word: status can be `stale` today and the Goals page showed it, so dropping it would change
  what readers see. The set is `state.WORDS`; anything else is `unknown`.
- bound_words is today's: the setpoint and its band (`<= 80 (+2)`); goalrow.js applies `op()` for ≤/≥ as before.
  Filed Q23's writing has not landed.
- The performance word stays as control.js's `performanceWord`, called from goalrow.js (`goalPerf`), not moved to the
  server: the loops answer carries `perf`, and the page's wording of it is unchanged.
- goalWord falls back to the status when an answer has no `word` (a snapshot file made before this, or the Dynamics
  graph's loops, which do not carry it); that mapping exists only in goalrow.js.
- The grep test (tests/test_graph_cli_web.py, test_no_page_script_words_a_goals_state_but_goalrow) allows two lines by
  name: openSystem's system status (a system box's state, not a goal's) and the Items lease line `x.how || "holding"`.
  The tone maps (`{off: ..., holding: ...}[x.status]` colours) are styling and do not match its patterns.
- Not moved: diagram.js's colour maps (styling); the Dynamics side list's "Goals off" lines, which the server words
  (state.attention).

Tests: unit test_each_goal_says_its_word_and_its_row_once (tests/test_runner_and_state.py, fixture FOUR_GOALS in
tests/conftest.py); test_every_examples_loops_answer_carries_each_goals_word_and_row and
test_no_page_script_words_a_goals_state_but_goalrow (tests/test_graph_cli_web.py); browser
test_the_goals_page_says_each_goals_word_as_the_server_does_live_and_from_a_snapshot (tests/test_diagram_rendering.py),
which was seen to fail when goalRow's status cell was broken for open goals. Net code lines: +66 −33.

Round 2 (the review's one finding):
- The header's tooltip (util.js refreshHeader) named every goal off, upkeep goals too, while #running counts only the
  system's (state.goals_off). It now leaves out goals with an `upkeep`, the same rule as the count, so '1 goal off'
  sits over a tooltip naming that one goal. Test: test_the_headers_tooltip_names_the_goals_its_count_counts
  (tests/test_items_page.py: first-loop with inbox-short off and the two modelling goals off); seen to fail before the
  fix (the title named requests-handled and model-fits too) and pass after.
- Done item 3's side list: the goals-page browser test now also reads the Blocks side list's lines on the four-goal
  fixture and asks each word to be /api/loops' (holding left unsaid, as the side list does); seen to fail when the
  side list printed `off` for an open goal.
- Not run to green: tests/test_items_page.py as a whole has six other failures in this container: the item-set
  panels (test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set,
  test_the_model_changes_are_found_by_heading_search_and_panel, test_a_valves_leased_items_are_listed_live,
  test_a_snapshot_lists_a_parts_items_and_opens_its_set, test_a_set_left_out_of_a_snapshot_says_so; itemsets.js and
  dynamics.js, which this branch does not change) and
  test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart at the project switcher's entry for another
  project (projects.py, unchanged; its header assertions before that line pass). A run on clean main was refused in
  this session (a git worktree and checking out main's files were both denied), so that they fail on main too is
  read from the diff, not seen.

Round 3: the merge of main (ead497d1) conflicted in details.js and pages.js.
- Main (ui-a-one-sided-limit-is-drawn-and-named-as-a-limit) changed the Loops rows that the branch draws with goalRow:
  the bound cell became `holdText` ("limit ≤ 0", "setpoint 5 ±1"), the column header "setpoint" became "r", and the
  "how far" title now says "its limit" or "its setpoint". Those three now live in goalrow.js's `bound` and `far` cells
  and in pageLoops' header, so the page reads as main has it. The loop panel's "holds" row takes main's `holdText`,
  and its status row takes the branch's `goalWord`. The side list's sub line (`goalLine`) is left as the branch had it.
- Ran: ruff (clean); the three acceptance unit tests; tests/test_runner_and_state.py (45 passed); in the browser,
  under the watchdog, the goals-page acceptance test, main's test_a_one_sided_limit_is_drawn_and_named_as_a_limit,
  test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks and
  test_the_headers_tooltip_names_the_goals_its_count_counts (all passed, rc 0). The whole suites are left to the factory.
- A heredoc append to this file with `cat >>` followed by a commit, given as one Bash command, was refused in this
  session; this section was written with the editor instead.

Round 4: the merge of main (5411f137) conflicted in diagram.js and pages.js.
- pages.js: main gave the Loops table its caption ("Loops"); pageLoops keeps goalRow's rows and passes main's caption.
- diagram.js: main closed the suggestions by default (no longer open when a loop is off) and folded the side list's
  loops into `details.loops`. Both are kept as main has them. The branch's goalRank order and goalWord/goalLine lines
  now sit inside the fold. The round-1 note that the suggestions' open-when-off reads goalWord no longer applies:
  main removed that rule.
- Ran: ruff (clean); the three unit acceptance tests (passed); in the browser, under the watchdog (rc 0), the
  goals-page acceptance test, test_the_headers_tooltip_names_the_goals_its_count_counts,
  test_the_side_panel_with_nothing_waiting_opens_on_the_legend_and_folds_the_rest,
  test_a_suggestion_appears_when_it_has_a_verdict and test_a_one_sided_limit_is_drawn_and_named_as_a_limit (all
  passed). The whole suites are left to the factory.
- Refused in this session: a `git diff $(git merge-base HEAD MERGE_HEAD) MERGE_HEAD ... | head; cat goalrow.js`
  compound, and the browser run when given with `| tail -8; echo rc=$?` (it was run again without them).
