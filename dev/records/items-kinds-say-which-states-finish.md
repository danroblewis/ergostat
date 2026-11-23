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

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:20).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:20).

Its runs failed past their attempts (a dead letter):
- attempt 16: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 17: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 18: nack given back
- attempt 19: nack the run ended with gap/items-kinds-say-which-states-finish still parked

## Where it stopped

Continued, round 1 (2026-11-23). Main (2a97eafb) merged in. The one conflict was in tests/test_items_page.py, where
both sides had added a test at the end of the file. Both are kept. No code was changed after the merge.

Run after the merge: tests/test_finished_states.py (5 passed). tests/test_items_page.py under the watchdog had 28 passed
and 1 failed, twice. Ruff is clean on ergostat, tests and scripts.

The failure is main's new test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, which times out at
test_items_page.py:1297 waiting for the other project's entry in the header's project menu. This branch does not change
that menu. The project list (web/server.py:244-272) is built once at start-up and then every 60 s. The first project's
server makes its list before the second project is running, so that entry can take up to 60 s to appear, and the test
waits only 30 s. This looks like a timing issue between main's test and the server, not this gap (lesson 13). It is
left alone. It was not run on clean main because this session was not allowed to make a worktree of main
(`git worktree add /tmp/mainwt main` was refused). This branch's own browser test in that file passes.

Not run here: the unit suite as a whole and the other browser files (the factory and the merge queue run them).
