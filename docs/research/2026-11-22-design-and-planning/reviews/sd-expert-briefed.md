# ergostat, reviewed again by a system dynamics modeller, after reading the intent

Persona: SD modeller (Sterman, Vensim, Stella). First read: `reviews/sd-expert-blind.md`. Then I read
`intent.md`, `ergostat/docs/WHY.md`, `CONCEPTS.md`, `DISCIPLINES.md`, `vocabulary.md`,
`layout-rules.md`, `proposals/diagram-options.md`, `DECISIONS.md`, and every demo README. I walked the
demos again at 1440x900, at 390x844 and in dark mode. The new screenshots are `shots/sdxb-*.png`. The
blind ones are `shots/sdx-*.png`.

## 0. What my blind reading got right and wrong

I was mostly right. ergostat is a running model of a socio-technical system. It is drawn two ways, it
is fed by live events and metrics, and it runs agents when a goal is off. I was wrong on three counts:

- **The audience.** It is not only an operator's console. The owner wants the model itself to be the
  product: something that goes into design docs, proposals, postmortems and capacity plans, for SREs
  and for product managers. That raises the bar for the Dynamics diagram. It has to explain the
  system on its own, the way the figures in Sterman's book do, and not only report it.
- **The word "loop".** In ergostat, "loop" means a goal plus the control path that serves it (vocabulary:
  "A goal-seeking loop | Balancing loop | Negative feedback loop | **Loop (holding, off)**"). That is
  deliberate, and it is why `/loops` has setpoints. The clash is real (see F4), but it is a naming
  decision, not confusion in the code.
- **`model-error` as a stock.** This follows the owner's rule "prefer modelling an idea (a measure as
  a stock) over new UI". The intent is fine. The SD form is still wrong (F8).

## 1. Where the application fails to say what it is for

1. **The first screen is three closed boxes and a list of numbers** (`sdxb-8796-home.png`,
   `sdxb-8791-home.png`). Nothing on it says "this system has 8 goals, 2 are off, and these feedback
   loops couple them". The opening figure of any SD study is an overview causal-loop diagram with
   three to five named loops. Here the reader gets modules, port names and "18 feedback loops inside".
2. **The goals, ergostat's central idea, are missing from the Dynamics diagram wherever no block in
   the same system acts on them.** On `big` they are drawn properly (`desired api-q0 -(-)-> excess
   api-q0 <-(+)- api-q0`, `sdxb-8797-api.png`). On `software-factory/product` the goals
   `no-live-bugs`, `few-missing` and `users-growing` are drawn nowhere, though they are the reason the
   product exists in the model (`sdxb-8796-product.png`). A newcomer cannot see what is wanted, so
   cannot see what the loops are for.
3. **The side panel speaks control in the SD view.** "loop requests-handled ... desired ... excess 37"
   in Dynamics, and "controller requests-handled ... setpoint ≤ 0 (off by 37)" in Blocks
   (`sdxb-8796-blocks.png`). The Blocks wording is translated properly. The Dynamics wording names a
   goal "loop", in the same panel that lists "Feedback loops 18 — R2, R3...".
4. **The Guide's payoff slide ("Your system, both ways") draws the SD half as black slabs with black
   text in light mode** (`sdxb-guide-13.png`). The one slide that should connect the teaching to the
   reader's own system fails visibly.

Within the owner's rules (no new pages, two pure diagrams, recognised types only), these would make it
obvious:

- **Dynamics at "Everything" = an overview stock-and-flow diagram at module level, with the goals
  exposed as ports** (each module shows `desired X / gap X` for its goals) and **the named
  cross-module loops drawn as R/B markers between the modules**. This is Vensim's "view per sector"
  practice and Stella's module map, so it is a recognised type, not a new page.
- **Every goal is drawn as goal-seeking structure in the system it belongs to**, whether or not
  anything acts on it. A goal with no connector leaving its gap *is* the "missing feedback" finding,
  drawn the SD way.
- **One sentence above the diagram, generated from the model** (the diagram's own caption, not a
  panel): "software-factory: 3 systems, 8 goals (2 off), 5 reinforcing and 13 balancing loops; the
  product's goals are served only through the factory."

## 2. Earlier findings: what stands, what was a misunderstanding, what is worse

| Blind | Now | Why |
|---|---|---|
| F1 R/B with unsigned links | **Stands, worse** | R3 still: 10 of 14 links unsigned yet "Reinforcing" (`sdxb-8796-R3.png`). Most of those links have a sign *by definition* (inflow → stock +, stock → its gap +, gap → the flow serving it +). Leaving them blank hides polarity the tool must already know, in a product the owner wants experts to trust on sight. |
| F2 fit loses to the mean | **Stands, partly a misunderstanding** | Some demos had restarted (17–20 min of record), and the Model page does say why estimates are held (record too short against the time constants; autocorrelated errors). But the diagram still shows nothing about validity: the churn valve (skill −0.11) looks the same as a good one. |
| F3 calibration prose | **Partly a misunderstanding, partly stands** | "Too little record: spans 14m, under 3 time constants (24m)" is a fair identifiability argument. "Nothing says the value written is wrong" is still false when 0.373 ± 0.13 sits about 13 SE from the declared 2. Say "the record so far rejects 2 but cannot yet settle a value". |
| F4 "loop" means two things | **Stands, but it is a naming decision** | It is deliberate (vocabulary.md), so the fix is a rename, not a new concept. The `big` demo shows the bridge already: SD loops are named after their goal (`B8 api-q0-low`). |
| F5 conservation residuals | **Stands** | Still "changed −0.0403, the known flows explain −0.0504: 0.0101 unexplained", with no unit, no window and no mark on the diagram. CONCEPTS says "what the known flows cannot explain is shown as a residual", but it is shown only in the side panel. |
| F6 label / loop-marker collisions | **Stands, worse** | The owner names large systems as a priority (decision 6). Product, api and web still overprint (`sdxb-8796-product.png`, `sdxb-8797-api.png`: B10 on "excess api-q2", B9's name struck through by a pipe). |
| F7 too many machine-named loops | **Stands, worse** | 16 of product's 18 loops are named "all-live via ...". They are enumerated elementary cycles, so the loops that matter cannot be told apart. This defeats the WHY ("explaining systems coherently"). |
| F8 fit statistic as a stock | **Stands, intent understood** | The owner prefers a measure as a stock. An SD expert still reads a stock as an accumulation. Keep the rule but apply it SD-correctly (see S6). |
| F9 two numbers for one flow | **Stands** | users: header 12.4/min and table 17.3/min; churn: 9.18 and 5.59 (`sdxb-8796-users.png`, `sdxb-8796-churn.png`). |
| F10 units | **Stands, worse** | On `big`, 24 "holds no-unit" requests fill the attention panel with Deny boxes (`sdxb-8797-api.png`). A units-check failure has been turned into human approvals. |
| F11 "nothing acts on its gap" | **Stands, worse** | The software-factory README says "each of its goals closes a loop ... through every queue in the factory". The users panel says "no feedback closes it", while the stock is in 13 loops and `/loops` judges `users-growing` (`sdxb-8796-users.png`, `sdxb-8796-loops.png`). The tool contradicts its own demo's design. |
| F12 long pipes | **Stands** | The owner's layout rules 1, 4 and 5 already say it. The q2 → q3 pipe on `big` still runs around the edge. |
| F13 flow values "−" | **Stands** | regressions, fixes, shipped and asks still show "−". |
| F14 raw ids in loop table | **Stands** | `stock:awaiting-deploy`, `gap:all-live`. |
| F15 Guide | **Partly a misunderstanding** | The slide 7 "B dominates" decay toward 0 is correct for churn with goal 0. Slide 13 now renders, but it is broken in a new way (black slabs, §1.4). |
| F16 XMILE export | **Stands, now in the intent** | DISCIPLINES lists XMILE as possible. It adds no page (one item in the existing Export menu) and is the strongest credibility signal for SD readers. |
| F17 no equation listing | **Stands, adjusted** | Not as a new page: put it in Export ("Equations (.txt / .xmile)"). |
| F18 Fit leaves the drawing small | Stands (minor) | |
| F19 phone | **Mostly a misunderstanding** | On a phone the home opens on Loops (`sdxb-8791-phone-home-dark.png`), which is the right glance view. The diagram is a cut-off window (`sdxb-8796-phone-product-dark.png`), and the Loops table still hides setpoint and error (`sdxb-8796-phone-loops.png`). |
| F20 shadow conventions | Stands (polish) | |
| F21 console errors | Stands | ELK "reading 'Sg'" and ShapeConnectionPin errors still appear on 8791 and 8797. |

New: the Feedback loops count at "Everything" disagrees with the sum of its modules (software-factory:
34 against 11 + 18 + 18; `sdxb-8796-home.png`), because loops that cross modules are counted in each.

## 3. Where the UI contradicts the intent, and what to keep

Contradictions:

- **Decision 2 ("a goal is a goal-seeking auxiliary" in Dynamics):** goals are invisible in product,
  and the Dynamics side panel uses control words ("loop ... off"). The Model page's "Loops" table
  ("u → y, process") also lives outside the Blocks view's vocabulary boundary.
- **"Each diagram instantly clear and obvious to an expert":** 18 overprinted loop markers named by
  path is not what an SD expert reads anywhere else. Sterman's figures name loops by their mechanism.
- **"Explaining systems coherently, in design docs":** Export gives SVG and PNG of a cluttered
  diagram, with no equations and no XMILE.
- **"Read-only, a few gated actions":** units-missing requests from the modelling tier appear as
  per-stock approvals. That is not wrong, but 24 of them bury the two goals that are really off.

Keep:

- Correct SD notation: boxes, double pipes, bow-tie valves, clouds, connector polarity, R/B markers
  with direction, and the `desired → excess` goal structure on `big` (`sdxb-8797-web-dark.png`).
- Loop highlight on click: the rest dims and the path is traced (`sdxb-8796-R3.png`). This is the best
  SD interaction in the product.
- The causes strip: stock with desired level, inflow and outflow on one time axis, replay dashed and
  projection lighter (`sdxb-8796-users.png`). This is exactly a behaviour-over-time graph.
- The honest modelling prose: identifiability against time constants, autocorrelated residuals, "quiet
  is not absent", and the "What ergostat can propose" list (DELAY3 from coloured residuals, ZIDZ
  guards, Little's law). This is real SD craft.
- The per-view translation of the attention panel (Blocks says controller/setpoint). Finish it for
  Dynamics.
- SD loops named after their goal on `big` (`B8 api-q0-low`): the bridge between the two disciplines.
- The Guide's SD slides (stock, flow, R/B, dominance) are textbook-correct and well drawn
  (`sdxb-guide-07.png`).
- Dark mode is clean everywhere I looked.

## 4. Significant changes I would make

Annotated sketch: `shots/sdxb-annotated-product.png`.

**S1. Loops that matter, named by mechanism; the rest folded (Dynamics).** Keep the full enumeration
for analysis, but draw only the loops the owner or the modelling tier has *named*, plus at most one
unnamed loop per goal (the shortest through its gap). Number the others in the side list only. Name a
loop on the diagram by its mechanism ("Quality erosion", "Feature pull", "Word of mouth", "Churn"),
and keep "all-live via regressions and churn" as its path, shown in its panel. Loop names are a
modelling act (`loops: {quality-erosion: {through: [regressions, bugs-live, churn]}}`). This is how
Sterman, Senge and every Vensim model present loops. On product it cuts 18 markers to about 5 and
removes most of F6 without layout work.

**S2. Every goal drawn as goal-seeking structure, always (Dynamics).** In the system that owns the
goal, draw `desired users (≥180) —(−)→ users gap ←(+)— users`. When the controller is in another
system, the gap's connector leaves through a module port ("→ factory: product-manager"). When nothing
serves the goal, the gap has no outgoing connector and carries a small "no feedback" mark. Missing
feedback becomes visible structure, which is ergostat's core claim, and F11 disappears because the
panel can only say what is drawn.

**S3. One word per discipline.** In Dynamics and its panels, a goal is a **goal** with a **gap**
("goal users-growing: gap 0, holding"), and **loop** means only an R/B feedback loop. In Blocks, the
side list and `/loops` keep "loop" (control usage) or, better, rename the page **Goals**, whose rows
link "served by B12 / B24 in Dynamics, controller C_pm in Blocks". The header becomes "2 goals off".
This renames things and adds no page.

**S4. Validity drawn on the diagram, not on another page.** A flow whose equation loses to its mean
gets a hatched valve and its value shown as "5.6 ?". A stock with a conservation residual gets a dashed
border and a small leak glyph with "±0.01 /15 min unexplained". A loop whose sign rests on an
undeclared link gets "?" in place of R/B. A link with a definitional sign shows it. The Check and Model
pages stay as the detail. On the diagram, an SD expert sees at a glance which structure is trusted. It
is the SD analogue of the Blocks view's "identified / best guess".

**S5. One rate per flow, with its window.** Each flow shows one number, the mean over the selected
window (the header's "Last 1h"). The causes strip's header shows "now" values labelled "now" (latest
bucket). The two tables that disagree today are merged.

**S6. A measure as a stock, done the SD way.** Keep the owner's rule, but model what accumulates.
For model quality, the stock is **open model gaps** (unexplained residuals, failed checks), filled by
`gaps-found` and drained by `changes-accepted`; `model-error` becomes an auxiliary computed from the
replay, whose goal `desired model-error 0.05` drives the gap. The change pipeline
(pending-changes → changes-testing → passed-changes) is already a correct aging chain. It should be the
stock chain that the goal acts on.

**S7. Export what an SD modeller can audit.** Export menu: "Model (XMILE)" and "Equations (text)": each
variable with its equation, units, source (declared, calibrated, measured) and documentation, with
loops listed with polarity. No page is added, and it is the most persuasive thing ergostat can hand an
SD reviewer or put in a design doc.

**S8. Units as a model error, one time unit per model.** A stock without a unit is a Check error
shown on the diagram (unit "?" under the value), and not 24 approvals. Rates display in the model's
time unit (per hour, say), with the stock's own unit per that time, and the dimensionless "1" is
hidden.

**S9. Layout: treat loop markers and labels as obstacles, and shorten pipes.** These are already the
owner's layout rules 1, 4 and 5. Add a rule that loop markers and loop names never overlap a part's
name or a pipe, and enforce it in the corpus. Together with S1 this makes product and `big` readable.

**S10. Fix the Guide's last slide**, and let it show the reader's *named* loops (S1) and goals (S2), so
the tour ends on "here are your 4 loops and 8 goals", not a black thumbnail.
