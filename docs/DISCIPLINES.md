# One file, many disciplines

Recorded 2026-11-16 as a map for future milestones. ergostat's YAML states only what accumulates,
what moves it, what it is held to, and who acts; the collectors record measurements and events.
Each discipline's diagram is a different reading of that same structure and record, not something
extra to write. ✅ drawn today · ⏳ being built · ◻ possible from data already there.

## From the YAML's structure

| Discipline | Diagram | |
|---|---|---|
| System dynamics | Stock-and-flow diagram: stocks, valves, clouds, connectors with polarity, R/B loop markers, goal-seeking structure | ✅ Dynamics view |
| System dynamics | Causal loop diagram: causes and signs without the stock/flow plumbing | ◻ |
| System dynamics | Loop list with polarity (reinforcing, balancing) | ✅ side panel |
| Control engineering | Block diagram: controllers, actuators, processes, sensors, summing junctions, samplers and holds, MIMO processes, nested cascades | ✅ Blocks view · ⏳ above the leaf ([proposals/blocks-levels.md](proposals/blocks-levels.md)) |
| Control engineering | Signal-flow graph (Mason's rule form) | ◻ |
| Systems engineering | Hierarchy and decomposition: systems within systems, modules with ports | ✅ both views |
| Systems engineering | SysML-style block definition and internal block diagrams | ◻ |
| Software engineering | State machine diagram per item kind | ◻ |
| Formal methods | Petri net: item states as places, events as transitions, items as tokens | ◻ |
| SD tool interchange | XMILE export (opens in Stella) | ◻ |

## From the record (what happened)

| Discipline | Diagram or chart | |
|---|---|---|
| System dynamics | Behaviour over time: stocks and flow rates with desired levels | ✅ causes strip |
| System dynamics | Causes strip: a part and what drives it, one time axis | ✅ |
| Control engineering | Scope: setpoint and measurement, control output, error, time off marked | ✅ |
| Control engineering | Loop performance table: time off, recovery, saturation | ✅ Loops page |
| Workflow / lean / Kanban | Cumulative flow diagram per item kind | ✅ Items page |
| Workflow / lean / Kanban | Cycle-time scatter / lead-time distribution | ✅ scatter · ◻ histogram |
| Queueing theory | Little's law check per stock (level = throughput × time in stock) | ◻ |
| SRE / observability | Evidence map of what passed between machines | ◻ (was the Wiring view; `system --wiring` on the command line) |
| SRE / observability | Service map with rate, errors, duration per edge | ◻ |
| Software engineering | Sequence diagram of one item's or incident's chain (`causedby`) | ◻ |
| Process mining | Process map (directly-follows graph) per item kind, object-centric: what one kind's work caused in another's | ✅ Process view |
| Discrete-event simulation | Event graph with observed delays and probabilities | ◻ |
| Statistical process control | Control charts (Shewhart, CUSUM, EWMA) on any measured part | ◻ |
| Documents | Item files: briefs, drafts, transcripts rendered | ✅ |

## From the model and the record together

| Discipline | What | |
|---|---|---|
| System dynamics | Replay and projection over the measured line | ✅ causes strip ([MODEL-TOOLS](MODEL-TOOLS.md#replay-and-projection)) |
| System dynamics | Fit with Theil's breakdown, calibration, sensitivity fans, what-if, extreme-conditions tests | ✅ Model page, panels, Check ([MODEL-TOOLS](MODEL-TOOLS.md#is-my-model-right)) |
| System dynamics | Loop dominance (Loops That Matter), leverage | ✅ a feedback loop's panel, a proposal's effect ([MODEL-TOOLS](MODEL-TOOLS.md#loop-dominance)) |
| System dynamics | Phase plots (stock against stock, or against its flow) | ◻ |
| Control engineering | System identification: gain, time constant, delay per process | ✅ process block's panel ([MODEL-TOOLS](MODEL-TOOLS.md#identification)) |
| Control engineering | Step response, Bode plot, stability margins | ✅ process and controller panels ([MODEL-TOOLS](MODEL-TOOLS.md#margins-closed-loop-step-and-bode)) |
| Control engineering | Tuning suggestions (SIMC), step-test proposals | ✅ controller and process panels ([MODEL-TOOLS](MODEL-TOOLS.md#simc-tuning-and-detuning)) |
| Control engineering | Nyquist, Nichols, root locus, pole-zero maps | ◻ |
| Discrete-event simulation | Simulated item runs: distributions and tails (p95 time to answer a review) | ◻ |
| Model validation | `ergostat check`: structural tests, units, boundary adequacy | ✅ |

About a dozen disciplines and some 34 diagrams and charts: 19 drawn today, the rest possible (the
model tools among them, with where each shows up and what it needs, are in
[MODEL-TOOLS.md](MODEL-TOOLS.md)). Which to build, and where they appear, waits on the user flows
([proposals/diagram-options.md](proposals/diagram-options.md)): more diagrams is not better.
