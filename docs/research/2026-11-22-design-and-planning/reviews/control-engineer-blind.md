# ergostat, reviewed blind by a control engineer

Reviewer: a control engineer who reads block diagrams, transfer functions, cascades and summing junctions every day. I used only the running demos (:8791 ticket-factory, :8792 the-job, :8793 image-squeeze, :8796 software-factory, :8797 big), in a browser at 1440x900, at 390x844, and in dark mode. Screenshots are in <workdir>/design/shots/ (prefix `ce-`).

## What I think it is (written before judging)

ergostat watches a working organisation and models it as a set of feedback loops. Its examples are a software team made of tickets, PRs, CI, people and AI agents, plus a personal "job" and an image-compression service. It reads an event record and items (Jira tickets, PRs and so on). From these it builds two views of the same system:

- a **system dynamics** view: stocks are queues such as `review-asked` and `picked`, flows are rates, and causal loops are labelled B/R.
- a **control** view: proper block diagrams with r, e, u, y, d and y_m, summing junctions, sensors H, relays, C(z) with ZOH and samplers, plants P(s), mostly 1/s integrators, and MIMO subsystems Q.

It identifies process models from the record (gain, τ, dead time θ, Ljung-Box on residuals), judges each loop (time off, settling, Harris index, how often it is past its bound) and suggests tuning ("more per run, or acting more often"). It also gates outward actions such as git push and Jira comments behind human approval. The intended user looks like an engineering lead or operator who runs a semi-automated "factory" of agents and wants to regulate it with control-theory discipline. A control engineer is a secondary audience, there to check that the regulation is sound. I am fairly sure of this (about 75%). The guide's "you control the knob, you want the stock" framing and the `ergostat actions` approvals confirm the operational use.

**Overall:** the Blocks notation is better than I expected. The relay sketches, C(z) = 350z/(z−1) with its difference equation, the ZOH, the sampler before the dead band, the MIMO mux/demux with vector slashes and the H(s) = e^{-sT} polled sensors are all textbook. The main problems are about **trust in the numbers**: loop panels contradict the record, stock balances do not close, and models fit worse than the mean. There is also **vocabulary drift** between the views, **diagrams that "Fit" does not fit**, and **no way to take the model out** to MATLAB, Simulink or a CSV.

## Findings, worst first

### 1. [major] A loop panel contradicts the record it is drawn from
- Pages: /loops (requests-handled row), /diagram (the side panel from Evidence), /agents, /record
- What I saw: requests-handled says "u moved by fixer: never opened. Its valve did not open in the 10m recorded" and "Last decision 10m ago: act: fixer". The parts table says sensor `unanswered-requests.main` is "unfilled" yet "read 2s ago: 36". "Cycled: yes, in this window" and "Moves requests-answered 4.85/h" sit next to "never opened". Meanwhile /record shows `block.commanded fixer {"from":"keep-requests-handled","amount":1}` every minute, and /agents shows fixer with 10 runs, the last one 46s ago, every 1m.
- Why it matters to me: the u trace is the first thing I check when a loop saturates or never closes. If the panel says the actuator never moved while the log shows it commanded every minute, I cannot tell whether this is actuator saturation, a broken actuator or a display bug, so I stop trusting every panel.
- Suggestion: derive "valve opened", "last decision" and "sensor filled" from the same events /record shows. If "commanded" and "opened" are deliberately different (commanded but no effect), say so in one line: "commanded 10 times, moved nothing".
- Screenshots: <workdir>/design/shots/ce-tf-evidence.png, <workdir>/design/shots/ce-tf-loop-click.png, <workdir>/design/shots/ce-tf-agents.png

### 2. [major] The identified model does not balance, yet loops are presented as "an integrator, from the model"
- Pages: /model (Residuals, History), /check
- What I saw: the residuals table shows stocks that did not change while their known flows explain large moves: review-asked changed 0, explained 142, unexplained −142; pr-open −71/+71; sailed 76/−76. /check gives 17 warnings, almost every flow being "its equation fits its record worse than holding it at its mean (R² 0.00)". model-error rose from 0.274 to 1.46 during my session. The Loops table on /model still states "an integrator, from the model" for most loops with no caveat.
- Why it matters to me: an integrator plant model is only as good as the mass balance behind it. With residuals that large, the flows are miscounted, or the stocks are, and every gain and dead-time estimate built on them is suspect. The UI presents the plant structure with confidence while the evidence against it sits on another page.
- Suggestion: carry a per-loop "model health" marker (balance closes or not, R² of its flows) next to "integrator, from the model". Show the balance violation on the plant block P(s) in the Blocks view as well.
- Screenshots: <workdir>/design/shots/ce-tf-model-bottom.png, <workdir>/design/shots/ce-tf-model.png

### 3. [major] "Fit" does not fit, and at Fit the large diagrams are unreadable
- Pages: /diagram?view=blocks&system=modelling (:8797), /diagram?view=blocks (:8793, opened from /model), /diagram?view=blocks&system=api (:8797)
- What I saw: after pressing Fit, wires still leave the right edge and the toolbar still says "More beyond the edge". On big/api, Fit shrinks four cascaded queue loops until the block text is about 5px. The serial chain q0→q1→q2→q3, obvious in the Dynamics view, is scattered in Blocks, so the cascade structure cannot be read.
- Why it matters to me: the block diagram is the reason I would use this. If I cannot see one whole loop at once (r to e to C to u to P to y to H and back), it does not help me.
- Suggestion: make Fit include every wire. For a large system, lay out one loop per row in signal-flow order, and keep serial couplings (the output of one plant feeding the next) left to right.
- Screenshots: <workdir>/design/shots/ce-big-blocks-modelling.png, <workdir>/design/shots/ce-big-blocks-api.png, <workdir>/design/shots/ce-is-controller.png, <workdir>/design/shots/ce-big-dyn-api.png

### 4. [major] Subsystem symbols are inconsistent across levels: Q, P, (s), dimensions
- Pages: /diagram?view=blocks (:8796, :8792), /diagram?view=blocks&system=product (:8796)
- What I saw: at the top level of software-factory, "Q_product(s) 3×1". Opening it shows "P_product(s) 3×2, not identified": a bare plant, no controller, with 2 inputs (u_deployed and d) rather than 1. The legend says "Q a subsystem; Q without (s) holds sampled or nonlinear parts", but most Q blocks have no (s) and a few do (Q_product(s), Q_messages(s)). The Q is bold on some diagrams and italic on others. The "12×1" style dimensions are never explained (outputs × inputs?).
- Why it matters to me: a plant labelled Q with a dimension that changes when opened makes me doubt the interconnection. In my field Q also commonly means the Youla parameter, so an unexplained Q is jarring.
- Suggestion: if a subsystem contains only a plant, label it P at both levels. Make the dimensions agree between levels (say whether disturbances count) and state "outputs × inputs" in the legend. Use one typeface.
- Screenshots: <workdir>/design/shots/ce-sf-blocks.png, <workdir>/design/shots/ce-sf-blocks-product.png, <workdir>/design/shots/ce-sf-blocks-factory.png, <workdir>/design/shots/ce-job-blocks-job.png

### 5. [major] "Loop" means two different things, and the counts disagree
- Pages: /diagram (Dynamics), /loops, the Blocks side panel
- What I saw: Dynamics says "Feedback loops 49" (modelling 11, factory 36, oversight 2). Inside factory, the sub-boxes say intake 6, making 6, review 22, shipping 14, which is 48, not 36. /loops and the Blocks panel list "Loops 16".
- Why it matters to me: to me a loop is a controlled variable with a setpoint and an actuator. SD causal loops (B/R) are a different object. Showing both as "loops" with counts that do not add up makes me think the model is double counting.
- Suggestion: name them differently ("causal loops" vs "control loops"). Make a parent's count the de-duplicated union of its children, and say so.
- Screenshots: <workdir>/design/shots/ce-tf-home.png, <workdir>/design/shots/ce-tf-dyn-factory.png, <workdir>/design/shots/ce-tf-loops.png

### 6. [major] Error and setpoint vocabulary drifts, and one-sided setpoints make "error" misleading
- Pages: /diagram (Dynamics and Blocks side panels), /loops (:8791, :8797)
- What I saw: the same deviation is "desired = 0: excess 36" (Dynamics), "setpoint ≤ 0 (off by 36)" (Blocks) and "error −36" (Loops). For one-sided setpoints the error column shows 0 whenever the value is within bound (api-q1 = 10, setpoint ≤ 20, error 0). On big, a loop shows "time off 0%" and "past its bound 5%" on the same row.
- Why it matters to me: e = r − y is sacred. A one-sided constraint is not a setpoint, and "time off 0%" next to "past its bound 5%" reads as a contradiction. (I think "past its bound" includes the tolerance and "off" does not, but nothing says so.)
- Suggestion: call one-sided targets "limit" or "constraint", show the constraint violation max(0, y − ȳ) as its own column, and use one term for it in every view. Put the tolerance in the setpoint cell, e.g. "≤ 20 ± 2".
- Screenshots: <workdir>/design/shots/ce-big-loops.png, <workdir>/design/shots/ce-tf-home.png, <workdir>/design/shots/ce-tf-blocks.png, <workdir>/design/shots/ce-tf-loops.png

### 7. [major, missed chance] Nothing exports the model, only pictures
- Page: the Export menu on every diagram
- What I saw: SVG, Design SVG and PNG only.
- Why it matters to me: I would want to take P(s), C(z), the interconnection, and the r/y/u/e traces into MATLAB/Simulink, Python-control or Modelica to verify margins and to simulate tuning changes offline. The panels already compute K, τ, θ and C(z). Not letting me take them away is the single biggest missed chance for my audience.
- Suggestion: add an export of per-loop transfer functions (JSON or a .m file), CSV of the r, y_m, u, e traces for the window, and ideally a Simulink or Modelica skeleton of the block diagram.
- Screenshot: <workdir>/design/shots/ce-tf-export.png

### 8. [major] Phone width hides the numbers that matter
- Pages: /loops, /diagram?view=blocks&system=oversight (:8791), /diagram?view=blocks&system=product (:8796, dark)
- What I saw: at 390px the Loops table shows only loop, status and holds. now, setpoint, error, time off and trend are off-screen, with no hint that it scrolls sideways. The nav cuts "Model" in half. Block diagrams open unfitted and are cut off on the right.
- Why it matters to me: on call I would check "which loop is off and by how much" from a phone, and that is exactly what is hidden.
- Suggestion: on narrow screens make each loop a card (status, now vs setpoint, error, sparkline), auto-fit diagrams on load, and make the nav scroll visibly.
- Screenshots: <workdir>/design/shots/ce-tf-loops-phone.png, <workdir>/design/shots/ce-tf-blocks-phone.png, <workdir>/design/shots/ce-sf-blocks-phone-dark.png

### 9. [major] The guide's final slide draws the SD diagram as black boxes
- Page: /guide, slide 13 "Your system, both ways" (light mode)
- What I saw: the left thumbnail (the system dynamics diagram) renders as solid black rectangles with near-invisible text. The control-diagram thumbnail beside it is fine.
- Why it matters to me: this is the slide that ties the tutorial to my own system, and half of it is unreadable.
- Suggestion: fix the thumbnail's fill colours (it looks like a dark-theme fill leaking into light mode).
- Screenshot: <workdir>/design/shots/ce-guide-control.png

### 10. [minor] A process panel opened from /model is blank at first, with no loading state
- Page: /model, then "process"
- What I saw: on the first click the Blocks canvas and the side panel stayed completely empty for at least 2s. On a second attempt with a longer wait it showed P_picked(s) = 1/s correctly.
- Why it matters to me: I took it as broken.
- Suggestion: show a loading indicator, or render the panel before the diagram.
- Screenshots: <workdir>/design/shots/ce-tf-model-process.png, <workdir>/design/shots/ce-tf-model-process2.png

### 11. [minor] The identification panel has garbled fit statements and text from another loop
- Page: /model, then "process" for quality-held (:8793)
- What I saw: "Fit: 0% of the record held out, of the 0% its noise allows; 56% of what it was fitted to"; "follows −128% held out". The quality-held panel ends with a paragraph about "the loop small-images".
- Why it matters to me: the content itself is excellent (K ± σ, θ ± σ, Ljung-Box Q, independence from u, closed-loop data warning). These sentences undermine it, and a negative fit percentage needs its definition (e.g. NRMSE fit).
- Suggestion: present fit as a small table (estimation vs validation NRMSE, defined). Keep panels scoped to their own loop.
- Screenshot: <workdir>/design/shots/ce-is-process.png

### 12. [minor] The relay is called "with hysteresis", but its law has none
- Page: the Blocks side panel for keep-nothing-awaits-approval
- What I saw: "an on-off controller (a relay with hysteresis): u = 1 while y > 0, u = 0 once y is back to ≤ 0". The on and off thresholds are the same, so there is no hysteresis band.
- Why it matters to me: a relay without hysteresis chatters, and the difference matters for limit-cycle analysis.
- Suggestion: either show the band (on above y_hi, off below y_lo) or call it an ideal relay.
- Screenshot: <workdir>/design/shots/ce-tf-model-controller.png

### 13. [minor] The Agents page's tier numbers read as counts and contradict the header
- Page: /agents
- What I saw: the header says "2 person → 4 ai → 0 narrow-ai → 0 decision → 13 program → 16 rule". The section headings say "0 person", "1 ai", "4 program", which look like tier indices but read as counts.
- Why it matters to me: on the same page "2 person" and "0 person" look like a bug.
- Suggestion: write "tier 0: person (2)".
- Screenshot: <workdir>/design/shots/ce-tf-agents.png

### 14. [minor] On big, the attention panel is flooded by 24 bookkeeping requests
- Page: / on :8797
- What I saw: one real control problem (requests-handled off by 164), then about 24 nearly identical "modelling holds no-unit on stock.api-qN" requests, each with Deny and no Approve.
- Why it matters to me: real alarms drown in housekeeping, which is a classic alarm-flood anti-pattern.
- Suggestion: group identical requests into one row with a count, put loop alarms first, and explain why only Deny is offered.
- Screenshot: <workdir>/design/shots/ce-big-home.png

### 15. [minor] Units are mixed within one view
- Page: /diagram (Dynamics, :8791)
- What I saw: "address 6.29 tickets/min", "work 40.4 tickets/h", "fix-ci 3.46 tickets/min" in the same box.
- Why it matters to me: I compare rates entering and leaving a stock, and I need one time base for that.
- Suggestion: use one rate unit per system, or per diagram.
- Screenshots: <workdir>/design/shots/ce-tf-dyn-factory.png, <workdir>/design/shots/ce-tf-home.png

### 16. [minor] Labels collide in diagrams
- Pages: /diagram?view=blocks&system=factory (:8791), /diagram?view=dynamics&system=api (:8797)
- What I saw: "to oversight" is printed over "y_intake". The B10 loop marker covers "excess api-q2". The "api-q1-low" label is struck through by a pipe.
- Suggestion: avoid collisions for port labels and loop markers.
- Screenshots: <workdir>/design/shots/ce-tf-blocks-factory.png, <workdir>/design/shots/ce-big-dyn-api.png

### 17. [minor] Ambiguous wire crossings and junctions
- Page: /diagram?view=blocks&system=factory (:8796)
- What I saw: the 2-wide bus from Q_delivery crosses the y_m,backlog return exactly at its "/2" slash. It then runs into Q_intake's input side merged with the y_m,users wire, so I cannot tell crossing from joining.
- Suggestion: draw a dot only at real take-offs, use a hop or gap at crossings, and keep vector slashes off crossings.
- Screenshot: <workdir>/design/shots/ce-sf-blocks-factory.png

### 18. [minor] Polled sensors are drawn inconsistently
- Pages: Blocks for oversight (:8791) vs product (:8796)
- What I saw: "H = 1, ergostat: actions.held, every 3 s" is drawn without a sampler. "H(s) = e^{-sT}, T = 5 s" is drawn with a sampler switch. Both are periodic polls.
- Why it matters to me: the legend says the switch appears when the period "matters against the loop's", but nothing on the diagram tells me that judgement was made or what it was compared with.
- Suggestion: always draw the sampler, and grey it out when T is negligible against the loop's time constant, stating the ratio.
- Screenshots: <workdir>/design/shots/ce-tf-blocks-oversight.png, <workdir>/design/shots/ce-sf-blocks-product.png

### 19. [minor] The Guide's section names cannot be clicked
- Page: /guide
- What I saw: clicking "Control: what we control" or "Yours" does nothing. Only the arrows move between slides, so jumping straight to the control part takes 8 clicks.
- Suggestion: make the section labels and dots links.
- Screenshots: <workdir>/design/shots/ce-guide-yours-dark.png, <workdir>/design/shots/ce-guide-control.png

### 20. [minor] Every demo's headline loops are the tool's own, and they are always off
- Pages: /loops on all demos
- What I saw: requests-handled and model-fits are "off" at 70–99% on every demo, so the red "N loops off" badge is never clean and opens on ergostat's own bookkeeping rather than the plant.
- Why it matters to me: I want the controlled process first. A permanently red indicator trains people to ignore it.
- Suggestion: separate the tool's own loops (or rank them below the system's), or fix them so they hold.
- Screenshots: <workdir>/design/shots/ce-sf-loops.png, <workdir>/design/shots/ce-tf-loops.png

### 21. [polish] The disturbance slide changes the decomposition without saying so
- Page: /guide slides 10–11
- What I saw: slide 10 has P_customers(s) "not identified". Slide 11 splits it into G_customers(s) "not identified" followed by P_customers = 1/s, with no explanation. The y and r end labels on the response plot sit on top of each other.
- Suggestion: one sentence ("we split off the integrator, the stock, from the unknown dynamics") and separated labels.
- Screenshot: <workdir>/design/shots/ce-guide-slide11.png

### 22. [polish] Uncoupled subsystems are stacked with no signals between them
- Page: /diagram?view=blocks&system=job (:8792)
- What I saw: ten Q blocks in one tall column with no wires between them and tiny labels at Fit.
- Why it matters to me: I cannot tell whether they are truly decoupled or the couplings are just not drawn.
- Suggestion: say "no signals between these systems", and use a grid layout.
- Screenshot: <workdir>/design/shots/ce-job-blocks-job.png

## What works well (keep it)

- Real block-diagram discipline: signed summing junctions, r/e/u/y/d/y_m subscripts, H in the feedback path, relay and dead-band sketches, C(z) with its difference equation, ZOH, samplers, and MIMO mux/demux with vector widths (<workdir>/design/shots/ce-is-controller.png, <workdir>/design/shots/ce-tf-blocks-oversight.png).
- Identification panels that report uncertainty (K ± σ, θ ± σ), residual whiteness (Ljung-Box) and closed-loop data caveats, and that refuse to propose a model when the data cannot support it.
- The scope panel (y, u, e stacked over time, with the off periods shaded) is exactly what I want for a loop (<workdir>/design/shots/ce-tf-model-scope.png).
- Dark mode renders the block diagrams cleanly (<workdir>/design/shots/ce-tf-blocks-dark.png).
