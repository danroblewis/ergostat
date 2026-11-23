# ergostat: an information designer's blind review

Reviewer persona: information designer (Tufte, Bertin, Few). I judged hierarchy, density, labelling, colour and how the diagrams carry meaning. I used only the running demos (:8791 ticket-factory, :8792 the-job, :8793 image-squeeze, :8796 software-factory, :8797 big), at 1440x900, at phone width 390x844 and in dark mode. All screenshots are in `<workdir>/design/shots/`, prefixed `infod-`.

## What I think this is

ergostat is an operations console for automated work systems, such as a "ticket factory" that takes Jira tickets through AI agents and programs to merged pull requests, or a set of request queues. It models a running system twice. The first model uses system dynamics: stocks, flows, connectors with signs, and R/B loops. The second uses control engineering: summing junctions, controllers, plants P(s), sensors H, and a setpoint r with error e for each loop. Live data comes from an event log ("Record"). It reports which feedback loops are "off" (outside their setpoint), lists the work items moving through states, shows the agents (person, AI, program, rule) acting as valves and controllers, and asks the owner to approve outward actions. The audience is a technical operator or engineer who runs AI agents and pipelines and knows some system dynamics and control theory, or is willing to learn it from the Guide. I am fairly sure of this (about 75%). The vocabulary (valve, Harris index, dead time, integrator) points strongly at an engineering reader.

## What works (keep it)

- The loop detail panel (Loops → click a row) is the best graphic in the product. It shows three small multiples, y, u and e = r − y, on one shared time axis, with red bands where the loop is off and the reference drawn on the y chart (`infod-tf-loop-click.png`). It is dense, aligned and honest.
- Guide step 2 puts a stock-and-flow diagram next to the equivalent block diagram (`infod-guide-3.png`). It is an excellent explanation of two notations.
- Hovering a diagram element dims everything that is not connected to it (`infod-big-api-hover.png`). Selecting a loop marker highlights the whole loop path and lists its links with their polarity (`infod-big-open2.png`).
- The leaf-level stock-and-flow drawing uses classic SD notation correctly: clouds, double-line pipes, valves, signed connectors and B markers (`infod-big-api-into.png`).

## Findings, worst first

### 1. [blocker] The Process view of the large demo is a blank canvas
- Page: `:8797 /diagram?view=process`
- I saw a toolbar and an empty white canvas, in both "Events" and "States" mode and after waiting 8 seconds. The SVG has no children, and there is no message.
- Why it matters: this is the demo built to stress layout, and the view shows nothing and gives no reason. The reader cannot tell "no data" from "broken" from "still loading".
- Suggestion: if there is nothing to map, say so ("no item kinds with states in this window") and offer the nearest view that does have data.
- Screenshots: `infod-big-process.png`, `infod-big-process-states.png`

### 2. [major] The landing diagram carries almost no data
- Page: `/diagram` on :8797, :8792, :8791 and :8796
- I saw large empty module boxes labelled only "N feedback loops inside" with Open/Into buttons. The big demo shows seven boxes and the-job shows two, with nothing else, while the sidebar lists 26 to 35 things that need attention. Nothing on the boxes says which module holds the trouble, and one or two clicks are needed before any stock or flow appears.
- Why it matters: the first view should carry the highest data density and the status overview. Here the ink-to-information ratio is lowest exactly where the reader orients. A module box is a natural place for a small multiple: the module's loops as a row of status ticks, its key stock with a sparkline, or the count of loops that are off.
- Suggestion: show inside each module how many of its loops are off, its main stocks and their trend, and colour or mark modules that hold an off loop.
- Screenshots: `infod-big-diagram.png`, `infod-job-diagram.png`, `infod-tf-home.png`

### 3. [major] The diagrams do not show which loops are off
- Page: `/diagram` (Into a module), e.g. `:8797` web and api
- I saw that while the sidebar said "loop web-q0-low … web-q0 is 7, desired = 5: excess 2", the web module drew B28 and the web-q0 stock exactly like the healthy loops. No loop marker, stock or valve is coloured or annotated by status.
- Why it matters: the product's central question is "which loop is failing and where". The diagram and the alert list are two disconnected displays, so the reader must translate names between them by eye. Status is the one variable that deserves colour here, and the diagrams leave it unused.
- Suggestion: draw off loops' markers and their stock in the alert colour, mark stocks that are beyond their desired level, and link each sidebar alert to its place on the diagram.
- Screenshots: `infod-big-web-into.png`, `infod-big-api-into.png`

### 4. [major] One number is named and signed three different ways
- Page: `/diagram` sidebar (Dynamics), `/diagram?view=blocks` sidebar, `/loops`
- For the same loop at the same moment I saw:
  - Dynamics sidebar: "desired unanswered-requests = 0: excess 37". Other loops say "gap 147".
  - Blocks sidebar: "setpoint ≤ 0 (off by 36)".
  - Loops table: "error −36", where e = r − y comes out negative when the level is above a ceiling.
  - Dynamics also writes "desired … = 0" where the setpoint is really a bound, "≤ 0".
- Why it matters: when one quantity changes its name, sign and relation symbol between views, the reader has to stop and reconcile them every time. The negative error for "too much" goes against the plain reading of "excess".
- Suggestion: pick one term and one sign convention, state the bound as a bound ("≤ 0") everywhere, and keep the engineering e = r − y for the control panel only.
- Screenshots: `infod-tf-home.png`, `infod-tf-blocks.png`, `infod-tf-loops.png`

### 5. [major] "Needs attention" mixes kinds, its count disagrees with the header, and it repeats itself
- Page: `/diagram` sidebar, every demo
- The header says "3 loops off" while the sidebar says "Needs attention 16". The sidebar mixes loops that are off, person tasks, approval requests and modelling requests. On :8797, 24 entries are each a 50-word paragraph that differs only in the stock name ("modelling holds no-unit on stock.api-q0 … stock.api-q1 …"), each with a "Deny" button and a truncated "why (to de" field. Backticks show literally (`` `ergostat actions` ``), and input placeholders are cut off ("how ma").
- Why it matters: repeated prose is the opposite of a table. A reader cannot scan 24 paragraphs for the one that differs, and the two counts in the header and sidebar look like a contradiction.
- Suggestion: group the list by kind under separate headings. Fold identical requests into one row such as "no-unit: 24 stocks (api-q0 … web-q3)" with one action, and make the header count match a sidebar group.
- Screenshots: `infod-big-diagram.png`, `infod-tf-home.png`, `infod-job-diagram.png`

### 6. [major] The item state chart uses 17 near-identical greys
- Page: `/items` (List, Graph, Timeline)
- I saw a stacked area chart of ticket states. Its legend has 17 states (new, leased, picked … stopped, dead), each a grey square only slightly different from the next, and most of them say "0". In dark mode the ramp is inverted, so the dominant "done" band becomes the brightest shape and the active states sink into the background.
- Why it matters: Bertin's rule is that value (lightness) supports only a handful of distinguishable steps, and 17 cannot be told apart. The reader cannot match a band to a state, so the chart shows only "total grew". Zero-count legend entries spend space on nothing.
- Suggestion: group states into 3 to 4 phases (waiting, in work, in review/CI, finished) with distinct hues, and label bands directly at their right edge. Hide zero states or show them faintly. Keep the ordering in dark mode.
- Screenshots: `infod-tf-items.png`, `infod-dark-tf-items.png`, `infod-phone-tf-items.png`

### 7. [major] The Agents page shows numbers that look like counts but are not
- Page: `/agents`
- The summary strip reads "2 person → 4 ai → 0 narrow-ai → 0 decision → 13 program → 16 rule → 0 retired". The group headings below read "0 person the most general agent", "1 ai …" and "4 program …". The heading numbers seem to be ranks, yet they sit in the same position and style as the counts. The arrows in the strip suggest a flow from one kind to the next. Most of the cost and tokens columns are dashes.
- Why it matters: the same typographic slot carries two meanings, and the reader will read "0 person" as "zero people" right above two people.
- Suggestion: drop the rank numbers from the headings, or write them as "tier 0". Explain the arrows or remove them. Hide columns that are entirely empty.
- Screenshot: `infod-tf-agents.png`

### 8. [major] Connector bundles between modules are unreadable
- Page: `/diagram` home, factory → Open, image-squeeze home
- I saw 7 to 15 connectors converge on one point at the receiving module edge, with their +/− signs stacked on top of each other. When a module is opened, wires run as parallel bundles around boxes. In image-squeeze, about 20 curves cross between lab, rollout and benchmark.
- Why it matters: a sign that cannot be assigned to its wire carries no information, and in SD the polarity is the meaning. The bundles are chartjunk-level clutter at the level the reader sees first.
- Suggestion: give each port its own entry point on the module edge and put the sign at the arrowhead of its own wire, or merge parallel wires between two modules into one labelled bundle ("7 links, 6+ 1−") that expands on hover.
- Screenshots: `infod-tf-home.png`, `infod-tf-factory-open-fit.png`, `infod-is-diagram.png`, `infod-sf-product-into.png`

### 9. [minor] Labels collide in the stock-and-flow diagrams
- Page: `:8797 /diagram` Into api and web
- The B10/B30 loop marker is drawn on top of the "excess api-q2" label ("exc(B10)i-q2"). The loop names "api-q1-low" and "web-q1-low" are printed across the flow pipe. "from api-arrivals" overlaps the source cloud. The pipe from api-q2 to api-q3 makes a long detour around the canvas.
- Why it matters: overprinted labels are the first thing a careful reader notices, and they cost trust in the rest of the drawing.
- Suggestion: treat labels as obstacles during placement, and keep loop markers in the open interior of the loop.
- Screenshots: `infod-big-api-into.png`, `infod-big-web-into.png`, `infod-dark-big-api.png`

### 10. [minor] The Blocks view is sparse at the top and very small inside
- Page: `/diagram?view=blocks`
- At the top level I saw three or seven identical boxes labelled "Q_factory", "Q_modelling" and so on, connected by a single unlabelled wire, with "Q" never explained (`infod-tf-blocks.png`, `infod-big-blocks.png`). On software-factory, "1×3", "3×1" and a bus slash marked "3" appear (`infod-sf-blocks.png`). Expanded, subscripts are about 7 px, and labels such as r_nothing-awaits-approval and u_changes-passed overlap lines (`infod-tf-model-scope.png`, `infod-dark-big-api-blocks.png`).
- Why it matters: the top level shows almost nothing, while the inside is too small to read at its natural zoom. The subscript names are the long ids (r_nothing-awaits-approval), which makes the subscripts longer than the symbols.
- Suggestion: show live values and a status mark on the top-level boxes, and add a one-line key for Q, P, C and H. Use short symbols with a legend, or full words, rather than 30-character subscripts.

### 11. [minor] Views open off-centre and clipped, and the reader has to press Fit
- Page: `/diagram` factory → Open, `/diagram?view=process`, phone Into
- Opening a module left the upper half of the canvas empty and the content cut at the right edge, with "More beyond the edge". After Fit, text shrank to about 8 px. The process map was also clipped at the right, and on the phone the api diagram opened mid-drawing.
- Why it matters: every change of view starts with a manual repair. The reader also loses the overview the zoom was meant to give.
- Suggestion: fit to content on every change of view, with a minimum readable text size, and pan for anything beyond that.
- Screenshots: `infod-tf-factory-open.png`, `infod-tf-factory-open-fit.png`, `infod-tf-process.png`, `infod-phone-big-api.png`

### 12. [minor] The Check page is a templated sentence repeated 17 times
- Page: `/check`
- I saw 16 warnings that each read "flow X: its equation fits its record worse than holding it at its mean (R² …, scaled error …, mean squared error … times its readings' variance, over 13 points): calibrate it, or write it again". Below them is a block of grey 11 px run-on text in a narrow column.
- Why it matters: when the varying part is a few numbers, the presentation should be a table. Comparing R² across flows is impossible while it is buried mid-sentence.
- Suggestion: one table (flow, R², scaled error, MSE/variance, n), sorted by fit, with the advice stated once. Give the fine print a list with readable size and line length.
- Screenshot: `infod-tf-check.png`

### 13. [minor] The item page draws possible states as a sequence and has no time view
- Page: `/item/ticket/SCRUM-3`
- The header path is every state of the kind in a line with arrows, so it reads "done → stopped → dead". The lease table repeats "(not counted)" on every row. Nothing shows how long the item spent in each state.
- Why it matters: arrows between alternatives assert a sequence that does not exist. The question the page should answer is "where did this ticket spend its time", and it needs a horizontal time strip (a Gantt of states and leases), not 27 rows of timestamps.
- Suggestion: show the path this item actually took, as a timeline strip coloured by state with the leases beneath it, and drop the repeated "(not counted)".
- Screenshot: `infod-tf-item.png`

### 14. [minor] Each Loops sparkline has its own scale and no reference values
- Page: `/loops`
- A backlog of 36 and a blip of 1 draw to the same height. There is no end value, minimum or maximum, and "requests-handled" reads as a flat line at the top. "time off 95%" and "behaviour: past its bound 100%" are two percentages for nearly the same idea in one row.
- Why it matters: sparklines without a scale cue invite false comparison down the column. Two near-duplicate percentages invite the question of which one is the truth.
- Suggestion: mark the setpoint line and the end value on every sparkline, or use a shared scale for loops with the same unit. Merge or explain the two percentages.
- Screenshot: `infod-tf-loops.png`

### 15. [minor] Record and Model are walls of text that could be summarised
- Page: `/record`, `/model`
- Record's main column is raw, truncated JSON in monospace (`infod-tf-record.png`). Model repeats "an integrator, from the model / its dead time: a step of u, or a step test" on almost every row, followed by "process, controller, scope" links. Clicking "process" did not visibly navigate (`infod-tf-model.png`, `infod-tf-model-process.png`).
- Why it matters: redundant repetition hides the two or three rows that differ.
- Suggestion: in Model, group rows that share the same identification. In Record, pull the 2 to 3 meaningful fields of each event type into columns.

### 16. [minor] At phone width the Loops table loses its data, and the diagram is cramped
- Page: `/loops`, `/diagram` at 390x844
- Loops shows only the loop, status and holds columns. now, setpoint, error, time off and trend are off-screen to the right. The nav is cut off ("Mode…"). The diagram gets about 400 px with the oversight module cut off, and the sidebar is stacked below it.
- Why it matters: on a phone, the columns that survive are the labels and not the numbers.
- Suggestion: on narrow screens, render each loop as a compact card with status, now/setpoint and the sparkline.
- Screenshots: `infod-phone-tf-loops.png`, `infod-phone-tf-diagram.png`, `infod-phone-tf-agents.png`

### 17. [polish] Charts on one page do not share a time range
- Page: `/items`, `/loops`
- The selector says "Last 1h", but each chart spans only the minutes recorded, and the spans differ between panels (03:23–03:26 on Items, 03:23–03:30 in the loop panel). The cycle-time chart prints "median 2m" twice and its y-axis starts at 50s without saying so.
- Suggestion: one time axis per page that matches the selector, one median label, and a marked zero or axis break.
- Screenshots: `infod-tf-items.png`, `infod-tf-loop-click.png`

### 18. [polish] Graph and Timeline look the same as List
- Page: `/items?…` Graph and Timeline
- The first screen of all three modes shows the same stacked areas and the same headers, so the change of mode is invisible above the fold.
- Screenshots: `infod-tf-items-graph.png`, `infod-tf-items-timeline.png`

### 19. [polish] Some values are placeholders or ambiguous
- Page: `:8797 /diagram`, loop panel and modelling module
- The loop panel's "When it drives the behaviour" stays at "…". The stock "model-error" shows "– 1" and "excess model-error" shows "–", which is ambiguous between no value, a negative value and a unit. While the loop panel loads, it shows only "…" (`infod-dark-tf-loops.png`).
- Screenshots: `infod-big-open2.png`, `infod-dark-tf-loops.png`

### 20. [polish] Schedule edges in the process map cross the whole drawing
- Page: `/diagram?view=process`
- Dashed lines from the "schedules" box run across every lane to the states they touched, with small counts placed mid-line.
- Suggestion: draw them as short stubs or as markers on the target state.
- Screenshots: `infod-tf-process.png`, `infod-sf-process.png`

## Dark mode in summary

Dark mode is consistent and legible in general (`infod-dark-tf-diagram.png`, `infod-dark-big-api.png`, `infod-dark-tf-loopdetail-wait.png`). Two problems: the Items state ramp inverts so that the dominant band becomes the brightest shape (finding 6), and the thin 1 px block-diagram strokes with 7 px subscripts are harder to read on dark than on light (finding 10).
