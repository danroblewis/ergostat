# ergostat: a blind newcomer review

Reviewer: a software engineer who had never heard of ergostat or system dynamics, opening a link a colleague sent. I used only the running demos (:8791 ticket-factory, :8792 the-job, :8793 image-squeeze, :8794 roadmap, :8796 software-factory, :8797 big), at desktop (1440x900), phone (390x844) and in dark mode. Screenshots are in <workdir>/design/shots/ with the prefix `newcomer-blind-`.

## What I think this is (written before judging)

ergostat looks like a **live control room for automated work pipelines**. Work items (Jira-like tickets, PRs, image batches, feature requests) move through states. "Agents" move them: people, AI agents, plain programs and threshold "rules". ergostat draws the system in two ways. One is a system-dynamics picture: stocks (queues, such as "located 2 tickets"), flows (rates, such as "work 35 tickets/h") and feedback loops (B/R). The other is a control-engineering block diagram: setpoint, controller, process, sensor. Each "loop" has a setpoint (often "queue ≤ 0"), and the app reports whether it is "holding" or "off". It also fits equations to the recorded data. It gates side effects (git push, jira transition, PR comments) behind human approval in a side panel, and it suggests changes ("consider gate: auto for jira-transition").

**Who it is for:** someone running AI-agent or automation "factories" (an engineering lead or platform or operations person) who wants to see the whole pipeline as one controlled system, approve risky outward actions and tune it. It assumes comfort with control theory (Kp, G(s), dead time, integrator, R², lag-one autocorrelation).

**How sure I am:** fairly sure about "operations dashboard for agent pipelines, framed as stocks/flows and control loops", about 70%. Much less sure what I, as a viewer, am *supposed to do* here, apart from Approve or Deny. Nothing on the first screen tells me the product's purpose. I had to infer it from the ticket titles and the Guide.

## Findings, worst first

### 1. [blocker] No orientation: the first screen never says what ergostat is or what I should do
- **Page:** `/diagram` (home of every demo)
- **Saw:** Home is a canvas of boxes ("modelling", "factory", "oversight") with "Open"/"Into" links and arrows labelled "+". Beside it is a dense red/orange "Needs attention 15" panel of lines like "loop requests-handled unanswered-requests is 37, desired unanswered-requests = 0: excess 37". There is no headline, no one-line description, no "start here" and no pointer to the Guide.
- **Why:** As a newcomer I could not tell, for minutes, whether this is a monitoring tool, a modelling tool or a workflow engine. The Guide tab, which is the only explanation, is the last tab and is never offered.
- **Suggest:** On first visit, add a one-sentence purpose line and a "New here? Take the 13-step guide" link above the diagram. Or open the Guide on first visit.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-home.png, <workdir>/design/shots/newcomer-blind-job-diagram.png

### 2. [major] Every demo is permanently "on fire" from ergostat's own housekeeping loops
- **Page:** `/diagram`, `/loops` (all six demos)
- **Saw:** In every demo the top of "Needs attention" is "loop requests-handled … excess 37/96/164" and "loop model-fits … excess". Both stay off 93–100% of the time. The header always reads "N loops off" in red. Every home diagram has a "modelling" system with 11 loops, unrelated to the demo's subject.
- **Why:** The first thing a newcomer learns is that the tool's own machinery is broken in every example. It drowns out the demo's real signals (for example, in ticket-factory the meaningful "located-worked" is third). I could not tell what "healthy" looks like.
- **Suggest:** Separate ergostat's own modelling loops from the user's system: collapse them by default, or show them under a "ergostat itself" heading. Demos should start in a state where the self-loops hold.
- **Shot:** <workdir>/design/shots/newcomer-blind-sf-diagram.png, <workdir>/design/shots/newcomer-blind-rm-diagram.png, <workdir>/design/shots/newcomer-blind-tf-loops.png

### 3. [major] Guide's final "Your system" frame draws the diagrams as solid black boxes in light mode, after a blank delay
- **Page:** `/guide?frame=12` (step 13/13)
- **Saw:** Stepping with the arrow, the last frame first shows only "Your system, both ways." on a blank stage (screenshot after 1.8s). When it does render, the system-dynamics thumbnail has black-filled boxes with near-invisible dark text in light mode. Dark mode looks right.
- **Why:** This is the payoff slide where the tutorial hands over to my real system, and it looks broken.
- **Suggest:** Use the light-theme fill for the thumbnail and show a loading state.
- **Shot:** <workdir>/design/shots/newcomer-blind-guide-13.png (blank), <workdir>/design/shots/newcomer-blind-guide-13-wait.png (black boxes), compare <workdir>/design/shots/newcomer-blind-sf-dark-guide.png

### 4. [major] "Needs attention" approval cards are unreadable machine text and refer to a CLI
- **Page:** `/diagram` side panel
- **Saw:** "person/approve@575 approve is asked: Outward acts wait for your approval. `ergostat actions` lists them (and the p..., waiting 1m06s; 2 asked this week, 0 approved, 0 denied" with a "how ma[ny]" box and "Done". Action cards show raw shell commands ("python3 bin/jira.py transition SCRUM-2 Done"). On :8797 and :8792 "request/…" cards have **only Deny**, with no Approve, and 24 near-identical cards ("nothing says its unit (no stock it joins has one, and it counts no one kind)") fill the panel. The same request is said to be held by the "decision tier" at one moment and the "rule tier" at the next.
- **Why:** This is the one place I am asked to act, and I can't tell what Approve would do, what "how many" means, why there is no Approve on some cards, or why I'm sent to a CLI from a web UI.
- **Suggest:** Lead each card with a plain verb sentence ("Move SCRUM-2 to Done in Jira"), put the command behind a disclosure, label the number field, explain Deny-only cards, and group duplicates ("24 stocks have no unit").
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-home.png, <workdir>/design/shots/newcomer-blind-big-diagram.png, <workdir>/design/shots/newcomer-blind-job-diagram.png

### 5. [major] The loop detail contradicts itself
- **Page:** `/diagram` → Evidence on loop requests-handled (:8792)
- **Saw:** "u moved by fixer … never opened. Its valve did not open in the 10m recorded". Below that it says "Moves requests-answered 4.76/h", and "Last decision 10m ago: act: fixer". The Agents page says fixer runs every 1m and has run 7–8 times.
- **Why:** When the numbers disagree, I stop trusting the whole dashboard.
- **Suggest:** Reconcile "never opened" with runs/moves, or explain the difference between a run and a valve opening.
- **Shot:** <workdir>/design/shots/newcomer-blind-job-evidence.png, <workdir>/design/shots/newcomer-blind-big-agents.png

### 6. [major] Phone width: the main navigation and tables are cut off with no affordance
- **Page:** `/diagram`, `/loops`, `/agents`, `/guide` at 390px
- **Saw:** The tab bar ends at "Mode…" (Model, Check and Guide are off-screen, with no scroll hint). The diagram is not fitted (the factory box is clipped at the right edge). The Loops table shows only loop/status/holds, and "now" is cut mid-number ("0."). The Agents table cuts runs and last-run columns.
- **Why:** I first opened the link on my phone. The Guide, the one explainer, can't be found there, and the key numbers are hidden.
- **Suggest:** Use a hamburger menu or a wrapped tab bar, fit the diagram on load, and stack table rows into cards on narrow screens.
- **Shot:** <workdir>/design/shots/newcomer-blind-sf-phone-diagram.png, <workdir>/design/shots/newcomer-blind-sf-phone-loops.png, <workdir>/design/shots/newcomer-blind-sf-phone-agents.png, <workdir>/design/shots/newcomer-blind-sf-phone-guide.png

### 7. [major] Items "Timeline" shows the same thing as "Graph"
- **Page:** `/items` → Timeline (:8791)
- **Saw:** After clicking Timeline and waiting 6s, the content is the same stacked area charts as Graph. Only the toolbar changes (By item/Lanes instead of By parent/By kind).
- **Why:** I wanted to see one ticket's path over time. The button suggests a timeline view that doesn't appear.
- **Suggest:** Render a per-item swim-lane/Gantt view, or remove the mode.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-items-graph.png, <workdir>/design/shots/newcomer-blind-tf-items-timeline2.png

### 8. [major] Diagrams open off-centre or at unreadable sizes
- **Page:** `/diagram` → factory "Open"; factory "Into"; :8797 api "Open"
- **Saw:** "Open" expands in place but leaves the view scrolled so the content runs off the right/bottom edge ("More beyond the edge"), with a large empty area at the top. "Into factory" draws everything at about 7px text. On :8797, "Open" lands mid-way through the modelling system, with the api box cut off at the top.
- **Why:** Every drill-down needs a manual Fit or zoom before it can be read, and I first thought the content was missing.
- **Suggest:** Auto-fit (or scroll to the opened system) after Open/Into, with a minimum text size.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-factory-open.png, <workdir>/design/shots/newcomer-blind-tf-factory-into.png, <workdir>/design/shots/newcomer-blind-big-api-open.png

### 9. [major] Process view on the big demo is a blank canvas
- **Page:** `/diagram?view=process` (:8797)
- **Saw:** An empty white canvas with the toolbar (States/Events, Counts/Times, a "paths ≥ 0%" slider) and no message.
- **Why:** I can't tell if it's loading, broken or empty by design.
- **Suggest:** Add an empty state ("No item kinds with recorded paths in this window") or default to States.
- **Shot:** <workdir>/design/shots/newcomer-blind-big-process.png

### 10. [minor] Jargon and configuration-speak everywhere, with no glossary
- **Page:** `/model`, `/check`, `/items`, flow detail panel
- **Saw:** "an integrator, from the model / its dead time: a step of u, or a step test"; "lag-one autocorrelation 0.96, so its 279 points hold about 6.4 independent ones"; "(SPEC §12e)"; "No relations among these kinds: a kind declares them under relations: (blocked_by: ticket)"; "ergostat.yaml:94 (use modelling: modelling)… give them under with:"; Check's footnote says "one line a newcomer can read without the YAML", which is itself unreadable grey 11px text repeated about 12 times.
- **Why:** As a non-specialist, half of each sentence is opaque. References to SPEC sections and YAML lines assume I have the repo.
- **Suggest:** Plain-language first line, technical detail on expand, and a hover glossary for stock/flow/valve/setpoint/dead time.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-check.png, <workdir>/design/shots/newcomer-blind-big-model.png, <workdir>/design/shots/newcomer-blind-tf-items-graph.png, <workdir>/design/shots/newcomer-blind-tf-making-click-flow.png

### 11. [minor] Block diagram at the top level says almost nothing
- **Page:** `/diagram?view=blocks`
- **Saw:** Boxes labelled only "Q factory", "Q modelling", "Q oversight" (and seven stacked Q boxes on :8797). In ticket-factory, one wire leaves factory's right edge and wraps round to oversight's left. Nothing explains what "Q" means.
- **Why:** The Guide taught me C, P, H, G, but never Q (step 12 shows Q without naming it). The top level of the "control" view gives me nothing to read.
- **Suggest:** Name what Q is (a closed subsystem?) on the box or in a legend, and show the signals carried between subsystems.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-blocks.png, <workdir>/design/shots/newcomer-blind-big-blocks.png

### 12. [minor] Overlapping loop markers and labels in drill-down diagrams
- **Page:** `/diagram?view=dynamics&system=making` (:8791), `system=api` (:8797)
- **Saw:** In "making", the B35 and B17 loop markers overlap, and "worked-opened" is printed across B17. On api, B10 sits on top of the "excess api-q2" label ("exc B10 i-q2"). Connector curves pass through text.
- **Why:** Loop names are what I'd click to understand behaviour, and here they are illegible.
- **Suggest:** Avoid collisions for loop markers and labels.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-making.png, <workdir>/design/shots/newcomer-blind-big-api-into.png

### 13. [minor] Same fact, different words, depending on the view
- **Page:** `/diagram` Dynamics vs Blocks side panel
- **Saw:** Dynamics: "unanswered-requests is 36, desired unanswered-requests = 0: excess 36". Blocks: "unanswered-requests is 36, setpoint ≤ 0 (off by 36)". Agents says "a valve too small", Diagram says "a flow too small", for the same suggestion.
- **Why:** I wondered if they were different conditions.
- **Suggest:** Pick one vocabulary for the panel, or show both terms together once ("setpoint (desired level)").
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-home.png, <workdir>/design/shots/newcomer-blind-tf-blocks.png, <workdir>/design/shots/newcomer-blind-tf-agents.png

### 14. [minor] Header "N loops off" count jumps every few seconds
- **Page:** all pages
- **Saw:** Across consecutive page loads on :8791 the red header read 3, 4, 6, 4, 5, 2 loops off. The Loops page shows most loops flicker between holding and off within 1s.
- **Why:** An alarm that changes every few seconds teaches me to ignore it.
- **Suggest:** Debounce (count loops off for more than X seconds or out of bound by more than Y), or show a trend instead.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-loops.png, <workdir>/design/shots/newcomer-blind-tf-item.png

### 15. [minor] Stacked state charts are 16 shades of grey
- **Page:** `/items` (Graph/List)
- **Saw:** Ticket states (new … dead, 16 of them) are stacked in near-identical greys. The legend swatches can't be matched to bands.
- **Why:** I couldn't tell where tickets pile up, which seems to be the point of the chart.
- **Suggest:** Highlight only non-zero or active states, use a sequential palette by pipeline position, or label the bands directly.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-items-graph.png

### 16. [minor] Item page: lease table noise and inconsistent time formats
- **Page:** `/item/ticket/SCRUM-2`
- **Saw:** Every row's "why" ends in "(not counted)". The "taken" column uses "11/22/2026, 03:24:02", while Record uses "03:24:28" and comments use ISO UTC "2026-11-22T11:24:27Z". The state strip lists stopped/dead after done as if they followed it.
- **Why:** "(not counted)" on every row carries no information, and the mixed time zones and formats make it hard to correlate.
- **Suggest:** Drop the repeated suffix (or explain it once), use one time format, and show terminal states as alternatives rather than next steps.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-item.png

### 17. [polish] Odd estimates shown without comment
- **Page:** flow detail panel (`/diagram?…system=making`, click "work")
- **Saw:** work-time declared 60s; calibrated "40m ± 2d".
- **Why:** An uncertainty of ±2 days on a 40-minute estimate reads like a bug rather than "unknown".
- **Suggest:** Say "not enough data yet" instead of printing the interval.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-making-click-flow.png

### 18. [polish] Unknown paths give a bare "not found"
- **Page:** `/nonsense`, `/item/ticket/does-not-exist`
- **Saw:** Unknown route returns plain text "not found" with no navigation. An unknown item shows "Nothing is recorded about this id." (fine), but the page never settles (it keeps polling).
- **Suggest:** Use a styled 404 with the nav bar.
- **Shot:** <workdir>/design/shots/newcomer-blind-job-missing-item.png

### 19. [polish] Console error on diagram views
- **Page:** `/diagram` (Blocks/Process, :8791 and :8796 phone)
- **Saw:** `xOffset value (395) in ShapeConnectionPin constructor greater than shape width (395)` in the console.
- **Suggest:** An off-by-one in a layout pin. Fix it before it hides real errors.
- **Shot:** <workdir>/design/shots/newcomer-blind-tf-process.png

## What worked
- The **Guide** (steps 1–12) is clear and well drawn, with stock/flow and block diagrams side by side. It's the best part of the app and should be the front door.
- **Clicking a stock or flow** opens a useful side panel: description, now, inflow/outflow, the equation, and "Show them on the Items page".
- **Dark mode** is consistent across diagram, items, loops and model.
- The **ticket list** on software-factory (type/op/title/priority) is the one view where I immediately understood what the system was doing.
