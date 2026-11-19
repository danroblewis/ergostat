# mended: the modelling template measures what it draws, and a panel says what it counts

Branch `mended`, from main (ec0e7da). The owner's report (2026-11-19): in ticket-factory `model-mended` showed a
short outflow from `model-error`, yet no `ergostat.model-change` was ever accepted (all superseded, inconclusive or
refused). There was no change to find. The cause is in `ergostat/library/templates/modelling/template.yaml`:
`model-mended` is measured by `changes: falls` of the fit, so any fall in the replay error counts (the record moving
on and fitting better), while its `driven-by` says accepted changes cause it, a link nothing measures; `model-drift`
likewise counts every rise. The diagram tells a causal story its measurements do not support. Separately, a stock's
or flow's side panel says its unit ("per minute") but not what it counts, so the owner could not tell the stock was
items of a kind.

## Definition of done

**Honest measurement.** Accepting a change (`proposals.accept`, the one path the owner, the CLI, the inbox and the
judge's `auto` policy all take) records on the change item what it lowered the scaled error by (`fit_gained`: its
fit before minus after, as Accept measured them). A flow's `items:` sensor may say `sum: FIELD`: the rate per hour
of that field summed over the items entering (or leaving) the state, instead of their count, in the engine's reading
and in the replay's record. `model-mended` is measured as `items: ergostat.model-change, entering: accepted, sum:
fit_gained`: only what the changes written took off the error, so a fall with no change accepted never shows in
it. A new `changes: rest` is a two-way flow's rate from its stock's net change less what the stock's other
measured flows account for (the residual flow); `model-drift` becomes two-way, measured so: whatever moved the error
that the written changes do not explain, rises and falls alike (the record moving on, the world changing). One
residual flow, not drift plus an "unexplained improvement", because nothing measures the two apart; the template's
`reading:` and the flows' descriptions say so. The hand-wired fixture and `scripts/scale_model.py` follow. Every
example using `use: modelling` (coordinator, image-squeeze, the-job) still passes `check`, coherence and
`demo_check`; nothing is re-recorded silently (any recorded drawing that changes is named in the commit).

**A check finding for the class of mistake** (`measured-not-caused`): a flow measured by `changes: rises` or
`falls` of its stock that declares a cause (`driven-by`) from another flow: "measured as every fall of X, but drawn
as caused by Y: either measure what Y contributes, or say it is any fall". Not on the fixed template.

**A panel says what it counts.** The Dynamics and Blocks side panels (details.js, dynamics.js: no new panel) of a
stock or flow whose sensor counts items, or reads its stock's changes, open with one plain line: a stock "Counts
items of kind `K` in state `S`" (and its `where:`), a flow "Items of kind `K` entering `S`" (or leaving; "summing
`F`" with `sum:`), each with a link to the Items page filtered to them; a `changes:` flow "Every rise (fall) of `X`,
whatever caused it" ("`X`'s net change less its other measured flows" for `rest`). The unit line stays, after it.

**Docs.** One paragraph in `docs/MODELLING.md`: a measured flow versus a causal claim. SPEC names `sum:` and
`changes: rest`.

## Acceptance tests

- `tests/test_mended.py::test_accepted_change_shows_in_mended`: a change accepted with a fit improvement is read by
  `model-mended` (its `fit_gained`, per hour over the window).
- `tests/test_mended.py::test_fall_without_change_is_drift`: the error falls with no change accepted: `model-mended`
  reads 0 and `model-drift` (`rest`) reads the fall, negative.
- `tests/test_mended.py::test_check_finds_measured_not_caused` and `::test_template_has_no_such_finding`.
- `tests/test_mended.py::test_replay_sum_and_rest`: the replay's record of a `sum:` flow and of a `rest` flow.
- `tests/test_items_page.py::test_panel_says_what_it_counts`: the panel's first line for an items-counting stock, an
  entering flow and a `changes:` flow, with the Items link (Playwright).

## Budget

300 net lines outside `tests/` and `docs/`.

## Added during the branch (the coordinator, for the owner)

**Finding the model's changes on the Items page.** What was there: every built-in `ergostat.*` kind (model-change,
claim, message, verdict, decision, correction, context, report, action, workspace) sat in one `ergostat` section at
the end of the page, after the project's own systems, headed by its raw kind name; nothing is folded by default
(only what the owner folded, remembered per project); the search matched ids and fields, never a kind; and the list
carried the newest 500 items of all kinds, so on a busy record a quiet kind's items were never listed at all, only
counted. Now: a built-in kind is under the system that counts it (model-change under `modelling`; one nothing counts
stays under `ergostat`); a built-in kind is headed by its plain name ("Model changes", its kind's name small beside
it); every kind's newest items are listed however busy the rest; the search matches kind names (and plain names)
and opens a folded system holding one; the stock panels link to their items (above); the Model page's review queue
links each change to its item page.

**A stock's panel names its kind first** and links to `/items` with exactly the query it counts (kind, states,
`where:`); the Playwright test holds the list's length to the stock's reading.

**A valve's leased items, live.** A valve whose flow a block that takes items moves: its panel names the kind, how
many are leased now and by which block (and agent), and links to the Items page's list of exactly those (`leased`,
`where=lease.block:BLOCK`). That list, like a stock's, follows the record by the page's existing poll (4 s, redrawing
only what changed): items appear when leased and go when given back, finished, expired or killed. Each row shows its
lease's holder, how long it has been held, and the time to expiry.

**Tests added:** `tests/test_items_page.py::test_the_model_changes_are_found_by_heading_search_and_panel` and
`::test_a_valves_leased_items_are_listed_live`; `tests/test_item_systems.py` follows the new placement.

**Budget:** unchanged, 300 net lines: the additions fit (about 150 net lines at the end).
