# ergostat, reviewed again by a product manager, now briefed

Persona: a product manager who wants to know **what a system really does, whether it is healthy and what to expect**, without the engineering detail.
Before this pass I read `intent.md`, `docs/WHY.md`, the SPEC's §1a (two perspectives) and its section on systems drawn as parts (the "control panel"), `docs/DESIGN.md` §8, `docs/proposals/diagram-options.md`, and the six demo READMEs.
New screenshots are `pmb-*.png` in `<workdir>/design/shots/`. Earlier ones (`pm-*.png`) are cited where a finding still stands.
I covered desktop (1440x900), phone (390x844) and dark mode on Diagram, Loops and Items.

## What I got wrong, and what I got right

My blind guess at the purpose ("watches and steers automated work systems, mostly AI factories, for control-literate engineers") was **too narrow in both directions**:

- **What it is for.** It is meant to be a *model* of any running system (a team, a product, a platform), placed on top of the monitoring and ticketing a company already has. I read it as an agent-orchestration console because every demo is a factory of agents. The demos chose that subject; ergostat itself is not defined by it.
- **Who it is for.** The SPEC says plainly that the Dynamics view is "for product managers and sales" and the Blocks view "for engineers". The intent lists "clearer expectations for product managers" and "the long-term health of products" as expected value. **I am a primary audience, not a secondary one.** That makes the gaps below more serious than I judged them blind.
- **"What to expect".** This exists, and I missed it. Every stock's panel draws a projection past "now" with a Monte Carlo fan and a probability that its goal goes off (`pmb-sf-users-stock.png`). It is hidden two clicks down, covers 4 minutes, and is written for modellers. My earlier claim that there was "no what-to-expect answer" was wrong. The truer complaint is that the answer is buried and illegible to me.
- **Health at a glance.** The SPEC promises that with every system closed, **the diagram is the model's control panel**: each box shows its measures with value, setpoint, health and trend. The image-squeeze README tells me to look there first. That promise is the right one, and the UI does not keep it (findings 1–2 below).

## 1. Where the application failed to tell me what it is for

1. **The first view shows ergostat itself first.** On every demo the top-left box is `modelling`: ergostat's model of its own upkeep (`pmb-big-home.png`, `pmb-sf-home.png`, `pmb-job-home.png`). The first red items in Needs attention are its loops (`requests-handled`, `model-fits`), and so is the red "N loops off" in the header. On the-job, every loop of the person's actual job is holding, yet the header says "2 loops off": both are modelling's (`pmb-job-loops.png`). The README for the-job says the page opens with `job` open. It opens with `job` closed (`pmb-job-home.png`), because the rule "a system alone at its level starts open" no longer applies once `modelling` sits beside it. The tool's own housekeeping hides the subject. A newcomer concludes that it is a tool about itself.
2. **Nothing on the page states the purpose of the model or of the tool.** The SPEC has `purpose:` (what the whole model is for), and every system has a `description` ("textkit and its customers"). The description appears only inside a module's side panel (`pmb-sf-users-panel.png`). The boxes say "18 feedback loops inside". That is a count for modellers. It tells me neither what the system is nor how it is doing.
3. **The boxes do not answer "is it healthy?"** In Dynamics, a closed box lists stocks and flows with bare numbers (`users 216`) and no goal beside them. In Blocks, a closed box is `Q_service 3×3` with nothing else (`pmb-img-blocks-closed.png`, `pmb-sf-blocks.png`, `pmb-big-blocks.png`). The "control panel" described in the SPEC and READMEs is not on screen anywhere.
4. **The forecast that makes it a dynamics tool rather than a monitor is hidden.** WHY.md argues that the shift is from "what happened" to "what will happen". On the page, "what will happen" is a light grey tail at the right of a chart in a stock's side panel, followed by a paragraph that begins "dashed: the model's replay; past now, lighter: its projection 4m ahead, with the loops running…" (`pmb-sf-users-stock.png`).

**What would have made the purpose obvious, within the owner's decisions** (no new pages or panels, two diagrams each true to its discipline, recognised diagram types only):

- Put the model's `purpose:` sentence in the diagram's own title (where a Vensim or Stella model carries its name), and each system's `description` in its box, in place of "N feedback loops inside" (the count can move to the panel).
- Keep `modelling` out of the first view: draw it last, folded, and leave it out of the header count (details in change B).
- Make the closed boxes the control panel the SPEC already specifies (change A). Then the first screen says: these are the systems, this is what each holds, this is how each is doing, and this is where each is heading.

## 2. My earlier findings: which stand, which were misunderstandings, which are worse

| # (blind) | Verdict now | Why |
|---|---|---|
| 1 Health signal is ergostat checking itself | **Stands, worse** | I am a named audience, and the README for the-job expects its own system first. On the-job and software-factory today, every "off" in the header is modelling's (`pmb-job-loops.png`, `pmb-sf-loops.png`). |
| 2 "Loops off" count jumps around | **Stands, partly answered** | The Loops page has a "time off" column over the record and a trend sparkline (`pmb-job-loops.png`), which answers it well. The header and the project switcher still show the instant count: image-squeeze read "7 loops off" in the header and "10 off" in the switcher within a minute. |
| 3 No "what to expect" | **Misunderstanding, but the real problem is as serious** | The projection exists in each stock's panel (`pmb-sf-users-stock.png`). It is 4 minutes long, cannot be lengthened, is not in the Loops table or on the boxes, and is phrased "users-growing: off at +4m03s with p≈0.02". |
| 4 A goal being met on schedule shown as red failure | **Partly a misunderstanding** | "Off" is correct by definition: below the setpoint is off. Users did reach the goal (212 ≥ 180, holding: `pmb-sf-loops.png`). For a PM, though, "not yet reached, on track" and "falling behind" are different news. Both are red today. |
| 5 Red loop names in Needs attention do nothing | Stands | Unchanged. |
| 6 Top-level diagram gives no health at a glance | **Stands, worse** | The SPEC promises measures with value, setpoint, health and trend on every closed box. Blocks shows none of these. Dynamics shows values only. |
| 7 Anyone can Approve/Deny with no confirmation | **Partly a misunderstanding** | Intent decision 7 says approving is the one thing people are meant to do here, and DESIGN.md says writes carry a per-run token. Still stands: there is no confirmation, no "what happens next" and no "who you are". The text points to the CLI (`ergostat actions`) inside a web page (`pmb-tf-home.png`). The "how ma" input with Done for a person block, with no unit or explanation, is still opaque. |
| 8 Process view blank on big | Not re-tested on big. On software-factory and ticket-factory the Process view now draws a process map (`pmb-sf-process.png`). | |
| 9 Blank loading pages | Stands (not re-measured) | |
| 10 Jargon everywhere | **Stands, and matters more** | The Dynamics view is meant to be mine. Its side panel still talks about "decision tier", "known flows explain −16: 16 unexplained" and "no one process". |
| 11 Self-contradictions | Stands. New: the users panel shows "signups 11.4 users/min" in the chart header and "Inflow 17.5/min" in the table under it, for the same moment (`pmb-sf-users-stock.png`). | |
| 12 Same alert worded differently per view | **Partly a misunderstanding** | Dynamics says "desired", Blocks says "setpoint". That follows decision 2: each discipline uses its own words. It still stands where the *substance* differs, not only the words. |
| 13 Suggestions defer their verdict | Stands | |
| 14 Open doesn't frame the result | Stands (`pmb-job-blocks-open.png`: "More beyond the edge") | |
| 15 Phone width half works | Stands | At 390 px the root opens Loops; the Loops table shows loop, status and holds only, with "now" cut (`pmb-sf-phone-dark.png`); the Diagram clips `factory` (`pmb-sf-diagram-phone-dark.png`); the tab bar cuts "Model". |
| 16 Items table overflows | Stands (`pmb-tf-items.png`, "latest" cut) | |
| 17 Grey-on-grey state chart | **Misunderstanding, partly.** Monochrome is a deliberate design decision (DESIGN.md §8.1: "design in greyscale, add colour last"). Done/underway still cannot be told apart when 16 states share 4 greys (`pmb-tf-items.png`). | |
| 18 Item state strip as a straight line | Stands | |
| 19 Event names stand in for status | Stands (`pmb-road-items.png`: every row "ergostat.item.joined") | |
| 20 Cost columns "–" | **Misunderstanding.** The demos run free stand-ins by default (READMEs: `FACTORY_AI=claude` for real tokens). The page should still say so. | |
| 21 Check page is a lint list | **Misunderstanding of audience.** Check is for the modeller (WHY.md: "ergostat check says what the model is missing"). Keep it; it is just not mine. | |
| 22 "Last 1h" with minutes of data | Stands | |
| 23–27 Guide slide 1, placeholders, truncated inputs, modelling first, wording slips | Stand; modelling-first (26) is **much worse** than I rated it (see §1.1) | |

## 3. Where the UI contradicts the intent or the decisions, and what to keep

### Contradictions

- **The control panel promised by the SPEC is missing from the Blocks view.** The SPEC says "With every system closed, the diagram is the model's control panel". The image-squeeze README says "Each system's box shows its measures, each with its value, setpoint, health and trend". Blocks shows `Q_lab 1×4` (`pmb-img-blocks-closed.png`). Dynamics shows values with no setpoint, health or trend (`pmb-img-home.png`).
- **Intent: a system alone at its level starts open.** The the-job README expects `job` open. It is closed because `modelling` is a sibling (`pmb-job-home.png`). The tool's own module changes the user's first view on every project.
- **Intent: on top of existing tools, for PMs too.** The projection is the core value for PMs, yet it is confined to a panel with a fixed 4-minute horizon that no control lengthens (the window menu offers only past windows: `pmb-sf-window-menu.png`).
- **Decision 2 (Dynamics has no controller blocks).** The Dynamics sidebar's Suggestions talk about "its decision (fixer, every 1m) is the slowest stage" (`pmb-sf-home.png`). That is controller language inside the SD view.
- **Decision 1 (no new panels).** The sidebar is already a panel stack (Needs attention, Suggestions, Feedback loops, How to read it). On big it holds 26 Deny requests (`pmb-big-blocks.png`). The diagram is supposed to carry the message, and here the sidebar outweighs it.
- **Decision 3 / diagram-options.** The process map is a recognised type (van der Aalst) and was the recommended replacement for Wiring, so it is right. But the proposal put an item kind's process map on the **Items** page; the build put it as a third Diagram view. That is fine, but the Items page still has the stacked chart the proposal meant to move.

### What it does well, and should keep

- **The module panel's "Its measures, on one time axis"** (`pmb-sf-users-panel.png`): each of product's outputs (missing-ops, bugs-live, users) with its "desired ≥ 180" line. This is the best PM view in the product. It is the control panel, just in the wrong place.
- **The stock panel's projection with its fan** (`pmb-sf-users-stock.png`). It is the honest, probabilistic "what to expect", and almost no monitoring tool has it.
- **The Loops page**: time off over the record, back-in time, trend sparkline, and "behaviour" in one word (`pmb-job-loops.png`). The windowed health figure I asked for blind is here.
- **Process map** (`pmb-sf-process.png`): ticket filed → started → submitted → merged, with counts and rework loops. A PM reads it on sight.
- **Roadmap Items > Graph** (`pmb-road-graph-dark.png`): critical path, "done in about 5s", who works on what. Good in dark mode and at phone width (`pmb-road-items-phone-dark.png`).
- **Monochrome Blocks with real notation** (`pmb-job-blocks-open.png`): an engineer can read it, which builds trust even if I don't read it myself.
- **Dark mode** is consistent everywhere I looked.

## 4. Significant changes I would make

### A. Make the closed boxes the control panel, in both views, as the SPEC says *(no new UI; it is the box)*

The data already exists in the module panel. Move it onto the box.

Dynamics (Sterman: a closed module with its stocks as exposed parts, each goal as a goal auxiliary):

```
┌ product ── textkit and its customers ───────────── Open  Into ┐
│ users        216 ▁▂▃▅▆▇ ≥180   holding · ↗ 240 in 15m         │
│ bugs-live      0 ▁▃▁▅▁▁ ≤0     holding (off 20% of the hour)  │
│ missing-ops    0 ▂▁▃▁▂▁ ≤1     holding                        │
└──────────────────────────────── 0 of 3 goals off · 16 loops ─┘
```

Blocks (textbook: a subsystem block whose outputs are y signals): `Q_product` with each output port labelled `y_users = 216 (r ≥ 180)`. The loop status goes in text under the block ("3 loops, 0 off"), not in colour, so the view stays monochrome.

Each row is clickable and opens the existing stock panel. The sidebar's Needs attention can then shrink to a line, because the diagram itself says where the trouble is.

### B. Put ergostat's own upkeep last, and out of the health count *(changes ordering and a count, no new UI)*

- Lay `modelling` out last (bottom right), always closed, drawn with a lighter rule.
- Do not let it stop the user's only system from opening ("alone at its level" ignores `modelling`).
- Header: "0 of 24 loops off" for the user's systems, with modelling's off loops after a separator, in grey ("· model upkeep 2"). On big, the 26 modelling Deny requests go to the Model page's review queue (which already exists) instead of Needs attention.

### C. Say "what to expect" everywhere a goal is shown *(an existing column and an existing menu)*

- On Loops, rename "back in" to an **"expected"** column, filled from the projection the stock panel already computes: "reaches ≥180 in ~6m (p90 9m)", "stays holding (98%)", "goes off in ~4m (60%)". This is the line a PM quotes.
- Tie the projection horizon to the window. Last 1h projects the next 15 minutes and Last 7 days projects the next week. Add "Ahead: 15m / 1h / 1d" to the window menu, which already holds window and moment.
- Rewrite the panel sentence. Instead of "users-growing: off at +4m03s with p≈0.02", write "users-growing: 98% likely to keep holding for the next 4 minutes". Move the method paragraph behind a "how this is worked out" disclosure.

### D. Two kinds of "off" *(a word and a mark in what exists)*

Today an "off" goal that is approaching its setpoint on schedule looks the same as one falling behind. Use the projection and the suggestion engine's own verdict ("keeps up on average" vs "falling behind") to show **"not reached yet, on track"** in neutral text, and reserve red for "falling behind" or "projected to go off". This is the single biggest fix to trust in red.

### E. Lead with the purpose *(text in existing places)*

- The model's `purpose:` sentence goes above the diagram where the view title sits ("software-factory: AI agents build textkit; its customers judge it").
- Guide frame 1 opens on the project's own model with that sentence, not on "You control the knob", with a line saying what ergostat is: "a model of this system, kept honest against what it measures, that says why it behaves as it does and what it will do next".

### F. Approvals a PM won't press by accident *(the existing Inbox controls)*

Each Approve says what will happen in words ("merge PR #7 in example/sample"), asks once ("Approve merge?") and says afterwards who approved it. Remove the CLI pointer from the page. Give the person-block input a unit and a label ("how many did you post?") instead of "how ma".

### G. Items in words *(the existing Items table)*

- Replace the "latest" column of event names with the item's last transition ("shipped 21s ago", "waiting for review 3m").
- Wrap or drop columns at desktop width instead of cutting them.
- Show the process map for a kind at the top of its Items section, as the diagram-options proposal intended, and move the cumulative-flow chart into the stock's causes strip.

### H. Phone: open on the control panel

At 390 px open on the Dynamics diagram with every system closed, with the boxes stacked vertically in the format from change A. Each box is one card's worth of value, setpoint, health and expected. The Loops table on a phone keeps loop, now, setpoint and expected, and drops holds and behaviour.
