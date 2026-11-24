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
