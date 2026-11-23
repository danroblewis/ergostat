# ergostat: an information designer's briefed review

Persona: information designer (Tufte, Bertin, Few). This second walk came after reading `intent.md`, `docs/WHY.md`, `docs/DESIGN.md`, `docs/DISCIPLINES.md`, `docs/proposals/diagram-options.md`, `docs/layout-rules.md`, SPEC §4 (systems "drawn as parts") and every demo README. I browsed all six demos again at 1440x900, at 390x844 and in dark mode. The new screenshots are in `<workdir>/design/shots/`, prefixed `infodb-`. Screenshots prefixed `infod-` are from the blind walk.

## What I got right and wrong blind

I had the two notations, the live record, the loops and the approvals right. I had three things wrong:

- **I read it as a pipeline console.** It is broader than that. It models any running system (a job, a product, a platform) as feedback loops. It sits *on top of* the monitoring and ticketing tools a team already has, and it holds the one thing none of them hold: the model that relates them. It is meant for design documents, projections, postmortems and product managers as well as for operators.
- **I wanted richer dashboards, but the owner wants fewer surfaces.** The intended "control panel" is the diagram with every system closed, and each box is supposed to show its measures with value, setpoint, health and trend (SPEC §4, image-squeeze README). My blind finding 2 asked for exactly that. It turns out to be the spec, and the build does not deliver it.
- **The two diagrams are deliberately kept apart**, each in its own discipline's notation. I had suggested mixing status colour freely. Intent says Blocks is monochrome, so status has to be carried differently there (see change C).

## 1. Where it failed to say what it is for

1. **The first screen states no purpose and no verdict.** On every demo the landing is 2 to 7 empty rounded boxes labelled "N feedback loops inside" (`infodb-big-home.png`, `infodb-job-root.png`). The model has a `purpose:` sentence (SPEC §4), and it is never shown. Nothing on the canvas says "this is one engineer's job, as 28 feedback loops, 2 of them off now". The only verdict is in the red "2 loops off" in the header and in a sidebar of prose.
2. **The product's own bookkeeping comes first in every demo.** The `modelling` system (ergostat modelling itself: `requests-handled`, `model-fits`) takes a third to a half of the top level in every demo. Its two loops head "Needs attention" everywhere: on the-job, a newcomer reads "unanswered-requests is 96" before anything about reviews or outages (`infodb-job-root.png`, `infodb-sf-home.png`). The first thing the tool says is about itself.
3. **The boxes are not the control panel the spec describes.** SPEC §4: "its measures: each one's value, setpoint, health and trend … With every system closed, the diagram is the model's control panel." What is drawn is port labels with a bare number ("users 195", "excess bytes-per-mp 42.6"), with no setpoint, no health and no trend. The `modelling` box, which holds both off loops, is drawn empty (`infodb-tf-home.png`, `infodb-is-home.png`, `infodb-sf-home.png`).
4. **The Guide opens on near-nothing.** Slide 1 is "You control the knob. You want the stock." with two words and a rectangle in a 1440 px field (`infodb-job-guide.png`). It does not use the reader's own model, which is loaded and running.

What would have made it obvious, within the decisions (no new pages or panels, two separate diagrams, only recognised types):

- A one-line caption **on the canvas**, drawn from `purpose:` with the verdict: "the-job: a senior engineer's responsibilities, 28 loops, 2 off (reviews-on-time, …)". This is a diagram title, which every published diagram has, and not a new panel.
- Closed boxes that carry their measures as the spec says, so the landing is itself the status overview.
- The `modelling` system drawn last and smaller, outside the user's systems, with its loops sorted below the user's own in attention.
- the-job opening with `job` open, as its README promises ("`job` open, each domain a closed module", `infodb-job-open.png`). It currently opens closed.

## 2. My earlier findings, revisited

| # (blind) | Verdict now | Note |
|---|---|---|
| 1 Process view blank on big | **Stands, worse.** | Still blank (`infodb-big-process.png`). Process is one of only three recognised views, and on the stress demo it fails silently. |
| 2 Landing carries no data | **Stands, worse.** | It contradicts SPEC §4 and the image-squeeze README. This is the core of the intended "control panel". |
| 3 Diagrams don't show off loops | **Stands, worse.** | DESIGN.md says "a loop's lines take its status colour", and nothing in either view does (`infodb-sf-modelling-into.png`, `infodb-sf-modelling-blocks.png`: model-fits is off and drawn like the rest). |
| 4 One number, three names and signs | **Stands.** | Dynamics sidebar: "desired = 0: excess 37". Blocks sidebar: "setpoint ≤ 0 (off by 37)". Loops: "error −37" (`infodb-sf-home.png`, `infodb-sf-blocks.png`, `infodb-dark-sf-loops.png`). Even the Process view's sidebar switches to the Blocks wording. |
| 5 Needs attention mixes kinds, repeats | **Stands, worse at scale.** | Big: 28 items, of which 24 are the same "no-unit" request (`infodb-big-home.png`). Intent decision 6 says large systems matter, and this list does not scale. |
| 6 17 grey states | **Stands, partly a misunderstanding.** | The CFD is a recognised diagram (DISCIPLINES) and should stay. The problem is the encoding: the states that need action (waiting, unmet) get the lightest value and the finished ones the heaviest (`infodb-job-items.png`, `infodb-is-items.png`), and dark mode makes "live" the brightest mass (`infodb-dark-sf-items.png`). |
| 7 Agents rank vs count | **Stands.** | "4 ai" in the strip, then "1 ai" over four AI agents (`infodb-tf-agents.png`). |
| 8 Connector bundles | **Stands.** | `infodb-is-home.png`: about 20 connectors from lab, signs piled at the rollout edge. |
| 9 Label collisions | **Stands.** | "exc(B10)i-q2" again (`infodb-big-api-into.png`). In sf factory-open, B15's name sits on three pipes (`infodb-dark-sf-factory-open.png`). |
| 10 Blocks sparse at top, tiny inside | **Stands, and is a discipline problem.** | Top level on big is seven unconnected "Q_x" boxes in a column (`infodb-big-blocks.png`). That is a list drawn as boxes, not a block diagram. "Q" is undefined and, to a control engineer, suggests IMC's Q-parameter. Inside, `fixer`, `judge` and `improver` are boxes with no function in them (`infodb-sf-modelling-blocks.png`), against the intent's "a function in every block". |
| 11 Off-centre / clipped views | **Stands.** | "More beyond the edge" on sf factory-open and modelling Into. |
| 12 Check page repeated sentences | **Stands, worse.** | sf: 12 of 16 warnings are one 60-word sentence ("not exercised by the record …") with only the part name changing (`infodb-sf-check.png`). |
| 13 Item path as sequence | **Partly fixed.** | The alternative "dropped" is now greyed (`infodb-sf-item.png`), but it is still joined by an arrow. There is still no time strip, and the Items Timeline (a Gantt, per the roadmap README) is not reachable from the item. |
| 14 Sparklines without reference | **Partly a misunderstanding.** | A dashed setpoint line is drawn (`infodb-dark-sf-loops.png`). The per-row scale and the two near-duplicate percentages remain. A new problem: "behaviour: no one process" is unexplained jargon in most rows. |
| 15 Record/Model walls of text | Stands (not re-walked). | |
| 16 Phone loses Loops numbers | **Stands.** | Only loop, status and holds show; "0." is clipped at the right edge (`infodb-phone-sf-loops.png`). |
| 17 Time ranges differ | Stands. | |
| 18 Graph/Timeline look like List | Stands (not re-walked). | |
| 19 Ambiguous values | **Stands.** | "model-error 0.951 1": the unit "1" reads as a second number (`infodb-sf-modelling-into.png`). |
| 20 Schedule edges in process map | Stands (not re-walked). | |

New findings from this walk:

- The loop count disagrees with itself: "Feedback loops 18, 6 Reinforcing, 11 balancing" (`infodb-dark-sf-factory-open.png`).
- Influence connectors leave an opened system as long lines across the drawing. In sf factory-open, the deploy → fixes/shipped/regressions links run up the whole height and across pipes. Rule 1 (flow-excursion) covers pipes but not connectors, and the reader still follows the long line.
- The item page offers "Send a note about this" above the item's facts (`infodb-sf-item.png`). It may be allowed, but it is the first thing on a read-only page and it pushes the history below the fold.

## 3. Where the UI contradicts intent, and what to keep

**Contradictions**

- *"The diagrams can represent almost everything"*, yet the diagrams carry no status, no setpoints and no trends at the levels people look at first. All of it lives in sidebar prose, which is the panel-heavy design the owner wants to avoid.
- *"Each diagram instantly clear to an expert of its discipline"*: a control engineer cannot read the Blocks top level (unconnected Q boxes, slash-3 bus, "1×3") or the agent blocks with no function. An SD modeller reads the Dynamics leaf well, but the closed modules show port lists, not stocks.
- *"Large systems matter"*: the attention list, the Check page and the big Process view all fail first on the large demos.
- *"Systems are namespaced"*: the attention list writes "stock.api-q0" in one place and "api-q0" in another, and "desired level.ci-upgrade-planned" mixes a part kind into a name (`infodb-job-root.png`).
- *the-job README*: it says `job` starts open, and it starts closed.

**Keep**

- The Dynamics leaf notation: clouds, double pipes, bow-tie valves, signed connectors, R/B markers in circular arrows, and "desired X" and "excess X" auxiliaries as goal-seeking structure (`infodb-big-api-into.png`). This is Sterman's notation, done right.
- The Blocks leaf: Σ with signs, r/e/u/y/d named, H(s) = e^{-sT} with its period, P(s) = 1/s for an integrating stock, relay symbols for on/off rules (`infodb-sf-modelling-blocks.png`). It is monochrome and recognisable.
- The loop scope (y, u, e on one time axis with off-bands), the hover dimming, the loop selection that lights the path, the Guide's side-by-side of the two notations, and the shared selection between views.
- The Loops table structure, now with the dashed setpoint in each sparkline.
- The image-squeeze cases chart: "21 unmet / 9 met" is a two-state CFD with direct counts, and it reads at a glance (`infodb-is-cases.png`).

## 4. Significant changes

### A. Make the closed system box the control panel the spec describes

Sketch of one closed box (Dynamics), replacing the port list as the box's body:

```
┌ product ───────────────────── 1 of 3 goals off ─┐
│ users         212  ▕████████████▏▏░░  ≥180  ╱‾‾  │   bullet graph: bar = now, tick = setpoint,
│ bugs-live       0  ▏               ≤0   ___      │   shaded band = tolerance; sparkline at right
│ missing-ops     2  ▕██▏▏           ≤1   _╱‾  ●   │   ● = off (one accent colour + the word "off" in the tooltip)
│ ── ports ──────────────────────────────────────  │
│ ◀ fixes  ◀ shipped  ◀ regressions   ▶ users …    │   ports stay on the edges, names only
└──────────────────────────────────────────────────┘
```

This uses Few's bullet graph (a recognised dashboard primitive, and DESIGN.md's own "meter with the setpoint's tick"), with Tufte's sparkline beside it. It needs no new panel, because it is the box. The header count replaces "N feedback loops inside", which tells the reader nothing about state. A box holding an off goal gets a heavier border, which carries status without colour. On big, seven such boxes would show at once which of the 24 queues is over.

### B. One status channel, used the same way in both diagrams

- **Dynamics:** draw an off loop's R/B marker filled (solid disc, light letter) and its "excess X" auxiliary in the accent colour with its value in bold. Everything else stays black. One hue, used only for "off", is Tufte's "use colour to say one thing".
- **Blocks:** keep the lines monochrome, as the intent requires. Fill the Σ of an off loop and print its e beside it in bold ("e = −37"), the way an engineer annotates a scope. Its r label carries the bound ("r ≤ 0").
- The sidebar's "Needs attention" rows then become **links that select the part** on the diagram, so the reader does not have to translate names by eye.

### C. One vocabulary for "how far off"

Use one phrase everywhere outside the Blocks panel: **"37 over its limit (≤ 0)"** or **"21 short of its goal (≥ 30)"**. That gives the bound as a bound, the magnitude as a positive number and the direction as a word. Keep e = r − y with its sign only in the Blocks view and the scope, where control engineers expect it. Drop "desired X = 0" for one-sided goals, because "=" states a falsehood.

### D. Put ergostat's own `modelling` system in its place

It is a real system, so draw it, but at the boundary: last in reading order, smaller, titled "ergostat (its own model)". Sort its findings after the user's own, under a separate heading. This changes order and emphasis only, not the model.

### E. Turn "Needs attention" into a grouped table

```
Loops off (2)        requests-handled  37 over (≤0)   off 100%  →
                     model-fits        0.9 over (≤0.05)  off 87% →
Asked of you (3)     declare-incident  waiting 4m35s   [Done]
Model requests (24)  no-unit on 24 stocks: api-q0 … web-q3   [Deny all] [list]
Unexplained (2)      in-review −16 · backlog +16
```

Fold identical requests into one row and keep the actions. The header's "N loops off" should equal the first group's count. This changes the existing panel and adds nothing.

### F. Make the Blocks top level a true block diagram

A control engineer expects signals between blocks. At top level, draw each system as one closed-loop block T_x(s) (or "G_x, closed": define the symbol in the existing "How to read it") with its r vector in and y vector out, and draw the real couplings between systems (sf: factory's deploys drive product's flows) as labelled signals. Systems with no coupling (big's six chains) are drawn as parallel rows with their own r and y, which is the standard drawing for decoupled loops, instead of an unconnected column. Every block names its function. For an agent block, write the law it implements: "relay, on while e < 0" for a rule, "sampled, T = 1 min" for a program, "AI: policy p" for an AI agent. The agent's name moves to the small caption above, as the kind badge already does.

### G. Items: encode by meaning, not by order

Keep the CFD. Colour it by phase. States that need someone (waiting, stale, unmet, proposed) get the accent hue, work in progress a mid tone, finished or dropped a light neutral at the bottom. Label each band at its right edge with its count, and hide zero states in a "+6 empty states" note. In dark mode, keep the same lightness order relative to the background, so finished work recedes in both themes. This is Bertin's selective variable, used for the one distinction that matters.

### H. Never draw an empty canvas

When the big Process view, or any view, has nothing to draw, write the reason in the canvas ("no item kinds in big; its parts are counted by sensors, not items") and name the views that do have something.

### I. Turn templated prose into tables

Check page: one table per warning kind (part, readings, R² or "never moved", window), with the advice written once above it. On sf, 12 rows of one sentence become one 12-row table. Do the same for repeated hints in the attention list.

### J. Start the Guide from the reader's own model

Slide 1 should show the reader's own landing control panel (A), with a caption: "Each box is a part of your system. Its rows are what you want held. Red discs are loops that are off." The abstract knob-and-stock slides come after it. This changes the Guide and adds no page.

### K. Phone: one card per loop

At 390 px, show each Loops row as a card: name, status word, "37 over (≤ 0)", and a sparkline the full width of the card. The diagram stays pan-and-zoom, but opens fitted to the box that holds an off loop.

## Screenshots

`infodb-is-home.png`, `infodb-tf-home.png`, `infodb-big-home.png`, `infodb-big-process.png`, `infodb-sf-home.png`, `infodb-job-root.png`, `infodb-job-open.png`, `infodb-sf-product-into.png`, `infodb-sf-blocks.png`, `infodb-big-blocks.png`, `infodb-big-api-into.png`, `infodb-sf-modelling-into.png`, `infodb-sf-modelling-blocks.png`, `infodb-job-guide.png`, `infodb-job-loops.png`, `infodb-job-items.png`, `infodb-is-items.png`, `infodb-is-cases.png`, `infodb-tf-agents.png`, `infodb-sf-check.png`, `infodb-sf-item.png`, `infodb-phone-sf-diagram.png`, `infodb-phone-sf-loops.png`, `infodb-phone-dark-sf-blocks.png`, `infodb-dark-sf-factory-open.png`, `infodb-dark-sf-items.png`, `infodb-dark-sf-loops.png`.
