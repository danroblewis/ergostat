# ergostat: blind review by an interaction and visual designer

Screenshots are in `<workdir>/design/shots/` (prefix `ixd-`).
Demos walked: ticket-factory (:8791), the-job (:8792), image-squeeze (:8793, home), roadmap (:8794, home), software-factory (:8796), big (:8797). I checked phone width (390x844) and dark mode on the main pages. I did not press Approve, Deny or Done, so I did not change any demo's state.

## What I think it is

ergostat is a live operations console for "factories" of automated work. AI agents, scripts, rules and people move items (tickets, PRs, documents, images) through states. The tool models the setup as **system dynamics** (stocks, flows, feedback loops R/B) and as **control blocks** (setpoint, controller, plant, sensor). Each "loop" holds a quantity at a setpoint, and the app shows which loops are "off".

The home page is a diagram with a "Needs attention" rail. That rail mixes loop alarms with **approval requests**: outward acts by agents (git push, PR comments, Jira comments) wait for a human Approve or Deny there. Other pages:
- **Loops**: control-loop health.
- **Agents**: who acts, at what cost.
- **Items**: work in progress, with per-item history.
- **Record**: the raw event log.
- **Model**: system-identification status.
- **Check**: lint of the YAML model.
- **Guide**: a 13-step primer on SD and control.

Audience: an engineer or engineering lead who runs AI-agent pipelines and thinks in control theory or system dynamics. It is also a supervisor who has to approve the agents' outward acts. It is not for casual users: the vocabulary is SD and control (plant, setpoint, transfer function, Harris index). Confidence: medium-high on "what". On "who" it is medium: the approvals rail suggests a single owner-operator, not a team.

## Findings, worst first

### Blockers

1. **`/` and `/diagram?…` (Open / Into on a module): the canvas goes blank and gives no feedback.** Clicking *Open* on "factory" (ticket-factory) or *Into* on "api" (big) blanks both the canvas and the right rail. They stay blank for at least 1.5–3.5 s, and there is no spinner or skeleton. Loading the same URL directly renders in under 1 s, so the slow part is the client-side transition. For an operator this looks like a crash, and they will click again or reload. Screenshots: `ixd-tf-diag-open-factory.png`, `ixd-tf-diag-open-fit.png` (pressing Fit on the blank canvas does nothing), `ixd-big-into-api.png`, and for comparison `ixd-big-into-api-late.png`. Fix: keep the old diagram (dimmed) until the new one is ready, show a loading state in canvas and rail, and never blank the rail.

2. **`/diagram?view=process` on big: an empty canvas with no explanation.** The Process view of the largest demo shows a blank white area for more than 6 s. There is no "no item kinds to map" message, and the controls (States/Events, Counts/Times, paths slider) still look active. The user can't tell "empty" from "broken" from "loading". Screenshots: `ixd-big-process.png`, `ixd-big-process-late.png`.

3. **`/guide?frame=12` (last step, "Your system, both ways"): the system-dynamics thumbnails render as solid black boxes.** In light mode the module cards are filled black, with near-invisible text and Open/Into ghosted. The same happens at phone width in dark mode. This is the payoff step of the onboarding guide, and it looks broken. Screenshots: `ixd-job-guide-12.png`, `ixd-sf-phone-dark-guide13.png`.

### Major

4. **`/` Needs attention rail: approvals, alarms and system chatter share one undifferentiated stream.** The rail has no grouping, no priority and no counts per kind:
   - Loop alarms (red), approval requests (amber, with Approve/Deny) and modelling requests (amber, Deny only) are interleaved.
   - On big, the rail is 24 near-identical "modelling holds no-unit on stock.api-q0 … q1 … q2" requests, each 7 lines long with its own Deny field. That buries the one real alarm.
   - The item text changes between loads ("the decision tier" vs "the rule tier"), so the list feels unstable.

   This rail is the primary action surface: it is where the operator approves git pushes. It needs separate sections (Approvals / Off loops / System), collapsing of repeated requests ("24 stocks have no unit – Deny all / review"), and bulk actions. Screenshots: `ixd-big-diagram.png`, `ixd-big-blocks.png`, `ixd-tf-home.png`.

5. **`/` approval controls are unclear and truncated.**
   - The text inputs are too narrow for their placeholders ("why (to de…", "how ma…"), so the user never sees what is being asked.
   - "Deny" is a borderless text button next to a bordered "Approve", so the two weigh differently and it's unclear whether the reason field belongs to Deny.
   - Some requests offer only "Deny", with no Approve.
   - Each card is a paragraph that mixes the command line (`python3 bin/github.py comment …`), timing and approval statistics.
   - The advice "consider gate: auto … or an AI approver" is buried mid-sentence instead of being an action.

   For a high-stakes action (an outward git push), the command, the target and the decision should each stand apart. Screenshots: `ixd-tf-home.png`, `ixd-tf-diag-blocks.png`, `ixd-job-home.png`.

6. **`/agents`: the tier summary and the group headers use the same "N label" pattern for different things.** The summary reads "**2** person → **4** ai → … **13** program". The group headers below read "**0** person", "**1** ai", "**4** program", but there are 2 people, 4 AIs and 6 programs listed under them. The header number is a tier index, not a count, yet it has identical bold-number-plus-label styling. A reader takes "0 person" as "no people", which contradicts the rows beneath. Screenshots: `ixd-tf-agents.png`, `ixd-sf-agents.png`, `ixd-tf-phone-agents.png`.

7. **`/` Dynamics overview: module cards carry no state.** The top-level cards for modelling, job, roadmap's delivery, and every system in big show only "N feedback loops inside" over a large empty area. They have no off-loop count, no colour and no key values. The app's main question is "which loop is off", but the overview can't say which module the off loop is in. A card should carry its own "2 off" badge, matching the header. Screenshots: `ixd-big-diagram.png`, `ixd-job-home.png`, `ixd-road-home.png`.

8. **`/` (Open): the opened module appears off-screen and the viewport is not refit.** After *Open* on factory, the expanded content starts low on the canvas and runs off the right and bottom ("More beyond the edge"). The floating toolbar overlaps diagram labels. After *Open* on modelling, the module is drawn below the others, and the user lands looking at the wrong thing. The view should frame what was just opened. Screenshots: `ixd-tf-diag-open-5s.png`, `ixd-tf-diag-open-modelling.png`.

9. **Phone width (all pages):**
   - The nav tabs scroll sideways with no affordance: "Mode…" is cut off, and Check and Guide are invisible.
   - Tables crop silently at the right edge. On Loops you see loop, status and holds, but not now, setpoint or error, which are the numbers that matter.
   - On Record, each row is a tall block of whitespace because the hidden data column wraps.
   - The diagram is not fitted: the oversight module is cut off.
   - `/` lands on Loops on a phone but on Diagram on desktop, with no notice.

   Screenshots: `ixd-tf-phone-diagram.png`, `ixd-tf-phone-loops.png`, `ixd-big-phone-dark-record.png`, `ixd-big-phone-dark-diagram.png`, `ixd-tf-phone-items.png`.

10. **`/record`: an empty filter result claims the log is empty.** Filtering for `nothing.matches` shows "Nothing recorded yet." The record is not empty; the filter matched nothing. This misleads, and there is no "clear filter" link. Screenshot: `ixd-job-record-empty.png`.

11. **`/items` search: "Nothing matches." is placed about 3000 px below the fold.** Searching "zzzz" leaves every per-kind chart and legend in place. The only feedback is a line at the bottom of the page, so the screen looks unchanged. Charts should filter or collapse, and the no-match message belongs under the search box. Screenshot: `ixd-job-items-search-nomatch.png`.

12. **`/check`: an unreadable wall of text.** The 17 warnings are full-width run-on sentences of up to 180 characters. They have no grouping (13 are the same "equation fits worse than its mean" warning) and no links to the flow or the YAML line. Below them, a small grey 11 px paragraph concatenates dozens of "no description" notices with semicolons. Group them by kind and make each one a link. Screenshots: `ixd-tf-check.png`, `ixd-big-check.png`, `ixd-tf-dark-check.png`.

13. **The same alarm is worded differently on each surface.** For the same requests-handled alarm:
   - Dynamics rail: "desired unanswered-requests = 0: excess 37"
   - Blocks rail: "setpoint ≤ 0 (off by 36)"
   - Loops page: setpoint "≤ 0", error "−36"

   That is "= 0" against "≤ 0", and "excess 37" against "error −36". The sign flips, and the vocabulary changes with the view. Pick one phrasing and sign convention for the alarm. Screenshots: `ixd-tf-home.png`, `ixd-tf-diag-blocks.png`, `ixd-tf-loops.png`.

14. **`/items` (Graph and Timeline): switching views barely changes the screen.** Graph and Timeline show the same per-kind area charts as List at the top. The difference sits below the fold or is replaced by a config instruction ("No relations among these kinds: a kind declares them under relations: (blocked_by: ticket)"). The segmented control promises a different view and gives nearly the same page. The empty state reads as developer documentation. Screenshots: `ixd-job-items-graph.png`, `ixd-job-items-timeline.png`.

15. **`/items` stacked charts: 10–17 states in near-identical greys.** The ticket chart has 17 states (new, leased, picked, … dead) in about 6 indistinguishable grey tones, and the legend swatches are 8 px. You can't tell which band is which. Use a sequential ramp with labels on the bands, or highlight a band on legend hover. Screenshots: `ixd-tf-items.png`, `ixd-tf-dark-items.png`.

### Minor

16. **`/` Process view crops content and uses tiny text.** On the first render the ticket chain runs off the right edge, and node labels are about 9 px. Screenshot: `ixd-tf-diag-process.png`.
17. **`/diagram?view=blocks` wiring collisions.** In ticket-factory, wire-count labels "3", "2" and "4" collide around the review block, and parallel wires overlap. In the big Blocks view, the seven modules are stacked in one vertical column with no relations, which wastes the canvas. Screenshots: `ixd-tf-diag-blocks.png`, `ixd-big-blocks.png`.
18. **SD diagrams after Into have small labels that collide.** Labels are about 8 px at default zoom (oversight). On api, the "B10" loop marker sits on top of "excess api-q2". Screenshots: `ixd-tf-diag-into-oversight.png`, `ixd-big-into-api-late.png`.
19. **"Open all" on big fits seven modules at thumbnail scale, so nothing is legible.** It needs a minimum zoom, or a prompt to drill into one module. Screenshot: `ixd-big-open-all-fit.png`.
20. **Side panels show leftover "…" placeholders.** The stock panel has "…" under the title, and the loop panel has "When it drives the behaviour …". These look like unresolved loading states. Screenshots: `ixd-tf-into-click-stock.png`, `ixd-tf-into-click-loop.png`.
21. **`/items` table overflows on desktop.** The last column header is clipped ("in" / "in stat"), and its values are cut ("1n"). Screenshots: `ixd-tf-items.png`, `ixd-tf-dark-items.png`.
22. **`/item/<id>`: run-together status text and an inconsistent date format.**
   - "Not held Attempts 0 of 3." runs together with no separator.
   - Timestamps are "11/22/2026, 03:28:05" (US locale), while Record uses "03:24:35" and charts use "03:24".
   - Item IDs in tables are bold black text that are actually links, with no link affordance.

   Screenshot: `ixd-job-item-detail.png`.
23. **`/record`: the data column is raw JSON.** It includes absolute temp paths ("<workdir>…") and long hex run IDs, truncated with no way to expand. Screenshot: `ixd-tf-record.png`.
24. **`/model` heading hierarchy.** "What's available" (h2) sits directly above "Loops" (h2) at the same weight with no content between them. The per-row "process, controller, scope" links all lead into the generic Blocks diagram rather than the specific panel. Screenshots: `ixd-tf-model.png`, `ixd-job-model-controller.png`.
25. **Loops counter in the header jitters.** "3 loops off" becomes 6, 4, 5 and 2 within seconds as you change tabs. It may be correct live data, but it has no trend or hysteresis, and the off/holding states flicker. Screenshots: `ixd-tf-loops.png`, `ixd-tf-agents.png`, `ixd-tf-record.png`.
26. **`/guide` first step.** "ad-spend" floats as bare text with no knob glyph or connector to "customers", so "You control the knob" has no knob. The step dots are about 10 px, too small as tap targets on a phone. Screenshots: `ixd-tf-guide.png`, `ixd-tf-phone-guide.png`.

### Polish

27. **Unknown routes return a bare, unstyled "not found"** in a serif monospace font, with no header and no way back. Screenshot: `ixd-job-404.png`.
28. **Pluralisation and units.** "1 actions" and "0.467 1" appear, the latter with a unit of "1". Screenshots: `ixd-tf-into-click-stock.png`, `ixd-tf-diag-open-modelling.png`.
29. **System picker.** It is a native select styled as plain grey text with a detached chevron about 150 px to the right, so it does not read as a control. The other systems' "(2 off, 1 unknown)" status only shows inside the list. Screenshot: `ixd-tf-home.png`.
30. **Internal jargon in user copy.** "(SPEC §12e)" appears on big's Items, and YAML file:line references appear in warnings. They read as developer notes. Screenshot: `ixd-big-items.png`.
31. **Dark mode is generally well done.** Tokens carry over and contrast is fine. The only dark-specific issues seen are the black-on-black guide thumbnails (#3) and the chart greys (#15). Screenshots: `ixd-tf-dark-diagram.png`, `ixd-tf-dark-check.png`.

## What works

- The loop highlight when you click a B/R marker is excellent: the rest dims and the loop's path turns blue, with a clear "Around the loop" table. Screenshot: `ixd-tf-into-click-loop.png`.
- The Loops page detail panel (y/u/e charts with the red band where the loop is off) explains a loop well. Screenshot: `ixd-job-loop-click.png`.
- The time-window menu is clear and well grouped. Screenshot: `ixd-job-timemenu.png`.
- The typography is quiet and consistent across pages, and the header is stable.
