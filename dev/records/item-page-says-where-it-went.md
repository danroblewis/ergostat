# item-page-says-where-it-went: An item says where it went in the model: the stocks it was counted in and the valve and block that moved it

depends-on: [kind-and-item-footprint-api]

Problem: the item page tells leasing three times (the Lease table, 'How it moved' pairs like review -> leased -> done that lose the state it was reviewed in, raw ergostat.lease.* events; shots/plan-ks-road-item-leased.png) and never says which stocks it was counted in, which flows and valves moved it or which blocks took it; nothing links to the diagram. The owner asks for what the item passed through.
Change: a 'Where it went' section after the header of pageItem (ergostat/web/static/pages.js:911), drawn from the `path` of /api/items/ID: one line the stock-and-flow way, in order: [todo 15s] =started (developer, run 2f02cb16, 4s)=> [in-progress 3s] =submitted=> [in-review] ... Each stock and valve is a link to the diagram with that part selected (filed Q36's address), each block a link to its agent page when it exists, each run a link to the Record; the final state is marked; rework shows as a repeated step with its attempt count. The current step of an item being worked says 'being worked by developer for 4m'. It replaces the lifecycle strip for items with a path; kinds nothing counts keep filed Q55's strip (Q55 is amended to cover uncounted kinds only) and say 'not counted anywhere in the model'. The path's current step is where the item is counted, with its link back: this is filed Q58's content, and Q58 is closed as superseded. The Lease table moves under it as a closed details 'Attempts (N)' (with filed Q54); the 'ergostat lease ITEM --redrive' command leaves the reader's text (Q12).
Definition of done:
1. On the roadmap fixture /item/ticket%2F<a done ticket> shows 'Where it went' naming todo, started, developer, in-progress and finished, reviewer, each a link.
2. A taken item's current step shows the block working it and for how long; no text of the section contains 'held'.
3. An item of an uncounted kind shows the sentence and no path.
4. No row of the page reads 'Not held Attempts'; the Lease table is inside the closed details.
5. At 390 px the strip wraps without horizontal scroll.
Files: ergostat/web/static/pages.js (pageItem), style.css, tests/test_items_page.py, docs/SPEC.md §5a.
Acceptance tests: test_an_item_page_shows_its_path (one link per step, in move order); test_an_uncounted_item_says_so.
Budget: 110 net lines.

Milestone: kind-and-item-pages. Owner items: 20 (what it passed through). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. `whereView` in ergostat/web/static/pages.js draws *Where it went* right after the item page's header.
It is drawn from `/api/items/ID`'s `path` and `/api/kinds/K`. Each stock and flow links to
`/diagram?view=dynamics&select=stock.S` (`flow.F`) and each block to `/diagram?view=blocks&select=block.B`. Each run
links to the Record. The final state has a double border. The current step says *being worked by B for T, run R*. A
kind nothing counts keeps the strip, with the line "Its kind, K, is not counted anywhere in the model." The lease view
is now a closed `details` *Attempts (N)*: "Taken by" replaces "held by", and "Not held" and the `--redrive` command are
gone. style.css makes the strip wrap. SPEC §5a has *Where it went, on the item's page*, and §9.5 points to it.
40 net lines outside tests and docs (budget 110).

Choices I made with nobody to ask (each the easiest to undo):
- **No page for an agent.** Ergostat has no page per agent: an agent is a panel, opened from the Agents page or a
  diagram. So "a link to its agent page when it exists" is read as: it does not exist yet, and the block links to the
  Blocks diagram with that block chosen.
- **Where the block comes from.** The done tickets in the roadmap fixture were never leased. A move's block is the
  step's lease when it has one. Otherwise it is the block whose `out:` names that flow, from the footprint's
  `taken_by`. For that the page also asks for `/api/kinds/K`. If that answer cannot be read, the page shows the old
  strip and makes no claim about the model.
- **Where the run link goes.** It opens the Record narrowed to this item over that step
  (`/record?item=ID&from=entered&to=left`). A run's own events are recorded under its agent's name, and `path` does
  not carry the agent.
- **Where the planner shows.** The flow that first brought the item in (roadmap: `planned`) leads the strip. The
  planner takes no tickets, so it is not named.
- **Q55's test moved.** Q55's lifecycle-strip test ran on image-squeeze's `session` kind, which is counted. It now runs
  on a small fixture, `lone`, whose `session` kind nothing counts, as the amended Q55 asks.
- **The 'How it moved' table** keeps its rows as they are. Only the Lease table part of Q54 is in this gap.

Tests: test_an_item_page_shows_its_path and test_an_uncounted_item_says_so pass. Each was broken by hand and seen to
fail:
- with the flow-to-block lookup removed, the link list loses `developer`;
- with the uncounted sentence removed, `.uncounted` is never drawn;
- with `flex-wrap: nowrap`, the strip is 969 px wide inside 358;
- with the details open, the closed-details check fails.

The *given back* wording for a nack or rework is not covered by a page test. Its steps are covered by
tests/test_footprint.py (`test_a_nack_is_a_repeated_step_with_its_attempts`).

tests/test_items_page.py: 69 pass and 1 fails, the same one in two runs:
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` times out waiting for the other project's
`#project` switcher entry on `/items`. That test reads the header and the project registry, which this branch does not
touch. kind-and-item-footprint-api's record reports the same failure. Running it on clean main was refused in this
session (`git worktree add --detach /tmp/maincheck main`).

test_diagram_rendering.py::test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes
passes: it reads the strip's arrows on an uncounted kind. Ruff is clean. Main is merged in: already up to date.

Build step, round 1: `[suites] build` failed with rc 5, not on a test. The branch changed only one test file,
tests/test_items_page.py. That file needs Playwright, which the build step does not install, so pytest skipped it at
module level and collected nothing. To fix it, tests/test_footprint.py has a new unit test,
`test_the_item_pages_where_it_went_joins_each_flow_to_the_block_whose_out_names_it`. It checks the data the new
section reads: `taken_by[].out` names each flow as `flow.X`, which joins to a path step's `flow`, and a taken item
carries its lease's holder, block and time taken. It runs without a browser, so the build step now has a test that
runs. Its file passes (10) and ruff is clean. The build step's own command (`scripts/affected_tests.py -- ...`) was
refused in this session, so it was not run here.

Round 2: the one review finding, fixed. A past run's link opened the Record over the step it left from. For a step
"taken from here" that window ends at the moment of the take, so it held none of the run's events. Now each run
link takes its window from that run's entry in `fields.lease.history`: `from=taken`, and `&to=ended` once the run
has ended. The current run's link stays open-ended. If a rollup has dropped the run's entry from the history, the
link opens from the step's start with no end. That window is too wide but still holds the run (the more reversible
choice). SPEC §5a now says the same.
- Test: the roadmap fixture's `ticket/e2-docs` now has a nacked first run (`r0bbbbbb`, taken 40 s before, given back
  15 s later) before the current one. test_an_item_page_shows_its_path checks five things: the *given back (nack)
  (developer, run r0bbbbbb)* move, that run's link (`from=taken&to=ended` as the API gives them), the current link's
  `from` (that lease's `taken`, no `to`), *attempt 2*, and *Attempts (2)*. This also adds the page assertion for the
  *given back* wording that round 1 lacked. I broke it by hand: with the history lookup set to `null`, the test fails
  on the past-run link.
- tests/test_items_page.py: 72 pass and 1 fails. Run alone, test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart
  fails, the same timeout on the `#project` switcher as in round 1 (unrelated: header and project registry). That
  test failing alone, plus test_an_item_page_shows_its_path passing alone, puts it as the full file's one failure.
  tests/test_footprint.py: 10 pass. Ruff is clean. Main: no newer commits in this clone than the round-1 merge.
- `uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_items_page.py::test_the_header_...` with
  no watchdog was refused. Run under `scripts/suite_watch.py`, it went through.
- Size: about 45 net lines outside tests and docs (budget 110).
