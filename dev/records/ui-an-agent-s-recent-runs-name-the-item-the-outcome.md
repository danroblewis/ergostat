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
