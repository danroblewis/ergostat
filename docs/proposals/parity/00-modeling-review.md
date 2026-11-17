# 00. The `modelling` subsystem: a review

Status: review, 2026-11-17. Read before the parity notes (01 to 16) that route their gaps through
`modelling`. Written from the code (`ergostat/numbers/improve.py`, `judge.py`, `proposals.py`,
`structural.py`, `verify.py`, `meta.py`, `ergostat/bench/`), SPEC §12e and §12f, MODEL-TOOLS.md,
MODELLING.md, the two examples that wire the loop (`examples/image-squeeze/model.yaml`,
`examples/the-job/job/modelling.yaml`), the Model page (`web/static/pages.js`, `review.js`), the run
records in `~/.ergostat/`, and a fresh stand-in run of image-squeeze (port 8791, no AI spend).

## Verdict

The owner's "it sort of sucked" is right, and the reason is not polish. What exists is a good
**gate** with almost nothing feeding it. The pipeline (propose line, scratch-copy check, judge on
held-out record, Accept, `ergostat.model-change` items, prediction check) is carefully built and
well tested on synthetic truth. But in the product:

- the only things that reach the gate are parameter re-estimates and mechanical fixes for
  `check` findings, plus SD Lab's "remove what did not move" rules;
- the one improver that can find structure (the benchmark stand-in, recall 12/16) lives in
  `ergostat/bench/` and is wired into no example; the examples' stand-ins only re-submit estimates
  the calibration already declined; the residual-pattern finder is a stub that returns `None`;
- it judges by one number, the replay's scaled error over the whole model, so it can say nothing
  about a change to a goal, a sensor, a block or a loop, which is what the parity notes want it for;
- in the one real run with the loop wired (image-squeeze, about three hours), it made 76 changes,
  wrote **one** (a parameter, 4500 to 4404 images an hour), and the goal it holds was never met.

It is a fit report wrapped in a control loop. As the place where structural changes to the
control model are decided, it would currently decide nothing, or decide wrongly.

## 1. What it does today, end to end

**Trigger.** A goal on `stock.model-error` (sensor `builtin: ergostat.model.fit`, the replay's
scaled error over the reference window), held at `<= 0.02` (image-squeeze) or `<= 0.05` (the-job).
While it is off, an `ai` block (`improver`, every 3 minutes) runs. Independently, ergostat's own
finders run whenever the Model page or `ergostat proposals` is asked (and every ten minutes for the
simplify rules), and the judge (`type: judge`) passes every 30 s.

**Context the improver reads.** The goal's error as one scalar (its input JSON), the prompt
(`prompts/improver.md`, a senior modeller's checklist), and MCP tools: `check`, `fit` (per-stock R²,
MAPE, Theil's U), `residuals` (last-hour summary), `explain`, `spec`, `improve_model`, `try_change`.
No tool returns a time series, so the improver never sees a reference mode, a residual's shape, or
the replay against the record. No goals, decisions, corrections, messages or experiment results are
passed in. No focus: it is told the whole model is off by a number. The benchmark's AI improver is
worse off: one `claude -p` call with every tool disallowed, summary statistics only, no
`try_change` (`bench/improvers.py`, `AI`).

**What can be proposed.** Anything as an edit (`{file, replace, with}` on the model's own files),
classified by what it changes (`numbers/version.py`): values only is `parameter`; otherwise
`equation` or `structure`. ergostat's finders propose (`proposals.make`, `structural.find`):
calibrated values; an equation for a flow with declared causes; fixes for `rate-driven-by-rate`,
`stock-without-outflow`, `units-mismatch`, sign, guard, exogenous; terms with no effect removed;
SD Lab's simplifications (dead flow, merged flows, pass-through, still/empty/twin/lone stock).
`structural.CANNOT` lists, honestly, what it cannot: a missing stock, flow or delay from the
residuals; a part replaced by another form; a cause named for an auxiliary. `from_residuals` is a
documented stub.

**How a proposal is checked** (`improve.validate`). Each reason's evidence must resolve: a current
`check` finding, a fit statistic, a residual, a line of any file in the project or in ergostat, a
URL, or a rule name from `RULES`. Then the edit is applied in memory, compiled, checked, replayed on
the reference window, the touched estimable parameters refitted; refused if it does not compile, the
replay is invalid, or the scaled error rises by more than 10%.

**How it is judged** (`judge.run`). After `hold-out` (4 minutes in the examples) of record after it
was made, the change and the current model are replayed on that record, whole, in halves and in
quarters, each window warmed up for 6 hours, scored as the mean of each stock's MSE over its mean
square. Passed only if better by 2% in **every** window, or no worse and answering findings without
making any. `accept: {parameter: auto}` writes the oldest passed value change, one per pass;
everything else waits for the owner in the review queue.

**Accepted, ever.** Across the 114 state directories in `~/.ergostat/`, one run (image-squeeze,
`/tmp/isq`, about three hours) has `ergostat.model-change` items:

| | count |
|---|---|
| made | 76 (74 by ergostat's finders, 2 by the improver stand-in, in 93 improver runs) |
| by kind | 49 parameter, 26 structure, 1 equation |
| failed | 59 |
| superseded | 13 |
| passed | 2 (one value; one equation for the modelling system's own `changes-superseded`) |
| accepted | 1 (`images-per-hour` 4500 → 4404, by the judge's auto policy) |

All 26 structural changes were "Remove X" from the simplify rules, aimed at flows that had not
moved yet in a young record: `claims-contradicted`, `messages-missing`, `failures-cleared`,
`candidate-failing`. Several of those are flows goals hold or the parity work depends on. Each was
failed as "better by 2% or more in 0 of 7 windows (from 0% to 0%)", then made again after the model
changed: churn, not judgement. After the one acceptance, every later re-estimate of
`images-per-hour` was failed as "worse in 7 of 7 windows: the scaled error rises by up to 5755%
(12.1 → 710)". The judge's window errors ran from 12 to 700 while the goal's sensor read 0.03 to
0.14 over the same model: the judge and the goal measure in different regimes (most likely the
6-hour warm-up on a record shorter than that, which integrates the stocks a long way from the
record before each window). `model-error` read 0.025 to 1.03 (mean 0.095), never at its 0.02 goal,
moving with the record and not with the one change written. Nothing else was accepted, by anyone,
in any run. The prediction check (`verify.py`) is wired into no example.

**Fresh run (this review).** A copy of image-squeeze in a temp folder, stand-ins only, about 20
minutes, page on port 8791. For the first ten minutes `ergostat proposals` said "too little record"
for both parameters to estimate (`window-time` "ran to the low end of its range"). Then five changes
were made: the improver stand-in re-submitted the two estimates the calibration had declined (both
failed: "worse in 1 of 7 windows", "better in 2 of 7"); the calibration proposed `images-per-hour`
4500 → 4317 (scaled error 0.0443 → 0.0284), which the judge passed and wrote at once, on 11 minutes
and 53 points of record (the earlier run wrote 4404 for the same number); and the simplify rules
proposed **removing `messages-awaiting`**, the queue of the owner's messages that 2.4 just built,
because it was "empty at 100% of its readings", with a benefit of "0.0467 → 0.0467". It was
superseded when the value was written, and made again. `ergostat improve` said "nothing proposed by
a block has been turned away". The calls are quick (`proposals` 2.7 s on this record). Nothing about
structure, goals or the control system was proposed, and nothing could have been.

## 2. Where it falls short

### Against Sterman's modelling process

| Sterman's step | What a practitioner does | ergostat today |
|---|---|---|
| Problem articulation, boundary | Name the problem, the reference modes, the time horizon; choose what is endogenous | No problem statement. The goal is "fit everything". `boundary` is a rule name a reason may cite; nothing tests boundary adequacy |
| Reference modes | Plot the behaviour over time to be explained | No series reach the improver; the Model page has charts, the improver has none |
| Dynamic hypothesis | A loop structure that would produce the reference mode, stated before fitting | Nothing proposes or records hypotheses. A proposal is an edit, not a hypothesis with a predicted behaviour |
| Formulation | Write the structure; small, meaningful parameters | Mechanical: one fix per `check` finding |
| Structure tests | Boundary, structure assessment, dimensional, extreme conditions, parameter assessment | `check` and extreme conditions are real and good. But they gate only as "evidence" strings, and a rule name passes the gate without any test that it applies |
| Behaviour tests | Reproduction, anomalies, sensitivity, surprise behaviour, family member | Reproduction only, as one scalar. Sensitivity exists on the page and is never used to judge a change |
| Policy | Test the decision rules the model is for | Absent. A change to a controller, a goal or a block is never simulated as a policy |

The judge's rule "better by 2% in every window" also inverts Occam: a simplification that leaves
the fit unchanged can never pass on fit, so every SD Lab simplify proposal fails unless it happens to
answer a finding. And it accepts compensating errors: MODEL-TOOLS.md's own benchmark says the damage
that gets through is "a value refitted to make up for a missing flow".

### Against system identification

A control engineer chooses an experiment, a model class and an order, fits, then validates on
fresh data with residual tests (whiteness, cross-correlation with inputs), and treats a closed loop
as needing an external excitation. ergostat has the pieces for loops (identification, step tests,
SIMC in §12d) but they live beside `modelling`, not in it: a loop's process or gain is a
`model-change` kind the judge explicitly skips. The residual tests that name missing structure
(autocorrelation means a missing state; cross-correlation with an input at lag k means a missing
delay) are not computed anywhere. Step tests, ergostat's only active experiments, never feed a
structural hypothesis.

### SD Lab work not reused

`~/orchestra_2/orchestra/sdlab/discovery` (and `~/orchestra/sdlab`, its source) holds about fifty
benchmarked strategies. Only the simplify rules came across. Not reused:

- **`kalman_lna`**, its best strategy on noisy reports (85 of 97 achievable noisy cells against 35),
  treating levels as noisy reports of hidden states. ergostat's fit takes readings as truth.
- **`hidden.py` / `hidden_transit` / `kalman.py`**: unmeasured stocks between measured ones as delayed
  copies, with a likelihood comparing "with H" against "plain". This is exactly the missing
  `from_residuals`.
- **`residual-diagnostics.md`**: a typed table from residual signature to proposal (autocorrelated →
  hidden stock or delay; follows a lagged level → link; one-sided near zero → floor or cap; CUSUM
  break → era-specific number; Theil bias → constant). Specified, not built, in either place.
- **`llm-critic.md`**: an LLM given the found flows, names, units and per-row residuals proposing typed
  edits, each fitted by the fitter and kept only if the judge improves. That is the improver this
  subsystem wants, with typed edits instead of raw YAML.
- **`structure-search.md`**: search over edit moves with a complexity penalty.
- **skill@H**: the share of the truth's movement over H steps a model predicts from the same states,
  a forecast measure that does not need a long free replay.
- **`held-out-judge.md`**: SD Lab measured pure held-out selection and *rejected* it (skill −4.8%
  against 70.8%); a blend worked. ergostat's judge is pure held-out. Worth reading before keeping it.

### The five shortcomings that matter most

1. **It cannot find structure.** The product has no finder for a missing stock, flow, delay or cause;
   the one that exists is benchmark-only; the improver is blind to time series. Structure is the
   thing the parity notes need, and the thing it cannot make.
2. **It judges only the dynamics model's fit, and misclassifies everything else.** Goals, sensors,
   blocks and controllers are not in `version.structure`, so an edit to them is called a
   `parameter` change. Tried on the fresh copy: changing the goal `hold: "<= 0.02"` to `"<= 0.5"`
   with the single reason `rule:behaviour-reproduction` "would be proposed", kind `parameter`. Under
   the examples' `accept: {parameter: auto}`, the only thing between that and an automatic write is
   that the judge sees 0% change and fails it; had it answered a finding, it would have passed and
   been written.
3. **The evidence gate is a rubber stamp.** Any rule name, any URL and any line of any file in the
   project or in ergostat count as verified evidence. The check confirms that the citation exists,
   not that it supports the claim.
4. **The loop's signal is noise.** One global scalar over a moving window, dominated by whichever
   stock is worst, never met in the real run; the improver runs every three minutes against it and
   proposes nothing (2 proposals in 93 runs). The judge's windows score in a different regime from
   the goal (12 to 700 against 0.03 to 0.14), so its verdicts swing by thousands of percent on a 2%
   value change. Its 0-and-0 error rates were measured on synthetic worlds with long records, not on
   a young, real one.
5. **It is opaque, and the diagram never shows a proposal.** A change appears as a list entry on the
   Model page; "Show on diagram" only selects parts that already exist, so a proposed stock or loop
   cannot be seen in place. The verdicts the owner reads ("0 of 7 windows, from 0% to 0%") say
   nothing about what the change would have done to the system's behaviour.

Also: two examples carry the same 150 lines of boilerplate to wire the loop (stocks of change items
by state), a model of the bookkeeping rather than of what improving the model is for; `verify` and
the loop's own measures are wired nowhere; and the Model page's fit took 24 s on a day of record
before F2 and still 9 to 16 s cold after it, slow for a loop that refits per proposal.

## 3. What it would need to be the place structural changes are decided

**Inputs: a request, not a scalar.** A `model.request` (an item, `ergostat.model-request`) that
names what prompted it and points at the record: a goal revision (2.1), a done-when judged unmet
(2.2), an inferred intent or invariant (2.3), a correction (2.13), a message (2.4), a failure
diagnosis (2.6), an experiment's result (2.7), a residual or finding. It carries references, not
copies (`decision/…`, `correction/…`, `message/…`, `finding:…`, a series and a span), and a
question ("why does `candidate-failing` rise after each rollout?"). The improver's context is a
projection recipe (§12j) built from the request: the referenced items, the neighbourhood's
definitions, and the series for its span, plotted or tabled. The fit-goal loop stays as one source
of requests among many.

**Focus: a neighbourhood.** Every request names parts; ergostat expands them to the neighbourhood
(the parts within k links, the loops through them, the goals and blocks that read or act on them,
the systems they sit in) and gives the improver only that, plus a one-line summary of the rest.
Judging is local too: the stocks of the neighbourhood weighted first, the rest required to be no
worse. This is also what makes the judge cheap enough to run often.

**Kinds of change.** Typed edits, not raw YAML, each with its own judge:

| Kind | Examples | Judged by |
|---|---|---|
| value | a parameter, a delay time | held-out replay of the neighbourhood (today's judge, fixed) |
| form | an equation replaced, a first-order drain made a DELAY3 | held-out replay plus residual whiteness |
| structure | a stock, flow, link or delay added or removed | the above, plus a complexity penalty, plus a test of the stated behaviour |
| measurement | a new sensor, `averages:`, a series bound | whether it explains a residual; no fit test |
| control | a goal's setpoint, a controller's law, a block added, its `every` | simulation of the policy against the goal, and the owner |
| boundary | a part made exogenous, a system's edge moved | the owner, with the residuals it would leave |

`kind_of` must use a hash of the whole spec by section, so a goal edit is never a parameter.

**Rate of change, and when work pauses.** One structural change in flight per neighbourhood (a lock
on its parts, as 2.14 proposes for code). Values may be written automatically; structure, control
and boundary never are. While a structural change to a neighbourhood is under test, the blocks that
act on it keep running (the change is in a scratch copy), but a change to a goal or a controller
they follow takes effect at the start of their next run, never mid-run, and is announced to running
sessions as a message (2.4). A budget of structural changes a day, as a goal on
`ergostat.model.accepted-per-day` by kind, stops churn.

**Evidenced, simulated, reviewed, applied.** A proposal states a **dynamic hypothesis**: what
behaviour it predicts (a series and a direction over a span, "`candidate-failing` peaks about 10
minutes after each rollout, then drains"). Evidence is checked for *support*, not existence: a
residual cited must be significant and of the sign claimed; a line cited must be read by a checker
that says whether it bears on the claim (the intent judge's machinery, §12i, reused). Simulation is
the hypothesis's prediction against the record after it (the judge), the sensitivity fan with and
without the change, and, for control, the closed loop simulated with its blocks' laws. Review is the
item, with the hypothesis, its prediction against what happened, and the diff. Apply is Accept as
now, plus `verify` running by default.

**Drawn in the existing UI.** On the Dynamics and Blocks views, a proposed change is drawn in place
as a tentative part: a dashed stock, flow or link in the accent colour, a struck-through part for a
removal, a changed setpoint marked on its goal, toggled by the review entry's "Show on diagram". The
causes strip of a touched part draws the record, the model as it is and the model with the change,
which it nearly does already. The item page holds the hypothesis, its prediction and the verdict.
No new page or panel: the Model page's review queue stays the list.

## 4. Milestones, ranked

1. **Classify and gate honestly.** `kind_of` by spec section (goal, sensor, block, controller kinds
   added); evidence checked for support (residual significance and sign, finding still present
   *and* about a touched part, rule applicable by `check`); rule names and bare file lines alone no
   longer suffice. *Done:* the goal-edit trial above is refused or classed `control`; a test plants
   ten unsupported reasons and all are refused. *Measured:* share of proposals whose evidence is
   support, not citation (target 100% on the bench's AI runs).
2. **A judge that works on a young, real record.** Warm-up bounded by the record held; scores in the
   goal's own measure; neutral-and-simpler passes (penalised likelihood or a complexity term);
   neighbourhood-weighted. *Done:* rerun the image-squeeze three-hour scenario; no 1000%-scale
   swings on a 2% value change; simplify proposals for genuinely dead parts pass, for rare goal
   flows are not made. *Measured:* `bench judge` still 0 false accepts, plus a new case set built
   from real example records with planted changes.
3. **Structure from residuals in the product.** Port SD Lab's `hidden.py`/`hidden_transit` and the
   residual-diagnostics table into `structural.from_residuals`; move the bench stand-in's menu into
   ergostat's finders. *Done:* `ergostat proposals` on a damaged image-squeeze proposes the missing
   stock or delay. *Measured:* `bench improve` recall with the product's own finders (no improver)
   ≥ the stand-in's 12/16, damage ≤ 2.
4. **Requests and focus.** `ergostat.model-request` items from goals, corrections, messages,
   findings; the neighbourhood projection recipe with series; the improver started per request.
   *Done:* a correction in the-job about a missing delay produces a request, a session that sees only
   that neighbourhood, and a proposal there. *Measured:* tokens per proposal, proposals per request,
   share accepted; parity cases routed through it (F3).
5. **Dynamic hypotheses and predictions.** Every structural proposal carries a predicted behaviour;
   the judge scores the prediction; the item shows predicted against actual. *Done:* review entries
   show it; a proposal without a prediction is a `value` change at most. *Measured:* prediction hit
   rate per improver, which becomes the improver's trust (§12g).
6. **Drawn on the diagram.** Tentative parts in both views, toggled from the review entry. *Done:*
   a proposed stock is visible in place with its flows dashed; the diagram render tests cover it.
   *Measured:* owner can say what a proposal does from the diagram alone (UX review).
7. **Control and boundary changes judged by policy simulation.** Goals, controllers and blocks as
   change kinds, simulated closed-loop with the block laws, written only by the owner, applied at the
   next run of the blocks they affect. *Done:* a setpoint revision (2.1) and a new sensor (2.7) go
   through the same item lifecycle with a verdict that is about the policy, not the fit.
   *Measured:* revisions accepted against later reverted.
8. **The loop wired once, not copied.** A built-in `modelling` system (or a recipe the YAML names in
   one line) replaces the 150 copied lines; `verify` and the meta-measures on by default. *Done:*
   every example can turn it on in one line. *Measured:* `accepted-per-day`, `verified-share` and
   `regressed` read in a week-long demo run.

Items 1 and 2 are prerequisites for anything the parity notes route here: without them a
structural change to the control model is either misfiled as a parameter or judged by a number
that cannot see it.
