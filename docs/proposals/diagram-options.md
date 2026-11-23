# Diagram options beyond Dynamics and Blocks

Status: recorded 2026-11-16, not planned. The owner decided not to start any of these yet: there
are three views now (Dynamics, Blocks, Wiring), Wiring is to be replaced because it isn't useful,
but every option below adds UI, and building them all would overload it. The user experience and
the user flows (who opens what, when, from where) come first, later. This records the research,
the options, and Claude's opinions and preferences so the decision can be made then.

## The rule the options were judged by

**Each diagram must be one that a community of engineers already recognises.** The owner's
words: "If the Wiring diagram isn't a standard kind of diagram that other engineers would
recognize, then we don't want to use it." Dynamics (System Dynamics, Sterman/Vensim/Stella) and
Blocks (classical control block diagrams) meet this rule. Wiring does not: it is an ergostat
invention.

A second rule, from earlier: a diagram shows **evidence or structure, not hope**. A flow chart
shows what someone hopes will happen; it proves nothing. Diagrams drawn from the record are
preferred.

## What Wiring is, and what it was close to

Wiring draws machines as boxes and an arrow where the record proves one machine's events caused,
or were followed by, another's runs (`causedby`, or a subscription that was heard and acted on),
with event types, counts and when last seen; declared-but-never-seen connections are dashed.

- It is not an **event graph** (Schruben, 1983): there, nodes are *event types* and arrows say
  "this event schedules that one, after this delay, if this condition holds". Wiring is an event
  graph collapsed onto who emitted the events.
- It is close to a **component diagram** (DEVS coupled models: components with ports and
  couplings) and closest to a **service map** (below).
- The raw material for a true event graph already exists: ergostat records `causedby` on events.

## The options, by what they show

| Diagram | Community that reads it | Shows | Drawn from | Fits |
|---|---|---|---|---|
| **Service map** (dependency graph) | SRE / observability (Jaeger, Datadog, Grafana, Kiali) | services and who talks to whom, with rate, errors, duration (RED) on each arrow | observed traffic | agents / machines |
| **Sequence diagram** (UML) | all software engineers | one chain over time: lifelines, messages in order, timestamps | one item's or one incident's events (`causedby`) | a single item |
| **Process map** (directly-follows graph, process mining: van der Aalst; Celonis, Disco, ProM) | business process and operations analysts | states/activities as boxes, arrows with how often items moved between them and how long it took | the event log, by item kind | an item kind |
| **Petri net** (timed, stochastic, coloured) | formal methods, simulation, process mining's algorithms | places (states) with tokens (items), transitions (events) | an item kind's states and `on:` events | an item kind (analysis) |
| **Event graph** (Schruben) | discrete-event simulation modellers | event types, scheduling arrows with delays and conditions | `causedby`, aggregated by type | events |
| **Activity cycle diagram** (Tocher) | British DES tradition | entities alternating between queues (waiting) and activities | an item kind | an item kind |
| **DEVS diagram** (Zeigler) | DEVS / simulation | hierarchical components with ports | the model | systems |
| **Queueing network diagram** | performance engineering | queues and servers with routing | the model | queues |
| **Flow chart / BPMN** | everyone | intended sequence and decisions | design (hope) | not recommended |

Observations that matter:

- **ergostat's items are already discrete-event entities and process-mining cases**: each moves
  through states, driven by events, and the record is an event trace. The Items page's counts per
  state are a Petri net's marking. Sequence diagrams, process maps and Petri nets would all be
  drawn from data ergostat already records.
- **AnyLogic** mixes System Dynamics, discrete-event and agent-based modelling in one model
  ("multimethod"); that is the precedent for one tool holding several perspectives.

## Claude's opinions and preferences

- **Replace Wiring with a service map, named "Map".** It is what Wiring almost is, and SREs read
  it on sight. Arrows labelled the standard way (rate, failures, cause-to-effect delay as median
  and p95); boxes with runs per hour, failure rate, duration; declared-but-unseen edges dashed (Kiali
  shows idle configured edges similarly); event types in the arrow's panel, not on the drawing; no
  rungs, no control or SD vocabulary. This is the one change I'd make first when diagrams are
  revisited, because it removes the unrecognisable view rather than adding one.
- **Sequence diagrams are the best answer to "people want a flow chart".** One item's or one
  incident's chain, from the record, gives the flow-chart feeling with evidence behind it. They
  would open from where the chain already is (an item's page, a Map arrow, a loop's crossing),
  not as a view of their own.
- **For an item kind, a process map over a Petri net.** Same information; the process map is what
  people read, the Petri net is the formal form underneath. If one is built, build the process map.
- **Against event graphs, activity cycle diagrams and DEVS diagrams** for this audience: each is
  recognised only by simulation specialists.
- **Against flow charts and BPMN**: intended sequence, not evidence.
- **Against building several at once.** Each one alone is cheap on data ergostat records; together
  they would crowd the UI. Decide the user flows first: what a person is trying to find out, and
  which single diagram answers it from where they already are.

## If and when these are built, where they would go (no new pages)

- **Map** replaces Wiring on the Diagram page (one of three views).
- **An item kind's process map** on the Items page, in place of the stacked cumulative flow
  diagram, which moves into the causes strip of the stocks counted from that kind (the SD place
  for it).
- **An item's sequence diagram** on the item's page, above its events.

## Related

- [dynamics-bundled-connectors.md](dynamics-bundled-connectors.md): many lines between two modules drawn as one
  in the Dynamics view, the system dynamics way (Stella's bundled connectors), not Blocks' vectors.
- [external-systems.md](external-systems.md): observed controllers.
- [charts.md](charts.md): behaviour over time beside the model.
- [../research/sre-control-systems.md](../research/sre-control-systems.md): the control systems SREs use.
