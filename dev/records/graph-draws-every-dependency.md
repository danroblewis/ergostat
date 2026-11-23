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

## Where it stopped

Round 2 (after the Docker restart that parked round 1; no review findings to answer): built, the same work as round 1.

- Read over again against the definition and the review lessons. One change only: a missing space in `rgModel`'s scope line (`&&(` to `&& (`).
- `main` is the base as of the clone. It is already merged, with nothing new.
- **Run here.** Ruff is clean. `tests/test_graph_parts.py`, `test_relations.py` and `test_graph_cli_web.py` pass (73). In `tests/test_items_page.py` under the watchdog, 28 of 29 pass, `test_the_graph_draws_every_dependency_of_the_unfinished_work` included, with no test skipped (rc 1, peak 271 threads).
- The same one fails as in round 1: `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. It times out in `wait_for_function` on the header's project switcher, which reads the projects under `ERGOSTAT_HOME` through `/api/status`. This branch touches neither. I could not run it on main: `git worktree add --detach /tmp/mainwt main` was refused in this session. Under lesson 13 it is reported here, not fixed.
- Not run here: the whole unit suite, the other three browser files, `demo_check` (no example was touched), and the real factory record. ELK's layout time at 600 cards is still not measured.

## Where it stopped

Round 3, answering the round-2 review's one finding (a group bigger than the bound dropped whole, active work and all; groups joined over parent links; no test of a group bigger than 600). About 98 net lines of code on main in all (`graph_parts.py`, `relations_api.py`, `relations.js`), inside the 600-line budget.

- **Groups join over precedence links only** (`graph_parts.mark`). A parent link joins nothing: a parent is in its own group, or in its own dependencies' group. It is still drawable, as before.
- **The cut** (`rgModel`). Past `RG.NODES` (600) it walks the groups in rank order:
  - Each group that fits whole is kept, together with its items' parents that are not yet drawn, and those parents count against the room.
  - The first group that does not fit whole is cut inside it. Its items are taken by status, then earliest start, then id, each with its parents, while they fit. The groups after it are left out.
  - So 600 active tickets under one epic, plus 3 paused tickets, draws the epic and 599 tickets, and none of the paused ones. A group of 701 draws its 600 most active.
  - The note now says groups are kept whole and only the first that does not fit is cut, by status.
- **What this gives up from the definition, said plainly.** The definition says "the cut never separates a dependency". The review asked for a cut inside a group that does not fit, and I followed the review. So two things can now leave a line half drawn:
  - the one group cut inside;
  - a parent drawn for its child while the parent's own group is left out.

  Every such line is counted in the note's "dependency lines not drawn". SPEC (§5a, *Relations*) now says this, not "no line is cut in half". The choice is easy to undo: it is the two lines after `need` in `rgModel`.
- **Left as it was.** Groups are still worked out over every drawable item, finished ones included, whatever Frontier and Collapse are set to. So with Collapse on, two chains joined only through a hidden finished item count as one group. Since a group too big no longer drops its active work, the cost is only a coarser cut.
- **Tests.**
  - In `tests/test_graph_parts.py`, the Python mirror `drawn()` follows the new rule.
  - New: `test_a_group_bigger_than_the_bound_is_cut_by_status_not_dropped`. One group of 701 with a paused root is drawn as its 600 most active items, none of the 3 paused gaps, and all 700 lines counted lost.
  - New: `test_an_epic_over_more_than_the_bound_draws_its_active_work`. 604 parts, so the parent joins nothing. The paused epic is drawn with 599 active children, and no paused gap.
  - Changed: the 1,200-gap cut test. At most one group is cut, the other lines are whole, every line not drawn is counted, and the groups left out rank below every kept one.
  - Changed: the two `part` tests, since parents are now their own part.
  - The browser test now checks the page's own `rgModel` against `drawn()` on all three answers past the bound: the same items drawn, the same `lost`, and no line unreported.
- **Each break seen to fail** (lesson 9), then restored:
  - the in-group cut removed (the old drop-whole rule): the browser test fails;
  - parent links joined again in `mark`: 3 unit tests fail;
  - parents not pulled in with their children: the browser test fails on the epic answer;
  - `lost` not counting a drawn item's undrawn dependency: the browser test fails on the fan answer. Before the fan's root was made paused, this break passed, which is why the root is paused.
- **Run here.**
  - Ruff is clean.
  - `tests/test_graph_parts.py`, `test_relations.py` and `test_graph_cli_web.py` pass (75).
  - In `tests/test_items_page.py` under the watchdog: 28 of 29 pass, none skipped (rc 1, peak 274 threads).
  - One fails: `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`, the same as in rounds 1 and 2. It times out in `wait_for_function` on the header's project switcher. Run alone it fails the same way. This branch does not touch the header or `/api/status` (lesson 13).
  - `sed -i` on `relations.js` was refused in this session. The same edits were made with the editor instead.
- **Not run here:** the whole unit suite, the other three browser files, `demo_check` (no example touched), the real factory record, and ELK's layout time at 600 cards. `main` is the base as of the clone, already merged.
