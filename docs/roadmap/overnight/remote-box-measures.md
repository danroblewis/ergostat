# remote-box-measures: a remote's closed box shows the measures its own systems' `show:` names (or a local `show:` on its `remotes:` entry), and marks every one stale when the remote or the reading is not current
depends-on: []

## What exists (not to be built again)

- `ergostat/remote/compose.py` already brings in a remote's nested systems with their `show:` renamed (`rename` maps `stock.open` to `stock.incidents-open`). `_cut` drops show refs to parts that `systems:` leaves out. So a nested remote box (`incidents-triage`) already shows its served `show:` through `spec.show`.
- The remote's top box (`incidents`, made by `compose.one` with only `description`/`within`) has no `show:`. `ergostat/fold.py:153-170` then falls back to "goals within it". For a remote that was never read, those goals are the stand-in goals that `_stand_in` makes (stock `incidents-gone`). That is a meaningless measure, and nothing marks it.
- Nothing marks a measure on a remote box as stale. `fold.py` copies `valueText` as if it were current, even when `remote.box()` says `unreachable` or `unknown`.
- Where the measures are seen: the Dynamics module box draws none (`dynamics.py:337` moves them to `charted`, and the panel charts them with `charts.js: moduleCharts`, through `details.js:63` and `dynamics.js:629`). The control diagram's `diagram.js: drawSystem` draws them as rows.

## Definition of done

1. **Where a remote's top box gets its measures**, in this order (`ergostat/remote/measures.py: refs(spec, name)`):
   a. **A local `show:` on the `remotes:` entry** (new key in `compose.KEYS`). It is a list of `KIND.NAME` with KIND one of stock, flow, auxiliary. **Every name is the remote's own name, as it serves it, never a local one.** `stock.open` means the remote's `open`, put in here as `incidents-open`, even when the local model also has a stock `open`. `stock.incidents-open` is looked up as a remote part called `incidents-open`, which normally does not exist, so it becomes a finding (point 3) whose message says the names are the remote's own and suggests `stock.open`. A part of the local model can never be shown on a remote's box. A `show:` that is not a list of `KIND.NAME` with an allowed kind is an **error** (`bad-remote`), like the entry's other malformed keys: it is the local author's typo.
   b. **Otherwise, the served `show:` of the remote's top-level systems.** These are the served systems with no `within`. With `systems:`, they are the kept systems whose served `within` is not kept. The systems are taken in the order the served model lists them, each one's `show:` in its own order, and a part shown twice appears once (at its first place). A nested system's `show:` never appears on the top box; it stays on that system's own box. A ref to a part that `systems:` leaves out is cut, as `_cut` already does for every ref to a left-out part (SPEC §4c `systems:`).
   c. **Otherwise, the existing goal default**, restricted to goals the remote actually serves (in `spec.remotes[name]["parts"]` and not in its `missing` list). Stand-in goals are never used.
   d. **A remote never read** (no cached model) gets the refs of a local `show:` (1a), each drawn as a measure that says *never read*. With no local `show:` its box shows **no measures**, never a goal fallback. The box's `says` already reads *never read*, and `remote-unreachable` is already a finding.
2. **Each measure on a remote's box carries `stale`, plus `missing` or `unchecked` where they apply.** This covers the top box and every nested remote system's box; `remote.system_remote(spec, box) is not None` decides which boxes those are. The value that `fold.py` sets is:
   - The **box state is not `ok`**: `unreachable` (the model has `ok: false`, or the readings have `read_ok: false`), or `unknown` (never answered). Then **every** measure is `stale: true`. Its `value` is `last V · AGE old` when a reading was ever recorded here, else `never read`. A stale measure's `value` is never the bare number.
   - The **box is `ok`**. A measure is stale when the newest reading of the part's sensors here is older than `max(readings.STALE_LEAST, readings.STALE_RUNS × that sensor's every)`, compared with the snapshot's `at`. These are the same constants as `readings.py`; no new number is added. A stale measure shows `last V · AGE old`. A part that has sensors here but no reading is stale with `never read here`. A part with no sensor here (for example a stock the remote serves with no sensor) is stale only when the box is not `ok`. Missing input counts as stale (lesson-3): no status file means box state `unknown`, and no reading time means `never read here`.
   - A **fresh** measure keeps today's `value` (the `valueText`/`rateText`), with `stale: false` and no age.
   - A **local `show:` ref that does not resolve** (point 3) stays in the list with `missing: true`, `stale: true` and `value: "not served"`. It is never dropped.
   - A local `show:` ref of a **never-read** remote has `unchecked: true`, `stale: true` and `value: "never read"`.
   - The reading times come from a new `remote.measures.read_times(project, spec, at)`. It looks up `project.measurements.latest("sensor/S", at)` for each sensor that measures a part shown on a remote box, and is called in `web/server.py` before `fold(...)` and passed to it as a new optional argument. A model with no remotes does not call it, and the output of `fold` does not change.
3. **The finding `remote-show-unresolved`** has level `finding`, so the model still loads; `ergostat check` still passes, since findings only report. Its subject is `system.NAME`, and its location is the `show:` key of the `remotes:` entry. It is raised **only for a local `show:` ref** (1a) that the read or cached model does not serve. Its message:
   - names the ref as written and the remote;
   - names the version it was checked against (first 7 hex of `spec.remotes[name]["version"]`), adding *as last read N ago* when the remote is unreachable and the cached model was used;
   - gives the reason: `it serves no stock waiting`, or `it is left out by systems: [triage]`, or, for a local-name form (`stock.incidents-*`), `names in show: are the remote's own: stock.open`.

   It never claims when the part went missing or that it was there before. For a never-read remote no per-ref finding is made, because there is nothing to check against; `remote-unreachable` stands, and the refs are drawn as *never read* (point 2). No stand-in is made for a show ref; that is why it is not `remote-reference-unresolved`.
4. **An unreachable remote whose model is cached.** Its show refs, served (1b) or local (1a), are resolved against the cached model and **kept**: a ref that resolves is drawn as a stale measure, not reported. A ref that does not resolve gets the finding in point 3 and the `missing` measure. Nothing is dropped silently.
5. **Rendering.**
   - The Dynamics module panel and the system panel list a remote box's measures under `remoteNote`. `details.js` gets a new `remoteMeasures(n)`, fed from `charted`, which `dynamics.py` now copies with `value`, `stale`, `missing` and `unchecked` kept. Each row shows the label and `value`. A stale, missing or unchecked row has the class `measure-stale` (dimmed in `style.css`). A fresh row does not have that class and shows its current value.
   - `moduleCharts` leaves out `missing` refs when it asks for series.
   - `diagram.js: drawSystem` adds `measure-stale` to a stale row. Its text is already the age text from point 2.
   - No new page or panel.
6. **Docs.**
   - `docs/SPEC.md §4c`: the `show` row in the `remotes:` key table, with the remote's own names and its precedence over the served tops; the "Drawn" paragraph (what the closed box shows, in the order 1a–1d, and when a measure is stale and what it then says); and `remote-show-unresolved` next to the other remote codes.
   - `docs/GAPS.md`: remove "a remote's measures on its closed box" from *Left* and note it done.
   - `docs/AGENT-GUIDE.md`: the remote section gets one line on `show:`.
7. **The rest of done.** Unit suite and the four browser files pass with rc 0, with no page test skipped for want of a port; ruff is clean; origin/main is merged in and the suites run again. No example is changed. If one is, `demo_check` must pass on it.

## Files to touch

- `ergostat/remote/compose.py`: the `show` key, checking and resolving local show refs, the finding, and `info["show"]`.
- `ergostat/remote/measures.py` (new): `refs`, `read_times`, `mark`.
- `ergostat/remote/__init__.py`: the docstring mentions `measures.py`.
- `ergostat/fold.py`: remote boxes take their measures from `measures.refs`/`mark`; new optional `reads` argument.
- `ergostat/web/server.py`: computes `read_times` and passes it to `fold` (both the dynamics and the control call).
- `ergostat/dynamics.py`: `charted` keeps `value`/`stale`/`missing`/`unchecked`.
- `ergostat/web/static/details.js`, `ergostat/web/static/dynamics.js`, `ergostat/web/static/charts.js`, `ergostat/web/static/diagram.js`, `ergostat/web/static/style.css`.
- `tests/test_remote_box_measures.py` (new), `tests/test_diagram_rendering.py`.
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`.

## Risks

- **lesson-3 (failing open):**
  - The inputs that can be missing are the cached model, `status.json`, a part's reading time, a show ref the model does not serve, and the whole remote never read.
  - Each must count as the worst case: stale, `never read`, `not served` plus a finding, or no measures. None may count as current, be dropped, or fall back to stand-in goals.
  - The risk is `fold.py`'s existing `valueText or "?"` path carrying through, or the goal default showing `incidents-gone`.
- **lesson-9 (a test that can't fail):**
  - The order test must contain a nested subsystem whose show must not appear, a duplicate, and two top systems in served order. Comparing the list exactly makes order and duplicates fail.
  - The stale tests cover all three non-ok inputs: model failing, readings failing, never answered.
  - The rendering test checks both directions: a fresh row is not dimmed, and a stale row shows its age, not the bare number.
  - The implementor breaks each guarded line and reports watching each test fail.
- **lesson-5 (stale state under a reused id):**
  - The remote's name is the reused id. If a part shown in version 1 is gone in version 2, the next load must report it, and nothing from version 1 may persist. `doc.remotes` is rebuilt each load, and `info["show"]` must be too.
  - A remote that recovers (status `ok` again after `failing_since`) must stop marking its measures stale, not keep an old `read_ok: false` in effect.
- **lesson-8 (claims wider than the code):**
  - The SPEC sentences "never a local part", "every measure stale when the remote is not answering", and "never a goal fallback for a remote never read" each have a test below.
  - The docs must not say "live", or that a measure is current, beyond what the reading-time check supports.
- **lesson-7 (merged changes that each passed):** another remote branch may touch `compose.py`/`fold.py` (for example remote-serves-ir or remote-items-record). Merge origin/main and run both suites again.
- **lesson-13 (staying in the gap):** a failure in an unrelated suite is reported by name, not fixed here.

## Acceptance tests

All in `tests/test_remote_box_measures.py` unless named otherwise. Each uses a served fixture, through `served_into` as in `tests/test_remote.py`, with:
- systems `triage` (show `[stock.open, stock.backlog]`), `triage-intake` within `triage` (show `[stock.depth]`), and `response` (show `[flow.resolved, stock.open]`);
- `stock.backlog` with no sensor.

1. `test_a_remote_box_shows_its_top_systems_show_in_served_order_once`
   - `measures.refs(spec, "incidents")` is exactly `["stock:incidents-open", "stock:incidents-backlog", "flow:incidents-resolved"]`. `stock:incidents-depth` is absent; it is on `incidents-triage-intake`'s box, which is also checked.
   - The page's `/graph` answer (control and dynamics) gives the `incidents` box the same parts, so the test fails if `fold` ignores `refs`.
   - Fails on: including nested systems, dropping served order, or duplicating `open`.
2. `test_with_no_show_a_remote_box_shows_only_goals_the_remote_serves`
   - The fixture has no `show:` anywhere, and the local model has a block reading `goal.incidents-gone-goal.error`, which makes a stand-in goal.
   - The box shows `stock:incidents-open` (from `few-open`) and nothing from the stand-in (no `incidents-gone`).
3. `test_a_local_show_names_the_remotes_own_parts_never_local_ones`
   - The local model has its own stock `open`, and `remotes.incidents.show: [stock.open, stock.incidents-open]`.
   - The first ref is `stock:incidents-open`, never `stock:open`.
   - The second is a `missing` measure, with a `remote-show-unresolved` finding that says the names are the remote's own and suggests `stock.open`.
   - The local `show:` takes the place of the served tops: `backlog` is absent.
4. `test_an_unresolved_show_reference_says_what_it_was_checked_against`
   - `show: [stock.waiting]`, which never existed: level `finding`, no error, the model loads. The message contains the cached version's first 7 hex and `serves no stock waiting`, and contains neither "no longer" nor "went missing". The measure is kept with `missing: true` and `value == "not served"`.
   - With `systems: [triage]` and `show: [flow.resolved]`, the message says `left out by systems: [triage]`.
   - `show: [queue.x]` and `show: open` (not a list) are each an error `bad-remote`.
5. `test_a_shown_part_the_remote_stops_serving_is_a_finding_at_the_next_load` (lesson-5)
   - Version 1 serves `backlog` and the local show names it: no finding.
   - Version 2 is re-served without it: after a reload there is the finding with version 2's version, the measure is `missing`, and nothing from version 1 remains.
6. `test_an_unreachable_remote_keeps_its_show_from_the_cache_every_measure_stale`
   - With `status` `ok: false` and the cache present, the served-top refs and a local ref are all kept, with no finding for those that resolve.
   - Every measure is `stale: true`, and its `value` starts `last ` and ends ` old`. It never equals the measure's bare `valueText`; the test records a reading so a number exists.
   - The test is repeated with `ok: true, read_ok: false` (readings failing): the same.
   - Fails on: marking only the `ok: false` state.
7. `test_a_never_read_remote_draws_its_local_show_as_never_read_and_no_goal_fallback`
   - No cache, and `show: [stock.open]`: one measure, `unchecked`, `stale`, `value == "never read"`, with no `remote-show-unresolved` (but `remote-unreachable` present).
   - Without `show:`, and with a stand-in goal in place, the box has `measures == []`.
8. `test_a_fresh_remote_measure_is_not_stale_and_an_old_or_missing_reading_is`
   - Box `ok`. `open` read 10 s before `at`: `stale: false` and `value` is its current value text.
   - `depth`, shown through a local show, read 1 h before: stale, `1h old`.
   - A shown flow with a sensor and no reading: stale, `never read here`.
   - `backlog`, with no sensor: not stale.
   - Then the status is written failing and then `ok` again, as a refresh would leave it: `open` is no longer stale (lesson-5).
9. `tests/test_diagram_rendering.py::test_a_remote_boxs_panel_dims_a_stale_measure_and_shows_its_age`
   - Setup: the remote-pair support side, copied, with a cache and status written by the `edit` callback; one fresh reading and one an hour old; a local `show:` also naming a missing part.
   - Opening the closed `incidents` module's panel in the default view:
     - the fresh row has no `measure-stale` class and shows its current number;
     - the stale row has `measure-stale`, contains `old`, and is not the bare number;
     - the missing row says `not served`;
     - the series request names no missing ref;
     - there are no page errors.

## Size budget

**190 net lines** of code outside `tests/`, `docs/` and `dev/`. This covers Python plus the JS/CSS under `ergostat/web/static/`. The estimate: `remote/measures.py` about 80, `compose.py` about 45, `fold.py`/`server.py`/`dynamics.py` about 15, JS/CSS about 30. Tests and the three docs are outside the budget. An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each)

- Test 6 contradicts point 2: backlog (served top, no sensor) gets 'never read' when the box is not ok, not 'last … old'. Restate test 6: measures with a recorded reading show 'last V · AGE old', backlog shows 'never read'. All are stale: true and none equals the bare valueText.
- Test 8: a local show replaces the served tops (1a), so naming depth locally drops open/resolved/backlog. Use one local show [stock.open, stock.depth, flow.resolved, stock.backlog], and give resolved a sensor with no reading.
- State and test what happens when a sensor's `every` is missing or 0: the threshold is STALE_LEAST, and it never counts as fresh with no bound.
- moduleCharts must leave out `unchecked` refs as well as `missing` ones. Assert this in test 9 or test 7.
- Define AGE as the snapshot's at minus the reading time, and use one formatter for the panel, the diagram and the '1h old' text in test 8.
- Test 4: also assert the finding's subject `system.incidents` and its location (the show: key of the remotes: entry).
- Test 5: assert that the finding's 7-hex version is version 2's and differs from version 1's.
