# Parity 2.2: knowing when it is done

Part of the harness-parity exploration ([harness-as-control-system.md](../harness-as-control-system.md) §5
function 2; [harness-parity-plan.md](../harness-parity-plan.md) §2.2). The question is how ergostat's structure, not
a harness, plays the Coordinator's part in deciding that a piece of work is finished, good enough, or needs another
round. The worker's own sense of "I am done" belongs to its harness and is not the subject here.

## 1. What the harness actually does, and why it is valuable

A Coordinator session ends a piece of delegated work many times a day: "merge it", "send it back with these three
points", "good enough, move on", "one more pass on the layout". Looking closely at what produces that decision:

- **The reference is in the context window, and it moves.** The owner's ask, the corrections since, and what the
  Coordinator itself wrote into the subagent's brief are all present when the report comes back. When the work
  reveals that the ask was underspecified, the Coordinator quietly rewrites what "done" means ("the split view
  works, but the real point was readable labels"). The done-criterion is not a fixed field; it is set by the brief
  and revised by later turns.
- **The evidence is gathered, not taken on trust.** The Coordinator reads the diff, runs the tests or checks their
  exit code, opens screenshots, and compares the report's claims to them (function 16 and 8). Done is a judgement
  over evidence, of which the worker's "finished" is only one, weak, piece.
- **It weighs two errors.** Stopping early (false done: the owner reopens it later) and over-polishing (rounds that
  the owner did not value, which also delay everything queued behind). The harness doc already names the decision as
  discretionary and wrong in both directions.
- **It weighs the opportunity cost.** With six things waiting, the Coordinator accepts "good enough" more readily;
  with nothing waiting it sends work back for one more round. The stopping threshold is scheduled on the backlog.
- **It knows which items never finish.** A Coordinator does not try to "complete" the model's fit, a dashboard, or
  the decisions record. Those are kept in band: looked at when they drift, left alone when they hold.
- **Training supplies a prior.** The model carries a learned sense of what a finished change looks like (tests
  green, no TODOs, the ask restated and ticked off) and also a learned bias towards declaring success early, which
  the owner's corrections push against.

The value is the combination: a criterion that is set where the work was asked for and revised as it is learned,
evaluated on gathered evidence, with a threshold that trades the two errors against what else is waiting.

## 2. Classical parallels, and where they fall short

- **Guarded transitions; supervisory control of discrete-event systems** (Ramadge and Wonham). A plant generates
  events; some are controllable; a supervisor disables controllable events whose occurrence would violate a
  specification. Here the worker's "done" event is a request, and moving the item into its accepting state is the
  controllable event the supervisor enables only when the guard holds. Falls short: the specification is a fixed
  language; the harness's guard is written in words and revised mid-run.
- **The rework cycle** in system dynamics project models (Cooper; Ford and Sterman, including "the liar's club" and
  the 90% syndrome). Work flows from to-do to perceived-done, a quality fraction of it truly done and the rest
  becoming *undiscovered rework*, a stock nobody can see, which drains into discovered rework after a discovery
  delay. False done is exactly undiscovered rework; the owner's reopen is its discovery. This is the cleanest
  parallel and the one ergostat should draw. Falls short: it is an aggregate model, it says nothing about how one
  item is judged.
- **Sequential testing and optimal stopping** (Wald's sequential probability ratio test; optimal stopping with a
  cost per observation). Keep sampling while the evidence sits between two thresholds; accept or reject when it
  crosses one. image-squeeze's rollout and rollback already work like this: traffic steps up while bytes are
  saved, and the candidate is kept or dropped when the evidence crosses a guard. Falls short: needs a numeric
  likelihood, which a code review rarely has.
- **Termination criteria of iterative methods, and settling criteria.** Stop when the improvement per iteration is
  below a tolerance or a maximum count is reached; a step response has settled when it stays within a band for a
  time. The second is the right model for items that never complete. Falls short: assumes a scalar error.
- **Cascade control.** The Coordinator writing a brief is an outer loop setting an inner loop's reference. The
  per-item done-when is that reference.
- **Gain scheduling.** The acceptance threshold scheduled on the backlog stock.

## 3. What ergostat already has

Honestly, quite a lot of the pieces, and none of the structure that ties them together.

- **States reached by events** (SPEC §5a): `on:` maps an event type to a state, so an item is "done" exactly when
  some block publishes the event that the kind maps to a final state. The kind declares no guard. Done is whatever
  the worker (or a project program) says; ergostat only records it. Several kinds have no final state at all
  (the-job's `day` ends in `recorded`, but `doc` items in a docs-fresh model live on), so "not all items complete"
  is already true in the data, though nothing distinguishes the two in the model.
- **Changesets with history** (F1, §5a): any field, including a done-when, can be set by the event that starts an
  item and revised by later ones, with every change kept. The mechanism for "set by an event's changeset" exists.
- **`done_when` as a field**, read by the intent judge (§12i). In code it is set in one place only:
  `ergostat/messages/deliver.py` puts the owner's message text on a follow-up it makes. Nothing else sets it; no
  kind declares a default; nothing evaluates it but the judge, and the free stand-in admits it cannot read it.
- **The intent judge** (§12i): judges work that entered an `at` state against done-when, confirmed decisions and
  corrections, and messages; verdicts as items; `held: reopen` moves it back. The gate itself, though, is not
  structural: the judge sets a field `intent`, and in image-squeeze it is the project's rollout program that
  declines to keep a candidate without a met verdict. Where the judge looks (`at`, `accepted`, `reopen-to`) is
  configuration hidden inside the judge block, not a flow in the diagram.
- **Claims and their checks** (§12g): `tests`, `changed`, `state`, `exit`, `level`, and project checks, run by
  ergostat, never by the claimant. These are machine-checkable predicates, on the program rung.
- **The rework measures** (§12i): `ergostat.intent.false-done` and its tests-alone twin, and `intent.yaml` draws them
  as auxiliaries with a goal. The discovery flow (reopen) is counted, but the rework cycle is not drawn as stocks.
- **Item sensors with `where:`** (§6), **cascade** outputs to a goal's setpoint (§13), **the modelling loop**
  (§12e) whose judge already backtests changes on held-out record.

What is missing: (a) where a done-when comes from, other than one follow-up path; (b) evaluation that is not a
single AI-shaped blob; (c) the accept transition as a drawn, gated flow; (d) the over-polish error, which nothing
measures; (e) the threshold's dependence on what is waiting; (f) a model-level distinction between kinds that
complete and kinds that are held in band.

## 4. Candidate designs

### A. The accept flow is a gated valve (supervisory control on the item's transitions)

Split the worker's "done" from the item being accepted. The worker's event moves the item to a *claimed* state (it
already does: `testing`, `review`, `drafted`); the move from claimed to accepted is a flow whose valve is a gate
reading the done-criterion's evaluation. Nothing else may make that move. A held item flows back (rework) with the
reasons. Drawn in SD as the flow *accepting* from stock *claimed* to stock *accepted* with a valve, plus the rework
flow back to *in progress*; in the control view as an interlock block on the actuator path, the evaluation as its
sensor. The gate is a built-in block on the rule rung: it computes, never decides by itself.

Ladder: rule. Modelling's role: none per item; it owns the gate's parameters. Measure: share of accepted items that
went through the gate (should be all), false-done before and after.

### B. The done-criterion is a reference, set by changesets, compiled into checks

Where it is set. Two layers, kept apart because one is model and the other is data:

1. **Static on the kind** (the definition of done): the checks every item of the kind must pass (its tests exit 0,
   its claims verified, no contradicted decision, a measure in band). This is the control model; only the
   modelling subsystem changes it, as an `ergostat.model-change`.
2. **Per item, by changeset**: the reference a commanding block or the owner sets when the item is started
   (cascade: the outer loop writes the inner reference) and may revise later (a message routed to it, 2.4; a
   revision, 2.1). It is data with history, folded like any field. The owner's words land here verbatim, as today.

How it is evaluated. When a per-item done-when is set, a translator (narrow AI, once per revision, not per pass)
splits the words into the checkable part, written back as claim-style checks on the item (`tests`, `changed: path`,
`level: measure <= x`), and a residual that only a reader can judge. The evaluation is then structure: each check is
a sensor reading on the item; the rule-rung gate accepts when every check holds and the residual is either empty or
has a met verdict; the AI judge is asked only about the residual. This takes the complexity out of the intent judge
and puts it in checks the diagrams can count (checks failing by kind is a stock; which check fails most is a
finding). It is 2.16's "turn a claim into a test" applied to the reference instead of the report.

Rate of change. A done-when revised while the item is claimed or in progress does not interrupt the work: the
revision is delivered to the running session as a message (§12h), and the gate evaluates against the version in
force when the item was claimed, recording which. A revision after acceptance is a reopen, explicitly. This is
bumpless transfer: the reference changes, the actuator is not jerked.

### C. The rework cycle, as a library part

Draw the Ford–Sterman structure for any completable kind, parametrised by the kind and its state names:

- stocks: *in progress*, *claimed*, *accepted*, and *undiscovered rework* (accepted but not done as meant: not
  observed, estimated);
- flows: *claiming*, *accepting* (A's valve), *sent back* (the gate's rework), *discovering* (reopened by the owner,
  a follow-up, or a correction naming it: the existing false-done events), with a discovery delay;
- information links: *accepting* reads the checks (B) and the backlog (D).

*Undiscovered rework* is an observer: a stock the model cannot measure, estimated from accepted items times the
recent false-done rate, corrected as discoveries arrive (MODELLING §4's perceived stock, the other way round). Its
value is what a Coordinator holds as "I suspect some of what we merged is wrong". Kinds that never complete get the
other library part: *in band* and *out of band* states with hysteresis (a settling criterion), entered by the same
checks, with no terminal state, so their "done" is a goal held, not an exit.

Ladder: structure only. Modelling's role: it fits the discovery delay and the quality fraction per kind from the
record, like any parameter. Measure: the observer's estimate against what is later discovered.

### D. Stopping as a scheduled controller (another round or not)

For kinds where good-enough is a matter of degree (a layout, a write-up, a model improvement), the gate in A has a
continue region, as a sequential test does: accept when the checks hold and the marginal improvement of the last
round is under a tolerance, send back when a check fails, and between them decide by a threshold scheduled on the
backlog (more waiting, accept sooner) and capped by rounds and cost. The schedule is a `lookup` or `expr` block on
the rule rung; the AI rung is consulted only inside the band. Modelling's role: tune the tolerance, the schedule
and the caps from the two error rates. This is the only design that addresses over-polishing.

### The strongest, sketched (A + B + C, with D's schedule)

```yaml
items:
  hypothesis:
    id: hypothesis/*
    states: [proposed, building, claimed, kept, dropped]
    on: {hypothesis.started: building, hypothesis.submitted: claimed, hypothesis.dropped: dropped}
    done:                          # static on the kind: the model; changed only through ergostat.model-change
      checks:
        - tests: {exit: 0}
        - claims: verified
        - decisions: not-contradicted
      per-item: done_when          # the field a changeset sets and revises (the owner's words, a command's brief)
      accept: {from: claimed, to: kept, by: block.accept-gate}
      rework: {to: building}

blocks:
  accept-gate:                     # rule rung: opens the accepting valve when the checks hold
    type: gate
    kind: hypothesis
    in: {waiting: +stock.ideas}    # gain scheduling: more waiting, the sooner good enough is accepted
    rounds: {max: 3}
    residual: block.intent-judge   # only the words the translator could not turn into checks
    out: {accepted: flow.kept, sent-back: flow.reworked}
```

The library part `rework-cycle(kind)` would then draw the stocks *claimed*, *accepted*, *undiscovered-rework* and the
four flows without the project writing them. (A sketch: `done:` and `type: gate` are not the point; the point is the
claimed/accepted split, a drawn valve on the accept flow, criteria that live on the kind and in the item's
changesets, and the rework loop that measures the result.)

How parity would be known:

- **Against the session's own decisions** (F3): every "merge it" and "send it back" in the transcript is ground
  truth; replay the items through the gate and score agreement, separately for the two errors.
- **False done** (exists) falling towards the tests-alone twin's gap, and **over-polish** (new): rounds and cost
  spent on an item after its first all-checks-held moment, by kind.
- **Ladder descent**: the share of acceptances decided on the rule rung, rising as the translator turns more
  done-whens into checks; the judge's spend falling with it.
- **Observer quality**: undiscovered rework estimated against what was later discovered.

## 5. Recommendation

Build B first, inside A's split, and draw it with C. B answers the owner's question directly: a done-criterion has
exactly two sources, the kind (model, changed only by modelling) and the item's changesets (data, set by whoever
commands the work and revised by messages and revisions, with history). A gives the evaluation a place in the
structure where both diagrams show it, and removes the current dependence on a project program reading a field. C
is what makes it analysable as system dynamics and gives the modelling subsystem something to fit; it is a library
part because every completable kind has the same shape. D is the right answer to over-polishing, but its threshold
can only be tuned once false done and over-polish are both measured, so it comes last, as the gate's schedule.

The modelling subsystem's part, specifically. Its neighbourhood is one kind: the kind's checks, its gate's
parameters, its rework-cycle stocks and flows, the verdicts and reopen reasons of its items, and the corrections
whose kind of work matches. It proposes changes to the kind's checks (add a check that would have caught the last
three reopens; drop one that has never failed and costs time), backtested the way §12e's judge already backtests:
re-evaluate the kind's past items under the proposed criteria and compare with what the owner later found. Changes
apply to items claimed after acceptance; work in progress is never re-judged retroactively, unless the owner asks.
It does not touch per-item done-whens; those are references, not model.

What to do with the old plan and last night's build:

- **Keep**: the `done_when` field and its history; the intent judge, verdict items, overrule and reopen; the
  false-done measures and their tests-alone twin (they are the discovery flow of C); the verbatim owner's words.
- **Change**: done-when is set by any starting or redirecting changeset, not only by message follow-ups; the kind
  declares its static part. The intent judge stops being the evaluator of everything and becomes the residual
  reader behind a rule-rung gate. Its `kinds: {at, accepted, reopen-to}` configuration moves out of the block into
  the kind's transitions, where it is drawn. "Done, not reopened" becomes the rework cycle's stocks rather than a
  standalone stock.
- **Retract**: the claim that every work item carries a done-when (many kinds never complete; for those the
  analogue is a band, not a criterion), and "verbatim from the message that started it" as the only source.
- **Add**: the over-polish measure, the translator from words to checks, and the claimed/accepted split.

## 6. Open questions for the owner

- Should a kind's static done-criterion count as part of the control model (changed only through the modelling
  subsystem), or as configuration a project writes freely?
- May the worker's own "done" event ever move an item straight to its accepting state, or is the gate always between
  them?
- When a done-when is revised while work is claimed, should the gate judge against the version in force at the
  claim or the latest one?
- Is the translator that turns a done-when's words into checks acceptable as a narrow-AI block, given that it writes
  the checks the gate then trusts?
- Should over-polishing be measured by rounds after the checks first held, by cost after it, or by something the
  owner says?
- Is a backlog-scheduled acceptance threshold (accept sooner when more is waiting) the behaviour you want, or should
  quality never trade against queue length?
- For kinds that never complete, is "held in band with hysteresis" the right analogue of done, or do they need no
  analogue at all?
