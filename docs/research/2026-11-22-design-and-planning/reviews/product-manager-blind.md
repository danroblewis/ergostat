# ergostat, reviewed blind by a product manager

Screenshots are in `<workdir>/design/shots/` (all `pm-*.png`).
I used the demos at :8791 (ticket-factory), :8792 (the-job), :8793 (image-squeeze), :8794 (roadmap), :8796 (software-factory) and :8797 (big), at desktop size, at phone size (390x844) and in dark mode.

## What I think this is (written before judging)

ergostat watches and steers automated work systems. In the demos these are mostly "factories" where AI agents and scripts take tickets through to merged PRs, plus a personal "job" assistant, an image-compression lab, a roadmap and a small product with users. It draws each system as a stock-and-flow (system dynamics) diagram and as a control-engineering block diagram. Every goal is a "loop" with a setpoint, and each loop shows whether it is holding or "off". It lists the agents (people, AI, programs, rules) with their runs and cost, tracks work items through their states, keeps a raw event log, fits a model, and asks a human to approve outward actions (git push, Jira changes, PR merges).

It is built first for the engineer or operator who builds and runs these agent pipelines and knows control theory. The Guide suggests it also wants newcomers to understand their system "both ways". How sure I am: fairly sure of the purpose (about 75%), less sure of the audience. The vocabulary (setpoint, u/y/e, Kp, P(s), Harris index, nack, lease, fence) says engineers, but the Guide and the "How to read it" legend reach for a wider audience.

As a PM I came with three questions: **what does this system do, is it healthy, and what should I expect next?** I could answer the first only roughly. I could not answer the second with confidence. I could answer the third only in one place (the roadmap's Items > Graph).

## Findings, worst first

### Blockers

1. **The health signal is mostly ergostat checking itself, not the system.** Pages: `/` on every demo. In every demo the top "Needs attention" items and the red "N loops off" count are led by `requests-handled` (unanswered-requests 36/96/164) and `model-fits` (model-error). Both belong to the "modelling" module, which is ergostat's own bookkeeping. On :8797 (big), all 24 real loops are holding, yet the header says "1 loop off" in red and Needs attention lists 26 entries. They are `request/... modelling holds no-unit on stock.api-q0` and similar, each with a Deny button. On Items, the only items shown for big are 188 "modelling requests". *Why it matters:* the first thing I see says "unhealthy" when the system I care about is fine, so I either learn to ignore red or I raise a false alarm. *Screenshots:* `pm-big-home.png`, `pm-big-items.png`, `pm-big-phone-dark.png`, `pm-tf-home.png`, `pm-job-home.png`.

2. **The headline "loops off" count jumps around from second to second.** Pages: header on all pages. On ticket-factory, loading the tabs one after another gave 3, 5, 4, 6, 4 loops off within about a minute. On the-job the header said 7 loops off, and 4 s later the Loops page showed 2 off and the header said 2. Loops flip between off and holding every second (Loops "back in 1s"), and the count shows the raw state. Nothing tells me whether it is getting better or worse. *Why:* a status I can't quote in a meeting is no status. I need a smoothed or windowed figure ("off 12% of the last hour, improving"). *Screenshots:* `pm-tf-loops.png`, `pm-tf-agents.png`, `pm-tf-model.png`, `pm-job-home.png`, `pm-job-loops-4s.png`.

3. **There is no "what to expect" answer, and the forecast that exists looks 2 minutes ahead.** Page: `/` on :8796, loop panel users-growing (via Evidence). Users climb steadily toward the 180 goal (80, then 115, then 176), and I want "you'll reach 180 in about N minutes". After a long "being worked out…" the panel says "users-growing: off at +1m59s with p≈1; 1m59s off expected over the 1m59s (100 runs)". It also says "How it is doing: Not worked out: it has no one process." *Why:* forecasting is the main reason a PM would open a dynamics tool, and here it is short-range, written in jargon and slow. The one good forecast I found ("last of 2 epic done in about 23s (p90 27s)" on the roadmap's Items > Graph) is a small grey line. *Screenshots:* `pm-sf-users-evidence.png`, `pm-sf-users-ahead.png`, `pm-road-graph.png`.

### Major

4. **A goal that is being met on schedule is shown as a red failure.** Page `/` on :8796: "loop users-growing ... off 100% of the time", red in Needs attention and Suggestions, while the chart shows users rising steadily to the target (173 of 180). Every ≤ 0 queue loop in ticket-factory works the same way: one item waiting makes it "off". *Why:* the tool can't tell "progressing toward a target" from "broken", so red loses its meaning. *Screenshots:* `pm-sf-users-growing.png`, `pm-sf-evidence-dark.png`, `pm-tf-loops.png`.

5. **Red loop names in Needs attention look like links but do nothing.** Page `/` (ticket-factory, software-factory). Clicking "loop requests-handled" or "loop users-growing" left the page unchanged: no panel, no highlight, no navigation. Only the small "Evidence" link under Suggestions opens the loop panel. Rows on the Loops page don't open anything either. *Why:* the natural next step after "what's wrong?" is "show me", and it fails silently. *Screenshots:* `pm-tf-click-loop-attention.png`, `pm-sf-users-growing.png`, `pm-tf-loop-detail.png`.

6. **The top-level diagram gives no health at a glance.** Pages `/` on all demos. The top-level modules (factory, oversight, modelling; big's api, billing, build, data, support, web) are plain black boxes reading "N feedback loops inside". Nothing marks which module holds the problem: no colour, no count off, no trend. On big, the boxes show no numbers at all. *Why:* the diagram is the home page, and it doesn't answer "where should I look?". *Screenshots:* `pm-big-home.png`, `pm-tf-home.png`, `pm-road-click-stock.png`.

7. **Anyone viewing the page can approve or deny real outward actions, with no confirmation.** Pages `/` sidebar on ticket-factory and big. Approve/Deny buttons for `git push --force-with-lease`, `pr-merge`, `jira-transition` sit in the sidebar of a page a colleague can send as a link. The page doesn't say who I am, gives no undo, and shows no "are you sure". On big, the requests show Deny only, with no Approve. (I did not press these.) *Why:* a PM browsing a shared link could merge a PR by accident. And the sidebar text "`ergostat actions` lists them" points me to a command-line tool from a web page. *Screenshots:* `pm-tf-home.png`, `pm-big-home.png`.

8. **The Process view on the large demo stays blank.** Page `/` > Process on :8797. After 3 s and again after 12 s the canvas was empty: no loading indicator, no "nothing to show" message. *Why:* it looks broken, and big is the demo built to stress the layout. *Screenshots:* `pm-big-process.png`, `pm-big-process-12s.png`.

9. **Pages render blank while they load, with no indicator.** Pages `/` > Loops and Items on :8792. After 1.5 s only the heading "Loops" or "Items" showed on a white page. Content arrived within about 4–5 s. *Why:* a blank page reads as "no loops" or "no data" to a first-time viewer. *Screenshot:* `pm-job-loops.png`.

10. **Jargon everywhere, with no plain-language layer.** All pages. Some examples: "u → y, process … an integrator, from the model … its dead time: a step of u, or a step test" (Model). "Harris index: a ceiling or a floor is not held at zero error" (loop panel). "nack … (not counted)", "fence", "lease 26" (item page). "Q_factory" boxes (Blocks). "stock epics-underway changed 1, the known flows explain −14: 15 unexplained" (sidebar). "R² 0.08, scaled error 0.98" (Check). "SPEC §12e" (Items > modelling). *Why:* I can't tell which items are business-relevant and which are model plumbing, so I can't brief anyone from this. *Screenshots:* `pm-tf-model.png`, `pm-road-evidence.png`, `pm-tf-item-detail.png`, `pm-tf-blocks.png`, `pm-road-click-stock.png`, `pm-road-graph.png`.

11. **Several screens contradict themselves.** (a) Agents: the summary strip reads "2 person → 4 ai → 13 program → 16 rule", but the group headings read "0 person", "1 ai", "4 program" over 2, 4 and 13 rows. They are level numbers that look like counts. (b) The agent panel for "work" says "Runs: not run by ergostat" and directly below "28 runs, 0 failed". (c) The users-growing panel says the sensor is "unfilled" yet "read 1s ago: 125". It also says the controller made "no decision yet" while the u chart shows about ten openings by product-manager. (d) The roadmap loop says "Its valve did not open in the 7m recorded" next to "Last decision 31s ago: act: developer". (e) The module card for product says 18 feedback loops inside, but its panel says "16 feedback loops inside and 13 through it". *Why:* every contradiction makes me distrust the numbers I'd want to quote. *Screenshots:* `pm-tf-agents.png`, `pm-tf-agent-detail.png`, `pm-sf-users-evidence.png`, `pm-road-evidence.png`, `pm-sf-click-users.png`.

12. **The same alert is worded differently depending on the view.** The sidebar on Dynamics says "desired unanswered-requests = 0: excess 36"; on Blocks it says "setpoint ≤ 0 (off by 36)". Suggestions are titled "loop X" in one view and "controller X" in the other. In Blocks the suggestion text changes too, and becomes more useful: "falling behind: its valve moved 4.89/h out while 228/h came in". The Agents page calls them "valve too small" where the diagram says "flow too small". *Why:* I can't tell whether these are the same issue, and the better explanation is hidden in the view I'm least likely to open. *Screenshots:* `pm-tf-home.png`, `pm-tf-blocks.png`, `pm-sf-blocks-dark.png`, `pm-tf-agents.png`.

13. **Suggestions hold their own verdict back for 10 minutes and repeat themselves.** Sidebar on all demos: "loop requests-handled was off 92% of the time; why (a flow too small to close the gap, or acting too seldom) is said after 10m of record (1m51s so far)". Each one names the loop twice and offers two candidate causes without picking one. *Why:* a suggestion that says "I'll tell you later" adds noise to the place I look for action. *Screenshot:* `pm-tf-home.png`.

### Minor

14. **"Open" on a module doesn't frame the result.** Page `/` on ticket-factory: after Open on factory, the drawing begins below a large empty area and runs off the right edge ("More beyond the edge"). Fit then shrinks it until the labels are unreadable at 1440 px. *Screenshots:* `pm-tf-diagram-factory-open.png`, `pm-tf-diagram-factory-fit.png`.

15. **Phone width only half works.** At 390 px the root URL opens Loops, not the Diagram. The tab bar cuts "Model" off with no hint that it scrolls. The Loops table shows only loop/status/holds, with "unanswered-reque…" clipped, so the numbers that matter (now, setpoint, time off) are off-screen. On the Diagram the right-hand module (oversight/factory) is cut off. The Guide's diagrams shrink to illegible thumbnails. *Screenshots:* `pm-tf-home-phone.png`, `pm-tf-loops-phone.png`, `pm-tf-diagram-phone.png`, `pm-sf-diagram-phone.png`, `pm-tf-guide-phone.png`.

16. **The Items table overflows at desktop width.** On ticket-factory Items, the "in state" column is cut ("in s"), along with the columns to its right. There is no visible horizontal scroll cue. *Screenshot:* `pm-tf-items.png`.

17. **The item state chart is grey-on-grey.** The stacked area charts on Items (ticket-factory, roadmap) draw up to 16 states in near-identical greys, so I can't tell which band is "done" and which is "leased". In dark mode the bands merge further. *Screenshots:* `pm-tf-items.png`, `pm-road-items.png`, `pm-tf-items-phone-dark.png`.

18. **The item page draws every state as one straight line.** The state strip on ticket/SCRUM-2 runs "… merged → done → stopped → dead", as if stopped and dead come after done. The lease table is 26 rows of "ack/nack … (not counted)" before the human-readable part (PR link, gated actions). *Screenshot:* `pm-tf-item-detail.png`.

19. **Internal event names stand in for status.** The Items "latest" column shows "ergostat.item.joined", "ergostat.lease.ended" and similar, where I'd expect "shipped" or "waiting for review". *Screenshots:* `pm-road-items.png`, `pm-tf-items.png`.

20. **Cost columns are all "–".** On Agents (ticket-factory), cost and tokens are "–" for every agent, and items show "AI cost $0.0000". As a PM, cost is one of my first questions. If the demo uses stand-ins, the page should say so ("no AI used in this demo") rather than look empty. *Screenshots:* `pm-tf-agents.png`, `pm-tf-item-detail.png`.

21. **The Check page is a developer lint list.** Check on ticket-factory shows "17 warnings" such as "oversight.yaml:173: block reporter…" and "its equation fits its record worse than holding it at its mean". It is useful to the builder, but sits at the same level as Loops with no framing of who it is for. *Screenshot:* `pm-tf-check.png`.

22. **The window says "Last 1h" while the data covers a few minutes.** The header says Last 1h. Loops says "over the 2m recorded"; Suggestions say "(1m51s so far)". The mismatch makes percentages like "off 93% of the time" look more serious than 2 minutes of data supports. *Screenshots:* `pm-tf-loops.png`, `pm-road-timepicker.png`.

### Polish

23. **The Guide opens with an unexplained slide.** Slide 1, "You control the knob. You want the stock.", shows "ad-spend" floating beside a "customers" box with no arrow. The later slides are clear and well paced, especially 3–7. Slides 8–12 switch to control notation (P(s), Kp, y_m, H) with no plain-language caption. *Screenshots:* `pm-tf-guide.png`, `pm-tf-guide-6.png`, `pm-tf-guide-9.png`.

24. **Placeholder text shows in panels.** The module panel shows a lone "…" line above the description, and the loop panel shows "When it drives the behaviour …". *Screenshots:* `pm-sf-click-users.png`, `pm-big-api-open.png`.

25. **Small input boxes cut off their placeholders.** "how ma" and "why (to de" are truncated. *Screenshot:* `pm-tf-home.png`.

26. **"modelling" is always the first module, at top left.** On every demo, ergostat's own module takes the most prominent spot in the diagram. *Screenshots:* `pm-big-home.png`, `pm-img-home.png`.

27. **Wording slips.** "last of 2 epic done", "1 re-ping(s)", "Not held Attempts 0 of 3." with no separator. *Screenshots:* `pm-road-graph.png`, `pm-tf-item-detail.png`.

## What worked well

- **Roadmap Items > Graph** (`pm-road-graph.png`). It shows the critical path in red, items that are waiting, who is working on what, and a finish estimate with p90. This is the most PM-friendly screen in the product.
- **Opening a single subsystem with Into**, e.g. big > api (`pm-big-api-into.png`), gives a clean, readable stock-and-flow picture with live rates.
- **The loop panel's y/u/e charts** (`pm-sf-users-evidence.png`) show history against target well, once the panel is found.
- **Dark mode** is consistent and legible on every page I checked (`pm-tf-home-dark.png`, `pm-sf-evidence-dark.png`, `pm-sf-blocks-dark.png`).
