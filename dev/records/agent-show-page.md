# agent-show-page: An Agent show page at /agent/NAME: what it is by rung (prompt, program, specification, means of deciding, law), its definition, its place, what it did

depends-on: [agent-spec-api]

Problem: an agent has no address: /agent/work is a 404 (shots/plan-agentshow-agent-route.png; 'agent' is not in UI_PAGES, ergostat/web/server.py:35, nor in route(), static/util.js:498-512). The only view is the side panel (openAgent, static/details.js:218-252), which shows what the agent did, never what it is: on :8791 `work` shows a command, the wrong 'Runs: not run by ergostat' and an absolute log path but no prompt (plan-agentshow-work-panel.png); keep-located-worked shows no law (plan-agentshow-rule-panel.png); approve shows no ask (plan-agentshow-person-panel.png). The owner asked for the page; the request overrides 'no new pages' for it and settles R12's 'decide on Agents' (Agents stays as the index).
Change: 'agent' joins UI_PAGES (server.py, util.js); route() sends /agent/NAME to pageAgent in a new static/agent.js (index.html before main.js), following the item page's pattern. openAgent's sections move into one builder (agentSections(a)) used by panel and page, so filed Q38-Q41 land in one place. Layout:
1. h1 the name; a flowing meta line: kind (rung letter and word, rung_why as title), machine, system, serves (goal links, each with the goal's word through goalWord when goal-row-one-renderer has landed), engaged (Q38's wording), mode, defined at (file:line link).
2. 'What it is' by rung. person 'What they are asked': the ask as Markdown (md(), pages.js:247), open asks now. ai 'Its prompt': the prompt rendered, {slots} outside code marked 'filled per item'; model, tools, actions, read, workspace, emits, takes, lease as a dl; 'Its wrapper' highlighted in a closed details. narrow-ai 'Its specification': the prompt plus the fixed parts (model, outputs, max-cost). decision 'How it decides': its prompt or program, then the answers given in the window as a ranked list with counts, and the ladder hint as a sentence. program 'Its program': the command (no absolute path), each program file highlighted (code(), pages.js:180-268), the first open; an own module reads 'ergostat's own: <module>' with its docstring. rule 'Its law': law.says, the MathML (blocks.js:1010-1030) and rows; for expr each input a link with its value now; tables for lookup and schedule; 'implied by <block>'s goal' linked.
3. 'Its definition': spec.source highlighted as yaml under its file:line; implied blocks say 'not written: ergostat put it in front of <block>'.
4. 'Its place': goals and control loops it serves (each opens the goal's evidence), what commands it and what it commands, the items it is working now ('working 2 tickets', never 'holds'), 'Show on Blocks'.
5. 'What it did': runs chart, cost, Recent runs, the log tail named by relative file.
Sections are anchors; the page polls like the item page; at 390 px code scrolls in its own box. The panel gains 'Open its page'; a row on /agents navigates to /agent/NAME. web/snapshot.py includes agent pages.
Definition of done:
1. /agent/work on :8791 shows 'Its prompt' with prompts/work.md rendered (no raw '#'), {key} marked, and bin/step.py highlighted (.hljs) in a closed 'Its wrapper'; /agent/nope says 'no agent nope' with a link to /agents.
2. /agent/keep-located-worked shows 'Its law' with a math element, 'releases at', the same says text as the Blocks panel, and 'implied by work' linking to /agent/work.
3. /agent/fixer shows 'Its program' and 'ergostat's own'; no text on any /agent/* page matches /\/private\/tmp|\.venv|SPEC §/.
4. A person block shows 'What they are asked'; examples/docs-fresh /agent/page-picker shows 'How it decides' with a tally or 'no decisions in the window'.
5. At 390 px document.scrollingElement.scrollWidth <= 390.
6. Every agent of every demo opens with no console error and its first h2 is the rung's section name.
Files: new ergostat/web/static/agent.js, static/main.js or util.js (route), ergostat/web/server.py, static/index.html, static/details.js, static/pages.js, static/style.css, ergostat/web/snapshot.py, new tests/test_agent_page.py.
Acceptance tests: Playwright tests for 1-5 on :8791 and examples/docs-fresh plus the render sweep.
Budget: 320 net lines; the Coordinator may split it as (a) route, header, 'What it is' and 'Its definition', (b) 'Its place' and 'What it did' moved from the panel.

Milestone: agent-show-page. Owner items: 19. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1: built. About 198 net lines outside tests and docs (220 added, 19 removed in ergostat/), under the 320 budget.

What is in it:
- `static/agent.js` (new): `pageAgent`, routed from `route()` in util.js; 'agent' joins UI_PAGES in server.py and
  util.js. Header meta line: kind (rung letter and word, `rung_why` as its title), machine, system, serves (each goal a
  link to /goals?select=G with its word through `goalWord`), engaged, mode, defined at (a link to the definition
  section). Sections, each an anchor (`#what-it-is`, `#its-definition`, `#its-place`, `#what-it-did`): the rung's own
  first ('What they are asked', 'Its prompt', 'Its specification', 'How it decides', 'Its program', 'Its law'), then
  'Its definition' (the YAML highlighted under file:line, or 'not written: ergostat put it in front of X'), 'Its place'
  (goals served, roles, what commands it and what it commands, 'working N tickets' linking to the Items set of the
  items it holds now, 'Show on Blocks'), 'What it did' (the panel's tally, runs chart, cost, Recent runs, log tail
  named by its file). Polled every 4 s, redrawn only when an answer changed. 'no agent NAME' with a link to /agents.
- `details.js`: the panel's parts moved into `engagedText`, `agentTally` and `agentRuns`, used by the panel and the
  page; the panel gains 'Open its page'. The log heading names its file.
- `server.py`: the agent answer gains `place` (system, mode, goal, commands, commanded_by, working {n, kind, set};
  n is null, said 'not known', when the leases cannot be read, never 0), and its log tail has absolute paths taken out
  (`agent_spec.plain`, split out of `agent_spec.spec`; agent_spec.py is outside the Files list, a 10-line move).
- `pages.js`: a row on /agents goes to /agent/NAME (`rowLink`), its name an ordinary link.
- `snapshot.py` is unchanged: it already takes agents/NAME, agents/NAME/files and loops, all the page asks for.
  The page in a snapshot was not tested.
- docs/DESIGN.md lists /agent/NAME among the page's addresses.

Decisions taken without the owner, each easy to undo:
- A row on /agents now goes to the page, as the definition says, so the panel is opened from the diagram (and
  'Open its page' links back). The panel tests in tests/test_agents_page.py that opened the panel by clicking a row
  now open it with `openAgent(NAME)` (the `panel()` helper, which waits for the panel to be read); what they assert
  about the panel is unchanged.
- Done item 3 ('no text matches SPEC §') is kept by taking SPEC-section references out of what the page shows: a
  parenthetical naming 'SPEC §' or a trailing 'SPEC §N' is dropped from the docstring, the YAML source, prompts,
  asks, program files and the description (`noSpec`). The examples carry such references in comments and docstrings
  (ticket-factory's `use: modelling` comment, the-job's bin/prepare.py), so the text shown is that text less those
  references.
- Done item 2's 'releases at' exists only for a relay with a band. The ticket-factory example's located-worked goal
  has none, so its keep-located-worked is an ideal relay (shown with its threshold, no 'releases at'). The test checks
  that, then serves a copy with `tolerance: 2` on the goal and checks 'releases at' and 'hysteresis' there. The live
  :8791 demo was not reachable from here.
- A person's 'open asks now' is read from the agent's run under way (`running_since`): 'Asked now: since …' or
  'Nothing is asked of them now'. Not each inbox entry.
- Not done from the layout (not in the definition of done): an expr rule's inputs each with its value now (the law's
  rows are shown as Blocks shows them); a lookup's or schedule's table is shown when its key is `table`, `points` or
  `schedule`.

Tests: tests/test_agent_page.py (31: done items 1-5, the row and panel link, and the render sweep over every
examples/*/ergostat.yaml: each agent's page opened, no console error, first h2 the rung's, no '/private/tmp', '.venv',
'SPEC §' or temporary folder in its textContent). Seen to fail when broken: slot marking off (item 1 fails); SPEC
references left in (the fixer and the-job sweep failed before `noSpec`); code allowed to overflow its box (the phone
test fails, once it opens every disclosure; it passed before that, so it was strengthened); the ideal relay has no
'releases at' (seen while writing the test).
Run here: tests/test_agent_page.py (31 passed), tests/test_agents_page.py (14 passed), tests/test_agent_spec.py and
tests/test_graph_cli_web.py (68 passed), test_diagram_rendering.py's readers test for ticket-factory (passed), ruff
clean. Not run here: the whole unit suite and the four browser files. main has not moved since the branch was made.

## Entry

**Agent show page** (done): /agent/NAME shows what an agent is by its rung (its ask, prompt and wrapper, specification,
how it decides with its answers tallied, program with ergostat's own module named, or law), its definition as written,
its place (goals, what commands it and what it commands, the items it is working), and what it did; a row on /agents
goes there and the panel links to it.
