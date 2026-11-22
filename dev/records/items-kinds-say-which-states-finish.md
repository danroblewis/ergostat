# items-kinds-say-which-states-finish: Each item kind says which of its states are finished, from one function for the Items page, the dependency graph and the estimates, and the page shows it

depends-on: []

Problem: what counts as finished is worked out on the server in precedence.py Kinds._info (precedence.py:58-97: declared `messages: {done:}`, else spec/itemindex.py:119 done_states, 'the states after the first that no item has left', minus queue, leased, dead and paused) and never reaches the list: /api/items gives each kind only states and counts. So 'Collapse done' (pages.js:689) names nothing a reader can check. For ticket-factory's ticket (nothing declared) the inferred set changes as items move; a one-state kind (pool: [held]) falls back to its last state, so every pool counts as done. Owner: 'which states are done?' done_states has other callers with their own rules (process.py:75-83, which also strips 'leased'; series.py:338 and 371-398, state counts over time; a separate done_states in messages/route.py:39); they are not touched here (finished-rule-in-series-and-routing follows).
Change: move the rule into one function, ergostat/spec/finished.py finish_of(spec, kind, left) -> {finished: [...], paused: [...], dead: bool, from: 'declared'|'inferred'|'none', lives_on: bool}. A kind with one state, or nothing declared and nothing inferable, lives on (finished empty). Kinds._info (precedence.py:60), the estimates (numbers/etamodel.py) and the items listing call it. /api/items gives each kind finished, paused, dead, finished_from, lives_on. Under each kind's state chart (charts.js flowChart legend) one line: 'finished: merged, closed (declared)', 'finished: answered (inferred: no item has left it yet)' or 'lives on'; paused states are marked 'paused'. This line and the kind's bar (items-one-section-per-kind-closed) deliver filed Q61's 'finishes / lives on' tag, which is closed as superseded.
Definition of done:
1. The Items listing, precedence.py and the estimates decide finished, paused and lives-on through finish_of; none of the three calls done_states directly. process.py, series.py and messages/route.py are unchanged (a test asserts their outputs on the demo specs are byte-identical before and after).
2. /api/items kinds carry the five fields.
3. A one-state kind is lives_on with finished empty.
4. Each kind's legend marks finished and paused states and says where the set came from.
5. SPEC §5a (Items) states the rule in one paragraph.
Files: new ergostat/spec/finished.py, ergostat/precedence.py, ergostat/spec/itemindex.py, ergostat/spec/items.py (listing kinds), ergostat/numbers/etamodel.py, ergostat/web/static/charts.js, pages.js, docs/SPEC.md, new tests/test_finished_states.py, tests/test_items_page.py.
Acceptance tests: unit: a factory-shaped spec gives gap finished=[merged, closed], paused=[parked], from=declared; pool lives_on; ticket-factory's ticket from=inferred; the parity test for the untouched callers. Browser: on a served fixture a kind with a declared done has 'finished:' and the state names in its legend; a one-state kind has 'lives on'.
Budget: 130 net lines.

Milestone: items-page-readable. Owner items: 4 (which states are 'done'), 1 (the definition the default filter hides). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Where the build differs from the text above, and why (each the most reversible option, since nobody was there to ask):

- ticket-factory's ticket is not inferred: examples/ticket-factory/ergostat.yaml:80 declares `done: {ticket: [done]}`.
  The acceptance test checks that ticket is `declared`, that the example's `okr` (nothing declared) is `inferred`, and
  that its one-state `report` lives on (tests/test_finished_states.py::test_ticket_factory_kinds_say_where_their_finish_comes_from).
- numbers/etamodel.py and spec/itemindex.py are not edited. The estimates already read finished and paused from
  precedence.Kinds, and Kinds now gets them from finish_of, so they go through it with no change to etamodel.py.
  itemindex.done_states stays as it was for the callers this gap leaves alone, and so does the item cache's
  `_open` test, which only decides what stays folded in memory.
- The behaviour change: when every state after the first has been left, the old rule falls back to the last state.
  finish_of drops that fallback, so the kind lives on (from `none`). This follows the definition's "nothing
  inferable lives on", and it applies to the relations' status and to the estimates.
- Parity snapshot (tests/fixtures/finished_parity.json): this session could not unpack main's tree to run the test
  there, so the snapshot was written on the branch. That stands in for main because `git diff main` is empty for
  process.py, series.py, messages/route.py and spec/itemindex.py. The test was seen to fail when done_states was changed.
- The listing reads the states items have left as of now, not as of `until`. A record with no item index on disk
  has no left states, so its kinds infer from the declared states alone, the same way Kinds does.
- The line under each kind's states also appears on a card with no flow chart. A finished or paused state's box in the
  chart's legend carries that word as its title.
- Q61 is not closed here: no file of filed questions was touched.
- Not run here: the unit suite as a whole, test_diagram_rendering.py and test_page_polling.py, demo_check (no example changed).
