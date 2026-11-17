# Parity 2.3: inferring intent, asking or acting, and invariants

Status: exploration, 2026-11-17. One of sixteen gap studies replacing the first parity plan's answers
([harness-parity-plan.md](../harness-parity-plan.md) §2.3). Function 3 of
[harness-as-control-system.md](../harness-as-control-system.md) §5.

## 1. What the harness actually does here

An AI block already infers intent for its own run: given a brief, it guesses what was meant and decides
whether to ask. That is not this gap. The gap is the **Coordinator's** inference: the long session that
held the owner's conversation, read each new sentence through everything said before, and turned it into
(a) what the system should now aim at, (b) what it must never do again, and (c) whether a doubt was worth
the owner's time.

Concretely, three things in the session produced it.

- **The always-loaded layer.** CLAUDE.md, AGENTS.md and the memory index are read at every session start
  and survive compaction. They are mostly not goals but **invariants**: one-package-no-path-hacks, humans
  talk only to the Supervisor, deletes by allowlist, no new pages. Each was written once, usually after one
  sentence of the owner's, and thereafter constrains every action without the agent re-deriving it. The
  flip the owner points at is exactly this: the harness records intent the *next* agent is not yet aware
  of, so that agent never has to infer it.
- **Generalisation from one sentence.** When the owner rejected one thing ("no new UI"), the Coordinator
  extended it to cases nobody named (a panel, a wizard, a dock). That comes from the model's training: it
  reads a sentence as an instance of a rule and guesses the rule's extent.
- **The ask-or-act prior, retuned.** Training gives a cautious prior (ask before outward or irreversible
  actions, act on reversible ones); the conversation retunes it (a memory entry tells it to decide and act,
  asking only before writes outside the machine). The decision weighs the owner's attention against the
  cost of rework, and the weighting is per neighbourhood: in some areas the session knew the owner's mind,
  in others it did not.

Its value: the owner says a thing once; it constrains all later work, including work the owner never
thought about; and the owner is asked only where a guess would be expensive and uncertain.

## 2. Classical parallels, and where they stop

Control engineering separates two things the word "intent" blurs.

- **References (setpoints)**: where the system should be. Regulation steers toward them; error is normal
  and is corrected continuously. ergostat's goals.
- **Constraints**: where the system must not go. In model predictive control they are written apart from
  the cost: **soft constraints** (violations penalised, steered back) and **hard constraints** (never
  violated; the optimiser must find a feasible move or none). In process plants they sit in separate
  **layers of protection** (IEC 61511): the basic process control system regulates; **alarms** call a
  person; **interlocks** and **permissives** block actions (a pump may not start until the valve
  upstream reads open); the **safety instrumented system** trips the process to a safe state. A setpoint
  is never allowed to drive the plant through a protection layer: the protection layer is designed to
  break the loop on purpose.

That answers "when does the system break, and when is it steered": **it is steered toward a setpoint;
it is stopped at a constraint.** The design choice between them is classical: is the violation
reversible, and is it observable in time to correct it? Reversible and observable: a soft constraint, a
balancing loop. Irreversible, outward-facing or too fast to see: a permissive in front of the valve. Already
breached: a trip and an alarm.

Asking or acting has three parallels:

- **Supervisory control and levels of automation** (Sheridan and Verplank): the same action done
  automatically, or proposed for a person to approve, chosen per task. ergostat's ladder is this scale.
- **Auto/manual mode switching** (with bumpless transfer), here **scheduled** on a measured variable, as
  gain scheduling schedules gains.
- **Dual control and active sensing** (Feldbaum): an action that both controls and probes to reduce
  uncertainty, and the value of information. Asking the owner is reading an expensive sensor; intent is an
  unmeasured state estimated by an **observer** from cheap measurements (the owner's past words,
  corrections, overrulings), and the sensor is sampled only when the estimate's uncertainty matters to the
  next action (event-triggered sampling).

Where they fall short: a plant's constraints are written by engineers in numbers before commissioning;
the owner's arrive as sentences, mid-run, and their extent is unclear. Nothing classical *compiles* a
sentence into an interlock, or guesses that a rule about pages also covers docks. That generalisation is
the part only a reasoner provides, and it is where the AI rung belongs: not inside every block, but in the
one place that turns words into structure.

## 3. What ergostat already has

Honestly, a lot of the record and little of the structure.

- **The invariants, as words.** `ergostat.decision` and `ergostat.correction` items (SPEC §5a): the owner's
  words verbatim, reasons, rejected alternatives, scope, proposed → confirmed → superseded. This is the
  CLAUDE.md layer as data, with history.
- **Delivery to sessions.** Projection recipes (§12j) put confirmed decisions and corrections in scope into
  an `ai` block's start; the parity benchmark scores that at 0.625 against 0.03 for nothing.
- **A gate on finished work.** The intent judge (§12i) holds work that passed its tests against confirmed
  decisions, corrections and the owner's messages; image-squeeze's rollout keeps no candidate before a
  verdict. That is already a **permissive**, on one transition, read at the narrow-AI or stand-in rung.
- **Hard constraints on the model itself.** `ergostat check`'s errors refuse the model until fixed (§12):
  the model's own invariants already behave as interlocks. Findings ("missing feedback", "critical goal
  decaying") are its alarms.
- **Manual mode.** `mode: advise` on any machine block (§9.3): commands wait for a person. A `person`
  block with `ask:` is the owner as a sensor-and-actuator, with `not-answering` after an hour.
- **Primitives that can build a permissive.** `compare` gives 1 or 0 on a signal; `expr` multiplies a
  command by it; `select: min` takes the lesser of two commands (§9.2). An interlock is wiring today.
- **Routing.** Messages (§12h) find the parts and work in flight a sentence concerns: that is the
  "neighbourhood of the graph" a new intent touches.

What is missing:

1. **No path from words to structure.** A confirmed decision is only ever read, by an AI block or the
   judge. Nothing turns it into a sensor, a goal or a permissive that a program or a rule can enforce. So
   the cheapest rungs never hold the owner's invariants, and the judge re-reads the same words forever.
2. **No distinction between a setpoint and a constraint** in the model. `docs/patterns.md` names this gap
   twice (a goal on one stock bounding valves on others). A goal `hold: "== 0"` on violations is steered,
   never stopped.
3. **No measured uncertainty of intent, per neighbourhood**, so nothing can schedule ask versus act.
4. **No route from the owner's words to the modeling subsystem.** A message is delivered to work; one that
   changes what the system should aim at reaches no one whose job is to change the model.

## 4. Candidate designs

### A. Invariants compiled down the ladder, by the modeling subsystem

A confirmed decision is an invariant held at the top rung (in words). The modeling subsystem's job,
for each one, is to propose structure that enforces it as low on the ladder as it can: a **sensor** that
measures violations (a check on a branch's diff, a test, a claim check of §12g), and then either a
**soft constraint** (a goal holding violations at 0, served by the block whose work causes them) or a
**permissive** (a `compare` on the sensor gating the valve that would make the violation irreversible).
Which one is decided by the rule of §2: reversibility and observability. The proposal is an ordinary
`ergostat.model-change`, its reason's evidence the decision's id, judged and accepted as any structure
change is (by the owner, by default).

The compiling loop is itself plain SD: stock *invariants in words only* (confirmed decisions no accepted
change cites), flow *compiled*, a goal holding the stock low, and the compiler, an `ai` block on the
modeling subsystem's side, as its controller. What it cannot compile (a decision about tone, about
taste) stays in words, and the intent judge remains the gate for those: the judge is the residual, not
the mechanism. A finding joins the others: **unguarded invariant**, a confirmed decision nothing measures,
as "missing feedback" is a goal nothing serves.

- *Ladder:* compiler on the AI rung, once per decision; enforcement on the program and rule rungs, every
  time.
- *SD view:* the compiling loop (B: uncompiled → compiler → compiled); each guarded flow shows the
  violations auxiliary as an information link to its valve.
- *Control view:* the permissive drawn as an **interlock** on the actuator (a derived role, like
  controller or actuator, never written: a `compare` whose output gates a valve's command), the
  protection layer drawn apart from the regulating loop.
- *Measure:* the share of confirmed decisions enforced below the AI rung; contradictions caught before
  the valve against after (the judge's `held`); "we already decided this" corrections (2.12, 2.13);
  on F3's tasks, rework from violated invariants.

### B. The owner as a scheduled sensor: ask or act

Intent uncertainty is measured per neighbourhood (a goal and its loop, or a kind of work): the rate of
corrections, overrulings, reopenings and not-done-as-meant verdicts there, over the work done there, plus
whether any confirmed decision is in scope at all. That is the observer's error, from measurements
ergostat already records (§12i's `false-done@KIND`, §5a's corrections by kind). It schedules the mode of
the valve that makes work irreversible: low uncertainty, `auto`; high uncertainty, `advise` (the owner
approves), or the owner's `person` block is commanded with the question. The trade-off is two balancing
loops on one valve: one holds rework from guessed intent down, the other holds the owner's attention
spent (questions asked, time to answer) within a budget. Both are goals; ergostat already analyses
competing goals.

The "inferred answer until confirmed" of the old plan becomes what already exists: a block that guesses
prints an `ergostat.decision.proposed` line, its assumption, and the permissive of design A treats an
unconfirmed decision in scope as uncertainty: work may proceed on it up to the irreversible valve, and
waits there.

- *Ladder:* scheduling on the rule rung; the owner on the person rung; the guess on whatever rung made it.
- *Measure:* questions per item against rework from unasked assumptions; compared on F3 with the long
  session's own ratio (questions it asked, corrections it then received, read from the transcript).

### C. The owner's words as a disturbance to the model, routed to modeling with a focus

When a message is about what the system should aim at or avoid (not status, not a correction of one
result), it is not delivered to a worker; it is a disturbance to the *model*, and goes to the modeling
subsystem with the neighbourhood routing found: the matched parts, their loops, and the decisions in
scope, as a context recipe (§12j's `model` and `decisions` parts). The modeler proposes the setpoint
changes, the new goals and the compiled invariants (A) it implies, and may widen to the whole model when
the words touch several neighbourhoods. This is the Coordinator's real act of intent inference: one
sentence, changed structure.

Rate of change follows the protection layers: a new hard constraint takes effect at once at its
permissive (work in flight continues, but nothing crosses the valve), which is where pausing happens,
not mid-session; a setpoint or structure change takes effect at the next run boundary, as a command that
arrives during a run is held, not queued (§9.1, bumpless transfer); running sessions in the neighbourhood
get ergostat's own message (§12h delivery) saying what changed, as a Coordinator would send an update.

### D. A guarded valve, as a library part

The sensor, the permissive, the soft goal and the alarm recur for every invariant. A parametric part
(the check command, the decision it cites, hard or soft) lets the compiler of A write one line per
invariant and keeps the diagrams uniform. It is a packaging of A, not an alternative.

### Sketch (A, with D's shape)

What the modeling subsystem would propose for image-squeeze's "JPEG and PNG only", every part ordinary:

```yaml
auxiliaries:
  format-violations:
    unit: lines
    description: lines on the candidate's branch that bring in another output format (enforces the
      owner's confirmed decision on formats; the change that wrote this cites it)
    sensor:
      run: ./checks/formats.sh run/product candidate   # written by the compiler, a program from now on
      every: 30s

blocks:
  formats-permit:                 # the permissive: 1 while nothing violates
    type: compare
    in: auxiliary.format-violations
    below: 1
  rollout-gated:                  # drawn as an interlock on the rollout's valve
    type: expr
    in: {cmd: block.rollout-controller, ok: block.formats-permit}
    expr: cmd * ok
    out: block.rollout

# the compiling loop, on the modeling side
stocks:
  invariants-unguarded:
    unit: decisions
    sensor: {builtin: ergostat.intent.unguarded, every: 1m}   # confirmed, cited by no accepted change
goals:
  invariants-guarded:
    stock: invariants-unguarded
    hold: "<= 2"
blocks:
  invariant-compiler:
    type: ai
    goal: invariants-guarded
    context: modeler              # decisions in scope, the model's neighbourhood, the checks it can write
    out: flow.compiled
```

## 5. Recommendation

Build **A**, with **C** as the way new intent reaches it and **B** as the ask-or-act policy, in that
order. Reasons:

- A is the flip the owner asks about, and it is what made CLAUDE.md valuable: intent written once,
  enforced without being re-inferred. In ergostat it is enforced lower on the ladder than the harness ever
  could (a program check at every valve, not an agent remembering a file). The complexity stays visible:
  each invariant is a sensor and a gate in both diagrams, not a hidden judgement inside a block.
- It answers break-versus-steer with the disciplines' own rule (layers of protection; soft and hard
  constraints), and keeps the AI rung where generalisation is needed: compiling, once.
- It uses only what exists (decisions, model-change items, the judge, compare/expr, contexts, routing).
  New pieces are a built-in measure (unguarded invariants), a finding, a derived interlock role in the
  control view, and a `decision:` form of evidence for a proposal's reason.
- C gives the modeling subsystem the context it needs (a neighbourhood, or the whole model), and gives the
  rate of change a principled answer: constraints at once at the valve, setpoints at run boundaries.
- B is weaker on its own (an uncertainty estimate from sparse corrections is noisy) but cheap once A's
  permissives exist, since they are the points where asking matters.

On the old plan's Build for 2.3: **retract** the `question` output line and the `ergostat.question` item
kind; a guess is a proposed decision, and a question is a command to the owner's `person` block or a
valve in `advise`. **Change** the "inference session started from the owner's words" into the compiler
and the C-routed modeler, both on the modeling side; their output is structure, not an answer. **Retract**
the stocks *questions open* and *inferred answers unconfirmed* as written; B's measures replace them.

On what was built last night: **keep** decisions and corrections (the invariant record) and recipes (the
modeler's context). **Keep** the intent judge, re-read as the top-rung permissive for invariants not yet
compiled; its `held` count on compiled decisions should fall toward 0, which is A's measure. **Keep**
messages, adding the class that routes to modeling.

## 6. Open questions for the owner

- Should every confirmed decision be a candidate for compiling, or only those the owner marks as rules
  rather than preferences?
- Is the owner's review of each compiled invariant (a structure change) acceptable, or should a compile
  that the intent judge's verdicts already support be accepted automatically?
- When an invariant cannot be checked by a program, is a narrow-AI sensor (a cheap model reading the diff)
  an acceptable enforcement rung, or must it stay with the intent judge?
- Should a hard constraint's permissive close at once on running work in its neighbourhood, or only for
  work started after it is accepted?
- What is the owner's attention budget for questions, as a number we can hold a goal on?
- Should a message that changes what the system aims at go only to the modeling subsystem, or also to the
  work in flight while the model catches up?
