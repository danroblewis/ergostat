# ui-an-agent-s-recent-runs-name-the-item-the-outcome: An agent's recent runs name the item, the outcome and what it asked to do outside

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q39 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** agent panel 'Recent runs'; /items Actions table; item 'Gated actions'

**The problem:** Recent runs has no item, outcome or outward action and no links; its table is clipped at 1440 px. The Actions 'by' column is '–' for all 121 actions though each action page names its asker and approver.

**The change:** Columns: when, item (link), outcome (done or refused, with why), outward actions asked (links), cost. Move CPU and memory behind a 'resources' disclosure so the table fits. Fill 'by' with the block that asked and 'approved by' with who answered ('owner (offline stand-in)').

**User stories it serves:** D2, E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 the panel for 'work' lists at least three runs each with a link to /item/ and an outcome word, and the table's right edge is inside the panel; on /items?kind=ergostat.action no 'by' cell is '–'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. About 23 net lines outside `tests/`.

- Agent panel 'Recent runs' (`ergostat/web/static/details.js`) now has these columns: when, item (a link to `/item/`), outcome, outward actions asked (links to their `ergostat.action/` items), cost. The outcome is `done`; `refused: <why>` when the run gave its item back (`nack`); or `failed: <note>`. Readings, openings, decisions, tokens, CPU and memory are in a 'resources' disclosure under the table. The item and outcome cells wrap so the table fits the panel (`style.css`). The server (`web/server.py`, `agents/NAME`) now sends `asked`: each run's gated actions, matched by the action's `run` to the run's start event id.
- The /items Actions table: the built-in kind's columns are now `by` and `approved by` (`spec/ir.py`). Both are worked out by `actions/record.who()` and filled into the listing in `_as_listed`. `by` is the asking block, else its session, else "a session". `approved by` is "gate (auto)", or who answered with their note in brackets ("owner (offline stand-in)" when the note is "offline stand-in"), or "denied by …", or "not yet answered". The item's 'Gated actions' section (pages.js `actionsAbout`) says the same, through `/api/actions`.
- Choice made with nobody to ask (the reversible one): "owner (offline stand-in)" comes from the approver plus their note. The ticket-factory demo's teammate notes "the owner's offline stand-in", so there it reads "owner (the owner's offline stand-in)". Changing that note would be in `examples/`, outside this gap's files.
- Acceptance test: `tests/test_agents_page.py::test_an_agents_recent_runs_name_the_item_the_outcome_and_the_actions_asked_and_fit_the_panel`. That file belongs to the agent panel, and it has the fixture with runs. The test uses a seeded project at 1440 px, not the :8791 demo, which is not reachable from this container, so the acceptance as written on :8791 was not run here. It was seen to fail three times, once for each break: without the wrapping CSS rule (table right edge 1529 px against the panel's 1440), with the server's `asked` emptied, and with the listing's `who()` fill removed (every 'by' cell '–'). The existing cost test in the same file now reads the costs from the runs table and the MB values from the resources table.
- Run here: tests/test_agents_page.py (4 passed, Playwright, under the watchdog), tests/test_items_page.py (21 passed, Playwright), tests/test_gated_actions.py, test_web_access.py, test_inbox.py, test_spec_items.py (passed), and ruff (clean). Not run here: the unit suite as a whole, the other three browser files, and demo_check. There is no remote in the clone, so main was not merged in; local `main` is the base.
- Build fix (same round): the build step (`scripts/affected_tests.py`) selected only `tests/test_agents_page.py`. That file is a browser file and skips without Playwright, so the build ended at rc 5 with nothing run. The branch now also changes `tests/test_gated_actions.py`, with a unit test, `test_each_action_names_who_asked_and_who_answered_in_the_list_and_the_items_page`. It covers `record.who()` through `/api/actions` (`actions_api.listing`) and the Items listing (`_as_listed`): gate (auto), owner with note, denied, unanswered, and a session with no block. It was seen to fail when `who()` dropped the block. tests/test_gated_actions.py: 11 passed; ruff is clean.

Round 2, built. About 34 net lines outside `tests/`. Both blocking findings of round 1 are answered (there were no non-blocking ones):

- 'refused' came from a `nack` on agent.ran that the engine never writes. Now the server (`agents/NAME`) also sends `ended`: how each recent run's lease ended. These are the `ergostat.lease.ended` events whose `causedby` is the run's start, read from the earliest run's start onward. The panel says `refused: <why>` when that end is a `nack`. This covers a run that exits 0 and gives its item back, and a pool-full run (agent.ran with a note), which the panel now shows as refused rather than "done: no workspace free". The fixture is now seeded as the engine writes it. It has no `nack` on agent.ran. Run 58 is pool-full (agent.ran with its note, lease nack), run 57 failed, run 54 exited 0 with a lease nack, and the rest end with an ack. The test checks the outcome word of all ten rows. It was seen to fail with the panel reading `e.data.nack` again (rows 58 and 54 read 'done').
- `record.who()` checked `approved_by` before `denied_by`. Now it takes the action's folded state, which the fold builds in event order. A denial is final, so for a denied action it is the last answer, and `note` is the denial's. A gate's own denial (deny gate, risk, fence, the check at the act) reads "denied by its gate: <its note>", not "gate (auto)". An owner approval that the act's check then denied reads "owner, then denied by its gate: …". Before an answer, and after a re-hold, it reads "not yet answered". The unit test `test_each_action_names_who_asked_and_who_answered_in_the_list_and_the_items_page` adds the deny-gate case and the approved-then-denied-at-the-act case (a real `gate.approve` after the model's gate became deny). It was seen to fail with the old approval-first order and gave exactly the label the review found.
- Left as it is (reversible, named): when an `auto` approval is later re-held and the owner then approves without a note, the folded `note` is still the gate's. That re-hold path keeps the old note (`gate.rehold`, outside this gap's files).
- Run here: tests/test_gated_actions.py (11 passed), tests/test_act_risk.py with tests/test_inbox.py (57 passed), tests/test_agents_page.py (4 passed, Playwright, watchdog rc 0), tests/test_items_page.py (21 passed, Playwright, watchdog rc 0), and ruff (clean). Not run here: the unit suite as a whole, test_diagram_rendering.py, test_page_refresh.py, test_web_access.py and demo_check. The :8791 demo can't be reached from this container. There is no remote, so main was not merged in again.

Round 3, merged. The only finding was the conflict with main in `tests/test_agents_page.py`. Both sides were kept: main's new `test_each_group_heading_counts_its_rows_as_the_summary_does` and this branch's recent-runs test, each with its own `assert not errors` and `pg.close()`. No code outside the tests changed this round.

- Run here after the merge: tests/test_agents_page.py (5 passed, Playwright, watchdog rc 0), tests/test_items_page.py (23 passed, Playwright, watchdog rc 0), tests/test_gated_actions.py (11 passed), and ruff (clean). Not run here: the unit suite as a whole, test_diagram_rendering.py, test_page_refresh.py and demo_check. The :8791 demo can't be reached from this container.
