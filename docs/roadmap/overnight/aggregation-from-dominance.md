# aggregation-from-dominance: chains of stocks within a system that no feedback loop beyond each stock's own drove over the window, named on the system's panel as candidates to aggregate into one delay
depends-on: []

## Definition of done

A new module `ergostat/numbers/aggregation.py` has `candidates(spec, dom)`. It reads the result of
`dominance.dominance(spec, data)` (Loops That Matter on the replay over a window) and returns, per system (`None` for
a model with no systems), the groups of stocks that are candidates to aggregate (Simon and Ando 1961; Iwasaki and
Simon 1994: a chain whose stages are each driven only by their own drain behaves as one delay).

1. **Which stocks qualify.** A stock qualifies when all of these hold:
   - It is in the system's own chain (its innermost system).
   - Every feedback loop through it (`causal.loops`) that runs through two or more stocks never dominated any stock
     in any bucket of the window. (A loop's only stock being this one makes it the stock's own loop, which may
     dominate it.)
   - When it has loops through it: it is in `dom["stocks"]`, `named` is True, its `steps` are above 0, and it has no
     tied bucket while it has any loop through two or more stocks.
   - A stock that no loop runs through qualifies structurally.
   - Anything unknown disqualifies, never qualifies: not scored, not named, never moved, or the dominance missing.
2. **Groups.** A group is a maximal set of 2 or more qualifying stocks in one system, joined by flows from one to the
   next (a material chain). Two qualifying stocks with no flow between them are not a group.
3. **What is said.** Each group is said as: `over the window (SINCE to UNTIL) no feedback loop beyond each stock's own
   drove stock.a, stock.b: a candidate to aggregate into one delay`, in material order.
4. **Where it shows.** `GET /api/dominance` returns `aggregate: [{system, stocks, said}]` for the window it scored.
   The Dynamics page's system panel (`dynamics.js`, beside the `size` row) shows one `aggregate` row per group of that
   system, from that response. There is no new panel or page, and no row when there are no groups or the dominance
   could not be worked out. `check` is unchanged.
5. **Docs.** SPEC §12c (after loop dominance) and §4a say what is computed, over which window, and that it is a
   candidate, not a finding. `docs/proposals/architecture.md` §4 moves aggregation from "Not computed" to "Computed
   today" (the computed rung; the AI rung's proposal stays left). `docs/GAPS.md`'s architecture entry is updated.
6. **Done.** The four suites pass with rc 0 and no page test skipped; ruff is clean; `demo_check` passes (the
   Dynamics panel changes); origin/main is merged in and the suites run again.

## Files to touch

- `ergostat/numbers/aggregation.py` (new)
- `ergostat/web/numbers_api.py` (`loop_dominance`: add `aggregate`)
- `ergostat/web/static/dynamics.js` (the system panel's `aggregate` row)
- `tests/test_aggregation.py` (new), `tests/test_diagram_rendering.py` (one page test)
- `docs/SPEC.md`, `docs/proposals/architecture.md`, `docs/GAPS.md`

## Risks

- **lesson-3 (failing open):** a stock with a loop the method could not score, a tied or unnamed bucket, a stock
  that never moved, or a failed replay could each count as "no loop dominated it", which is the claim the candidate
  rests on. Each must disqualify, and no row is shown when dominance is missing.
- **lesson-8 (claims too wide):** saying "the last week", "should be aggregated", or "no loop drove it" when each
  stock's own drain did. The wording names the window actually scored (since and until), says "beyond each stock's
  own" and "a candidate", and SPEC says the same.
- **lesson-5 (stale state):** a panel showing groups from a previous model version or window. The cache key already
  carries `live.mtime` and the window. A test changes the model and sees the row go.
- **lesson-9 (tests that can't fail):** a test whose fixture has no multi-stock loop cannot show that a loop which
  dominated disqualifies a stock. Each disqualifying test has a counterpart differing in one thing that does qualify.
- **lesson-7 (merges):** `/api/dominance` and `dynamics.js` are shared, so merge origin/main and run the browser
  files again.
- **lesson-13 (staying in the gap):** an unrelated failure seen in the suites is reported, not fixed here.

## Acceptance tests

- `tests/test_aggregation.py::test_a_chain_of_first_order_stages_is_a_candidate_to_aggregate`: in system `plant`,
  stocks a → b → c each drain by stock/τ, with a fed from outside and a measured record over an hour. `candidates`
  gives one group [stock.a, stock.b, stock.c], and the text names the window's since and until.
- `tests/test_aggregation.py::test_a_dominant_loop_through_two_stocks_disqualifies_them`: the same chain plus a
  reinforcing loop c → inflow of a, strong enough to dominate a within the window, gives no group with a. With the
  loop's gain set so it never dominates, the group is back. Removing the "never dominated anywhere" check makes the
  first half fail.
- `tests/test_aggregation.py::test_unknown_dominance_is_never_a_candidate`: three sub-cases. A loop through b goes
  through a decision with 2 inputs (not scored); a window in which b never moves; dominance missing. None gives b in
  a group; the unchanged chain does.
- `tests/test_aggregation.py::test_stocks_without_a_flow_between_them_are_not_a_group`: two qualifying stocks in one
  system that share no flow give no group; one in each of two systems give no group.
- `tests/test_aggregation.py::test_the_dominance_api_returns_aggregate_and_drops_it_when_the_model_changes`:
  `/api/dominance` has the group. After the model is rewritten with the dominating loop, a fresh call does not.
- `tests/test_diagram_rendering.py::test_the_system_panel_names_stocks_to_aggregate`: on the Dynamics page, opening
  system `plant` shows an `aggregate` row with the group's text. A system with no group has no such row.
- The four suites pass with rc 0 and no page test skipped; ruff is clean; `demo_check` passes; the suites run again
  after merging origin/main.

## Size budget

160 net lines of code outside `tests/` and `docs/` (expected about 110: `aggregation.py` ~75, the API ~8, the panel
row ~20).

## Notes from the plan review (answer each)

- Rule 1 contradicts itself: 'a stock that no loop runs through qualifies structurally' vs 'anything unknown disqualifies: never moved, or the dominance missing'. Settle it explicitly: a stock with no loop still needs the dominance result present and steps > 0 (or say why not). Add a test: a loop-less stock that never moved, and one with the dominance missing, are in no group.
- lesson-8: a stock with no loop through it has no drain of its own (a pure accumulator), so 'a chain whose stages are each driven only by their own drain behaves as one delay' does not hold for it. Either require each stock in a group to have its own first-order loop (its drain), or narrow the wording and SPEC so 'one delay' is not claimed for chains that contain accumulators. Add a test for whichever you choose.
- Unscored loops must disqualify: an unscored loop through two stocks has trivially 'never dominated', which is exactly failing open (lesson-3). State that any loop through the stock that is not scored disqualifies it, whether it runs through one stock or two. In test_unknown_dominance_is_never_a_candidate, make the unscored loop run through two stocks. Its counterpart must differ in one thing only: the same loop, made scorable (a decision with 1 input). Removing the loop is not that counterpart (lesson-9).
- test_a_dominant_loop_through_two_stocks_disqualifies_them: the loop c -> a's inflow runs through a, b and c, so assert that there is no group at all, not only 'no group with a'.
- Groups: 'maximal set joined by flows' and 'material order' are undefined for branches (a->b, a->c) and for material cycles. Define it: either linear chains only, or a stated order. Add a test for a branch.
- lesson-5: the cache key relies on live.mtime, and a rewrite within the same second (or on a filesystem with coarse timestamps) can leave it unchanged. In the API test, set mtime explicitly (os.utime) or key the cache on the model's content, so the test cannot pass or flake because of timestamp resolution.
- Report, for each disqualifying rule (multi-stock loop dominated, not named, tied bucket, steps 0, unscored, dominance missing), that removing the check makes its test fail, not only the 'never dominated' check.
