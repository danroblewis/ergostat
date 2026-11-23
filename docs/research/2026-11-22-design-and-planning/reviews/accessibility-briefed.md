# ergostat: accessibility review, briefed

Reviewer: accessibility specialist (contrast, keyboard use, focus, screen-reader structure, colour-only meaning, motion, text size).

I read `intent.md`, `README.md`, `docs/WHY.md`, `docs/DESIGN.md` §6, `docs/DISCIPLINES.md`, `docs/DECISIONS.md`, `docs/proposals/diagram-options.md` and the six demo READMEs, then walked the demos again: Dynamics and Blocks at the top level and inside a system, a block's definition panel, the side panel's inbox entries, the Guide, Loops and Items. I checked each at 1440x900 and 390x844, in light and dark mode, and probed the DOM with Playwright (focus order, names, roles, rendered text size, colours used in the SVG).

- Screenshots: `<workdir>/design/shots/`. New ones start with `a11yb-`; the ones from the first walk start with `a11y-`.
- Scripts: `<workdir>/design/work/a11yb_*.py`.

## What it is, now that I know

I had the purpose roughly right but drew it too narrowly. I thought it was a console for one "factory". It is meant to be a general **model of any running system as feedback loops**, sitting on top of the monitoring and ticketing tools a team already has. It gives two readings of one model, each in the notation of its own discipline: **Dynamics** (system dynamics, "what is") and **Blocks** (control engineering, "what we control"). People mostly read it. The one place they act is the gated approvals (the "Inbox").

That changes how much my findings weigh. The owner has decided that **the diagram is the interface** ("the diagrams can represent almost everything we want"), with no new pages or panels. So a diagram that only a mouse can use does not lock a keyboard or screen-reader user out of one feature. It locks them out of the product. The other change: **approving or denying is the only thing a person does**, so every barrier on those controls matters more than I rated it.

## 1. Where it failed to tell me what it is for, and what would make it obvious

For a screen-reader user the home page tells nothing. There is no h1. The diagram is one unnamed `<svg>` with no title or description, and nothing in it can take focus (`a11yb-8791-dynamics-light.png`). The first thing such a user hears is a run of headings: "Needs attention", then "Feedback loops 49". For a sighted newcomer the toolbar says "Dynamics | Blocks | Process", but nothing says that these are two named disciplines' diagrams of the same model. Switching views changes the side panel from "Feedback loops 49" to "Loops 16" and from "desired … excess" to "setpoint … off by", with no explanation (`a11yb-8791-blocks-light.png`). That is correct by the discipline rules, but it looks like two different systems.

What would make it obvious, without a new page or panel:

- **Give each diagram a figure caption, as every textbook diagram has**, one line under the view switch. It doubles as the diagram's accessible name and as the page's h1:
  `Stock-and-flow diagram (system dynamics): ticket-factory · 3 systems · 49 feedback loops (R reinforcing, B balancing) · 2 off`
  `Block diagram (control): ticket-factory · 16 control loops · 2 off their setpoint`
  This names the discipline, which is the owner's test ("instantly clear to an expert of its discipline"). It tells a newcomer which notation to read. It gives a screen-reader user the orientation a sighted user gets from the drawing.
- **Label the toggle by what each view answers**, not only by the discipline's name, for example as an `aria-describedby` hint and a tooltip: "Dynamics: what is, and why it moves", "Blocks: what is controlled, and how well".
- **Name the inbox.** The intent calls it the Inbox and says it is the one place people act. On the page it has no name of its own: approvals are mixed into "Needs attention" between "loop off" findings, as entries such as "person/approve@3156" (`a11yb-8792-root.png`). A heading "Asked of you (3)" over the approvals would say in two words what people do here.

## 2. My earlier findings, revisited

| # | Blind finding | Now |
|---|---|---|
| 1 | Diagram mouse-only | **Worse.** The diagram is meant to be the interface, so this locks out the whole product. Blocks' "definition on click" (C(s), P(s), H(s)) can only be reached by mouse (`a11yb-8793-into-service-block-click.png`). Focus also stays on `<body>` after a click. |
| 2 | Loops and Agents rows mouse-only | **Stands.** Today the Loops page is the only text twin of the loops. |
| 3 | Side-panel "Feedback loops" rows mouse-only | **Stands, and matters more.** This list is the natural keyboard route into the diagram. |
| 4 | Items charts in shades of grey | **Partly a misunderstanding.** The monochrome is deliberate ("plain ink: no colour carries meaning"), so the answer is not colour. It is direct labels and patterns. The CFD is also meant to move into a stock's causes strip. The barrier stands (`a11yb-8794-items-graph.png`). |
| 5 | Diagram text tiny | **Stands, and worse in Blocks.** In Blocks the meaning sits in subscripts (y_m,quality, u_tuner, e_k), which render at about 7–8px (`a11yb-8793-into-service-blocks.png`). Inside a system in Dynamics the labels in the boxes are about 8–9px (`a11yb-8791-into-factory-dynamics.png`). |
| 6 | Live updates not announced, rows move under the pointer | **Worse.** The inbox is the one place people act, and it reshuffles itself (4 → 12 → 17 entries between my loads of :8793). |
| 7 | No aria-current or aria-pressed | **Stands, and matters more.** The Dynamics/Blocks switch moves between two disciplines, and a screen reader cannot tell which one is on (only `class="on"`). |
| 8 | Contrast 1.6:1, "Red: off" | **Stands.** The scope in the controller panel marks off periods with pale pink bands and the legend "Red: off" (`a11yb-8793-into-service-block-click.png`). That also breaks Blocks' own monochrome rule. |
| 9 | Nav cut off at 200% zoom and on a phone | **Stands** (`a11yb-8792-loops-dark-phone.png`: "Mode…" fades out). |
| 10 | No h1, tables without headers | **Stands.** I was wrong about one detail: "0 person / 1 ai / 4 program" on /agents are rungs of the ladder (person → ai → narrow-ai → decision → program → rule), not a counting bug. They still read as counts, so the label should say "rung". |
| 11 | Truncated placeholders | **Worse.** These are the gated actions. The deny-reason field comes *after* its Deny button in Tab order, so a keyboard user reaches Deny before typing the reason. Every button is called just "Deny" or "Done", so out of context nobody can tell which request it answers. "How much was done: how many" appears on a "declare an incident?" decision, where a number makes no sense. |
| 12 | Small targets | **Stands.** |
| 13 | Identical links ("process, controller, scope", "Evidence") | **Stands.** |
| 14 | Symbol-only buttons, "Sort by by" | **Stands.** |
| 15 | Check page is a wall of grey prose | **Stands.** |
| 16 | Labels overlap | **Stands, and is part of a larger problem.** At the top level of Dynamics the link-polarity signs (+/−), the key notation of system dynamics, are drawn as clusters of 11–13px glyphs stacked at the arrowheads, where nobody can tell which sign belongs to which link (`a11yb-8793-dynamics-light.png`, `a11yb-8791-into-factory-dynamics.png`). |
| 17 | Red versus amber only in "Needs attention" | **Stands.** |
| — | "Console for a factory" | **Misunderstanding.** The factory is one demo; the product models any running system. |

## 3. Where the UI contradicts the intent, and what to keep

Contradictions:

- **"The diagram is the interface" and "the diagram is mouse-only" cannot both hold.** As built, every user who cannot use a mouse needs exactly the extra pages the owner wants to remove (Loops, Agents).
- **Blocks is monochrome, and its scope is not.** The off periods in the controller panel are shown only by a red tint with "Red: off". Control texts mark such a period with a shaded band *and* a label.
- **"Each diagram clear to an expert of its discipline":** link polarity is unreadable at the top level and inside systems. An SD expert cannot check a loop's sign, and a low-vision user cannot either.
- **"Read-only, except the gated actions":** the gated actions are the least labelled controls on the page (truncated placeholders, generic button names, reason after Deny, raw CLI text in backticks such as "`ergostat actions` lists them").
- **"Large systems matter":** at the size the owner works at, labels fall to 7–9px and run into each other. "More beyond the edge" is the right idea, but the default fit still shrinks text below what can be read.

Keep:

- **MathML in the definition panels.** C_tuner(z) = 350z/(z−1), P(s), H(s) and the matrices are real `<math>` (`a11yb-8793-deadband-panel.png`). Screen readers can speak and navigate this, which is rare and excellent. Give each one `alttext` as a fallback.
- **Blocks is genuinely monochrome and shape-coded.** Summing junctions with ± signs, ZOH and sampler symbols, dead-band glyph, a selection shown by outline (`a11yb-8793-service-blocks-dark.png`). Shape carries meaning, so it is colour-blind safe.
- **Agent badges lettered as well as coloured** (H, A, N, D, P, R: DESIGN §6, "colour is never the only cue"). Apply the same rule everywhere.
- **The side panel's change of vocabulary by view** ("excess" in Dynamics, "setpoint … off by" in Blocks) is correct. It needs the caption above to explain it.
- **"More beyond the edge"** instead of shrinking everything; keyboard focus ring; Escape closes the panel; dark mode complete; the Guide's arrow-key steps.

## 4. Significant changes I would make

### A. Make each diagram keyboard-navigable in its own discipline's reading order (no new view)

The diagram should be the accessible structure, not a picture beside it. Use one roving tab stop per diagram (`role="application"` with `aria-roledescription="stock-and-flow diagram"` or "block diagram"), and let arrow keys follow the lines the discipline reads along:

```
Dynamics (focus on a stock)
  Tab        -> the diagram; focus lands on the first stock that is off
  Right/Left -> along the pipe: downstream flow / upstream flow (valve, cloud)
  Up/Down    -> along information links (connectors), announcing polarity
  L          -> cycle through the feedback loops this part is in (B2, B36, R12)
  Enter      -> opens its definition in the side panel, focus moves there
  I / Esc    -> Into the system / back out
  Announced: "Stock bytes-per-mp, 52.8 KB per MP, desired 20, excess 32.8, off.
              Inflow bytes-turnover −1.01 per minute. In loops B2 and B36."
Blocks (focus on a block)
  Right/Left -> along the signal: r -> Σ -> sampler -> dead band -> C_tuner(z) -> ZOH -> P
  Down       -> into the feedback path (H(s) sensor), Up -> back to the forward path
  Announced: "Controller C tuner of z, equals 350 z over z minus 1. Input e k from dead band.
              Output u k to ZOH. Loop quality-held, off 50 % of the hour."
```

This is the screen-reader equivalent of reading the figure the way an expert does, and it adds nothing to the screen. The "Feedback loops" and "Loops" lists in the side panel become the entry points: each row is a button that focuses its loop's first part in the diagram.

### B. A caption line that names the figure, which is also the h1 and the SVG's name

Section 1 above has the text. It replaces nothing and adds one line. It answers "what is this?" for every user, and it carries the live count ("2 off") that a screen reader can be told about.

### C. Split "Needs attention" into the Inbox and the findings, and make the Inbox calm and fully labelled

```
Asked of you (3)                               <- h2, aria-live="polite" (count only)
  ┌───────────────────────────────────────────┐
  │ Approve: comment on PR #412 (ticket-…)    │  <- h3: the request in words, not "person/approve@3156"
  │ Waiting 11 min · asked 11× this week      │
  │ Reason (required to deny) [____________]  │  <- visible label, before the buttons
  │ [Approve this comment]  [Deny this comment]│  <- names say what they answer
  └───────────────────────────────────────────┘
What is off (2)  ·  Suggestions (2)            <- the findings, below, unchanged in kind
```

Order stays fixed while focus or the pointer is inside the box. New requests are announced as "1 new request", never by moving the one being read. Raw CLI text is left out of the entry. A person task whose answer is yes/no gets yes/no buttons, not "how many".

### D. No meaning by colour alone, in any of the three places it still happens

- Scope charts: hatch the off periods and put an "off" tick label on the time axis. Replace "Red: off" with a hatched swatch labelled "off".
- Needs-attention names: put the state word in front, as /loops does: "off · loop requests-handled", "unknown · loop model-fits".
- Items CFD: label each band directly at its right edge ("done 317", "leased 1"). Merge rare states into "other". When the proposal is built, move the chart into the stock's causes strip.

### E. A floor on text size, with panning instead of shrinking

Never fit a diagram below a 12px label (11px for subscripts, which then render as 9–10px). On a phone, open the drawing at that floor centred on the first off part, with "More beyond the edge" pointing the way. Draw link-polarity signs at 14px, offset along the link from the arrowhead and spaced apart, so each sign sits on its own link. This is Sterman's own convention, and it fixes legibility and correctness together.

### F. Fewer top-level pages, so the navigation fits at 200% zoom and on a phone

Within decision 1, which allows merging, the pages could be cut from eight to five:

- Agents into the Blocks view: an agent is the block's badge, and its runs, log and cost belong in that block's panel.
- Check into Model: both answer "is the model right?".
- Record into the Items page or the item's own page: an event is about an item.

That leaves Diagram, Loops, Items, Model and Guide. These fit on one line at 390px and at 200% zoom with no "More" menu. A keyboard user has fewer stops, and a newcomer gets a clearer story.

### G. Small structural fixes that cost little

- `aria-current="page"` on the nav and `aria-pressed` on the view toggles.
- Make the side panel an `<aside aria-label="…">`: today it is a `div.side` inside `main`.
- Move focus into the panel on open and back to the part on close.
- `alttext` on the MathML.
- On /agents, "rung 0: person" instead of "0 person".
- Give the matrix in the process panel a horizontal scroll container: today it is cut off at the panel's edge (`a11yb-8793-deadband-panel.png`).

## Revised findings (worst first)

The structured result returned with this review holds the full list. In summary:

1. **Blocker:** diagrams mouse-only (both views; the definitions too).
2. **Blocker:** Loops and Agents rows mouse-only.
3. **Major:** inbox controls: reason after Deny, generic names, truncated labels, a "how many" on a yes/no decision.
4. **Major:** live inbox reshuffles and is not announced.
5. **Major:** no h1 or diagram name, and the purpose and discipline are never stated.
6. **Major:** text below 9px in Blocks subscripts and in Dynamics system boxes; overlapping polarity signs.
7. **Major:** colour-only "off" in scopes, red/amber in Needs attention, grey CFD bands.
8. **Major:** view toggles and nav without state.
9. **Major:** nav cut off at 200% zoom and on a phone.
10. **Major:** side-panel loop rows mouse-only.
11. **Major:** contrast 1.6:1 on future states, tier arrows and Guide dots.
12. **Minor:** process matrix overflows its panel.
13. **Minor:** the side panel is not a landmark.
14. **Minor:** small targets.
15. **Minor:** identical link names.
16. **Minor:** symbol-only buttons and "Sort by by".
17. **Minor:** Check page prose.
18. **Minor:** "Feedback loops 49" versus "Loops 16" unexplained.
19. **Polish:** tier labels read as counts.
20. **Polish:** CLI text in the UI.
