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
