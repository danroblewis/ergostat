# ui-the-address-holds-what-is-selected-and-the-windo: The address holds what is selected and the window

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q36 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /loops, /diagram, /record, /items

**The problem:** Selecting a goal or changing the window leaves the address at /loops; a pasted link shows no panel and 'Last 1h'. A stock selection on the diagram is not in the address. Changing the window closes the open panel and blanks the table.

**The change:** Write ?select=, ?window= (and ?filter= on Record) with replaceState and read them on load. Changing the window keeps the panel open and shows 'Loading…' in the table.

**User stories it serves:** H6, F4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/loops select api-q2-low and choose Last 6 hours; opening location.href in a new tab shows the same panel and window; on the diagram selecting a stock adds 'select=' to the URL and a reload shows it ringed.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built, within budget (about 30 net lines in `ergostat/web/static/`: util.js, main.js, details.js,
pages.js, interact.js, diagram.js; no template or style change was needed).

What was built:
- `?select=`: on /loops, the loop whose row is clicked (read on load: its panel opens; the panel's × or Escape takes
  it out of the address). On /diagram, the parts chosen (`S.sel`, e.g. `select=stock.inbox`), written by `choose()`,
  read on load so the draw rings them, and carried by the diagram's own view/system/open links.
- `?window=`: written when a window is chosen (omitted for the default 1h), read on load, and carried to every page
  gone to by `navigate` or `replaceRoute` (so the Items page's own filters keep it).
- `?filter=` on /record: written on Filter or Enter; read on load (the older `?type=` links still work; a new filter
  replaces `type=` in the address).
- Changing the window no longer closes the panel: `route(true)` skips `closeDetail()`, and the open panel is asked
  again in the new window (`S.again`, set by openNode, openLoop and openAgent). The Loops, Record and Items tables say
  'Loading…' until their first answer.

Choices made without anyone to ask (each the most reversible I could see):
- The Record page already uses `window=1` to mean "only events in the window" (links from itemsets.js). Kept as it
  was: a page-wide window is read only when the value is a window name (10m, 1h, 6h, 1d, 7d), and choosing a window on
  a Record page whose address says `window=1` leaves the address as it is.
- The acceptance names api-q2-low on :8797, a demo's goal that no test has; the browser test uses first-loop's
  inbox-short and its inbox stock in place of it.
- On the diagram, a reload rings what was chosen; it does not reopen its panel (the acceptance asks for the ring).
- A panel opened on an edge or a line (not through openNode, openLoop or openAgent) stays open on a window change
  but is not asked again.

The test: tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window. It passes. Each
of six breaks made it fail: closeDetail() on a window change again; no 'Loading…' in the Loops table; the diagram
not reading `select=`; main.js not reading `window=`; the Loops page not reading `select=`; the Record not reading
`filter=`.

Browser files run here, serially, under the watchdog, with Playwright (none skipped):
- tests/test_items_page.py: 21 passed, rc 0. tests/test_page_refresh.py: 8 passed, rc 0.
- tests/test_page_polling.py: 16 passed, 1 failed on the first run:
  test_a_page_left_open_does_not_grow[diagram?view=dynamics&open=*] (long-task p95 608 ms against a bound of 550).
  Run again, the whole test function (10 pages) passed, rc 0. A timing bound under load; that page's polling is
  not code this branch changed.
- tests/test_diagram_rendering.py: 196 passed, 5 failed (rc 1), and none of the five is shown to come from this change:
  - test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back: passed when run again alone.
  - test_a_big_tangled_model_lays_out_in_time_and_cleanly: fails again alone, "[open=*] took 2968ms to draw" against
    LAYOUT_BUDGET_MS 2500. That is ELK's layout time on this container, and the branch does not touch the layout.
  - test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze]: layout and size checks on views
    opened with no `select=`. Not run again, because named_tests.py does not accept a parametrised id.
  - test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page: fails again alone at line 3305
    ("Nothing waiting." not on /model after an accept). The Model page and its queue are not touched here, and it
    is opened with a fresh goto (no window carried). Running it on main to confirm was refused (a /tmp worktree of
    main), so whether it also fails on main is not shown here.
- Not run here: the unit suite (not touched: no Python changed), and a merge of main (main is the clone's base,
  unchanged since).
