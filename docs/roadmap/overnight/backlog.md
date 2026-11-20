# backlog: the gaps groomed into an ordered backlog

depends-on: []

Branch `backlog`, from main. Asked by the owner (2026-11-20): "the gap tickets we have don't have dependencies. If we
don't have dependencies, we can't do a topological sort to choose the next gap... we may want to re-order our gaps,
which may mean setting dependencies, and it may mean suggesting an ordering and using a constraint solver or something
to propose a reordering... We can also trust an AI agent to do that solving process. We currently don't have a gap
task queue that is ordered or orderable in the way that a backlog of tickets should be groomed and prioritized."

## Definition of done

The open gaps are a groomed backlog: each has a `rank` (an integer, lower first) and grooming fields (`value` 1-5,
`size` S/M/L or hours, `risk` low/medium/high, `why`), and the implementor and the planner take the unblocked gaps (each
dependency finished) in rank order.

1. **Ordering on takes (the core change).** `takes:` could not order by a field: it took the oldest first, or with
   `unblocked: true` the critical first. A block's `takes:` gains `order: FIELD`: the items it may take are taken by
   that field, lowest first, the items without it last; the block's own order (its states of `at`, oldest first, or
   the critical first) is kept among equals. The completion estimates queue the items in the same order. SPEC §9.5
   (the takes table and *Dispatch*) and §5a (the projected queue) say so. The implementor takes
   `{unblocked: true, order: rank}`; the planner takes `{unblocked: true, order: rank}` too.
2. **The solver** (`dev/bin/solve.py`, a program, deterministic): given the backlog's gaps, their `depends_on`, value,
   size, risk and pins, a ranked list with a reason for each. A topological order (a gap after every gap it depends on
   that is still in the backlog), by list scheduling: at each place, of the gaps whose dependencies are placed, the
   highest score, where score = WSJF (value / size points, S 1, M 3, L 8, hours / 4; risk multiplies the size: low 1,
   medium 1.25, high 1.5) times (1 + 0.25 for each backlog gap that waits on it, however far: the critical path).
   Missing grooming fields are assumed (value 3, size M) and said. A pinned gap (`rank_pin: N`) takes place N once it
   is due, its unplaced dependencies pulled ahead of it (said when the pin cannot be held). Ties: the earlier rank,
   then the id. A cycle is refused: no order, the cycle said as the finding.
3. **The groomer** (`backlog.py groom`, an `ai` block on Opus, pool 1, commanded by `groom-when` while the switch
   `grooming-open` reads 1, default 0, and money is left). Every 30 minutes it looks; it grooms when a backlog gap has
   never been groomed, or the last grooming is older than `[backlog] every_hours` (12), and no proposal waits in the
   inbox. A session in a read-only clone of main is given the open gaps (titles, GAPS.md entries, definitions, current
   links and fields, pins), the module map and main's recent log, and answers one fenced JSON: dependencies to add and
   remove, value, size, risk and why for each gap, gaps to close (done on main, or a duplicate of another, e.g.
   superseded by a `*-continued` gap) and splits of gaps too large. The program checks it (names that are gaps, no
   link that closes a cycle, no pin moved, closes only of gaps not started) and runs the solver on it. The proposal is
   one gated action, `groom-backlog` (the coordinator approves), whose summary and file
   (`run/backlog/<time>.md` beside its `.json`) show the diff: links added and removed, rank changes, closes, splits.
   Approved, `backlog.py apply FILE` writes the events: `gap.groomed` (rank, value, size, risk, why, depends_on) and
   `gap.closed` (an end state, `closed`, finished: `end` done or duplicate, with its reason; a duplicate's dependents
   wait on what it duplicates instead).
4. **The operator's overrides** (`dev/bin/backlog.py`, the coordinator's or the owner's): `show` (the backlog in rank
   order), `pin GAP N` (and `pin GAP --off`), `dep add GAP ON` and `dep rm GAP ON` (a removal is kept, so the intake does
   not add the link again from GAPS.md), `close GAP --done|--duplicate-of OTHER --why TEXT`, `propose` (the solver's
   order and reasons, and how it differs from the ranks now, writing nothing) and `apply FILE`. Each change re-ranks
   the backlog with the solver. Pins are respected by the solver and the groomer.
5. **Visible.** The Items page's Graph draws the gaps' `depends_on` edges (checked on the factory's own model); the
   list sorts by a column (`sort=FIELD` in the address, a header's click), and the gap shows `rank`, `value` and
   `size`. `status.py` prints the top of the backlog.
6. **The intake's done rule.** An entry's *head* is the text right after its bold title, over its continuation lines:
   the parenthetical that opens it (balanced, across lines), else the clause after its colon. The head's first clause
   (up to the first `;`, `,` or `)`, emphasis stripped) beginning with the word `done` marks the entry done ("(done",
   "(done, on `x`", "(**done**", "(done on `x`; ..."); one beginning `superseded by` marks it superseded. "first slice
   done", "partly done", "computed measures done" are not done. A done or superseded entry is never found as open; one
   the record holds open (not yet started) is closed (`gap.closed`, end done or duplicate, its reason the GAPS.md
   line).

## Acceptance tests

- `tests/test_backlog.py::test_solver_orders_topologically_by_wsjf_with_a_bonus_for_unblocking`
- `tests/test_backlog.py::test_solver_holds_pins_and_pulls_their_dependencies_ahead`
- `tests/test_backlog.py::test_solver_refuses_a_cycle_with_a_finding`
- `tests/test_backlog.py::test_takes_order_by_rank_among_unblocked` (the dispatcher's hook, and the spec's `order:`)
- `tests/test_backlog.py::test_groomer_proposes_and_apply_writes_the_events` (a stand-in AI; the gated action held)
- `tests/test_backlog.py::test_groomer_refuses_cycles_and_pinned_ranks_and_closes_of_started_gaps`
- `tests/test_backlog.py::test_close_done_and_duplicate_repoints_dependents`
- `tests/test_backlog.py::test_intake_done_rule_on_a_gaps_fixture` and `::test_intake_done_rule_on_the_real_gaps_md`
- `tests/test_backlog.py::test_backlog_commands_on_a_fixture_instance` (show, pin, dep add/rm, close, propose, apply)
- `tests/test_backlog.py::test_the_items_graph_draws_gap_dependencies`
- `tests/test_items_page.py::test_items_list_sorts_by_a_column`

## Size budget

450 net lines outside `tests/` and `docs/` (the core change, `dev/bin`, `dev/model`, the prompt, the page).
