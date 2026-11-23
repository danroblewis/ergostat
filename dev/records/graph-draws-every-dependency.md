# The Items page's Graph draws every dependency of the unfinished work

## The problem

On a large record the Graph hides almost all of the work's dependencies. On the factory's record, with kind `gap` chosen, the answer from `/api/items-graph` is right: all 375 unfinished gaps and their dependencies are in it. The page then draws 2 of the 338 dependency lines into unfinished gaps, and 108 of the 375 unfinished gaps.

`rgModel` in `ergostat/web/static/relations.js` causes this in two ways:

1. **Items of a kind nobody asked for take the room.** The answer holds the items relations reach, and `rgModel` starts its scope from all of `d.items`. 190 of the 300 cards are `review` records, reached only because they name a gap. A review in state `merge` also reads as `active`, so these sort first.
2. **The cap cuts dependency chains apart.** Past `RG.NODES` (300) it keeps the first cards by status. Waiting items sort last, so a waiting gap and what it waits on are dropped, and a line is drawn only when both ends survive.

## What done means

- The scope starts from the items of the kinds asked (`asked` on the answer's kinds). Another kind's item is drawn only when an asked item waits on it through a precedence relation, or it is the parent of a drawn item. A record that only refers to an item, such as a review of a gap, is not drawn.
- With kind `gap` on a record of the factory's shape (about 375 unfinished gaps, about 340 dependency lines, about 340 review records), every unfinished gap and every dependency line into one is drawn. Raise `RG.NODES` as far as that needs, and keep a bound.
- Past the bound, the cut never separates a dependency: whole connected groups of items are kept or left out, those holding active or unblocked work first. The existing note says how many items and how many dependency lines are not drawn.
- A finished predecessor still follows the collapse setting (`via N done`).
- The Timeline's rows and the statuses' counts are unchanged, except where they read the same scope on purpose.

## Tests

Add tests beside `tests/test_relations.py` using a generated answer of that shape: no dependency line of an unfinished item is lost, a review record is not drawn, and a cut past the bound leaves no drawn item with a missing drawn-kind dependency unreported. The browser suite is not run on each merge at present, so the test must not depend on it alone.

Do not add a page, panel or control.

## Where it stopped

Round 1: built. About 95 net lines of code (`web/graph_parts.py` +59, `relations_api.py` +3, `relations.js` +25 net), inside the 600-line budget.

- **The scope** (`relations.js` `rgModel`): starts from the items of the kinds marked `asked`; the precedence chain and the parents are added as before. When no kind is marked asked (an older answer), every item starts it, as before.
- **The groups** (`ergostat/web/graph_parts.py`, called in `relations_api.graph` and cached with the answer): each drawable item (the asked kinds, what they wait on however far back, their parents up to the top) gets `part`, the rank of its connected group over precedence and parent links. Groups are ranked by their best status (active, queued, unblocked, blocked, paused, dead, done; a status not known ranks last), then the earliest start, then the least id. I put the grouping on the server, not in the page, so that a unit test can check it without a browser: the container has no JavaScript runtime outside Playwright's Chromium.
- **The cut**: `RG.NODES` is now 600, the same as `precedence.MOST_OPEN`. Past it, `rgModel` keeps whole groups in rank order, first-fit: a group too big for the room left is skipped and smaller ones after it are still kept. The note says "N of M items drawn: K items and L dependency lines not drawn (whole connected groups left out, …)".
- **Choices made without anyone to ask** (each easy to undo):
  - A single group bigger than 600 is left out whole and counted in the note. It is not cut in half.
  - The groups are worked out over every drawable item, whatever Frontier and Collapse are set to. So a group can be coarser than the view needs (two chains joined only through a finished item the frontier hides count as one group). That is the safe direction: it never separates a drawn dependency.
  - The Timeline reads the same scope on purpose (its rows are `m.nodes`), so a review of a gap no longer gets a row. The legend's counts still read every item in the answer, reviews included, so they are unchanged.
- **Tests.** `tests/test_graph_parts.py` (unit, 7 tests) uses a generated answer of the factory's shape: 375 unfinished gaps, 340 lines into them, 340 active reviews. It covers: every line into an unfinished gap has both ends in one group, and all 375 are kept; no review is drawable; a review that a gap waits on, and the parent's parent, are drawable; a status not known ranks last; a 1,200-gap answer cut past 600 keeps whole groups, counts every line it leaves out, and keeps the groups with active work; and `relations_api.graph` marks the parts on a real project. The cut is checked in the unit test through `drawn()`, a mirror of `rgModel`'s rule written in Python. The page's own `rgModel` runs only in the browser test `tests/test_items_page.py::test_the_graph_draws_every_dependency_of_the_unfinished_work`, on the same generated answers (Collapse off: all 340 lines drawn, no review; Collapse on: the lines between unfinished gaps; past the bound: no line cut in half, `lost` equal to the lines left out, the active groups kept).
- **Each test was seen to fail** with the code it guards broken (lesson 9), and passed again once restored:
  - the scope started from every item: the browser test fails (`capped` 738);
  - the cut made `slice(0, RG.NODES)`: the browser test fails (a line cut in half);
  - the note's count of lines from undrawn items dropped: the browser test fails (0 against 589);
  - `mark` not reading `asked`: 4 unit tests fail;
  - `mark` joining nothing: 4 unit tests fail.
- **Run here.**
  - Ruff is clean.
  - These pass: `tests/test_graph_parts.py`, `test_relations.py`, `test_eta.py`, `test_relations_asof.py`, `test_process.py`, `test_item_index.py` and `test_graph_cli_web.py`.
  - In `tests/test_items_page.py` under the watchdog, 28 of 29 pass, the new test included, with no test skipped.
  - One fails: `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. It times out waiting for the other project's entry in the header's project switcher (`#project option`), which reads the projects under `ERGOSTAT_HOME`. This change touches neither the header, the switcher nor `/api/status`, so I take it to be unrelated. I could not prove it fails on main: `git checkout main -- ergostat/web/relations_api.py ergostat/web/static/relations.js` was refused in this session.
  - Not run here: the other three browser files, the whole unit suite, `demo_check` (no example was touched), and the real factory record (none is in the clone). ELK's layout time at 600 cards was not measured.
- `main` merged in: already up to date.

## Where it stopped

Parked by the factory (reviewer, 2026-11-22 17:03).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 143, in main
    return judge(cfg, given["item"], began)
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 195, in judge
    got = fac.session(cfg, "reviewer", text, wt)
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
