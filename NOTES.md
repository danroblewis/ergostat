# Ergostat: settled terms

Working notes: what has been decided so far. Not the spec and not the invariants file yet.

**Ergostat**: a device that keeps work going at a steady rate. From the Greek *ergon* (work) and
*-stat* (held in place), like thermostat and homeostat. Ergostat is a general tool for drawing a
control-system boundary around whatever someone wants to keep working: repositories, services, a
team's work, an operating system.

## Work

- **Ergostat is about work, not tasks.** Work is change in the world over time. It can happen with
  no task, on its own, indefinitely after one action, or in answer to unpredictable maintenance
  events.
- Tasks, tickets and issues are **units of work** that users build for themselves, many kinds of
  them. Ergostat ships none and treats none specially.

## Roles

What the control diagram is made of:

- **Sensor**: measures. Never acts.
- **Controller**: decides, to hold something at a setpoint.
- **Valve**: acts on the world. Changes outside ergostat happen only through valves.

**Disturbance**: an input to the system that no valve controls. It is part of the model, either
measured by a sensor or estimated from its effects. Agents can be disturbances too.

**Residual**: what the model fails to explain, the gap between prediction and measurement. A
structured residual is how unmodelled disturbances (and missing dynamics) are found; once found,
a disturbance is added to the model.

## Numbers

- **Equation**: what a flow's rate or an auxiliary's value is, written in the model's own names.
  A stock needs none: it is the integral of its flows.
- **Parameter**: a number an equation names. Every number says where it comes from (its
  **provenance**): declared, estimated from the record, or not known yet.
- **Replay**: the model run over the record, each stock integrated from its flows and every input
  without an equation taken as measured. **Projection**: the same, forward from now. **Fit**: how
  well the replay follows the readings (R², MAPE, Theil's U_M, U_S, U_C).
- **Proposal**: a change to the model the record supports, with its reason, the fit before and
  after, and its edit. The owner accepts or dismisses it; nothing estimated changes the model by
  itself (2026-11-16).

## Agents

- An **agent** fills one or more roles. It is the ordinary meaning of the word: whatever acts on
  someone's behalf, not only an AI.
- Every agent is shown with its **rung** on the ladder:

  | Rung | Agent |
  |---|---|
  | 0 | person |
  | 1 | AI agent (universal) |
  | 2 | narrow AI agent |
  | 3 | decision (e.g. Jev, a short model call with fixed answers) |
  | 4 | program |
  | 5 | rule |
  | 6 | gone: the role is **retired**, the work designed out |

- **Filling a role** (who does it) is different from **adding a role** (designing the factory). A
  role stays the same while the agent filling it changes.
- **The refactor path**: start with the universal agent, the AI agent, filling every role, then
  decompose and move each role down the ladder. A good factory removes the need for the work where
  it can. Rung 6 is the goal, not a failure. There is a deprecation path as well as a refactor path.
- People are agents: they fill several roles and are sometimes disturbances.
- Every agent is held to the same discipline: measured, bounded, and acting only through the
  valves the owner grants.

## People

- **Owner**: the principal. Adds roles and grants valves.
- **Supervisor**: the agent that helps maintain ergostat, build it out, and improve the setup.

## Records

- **Event**: something that happened. Append-only, never edited.
- **Projection** (2026-11-26, the owner's decision; was "kind of item"): a way of looking at a set of events, declared
  under `projections:`. It folds the events whose ids it matches into its own table of the SQLite cache, kept up to
  date as events come in; people and dashboards query those tables. Several projections may look at the same events.
  Never "kind" for a projection.
- **Item**: one id's row of a projection: the fold of that id's events (a projection's items). An event's `item` field
  (a printed line may say `key`, the same) is the id it is about.
- **Handlers** (2026-11-27, the owner's design): a projection reads the events its `match:` holds for, keys each to an
  item (`key:`), and says per event type, field by field, what the event does to the item (`events:`), each value an
  expression (`add(1)`, `data.reason`, `set('done')`) of built-in fold functions and the model's own Python
  `functions:`. Events are facts; the handlers are the projection. `id:`, `on:` and `fold:` are gone.
- **Metrics**: time-series measurements. Kept in a store of their own, separate from events,
  because there will be few events and many metrics.
- **Every metric goes through PromQL, recorded in VictoriaMetrics** (2026-11-25, the owner's decision). VictoriaMetrics
  is the only metrics store and is required: the SQLite readings store, its roll-up tiers and `ergostat migrate` are
  gone. With none answering, ergostat says how to start one and does not run; it never keeps readings anywhere else.
  The events and the item index stay in the state directory.
- **Two data sources: `promql` and `sql`** (2026-11-25, the owner's decision). ergostat has exactly two: `promql`, every
  metric, recorded in VictoriaMetrics, and `sql`, all item data, projected into SQLite (the item views). "All things
  that are not external systems are stored in promql or sql." The built-in shortcuts (item fields, item moves, items
  per state, events, metric series, a frequency response) are query generators, syntactic sugar in YAML and on the
  dashboard: each writes a PromQL or SQL query and asks it, and the answer shows what it asked. "They are query
  generators. They are not data sources, not at all." The listing always shows both, an unavailable one with its
  reason, never dropping one silently. Removed: the `model` and `analysis` sources, the external Prometheus and SQL
  data sources, and declaring a dashboard source under `sources:` (a model error that says why). Sensors that read
  external systems stay: they are sensors, and `sources:` holds only their connections.
- Pub/sub may be how ergostat runs its own processes and their communication. The event bus is how
  the relationships between agents are read off.

## The diagram

- **Control-theory diagrams are a primary part of the product.**
- **One big control system**: pan, zoom, and group parts into systems. Truly disconnected parts can
  be found by graph analysis and drawn apart.

## Design stance

- **Discovery comes later**: inferring a control system from metrics alone (system dynamics, Kalman
  filters, LNA). Until then, the design toes the line between what is defined and what is inferred
  from data, so that discovery can be added.
- **The first use case is AI agents** as a general solution to every role.
- **Ergostat adds nothing of its own accord**: no built-in agents, no built-in units of work.
