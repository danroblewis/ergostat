# code-area-ownership: Areas of the code have owners, and work is routed to avoid collisions

Map code areas to owning streams (a milestone, a worker kind, or a single lane at a time), declared in the model. Gaps touching the same hot area are sequenced or batched together instead of colliding in the queue. Use the conflict history to draw the first map.
Done: 1. A map from the record's conflict history. 2. A replay shows fewer conflict send-backs. 3. The map is data the owner can change.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1, built. The mechanism, the first map and the replay are in. **The replay's finding is that this map
saves few conflicts at a large cost in time.** So the factory's routing ships switched off (`[areas] route = false`) for
the owner to decide. The numbers are below.

- **Core** (`ergostat/leases/areas.py`, SPEC §9.5 *Areas*, the schema, the agent guide). The option is
  `takes: {areas: {touches: FIELD, holding: [STATE], map: {AREA: {paths: [PATTERN], owner: lane | {field: F} | {block: B}}}}}`.
  It is off unless declared. An item whose FIELD matches an area held by another stream (an item leased or in a
  `holding` state) is not taken. An item already holding is never kept waiting, so two holders cannot deadlock. Within
  one look, an item let through holds its areas for the items after it. The owners: `lane` is one item at a time,
  `{field: F}` is the items sharing F's value (a milestone's gaps share the area, and the next milestone waits), and
  `{block: B}` means only block B takes items touching the area. An unreadable FIELD touches every area. The
  dispatcher's view (`ready.wanted`) now also keeps items in the holding states. `block --now` follows the same rule.
- **Done 1, the map from the conflict history.** `dev/bin/areas.py history | draw` reads git's own record on main:
  each `Merge branch 'factory/X'` (454 gaps on the first-parent line, 97.5 h from the first start to the last landing,
  9.2 h in flight on average), and each merge of main into a gap's branch whose message keeps git's `# Conflicts:`
  list (419 of them). Each one is a conflict send-back, or a round's own merge of main that stopped on a conflict.
  `draw` makes a lane of each file named in 3 or more conflicted merges whose **load** is at most 2.0. Load is the
  hours its gaps were in flight, summed, over the history's hours: what one lane would carry in series. That gives
  34 areas, now the implementor's `areas: map` in dev/model/building.yaml, each with its counts. The 26 hot files past
  that load (docs/SPEC.md: 55 conflicts, landed by 210 gaps; pages.js 70/54; test_diagram_rendering.py 61/81; ...)
  are left out. A lane there would serialise most of the factory.
- **Done 2, the replay** (`areas.py replay`). The merges are replayed with the declared map as the dispatcher holds
  them: a gap starts at its own start, or once no gap holding an area it touches is in flight. Each gap keeps the span
  it had. A conflicted merge stays when a gap still lands one of its files while that branch is in flight. A new
  collision (a file that ever conflicted, landed in a gap's flight where nothing landed it before) is added as an
  upper bound. Results on main's history with the committed map:
  - With what the gaps landed (the best the rule could know): conflicted merges 419 → 373 (332 kept, 41 added).
    The span grows from 97.5 h to 239.5 h; 197 gaps wait, 10,041 gap-hours in all, the longest 154.5 h.
  - With what the live rule reads (the paths each definition names, and for gaps already in, those and their
    branch's files): 419 → 397, and the span grows from 97.5 h to 225.3 h.
  - The sweep behind the choice (not committed; `draw(least=, load=)` reproduces it):
    - Every one of the 60 hot files as a lane: 419 → 24 (landed) or 115 (named), but the span grows to 2,197 h or
      1,755 h.
    - Load at most 0.5 (6 areas): 419 → 426 or 423, so no gain.
    - A bounded wait (an item goes after 1 to 8 h held, on maps of 8 to 80 areas): more conflicts in every case
      (495 to 668), because shifted starts make new overlaps without separating the colliding ones.
  - With about 43 gaps in flight on average, a lane cuts conflicts only in proportion to the work it serialises.
    Spans that would shrink with fewer conflict rounds are not modelled, so the delay is an upper bound too.
  - Test: `test_a_replay_shows_fewer_conflict_send_backs` (a git fixture: two gaps on one file, the later one's merge
    of main stopped on it; with the map 1 → 0 at 8 h waited; without it, 1 → 1; with a 3 h most wait, still 1).
- **Done 3, the map as the owner's data.** It is plain YAML on the implementor's `takes:`, compiled and checked (a
  malformed map, an unknown holding state or block owner is refused whole: `bad-areas`). `test_the_map_is_the_models_data`
  checks the factory model compiles with it and that the replay reads the same map. The switch is `[areas] route` in
  dev/factory.toml. Off (as shipped), the intake's pass empties every gap's `touches`, so the map holds nothing. On,
  the intake writes each waiting or unmerged gap's `touches` (its branch's files from main, and the paths its
  definition names) after it defines gaps, so a newly defined gap is routed from its first look.
- **Seen to fail** (each mutation reverted):
  - `ready.wanted` without the holding states fails the lane and unreadable tests.
  - Waiting an item that already holds fails `test_an_item_already_holding_never_waits` (deadlock).
  - The replay without its hold fails the replay test.
  - The route switch ignored fails the switch test.
- **Run here:** tests/test_code_areas.py (8), tests/test_code_areas_factory.py (5), tests/test_factory_split_systems.py
  (the factory model's `ergostat check`), and tests/test_factory.py (the intake, and no new finding on the factory
  model: 251 passed, 2 skipped for want of Docker); ruff is clean; main merged in (already up to date). **Not run here:**
  the whole unit suite and the four browser files (no page changed). No example touched.
- **Size:** about 232 net lines outside tests, docs and dev (budget 600).

Decisions taken alone (each the more reversible):
- **Routing off.** The definition asks for routing, but the replay shows the committed map stretching the factory's
  work about 2.4 times to save 5% to 11% of conflicted merges. Turning it on changes the live factory, which is the
  coordinator's. `route = true` turns it on; `false` empties every gap's touches again.
- **The conflict history is git's.** This is the merge messages in the clone, not the live record's
  `gap.sent-back {sent_back_by: queue}` events: the session may not read the live instance, and the git messages also
  catch the conflicts resolved inside a round. A replay over the live record is the coordinator's to run.
- **One file per area, drawn by load.** The owner may merge areas, add patterns or change an owner to
  `{field: milestone}`. The replay cannot judge that owner: git carries no gap's milestone, so it treats each gap as a
  stream of its own.
- **Holding from start to landing.** The holding states are building through queue-failed, and fix. A gap stacked on
  its base (`depends_on`, starts_at approved) and touching one of the base's areas therefore waits for the base to
  land: on that area, stacking is undone.
- **Waits are said in the engine's log, not recorded as events**, so the Items tab's why does not show them, and the
  completion estimates do not simulate the rule (SPEC says so).
- **The intake writes touches, not a block of its own.** A block that only writes fields drew a `no-visible-effect`
  finding on the factory model.

### Round 2

Built. This round answers the review's one finding: a gap made ready had no `touches` until the intake's next pass,
and the core read a missing field as touching nothing (a fail-open, lesson-3). The fix does both things the finding
offered:

- **Core: a field never said is unreadable.** `touched()` now reads a FIELD that is absent or null as touching every
  area, like one that cannot be parsed. Only an empty text or list says an item touches nothing (SPEC §9.5 *Areas*
  and the agent guide say so, and say to write the field in the event that makes an item takeable).
- **The factory writes touches in the event that makes a gap ready.** In the model only `gap.defined` makes a gap
  ready, and only `plan.route` (the planner, and the intake's coordinator definitions through `plan.coordinated`) and
  `parks.ready_again` say it. Both now carry `touches=areas.at_ready(...)`:
  - With `[areas] route` on: the paths the definition names, plus the branch's files when the branch exists.
  - With it off: `[]`.
  - When the definition, the branch or the configuration cannot be read (or `route` is not true or false):
    `{"unread": why}`, which the rule reads as every area.
  - The intake's pass now uses the same `measure()`. A gap whose definition or branch cannot be read is no longer
    skipped: it is said `{"unread": ...}`. With the route off, it also says `[]` to a waiting or unmerged gap that
    has none.
- **What fail-closed costs, and where.** A gap that reaches `ready` or `fix` without `touches` waits as touching every
  area until the intake's next pass (every 5 minutes) measures it. Examples: a gap that was in flight before this
  lands, or one sent back from a park by measure-runs. This is so even with the route off, so the switch is inert
  only once each gap has been said `[]`. On the live instance that is one intake pass after this lands.
- **The replay's "named" mode.** It assumes a gap's named paths are known at its start. That is now what the live
  rule reads for a gap made ready by `gap.defined`. It does not model the wait (up to 5 minutes) of a gap that
  reaches the implementor some other way without touches.
- **Test:** `test_a_gap_made_ready_is_routed_from_its_first_look` (tests/test_code_areas_factory.py) checks these
  cases:
  - `plan.route` with the route on, for a new gap and for one with a branch.
  - An unreadable definition, and an unreadable configuration.
  - The route off.
  - `parks.ready_again`, with a definition and without.
  - The rule reading no field, and a null one, as every area, on the factory's own map.

  `test_an_unreadable_field_is_the_worst_case` adds an item with no field and one with a null field. Both wait while
  an area is held. `test_the_route_switch_writes_or_empties_touches` now expects `{"unread": ...}` for a gap with no
  readable definition. The factory's `Slots` fixture (tests/test_factory.py) says `touches: []` in its `gap.defined`,
  as `plan.route` now does.
- **Seen to fail** (each mutation reverted):
  - The core reading a missing field as touching nothing fails both new checks.
  - `plan.route` without `touches` fails the new test.
  - `parks.ready_again` without `touches` fails it too.
- **Run here:** tests/test_code_areas.py, tests/test_code_areas_factory.py, tests/test_factory.py, tests/test_plan.py,
  tests/test_ai_limit_hold.py, tests/test_factory_knowledge.py and tests/test_factory_split_systems.py. ruff is clean
  on ergostat, tests and scripts. **Not run here:** the whole unit suite and the four browser files (no page changed).
  Other files whose fixtures say `gap.defined` without `touches` and then dispatch the real implementor on the
  factory model would now hold a gap that never got touches. Only `Slots` was found doing that.

### Round 3

The queue's one finding was a conflict with main (fa5a570c), which added `takes: {lanes:}` (merge-lanes-in-parallel)
on the same lines as `takes: {areas:}`. The merge keeps both:

- `TAKES_KEYS`, `Takes` and the schema carry `lanes` and `areas` side by side; each is compiled as on its own side.
- The dispatcher applies the areas' rule first, then the lanes': `areas.only` filters what `groups.only` lets through,
  and `lanes.choose` plans lanes over that. An item an area holds out is never planned on a lane, and the check that
  skips an item on top of a lane not taken stays as main wrote it.
- SPEC §9.5 keeps the *Areas* paragraph, then *Lanes*, and says which rule goes first.
- New test: `test_lanes_take_only_what_the_areas_let_through`. A block declares both. Two items share no lane entry but
  touch one area: the second waits.
- The factory model declares no lanes, so its implementor is unchanged.

## Entry

section: The factory (ergostat on ergostat)

- **Areas of the code have owners, and work is routed to avoid collisions** (built, on `code-area-ownership`; SPEC
  §9.5 *Areas*): `takes: {areas: {touches, holding, map}}` keeps an item out of an area another stream holds (a lane,
  a field's value such as a milestone, or a block); an item whose field is unsaid or unreadable touches every area,
  and each gap is said its touches in the event that makes it ready. The implementor's map is the 34 hot files drawn from main's 419
  conflicted merges (`dev/bin/areas.py draw`). Its replay cuts them to 373-397 only by stretching 97 h of work to
  225-240 h, so routing ships off (`[areas] route = false`). *Left*: the owner's choice of map and owners; a replay
  over the live record's send-backs; waits recorded, and simulated in the estimates.
