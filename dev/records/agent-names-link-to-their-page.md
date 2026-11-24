# agent-names-link-to-their-page: Every agent name links to its page, and Agents rows are links

depends-on: [agent-show-page]

Problem: agent names are plain text everywhere except the Agents table, where a row click opens a panel (ergostat/web/static/pages.js:100, a tr onclick: no focus, no new tab; filed Q47 records a re-sort opening the wrong agent). On :8791 the item page's lease table shows 'close', 'merge', 'ci', 'review' in its block column as text (shots/plan-agentshow-item-pattern.png); Recent runs, Actions 'by', the evidence actor line and Blocks captions likewise.
Change: one helper agentLink(name) (extending details.js:46) returning an a with href /agent/NAME (encoded). On /agents the name cell is agentLink; a plain click on the row outside the link still opens the panel. The item page's lease table block column, the Actions table's 'by' and 'approved by' (when a block), the evidence actor line (filed Q28/Q30 wherever it lands), the goal panel's controller and actuator names, the Blocks definition panel's 'block' row and the valve panel's list of taken items use it. The Record's machine filter (?machine=NAME) links back to the agent page in its scope line.
Definition of done:
1. On :8791/agents each row's first cell contains an a with href /agent/<its name>, reachable by Tab.
2. On /item/ticket%2FSCRUM-7 every non-empty cell of the lease table's block column is a link to /agent/.
3. On the Blocks panel for a machine block the agent's name is a link to /agent/.
4. A test listing the agent names asserts each occurrence in those containers is inside an a.
Files: ergostat/web/static/util.js or details.js (helper), pages.js, details.js, blocks.js, itemsets.js, a Playwright test.
Acceptance tests: the four points on :8791 and :8792 (structure only).
Budget: 30 net lines.

Milestone: agent-show-page. Owner items: 19. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1, built. The changes in code come to 22 lines added and 17 taken out (+5 net, within the 30-line budget).

- The helper: `agentA(name)` in details.js (it was in agent.js; moved, so that pages.js, blocks.js and itemsets.js can
  use it) returns an `a.agent-link` with href `agentHref(name)` = `/agent/` + the encoded name. The existing panel
  helper `agentLink(agent)` (the goal panel's "filled by", and so its controller and actuator rows) now uses it: a real
  href in place of `#`. A plain click still opens the agent's panel in place. A modified or middle click opens the page.
- Where it is used: the item page's lease Attempts table, block column (pages.js leaseView); the Actions on an item,
  "asked by" both waiting and answered, and the action page's "asked by" (when a block asked); the goal panel's actor
  line (details.js); the Blocks panel's "block" row for a machine block (`blk:` ids; blocks.js openBlock: the name
  is a link, then the rest of the row's text); the valve panel's leases line, its "being worked by" head and its
  "is working nothing now" line (itemsets.js); the Record's scope line for `?machine=NAME` ("from NAME", linked).
- Decisions taken without asking (each the more reversible choice):
  - The Agents row. agent-show-page (merged before this gap) already made the row a `rowLink` to /agent/NAME and its
    first cell an `a`. That is left as it is: a click on the row goes to the page, not the panel the Change line
    describes. Changing it back would undo the dependency's tested behaviour (test_agent_page.py
    test_a_row_on_agents_goes_to_its_page...). The first cell keeps `a > b`, because existing tests select
    `b:text-is(name)`.
  - "approved by" is not linked. The client has no list of agent names to tell a block approver from a person or the
    gate, and `approved by` arrives as composed text (actions/record.py who()). Linking it needs either the server to
    send the approver's kind or the page to read /api/agents. Left for a later gap.
  - "Recent runs" and the Blocks diagram's captions are named in the Problem line but not in the Change line. They are
    not touched.
- One existing test changed: test_items_page.py test_a_valves_leased_items_are_listed_live clicked the leases line's
  only `a`. The line now has two links, so it clicks `a.leased-link`.
- Tests: tests/test_agent_links.py (5 tests). (1) Each /agents row's first cell has `a[href=/agent/NAME]`, and Tab
  reaches every row's link. (2) The lease table's non-empty block cells are links to /agent/ (leaseView drawn on
  /item/ticket%2FSCRUM-7 with a lease history; the test project has no leases recorded, so the structure is checked
  with a given history). (3) The Blocks panel of `blk:work` has its name linked to /agent/work. (4) For every agent
  name: each exact-name text node in the Agents first cells, the lease table, the valve panel's leases lines and the
  actions' "asked by" is inside `a[href=/agent/NAME]`, and the count of containers drawn proves each was checked.
  (5) /record?machine=work links "from work" to /agent/work. Checked that they can fail: with the lease cell, the
  Agents first cell and the Blocks row put back to text, tests 1-4 all failed. With "asked by" put back to text, test 4
  failed (70 unlinked).
  Not covered by a test: the actor line, which needs a goal with recorded runs.
- Run here (Playwright, under the watchdog): test_agent_links.py 5 passed; test_agents_page.py with
  test_agent_links.py 18 passed; test_agent_page.py with test_item_sets.py 53 passed. test_items_page.py: 86 passed,
  4 failed, none of them this change's. Each is already recorded as failing on main in other gaps' records
  (ui-a-filter-that-matches-nothing-says-so-with-a-way.md, items-graph-one-show-choice.md):
  - test_every_surface_prints_the_servers_one_count_of_goals_off: expects "Loops ·", and main's heading is "Goals ·".
  - test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart.
  - test_the_graph_and_the_timeline_left_open_change_nothing[graph]: mutations on the items graph.
  - test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel: an 8 s wait in the full file. It passed alone, and
    with the two valve tests before it.
  test_page_refresh.py with test_keyboard_story.py: 10 passed, 2 failed, both recorded on main:
  - test_the_items_page_changes_only_the_new_row: `table.items tr` is no longer anywhere in the page code
    (what-is-holding-everything-up.md).
  - test_other_pages_left_open_change_nothing[diagram?view=process&by=events-graph]: 6 mutations, as in many records.
  ruff clean. Not run here: the unit suite, test_diagram_rendering.py, demo_check (no example touched).
- Refused: `git worktree add --detach /tmp/mainwt main`, meant to rerun the failing tests on clean main. The records
  named above were used instead.

## Entry

**Agent names link to their page** (done): an agent's name links to /agent/NAME wherever this gap's places show it:
the Agents table, an item's lease attempts, an action's "asked by", the goal panel's actors and "filled by", the
Blocks panel of a machine block, a valve panel's leases, and the Record's machine scope. In a panel a plain click opens
the agent's panel; a modified click opens its page. Left: "approved by" when the approver is a block.
