# ergostat: the newcomer, briefed

Reviewer: the same software engineer who wrote `newcomer-blind.md`. Since then I have read `intent.md`, the README, `docs/WHY.md`, `docs/DESIGN.md` (§6 and §8), `docs/proposals/diagram-options.md`, `docs/layout-rules.md` (opening) and every demo's README. I walked the demos again at 1440x900, at 390x844 and in dark mode. My screenshots for this round are in <workdir>/design/shots/ with the prefix `newcomer-briefed-`.

## What I got right and wrong

My blind guess was that ergostat was "a live control room for AI-agent work pipelines, for operators who know control theory". That was about half right.

- **Right:** it is about feedback loops (stocks, flows, goals, sensors, actors), drawn two ways, and it runs agents when a goal is off.
- **Wrong about the scope:** the pipelines are not the product. They are the demos. ergostat is a **modelling layer on top of the tools a team already has** (monitoring, ticketing, autoscalers). It holds the one thing none of those tools hold: the model relating them. Its value is explaining a system, projecting it, predicting failures and judging controllers, the team's own and the vendors' alike. The aim is to move operations from "monitoring" to "dynamics and controls".
- **Wrong about the audience:** it is for SREs and engineers, and *also* for product managers ("what really exists and what we sell"). Nothing on screen speaks to the second group.
- **Wrong about my role:** a viewer is mostly meant to *read the model*. Approve/Deny is the only write, and it is incidental.

The UI did not teach me any of this. The README and WHY.md did, and the app does not link to them.

---

## 1. Where the application fails to say what it is for

1. **The home view is a set of empty boxes.** On the-job (`/`), the whole first screen is two boxes, "job: 28 feedback loops inside" and "modelling: 11 feedback loops inside" (`newcomer-briefed-job-home.png`). On big it is seven such boxes (`newcomer-briefed-big-home.png`). Intent decision 1 says "a control panel is the diagram with everything else folded away". Today, folding everything away leaves a box, a count and two link-buttons. A closed box says nothing about what the system is, what it is meant to hold, or whether it is holding it. The image-squeeze README promises closed boxes that show "each measure with its value, setpoint, health and trend". The image-squeeze home shows values only, with no setpoint, no health and no trend (`newcomer-briefed-is-home.png`).
2. **The loudest thing on every home page is ergostat modelling itself.** "loop requests-handled … excess 36" and "loop model-fits … excess 1.81" lead the side panel in all six demos. The briefing explained why (the `modelling` system is ergostat-on-ergostat: check findings held as requests, a fixer and an AI tier answering them). It still teaches a newcomer that the product's main subject is the product's own repair queue, not the system it models.
3. **The one place that explains the ideas (the Guide) is the last tab. Its last frame, the hand-over to "your system", is still broken in light mode** (black boxes, `newcomer-briefed-guide-13.png`).
4. **No surface states the value.** WHY.md has a sharp two-sentence pitch ("monitoring tells you a number went up; it does not tell you why, what next, or whether the controls work"). DESIGN §8.1 rules out a paragraph under a page title, which is fair. But no *system* carries even its own one-line description on the diagram. Those descriptions exist: the Items page shows "the tickets, from todo to done" and "asked, re-pinged, answered, approved, labelled SAIL" (`newcomer-briefed-tf-timeline-full.png`).
5. **Projection, prediction and controller judgement, the claimed value, are hidden.** Time-to-limit, projection fans, loop dominance, margins and identified processes all live inside click-only panels and on the Model page. That page is a table of "its dead time: a step of u, or a step test" repeated 12 times (`newcomer-briefed-tf-model.png`). A newcomer never sees a forecast without knowing where to click.

**What would make it obvious, within the decisions (no new pages or panels, two true diagrams, recognised types only):**

- **Make the closed system box the control panel.** Each box should show its one-line description and its goals as rows: name, now vs setpoint (with ≤), a sparkline over the window, the word "off" in red only when it is off, and, where the model has it, "reaches limit in 3h" or a projected end value. This uses an existing surface, the system box and its exposed parts. A newcomer reading `/` would then see "factory: turns Jira issues into merged PRs · tickets waiting ≤ 0 · 0 · holding" and understand the product in five seconds.
- **Put ergostat's own `modelling` system last, collapsed, and stop it leading "Needs attention"** unless the user's own systems are all holding. It is a legitimate system and should stay modelled (that is the ergostat-on-ergostat framing). It should not outrank the subject.
- **Give the Guide a door from the empty state.** On the first visit to a project (no pins and no history in browser storage), the Diagram's toolbar could hold a single quiet link, "New to stocks, flows and loops? Guide (13 frames)", which goes away once the Guide has been visited. This is no new panel: it is one link in the toolbar that already exists.

## 2. My earlier findings, revisited

| # | Blind finding | Verdict now |
|---|---|---|
| 1 | No orientation on the first screen | **Stands, and is worse**: the intent makes the folded diagram *the* control panel, and today it is the emptiest view in the app. |
| 2 | Demos permanently "on fire" from housekeeping loops | **Partly a misunderstanding.** `modelling` is ergostat modelling its own upkeep, on purpose. The finding **stands** as a priority and wording problem: the subject's loops are drowned, and "unanswered-requests 36" is really "36 model problems nobody has fixed yet", which nothing says. |
| 3 | Guide's last frame has black boxes in light mode | **Stands** (`newcomer-briefed-guide-13.png`). |
| 4 | Approval cards are machine text and point at a CLI | **Stands, and is worse**: intent decision 7 makes approving and denying *the* human action (the "Inbox"). The UI has no "Inbox". It has "Needs attention", where the cards read "person/approve@3156 approve is asked: … `ergostat actions` lists them", with a "how ma[ny]" box. On big, 24 Deny-only "request/…" cards fill the panel. |
| 5 | Loop evidence contradicts itself | **Stands**: "u moved by fixer … never opened. Its valve did not open in the 16m recorded" sits beside "Moves requests-answered 3.45/h" and "Last decision 16m ago: act: fixer" (`newcomer-briefed-tf-evidence.png`). |
| 6 | Phone width cuts the nav and tables | **Stands, with a new twist**: at 390px, `/` opens the **Loops** table, not the diagram (`newcomer-briefed-tf-phone.png`, `newcomer-briefed-is-phone-dark.png`). The phone user never sees the product's main view. The nav still fades out at "Mode…", so Check and Guide are hidden, and the Guide stays unreachable. |
| 7 | Items Timeline equals Graph | **Partly a misunderstanding.** Timeline is a real Gantt chart where items have relations (roadmap: `newcomer-briefed-rm-timeline.png`). On ticket-factory, though, Timeline silently shows the same flow charts plus "No relations among these kinds: a kind declares them under relations: (blocked_by: ticket)" (`newcomer-briefed-tf-timeline-full.png`). That is a YAML instruction to a reader who cannot edit YAML (decision 7). It should show each ticket's states as bars over time, which needs no relations. |
| 8 | Open/Into land off-centre or tiny | **Stands** (`newcomer-briefed-tf-factory-open.png`: the factory frame opens with its top-left at mid-screen and the rest beyond the edge). |
| 9 | Big Process view blank | Not re-tested on big. The ticket-factory process map renders, but see the new finding on its tangle. |
| 10 | Jargon everywhere | **Partly a misunderstanding**: much of it is the disciplines' own words, which the decisions protect (Sterman's and Åström's vocabulary is the point). It **stands** for the configuration-speak ("declares them under relations:", "SPEC §12e", "ergostat.yaml:94", "`ergostat actions` lists them"). That text speaks to the author, not the reader, and contradicts decision 7. |
| 11 | Top-level Blocks view says nothing; "Q" unexplained | **Partly a misunderstanding**: on software-factory, Q_factory (1×3) → Q_product(s) (3×1) with a 3-wide feedback bus is a correct MIMO closed-loop diagram, and it shows the main story (`newcomer-briefed-sf-blocks.png`). It **stands** that "Q" is never defined. A control engineer expects T(s) or G_cl for a closed loop, or at least a legend. Seven unconnected Q boxes on big carry nothing (`newcomer-briefed-big-blocks.png`). |
| 12 | Overlapping loop markers | **Stands, and is worse** than I thought, because the Dynamics view must look like Sterman to an SD expert. B35 still sits on B17 in `making` (`newcomer-briefed-tf-making-dyn.png`). In image-squeeze `service`, five loop markers (B42, B36, R12, R8, B39, each with "+2" or "+1") are stacked in a column, far from the loops they name (`newcomer-briefed-is-service.png`). |
| 13 | Same fact, different words per view | **A misunderstanding, by design**: "desired level / excess" in Dynamics and "setpoint / off by" in Blocks are each discipline's own words (decision 2). The flaw is that the *side panel* switches with the view, so the same loop changes wording in place. The panel is not a diagram: it should keep one vocabulary. |
| 14 | "N loops off" jumps | Stands (minor). |
| 15 | 16 greys in stacked charts | Stands (minor). The DESIGN rule "colour only for exceptions" is right, but the states should then be fewer: fold the zero-count ones. |
| 16 | Item page time formats | Stands (minor). |
| 17 | "40m ± 2d" | Stands (polish). |
| 18 | Bare "not found" | Stands (polish). |
| 19 | ShapeConnectionPin console error | Stands: seen again on every diagram load (408.4 and 240.9). |

## 3. Where the UI contradicts the intent, and what to keep

**Contradictions**

- **Decision 1 (the diagram is the control panel; no extra panels).** The home is the diagram, plus a permanent side panel that duplicates the Loops page, plus a Loops page that duplicates both. The Agents page and the Model page are tables of the same loops again. This is the "more pages, more panels" pattern the owner warns against. It already exists.
- **Decision 2 (Blocks: a function in every block).** In the `making` Blocks view, the controllers and actuators are labelled with agent names ("keep-worked-opened", "open-pr", "work", "AI agent"), and sensors read "H = 1, items: ticket, worked, every 3 s". The plants are right (P(s) = 1/s). The loops do not read one per row: the pr-open sensor dangles at the bottom left with ovals saying "from intake" and "to review", and the text is about 7px (`newcomer-briefed-tf-making-blocks.png`, `newcomer-briefed-tf-blocks-dark.png`). A control engineer would expect C₁(s) in the block, with the agent as a small caption under it.
- **Decision 2 (Dynamics true to Sterman).** Mostly met. The stocks, valves, clouds, goal-seeking auxiliaries ("desired worked → − → excess worked"), link polarities and `<shadow>` variables are right (`newcomer-briefed-tf-making-dyn.png`). It breaks where loop markers float away from their loops (image-squeeze `service`) or collide (B35 on B17).
- **Decision 3 (recognised diagrams).** The process map is a recognised type, and replacing Wiring with it was right. But it draws a "schedules" pseudo-kind whose dashed causation lines wrap around and through the ticket frame (`newcomer-briefed-tf-process.png`). That part is not process mining, and it is the least readable part of the view.
- **Decision 7 (read-only, a few gated actions).** The human action is buried in prose cards. The cards also send the reader to the CLI (`ergostat actions`) and to YAML. Some cards offer Deny with no Approve.
- **DESIGN.md §6 vs. the drawn Dynamics.** The doc still describes the main diagram as "sensors as gauges, controllers as boxes with their setpoint". Decision 2 forbids both in Dynamics, and the current drawing correctly omits them. The doc should follow the drawing.
- **Agents page counts disagree with themselves.** The header ladder says "2 person · 4 ai · 13 program · 16 rule", but the group headings below say "0 person", "1 ai", "4 program" (`newcomer-briefed-tf-agents.png`).

**Keep**

- The **Dynamics drill-down** at system level (`making`): it is a recognisable Sterman stock-and-flow diagram with live values. Light and dark are equally clean.
- The **software-factory top level**: two system boxes with signed links between product (bugs-live, users) and factory (filed-bugs, deployed). It tells the "a factory and the software it builds" story at a glance. This is the model every closed-box home should follow.
- The **Loops table** (`newcomer-briefed-tf-loops.png`): its columns (now, setpoint, error, time off, back in, trend, behaviour) are exactly the control-panel rows the closed boxes should carry. Keep the content; move it into the box.
- The **roadmap Timeline** (Gantt with dependencies and a "now" line), and the image-squeeze **case gallery** on Items.
- The **evidence panel's scope** (y vs r, u, e on one axis).
- The **restraint** of the visual design (one ink, red only for off), the shared selection across views, and the URL-per-page routing.

## 4. Significant changes I would make

**A. The folded diagram becomes the product's front page (merge Loops into it).**
*Sketch:* `/` with every system closed. Each box is a small table:
```
┌ factory ─ turns Jira issues into merged PRs ─────────── ▸ ┐
│ tickets waiting       0   ≤ 0     ▁▁▂▁▁▁   holding        │
│ CI failures fixed     0   ≤ 0     ▁▃▁▁▁▁   holding        │
│ cycle time         0.04h  ≤ 2h    ▂▂▃▂▂▂   in 6h at limit │
└────────────────────────────────────────────────────────────┘
```
The links between boxes stay signed (as on software-factory). A box with a loop off gets its row in red and its outline in red. **Remove the Loops page** (its rows are now in the boxes; one box per system). The phone home becomes this same stack of boxes, one per row, so it can stop redirecting to a table.

**B. The Inbox is a part of the diagram, not prose in a side panel.**
Model "waiting for you" as a stock in a `you` (person) box on the home diagram, which decision 1 prefers. Each waiting request becomes an item in that stock. Clicking the stock opens the existing item list: one line per request in plain verbs ("Move SCRUM-2 to Done in Jira", "Push branch fix-12"), with Approve and Deny on each, and the command behind a disclosure. Twenty-four requests of one kind fold into one row ("24 stocks have no unit: deny all / open"). The side panel's "Needs attention" shrinks to a count that links to that box.

**C. Blocks drawn as a textbook would draw them.**
Every block carries its function (C(s), a relay symbol, P(s) = 1/s, H(s) = 1). The agent name goes in small text *under* the block, never as its label. One loop per row, left to right: r → Σ → C → u → P → y, with H on the return path beneath. Cross-loop signals use the textbook's labelled arrows into a junction, not oval off-page tags. At the top level, replace "Q" with "T" (the closed-loop transfer) and define it once in the export legend. Minimum drawn text of 11px (the DESIGN token), reached by fitting each row rather than the whole graph.

**D. Dynamics loop markers belong inside their loops.**
Each R/B marker should sit at the centre of the polygon its loop draws, and never in a list or column. Where loops share a centre, offset them along the loop path. The "+2" annotations should go: they are not Sterman notation, and the loop list in the panel can hold that detail.

**E. Show the value: projection on the diagram.**
Every stock tank that has a limit or a goal gets its projected value at the window's end, as a faint dashed tick on its meter, plus "limit in 3h" in the box row (change A). This is the "what next" that WHY.md promises, and today it appears only after the right click.

**F. Fold ergostat's own `modelling` system by default, and rename it in the reader's words.**
Draw it last, closed, with the goal "model problems unfixed: 36 (≤ 0)". Its loops enter the header count only when the user opts in (via the ⋯ menu, which already exists).

**G. Cut configuration-speak from every reader surface.**
No "declares them under relations:", no "ergostat.yaml:94", no "`ergostat actions` lists them", no "(SPEC §12e)" outside Check. Replace each with what the reader can see or do. For Timeline without relations, draw plain per-item state bars instead of a hint about YAML.

**H. Phone.**
Make the tab bar wrap into two rows, or turn it into the existing select-style control the project picker uses, so Check and Guide are reachable. Make the home the stacked system boxes from change A.

Every change above reuses an existing surface: the diagram, the system boxes, the Items list and the ⋯ menu. One page is removed (Loops) and none is added.
