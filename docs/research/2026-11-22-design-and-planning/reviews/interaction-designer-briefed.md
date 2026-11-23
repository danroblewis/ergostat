# ergostat: briefed review by an interaction and visual designer

Second pass, after reading `intent.md`, `docs/WHY.md`, `docs/DESIGN.md`, `docs/DISCIPLINES.md`, `docs/DECISIONS.md` and every demo README. New screenshots are in `<workdir>/design/shots/` with the prefix `ixdb-`; the blind pass used `ixd-`. I did not press Approve, Deny or Done.

## What I believed, and what it is

**Blind:** an operations console for agent pipelines, for one owner-operator who approves outward acts.

**Actually:** a modelling tool. It holds the model that relates a system's existing tools, and it shows that model two ways, each in its own discipline's notation: **Dynamics (what is)** and **Blocks (what we control)**. Running agents when a goal is off is one use of the model, not its point. The audience is wider than I assumed: engineers and SREs, but also product managers ("what really exists and what we sell"). It has to survive three doubts in order: is it useful, will people use it, will it make a difference.

I got the mechanics right. I got the purpose wrong, and the UI is why: almost everything on the first screen is about running the machinery, and very little is about the system being modelled.

## 1. Where the application fails to say what it is for

1. **ergostat's own self-model is the first thing you see in every demo.** Every project includes a system called `modelling` (11 feedback loops). It always sits top-left on the home diagram. Its two goals, `requests-handled` and `model-fits`, are the top red items in Needs attention in ticket-factory, software-factory, the-job, image-squeeze and big. They also account for most of the header's "N loops off".
   - So a newcomer's first alarm is about ergostat's own housekeeping (unanswered modelling requests, model error), never about the team, product or service in front of them.
   - In big, 24 of the 26 attention items are modelling requests ("nothing says its unit").
   - The page says "this is a tool that is struggling with itself", not "this is your system, and here is what is off in it".
   - Screenshots: `ixdb-tf-home.png`, `ixdb-sf-home.png`, `ixdb-big-home.png`, `ixdb-job-sd-open.png`.
2. **The two perspectives aren't named where you choose them.** The Guide's own chapter titles say it best: "System dynamics: what is" and "Control: what we control". The view switch, though, says only "Dynamics / Blocks / Process". The single sentence that explains the product ("one model, read two ways") is on step 2 of a 13-step guide behind the last tab. Screenshots: `ixdb-job-guide1.png`, `ixdb-tf-home.png`.
3. **The "control panel" carries no control information.** The intent says the control panel is the diagram with everything folded away. The image-squeeze README promises closed boxes that show "each measure with its value, setpoint, health and trend". What the boxes actually show is a list of bare port numbers ("excess bytes-per-mp 29.6", "batch-time 37.1"), with no setpoint, no health, no trend and no "off" mark. The other systems' boxes say only "N feedback loops inside" over empty space. A product manager looking at the home page can't tell whether anything is good or bad. Screenshots: `ixdb-sq-service-crop.png`, `ixdb-sq-home.png`, `ixdb-big-home.png`.
4. **The two disciplines are hidden two levels down.** In both views the first screen is a grid of closed modules. In the-job, Open on `job` reveals another grid of 10 closed modules. Only at the third level (`incidents`, `delivery`) do the true stock-and-flow and block diagrams appear, and those are good. An SD expert or control engineer judging "instantly clear to an expert" never reaches the expert notation without knowing to drill. Screenshots: `ixdb-job-home.png`, `ixdb-job-sd-open.png`, `ixdb-job-dynamics-incidents.png`, `ixdb-sf-blocks-delivery.png`.

**What would make it obvious, within the owner's decisions (no new pages or panels, two true diagrams, only recognised types):**

- **Label the view switch with its purpose:** "Dynamics · what is" and "Blocks · what we control". The legend at the bottom of the rail ("How to read it") opens collapsed at the top of the rail on first visit, then collapses for good.
- **Make the user's system the subject of the first view.** Draw `modelling` (ergostat's own loop) as a small, muted box apart from the others. Keep its goals out of the header count, or count them apart ("2 off, both ergostat's own"), and put its requests in their own collapsed group in the rail.
- **Make the closed boxes the control panel they are meant to be.**
  - **In Dynamics,** each shown stock gets its level, the desired level as a tick, a trend line and the off state.
  - **In Blocks,** a subsystem block keeps its function label (Q_x) and gets its loops' status on its output lines, as DESIGN §6 already colours a loop's lines. Its r inputs and y outputs are named on the ports.
- **Open the first diagram one level deeper by default, when the root is only a wrapper.** If a system contains only modules, the first view opens it, as the-job's README describes ("`job` open").

## 2. My earlier findings, revisited

| # | Blind finding | Now |
|---|---|---|
| 1 | Open / Into blanks the canvas with no loading state | **Stands** (not contradicted; Open on the-job took about 5 s to render) |
| 2 | Process view on big is blank with no explanation | **Stands**, confirmed again: `ixdb-big-process.png` |
| 3 | Guide step 13 renders the SD thumbnails as black boxes | **Stands, worse.** This step is the payoff "your system, both ways", the one place the two perspectives sit side by side: `ixdb-job-guide12.png` |
| 4 | Needs attention mixes approvals, alarms and chatter | **Worse.** It is the Inbox, the only place people act (decision 7), and in every demo it is led by ergostat's own modelling loop |
| 5 | Approval controls unclear and truncated | **Worse.** The approval card doesn't approve the act. It says "Outward acts wait for your approval. `ergostat actions` lists them", which sends the person to the command line. The only controls are a "how ma[ny]" field and "Done". Clicking the card's name opens Blocks "around block/approve" at the top level, with nothing highlighted: a dead end. `ixdb-tf-approve-item.png` |
| 6 | Agents tier index styled like a count | Stands (not re-walked) |
| 7 | Module cards carry no state | **Worse.** It contradicts the core idea that the folded diagram is the control panel (§1.3) |
| 8 | Opened module lands off-screen | **Stands.** Even Fit leaves `delivery` cut off on the left: `ixdb-sf-dynamics-delivery.png` |
| 9 | Phone width | Stands: the Loops table still crops, and the nav scrolls with no affordance (`ixdb-sf-phone-dark-home.png`, `ixdb-sf-phone-dark-diagram.png`) |
| 10, 11 | Empty filter results mislead (Record, Items) | Stand |
| 12 | Check is a wall of text | Stands, but lower priority for this audience |
| 13 | The same alarm is worded differently per surface | **Partly a misunderstanding.** Dynamics says "desired … = 0: excess", Blocks says "setpoint ≤ 0 (off by)". That is deliberate: each discipline's vocabulary. What still stands: "= 0" against "≤ 0" for one goal. What is new and worse: the translation is a find-and-replace that corrupts identifiers. The same request reads "queue-**desired level**-tolerance on **desired level**.ci-upgrade-planned" in Dynamics and "queue-goal-tolerance on goal.ci-upgrade-planned" in Blocks (`ixdb-job-sd-open.png`, `ixdb-job-blocks-incidents.png`). Also, Dynamics still calls the entries "loop X", while its own panel counts R/B "Feedback loops 49", a different thing |
| 14 | Items Graph and Timeline barely differ | **Partly a misunderstanding.** They are for related items (the roadmap demo). The empty state should say "no relations between these kinds" in plain words, not show YAML |
| 15 | Stacked charts in near-identical greys | Stands (`ixdb-sf-items.png` reads well with 6 states; 17 don't) |
| 16–18 | Tiny text and collisions in drilled diagrams | **Stand, and matter more:** these are the expert diagrams the product is judged by. At Fit, incidents' labels are about 6 px (`ixdb-job-dynamics-incidents.png`) |
| 19 | Open all on big is illegible | **Worse:** large systems are a named priority (decision 6) |
| 20 | "…" placeholder in panels | Stands: `ixdb-sq-measure-click.png` (the module panel has "…" under its title; it also says 16 loops where the card says 22) |
| 21–30 | Minor and polish items | Stand. #30's "(SPEC §12e)" appears on Items under `modelling` again |
| 31 | Dark mode well done | **Keep:** `ixdb-sf-dark-blocks-delivery.png` is excellent |

Misunderstandings, in short:
- I took `requests-handled` and `model-fits` to be the user's loops. They are ergostat's own modelling loop.
- I took the per-view wording as an inconsistency. It is a deliberate choice of vocabulary; only its implementation is broken.
- I took the product to be "for an operator". It is equally for explaining a system to people who don't operate it.

## 3. Where the UI contradicts the intent, and what to keep

**Contradictions**
- **Decision 1 (the diagram is the control panel):** the folded boxes show no goals, health or trend (§1.3).
- **Decision 2 (each diagram true to its discipline, and expert-clear):**
  - The notation is right when you get there.
  - The top level of Blocks breaks it. Seven Q blocks are stacked in a column with no signals between them (`ixdb-big-blocks.png`). Ticket-factory has one unlabeled wire from Q_factory into the side of Q_oversight (`ixdb-tf-blocks.png`). That isn't a recognisable block diagram: a hierarchy with no signals should be laid out as a decomposition, or the subsystems drawn with their r and y ports.
  - The Dynamics rail calling a goal a "loop" mixes control vocabulary into the SD view.
- **Decision 5 (namespacing):** parts in the rail are bare ("stock api-q0", "loop requests-handled") with no system shown, even when there are seven systems.
- **Decision 6 (large systems):** the rail repeats 24 identical requests, Process is blank on big, Open all is illegible and Blocks is a column.
- **Decision 7 (people approve or deny in the Inbox):** the approval card points to the CLI and offers no approval of the act (§2, #5).
- **WHY.md's audience (PMs, design docs):** nothing on the first screen answers "what exists, and is it healthy?". `software-factory` has `users 202` and `bugs-live 0` on the product box as bare numbers, with no goal shown.

**Keep**
- **Stock-and-flow at the system level:** clouds, bow-tie valves, shadow variables (`<backlog>`), goal-gap structure (desired → excess, with polarity), and R/B markers with loop names (`ixdb-sf-dynamics-delivery.png`). An SD modeller would recognise this at once.
- **The block diagram at the system level:** Σ with + and −, P(s) = 1/s integrators, H = 1 on the feedback path, r/e/u/y with subscripts, a relay glyph for on-off controllers, MIMO bars, and "to product" / "from intake" off-page connectors (`ixdb-sf-blocks-delivery.png`, `ixdb-job-blocks-incidents.png`). It is textbook-clean, and in dark mode too.
- **The rail switching vocabulary with the view** (desired/excess against setpoint/off by; loop against controller). Fix the implementation, keep the idea.
- **Breadcrumbs** (Everything › factory › delivery) and URLs for every view.
- **The loop highlight and the Loops page scope charts** (from the blind pass).
- **The Guide's structure** (Why / what is / what we control / Yours). It is the clearest statement of the product anywhere in it.

## 4. Significant changes I would make

### A. The rail becomes the Inbox, in three groups, every entry a link into the diagram

```
Needs attention                                     (rail, same place, same width)
┌ Asks you  2 ──────────────────────────────────────────────────────────┐
│ factory · gh comment on PR #41                     waiting 12m        │
│   python3 bin/github.py comment 41 "…"      (monospace, 2 lines max)  │
│   [ Approve ]  [ Deny ]          reason (optional) ______________     │
│   11 asked this week · 0 approved · 0 denied   gate: manual → auto?   │
└───────────────────────────────────────────────────────────────────────┘
┌ Off  1 ───────────────────────────────────────────────────────────────┐
│ ● product · no-live-bugs   bugs-live 2, desired 0      ▁▂▅▇  (spark)  │
└───────────────────────────────────────────────────────────────────────┘
▸ ergostat's own model  2 off · 24 requests (collapsed: "24 stocks have no unit · Deny all")
▸ Suggestions (2)
```

- Approve and Deny carry equal weight, and the act itself (command and target) is the content. The page never sends people to the CLI.
- Every entry's name focuses the part in the current view: it opens the systems that contain it, zooms, and rings the part with the correspondence ring that already exists. That is better than navigating to `around block/approve` at the top level.
- Parts are shown with their system prefix (decision 5).
- Repeated requests of one code fold into one row with a count.

### B. Closed boxes become the control panel (both views, each in its own notation)

Dynamics, closed system box (an SD "sector"):

```
┌ product ───────────────────────── 1 off ┐
│ bugs-live     2 ▕▇▇▏▏ desired 0   ▁▂▅▇  ● │   level bar with the desired tick,
│ missing-ops   1 ▕▇▏▏▏ desired ≤1  ▃▃▂▁    │   trend on one scale, a dot only
│ users       202 ▕▇▇▇▇▏ ≥180       ▂▃▅▆    │   when off (a shape as well as colour)
│ Open ▸   Into ⤓                          │
└───────────────────────────────────────────┘
```

Blocks, closed subsystem: keep `Q_product (3×1)` as the function label, and name the r inputs and y outputs on the ports (r_no-live-bugs, y_bugs-live …). Each output line takes its loop's status colour, as DESIGN §6 already specifies for open loops. Lay out a top level whose subsystems share no signals as a decomposition grid, not a single column.

The "N feedback loops inside" line moves into the box's panel; it says nothing at a glance.

### C. Say the two perspectives where they are chosen

The view switch reads `Dynamics · what is | Blocks · what we control | Process · what happened`. Under the switch, until it is dismissed, the rail opens with a one-line key: "One model, two readings. Click any part: the same part lights in the other view (drag a canvas edge to see both)." This uses the existing split pane and correspondence ring, so it adds no new panel.

### D. Lead with the user's system, and keep ergostat's own loop apart

`modelling` is drawn last, smaller and muted, at the edge of the top level. Its goals are excluded from the header count, which then reads "1 off in product · 2 in ergostat's own model". On every demo the first red thing becomes something about the demo.

### E. Land one level deeper, and fit what you open

- When the root contains only modules, open it.
- After Open or Into, frame the opened system: Fit to its bounds, never to the whole canvas.
- Never blank the canvas: keep the old diagram dimmed under a progress bar until the new layout is ready.
- Hold a minimum label size of 9 px (DESIGN §6 already states it). When Fit would go below it, show "More beyond the edge" instead of shrinking.

### F. Large systems by aggregation, not by shrinking

- On big, "Open all" first opens systems as sectors showing only their goal meters (B).
- In the rail, identical findings collapse to one row.
- On Process, when the map is empty or too large, show a centred statement ("No item events in the last 1h on these systems. Widen the window ▸") instead of a blank canvas.

### G. Phone: the Inbox first

- At 390 px, the page opens with the rail's "Asks you" and "Off" groups. The diagram follows as a fitted, non-interactive thumbnail that opens full screen.
- The nav collapses into a menu with the current page named.
- Tables keep the identifier column and the value, error and setpoint columns, and wrap the rest into a second line per row.

### H. Fix the vocabulary translation at the source

- Translate labels, never identifiers: "goal.ci-upgrade-planned" stays as it is, and the sentence around it changes.
- In Dynamics, call a goal a goal ("goal no-live-bugs"); keep "loop" for R/B loops and for Blocks.
- Use one comparison per goal on every surface: "≤ 0" both in the "desired" sentence and as the setpoint.

## Findings (full revised list)

They are listed in the structured result, worst first.
