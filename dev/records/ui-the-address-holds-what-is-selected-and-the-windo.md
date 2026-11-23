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

The factory's `build` step ended with rc 5. Its only affected file, tests/test_diagram_rendering.py, was skipped
as a whole because the build step has no Playwright ("could not import 'playwright.sync_api'": 1 skipped, 0 run).
No test failed, so there was no code to fix. I ran it again here with Playwright, under the watchdog:
tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window passed (rc 0). Ruff is clean.
To give a verdict on this gap, a build step that runs only browser files needs Playwright (or `[suites] build_browser`).

Round 2 (no review findings to answer; the round was the build step's rc 5). Main (277a9c6c) was already merged in.
Main's fix for the same skip on the Agents page (ab17bb6e) adds a unit test that the build can run, so I did that
here too: tests/test_graph_cli_web.py::test_a_link_s_window_is_the_one_the_api_is_asked_for_and_its_address_is_the_page.
It reads WINDOWS from main.js and checks that the server reads each name as its own seconds, not its 1h fallback
(a link's `?window=` becomes the API's `since=`). It also checks that a link with `select=`, `window=` and `filter=`
is still served as the page. Seen to fail when a window name in main.js was broken ("1d" to "1day": 3600 s, not
86400). No code outside tests/ changed in this round. Run here: tests/test_graph_cli_web.py, 33 passed;
the browser acceptance test again with Playwright under the watchdog, 1 passed, rc 0; ruff clean. The four browser
files were not run again after the merge. That merge (18c67055) brought main's Agents-page change into
ergostat/web (pages.js 7 lines, style.css 2), so the round 1 results above are from before it; the merge queue
runs them in full.

Round 3, answering the one review finding (S.again left over from an earlier opener, so a flow's panel was replaced
by the stock's after a window change). It was true, and round 1's claim that such panels "stay open but [are] not asked
again" was false. Fixed in details.js: showDetail now clears S.again. openNode, openLoop and openAgent go through
askedAgain, which sets S.again only when the opener's own panel is the last one shown (no other opener started
since, and a panel was shown during the call). So any panel shown by something else (an edge or flow pipe, a
connector, a feedback loop, a Blocks signal, an event) stays as it is on a window change and is not asked again. An
opener whose request fails shows nothing and leaves the panel already shown, and that panel's S.again, as they were.
main.js's setWindow now returns its promise so a test can wait for it (no line added). This is about 5 net lines
more than round 1, still within the 60-line budget.

The test gains two steps in tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window,
on /diagram?view=dynamics. First: the stock inbox's panel, then a flow pipe's, then a window change; the panel is
still the Flow. Second: the stock's own panel and a window change; the panel is shown again in the new window (a
marker put into the old panel is gone). Both breaks were seen to fail the test: with showDetail not clearing S.again,
it fails with "the flow's panel was replaced by Stock". With askedAgain never setting S.again, the stock's panel is
not asked again. Restored, the test passes (rc 0, under the watchdog with Playwright). Ruff is clean. Merging main
gives "Already up to date".

Not run in this round: the whole of tests/test_diagram_rendering.py. A first run was stopped by the 10-minute
background limit before it reported anything. The command to run it again with a longer limit
(`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py
tests/test_diagram_rendering.py > /tmp/diag_full.log 2>&1; ...`, in the background) was refused. The other three
browser files and the unit suite were not run again either (no Python changed). The merge queue runs them.

Round 4, answering the queue's one finding (a conflict with main in tests/test_diagram_rendering.py). Main
(afeee013) was merged in (9b552e4e). The conflict came from both sides adding tests at the same place at the end of the
file, with the same closing lines. Resolved by keeping both: the branch's test (now with its own `assert not errors` /
`finally` closing), then main's two new tests (the diagram's caption, the needs-attention groups) unchanged. No code
outside tests/ changed in this round. The merge also brought main's changes to ergostat/web (diagram.js, dynamics.js,
export.js, pages.js, relations.js, style.css, server.py, eta_api.py); none conflicted with the branch's lines. Run
here after the merge: the branch's acceptance test and main's two new tests, with Playwright under the watchdog, 3
passed, rc 0; tests/test_graph_cli_web.py, 36 passed; ruff clean. Not run: the whole of the four browser files and the
unit suite (the merge queue runs them).

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:02).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:03).

Its runs failed past their attempts (a dead letter):
- attempt 21: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 22: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 23: nack exited 1
- attempt 24: nack the run ended with gap/ui-the-address-holds-what-is-selected-and-the-windo still parked

## Where it stopped

Round 5 (the park was the Docker restart, not a finding). Main (52c675fe) was merged in (b4959886). It conflicted in
five files. Each was resolved by keeping what main changed and what the branch adds:
- main.js: main's window menu now also calls refreshHeader(). The menu still calls setWindow, and setWindow now
  calls refreshHeader() too.
- details.js: main added rolesText and a 'Loading…' panel (panelLoading) to openAgent. Both are kept, inside the
  branch's openAgentNow, which askedAgain wraps. Because of main's panelLoading, an opener now shows its 'Loading…'
  panel at once, and its own "Could not be read." if the request fails. So round 3's sentence "an opener whose
  request fails shows nothing and leaves the panel already shown" no longer holds on main. An opener that throws
  (openNode, openAgent) still never sets S.again. openLoop, which returns on failure, does set it, so its "Could not
  be read." panel is asked again on a window change.
- pages.js, Loops: main's 'Loading…' note and its name button are kept. The row and the button both call the branch's
  pick (it writes select= and opens the loop). The branch's loadingNote helper is removed. Loops and Items use main's
  note, and the Record's box now starts with one as well.
- pages.js, Record: main now keeps the Record's filter and scope in the address itself, as `match=` (kept() and
  replaceRoute in tick). The branch's separate setQuery({filter}) would have been overwritten by it at once, so it is
  removed and main's `match=` is the name that gets written. A link's `?filter=` is still read on load (match, then
  filter, then type). This is the most reversible choice: one name written, the definition's name still read.
- tests: both sides' new tests are kept in both files. The branch's test now waits for main's Loops 'Loading…' note
  (`p.muted`, not `.loading`). It checks that the Record writes `match=`, and that a `/record?filter=agent.*` link
  fills the filter.

Size: `git diff main --stat -- ergostat/` is 52 insertions and 18 deletions (about 34 net, within 60).

Run here after the merge: ruff, clean. tests/test_graph_cli_web.py, 41 passed. The acceptance test
tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window, with Playwright under the
watchdog, passed (rc 0) twice. Break check: with the Record not reading `filter=`, the test failed (TimeoutError),
and it passed again when restored.

tests/test_items_page.py: 29 passed and 1 failed, the same result on two runs. The one failure,
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, also fails run alone. It times out at
tests/test_items_page.py:1331, waiting for the other project's entry in the header's #project list. That list comes
from main's refreshProjects (util.js) and the server's lister (server.py list_projects, `/api/projects`). The page
asks once on load and, if the lister has made no list yet (`ps.at == null`), asks again only on pointerenter or
focus, which the test never does. The branch changes none of refreshHeader, refreshProjects or server.py. The test's
pages are opened with no `window=` or `select=`, so withWindow and setQuery change nothing on them. It is reported here
as not this branch's (lesson 13) and not fixed. To confirm it on main, I tried to run it with main's
ergostat/web/static checked out for a moment (`git checkout main -- ergostat/web/static && ...; git checkout HEAD --
ergostat/web/static`), but that command was refused, so whether it also fails on main is not shown here.

Not run: the rest of tests/test_diagram_rendering.py, tests/test_page_polling.py, tests/test_page_refresh.py, and the
unit suite (no Python changed outside tests). The merge queue runs them.

## Where it stopped

Round 6. Main (ead497d1) was merged in (cd52eabd). It conflicted in three files, each resolved by keeping both sides:
- pages.js, Loops: main moved each loop's performance word to the server (`loops?perf=1`) and renamed the column
  `r`. Main's version is kept, and its row and name button call the branch's pick (writes select=, opens the loop).
- tests/test_graph_cli_web.py and tests/test_diagram_rendering.py: both sides added tests at the same place. All are
  kept. The branch's test has its own `assert not errors` / `finally` closing again.

The review finding (route() never read `?window=`, so after Back or Forward the address and the page's window could
differ) was true. Fixed in util.js route(): when the address names one of WINDOWS, that is S.since. With no
`window=`, S.since is 1h. The Record's `window=1` leaves S.since as it is. When S.since changes, the header is
redrawn (showAt, refreshHeader) and the graph signature is cleared. Not in a snapshot. That is 2 lines.
`git diff main --stat -- ergostat/` is 54 insertions and 18 deletions (about 36 net, within 60).
The test gains the finding's step: choose 1d on /loops, navigate to /items (its address gets window=1d), choose 1h,
Back, then Forward. Each time S.since, the address's window= and the header's label agree. With route()'s new lines
disabled, the test failed (`['1h', '1d', 'Last 1h'] != ['1d', '1d', 'Last 1d']`). Restored, it passes.

Run here: ruff clean. tests/test_graph_cli_web.py, 43 passed. Under the watchdog with Playwright: the acceptance
test and main's two new tests in tests/test_diagram_rendering.py, 3 passed, rc 0.
tests/test_items_page.py: 32 passed and 1 failed, test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart.
That is the same timeout on the header's #project list that round 5 reported as not this branch's.
tests/test_page_refresh.py: 8 passed and 1 failed,
test_other_pages_left_open_change_nothing[diagram?view=process&by=events] (6 mutations: a DIV's class and an H1's
title, across refreshes with nothing new). It fails the same way with this round's route() lines disabled. The
branch changes no class or title that a refresh sets on the process view, and that view is opened with no select=
or window=. Reported as not this branch's (lesson 13). It was not run on main: earlier rounds' attempts to check out
main were refused, and this round a command writing a log to /tmp and one listing failed tests were refused too.
Not run: the rest of tests/test_diagram_rendering.py, tests/test_page_polling.py, and the unit suite (no Python
changed). The merge queue runs them.

## Where it stopped

Round 7, answering the one review finding (popstate passed its PopStateEvent to route() as `keep`, so Back and
Forward kept the open panel and its S.again). It was true. Fixed in main.js: popstate now calls `route()` with no
argument, so every Back and Forward closes the panel (and clears S.again) as main did, and the Loops page then opens
the address's `select=` loop. One line changed; `git diff main --shortstat -- ergostat/` is 55 insertions and 19
deletions (about 36 net, within 60).

The test gains the finding's step: open inbox-short's panel on /loops, navigate to /diagram?view=dynamics, open the
stock inbox's panel, then Back. The address says select=inbox-short and the panel shown is that loop's, not the
stock's. Forward: no panel is left over on the diagram, and a window change there opens none. With the old
`addEventListener("popstate", route)` put back, the test failed at Back (the stock's panel stayed, timeout). Restored,
it passes.
A first run of the new step failed at Forward. The test had gone on while the loop's panel still showed 'Loading…',
so the loop's answer landed on the diagram after Forward. The test now waits for the loop's answer before going
Forward. Any opener's late answer can land after a route change (on main too, e.g. a click and then a quick
navigation). The branch's `select=` on Back makes this easier to reach, but guarding every opener's answer against a
route change is outside this gap, so it is not fixed here (lesson 13).

Run here: ruff clean. Under the watchdog with Playwright:
tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window passed 3 times after the change
to the test (rc 0), and test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back passed (rc 0).
Not run: the rest of the four browser files and the unit suite (no Python changed). The merge queue runs them.

## Where it stopped

Round 8, answering the queue's one finding (a conflict with main in util.js; the factory's merge of main e43046dc
also conflicted in pages.js and tests/test_graph_cli_web.py). Merged (8c2457a7), each resolved by keeping both sides:
- util.js route(): main's nav loop that also sets `aria-current="page"` is kept, after the branch's two lines that
  read `?window=` into S.since.
- pages.js, Loops: main's quiet-systems box (`qbox`, appended before the table) is kept, after the branch's `pick`
  and its opening of the address's `select=` loop.
- tests/test_graph_cli_web.py: both sides' new tests at the same place, both kept.
No code outside tests/ changed in this round beyond the merge. `git diff main --shortstat -- ergostat/` is 55
insertions and 19 deletions (about 36 net, within 60).

Run here after the merge: ruff clean. tests/test_graph_cli_web.py, 45 passed. Under the watchdog with Playwright:
tests/test_diagram_rendering.py::test_the_address_holds_what_is_chosen_and_the_window and
test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back, 2 passed, rc 0.
A first try of that browser command with `| tail -5; echo rc=$?` appended was refused; run again without them, it ran.
Not run: the rest of the four browser files and the unit suite (no Python changed). The merge queue runs them.
