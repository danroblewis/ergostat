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
