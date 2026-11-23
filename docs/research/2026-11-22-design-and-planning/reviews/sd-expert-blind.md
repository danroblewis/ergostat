# ergostat, reviewed blind by a system dynamics modeller

Reviewer persona: SD modeller (Sterman / Vensim / Stella habits). I used only the running demos
(:8791 ticket-factory, :8796 software-factory, :8797 big, plus the home pages of :8792, :8793, :8794),
at 1440x900, at 390x844 and in dark mode. Screenshots are in `../shots/`, all prefixed `sdx-`.

## 1. What I think this is (written before judging)

ergostat is a live **operations console for a running socio-technical system** (a software or ticket
"factory" worked by programs, AI agents and people). It draws that system two ways:

- a **stock-and-flow model** (Dynamics view) whose stocks and flows are *measured live* from events
  (tickets, PRs, users, queues), with equations, parameters, calibration, replay and projection, loop
  detection (R/B numbering), loop dominance, mass-balance checks and "extreme conditions" checks;
- a **control-engineering block diagram** (Blocks view: controller C, process P(s), sensor H, setpoints),
  where each "loop" is a regulator holding a stock at a setpoint, with on/off controllers and
  identification (integrator, dead time, SIMC tuning).

There is also a process-mining view (Process), an event log (Record), a model-quality page (Model),
a lint page (Check) and a 13-slide Guide teaching SD then control. A side panel ("Needs attention")
lists loops that are off setpoint and approvals waiting for a human (Approve / Deny Jira and GitHub
actions).

Who it is for: an engineering lead or operator who runs an automated delivery pipeline and wants to
see, steer and approve it, with SD and control theory as the lenses. It is *not* a modelling tool in
the Vensim sense: the model is mostly declared in YAML files (the Check page cites `oversight.yaml:173`
etc.) and fitted to live telemetry; the UI lets you inspect, what-if parameters and approve proposals,
not draw. Confidence: medium-high on the "live ops console with SD+control lenses" reading; medium on
who exactly authors the model (it seems to be partly the owner in YAML, partly a "modelling" subsystem
that proposes changes).

As an SD modeller, I came to: read the stock-and-flow structure, check loop polarity and conventions,
check units and conservation, see whether the model reproduces behaviour, and try a what-if.

## 2. Findings, worst first

### F1 (blocker). Loops are classified R/B while their link polarities are unknown
- Page: `/diagram?view=dynamics&system=modelling` (8791), valve `tests-started`; and
  `/diagram?view=dynamics&system=product` (8796), loop R3.
- Saw: the `tests-started` inspector lists its inputs as `changes-testing (?)`, `pending-changes (?)`
  and its equation as "a declared cause with a sign, its size not estimated", yet it is said to be in
  five *balancing* loops (B19, B38, B39, B40, B41), and the B40 panel lists `pending-changes ->
  tests-started` as `+`. The R3 panel ("Reinforcing by the signs of its links in the model") shows
  10 of its 14 links with **no sign at all**, and says not all of them are drawn in this view.
- Why it matters: loop polarity is the product of link polarities. If the UI itself says a sign is
  unknown, calling the loop B or R is unsupported, and two panels contradict each other about the
  same link. This is the first thing an SD reviewer checks, and it undermines trust in every R/B label.
- Suggest: when any link in a loop is unsigned, mark the loop "?" (Vensim/Stella practice is to
  leave it unlabelled), show the sign column for every row, and never show `(?)` in one panel and `+`
  in another for the same link.
- Screenshots: `shots/sdx-8791-gap.png` (tests-started panel), `shots/sdx-8791-modelling-fit.png`
  (B40 table), `shots/sdx-8796-loop-R3.png`.

### F2 (major). The model does not reproduce behaviour, and the UI still presents it as the system's structure
- Page: `/check` (8791, 17 warnings), churn panel on `/diagram?...system=product` (8796), `/model`.
- Saw: on 8791 every machine flow (address, ask-review, ci, close, fix-ci, locate, merge, open-pr,
  pick-up, review, sail, work...) "fits its record worse than holding it at its mean" (R² 0.00-0.14).
  `churn` on 8796: R² 0.10, skill -0.56. `model-error` (the system's own fit score) reads 0.27-1.26
  on 8791, 0.93 on 8796 and **15.5** on 8792 against a goal of 0.05. Many flows/stocks on 8797 are
  "not exercised by the record".
- Why it matters: a model that loses to a constant has not passed the most basic behaviour
  reproduction test (Sterman ch. 21). The Dynamics diagram still shows equations, loop dominance
  and 2-3 minute projections with a confident look; the warnings live on another page. I could not
  find one place that shows "simulated vs actual" for the whole model.
- Suggest: put a model-validity badge on the diagram itself (and grey out / hatch flows whose
  equations lose to the mean), and add one behaviour-reproduction page: each stock's replay over its
  record, with fit statistics (Theil decomposition would be what an SD reviewer expects).
- Screenshots: `shots/sdx-8791-check.png`, `shots/sdx-8796-churn-whatif.png`,
  `shots/sdx-8792-home.png` (model-error 15.5).

### F3 (major). Calibration text contradicts its own numbers
- Page: churn panel, `/diagram?view=dynamics&system=product` (8796); also `/model`.
- Saw: `churn-per-failing-op` declared 2 1/op/h; calibrated estimate **0.404 ± 0.116** (n=106), i.e.
  the declared value is about 14 standard errors away. The text says "not proposed: held,
  inconclusive ... Nothing says the value written is wrong". Also `base-churn = 2.4 1/h` means every
  user churns 2.4 times an hour (mean lifetime 25 min), which is implausible on its face.
- Why it matters: an SD modeller reads the interval and concludes the declared value *is* wrong. Saying
  the opposite in prose makes the tool look like it is ignoring its own evidence. Implausible
  parameter values are an extreme-conditions/face-validity failure the Check page does not raise.
- Suggest: distinguish "not enough record to identify" from "the record rejects the declared value";
  add a plausibility check on fractional rates (residence time = 1/fraction).
- Screenshot: `shots/sdx-8796-churn-whatif.png`.

### F4 (major). Two different things are both called "loop"
- Page: `/loops` vs `/diagram` (all demos).
- Saw: the diagram says "Feedback loops 49" (R/B loops found in the structure, B3...B41); the Loops
  page lists 16 named regulators (`requests-handled`, `picked-located`...) with setpoint, error,
  "time off" and "back in". Some share a name with an SD loop (B40 "model-fits"), most do not.
  The header says "3 loops off".
- Why it matters: for an SD reader a loop is a closed causal path with a polarity; it cannot be "off"
  or have a setpoint. The control meaning (a regulator/goal) is legitimate but must be named
  differently, or every page needs translation.
- Suggest: call the Loops page "Goals" or "Control loops" consistently, and in the SD view mark which
  B-loop implements which goal (e.g. "B40 implements goal model-fits").
- Screenshots: `shots/sdx-8791-loops.png`, `shots/sdx-8791-home.png`.

### F5 (major). Conservation failures are flagged but not explained or shown on the diagram
- Page: side panel on `/diagram` (8791, 8796, 8794).
- Saw: "stock pr-open changed 0, the known flows explain -71: 71 unexplained", "stock review-asked
  changed 0, the known flows explain 142: -142 unexplained", "stock epics-underway changed 1, the
  known flows explain -32: 33 unexplained", "stock in-review ... 16 unexplained".
- Why it matters: good that ergostat checks stock = integral of flows (most tools do not). But the
  numbers are large, unsigned in a confusing way ("explain 142: -142 unexplained"), have no units and
  no time window, and the diagram shows these stocks as ordinary, trustworthy boxes.
- Suggest: show the balance as `delta stock = inflows - outflows + residual` with units and window, and
  mark the affected stock on the diagram (e.g. a dashed border or a "leak" glyph).
- Screenshots: `shots/sdx-8791-stock-model-error.png` (panel text), `shots/sdx-8796-home.png`,
  `shots/sdx-8794-home.png`.

### F6 (major). Label and loop-marker collisions make the larger stock-and-flow views unreadable
- Page: `/diagram?view=dynamics&system=product` (8796), `/diagram?...system=api` and `web` (8797),
  `/diagram?view=dynamics&around=flow/tests-started` (8791).
- Saw: in product, R2 and R3 loop names print on top of each other ("all-live via regressions and
  churn" over "all-live via regressions and filed-bugs"); B11/B12/B24 markers and their names overlap;
  B25's name covers the `users` stock's value ("146 users" cut off). In 8797 the B10/B30 markers sit
  on the "excess api-q2"/"excess web-q2" auxiliary names; B9's name is drawn across a pipe. In the
  tests-started neighbourhood, B18's name is struck through by a pipe.
- Why it matters: SD diagrams are read by tracing loops; a loop marker that hides the variable it
  passes through, or names that overprint, defeats the purpose.
- Suggest: treat loop markers and labels as obstacles in layout; in crowded views show only the
  marker (B11) and the name on hover/selection.
- Screenshots: `shots/sdx-8796-product-zoom.png`, `shots/sdx-8796-product.png`,
  `shots/sdx-8797-api.png`, `shots/sdx-8797-web.png`, `shots/sdx-8791-around-tests-started.png`.

### F7 (major). Too many enumerated loops, with machine-generated names
- Page: product (8796) sidebar "Feedback loops 18"; modelling (8791) 11; ticket-factory total 49.
- Saw: loops named "all-live via regressions and signups and asks" (16 parts), "all-live via fixes
  and churn and asks", "B38 +1", "B1 +1", "B38 +2"; trivial first-order drain loops (stock -> its own
  outflow, "B8 model-error", "B3 changes-testing") are numbered and drawn alongside the big ones.
- Why it matters: SD practice is to name a handful of *meaningful* loops (Sterman: "Word of mouth",
  "Saturation") and suppress the minor drain loops. Enumerating every elementary cycle buries the story.
  The "+1"/"+2" suffix next to a loop marker reads like a gain or a polarity; I learnt only from a
  panel that it means "1 more loop drawn alike".
- Suggest: hide stock-drain loops by default; let the owner name loops; replace "+1" with a stacked
  marker or "(2 loops)".
- Screenshots: `shots/sdx-8796-churn.png` (sidebar list), `shots/sdx-8791-loop-B38.png`,
  `shots/sdx-8796-product-zoom.png`.

### F8 (major). A fit statistic is modelled as a stock
- Page: `/diagram?view=dynamics&system=modelling` (8791 and every demo).
- Saw: `model-error` ("the scaled error of the model's replay on the record") is a stock with an
  inflow `model-drift` and an outflow `model-mended`, unit `1`. Its inflow is "measured as every rise".
- Why it matters: an error statistic is an instantaneous function of the model and the data, not an
  accumulation; it has no physical inflow. Drawing it as a stock teaches the wrong habit (the very
  thing the Guide's slide 3 explains: "a stock fills through its inflow").
- Suggest: draw it as an auxiliary (or an information stock only if the remediation backlog is the
  stock) and let the change pipeline (pending-changes -> accepted-changes) be the real stock chain.
- Screenshot: `shots/sdx-8791-modelling-dark.png`, `shots/sdx-8791-stock-model-error.png`.

### F9 (major). Inconsistent numbers for the same flow in one panel
- Page: users stock and churn valve, `/diagram?...system=product` (8796).
- Saw: users panel: chart header "signups 22.8 users/min, churn 6.51 users/min"; table below
  "Inflow 17.3/min, Outflow 3.63/min". churn panel: "rate ... 5.53 users/min" vs "Rate, over the
  window 3.96 users/min"; diagram shows 3.96.
- Why it matters: I cannot tell which number is the flow. One is probably the latest bucket and the
  other a window average, but neither is labelled as such.
- Suggest: label each ("now, last 15 s" vs "mean over last 1h") or show one.
- Screenshots: `shots/sdx-8796-users.png`, `shots/sdx-8796-churn.png`.

### F10 (major). Units are missing or inconsistent
- Page: 8797 api/web, 8791 modelling, 8796 product, stock inspectors.
- Saw: 8797 stocks have no unit (24 "holds no-unit" requests in Needs attention), yet their flows are
  "/min"; `model-error 0.274 1` prints the dimensionless unit `1` after the number, reading as two
  numbers; stock inspector shows "Inflow 18.1/day, Outflow 0/h" side by side; flows switch between
  1/h, 1/day, /min, tickets/h, tickets/min in the same view (factory module ports: "address 1.98
  tickets/min", "fix-ci 41.4 tickets/h"); `bugs-live` and `missing-ops` are measured in "ops".
- Why it matters: units consistency is the cheapest validity test in SD (Vensim's Units Check). A
  stock-and-flow model with unitless stocks and per-minute flows cannot be checked.
- Suggest: one time unit per model (or at least per panel), hide the dimensionless "1", and treat
  missing stock units as a Check error, not a pending approval in the attention panel.
- Screenshots: `shots/sdx-8797-api.png`, `shots/sdx-8791-stock-model-error.png`,
  `shots/sdx-8791-factory-open.png`.

### F11 (major). Contradiction about whether anything acts on a goal
- Page: users stock (8796).
- Saw: "Desired level: desired users = 180 (nothing in the model acts on its gap: no feedback closes
  it)", while the Loops page lists `users-growing` as a loop that is "off", and the suggestion says
  "its decision (product-manager, every 30s) is the slowest stage".
- Why it matters: either a balancing loop closes the users gap or it does not; the two pages disagree.
- Screenshots: `shots/sdx-8796-users.png`, `shots/sdx-8796-export.png` (suggestions panel).

### F12 (minor). Pipes drawn as long orthogonal routes around the diagram
- Page: `/diagram?view=dynamics&around=flow/tests-started` (8791); 8797 api/web.
- Saw: `changes-superseded` runs from pending-changes right, down, then ~750 px left along the
  bottom to a cloud; the tests-started pipe leaves pending-changes leftwards then turns down;
  in 8797 the q2 -> q3 pipe snakes around the diagram's edge.
- Why it matters: in SD convention pipes are short and straight, and clouds sit next to their valve;
  long pipes read as material travelling a long way and are easily confused with connectors.
- Suggest: keep sources/sinks adjacent to the valve; allow a pipe one bend at most.
- Screenshots: `shots/sdx-8791-around-tests-started.png`, `shots/sdx-8797-api.png`.

### F13 (minor). Flow values missing on main flows; placeholder text in inspectors
- Page: product (8796), modelling inspectors (8791).
- Saw: `regressions -`, `fixes -`, `shipped -`, `asks -` (dash for the value of real flows);
  inspectors show a lone "..." under the title and descriptions like "the rate of tests-started".
- Why it matters: a flow with no number on a live diagram looks broken; "the rate of X" says nothing.
- Screenshots: `shots/sdx-8796-product-zoom.png`, `shots/sdx-8791-gap.png`.

### F14 (minor). Raw ids leak into the loop tables
- Page: loop R3 panel (8796).
- Saw: rows mix `stock:awaiting-deploy`, `gap:all-live`, `flow:filed-features` with plain names
  (`regressions`, `users`), and the plain ones are links while the prefixed ones are not.
- Screenshot: `shots/sdx-8796-loop-R3.png`.

### F15 (minor). The Guide's SD slides do not match their charts, and the last slide is empty
- Page: `/guide` (8791).
- Saw: slide 4 ("when outflow equals inflow, the stock holds") shows a linear rise then a flat line,
  with no indication of when churn starts; slide 7's "B dominates" curve declines with no goal
  drawn; flows carry no values or units in any slide. Slide 13 "Your system, both ways." stays blank
  even after 6 s. On a phone, slide 2's two diagrams render at about 5 px text.
- Why it matters: the Guide is where an SD person decides whether the authors know the craft; a chart
  that does not follow from the diagram drawn next to it is a red flag.
- Suggest: show the flows' values/equations on each slide (e.g. "signups = 10/week, churn starts at
  week 8"), and fix or drop slide 13.
- Screenshots: `shots/sdx-guide-04.png`, `shots/sdx-guide-07.png`, `shots/sdx-guide-13-wait.png`,
  `shots/sdx-guide-02-phone.png`.

### F16 (minor). No model export in an SD format
- Page: Export menu on `/diagram` (8796).
- Saw: only SVG, Design SVG and PNG.
- Why it matters: a missed chance. The model has stocks, flows, equations, units and parameters;
  XMILE (or a Vensim .mdl) export would let an SD modeller audit and simulate it in a familiar tool,
  and would be the strongest credibility signal for this audience.
- Screenshot: `shots/sdx-8796-export.png`.

### F17 (minor). No equation listing for the whole model
- Page: `/model` (8791, 8796).
- Saw: the Model page has loop identification, parameter estimates and a long list of what ergostat
  can propose (DELAY3, ZIDZ, MAX guards, Little's law). Equations are only visible one flow at a time
  in the inspector.
- Why it matters: SD review starts from the equation listing with units and documentation (Vensim's
  Document view). Without it I cannot audit the model in one pass.
- Screenshot: `shots/sdx-8796-model.png`.

### F18 (minor). Fit leaves the diagram small and pushed down; tiny text at Fit
- Page: `/diagram?view=dynamics&system=modelling` (8791).
- Saw: after Fit, the diagram sits in the lower half with ~250 px blank above and its labels at about
  6 px; "More beyond the edge" stays visible after zooming in.
- Screenshots: `shots/sdx-8791-modelling-fit2.png`, `shots/sdx-8791-modelling-zoom.png`.

### F19 (minor). Phone width: the diagram and tables lose their content
- Page: `/diagram?...system=product`, `/loops` (8796); `/diagram?...system=api` (8797) dark.
- Saw: the diagram gets a ~400 px window that opens on the left edge of the model, with the stock
  cut off; the Loops table hides now/setpoint/error off to the right; the "Model" tab is cut to "Mode".
- Why it matters: OK for a quick status glance, but no structure can be read.
- Screenshots: `shots/sdx-8796-phone-product.png`, `shots/sdx-8796-phone-loops.png`,
  `shots/sdx-8797-phone-api-dark.png`.

### F20 (polish). Mixed conventions for shadow variables and drift biflow
- Page: product (8796), modelling (8791).
- Saw: `<deployed>` uses Vensim's angle-bracket shadow convention, but `filed-bugs` and
  `filed-features` (also from another module) appear as plain grey text; `model-drift` is drawn with
  arrowheads at both ends (a biflow) but its inspector calls it an "inflow".
- Screenshots: `shots/sdx-8796-product-zoom.png`, `shots/sdx-8791-modelling-zoom.png`.

### F21 (polish). Console errors during layout
- Page: `/diagram?view=dynamics&system=modelling` (8791) and 8797 pages.
- Saw: "ELK failed ... TypeError: Cannot read properties of undefined (reading 'Sg')" and
  "xOffset value (408.4) in ShapeConnectionPin constructor greater than shape width".
- Why it matters: may explain some of the overlaps in F6.
- Screenshot: `shots/sdx-8791-modelling-fit2.png` (page where it was logged).

## 3. What works well (for balance)

- Correct core notation: stocks as boxes, double-line pipes with bow-tie valves, clouds at the
  boundary, connector polarity marks, R/B loop markers with direction, `desired` / `excess` gap
  structure with the right signs (`shots/sdx-8797-api.png`, `shots/sdx-guide-02.png`).
- Conservation (stock vs integrated flows) and "extreme conditions" checks, replay vs record, loop
  dominance and parameter calibration with intervals are things most SD tools do not do on live data.
- Equations are typeset and parameters are editable in place with units (`shots/sdx-8796-churn-whatif.png`).
- Honest limits: "not exercised by the record ... not evidence it is absent" and "nothing in the
  model acts on its gap" are the right instincts.
- Dark mode is clean on all pages I checked (`shots/sdx-8796-product-dark.png`, `shots/sdx-guide-07-dark.png`).
