# route-one-large-system-in-parts: any line group over GROUP_CAP is split into parts: components with hub parts set aside, a component over the cap cut into bands; the shared group "" is bounded, and when it goes over it is routed free
depends-on: []

## The gap (as found on main)

`avoidSpec` (`ergostat/web/static/avoid.js:586-605`) groups a large view's lines (over `GROUP_OVER = 150`). Each open system's own lines (both ends in it) form one group. Lines between systems go to `""`, which takes with it the systems they reach most while the total stays within `GROUP_CAP = 100`. Then a net (lines of one kind leaving one part, or reaching one) that spans groups goes whole to `""`. `avoidCore.route` weighs crossings only within a group, and that weighing is most of the routing time (fastroute.md). Two things are missing:

- **One system's lines are never split.** A one-system view (`system=sys-001`, scale.md #13: 280 shapes, 190 s at N = 30) puts every line in one group. Every line between parts with no system goes in `""` as well. So the grouping does nothing for the view that is slowest.
- **`""` has no ceiling.** Its starting size and the net rule's additions are never checked against any cap.

## Definition of done

1. **A new module, `ergostat/web/static/routeparts.js`.** It provides one pure function, `partGroups(conns, at, groups)`, with no DOM, no libavoid and no globals read.
   - **Inputs:**
     - `conns`: `[{id, s, t}]`;
     - `at`: `{partId: [x, y]}`, each part's centre;
     - `groups`: `{lineId: name}`, the system-level grouping on main, unchanged.
   - **Output:** `{groups, free}`.
   - **Constants:** `GROUP_CAP = 100` (moved here from avoid.js; avoid.js uses this one), `SHARED_CAP = 100`, `HUB = 8`.
   - **Order of work.** Each group `G` with more than `GROUP_CAP` lines is parted, in name order. `""` itself is parted when it is over the cap.
     - a. **Hubs.** A hub is a part with more than `HUB` of `G`'s lines. Every line of `G` that touches a hub goes to `""`.
     - b. **Missing position (lesson-3).** A line with an end that has no entry in `at` goes to `""`. That is the worst case: it is routed with the shared lines, and it never decides a band.
     - c. **Components.** The rest of `G`'s lines are split into components: lines joined when they share an end part.
     - d. **Bands.** A component of at most `GROUP_CAP` lines is one piece. A larger component is cut into bands:
       - The axis is x when the component's parts span at least as wide as tall, otherwise y.
       - Parts are sorted by (axis coordinate, id).
       - Taking parts in that order, a part joins the current band unless the band's lines plus the part's lines to parts already in the band would exceed `GROUP_CAP`. In that case, and only when the band is not empty, the part starts a new band.
       - A line with both ends in one band belongs to that band's piece. A line whose ends are in two bands goes to `""`.
     - e. **Packing.** Pieces are sorted by (smallest x of their parts, smallest y, smallest line id). They are packed in that order into groups named `${G}#${k}` (k = 0, 1, …). Each group takes pieces while its total stays at most `GROUP_CAP`.
   - **After parting:**
     - No net rule runs. `""` does not count in any net rule here: nothing is ever moved into `""` because of a net, so nothing can cascade.
     - The net rule on main, at system level, runs before `partGroups` and is unchanged.
     - `free` is true when `""` holds more than `SHARED_CAP` lines.
   - **Determinism.** The result depends only on the inputs as sets. The order of `conns` and the key order of `at` never change it.
2. **What the split guarantees.** Each guarantee is stated in the module's header comment and nowhere wider (lesson-8):
   - (i) Every group other than `""` has at most `GROUP_CAP` lines.
   - (ii) Two lines that share an end and are both outside `""` are in one group. A net can therefore be split only between `""` and one other group, at a hub or a band edge. The spacing pass on main already reroutes, free, two lines of one point that cross.
   - (iii) A group of n lines is parted into at most `2·⌈n / GROUP_CAP⌉ + 1` groups. This holds because packing is consecutive, so two neighbouring groups together hold more than the cap. The count is bounded because every group is a libavoid router holding every shape (lesson-4).
   - (iv) Groups of at most `GROUP_CAP` lines are returned unchanged. A view whose groups are all within the cap is grouped exactly as on main.
3. **`""` is bounded.** When `free` is true, `avoidSpec` adds `penalties: {"": 0}` to the spec. `avoidCore.route` then sets each router's crossing penalty to `spec.penalties?.[name] ?? spec.crossingPenalty`. So `""` past `SHARED_CAP` lines is routed with no crossing weighing: fastroute.md measured 0.3 s against 18 s for that. `prof` records:
   - `prof.shared`: the number of lines in `""`;
   - `prof.free`: the number of lines routed with penalty 0 through `penalties`, 0 when none.

   No other part of the core changes. The first pass, the spacing pass, `move` and `moveMany` stay as they are.
4. **Wiring.**
   - `avoidSpec` calls `partGroups` on its `groups` when they are non-null (lines > `GROUP_OVER`), with the shapes' centres.
   - `routeparts.js` is loaded before `avoid.js` in `index.html`. The `avoidCore.toString()` worker source does not need it, because the grouping is computed on the page.
   - The page snapshot (`ergostat/web/snapshot.py`) inlines it like the other scripts. This is checked by the test in item 6.
5. **Docs.**
   - `docs/proposals/scale.md`: the #13 row and a short paragraph say what the parting does. They also give the routed time of the two end-to-end test models below, on main and on the branch, measured one after the other on the same machine. Any number that did not improve is reported as such. If scale_model N = 10 `system=sys-001` was not measured, the paragraph says so.
   - `docs/layout-rules.md` gets one paragraph stating guarantees (i) to (iv) and the free routing of `""` over its cap.
   - `docs/GAPS.md`: the entry "An engine per system; line routing for large diagrams" notes this part done and what is left.
6. **Done** also means the house rules: the unit suite and the four browser files pass with rc 0, ruff is clean, origin/main is merged in and both are run again (lesson-7: the ready gap `line-routing-for-large-diagrams` also edits `avoidStart`/`avoidCore`).

## Files to touch

- `ergostat/web/static/routeparts.js` (new)
- `ergostat/web/static/avoid.js`: the call in `avoidSpec`, per-group penalty and `prof.shared`/`prof.free` in `avoidCore.route`, `GROUP_CAP` moved out
- `ergostat/web/static/index.html`: the script tag
- `ergostat/web/snapshot.py`: only if it does not already inline every script tag
- `tests/test_diagram_rendering.py`
- `docs/proposals/scale.md`, `docs/layout-rules.md`, `docs/GAPS.md`

## Risks

- **lesson-4.** The risk is an unbounded `""`, or an unbounded number of routers (each router copies every shape). `""` past `SHARED_CAP` is routed free (item 3). The number of groups is at most `2·⌈n/GROUP_CAP⌉ + 1` per parted group (iii). Hubs, band-crossing lines and lines between systems all go to `""`. The tests assert its size: exactly the hub lines in the hub model, at most `SHARED_CAP` in the chain model, and free in the star model.
- **lesson-9.** The risk is tests that never run band cutting, or that pass with every line in `""`. One test has a single component of 260 lines with no hub. Every test asserts the size of `""` and checks that each `""` line has a reason to be there (it touches a hub, crosses bands, or has a missing position). Each test is broken on purpose and seen to fail, and the report says so:
  - crossing lines put in the lower band;
  - `HUB` ignored;
  - `penalties` not set;
  - packing with no cap.
- **lesson-8.** The risk is the docs claiming "a net is never split" (the claim on main), or a speed-up that was never measured. Guarantee (ii) is narrowed and has a test. Times go in scale.md only as measured, with main's time beside them.
- **lesson-3.** The risk is a part with no position being sorted as 0 and deciding a band. Its lines go to `""`, and a test covers this.
- **lesson-7.** The risk is the ready gap `line-routing-for-large-diagrams`, which adds a quick pass with `spec.plain` (no groups) in the same functions. The branch merges origin/main and runs the suites again. If that gap has landed, `plain` must still bypass the groups and the penalties.
- **lesson-10.** The end-to-end tests have time bounds. They use `ROUTED_BOUND_MS` and are marked `slow`, and `serial` if they route near the bound. A failure that happens only under load is investigated, never cured by a higher bound.
- **lesson-13.** A suite failure in something this change does not touch is named in the report and not fixed here.

## Acceptance tests

All are in `tests/test_diagram_rendering.py`. The pure tests load a served example page and call `partGroups` through `pg.evaluate` on synthetic inputs. The end-to-end tests serve a generated one-system model, open `system=s0`, wait for routing, and call `avoidSpec(S.layout, S.graph)` to read the groups.

- `test_a_chain_over_the_cap_is_cut_into_bands`
  - **Input.** A single straight chain of 261 parts along x, 260 lines, no hub, all in group `"s0"`.
  - **Bands.** There are at least 3 groups `s0#k`, each with at most 100 lines.
  - **`""`.** It holds exactly the lines whose ends are in two different bands, one per cut: (number of bands − 1) lines.
  - **Determinism.** The same inputs with `conns` shuffled, and `at` built in reverse key order, give an identical result.
  - **Fails if:** crossing lines are kept in a band, the cap check is off by one, or the sort uses input order.
- `test_a_part_with_more_than_eight_lines_is_a_hub_and_its_lines_alone_go_to_the_shared_group`
  - **Input.** 12 chains of 11 lines, and one hub part with a line to each chain's first part: 144 lines in one group.
  - **`""`.** It is exactly the 12 hub lines.
  - **Chains.** Each chain lies wholly within one group, and the groups are each within the cap.
  - **Guarantee (ii).** Lines that share an end and are outside `""` share a group.
  - **Guarantee (iii).** The group count is within the bound.
- `test_groups_within_the_cap_are_returned_unchanged`
  - **Input.** A grouping on main where every group is at most 100 lines.
  - **Expected.** The output is identical to the input, and `free` is false.
- `test_a_part_with_no_position_sends_its_lines_to_the_shared_group`
  - **Input.** The chain input with one part removed from `at`.
  - **Expected.** That part's lines are in `""` and every band is still within the cap.
- `test_the_shared_group_over_its_cap_is_routed_free`
  - **Pure part.** 15 hubs with 10 lines each give `free` true and `""` = 150.
  - **End-to-end part.** A one-system model with 12 valves, each driving 10 others through `driven-by` (more than 100 hub lines). After routing:
    - `AV.prof.free` equals the size of `""` and `AV.prof.shared`;
    - `AV.invalid == 0`;
    - no page errors.
  - **Fails if:** `penalties` is not passed to the core, or `free` is never set.
- `test_one_systems_lines_are_routed_in_parts` (slow)
  - **Model.** One system of 12 chains (flows between stocks, as `big_model` writes them) with one hub flow driving each chain's first flow. It has more than 150 routed lines.
  - **Groups.** `AV.prof.groups >= 3`. Every non-`""` group has at most 100 lines.
  - **`""` is checked against an independent count.** It equals the set of lines with an end at a part that has more than 8 of the view's lines, computed by the test from `S.graph.edges`.
  - **Guarantees (ii) and (iii)** hold on the real layout.
  - **Routing.** `AV.invalid == 0`. `AUDIT` finds no `through` and no `detour`. The routed time is under `ROUTED_BOUND_MS`.
  - **Printed.** The routed time and the net-crossing count.
- `test_one_long_chain_with_no_hub_is_routed_in_bands` (slow)
  - **Model.** One system with a chain of 90 stocks: more than 150 pipe lines in one component.
  - **Bands.** At least 2 non-`""` groups, each with at most 100 lines.
  - **`""`.** Every line in it has its two ends in two different non-`""` groups' parts, and it holds at most 100 lines.
  - **Determinism.** A reload gives the same groups.
  - **Routing.** `AV.invalid == 0`, and no `through` or `detour`.
- `test_a_snapshot_page_still_routes_its_lines`: if no snapshot test already loads the router on a large view, a one-line check that `partGroups` is defined in a snapshot page.

## Size budget

220 net lines (routeparts.js about 140, avoid.js about 25, index.html 1, plus margin)

## Notes from the plan review (answer each)

- Parting "" itself when over the cap contradicts guarantee (ii): a between-system line moved from "" into a "#k" group shares an end with that system's lines in another group, both outside "", so (ii) and the 'net split only between "" and one other group' claim are false (lesson-8). Order is also undefined: "" sorts first, then other groups' hub/crossing/missing-position lines are added to it after its parting. No acceptance test has "" over the cap before parting (all are one-system), so nothing would fail. Either drop parting of "" (rely on free) or narrow (ii) to lines from one source group, define the order and naming, and add a multi-system test with "" initially over 100 asserting the narrowed guarantee.
- Confirm avoidCore (serialised by toString into the worker) does not reference GROUP_CAP; if it does, pass it via the spec rather than a page global.
- Band cuts in components with long-range lines can send many lines to ""; the header should say "" may grow and is bounded only by free routing, not claim one line per cut.
- The e2e hub test counts hubs by the view's lines while the rule counts by G's lines; equal only in a one-system view. State that, or compute per group.
- Specify the axis choice when a component has no positioned parts or a zero span.
- Add a mutation for free (>= vs > SHARED_CAP) and show a test fails.

## Where it stopped

Built, round 1: `routeparts.js` (97 lines), `avoid.js` (+15 −7), `index.html` (+1): 106 net lines, within the 220
budget. `snapshot.py` is unchanged: it already inlines every script tag (`test_a_snapshot_page_still_routes_its_lines`
checks it).

**Decided alone, the most reversible way (no one to ask):**

- **`""` is parted, and why that is not optional.** In a `system=X` view no part has an open system (`systems: []`),
  so on main every line of a one-system view is in `""`, not in a group named for the system. Dropping the parting
  of `""` (the plan review's first option) would leave the gap doing nothing for the view it is for. So `""` is
  parted, first (name order, as item 1 says). To keep (ii) as written, instead of narrowing it, parting `""` adds one
  rule: a line of `""` at a part that has a line of another group, as given, stays in `""`. Its pieces go to groups
  `#k` (`${G}#k` with G = `""`). What the later groups set aside goes to `""` after its parting and is not parted
  again. Test: `test_the_shared_group_over_the_cap_is_parted_and_keeps_its_lines_at_a_systems_parts` (a system's
  group of 60 lines and a `""` of 130, 10 of them at the system's parts). This answers the plan review's first note.
  To undo it, drop the `others` rule and the `""` parting together.
- **The end-to-end group names are `#k`**, not `s0#k`, for the same reason.
- **The other plan-review notes.** `avoidCore` never referred to `GROUP_CAP`; it reads only `spec.penalties`. The
  header says `""` is not bounded by the parting (many lines can cross at one cut) and is bounded only by free
  routing. The e2e hub count uses the view's lines; it says so, and in a one-system view they are the group's lines
  (all start in `""`). The axis is x on a zero span. A component never has a part with no position (rule b takes
  those lines out first), so that case cannot arise. The `>=` mutation of `free` is below.

**Where the acceptance text could not hold as written:**

- `test_one_long_chain_with_no_hub_is_routed_in_bands`: "every line in `""` has its two ends in two different
  non-`""` groups' parts" is false under item 1d's own band rule on the laid-out chain. ELK wraps the 90 stocks into
  rows, so a band edge falls where the chain runs across the axis. Parts there join a band with no line to its parts,
  both their lines cross, and the part is in no group (11 lines crossed at one cut here). The test asserts what holds
  instead: no line in `""` has both ends in one group, `""` ≤ 100, and at least 2 bands. The pure chain test keeps the
  exact claim (one line per cut, bands of 100, 100 and 58).
- `test_the_shared_group_over_its_cap_is_routed_free`, end-to-end model: 12 valves, each driving the 10 flows of a
  chain of its own (384 lines, 144 at the hubs). It routes in 0.6 s with `invalid == 0`. Shapes tried and dropped:
  each driven flow filling a stock of its own (weighed groups of 100 among 396 shapes: more than 4 minutes); each ten
  filling one stock (more than 90 s even with every line free); one chain of 120 driven flows (1 line with no valid
  route, with main's grouping too).
- The chain inputs of the pure tests give parts and lines ids in no order of x. With ids in x order, sorting by id or
  in line order passed the test (found by breaking it).

**Broken on purpose, and what failed (lesson-9):** each run on the new tests, then restored.

- crossing lines kept in the lower band: 4 failed (the chain, missing-position, `""`-parting and long-chain tests);
- `HUB` ignored: 3 failed (the hub test, the free test, `test_one_systems_lines_are_routed_in_parts`);
- `penalties` not set in `avoidSpec`: the free test failed;
- packing with no cap: 6 failed;
- `free` at `>= SHARED_CAP`: the free test failed (`""` of exactly 100);
- the band cap off by one (`>=`): at first nothing failed, so the chain test now asserts the exact band sizes, and it
  fails;
- parts in line order, not by position: at first nothing failed, so the ids were scrambled, and the chain test fails;
- the `""` rule for a system's parts removed: the `""`-parting test failed;
- a missing position taken as (0, 0): at first nothing failed (its lines crossed bands anyway), so the part removed is
  now one near the start, and the missing-position test fails.

**Measured** (scale.md, *Routing one system in parts*): 0.25 s parted against 1.02 s with main's grouping on the
12-chain model. On the 90-stock chain, 0.42 s against 0.40 s: not improved. Main's grouping was routed by the
branch's core, not by a checkout of main. scale_model's `system=sys-001` was not measured.

**Not done here:** this clone has no `origin` remote and local `main` has no commit past this branch's base, so
"merge origin/main" was a no-op. If `line-routing-for-large-diagrams` lands first, its `spec.plain` pass must still
bypass `groups` and `penalties` (lesson-7), and the suites must run again after the merge.
