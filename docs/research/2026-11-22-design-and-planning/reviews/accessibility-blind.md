# ergostat: accessibility review (blind walk)

Reviewer: accessibility specialist (contrast, keyboard, focus, screen-reader structure, colour-only meaning, motion, text size).
Method: the running demos only (:8791 ticket-factory, :8792 the-job, :8793 image-squeeze, :8794 roadmap, :8796 software-factory, :8797 big), at 1440x900, at 390x844 (phone), at 720x450 (the same as 200% browser zoom on a 1440x900 screen), in light and dark mode. Every page was checked with a Playwright script that reports landmarks, headings, unnamed controls, computed text contrast, rendered text size, target size and Tab order. Screenshots are in `<workdir>/design/shots/` with the prefix `a11y-`. Scripts are in `<workdir>/design/work/a11y_*.py`.

## What I think this is, and who it is for

ergostat is a live operations console for a "factory" of automated workers (AI agents, programs and a few people) that move work items such as tickets, pull requests, image-compression hypotheses and roadmap epics through states. It models that factory in two ways: as a system-dynamics stock-and-flow diagram (Dynamics), and as a control system of feedback loops, each with a setpoint, an error and a controller (Blocks, Loops). It flags loops that are "off" and approvals that are waiting ("Needs attention", Approve/Deny). It also shows the event record, the agents' runs and costs, how well a fitted model explains the data (Model), and warnings about the system description (Check). The Guide is a 13-step tutorial on the two notations.

The audience is the engineer or operator who runs such a factory and knows some control theory and system dynamics. The vocabulary (setpoint, valve, stock, Harris index, dead time) assumes that. How sure I am: fairly sure about the purpose (about 80%), less sure who is meant to approve actions day to day.

For my persona: someone who uses a keyboard only, a screen reader, 200% zoom or a phone, or who does not see colour well, needs to be able to (1) find out which loops are off and why, (2) approve or deny waiting actions, and (3) look at the system's structure. (2) works by keyboard. (1) only partly works. (3) does not work.

## Summary

The page shell is in good shape: `lang="en"`, header/nav/main/aside landmarks, a clear 2px blue focus ring on every native control, Escape closes the detail panel, the time menu moves focus into itself, the Guide takes arrow keys, the CSS has `prefers-reduced-motion` rules, and body text contrast passes in both themes. The problems are where the product earns its value: the diagrams and the tables you click into. They are built for the mouse, have no text alternative, and are drawn at sizes that do not survive zoom or a phone. Several charts tell states apart only by shades of grey.

## Findings (worst first)

### 1. Blocker: the diagram cannot be used by keyboard or screen reader
- **Page:** /diagram (every demo; Dynamics, Blocks and Process views)
- **Saw:** The diagram is one `<svg>` (1120x852) with no role, name, `<title>` or `<desc>`, and nothing inside it can take focus. The "Open" and "Into" controls on each system box are `<g class="sys-btn">` with a rect and a text, so they are not buttons. Stocks (`g.node k-stock`) and connections (`path.edge-hit`) can only be clicked with a mouse. Pressing Tab goes from the toolbar to Export and then straight into the side panel; the diagram is skipped. 37 elements on this page have a pointer cursor and cannot be focused.
- **Why it matters:** The diagram is the home page and the only way to open a system, drill into a stock's detail panel (its value, inflow, outflow, desired level and items), or follow "Draw what is around it". A keyboard user cannot open "factory" in ticket-factory at all. A screen reader hears an empty graphic. This fails WCAG 2.1.1 Keyboard and 1.1.1 Non-text Content.
- **Suggestion:** Give each node, system box and loop marker `role="button"` (or wrap them in `<a>`), `tabindex="0"`, an accessible name such as "stock api-q0, 13, desired 20", and Enter/Space handlers that do what the click does. Make Open/Into real buttons. Also offer a text view of the same structure: a list of systems, then the stocks in each with their inflows, outflows and links, which is what a screen reader user can navigate.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-home.png`, `<workdir>/design/shots/a11y-8797-into-api.png`, `<workdir>/design/shots/a11y-8797-stock-click.png`

### 2. Blocker: table rows that open the detail panel are mouse-only (Loops, Agents)
- **Page:** /loops, /agents (every demo)
- **Saw:** Each row is `<tr class="click">` with no link, button or tabindex inside. On /loops the only focusable elements are the 11 in the header. Clicking a row opens the detail panel: the loop's y/u/e charts, last decision, status, sensor and controller, and the explanation of why the loop is off. On /agents the panel shows the agent's command, runs, log and costs. /items is fine because its rows hold an `<a>`. Even after a mouse click, focus stays on `<body>` and does not move into the panel.
- **Why it matters:** "Why is this loop off?" is the main question this product answers, and keyboard and screen-reader users cannot reach the answer. WCAG 2.1.1 and 2.4.3 Focus Order.
- **Suggestion:** Make the first cell of each row a link or button, as /items does. When the panel opens, move focus to its heading. When it closes, return focus to the row.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-loops.png`, `<workdir>/design/shots/a11y-8791-loops-row-clicked.png`, `<workdir>/design/shots/a11y-8793-agent-detail.png`

### 3. Major: the rows under "Feedback loops" in the side panel are mouse-only
- **Page:** /diagram, side panel "Feedback loops"
- **Saw:** Rows such as "factory: 36 feedback loops inside / Open it to see them" are `div.looprow` with a pointer cursor, but they cannot be focused and have no role.
- **Why it matters:** The diagram cannot be reached by keyboard, so this list should be the alternative, and it cannot be reached either.
- **Suggestion:** Use real buttons or links that open the system.
- **Screenshot:** `<workdir>/design/shots/a11y-8794-focus-ring.png`

### 4. Major: chart series are told apart only by shades of grey
- **Page:** /items (List, Graph and Timeline views; every demo)
- **Saw:** The stacked-area chart per item kind uses up to 17 states (new, leased, picked, located, worked, pr-open, ... done, stopped, dead), each drawn in one of about four greys. The legend swatches are 8px squares in the same greys. In dark mode the dark swatches almost vanish into the background. The sparklines on /loops and the item-count charts are `<svg>` with no name or data alternative.
- **Why it matters:** Nobody can match an area to a state, whatever their colour vision. A screen reader user gets nothing from the charts. WCAG 1.4.1 Use of Color, 1.4.11 Non-text Contrast and 1.1.1.
- **Suggestion:** Label the bands directly or show a hover/focus readout. Group the states into at most four or five bands with patterns or clearly different tones, and give each chart an `aria-label` that summarises it (for example "8 tickets: 6 done, 1 leased, 1 located"). The legend counts already hold that data.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-items.png`, `<workdir>/design/shots/a11y-8791-items-dark.png`, `<workdir>/design/shots/a11y-8793-items-graph.png`

### 5. Major: diagram text becomes tiny and does not reflow
- **Page:** /diagram Process view (:8796), /guide on a phone, /diagram on a phone
- **Saw:** In the Process view at the default fit, 49 of 54 labels render at about 8px (event names "ticket.filed 12x", schedule pills "product-manager · every 30s", edge counts). Edge counts are pale grey on grey, and dashed grey lines are hard to see in dark mode. At 390px the Guide's two diagrams shrink to about 3px text and cannot be read. Diagram text is 11px even at desktop size. On a phone the Process view is cropped, and you have to pan to see it.
- **Why it matters:** Low-vision users cannot read the labels, and browser zoom does not help because the SVG is fitted to its container. WCAG 1.4.4 Resize Text and 1.4.10 Reflow.
- **Suggestion:** Keep a minimum on-screen label size (12px or more) and let the diagram scroll instead of shrinking below it. On a phone, show the Guide's two diagrams one above the other at full width.
- **Screenshots:** `<workdir>/design/shots/a11y-8796-process.png`, `<workdir>/design/shots/a11y-8796-process-dark.png`, `<workdir>/design/shots/a11y-8796-phone-process-dark.png`, `<workdir>/design/shots/a11y-8797-phone-guide.png`

### 6. Major: live updates are not announced, and live tables move under the pointer
- **Page:** /diagram side panel, /agents, /loops, /record
- **Saw:** The pages refresh by themselves: 21 DOM changes in 8 seconds on /diagram and 46 on /agents. "Needs attention" went from 15 to 18 to 14 while I watched, and Approve/Deny entries come and go. The only live region I found is one polite `<p>` on /items. On /agents I clicked the 4th row ("improver" was highlighted) and the panel opened "customers", because the rows had re-sorted between the hover and the click. There is no pause control.
- **Why it matters:** A screen reader user is not told that a new approval is waiting, which is the reason to keep the page open. A user with a motor impairment or slow pointer can click the wrong thing, such as Approve on a different action. WCAG 4.1.3 Status Messages and 2.2.2 Pause, Stop, Hide.
- **Suggestion:** Put the "Needs attention" count and new entries in an `aria-live="polite"` region. Keep row order stable while the pointer or focus is in a table, or hold updates while a row is hovered. Add a pause/resume control for live refresh.
- **Screenshots:** `<workdir>/design/shots/a11y-8793-agent-detail.png`, `<workdir>/design/shots/a11y-8791-home.png`

### 7. Major: selected state is shown only visually (no aria-current or aria-pressed)
- **Page:** top navigation (all pages); Dynamics/Blocks/Process; States/Events, Counts/Times; Items List/Graph/Timeline and By parent/By kind; Loops (selected row); Guide dots
- **Saw:** The current page in the nav is marked only by `class="on"` and an underline, with no `aria-current="page"`. The view toggles are plain buttons with no `aria-pressed` or tab roles. The Guide's 13 step dots are `<button class="g-dot">` named only by `title`, and the current step is shown only by a filled dot.
- **Why it matters:** A screen reader user cannot tell which page or view is active, or which Guide step they are on. WCAG 4.1.2 Name, Role, Value.
- **Suggestion:** Add `aria-current="page"` to the nav, use `aria-pressed` (or tablist/tab with `aria-selected`) on the toggles, and use `aria-current="step"` with an `aria-label` such as "Step 2 of 13" on the dots.
- **Screenshots:** `<workdir>/design/shots/a11y-8796-process.png`, `<workdir>/design/shots/a11y-8791-guide.png`

### 8. Major: very low-contrast text and controls (1.6:1)
- **Page:** /item/... (state path), /agents and /items (tier arrows), /guide (dots), loop charts
- **Saw:** On an item page the future states in the state path ("kept → dropped → dead") are rgb(198,203,208) on white, which is 1.63:1. The arrows between tiers on /agents and between counts on /items are the same colour (1.63:1 in light, 1.75:1 in dark). The Guide's unvisited step dots have a 1px border of the same colour. In the loop detail charts the "off" periods are shaded light pink in light mode and dark maroon in dark mode, and the only key is the plain text "Red: off".
- **Why it matters:** Text needs 4.5:1 (WCAG 1.4.3) and controls need 3:1 (1.4.11). "Which states are still ahead" is information, not decoration. The off periods are shown only by colour.
- **Suggestion:** Show future states in the normal muted text colour (4.5:1 or more) with a "not yet" style such as dashed or italic. Raise the dot border to 3:1 or more. Mark off periods with a hatched band or an "off" label on the axis as well as the colour.
- **Screenshots:** `<workdir>/design/shots/a11y-8793-item-detail.png`, `<workdir>/design/shots/a11y-8791-agents.png`, `<workdir>/design/shots/a11y-8791-guide.png`, `<workdir>/design/shots/a11y-8791-loops-row-clicked.png`, `<workdir>/design/shots/a11y-8791-loops-dark.png`

### 9. Major: at 200% zoom and on a phone, half the navigation is hidden with no cue
- **Page:** all pages at 720px or narrower
- **Saw:** At 720x450 (200% zoom) the nav shows "Diagram Loops Agents Items R" and stops; Record, Model, Check and Guide are cut off with no scroll arrow or "more" menu. At 390px "Mode..." fades out. On /loops at both widths the table loses its right columns (now, error, trend, behaviour) to a horizontal scroll inside the table, with no sign that the table scrolls.
- **Why it matters:** Zoom users do not know that the Check and Guide pages exist. WCAG 1.4.10 Reflow.
- **Suggestion:** Wrap the nav or put the overflow under a "More" menu. On narrow screens, show each loop as a card instead of a 12-column table.
- **Screenshots:** `<workdir>/design/shots/a11y-8792-zoom200-diagram.png`, `<workdir>/design/shots/a11y-8792-zoom200-loops.png`, `<workdir>/design/shots/a11y-8792-phone-loops.png`, `<workdir>/design/shots/a11y-8792-phone-diagram.png`

### 10. Major: the main page has no h1, and table headings have no caption or scope
- **Page:** /diagram (no h1; the only headings are two h3s, "Needs attention" and "Feedback loops"), /loops, /agents, /items, /record, /model
- **Saw:** Every other page has an h1, but the home page skips straight to h3. The data tables have no `<caption>` and no `<thead>` (/loops has 11 `<th>` in a body row). On /items the h2 accessible names include the disclosure glyph and the summary, for example "▾review 8 items, 1 kind asked, re-pinged...". On /agents the group headings read "0 person", "1 ai", "4 program". Those numbers are tier ranks, but they look like counts, and the summary line above says "2 person", "4 ai", "13 program".
- **Why it matters:** Screen reader users move around by headings and tables. A missing h1 and unlabelled tables make the pages hard to scan, and "0 person" followed by two people sounds like an error.
- **Suggestion:** Add a visually hidden h1 such as "Diagram: ticket-factory". Use `<thead>`, `scope="col"` and a caption. Mark the ▾ as `aria-hidden`. Label the tiers "tier 0: person" or drop the number.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-home.png`, `<workdir>/design/shots/a11y-8791-agents.png`, `<workdir>/design/shots/a11y-8791-items.png`

### 11. Minor: inputs labelled only by truncated placeholders
- **Page:** /diagram side panel, Needs attention
- **Saw:** The deny-reason field shows "why (to de" and the person-task field shows "how ma". Both are cut off at about 80px. They have an `aria-label`, so a screen reader is fine, but sighted users never see the full prompt, and on :8797 "Deny" appears with no "Approve" beside it, which leaves it unclear what the row is asking for.
- **Why it matters:** WCAG 3.3.2 Labels or Instructions. People with cognitive impairments or low vision cannot tell what to type.
- **Suggestion:** Show a visible label above the field, or widen it to fit its prompt.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-home.png`, `<workdir>/design/shots/a11y-8797-home.png`

### 12. Minor: small click targets
- **Page:** /guide, /model, /items, /record, /diagram side panel
- **Saw:** The Guide's step dots are 12x12px. On /model the "process, controller, scope" links are 15px tall and sit close together. The legend links on /items, the links on /record and the "Evidence" links are 17px tall. The checkbox on /record is 13x13px.
- **Why it matters:** WCAG 2.5.8 Target Size (Minimum) asks for 24x24 or enough spacing. Tremor and touch users will miss.
- **Suggestion:** Give each target at least 24x24px of padding.
- **Screenshots:** `<workdir>/design/shots/a11y-8791-guide.png`, `<workdir>/design/shots/a11y-8791-model.png`

### 13. Minor: links that look the same out of context
- **Page:** /model, /diagram side panel
- **Saw:** Every row on /model ends with "process, controller, scope", and the side panel repeats "Evidence" with `href="#"`. In a links list a screen reader reads "process, controller, scope, process, controller, scope..." with no loop name.
- **Why it matters:** WCAG 2.4.4 Link Purpose.
- **Suggestion:** Add the row's name to each link with `aria-label` or visually hidden text, for example "process of loop located-worked". Make "Evidence" a button, since it does not navigate.
- **Screenshot:** `<workdir>/design/shots/a11y-8791-model.png`

### 14. Minor: sort buttons and symbol-only buttons have poor names
- **Page:** /items (column sort), /diagram toolbar
- **Saw:** The column header "by" is a sort button whose title reads "Sort by by". The zoom buttons are "−" and "+", and "⋯" opens a menu. All three get their names only from `title`.
- **Why it matters:** Names that come only from `title` are announced inconsistently, and "Sort by by" makes no sense.
- **Suggestion:** Use `aria-label`s such as "Zoom out", "Zoom in", "More diagram options" and "Sort by author".
- **Screenshot:** `<workdir>/design/shots/a11y-8791-items.png`

### 15. Minor: the Check page is a wall of small grey prose
- **Page:** /check
- **Saw:** Below the warnings, one paragraph of about 30 lines of 12px grey text lists clusters and several "no description" notes, run together with semicolons.
- **Why it matters:** It is hard to read at low vision and for people with dyslexia, and a screen reader cannot skim it.
- **Suggestion:** Show each note as its own list item at body size, grouped under headings.
- **Screenshot:** `<workdir>/design/shots/a11y-8793-check.png`

### 16. Polish: labels overlap in the diagram
- **Page:** /diagram, Into api (:8797)
- **Saw:** The "B10" loop marker sits on top of "excess api-q2" ("exc B10 i-q2"), "api-q1-low" is drawn across the flow pipe, and in dark mode the floating "More beyond the edge" toolbar covers parts of the diagram.
- **Why it matters:** Overlapping text cannot be read and confuses low-vision users.
- **Suggestion:** Avoid label collisions, and keep the toolbar off the drawing area.
- **Screenshots:** `<workdir>/design/shots/a11y-8797-into-api.png`, `<workdir>/design/shots/a11y-8791-diagram-factory-open-dark.png`

### 17. Polish: some categories are told apart by colour alone in "Needs attention"
- **Page:** /diagram side panel
- **Saw:** Entry names are red for a loop that is off and amber for an unknown loop, a person task, an action, a request or a stock surprise. The prefix word ("loop", "action", "stock") helps, but "loop model-fits" in amber (unknown) and "loop requests-handled" in red (off) differ only by colour.
- **Why it matters:** WCAG 1.4.1. A colour-blind user cannot tell an off loop from an unknown one in this list.
- **Suggestion:** Add the status word, for example "loop model-fits (unknown)", as /loops already does.
- **Screenshot:** `<workdir>/design/shots/a11y-8794-focus-ring.png`

## What works (keep it)
- A visible 2px blue focus ring on every native control, in both themes (`<workdir>/design/shots/a11y-8794-focus-ring.png`).
- Landmarks, `lang`, page titles of the form "demo · ergostat", and `aria-expanded` on the menus and Items groups.
- Escape closes the detail panel, the time menu moves focus into itself, and the Guide responds to arrow keys.
- `prefers-reduced-motion` rules are present. I saw no auto-playing animation.
- Body text passes 4.5:1 in both themes, and dark mode is complete across all pages.
- /items rows contain real links. The Approve/Deny and Done controls are native buttons with labelled inputs.
