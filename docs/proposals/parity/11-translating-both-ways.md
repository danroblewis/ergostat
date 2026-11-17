# Parity 2.11: translating in both directions

Status: exploration, 2026-11-17. One of sixteen parity explorations
([harness-as-control-system.md](../harness-as-control-system.md) function 11; the first plan's answer is
[harness-parity-plan.md](../harness-parity-plan.md) §2.11). It reframes the gap as the operator interface of a
control system (HCI), and keeps to the standing rule that ergostat adds no pages or panels: what the owner reads
and what the owner does go through the diagrams, the system boxes and the Items pages.

## 1. What the harness actually does here, and why it is valuable

A long session sits between one person and a large, changing technical system, and it is the only interface
the person uses. Two translations run through it all day.

**Words in.** The owner writes short, vague, referential sentences in their own vocabulary: "that one can wait",
"the block diagram still looks poor", "why is the fit page empty", "go ahead", "don't do that again". The session
turns each into one of quite different acts, and the act matters more than the words:

- a **question about state** (it reads the repository, the run, the record, and answers);
- **new work** (it plans and starts something);
- a **change of goal** for work in flight (it re-plans, 2.1);
- a **mode change** (pause, stop, go ahead, ask me first next time);
- a **permission** (2.5);
- a **correction or standing rule** (it writes a memory, 2.13);
- an **observation**: the owner is one of its sensors ("the session froze", "this layout is bad"), reporting
  something no instrument measured.

What produces this: the whole conversation is in the window, so referents resolve ("that one" is the thing it
reported two turns ago); the owner's vocabulary has been learned in context (what "pitiful" means for a
diagram); training supplies pragmatics, the ability to tell a complaint from a request and a question from a
command. Thinking picks the act, and asks when the act is unclear and the cost of a wrong guess is high (2.3).

**State out.** The session compresses an enormous technical state (diffs, test runs, agent reports, logs) into
a few sentences at the owner's level, in the owner's terms, at a moment the owner will read them, saying what
changed, what needs them, what is uncertain. For the owner, the session's reports *are* the state estimate
([harness-as-control-system.md](../harness-as-control-system.md) §5, function 11): their picture of the project
is only as good, as current and as honest as those sentences. It also answers ad hoc: any question, at any
depth, from overview to one line of a log.

Why it is valuable: the owner never has to learn the system's structure to steer it (no tag names, no file
paths, no part references), and never has to go looking for state. The cost of steering is one sentence. A
control system's operator station, by contrast, costs the operator training on its structure.

## 2. The classical parallels, and where they fall short

**The operator interface (HMI) of a process control system.** A control room has had both directions for decades,
and the vocabulary is settled:

- **Displays**, in a hierarchy (ISA-101's high-performance HMI): level 1 an overview of the whole plant
  (key measures against their targets, deviations made salient), level 2 a unit, level 3 a detail (one
  loop's trend, setpoint and output), level 4 diagnostics. Grey by default, colour only for abnormal states.
- **Alarm management** (ISA-18.2, EEMUA 191): what needs the operator, prioritised, acknowledged, shelved,
  with flood rates measured and a rationalisation process that reviews which alarms earn their place.
- **Operator inputs**, a closed, typed set: enter a setpoint, switch a loop's mode (manual, auto, cascade),
  override an output, acknowledge an alarm, grant a permissive. Every input is logged.
- **Shift logs and handover reports**: what happened on the shift, what is outstanding, written for the next
  operator.

**Supervisory control** (Sheridan): the human is an outer loop who plans, teaches, monitors, intervenes and
learns, through displays and controls. The displays act as the human's observer: the operator's mental model of
the plant is estimated from what the screens show.

**System dynamics** has the matching structure for the human side: a **perceived value** is a stock that
adjusts toward the actual value with a time constant (Sterman's perception delays, *Business Dynamics* ch. 11), and
decisions read the perceived, not the actual, value. Reporting is the flow that updates the owner's perceived state;
its cadence sets the delay; the gap between perceived and actual is misperception, the classic source of
overshoot in managed systems.

**Where they fall short of the harness:**

- An HMI's inputs are typed and closed. Nothing turns "that one can wait" into "lower the priority of
  review/2041"; the operator must know the structure to use the controls.
- Displays are designed up front by an engineer, then rationalised slowly. They do not answer a question
  nobody designed a display for, and they do not learn from the questions the operator keeps asking.
- An HMI has no input for an **observation**: the operator's "that pump sounds wrong" goes into a log book, not
  into the model.
- Narrative compression (what changed, why it matters, at this person's level) is a human's job in the
  control room: the shift supervisor's handover.

So the parallels supply the right structure (display levels, alarm discipline, typed inputs, logs, a
perception stock) and miss exactly the two translations: free words into a typed act, and novel questions into
answers, plus the learning loop that turns repeated questions into displays.

## 3. What ergostat already has

Honestly, most of an HMI already exists; what is missing is the translation layer and its loop.

**Displays.**

- The diagrams with every system closed are the model's control panel: each system box shows its measures'
  values, setpoints, health and trend (`show:`, SPEC §4a). This is ISA-101's level 1; opening a box is level
  2; a part's panel (its chart, causes strip, equation, scope) is level 3; the Model page's fit and
  residuals are level 4.
- The side panel's attention list is the alarm list (the goals off, unrouted messages, contradicted claims,
  held verdicts, repeated corrections; `ergostat status --exit-code` for cron).
- The Items pages render an item's markdown fields; the-job's `day/<date>` items carry the **morning brief**
  and the **ledger** (`examples/the-job/job/rhythm.yaml`: two program blocks, each under a goal, `morning-brief-ready`
  and `day-recorded`). That is a shift log, already modelled as stocks, flows and goals.
- `ergostat explain` says the model or a part in sentences; `ergostat status`, `findings`, `items`, and the
  MCP tools of the same names, answer structured questions.

**Inputs.**

- The page's typed writes: Accept, Approve, Dismiss on model changes; Confirm, Dismiss, Supersede, Retire on
  decisions and corrections; a person block's `ergostat block NAME --done` and `mode: advise` approvals (SPEC §9).
- Messages (SPEC §12h, built last night): the owner's words, verbatim, as `ergostat.message` items, routed by
  explicit `about`, by mention, or by a classifier block (a haiku `ai` block answering with `route` lines, or the free
  stand-in), and delivered live into a running session, on resume, or in a block's next input. A message on
  finished work becomes a follow-up carrying the words as its `done_when` (SPEC §12i). Measures:
  `ergostat.messages.unrouted`, `.reached`, `.missed`. The-job models it (`job/messages.yaml`).
- Decisions and corrections (SPEC §5a): the extractor turns the owner's words into proposed `ergostat.decision`
  and `ergostat.correction` items, every quote checked against the owner's turn.
- Manual sensors (`manual: true`, SPEC §6) and MCP `read_sensor`: the owner can be a sensor, but only for a
  stock already in the model.
- A what-if typed over a parameter becomes a model change made by `owner` (SPEC §12e): the only typed path for
  a setpoint or value, and it already goes through the modeling subsystem.

**What is missing.**

1. **The act is never classified.** The router asks *what work does this concern*, not *what is the owner
   doing*. A status question, a new piece of work, a request to change a goal, an observation: each either
   lands on an item as a note or falls into `unrouted`, which is attention for the owner, i.e. the
   translation is handed back to the person it was meant to spare. The-job's run left 19 of 115 messages
   unrouted "by design".
2. **No one answers a question.** A question delivered to a preparer may be answered by it (`answer` lines),
   but nothing answers from the record as such, and the answer is not held to the record.
3. **Reports exist only as project code** (the-job's `bin/rhythm.py`), not as a reusable part, and nothing
   measures whether they keep the owner's picture current.
4. **No loop learns displays.** Questions asked again and again change nothing; the system boxes' `show:`
   is written once by hand.
5. **Observations go nowhere.** "The page froze" is not a reading of any stock, so the modeling subsystem never
   sees it, though it is exactly the evidence of a missing sensor or flow.

## 4. Candidate designs, as control structure

### A. The interpreter as a reference prefilter

In two-degree-of-freedom control, a **prefilter** F shapes the raw reference before it reaches the loop, so the
loop sees an r it can follow. The interpreter is that prefilter for words: it maps a message to one act from a
closed set, the same set an HMI's typed inputs have, plus the two an HMI lacks:

| Act | Where it flows (all existing destinations) |
|---|---|
| query | the answer queue (design B) |
| work | an item of a kind, in its first state (the follow-up path, generalised to new work) |
| goal or setpoint | a model change made by `owner`, through the modeling subsystem (12e) |
| mode (pause, advise, go ahead) | a model change to a block's `mode` or a goal, likewise; or a person block's answer |
| permission | a decision in scope (2.5's gates read it) |
| correction or rule | a proposed correction or decision (5a) |
| observation | a reading of a manual sensor when one fits; else evidence for modeling (design C) |

As structure: a stock *messages not yet translated* (received, no act), drained by one flow per act, each a
valve the interpreter opens. On the ladder, rule first (the page's typed controls and `about` are already acts;
"go ahead" on an item with a waiting ask is a pattern), then a narrow AI (the classifier the routing already
names, answering with the act as well as the target). Rate of change follows from the act: queries and work take
effect at once; anything that touches goals, modes or structure becomes a model change and is applied by the
modeling subsystem between runs, with **bumpless transfer** (the control term for switching a setpoint or mode
without a jump in the output): running work finishes under the old goal, as a Coordinator would not rewrite a
subagent's goal mid-run, and is told by a message (12h) when that is cheaper than redoing it.

Drawn: in Dynamics, the stock and its seven outflows, one of which feeds the model-changes stock of the modeling
subsystem. In Blocks, the interpreter is F on the reference path of every loop the owner sets: the owner's box
(a person block) is the outer controller, and F sits between it and each inner loop's summing junction.

Measured: the share of messages whose act or target the owner changed by hand (re-routed, dismissed follow-up,
dismissed model change); `unrouted` falling toward questions that truly concern nothing.

### B. The reporter and answerer as the owner's observer

The owner's picture is a **perceived state**: a stock per shown measure (or one aggregate) that adjusts toward the
record when a report is read. Reporting is the flow that closes the gap; the loop is balancing (B: gap → report →
perceived state → gap). Two classical refinements:

- **Event-triggered reporting** (send-on-delta sampling, from networked control): a report goes when the change
  since the last report read exceeds a threshold, or when something needs the owner, not on a fixed clock alone.
  The-job's daily brief is the periodic case; the threshold is a parameter the modeling subsystem can tune.
- **Pull samples**: each status question is the owner's observer requesting a sample. Questions per day are the
  observable sign of a gap the push reports did not close. That is the sensor for this loop, and it needs no
  model of the owner's mind.

The answerer drains an *open questions* stock. On the ladder it is a program first: an answer composed from
`explain`, `status`, `items` and the measures, every sentence carrying the reference it was read from (a measure, an
item, an event), so a report is truthful by construction and 2.16's claim checks can test any sentence. A narrow AI
may phrase and select, never assert a number it was not handed. An answer is the message's `answered` step, shown on
the message's item page; a report is an item of a report kind (the-job's `day/` pattern), shown on the Items page.
No page or panel is added.

Measured: open questions' age; questions about something already reported and read (2.9's measure: the report
did not reach or was not clear); answers the owner corrects or that the record contradicts.

### C. The display loop: questions become measures (the dashboarding subsystem)

The answerer's record of questions is evidence for the modeling subsystem. A question asked repeatedly is a
measure the owner wants and the displays lack. The modeling subsystem, focused on the neighbourhood of the parts
the questions touched, proposes one of: add the measure to a system box's `show:` (a display change, ISA-101 level 1
or 2); add an auxiliary or stock with a sensor that measures what the owner keeps asking about ("how many reviews
wait on me" becomes a stock); or, for an observation ("the page froze"), a sensor or a flow the model lacks (a
residual the owner noticed before any instrument did). This is **alarm rationalisation** run as a loop: displays and
attention entries earn their place by the questions they answer, and lose it when nobody looks.

The loop (B): repeated questions → proposals → displays → fewer repeated questions. Over time translation moves
**down the ladder**: an AI interprets a question at first; once it is a measure on a box, a rule answers it; once it
is shown, nothing is asked. That is the agent-first pattern applied to the operator interface.

Rate of change: a display change alters no dynamics and no replay, so the judge could pass it at once; a new stock
or sensor is structure and waits like any other.

Measured: repeated questions per week falling; the share of questions answered by a rule or a reading rather than an
AI; the owner's acceptance rate of display proposals.

### D. An AI front-end only (the status quo, made explicit)

The owner keeps talking to their own Claude Code, which reads ergostat over MCP (`explain`, `status`, `items`,
`context`) and relays words with `message`. Translation then lives in a harness, not in ergostat's structure: no
measures, no learning displays, no parity once the front-end session ends. It stays as a valid way in (the
interpreter must accept whatever it relays), but as the design it simply re-imports the Coordinator.

### The strongest: A, B and C as one subsystem, a library part

One subsystem, `operator` (the control room's own name for the station; it holds no domain words), shipped as a
maintained library part a project includes, like the modeling and messages wiring the examples already carry. A
sketch (names and the two built-in measures marked *new* do not exist yet):

```yaml
systems:
  operator:
    description: the owner's station; words in as acts, the state out at the owner's level
    show: [stock.untranslated, stock.questions-open, stock.picture-gap]

stocks:
  untranslated:                  # received, no act yet
    sensor: {items: ergostat.message, state: received}
  questions-open:
    sensor: {items: ergostat.message, state: routed, where: {act: query}}
  picture-gap:                   # shown measures that moved past their delta since the last report read (new)
    sensor: {builtin: ergostat.report.unseen-change}
  display-proposals:
    sensor: {items: ergostat.model-change, state: checked, where: {kind: display}}

flows:
  as-query:    {from: untranslated, to: questions-open}
  as-work:     {from: untranslated}            # into the kind's first state, elsewhere in the model
  as-change:   {from: untranslated}            # into the modeling subsystem's pending changes
  as-observation: {from: untranslated}
  answered:    {from: questions-open}
  reported:    {from: picture-gap}
  repeat-questions:                            # the same question within a week (new)
    sensor: {builtin: ergostat.questions.repeated, averages: 7d}

goals:
  nothing-untranslated: {stock: untranslated, hold: "<= 0"}
  questions-answered:   {stock: questions-open, hold: "<= 0"}
  picture-current:      {stock: picture-gap, hold: "<= 3"}
  few-repeats:          {flow: repeat-questions, hold: "<= 2"}   # held by modeling, through displays

blocks:
  interpreter: {type: narrow-ai, model: haiku, goal: nothing-untranslated,
                out: [flow.as-query, flow.as-work, flow.as-change, flow.as-observation]}
  answerer:    {type: program, goal: questions-answered, out: flow.answered}
  reporter:    {type: program, goal: picture-current, out: flow.reported}
  # few-repeats is the modeling subsystem's goal: its improver proposes display and sensor changes
```

How we would know parity is reached: on the parity benchmark (F3), the owner's status questions from this session
answered by the answerer from the record and judged against what the session answered; the owner's commands
classified by the interpreter and scored against what the session did with them; and, live, the five measures
above (untranslated age, re-routes by hand, question age, repeated questions, report sentences contradicted).

## 5. Recommendation

Build the `operator` library part (A, B and C together) on top of the messages machinery, in this order: the act
on the route line (A, smallest, unblocks the rest), the answerer citing its readings (B), the display loop through
the modeling subsystem (C). Reasons: every destination already exists, so the work is wiring the acts to them and
measuring the translation, not new kinds; the interface stays the diagrams, the boxes and the Items pages; each
block starts low on the ladder and the loop pushes it lower; and it is the only design where the owner's language
changes the model (through modeling) instead of being consumed and forgotten.

What of the old plan's Build for 2.11:

- **Keep:** reports generated from the record, never from a worker's claims; strengthen it so every sentence
  cites its reading. Keep "rule-based first, an AI session where needed". Keep the measure "the owner's
  corrections of translations".
- **Change:** the intake was "a message becomes an item with its done-when". New work is one act of seven; done-when
  belongs to 2.2 (set by the event that starts the item, or static on its kind). The stock *messages not yet items*
  becomes *messages not yet translated*, with one outflow per act.
- **Retract:** the "intake block" as a new resource; the interpreter is the existing classifier answering one
  more question. Retract 2.9's separate `digest` kind as a new built-in: a report is an item of the library part's
  own kind, as the-job's `day/` already is.
- **Last night's work:** messages (12h) is the inward channel and stays; its `unrouted` state is where this gap
  starts, and the classifier's route line is where the act goes. The follow-up's `done_when` from the words (12i)
  stays. The-job's brief and ledger are the pattern to lift into the library part's reporter. Claims (12g) are how
  the answerer's sentences get checked.

## 6. Open questions for the owner

- Is the closed list of acts (query, work, goal, mode, permission, correction, observation) right, or should the
  modeling subsystem be allowed to learn new ones?
- May a display-only change (a measure added to a box's `show:`) be accepted by the judge at once, since it alters no
  dynamics?
- Is a mode request in words ("pause the developer") a model change through modeling, or does ergostat need a run-time
  operator mode that changes no YAML?
- Should the owner's perceived state be a modelled stock fed by reports read, or is counting status questions enough?
- May a narrow AI phrase answers and reports, provided every number and claim in them is a cited reading?
- Should reports be pushed when the gap passes its threshold, or only shown on the Items page for the owner to pull?
- Should an observation that matches no sensor become a finding for the modeling subsystem, or wait for the owner to
  route it?
