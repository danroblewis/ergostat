# open-all-stops-at-what-fits: 'Open all' on a model that will not fit opens to the system boxes and says 'Into' for the rest

depends-on: []

Problem (R8 piece 6): 'Open all' on big shows about one system on screen and takes the longest layout the page can ask for (shots/story-7-h2-open-all.png, ixd-big-open-all-fit.png); on the-job in Blocks it left a blank canvas after 10 s (plan-notation-job-openall-blocks-fit.png). The reader asked to see everything and gets less.
Change: before opening, the page estimates the open drawing's size from the graph (parts and lines per system, already in the top-level answer). When everything open would exceed what fits at an 11 px text floor by more than a set factor (or the line count exceeds the routing bound), 'Open all' opens one level: nested systems stay closed boxes (each with whatever its box shows), and a line on the canvas says 'Opened to the first level: N systems stay closed. Use Into to open one.' with each closed box keeping its Into control. The ⋯ menu's wording says what it will do ('Open all (first level)'). A model that fits opens fully as today.
Definition of done:
1. On :8797 'Open all' leaves nested systems closed, shows the sentence with the right count, and reaches attached lines within 3 s.
2. On :8791 (fits) it opens everything as before.
3. On :8792 ?view=blocks it never leaves a blank canvas.
4. The address records what was opened (open= lists them), so a reload shows the same.
Files: ergostat/web/static/diagram.js (the menu action and estimate), style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-3.
Budget: 60 net lines.

Milestone: r8-open-fit-large. Owner items: R8 piece 6. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (round 1), in `ergostat/web/static/diagram.js` (`openPlan`, `openLevelNote`, the ⋯ menu's item) and `style.css`
(`.open-level`): about 32 net lines, inside the 60.

- The estimate: the parts the open drawing would hold are counted from the answer as it is (each open part 1, each
  closed box its `parts`; terminals and ports 0). Measured on eight examples at 1600x1000 the count was exact, and
  each part took 30,000 to 110,000 px² of the open layout (median about 60,000: `PART_AREA`). It "will not fit" when
  `parts × 60,000` is more than 4 times (`FIT_OVER`) what the canvas shows with its 12 px text drawn at the 11 px floor
  (canvas area ÷ (11/12)²), or when about 1.3 lines a part would pass 600 lines (`LINES_MAX`, the tier past which
  avoid.js already lowers its crossing penalty for time). At 1600x1000 that is about 97 parts.
- Too big, and with systems nested below the first level: the menu reads 'Open all (first level)' (hint: 'N within
  stay closed') and goes to `open=<the first level, by name>`; the canvas says 'Opened to the first level: N systems
  stay closed. Use Into to open one.' whenever what is open is exactly that first level, so a reload of the address
  says it again. Anything else (fits, or nothing nested) is 'Open all systems' and `open=*`, as before; `open=*` typed
  in the address still opens everything (the snapshot and the tests rely on it).
- Choices made without an answer (the most reversible, each one line to change):
  - The ports are the owner's hand-started servers and the clone does not say which project each serves. The tests
    stand in with the-job for :8797 and :8792 (too big, ten systems nested in `job`) and software-factory for :8791
    (fits, a system nested in another).
  - big (named in the Problem) is flat: its seven systems are all first level, so the first level is everything and
    'Open all' on big opens everything as before. This gap does not help big; making a flat model open less would
    need its own rule (what to open when the first level is itself too big).
  - In Blocks a closed system has a '+' and no Into, so the sentence there says "Use a block's + to open one." (one
    word changed from the definition, so it does not name a control the drawing lacks). No Into was added to Blocks.
  - A snapshot page keeps 'Open all systems' (`open=*`): the snapshot holds only that answer, not the first level.
  - The sentence is shown for any page whose open set equals the first level of a model too big to fit, also when the
    reader opened those systems one by one (it is still true then).
- Acceptance tests (tests/test_diagram_rendering.py):
  `test_open_all_on_a_model_that_will_not_fit_opens_the_first_level_and_says_into_for_the_rest` (1, 3 and 4: in
  Dynamics and Blocks, the label, `open=job,modelling` in the address, each of the ten nested systems a drawn closed box
  with its Into or +, the sentence with 10, the lines routed within 3 s of the click in Dynamics, and all of it again
  after a reload; marked serial for the 3 s bound) and
  `test_open_all_on_a_model_that_fits_opens_every_system_as_before` (2).
- Seen to fail (lesson 9): the count off by one (the sentence assert failed); `FIT_OVER` at 0.5 (the fits test failed:
  'Open all (first level)' offered on software-factory); the sentence kept in memory only, not read from the address
  (the reload check failed).
- Run here (in the container, serially, under suite_watch): both acceptance tests pass (2 passed, 22 s);
  tests/test_style_tokens.py and tests/test_graph_cli_web.py pass (37); ruff is clean. The whole of
  tests/test_diagram_rendering.py, twice: 7 failed / 195 passed, then 5 failed / 197 passed. None of them uses the
  menu item. Each loads `open=*` from the address (the page draws no note there), or is the Model page:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: routing `open=*` took about 36 s
    against 20 s; `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: drawn in 3.5 s against 2.5 s. These are
    time bounds in a 40-minute serial run. The stress test passed when run alone (37 s).
  - `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it` (parts on
    the outline of frame:factory after the drag, line 1738, before the test opens the ⋯ menu) and
    `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` ('Nothing waiting.', line 3305;
    earlier reviews' records name this Model page test as failing): both failed again when run alone.
  - Not checked on main: `git checkout main -- ergostat/web/static/diagram.js ergostat/web/static/style.css` (to run
    them on main's page) was refused here. The factory's rerun on clean main must settle them (lesson 10, 13). The
    other three browser files, the unit suite and a merge of main were not run here (by the rules, the factory and
    the merge queue run them). There is no remote here, so local `main` is the base; the branch was cut from it and
    main has not moved in this clone.
