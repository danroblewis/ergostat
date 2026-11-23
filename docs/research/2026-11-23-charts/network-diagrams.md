# Network, graph and node-link diagrams for ergostat

Research of 2026-11-23. This report covers the family the chart catalog ([`catalog.md`](catalog.md)) left out. Code claims were read at commit `5bc8236c`. No repository was changed and nothing ran against a live system. The checks in §2 ran on synthetic data, in a scratch directory.

**Evidence labels.** Every reference in §15 carries one:

- **[O] opened:** I read the relevant passage for this report.
- **[R] record:** I confirmed that the work exists (author, year, title) from its Crossref record or publisher page. What it says is from my knowledge of it.
- **[S] search:** seen only in a search result or a secondary source.
- **[K] known:** from memory, with no record checked. Treat as a lead.

`[unsure]` marks a claim I could not settle. **[measured]** marks a result from §2.

## 1. Summary

**The decision.** Add one result shape, `graph`, and one panel form that draws only named diagram kinds. Build **fourteen** diagrams on it, of which five already exist in some form. Do not build a general graph explorer. Of the 99 diagrams and encodings assessed, 14 diagrams and one layout are must-haves, 27 are useful, 45 are niche and 12 should not be built.

**Six findings change what should be built.**

1. **The catalog's "a graph is not a result shape" should be reversed, narrowly.** It was right that Dynamics and Blocks keep their own renderers. But `process.py`, `precedence.py` and `graph.py` already return three incompatible graphs, and a query-driven panel cannot draw any of them. A pair of tables cannot state what a reader most needs to know: **whether a path through two edges actually happened** (§12.1).
2. **The Process view today reports concurrency as rework.** On a synthetic log of 100 jobs where *no job repeated a step*, and three steps ran in random order, `process.py` flagged **3 lines and 94 passages as rework** [measured]. A later-to-earlier line is rework only if the step actually repeats. This is the first thing to fix, because rework is a number people act on.
3. **A process map shows paths nobody took.** Five routes through one shared step draw as 25 paths, of which 20 (80%) never happened [measured]. Any answer to "what path does work take?" must come from **variants**, not from following arrows.
4. **The obvious graph metric finds the wrong bottleneck.** In a five-station line whose true bottleneck is station 4 (95% utilised, mean wait 19.2), betweenness centrality picks station 3 (71% utilised, wait 1.8) [measured]. Bottlenecks come from utilisation and queueing measurements. Centrality should not be offered for this question.
5. **Granger "causal maps" should not ship as a picture.** With eight series and **no** real link between them, a shared driver produced 41 of 56 possible edges. Even fully independent series gave at least one false edge in 96% of runs [measured].
6. **Layouts must not be recomputed while scrubbing time.** Adding *one* edge to a 60-node graph moved 88% of nodes under ELK layered, 80% with model order and 100% under stress [measured]. Time scrubbing needs one fixed layout over the union of the window.

**The missing diagrams that matter most** were not on the brief's list: the **wait-for graph** (E11), the most direct answer to "what is holding everything up?"; **dominators and articulation points** (E12), which find single points of failure; and the **Marey chart** (C8), which shows overtaking, stalls and batching in a way no aggregate graph can.

**Build order:** fix rework and name the graph's limits → `graph` shape → wait-for and impact queries → variants and declared-versus-observed → service map → graph diff and time scrubbing.

## 2. Checks run for this report

All used synthetic data with fixed seeds. They test specific claims and say nothing about any real system's rates.

| # | Check | Result |
|---|---|---|
| X1 | Routes `A→B→C` and `D→B→E`, drawn as a first-order graph | 4 paths drawn, 2 real. With *k* routes through one hub: *k²* drawn, *k* real (5 routes: 80% invented) |
| X2 | *n* steps run once each, in any order | `n(n-1)` directed lines. Half run against any fixed order: 5 steps give 20 lines, 10 "backward" |
| X3 | The real `process.py`, 100 jobs, 3 concurrent steps, none repeated | 14 lines, **3 flagged rework, 94 passages** |
| X4 | The real `process.py` with `paths=0.5`, where 20 of 100 jobs take a rare middle step | The first step shows 100, its only remaining line 80. The 20 vanish with no line (van der Aalst's "invisible gaps") |
| X5 | Five-station tandem queue, arrival rate 1, service rates 1.6, 1.5, 1.4, **1.05**, 1.7; 200,000 jobs | Utilisation .63, .67, .71, **.95**, .59. Mean wait 1.05, 1.35, 1.81, **19.22**, .85 (theory 1.04, 1.33, 1.79, 19.05, .84). Betweenness 0, 3, **4**, 3, 0 |
| X6 | Critical path versus capacity: `a(3)` then `b(4)` and `c(4)` in parallel, then `d(2)` | Critical path 9. With one worker the work takes 13, 44% longer than the path says |
| X7 | Pairwise Granger at 5%, 8 series, 500 samples, lag 1, 200 runs, 56 possible edges, **no true edge** | Independent AR(1): 5.2% false, at least one false edge in 96% of runs. Independent random walks in levels: 17.1%. One shared driver at different lags: **73.9%, 41 edges** |
| X8 | Chance a head-sampled trace shows a given edge | At 1/1024: 2.3% for an edge called 24 times in the window, 62% for 1,000 calls. At 1%: 21% for 24 calls |
| X9 | ELK timing in Node 24, one laptop, synthetic DAG-like graphs, one run each | Table in §12.3 |
| X10 | ELK stability: add one edge to a 60-node, 90-edge graph; median of 8 graphs; "moved" means more than 45 px, half a node's width | Layered 88% moved; layered with model order 80%; stress 100% |

## 3. How to read the entries

Each entry's heading gives the name, aliases, priority and whether ergostat already has it. The fields are:

- **Q:** the analytical question and the decision it supports
- **Read:** how an expert reads it, what good and bad look like
- **Beyond:** what it does that a plain chart or a stock-and-flow diagram cannot
- **Needs:** the data or model required
- **Shape:** the input shape, using the five existing shapes plus `graph` (§12.1)
- **Get:** how to obtain it
- **Misuse:** the common error and how the tool should prevent it
- **Ops:** whether it applies to software and operations, with one example
- **Why:** one sentence on the priority
- **Refs:** sources

Priorities: **must-have** (a core operating question goes unanswered without it), **useful** (changes a decision in a common situation), **niche** (real, but for a specialist or a rare case), **don't build** (known, and would not change a decision here; some keep a one-line alternative).

## 4. Concurrency and discrete-event

### A1. Place/transition Petri net · *P/T net* · useful (as an engine), niche as a picture
- **Q:** Can this workflow deadlock, or lose or duplicate work? Decides whether a declared workflow is safe to run.
- **Read:** Circles are places, bars are transitions, dots are tokens. Check boundedness, liveness and reachability. Bad: a place that grows without bound, or a marking with nothing enabled.
- **Beyond:** Represents concurrency, synchronisation and conflict exactly, which a state diagram must enumerate and a stock-and-flow diagram averages away.
- **Needs:** Places, transitions, arcs, an initial marking.
- **Shape:** `graph` (bipartite). Analysis results are a `table`.
- **Get:** From an item kind's `states` and `on:` events, plus leases as resource places.
- **Misuse:** Treating a net compiled from a state list as proof about the real system. Label the result "of the declaration".
- **Ops:** Yes. A merge step needing both a passed build and an approval is an AND-join.
- **Why:** The analysis catches real workflow errors, but operators will read a process map, not a net.
- **Refs:** [Murata 1989](https://doi.org/10.1109/5.24143)

### A2. Workflow net with soundness check · *WF-net* · useful (a check, not a view)
- **Q:** From every reachable state, can an item still finish, cleanly, with every step usable? Decides whether a kind's declaration is accepted.
- **Read:** Three verdicts: option to complete, proper completion, no dead transitions. A failure names a state or transition.
- **Beyond:** Proves a property over *all* executions, including those not yet seen.
- **Needs:** A declared workflow with one start and one end.
- **Shape:** `table` of findings. No diagram needed.
- **Get:** Compile from the model, run in `ergostat check`.
- **Misuse:** Reading "sound" as "good". Soundness says nothing about speed or whether the process is the right one.
- **Ops:** Yes. Finds a review state with no exit on rejection.
- **Why:** A cheap structural test in the place ergostat already runs them.
- **Refs:** [van der Aalst 1998](https://doi.org/10.1142/S0218126698000043)

### A3. Coloured Petri net · *CPN* · niche
- **Q:** Does the workflow stay correct when tokens carry data? Supports formal design of a protocol.
- **Read:** Typed tokens and arc expressions; analysed through state spaces.
- **Beyond:** Compact modelling of data-dependent concurrency.
- **Needs:** Types, guards, arc expressions.
- **Shape:** Not drawn. **Get:** Hand modelling.
- **Misuse:** State-space explosion and a model that outlives the system. Do not offer it.
- **Ops:** Protocol verification, such as a lease hand-off; rarely by operators.
- **Why:** Needs a modelling specialist, and TLA+-style tools serve this audience better [unsure].
- **Refs:** [Jensen & Kristensen 2009](https://doi.org/10.1007/b95112)

### A4. Timed and stochastic Petri nets · *TPN, SPN, GSPN* · niche
- **Q:** What throughput does this concurrent workflow achieve? Supports capacity choices where synchronisation matters.
- **Read:** Transitions carry delays or rates; a GSPN maps to a CTMC for steady-state measures.
- **Beyond:** Captures fork-join and shared resources, which product-form queueing networks do not.
- **Needs:** A net plus fitted delay distributions.
- **Shape:** `table`, `distribution`. **Get:** Simulation.
- **Misuse:** Exponential assumptions on heavy-tailed work durations. Require a fit check.
- **Ops:** Worker pools with fork-join reviews. ergostat's item simulation answers the same question.
- **Why:** The simulation already planned gives the answer without a new notation.
- **Refs:** [Molloy 1982](https://doi.org/10.1109/TC.1982.1676110), [Ajmone Marsan et al. 1984](https://doi.org/10.1145/190.191), [David & Alla 2010](https://doi.org/10.1007/978-3-642-10669-9)

### A5. Reachability and coverability graphs · niche
- **Q:** Which global states can the system reach? Supports debugging a failed soundness check.
- **Read:** Nodes are markings; a dead end is a deadlock. An ω in a coverability tree marks an unbounded place.
- **Beyond:** Enumerates futures rather than history.
- **Needs:** A Petri net or automaton.
- **Shape:** `graph`, only for a small counterexample. **Get:** Computed from the model.
- **Misuse:** Drawing the whole graph, which explodes combinatorially. Show only the shortest path to the failure.
- **Ops:** Yes, as the witness for A2.
- **Why:** The counterexample path matters; the full graph never does.
- **Refs:** [Murata 1989](https://doi.org/10.1109/5.24143), [Karp & Miller 1969](https://doi.org/10.1016/S0022-0000(69)80011-5)

### A6. GRAFCET / Sequential Function Chart · *SFC* · don't build
- **Q:** What is the step sequence of a PLC program? Supports industrial control programming.
- **Read:** Steps, transitions, actions, in a fixed standard form.
- **Beyond:** Direct mapping to executable PLC logic.
- **Needs:** A sequential controller program.
- **Shape:** None. **Get:** None available.
- **Misuse:** Importing the notation for prestige; it would mean nothing to its audience here.
- **Ops:** No. Software runbooks are not PLC programs.
- **Why:** Its community does not run software systems.
- **Refs:** IEC 60848; IEC 61131-3

### A7. Event graph (Schruben) · niche
- **Q:** Which event schedules which, after what delay and condition? Supports building a discrete-event simulation.
- **Read:** Nodes are event types; arrows carry delay and condition.
- **Beyond:** The most compact statement of a DES model.
- **Needs:** Event types, scheduling relations, delays.
- **Shape:** `graph`. **Get:** `causedby` aggregated by event type.
- **Misuse:** **The name collides:** Petri-net literature uses "event graph" for marked graphs [Commoner et al. 1971](https://doi.org/10.1016/S0022-0000(71)80013-2). An observed `causedby` count is also not a scheduling rule. Label it as observed.
- **Ops:** Partly. "`build.failed` leads to `fix.started` after 40 min, 70% of the time."
- **Why:** The service map and sequence diagram carry this information for readers who are not simulation specialists.
- **Refs:** [Schruben 1983](https://doi.org/10.1145/182.358460)

### A8. DEVS coupled-model diagram · niche
- **Q:** How do hierarchical simulation components couple? Supports composing simulations.
- **Read:** Components with input and output ports.
- **Beyond:** A formal semantics for modular simulation.
- **Needs:** Atomic and coupled models. **Shape:** None. **Get:** Model.
- **Misuse:** It resembles a block diagram and would be confused with Blocks. Do not add it.
- **Ops:** Only for those building simulators.
- **Why:** Its audience is simulation researchers.
- **Refs:** Zeigler et al.

### A9. Process algebra views · *CCS, CSP, labelled transition systems* · don't build
- **Q:** Are two concurrent specifications equivalent? Supports protocol verification.
- **Read:** Terms and labelled transitions; equivalence by bisimulation or refinement.
- **Beyond:** Compositional reasoning about communication.
- **Needs:** A formal specification. **Shape:** None. **Get:** None available.
- **Misuse:** Has no operational reading for someone on call.
- **Ops:** Only in protocol design.
- **Why:** Would change no decision made in this product.
- **Refs:** Hoare 1978

### A10. BPMN · *Business Process Model and Notation* · don't build as an editor; accept as import at most
- **Q:** What is the intended business process? Supports agreement between business and IT.
- **Read:** Pools, lanes, tasks, gateways and events, in a standard notation.
- **Beyond:** A widely recognised notation with precise gateway types.
- **Needs:** A hand-authored process.
- **Shape:** None. **Get:** External file.
- **Misuse:** It records what people hope happens. It fails the "evidence or structure, not hope" rule when shown alone.
- **Ops:** Sometimes as the *declared* side of a conformance check (C4), for organisations that already hold BPMN.
- **Why:** ergostat's item kinds already are the declaration.
- **Refs:** [OMG 2014](https://www.omg.org/spec/BPMN/2.0.2/About-BPMN)

### A11. UML activity diagram · don't build
- **Q:** What is the intended control flow? **Read:** Actions, forks, joins, decisions. **Beyond:** Token semantics close to Petri nets.
- **Needs:** Hand authoring. **Shape:** None. **Get:** None.
- **Misuse:** The same as A10: a statement of intent that looks like evidence.
- **Ops:** Design documents only.
- **Why:** A process map from the record answers the same question with evidence.
- **Refs:** [OMG 2017](https://www.omg.org/spec/UML/2.5.1/About-UML)

### A12. Sequence diagram · *message sequence chart, MSC, UML sequence* · **must-have** · not built
- **Q:** In what order did things happen for this one item or incident, and who waited on whom? Decides where to look next.
- **Read:** Lifelines across, time down, arrows as messages. Long vertical gaps are waits; a message with no reply is a suspect. Good: a short chain. Bad: ping-pong between two parties.
- **Beyond:** Shows one real execution with order and timing. No aggregate can.
- **Needs:** Ordered events with a source, an item and `causedby`.
- **Shape:** `graph` with `time.mode: events`.
- **Get:** The event log, following `causedby` from an item or event, bounded by hops.
- **Misuse:** Clock skew draws arrows going backward. Order by causality first and flag skew. One example is not typical behaviour, so link to its variant's frequency.
- **Ops:** Yes. One merge request: queued, build, flaky failure, retry, review, merge, with the 3-hour wait visible.
- **Why:** The most direct evidence for "why isn't this done?", and the data is already recorded.
- **Refs:** [ITU-T Z.120 (2011)](https://www.itu.int/rec/T-REC-Z.120), [OMG 2017](https://www.omg.org/spec/UML/2.5.1/About-UML), [Lamport 1978](https://doi.org/10.1145/359545.359563)

### A13. Space-time diagram · *Lamport diagram, happens-before graph* · niche
- **Q:** Which events could have influenced which? Supports debugging races across replicas.
- **Read:** Process lines and message arrows. Two events with no causal path are concurrent, whatever their timestamps.
- **Beyond:** Shows partial order honestly, where a timeline implies a total order.
- **Needs:** Logical clocks or explicit causal links. **Shape:** `graph`. **Get:** `causedby`, vector clocks.
- **Misuse:** Reading wall-clock order as causal order.
- **Ops:** Yes, for distributed-systems debugging. Use the A12 renderer with a "causal order" option rather than a new diagram.
- **Why:** A mode of the sequence diagram, not a diagram of its own.
- **Refs:** [Lamport 1978](https://doi.org/10.1145/359545.359563), [Beschastnikh et al. 2016](https://doi.org/10.1145/2927299.2940294)

### A14. Swimlane diagram · *cross-functional flowchart* · useful (as a grouping)
- **Q:** Where does work cross between people or teams? Decides which hand-offs to remove.
- **Read:** Each lane is an owner. Count crossings and the wait at each one.
- **Beyond:** Makes hand-offs visible, which a stock-and-flow diagram aggregates away.
- **Needs:** Each step attributed to an actor or team.
- **Shape:** `graph` with node `group`, or a `table` of spans.
- **Get:** Moves joined to the acting machine.
- **Misuse:** A hand-drawn swimlane is hope. Draw from the record, and do not use it to rank people.
- **Ops:** Yes. An incident moving between on-call, database team and vendor.
- **Why:** Worth having as a group-by on the Timeline and sequence diagram, not as another diagram.
- **Refs:** [OMG 2017](https://www.omg.org/spec/UML/2.5.1/About-UML)

### A15. Activity cycle diagram · *ACD* · niche
- **Q:** How do entities alternate between waiting and being served? Supports building a DES.
- **Read:** Alternating queue and activity nodes in closed cycles.
- **Beyond:** Forces every wait to be explicit.
- **Needs:** Entity life cycles. **Shape:** None. **Get:** Item kind.
- **Misuse:** Readers outside the British DES tradition will not recognise it, which fails the recognised-diagram rule for this audience.
- **Ops:** In principle; a process map serves better.
- **Why:** Recorded in `diagram-options.md`, and nothing here changes that view.
- **Refs:** Tocher 1963

## 5. State

### B1. Finite state machine diagram · *state diagram, FSM* · useful
- **Q:** What states may this kind of item be in, and what moves it? Decides whether a move is legal.
- **Read:** States and labelled transitions. Bad: a non-final state with no exit, or an unreachable state.
- **Beyond:** States the rules completely, which the record cannot (it shows only what occurred).
- **Needs:** The kind's `states` and `on:`.
- **Shape:** `graph` (`evidence: declared`).
- **Get:** The model's structure.
- **Misuse:** Showing it alone implies work obeys it. Draw it as the declared half of C4.
- **Ops:** Yes. `queued → building → passed|failed → merged`.
- **Why:** Essential as the reference for conformance, of little use as a standalone picture.
- **Refs:** [Harel 1987](https://doi.org/10.1016/0167-6423(87)90035-9)

### B2. Harel statechart · *hierarchical state machine, UML state machine* · niche
- **Q:** How do nested and parallel modes behave? Supports designing a complex controller.
- **Read:** Depth (superstates), orthogonal regions, broadcast events.
- **Beyond:** Avoids the state explosion of a flat FSM.
- **Needs:** A hierarchical declaration, which item kinds do not have. **Shape:** `graph` with `parent`. **Get:** Model, if declared.
- **Misuse:** Semantics differ between dialects; name the one used.
- **Ops:** Yes for a controller with modes (normal, degraded, failover). Blocks' modes may be enough.
- **Why:** Worth having only if ergostat ever adds nested item states.
- **Refs:** [Harel 1987](https://doi.org/10.1016/0167-6423(87)90035-9)

### B3. Observed state-transition diagram with rates · useful
- **Q:** How often does work move between states, and how long does it stay? Decides which transition to study.
- **Read:** Edge is a rate or probability, node is holding time. Compare with B1.
- **Beyond:** Gives routing probabilities, which stock-and-flow diagrams only imply.
- **Needs:** Moves with timestamps. Open items for censored holding times.
- **Shape:** `graph`.
- **Get:** SQL over `moves`; or PromQL over a `from`/`to` counter once that exists. An arrival has no `from`, and Prometheus treats an empty label as absent, so entries need their own label value.
- **Misuse:** Holding times from completed stays alone omit stuck work (catalog finding 4).
- **Ops:** Yes. 22% of builds go `failed → queued`.
- **Why:** It is the Process view in `states` mode; add rates and censoring rather than a new diagram.
- **Refs:** [van der Aalst 2016](https://doi.org/10.1007/978-3-662-49851-4)

### B4. Markov chain / CTMC, absorbing analysis · useful
- **Q:** What share of items finish, how many visits does each state get, and how long until absorption? Decides whether rework or abandonment dominates.
- **Read:** Fundamental matrix gives expected visits. Good: most mass reaches `done` in about one visit per state.
- **Beyond:** Computes long-run consequences of routing, including loops, from transition counts.
- **Needs:** Transition counts; holding-time rates for a CTMC.
- **Shape:** Input `graph`; output `table`.
- **Get:** SQL over `moves`.
- **Misuse:** The Markov assumption fails when the third attempt differs from the first. Test by conditioning on visit number, and refuse if it fails. Holding times are rarely exponential, so prefer a semi-Markov reading.
- **Ops:** Yes. Expected build attempts per merge = 1.6.
- **Why:** Turns a process map into a number that supports a decision.
- **Refs:** [Bolch et al. 2006](https://doi.org/10.1002/0471791571)

### B5. Hidden Markov model · *HMM* · niche
- **Q:** Which unobserved mode generated these signals? Supports regime detection.
- **Read:** Hidden states, transition and emission probabilities.
- **Beyond:** Infers modes never logged.
- **Needs:** Long multivariate records. **Shape:** `series` of state probabilities. **Get:** Fit.
- **Misuse:** The fitted states have no inherent meaning, yet people name them. Show as a hypothesis.
- **Ops:** Possibly for "degraded" regimes; a state band on a time chart is the right display, not the graph.
- **Why:** The graph of hidden states tells an operator nothing.
- **Refs:** [Rabiner 1989](https://doi.org/10.1109/5.18626)

### B6. Markov decision process diagram · *MDP* · niche
- **Q:** Which action in each state maximises long-run value? Supports policy design.
- **Read:** States, action nodes, probabilistic outcomes, rewards.
- **Beyond:** Compares policies rather than describing one.
- **Needs:** Rewards and action-conditional transitions, usually unidentified from observational logs.
- **Shape:** `table` (policy). **Get:** Model plus experiments.
- **Misuse:** Estimating action effects from logs where actions were chosen by a policy is confounded.
- **Ops:** Autoscaling research. Rarely identified in practice.
- **Why:** The data needed seldom exists.
- **Refs:** [Puterman 1994](https://doi.org/10.1002/9780470316887)

### B7. Hybrid automaton · niche
- **Q:** How do discrete modes and continuous dynamics interact? Supports verifying switched controllers.
- **Read:** Modes with flow equations, guards and resets.
- **Beyond:** The correct formalism for a controller with mode switches.
- **Needs:** Mode-specific dynamics. **Shape:** `graph`. **Get:** Model.
- **Misuse:** Verification is undecidable in general, so a picture implies more assurance than exists.
- **Ops:** Autoscaler with cooldown and scale-to-zero. Blocks should show the modes in its own notation.
- **Why:** Conceptually apt, but it would duplicate Blocks for a specialist audience.
- **Refs:** [Alur et al. 1995](https://doi.org/10.1016/0304-3975(94)00202-T), [Henzinger 1996](https://doi.org/10.1109/LICS.1996.561342)

## 6. Process mining from event logs

### C1. Directly-follows graph · *DFG, process map* · **must-have** · exists, needs fixes
- **Q:** What steps does work go through, how often, and where does time go? Decides which step or hand-off to investigate.
- **Read:** Nodes are activities, edges are "immediately followed by", with count or median time. Experts filter, then check variants before believing a path.
- **Beyond:** Discovers real routes, rework and skipped steps from the log with no model.
- **Needs:** Case ID, activity, timestamp.
- **Shape:** `graph` with `paths_real: false`.
- **Get:** `process.py`. SQL over `moves` must fold leases out as `process.py` does, or the lease state appears as a step.
- **Misuse:** Van der Aalst names three traps [van der Aalst 2019](https://www.vdaalst.com/publications/p1101.pdf): concurrency reads as loops, frequency filtering leaves "invisible gaps", and times on edges are conditional. All three reproduce here (X1, X3, X4). Prevent: count **rework only on a repeated step**, mark concurrent pairs, state what the filter removed on the affected node, and open variants from any path.
- **Ops:** Yes. A merge pipeline's `review → changes → review` loop with its cost in hours.
- **Why:** The entry point for "what actually happens?", and the current rework flag can mislead.
- **Refs:** [van der Aalst 2019](https://www.vdaalst.com/publications/p1101.pdf), [van der Aalst 2016](https://doi.org/10.1007/978-3-662-49851-4)

### C2. Heuristic net and fuzzy map · *Heuristics Miner, Fuzzy Miner* · niche
- **Q:** What is the main behaviour of a noisy log? Supports simplifying a spaghetti map.
- **Read:** Dependency scores decide which edges remain; fuzzy maps cluster minor activities.
- **Beyond:** Handles noise better than a raw DFG.
- **Needs:** An event log and tuned thresholds.
- **Shape:** `graph`. **Get:** Log.
- **Misuse:** Threshold choice silently changes the story, and heuristic nets may be unsound.
- **Ops:** Large, messy logs. Item kinds with declared states are rarely so messy.
- **Why:** Variants plus the existing filter cover this at ergostat's scale.
- **Refs:** Weijters et al. 2006, [Günther & van der Aalst 2007](https://doi.org/10.1007/978-3-540-75183-0_24)

### C3. Inductive miner process tree · *IMf* · useful (backend for concurrency)
- **Q:** Which steps are really parallel, exclusive or looped? Decides whether a line in the map is real order.
- **Read:** A block-structured tree of sequence, choice, parallel and loop operators.
- **Beyond:** Guarantees a sound model and represents concurrency, which a DFG cannot.
- **Needs:** An event log.
- **Shape:** `table` of concurrent pairs; a tree only if drawn.
- **Get:** An implementation over the log. A much cheaper first step: mark a pair concurrent when both orders are common and neither step depends on the other.
- **Misuse:** It can overgeneralise ("flower" models that allow almost anything). Report precision.
- **Ops:** Yes. Lint, test and scan run in parallel, so no line between them means order.
- **Why:** The fix for C1's worst error needs only its concurrency detection.
- **Refs:** [Leemans et al. 2013](https://doi.org/10.1007/978-3-642-38697-8_17)

### C4. Conformance view · *alignment, token replay, declared versus observed* · **must-have** · not built
- **Q:** Does work follow the declared path? Where does it deviate, how often, at what cost? Decides whether to fix the process or fix the declaration.
- **Read:** The declared graph with deviations overlaid: moves in the log only (undeclared), moves in the model only (skipped). Report **fitness** and **precision** together, since a model allowing everything has perfect fitness.
- **Beyond:** The only diagram that compares intent with evidence on one structure.
- **Needs:** A declared model and an event log.
- **Shape:** `graph` with `evidence` per edge: `both`, `observed_only`, `declared_only`.
- **Get:** Declared states against `moves`. Start with **edge-level** deviation. Full alignments are costly and only needed for a per-item explanation.
- **Misuse:** Treating every deviation as a violation. Many are legitimate exceptions, so show their outcome (did those items finish faster?).
- **Ops:** Yes. 12% of merges skipped the review state; those had a higher revert rate.
- **Why:** It directly answers one of the owner's five named questions.
- **Refs:** [Carmona et al. 2018](https://doi.org/10.1007/978-3-319-99414-7), [van der Aalst et al. 2012](https://doi.org/10.1002/widm.1045)

### C5. Dotted chart · useful
- **Q:** What is the temporal pattern across all cases? Reveals batching, shift effects, arrival bursts and drift.
- **Read:** Each row a case, each dot an event, colour for activity. Vertical lines are batches; diagonal bands are steady flow.
- **Beyond:** Shows every event at once, without aggregation.
- **Needs:** Case, activity, timestamp.
- **Shape:** `points` with `group`.
- **Get:** SQL over `moves`.
- **Misuse:** Row order creates the pattern. Default to first-event order, and state it.
- **Ops:** Yes. Reveals that reviews happen only in two daily batches.
- **Why:** Cheap with existing shapes and catches batching, which aggregate maps hide.
- **Refs:** Song & van der Aalst 2007

### C6. Variant explorer · *trace variants, path analysis* · **must-have** · not built
- **Q:** What complete paths does work really take, and which are slow or fail? Decides which path to standardise or remove.
- **Read:** Ranked list of exact sequences with count, share, median and p90 duration, outcome. Good: few variants cover most work. Bad: a long tail of one-offs, or a common variant far slower than the main one.
- **Beyond:** The honest answer to "what path?": unlike C1, each row **really happened**.
- **Needs:** Ordered activities per case.
- **Shape:** `table` (variant, count, duration, outcome).
- **Get:** SQL over `moves`, grouped by the ordered state sequence. Collapse repeats as an option, and report it.
- **Misuse:** With concurrency, each ordering is a separate variant. Canonicalise concurrent steps. Count open items as open, not as a short variant.
- **Ops:** Yes. Top three merge paths cover 81%; the fourth takes 5× as long.
- **Why:** It removes the invented-path error at almost no cost.
- **Refs:** [van der Aalst 2016](https://doi.org/10.1007/978-3-662-49851-4)

### C7. Object-centric process map · *OCPM, OCEL* · useful · partly exists
- **Q:** How do different kinds of object interact, such as one epic and many tickets? Decides where fan-out and joins stall.
- **Read:** One map per object type, joined where events share objects.
- **Beyond:** Avoids convergence (one event counted many times) and divergence (order lost) when flattening to a single case ID.
- **Needs:** Events related to several objects.
- **Shape:** `graph` with node `group`.
- **Get:** The Process view's per-kind maps and `causedby` lines.
- **Misuse:** Counts summed across kinds double-count. Keep per-kind totals.
- **Ops:** Yes. A release waits on the last of its 14 tickets.
- **Why:** ergostat is already object-centric, so the remaining work is the join-wait measurement.
- **Refs:** [van der Aalst 2019](https://doi.org/10.1007/978-3-030-30446-1_1), [OCEL 2.0](https://www.ocel-standard.org/)

### C8. Marey chart · *string chart, train graph, time-distance diagram* · useful · not on the brief
- **Q:** How does each item travel through ordered stages over time? Reveals overtaking, stalls, batching and whether FIFO holds.
- **Read:** Stages on one axis, time on the other, one line per item. Slope is speed. Crossing lines mean overtaking; flat segments are waits; lines converging are a batch.
- **Beyond:** Keeps individual paths, ordering and time together, which neither a CFD nor a process map does.
- **Needs:** Item, ordered state, entry time.
- **Shape:** `points` (`group`, `order: time`).
- **Get:** The `item_spans` view.
- **Misuse:** Needs a meaningful stage order; rework draws backward. Cap the number of lines (about 200) and highlight rather than plot everything [unsure of the cap].
- **Ops:** Yes. In a merge queue, shows large changes being overtaken and batches landing together.
- **Why:** The most information-dense view of flow, and it needs no new shape.
- **Refs:** Tufte 1983

## 7. Queueing and flow networks

### D1. Queueing network diagram · *Jackson, BCMP, closed networks* · useful
- **Q:** Given routing and service demands, what throughput and latency should this system have, and what happens if load or capacity changes? Decides capacity.
- **Read:** Stations with queues and servers, arrows with routing probabilities. Compare predicted with measured: a gap means a missing resource or wrong assumption. Open networks have arrivals; closed ones have a fixed population.
- **Beyond:** Predicts nonlinear delay near saturation from a few measured numbers.
- **Needs:** Visit ratios, service demands, servers, arrival rate or population.
- **Shape:** `graph` plus `table` of results.
- **Get:** Routing from `moves`, demand from busy time. Solve with MVA for closed product-form networks.
- **Misuse:** Product form needs specific assumptions (Jackson: Poisson arrivals, exponential service, Markov routing). Fork-join, blocking and priorities break them. Show the assumptions and the fit to measured data.
- **Ops:** Yes. A closed worker pool with a WIP limit is a closed network.
- **Why:** The right model for capacity questions, best shown as results on the service map rather than as its own diagram.
- **Refs:** [Jackson 1957](https://doi.org/10.1287/opre.5.4.518), [Jackson 1963](https://doi.org/10.1287/mnsc.10.1.131), [Baskett et al. 1975](https://doi.org/10.1145/321879.321887), [Gordon & Newell 1967](https://doi.org/10.1287/opre.15.2.254), [Reiser & Lavenberg 1980](https://doi.org/10.1145/322186.322195), [Bolch et al. 2006](https://doi.org/10.1002/0471791571), [Lazowska et al. 1984](https://homes.cs.washington.edu/~lazowska/qsp/)

### D2. Bottleneck overlay · *asymptotic bounds, utilisation law* · **must-have** · not built
- **Q:** Which resource limits throughput right now, and what would adding capacity there gain? Decides where the next unit of capacity goes.
- **Read:** On the map, mark the station with the highest utilisation and its queue. Check the bound `X ≤ min(1/D_max, N/(D+Z))`. Past the knee `N* = (D+Z)/D_max`, more work in progress adds only delay. The bottleneck is confirmed when a queue builds **before** it and work is starved **after** it.
- **Beyond:** Separates "busy" from "constraining", and gives the maximum gain from a fix before making it.
- **Needs:** Per-station busy time or service demand, throughput, WIP. For a pool: capacity.
- **Shape:** `graph` with node fields `utilisation`, `wait`, `blocked_share`, plus `points` for the bounds.
- **Get:** Item spans and worker leases; PromQL for services.
- **Misuse:** (1) Using centrality (X5 picks the wrong station). (2) Using the longest queue alone: with finite buffers, blocking pushes queues upstream. (3) Treating a human or external wait as a server with unlimited capacity. (4) A bottleneck moves, so show it over time.
- **Ops:** Yes. Review is at 96% and builds at 40%, so more build agents will not raise merges per day.
- **Why:** It is the owner's named question, and the laws involved need no distribution assumptions.
- **Refs:** [Denning & Buzen 1978](https://doi.org/10.1145/356733.356735), [Lazowska et al. 1984](https://homes.cs.washington.edu/~lazowska/qsp/), [Little 1961](https://doi.org/10.1287/opre.9.3.383), [Little 2011](https://doi.org/10.1287/opre.1110.0940), [Kingman 1961](https://doi.org/10.1017/S0305004100036094)

### D3. Max-flow / min-cut · niche
- **Q:** What is the most this routed network can carry, and which set of links limits it? Supports capacity planning on multi-path networks.
- **Read:** The minimum cut's edges sum to the maximum flow.
- **Beyond:** Finds a limit formed by *several* edges jointly, which per-station utilisation misses.
- **Needs:** Reliable capacity on every edge, which software systems rarely have.
- **Shape:** Input `graph`; output `table`. **Get:** Declared capacity plus routing.
- **Misuse:** Treats capacity as a fixed number, though real capacity varies with load and work mix. Refuse when capacities are guesses.
- **Ops:** Network or multi-region traffic; rarely a work queue.
- **Why:** Few operators have the capacities needed to run it honestly.
- **Refs:** [Ford & Fulkerson 1956](https://doi.org/10.4153/CJM-1956-045-5)

### D4. Sankey diagram · niche
- **Q:** How does a quantity split and merge across stages? Supports explaining where volume goes.
- **Read:** Band width is quantity, conserved across nodes.
- **Beyond:** Very clear proportion-of-flow display for an **acyclic** breakdown.
- **Needs:** Conserved flows over one window.
- **Shape:** `graph`. **Get:** SQL or PromQL.
- **Misuse:** Hides time and accumulation, draws loops badly, and implies a path through a node (X1). A Sankey of a DFG **invents routes**.
- **Ops:** One honest use: final outcomes of work arriving in a window (merged, abandoned, reverted).
- **Why:** The catalog cut it, and that stands. A stacked bar conveys the outcome split.
- **Refs:** [Riehmann et al. 2005](https://doi.org/10.1109/INFVIS.2005.1532152)

### D5. Alluvial diagram · niche
- **Q:** How did category membership change between two times? Supports reorganisation or re-tiering analysis.
- **Read:** Ribbons between columns of categories.
- **Beyond:** Tracks **the same entities** across columns, so unlike D4 its paths are real.
- **Needs:** Per-entity categories at each time. **Shape:** `table`. **Get:** SQL.
- **Misuse:** Too many categories; column order implies sequence.
- **Ops:** Services moving between ownership or severity tiers per quarter.
- **Why:** An occasional report, not an operating view.
- **Refs:** [Rosvall & Bergstrom 2010](https://doi.org/10.1371/journal.pone.0008694)

### D6. Value stream map · *VSM* · useful (as a timeline strip)
- **Q:** How much of lead time is work and how much is waiting? Decides whether to speed up work or remove waits.
- **Read:** Steps with process time and wait; the lead-time ladder at the bottom. **Flow efficiency** = work time ÷ lead time. Low values are normal in knowledge work and point at queues.
- **Beyond:** Splits value-adding time from waiting across the end-to-end process.
- **Needs:** Active and waiting time per state. Leases give active time.
- **Shape:** `table`.
- **Get:** Item spans classified by state role.
- **Misuse:** The hand-drawn form is a one-day snapshot, and "value-adding" is a judgement. Report active versus waiting, which the record can prove.
- **Ops:** Yes. A 26-hour merge with 50 minutes of machine time.
- **Why:** The number is decisive, but the classic factory icons add nothing.
- **Refs:** Rother & Shook 1999

### D7. Routing and flow map · *geographic flow map* · niche
- **Q:** Where does traffic travel between locations? Supports placement and failover.
- **Read:** Weighted arcs on a map.
- **Beyond:** Relates traffic to real geography.
- **Needs:** Location-tagged traffic. **Shape:** `graph` with coordinates. **Get:** Edge or CDN metrics.
- **Misuse:** Long arcs dominate visually regardless of volume.
- **Ops:** Multi-region serving only.
- **Why:** Outside ergostat's work-and-control focus.
- **Refs:** [Munzner 2014](https://doi.org/10.1201/b17511)

### D8. Kanban system map · niche
- **Q:** What are the stages, WIP limits, classes of service and commitment points? Supports designing a pull system.
- **Read:** Columns or a flow diagram with limits and buffers.
- **Beyond:** Makes policies explicit.
- **Needs:** Declared limits and policies. **Shape:** `table`. **Get:** Model.
- **Misuse:** A board does not prove the limits are enforced. Compare with measured WIP.
- **Ops:** Yes, but the Items page and limits on stocks already show this.
- **Why:** Duplicates what already exists.
- **Refs:** Anderson 2010

## 8. Dependency and scheduling

### E1. Dependency DAG · *task graph, build graph, precedence network* · **must-have** · exists (Items Graph)
- **Q:** What must finish before what? What can start now? Decides what to work on next.
- **Read:** Left-to-right precedence. Good: wide and shallow (parallel). Bad: long chains and a node with very high fan-in.
- **Beyond:** Shows precedence, which stock-and-flow aggregates away entirely.
- **Needs:** Explicit relations between items.
- **Shape:** `graph` with `paths_real: true` (a precedence chain really holds).
- **Get:** `links` in the item index (`blocked_by`, `after`, `depends_on`).
- **Misuse:** Declared links go stale. Mark links to finished work, and show when each was last confirmed. Transitive reduction prevents false visual density.
- **Ops:** Yes. Tickets in an epic, build targets.
- **Why:** Exists; needs only to move to the shared shape so panels can use it.
- **Refs:** [Kelley & Walker 1959](https://doi.org/10.1145/1460299.1460318), [Sugiyama et al. 1981](https://doi.org/10.1109/TSMC.1981.4308636)

### E2. PERT network · *three-point estimate* · niche
- **Q:** How likely is a target date? Supports schedule risk.
- **Read:** Optimistic, likely and pessimistic durations on a network.
- **Beyond:** Adds uncertainty to CPM.
- **Needs:** Three estimates per task, which ergostat should replace with measured distributions.
- **Shape:** `graph`, `distribution`. **Get:** Monte Carlo from observed durations.
- **Misuse:** Classic PERT looks only at the critical path and ignores merge bias, so it is systematically optimistic. Never use its closed form.
- **Ops:** Program planning. A simulated completion distribution is better.
- **Why:** The same question has a better answer from the record.
- **Refs:** [Malcolm et al. 1959](https://doi.org/10.1287/opre.7.5.646)

### E3. Critical path · *CPM* · **must-have** · exists
- **Q:** Which chain sets the finish date, and how much can each item slip? Decides what to expedite.
- **Read:** The zero-slack chain, highlighted. Expedite only critical items. Watch near-critical chains, which take over after a small improvement.
- **Beyond:** Identifies which delays matter and which are absorbed by slack.
- **Needs:** A DAG and durations.
- **Shape:** `graph` with `critical`, `slack`.
- **Get:** `precedence.py` (forward and backward pass, plus a levelled schedule).
- **Misuse:** **Ignores capacity** (X6: 9 versus 13). Show the levelled end beside it, and say which one applies. Point estimates also hide variance, so show near-critical items.
- **Ops:** Yes. Which of 40 tickets actually determines the release date.
- **Why:** Exists and answers "why isn't this done?" for dependent work.
- **Refs:** [Kelley & Walker 1959](https://doi.org/10.1145/1460299.1460318), [Kelley 1961](https://doi.org/10.1287/opre.9.3.296), [Graham 1969](https://doi.org/10.1137/0117039)

### E4. Critical chain · *CCPM, buffer management* · niche
- **Q:** What is the longest chain once resources are counted, and how much buffer remains? Supports project control.
- **Read:** Buffer consumption against progress (fever chart).
- **Beyond:** Adds resource contention to the critical path.
- **Needs:** Resource assignment and buffers.
- **Shape:** `graph`, `points`. **Get:** The levelled schedule.
- **Misuse:** Herroelen and Leus report that the 50% buffer rule can seriously overestimate the protection needed, and that regularly updating the baseline gave the shortest final duration.
- **Ops:** Large delivery projects. The levelled schedule already covers the resource part.
- **Why:** Keep the insight (resources make the chain), and skip the buffer method.
- **Refs:** [Herroelen & Leus 2001](https://doi.org/10.1016/S0272-6963(01)00054-7), Goldratt 1997

### E5. Gantt chart with dependencies · **must-have** · exists (Timeline)
- **Q:** What happened, what is running, and what is projected, on one time axis? Decides what to chase and what to tell stakeholders.
- **Read:** Bars on time, arrows for dependencies, a now line. Actual and projected must look different.
- **Beyond:** Combines precedence with calendar time.
- **Needs:** Spans and dependencies.
- **Shape:** `table` of spans plus `graph` edges. Treat as `graph` with `time.mode: intervals`.
- **Get:** `precedence.py`.
- **Misuse:** A projection presented as a commitment. Keep its assumptions in view.
- **Ops:** Yes. Release status for stakeholders.
- **Why:** Exists, and serves the "why is it held up?" use directly.
- **Refs:** [Kelley & Walker 1959](https://doi.org/10.1145/1460299.1460318)

### E6. Dependency structure matrix · *DSM, design structure matrix* · useful
- **Q:** How is this system modular, where are the feedback couplings, and in what order should parts be built? Decides how to split teams or services.
- **Read:** Square matrix with items in the same order on both axes. After sequencing, marks on one side of the diagonal are feedback (**state the convention**, since it varies). Blocks along the diagonal are modules; a full row or column is a bus or hub.
- **Beyond:** Stays readable at hundreds of nodes and makes cycles and modularity visible where a node-link diagram is a hairball.
- **Needs:** A dependency list, ideally with strengths.
- **Shape:** `graph`, rendered as a matrix.
- **Get:** Item relations, service-map edges, the model's parts.
- **Misuse:** Unordered, a DSM shows nothing, and ordering choices create apparent clusters. State the method.
- **Ops:** Yes. Finds two services that form one cycle across team boundaries.
- **Why:** The strongest view of a large dependency structure, for a periodic architecture decision.
- **Refs:** [Steward 1981](https://doi.org/10.1109/TEM.1981.6448589), [Browning 2001](https://doi.org/10.1109/17.946528), [Eppinger & Browning 2012](https://doi.org/10.7551/mitpress/8896.001.0001)

### E7. Adjacency / transition matrix · *matrix view* · **must-have** (as the graph fallback) · not built
- **Q:** Who connects to whom, and how strongly, when a node-link drawing is unreadable? Decides what to drill into.
- **Read:** Row to column, shade by weight. Look for blocks, bright rows and off-diagonal outliers. A state transition matrix shows rework as cells below the diagonal.
- **Beyond:** No edge crossings. Dense graphs remain legible.
- **Needs:** An edge list.
- **Shape:** `graph`; the existing heatmap can draw its `table` projection.
- **Get:** Any `graph` result.
- **Misuse:** Poor for tracing paths: Ghoniem et al. found path finding was the task where node-link stayed ahead, and later studies are mixed. Default ordering must not suggest clusters.
- **Ops:** Yes. 80 services calling each other.
- **Why:** This is the answer to the hairball, and it reuses the heatmap.
- **Refs:** [Ghoniem et al. 2004](https://doi.org/10.1109/INFVIS.2004.1), [Ghoniem et al. 2005](https://doi.org/10.1057/palgrave.ivs.9500092), [Okoe et al. 2019](https://doi.org/10.1109/TVCG.2018.2865940), [Behrisch et al. 2016](https://doi.org/10.1111/cgf.12935)

### E8. Reachability / transitive closure · useful (a query)
- **Q:** Can A affect B at all, and by what route? Decides whether a change or failure is in scope.
- **Read:** Yes or no plus a shortest witness path.
- **Beyond:** A global structural property that no local view shows.
- **Needs:** A directed graph with a defined edge meaning.
- **Shape:** `table`, or `graph` for the witness.
- **Get:** Traversal over relations or the service map.
- **Misuse:** Reachable does not mean affected (see E10). Over time, a path only counts if its edges occur in order (J8).
- **Ops:** Yes. Is this ticket really upstream of the release?
- **Why:** The primitive under E10, E11 and "why".
- **Refs:** [Newman 2018](https://doi.org/10.1093/oso/9780198805090.001.0001)

### E9. Topological layers · niche (as a view)
- **Q:** What can run in parallel, and how deep is the graph? Supports parallelism planning.
- **Read:** Nodes in a layer are not ordered against each other. Depth is the minimum number of sequential steps at unlimited capacity.
- **Beyond:** Gives maximum parallelism directly.
- **Needs:** A DAG. **Shape:** `graph` with `layer`. **Get:** Kahn's algorithm.
- **Misuse:** Layer position implies timing or importance that may not exist.
- **Ops:** Build graph width. Layered layout (K2) already shows it.
- **Why:** A property of K2 rather than a diagram.
- **Refs:** [Sugiyama et al. 1981](https://doi.org/10.1109/TSMC.1981.4308636)

### E10. Impact graph · *blast radius, dependents graph* · **must-have** · not built
- **Q:** What breaks, or slips, if this fails or is delayed? Decides whether to page, roll back or proceed.
- **Read:** A focal node with its downstream reach, by hops. Distinguish **hard** dependencies (it fails), **soft** ones (it degrades), and **unknown**. Show the traffic or items at risk, and the fallback if known.
- **Beyond:** Propagates a failure across structure, which no time-series chart can do before it happens.
- **Needs:** A directed dependency graph with edge meaning, freshness and, ideally, criticality.
- **Shape:** `graph` with `focus`, and node field `exposure`.
- **Get:** Item relations (`blocks`), the observed service map, the system model. For a *what-if* on a modelled stock, simulate.
- **Misuse:** Reachability **overstates** impact where there are retries, caches and fallbacks, and **understates** it through shared infrastructure and uninstrumented paths. Label as "could be affected", give the graph's age, and confirm with past incidents or a game day.
- **Ops:** Yes. "If the auth service fails, 11 services and the merge pipeline depend on it, 3 of them hard."
- **Why:** The named question, and the most common use of a topology in an incident.
- **Refs:** [Soldani & Brogi 2022](https://doi.org/10.1145/3501297), [Newman 2018](https://doi.org/10.1093/oso/9780198805090.001.0001)

### E11. Wait-for graph · *blocker chain, resource-allocation graph* · **must-have** · not on the brief
- **Q:** **Who or what is everything waiting on, right now, and is any of it circular?** Decides which single thing to unblock.
- **Read:** An edge means "A cannot proceed until B acts". Follow to the **roots**: nodes that wait on nothing and hold others. Rank roots by the work behind them. A cycle is a deadlock when each resource has one unit. With multi-unit resources a cycle is necessary but not sufficient.
- **Beyond:** It is the only diagram whose edges mean *currently blocked*. A DAG shows all precedence, including work that is not yet due.
- **Needs:** Open items, relations, leases, the state each waits in, and the actor or external party it waits for. Age of each wait.
- **Shape:** `graph` with node `waiting_since`, `blocked_count`.
- **Get:** The `precedence.py` status (`blocked`, `paused`) plus leases; manual to-dos and external waits as nodes.
- **Misuse:** Stale `blocked_by` shows false blockers. Verify that the target is unfinished and show the wait's age. Showing people as roots can read as blame, so label the *thing* awaited.
- **Ops:** Yes. 23 changes trace to one failing integration environment, and 6 to one security approval.
- **Why:** The most direct answer to the owner's first question, largely from data already held.
- **Refs:** [Holt 1972](https://doi.org/10.1145/356603.356607)

### E12. Dominators and articulation points · *SPOF analysis, dominator tree* · useful · not on the brief
- **Q:** Which single node does every path to X pass through? Decides where to add redundancy.
- **Read:** A dominates X if all paths from the entry to X pass through A. An articulation point disconnects the graph when removed.
- **Beyond:** Proves a structural single point of failure, which degree or centrality only hints at.
- **Needs:** A reasonably complete graph with an entry point.
- **Shape:** `table`, with an overlay on `graph`.
- **Get:** Lengauer-Tarjan over the service map or the declared dependencies; Hopcroft-Tarjan for articulation points.
- **Misuse:** A missing edge creates a false SPOF, and shared infrastructure not on the graph hides real ones. Report coverage.
- **Ops:** Yes. All deployment paths pass through one runner pool.
- **Why:** An exact, cheap answer to a common resilience question.
- **Refs:** [Lengauer & Tarjan 1979](https://doi.org/10.1145/357062.357071), [Hopcroft & Tarjan 1973](https://doi.org/10.1145/362248.362272)

### E13. Commit and merge graph · *git DAG, merge train view* · niche
- **Q:** How do changes stack and land? Supports debugging a merge queue.
- **Read:** Commits as a DAG, branches and rebases as structure.
- **Beyond:** Shows ancestry, which an item list omits.
- **Needs:** Repository history. **Shape:** `graph`. **Get:** External source.
- **Misuse:** Rebases rewrite the history the view relies on.
- **Ops:** Yes, for PR stacks. The forge already draws it.
- **Why:** Leave it to the forge unless ergostat comes to manage stacks.
- **Refs:** [Newman 2018](https://doi.org/10.1093/oso/9780198805090.001.0001)

## 9. Software and infrastructure topology

### F1. Service map · *service graph, dependency map* · **must-have** · not built (the Process view replaced Wiring; nothing draws runtime traffic)
- **Q:** What talks to what, and which link is unhealthy now? Decides where an incident lives.
- **Read:** Nodes are services, edges carry rate, errors and latency. Follow red **toward the dependency**: the deepest unhealthy node is the first suspect, since callers inherit its errors. Compare with the last healthy period.
- **Beyond:** Places RED metrics on the structure they belong to.
- **Needs:** Caller and callee identity on traffic counts.
- **Shape:** `graph` with `paths_real: false`, `time.mode: window`.
- **Get:** PromQL over `from`/`to` labels: `traces_service_graph_request_total{client,server}` (Tempo and OpenTelemetry), `istio_requests_total{source_workload,destination_workload}` (Istio). For machines, the event log.
- **Misuse:** (1) **Stale topology:** an unseen edge may be idle or gone, so show last-seen. (2) Low-rate edges vanish under sampling (X8); Tempo offers a `connection_info` series for this. (3) A missing caller span appears as a virtual `user` node, which is not a real service. (4) A→B and B→C does not mean A's requests reach C (X1). (5) Co-failing does not mean causing.
- **Ops:** Yes. The fleet's central view in an incident. Grafana, Kiali and Jaeger all ship one.
- **Why:** The recognised view of runtime traffic, which no ergostat view draws now that the Process view has replaced Wiring on the Diagram page.
- **Refs:** [Grafana Tempo](https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/), [Istio](https://istio.io/latest/docs/reference/config/metrics/), [Kiali](https://kiali.io/docs/features/topology/), [Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/), [Jaeger](https://www.jaegertracing.io/docs/latest/features/)

### F2. Static call graph · niche
- **Q:** What code calls what? Supports refactoring and reachability of a vulnerability.
- **Read:** Functions and calls; look for cycles and high fan-in.
- **Beyond:** Covers paths not exercised at runtime.
- **Needs:** Source analysis. **Shape:** `graph`. **Get:** External tool.
- **Misuse:** Dynamic dispatch makes it both over- and under-approximate.
- **Ops:** Developer tooling, not operations.
- **Why:** IDEs and code tools own this.
- **Refs:** [Cornelissen et al. 2009](https://doi.org/10.1109/TSE.2009.28)

### F3. Trace waterfall · *span timeline, run waterfall* · useful
- **Q:** Where did this one request or run spend its time? Decides which span to fix.
- **Read:** Nested spans over time. Look for the longest **self time**, sequential calls that could be parallel, N+1 repeats, and gaps with no span (uninstrumented time).
- **Beyond:** Shows nesting and concurrency for a single execution.
- **Needs:** Spans with parent links. Agent and block runs provide a similar structure.
- **Shape:** `graph` with `time.mode: intervals`, drawn as a tree of bars.
- **Get:** An external trace source; for ergostat's own runs, events with `causedby`. No trace source exists today.
- **Misuse:** Summed span time exceeds elapsed time under concurrency. Highlight the critical path. OpenTelemetry messaging uses **links**, so a batch or queue is not a tree. An outlier trace is not typical.
- **Ops:** Yes. A slow checkout dominated by 40 serial database calls.
- **Why:** Standard and valuable, but it depends on a trace source.
- **Refs:** [Sigelman et al. 2010](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/), [OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/), [Chow et al. 2014](https://www.usenix.org/node/186168)

### F4. Flame graph · *icicle* · niche
- **Q:** Which code paths consume the most of a resource? Supports performance work.
- **Read:** Width is share of samples; look for wide plateaus. **The x-axis is not time** (it is sorted alphabetically).
- **Beyond:** Compresses thousands of stacks into one view.
- **Needs:** Stack samples or aggregated spans. **Shape:** `graph` (tree) with `weight`. **Get:** A profiler.
- **Misuse:** Reading left-to-right as sequence.
- **Ops:** Yes, but profilers ship their own.
- **Why:** Ergostat holds no profiles.
- **Refs:** [Gregg 2016](https://doi.org/10.1145/2909476), [Gregg](https://www.brendangregg.com/flamegraphs.html)

### F5. Trace graph · *aggregated trace DAG, deep dependency graph* · niche
- **Q:** What structure do requests through this service really have? Supports a change to one endpoint.
- **Read:** Service or endpoint nodes through a focal service, from real traces.
- **Beyond:** **Keeps real multi-hop paths**, which a one-hop service map cannot (X1).
- **Needs:** Complete traces. **Shape:** `graph` with `paths_real: true`. **Get:** Trace backend.
- **Misuse:** Built from a search result, so it reflects only that sample.
- **Ops:** Yes, if tracing exists. Link out to it.
- **Why:** Jaeger already has it, and ergostat should not rebuild a trace UI.
- **Refs:** [Jaeger](https://www.jaegertracing.io/docs/latest/features/)

### F6. Network topology diagram · *L2/L3 map* · niche
- **Q:** How are hosts and links physically or logically connected? Supports network fault isolation.
- **Read:** Devices and links, with redundancy visible.
- **Beyond:** Shows failure domains below the service level.
- **Needs:** LLDP, SNMP or cloud inventories. **Shape:** `graph`. **Get:** External inventory.
- **Misuse:** Hand-maintained drawings go stale quickly.
- **Ops:** Yes, for network teams, who have tools for it.
- **Why:** Not ergostat's domain.
- **Refs:** [Munzner 2014](https://doi.org/10.1201/b17511)

### F7. Data lineage and provenance graph · *W3C PROV, OpenLineage* · useful (narrowly)
- **Q:** Where did this number come from, and what depends on it? Decides whether to trust a chart, and what a bad source contaminates.
- **Read:** Datasets, jobs and runs, or entity, activity and agent in PROV. Follow upstream for trust, downstream for impact.
- **Beyond:** Explains a value's origin, which the value's chart cannot.
- **Needs:** Recorded derivations.
- **Shape:** `graph`.
- **Get:** ergostat's own: a panel's query → series → sensor → goal; `meta.provenance` already carries the type. External: OpenLineage events.
- **Misuse:** Coarse lineage says a table was involved, not that a given value was affected.
- **Ops:** Yes. Which goals depend on the metric whose exporter broke at 09:00?
- **Why:** A small, valuable slice supports the trust layer; a data-catalog clone is out of scope.
- **Refs:** [W3C 2013](https://www.w3.org/TR/prov-overview/), [OpenLineage](https://openlineage.io/docs/)

### F8. C4 and architecture diagrams · don't build
- **Q:** How is the system organised for people who need to understand it? Supports onboarding and design review.
- **Read:** Context, containers, components, code, at increasing zoom.
- **Beyond:** A clear **zoom discipline** that is useful to borrow.
- **Needs:** Hand-authored model. **Shape:** None. **Get:** Documentation.
- **Misuse:** Drifts from reality unless generated.
- **Ops:** Yes, as documentation.
- **Why:** The service map, drawn from evidence, is the operational equivalent; borrow only its levels for drill-down.
- **Refs:** [C4 model](https://c4model.com/)

### F9. Kubernetes resource graph · *owner graph* · useful (when the source is attached)
- **Q:** Which workloads, pods, services and nodes relate, and which change produced this state? Decides where a rollout stalled.
- **Read:** Deployment → ReplicaSet → Pod by owner references; Service → Pod by selectors. Those are **different edge kinds** and must stay visually distinct.
- **Beyond:** Explains a controller's chain of objects, which metrics do not.
- **Needs:** API objects, read-only.
- **Shape:** `graph` with `relation`.
- **Get:** Kubernetes API or kube-state-metrics joins. Index owners by UID, since names can be reused.
- **Misuse:** A dangling owner reference is not a live edge, and cross-namespace owners are disallowed by design.
- **Ops:** Yes. A rollout stuck because a new ReplicaSet's pods cannot schedule.
- **Why:** Important for the external-systems direction, but only once such a source exists.
- **Refs:** [Kubernetes](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/)

## 10. Causal and probabilistic

### G1. Causal DAG · *structural causal model diagram* · useful
- **Q:** What must I control for to estimate this effect? Decides whether an observational comparison means anything.
- **Read:** Arrows are assumed direct causes. Apply the back-door criterion. A collider must **not** be conditioned on.
- **Beyond:** Separates correlation from identifiable effect, and shows which adjustment is valid.
- **Needs:** Assumptions from a person or the declared model. Data cannot supply them alone.
- **Shape:** `graph` (`evidence: declared`).
- **Get:** The model's structure as a starting hypothesis, with feedback unrolled over time.
- **Misuse:** A discovered graph presented as fact. Feedback systems also violate acyclicity unless time-indexed.
- **Ops:** Yes. Did the new review rule cut reverts, or did smaller changes do it?
- **Why:** The right guard for "did this change work?", shown within the experiment's analysis.
- **Refs:** [Pearl 1995](https://doi.org/10.1093/biomet/82.4.669), [Pearl 2009](https://doi.org/10.1017/CBO9780511803161), [Spirtes et al. 2001](https://doi.org/10.7551/mitpress/1754.001.0001)

### G2. Bayesian network · niche
- **Q:** Given these symptoms, what is the probability of each cause? Supports diagnosis.
- **Read:** A DAG with conditional probability tables; evidence updates beliefs.
- **Beyond:** Coherent reasoning from partial evidence.
- **Needs:** Structure plus probabilities, rarely available for rare incidents.
- **Shape:** `graph`, `table`. **Get:** Expert elicitation or fit.
- **Misuse:** Precise posteriors from invented priors.
- **Ops:** Alert diagnosis, in research more than practice.
- **Why:** The parameters are seldom defensible.
- **Refs:** [Pearl 2009](https://doi.org/10.1017/CBO9780511803161)

### G3. Influence diagram · niche
- **Q:** Which decision maximises expected utility under uncertainty? Supports a one-off high-stakes choice.
- **Read:** Decision, chance and value nodes.
- **Beyond:** Puts decisions and values in the model.
- **Needs:** Probabilities and utilities. **Shape:** `graph`. **Get:** Elicitation.
- **Misuse:** False precision; the name is also confused with a causal loop diagram.
- **Ops:** Rare: a migration decision.
- **Why:** A paired what-if comparison serves ergostat's decisions.
- **Refs:** [Howard & Matheson 2005](https://doi.org/10.1287/deca.1050.0020)

### G4. Fault tree · *FTA* · useful
- **Q:** What combinations of failures produce this outage? Decides what redundancy matters.
- **Read:** Top event, AND/OR gates, basic events. **Minimal cut sets** are the output: a size-one set is a single point of failure.
- **Beyond:** Handles **combinations** of failure, which graphs of single dependencies do not.
- **Needs:** A declared failure logic; optional failure rates.
- **Shape:** `graph` (tree) and `table` of cut sets.
- **Get:** Hand-declared, seeded by E12 and past incidents.
- **Misuse:** Treating events as independent when they share a cause. Probabilities invite false precision, so lead with cut sets.
- **Ops:** Yes. Checkout is down if (DB primary AND failover) OR the auth service.
- **Why:** The strongest reliability method for a critical service, but it needs deliberate authoring.
- **Refs:** [Vesely et al. 1981](https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr0492/index.html), IEC 61025

### G5. Event tree · *ETA* · niche
- **Q:** After an initiating event, which sequence of safeguards leads to which outcome? Supports defence-in-depth review.
- **Read:** Left to right, each safeguard branches success or failure.
- **Beyond:** Inductive and forward-looking, the counterpart of a fault tree.
- **Needs:** Safeguards and their failure probabilities. **Shape:** `graph`. **Get:** Hand-declared.
- **Misuse:** Independence between safeguards is often false.
- **Ops:** Yes in principle: bad deploy → canary → alert → rollback.
- **Why:** Rarely maintained outside regulated settings.
- **Refs:** IEC 62502

### G6. Attack tree · niche
- **Q:** How could an attacker achieve this goal? Supports security investment.
- **Read:** Goal at root, AND/OR sub-goals, with cost or feasibility.
- **Beyond:** Models an adversary, which reliability methods do not.
- **Needs:** Threat analysis. **Shape:** `graph`. **Get:** Hand-declared.
- **Misuse:** Scores give an illusion of measured risk.
- **Ops:** Yes, for security teams, outside this product.
- **Why:** Not part of operating a feedback system.
- **Refs:** [Schneier 1999](https://www.schneier.com/academic/archives/1999/12/attack_trees.html)

### G7. Reliability block diagram · *RBD* · niche
- **Q:** What is the availability of this series-parallel arrangement? Supports redundancy design.
- **Read:** Paths from input to output; the system works if a path survives.
- **Beyond:** Direct availability arithmetic.
- **Needs:** Component availability, independence. **Shape:** `graph`. **Get:** Declared.
- **Misuse:** Correlated failure breaks the multiplication, and common-mode failures dominate in software. **It also looks like a control block diagram,** which must not be confused with Blocks.
- **Ops:** Quick SLO arithmetic for a dependency chain.
- **Why:** A table can do the arithmetic.
- **Refs:** IEC 61078

### G8. FMEA relationship view · niche
- **Q:** How can each part fail, with what effect? Supports prioritising mitigations.
- **Read:** A table of failure modes, effects, causes, controls.
- **Beyond:** Systematic per-component coverage.
- **Needs:** Expert analysis. **Shape:** `table`. **Get:** Hand-authored.
- **Misuse:** The risk priority number multiplies ordinal scales, which has no sound meaning.
- **Ops:** Pre-launch reviews.
- **Why:** It is a table, and it needs no graph.
- **Refs:** IEC 60812

### G9. Ishikawa diagram · *fishbone, cause-and-effect* · don't build
- **Q:** What might have caused this? Supports brainstorming.
- **Read:** Categories of candidate causes branching to an effect.
- **Beyond:** Only structures a discussion.
- **Needs:** People's opinions. **Shape:** None. **Get:** A meeting.
- **Misuse:** Its edges are unverified guesses that look like analysis, and it encourages a single linear cause.
- **Ops:** Post-incident workshops, at best.
- **Why:** Holds no evidence and would break the rule that diagrams show evidence or structure.
- **Refs:** Ishikawa

### G10. Bow-tie diagram · niche
- **Q:** What prevents this hazard, and what limits the damage if it happens? Supports reviewing barriers.
- **Read:** Threats on the left, consequences on the right, barriers on each path.
- **Beyond:** Places prevention and mitigation on one view.
- **Needs:** Declared threats and barriers. **Shape:** `graph`. **Get:** Hand-declared.
- **Misuse:** A barrier drawn is not a barrier tested.
- **Ops:** Risk review of a high-severity failure mode.
- **Why:** A compliance artefact more than an operating view.
- **Refs:** IEC/ISO 31010

### G11. STAMP/STPA control structure · useful (as an analysis over Blocks)
- **Q:** Which control action, given when and under what belief, could lead to a loss? Decides which feedback and guardrails are missing.
- **Read:** A hierarchy of controllers and controlled processes with control actions and feedback. For each action, ask the four STPA questions: not provided, provided when unsafe, too early, late or out of order, and stopped too soon or applied too long. Look for a controller whose **process model** can go wrong.
- **Beyond:** Finds accidents with **no failed component**, which fault trees cannot represent.
- **Needs:** Controllers, actions, feedback, hazards. ergostat already knows the first three.
- **Shape:** `table` of unsafe control actions, keyed to parts of the model.
- **Get:** The model's structure plus a declared list of losses and hazards.
- **Misuse:** A diagram with no analysis is only a block diagram. **Do not add an STPA drawing**, since it would create a rival to Blocks.
- **Ops:** Yes. An autoscaler acting on a stale metric, or an agent merging on a green check that ran on the wrong commit.
- **Why:** The closest safety discipline to ergostat's model, and it needs only a table.
- **Refs:** [Leveson 2004](https://doi.org/10.1016/S0925-7535(03)00047-X), [Leveson 2012](https://doi.org/10.7551/mitpress/8179.001.0001), [Leveson & Thomas 2018](https://www.flighttestsafety.org/images/STPA_Handbook.pdf), [ICAO training material](https://www.icao.int/sites/default/files/SMI/TrainingDocs/Chapter%202%20Safety%20Management%20Fundamentals/2.6-05-SRM-Methodology-STPA.pdf)

### G12. Granger or transfer-entropy network · niche (a ranked hypothesis list, never a picture)
- **Q:** Which signals help predict which? Supports choosing what to investigate.
- **Read:** A directed edge means past X improves prediction of Y. It says nothing about intervention.
- **Beyond:** Suggests candidates from data with no declared structure.
- **Needs:** Long, stationary, adequately sampled series.
- **Shape:** `table` of ranked pairs with effect size, lag and adjusted significance.
- **Get:** Analysis source. Condition on other series (PCMCI style). For Gaussian data, Granger and transfer entropy are equivalent, so TE adds cost without benefit there.
- **Misuse:** The largest risk in this report. Shared drivers, trends and multiple testing produce dense false graphs (X7). Closed-loop control further hides or reverses the apparent direction. Refuse non-stationary input, correct for multiple tests, and **never draw the result as a network**.
- **Ops:** As a lead during an incident: "queue depth precedes latency by 2 min". Confirm with a change or experiment.
- **Why:** A graph drawing gives correlation the visual authority of structure.
- **Refs:** [Granger 1969](https://doi.org/10.2307/1912791), [Schreiber 2000](https://doi.org/10.1103/PhysRevLett.85.461), [Barnett et al. 2009](https://doi.org/10.1103/PhysRevLett.103.238701), [Runge et al. 2019](https://doi.org/10.1126/sciadv.aau4996)

## 11. Physical, organisational, analytic and layout

### Physical and control structure

### H1. Bond graph · don't build
- **Q:** How does energy move across physical domains? Supports multi-domain physical modelling.
- **Read:** Power bonds, 0- and 1-junctions, causal strokes.
- **Beyond:** Enforces energy conservation and derives equations.
- **Needs:** Effort and flow variables whose product is power. **Shape:** None. **Get:** None.
- **Misuse:** Software queues have no conserved energy, so effort and flow analogies are decorative.
- **Ops:** **No.**
- **Why:** Its central invariant has no counterpart here.
- **Refs:** Paynter 1961, [Karnopp et al. 2012](https://doi.org/10.1002/9781118152812)

### H2. Signal-flow graph / Mason graph · niche
- **Q:** What is the transfer function between two signals? Supports loop algebra.
- **Read:** Nodes are signals, branches are gains; Mason's rule sums forward paths and loops.
- **Beyond:** Closed-form gain of a complex linear structure.
- **Needs:** A linear model. **Shape:** None as a panel. **Get:** Model.
- **Misuse:** Drawn alongside Blocks it adds a second notation for the same fact.
- **Ops:** Internally, for computing closed-loop responses.
- **Why:** As the catalog says, keep the algebra and skip the picture.
- **Refs:** [Mason 1953](https://doi.org/10.1109/JRPROC.1953.274449)

### H3. P&ID-style diagram · don't build
- **Q:** How are plant equipment, piping and instruments connected? Supports process plant engineering.
- **Read:** ISA-5.1 symbols and tags.
- **Beyond:** A contractual record of a physical plant.
- **Needs:** A plant. **Shape:** None. **Get:** None.
- **Misuse:** Tanks and valves for software is the metaphor Dynamics already handles in its own discipline's notation.
- **Ops:** **No.**
- **Why:** Would be unrecognised and unnecessary.
- **Refs:** ANSI/ISA-5.1

### H4. Structural controllability and observability check · useful (a check, no diagram)
- **Q:** Can any actuator reach this stock, and can any sensor see it? Decides where a controller or sensor is missing.
- **Read:** A list of unreachable or unobservable parts. Each finding names the missing link.
- **Beyond:** Detects from structure alone that no tuning can ever hold a goal.
- **Needs:** The model's signed structure and which parts are actuated and sensed.
- **Shape:** `table` of findings.
- **Get:** `ergostat check`. Lin's structural conditions; reachability is the first, cheap step.
- **Misuse:** The network-science "driver node" count is highly sensitive to self-dynamics, as Cowan et al. argue, and stocks with outflows have them. Do not report it.
- **Ops:** Yes. A backlog with no controller acting on any of its flows.
- **Why:** One of the highest-value structural tests available to a control model.
- **Refs:** [Lin 1974](https://doi.org/10.1109/TAC.1974.1100557), [Liu et al. 2011](https://doi.org/10.1038/nature10011), [Cowan et al. 2012](https://arxiv.org/abs/1106.2573)

### H5. Consensus / multi-agent network view · niche
- **Q:** Will distributed agents converge, and how fast? Supports the design of gossip and coordination.
- **Read:** Communication graph; the Laplacian's second eigenvalue sets convergence speed in linear consensus.
- **Beyond:** Links topology to dynamics.
- **Needs:** Agents with linear averaging dynamics. **Shape:** `graph`. **Get:** Model.
- **Misuse:** Raft or Paxos are not linear averaging consensus, despite sharing the word.
- **Ops:** Rarely. Fleet load-balancers sharing state.
- **Why:** The theory does not apply to most systems that use the word "consensus".
- **Refs:** [Olfati-Saber et al. 2007](https://doi.org/10.1109/JPROC.2006.887293)

### Organisational and social

### I1. RACI graph · niche
- **Q:** Who is responsible and accountable for each activity? Supports resolving ownership gaps.
- **Read:** A matrix of roles against activities. Each row needs exactly one A.
- **Beyond:** Separates kinds of involvement.
- **Needs:** Declared roles. **Shape:** `table`. **Get:** Declared.
- **Misuse:** It records assignment, not behaviour, and a graph adds nothing to the matrix.
- **Ops:** Incident roles.
- **Why:** A table in a document suffices.
- **Refs:** none; a practitioner convention with no primary source I could verify.

### I2. Communication network · niche, with a privacy warning
- **Q:** Who actually coordinates with whom? Supports team design.
- **Read:** Weighted people graph; bridges and isolated groups.
- **Beyond:** Reveals the informal organisation.
- **Needs:** Message or review metadata. **Shape:** `graph`. **Get:** External sources.
- **Misuse:** Surveillance and individual ranking. Do not build per-person views.
- **Ops:** Team-level only.
- **Why:** The risk outweighs the decisions it would support.
- **Refs:** [Newman 2018](https://doi.org/10.1093/oso/9780198805090.001.0001)

### I3. Conway's-law view · *socio-technical congruence* · niche
- **Q:** Does the team structure match the dependency structure? Decides whether to move ownership or a boundary.
- **Read:** DSM of components overlaid with team boundaries. Dependencies crossing teams with no coordination are the risk.
- **Beyond:** Compares two structures that are otherwise seen apart.
- **Needs:** Dependencies, ownership, coordination.
- **Shape:** `graph` with `group`, shown as E6.
- **Get:** Service map plus declared ownership.
- **Misuse:** Mirroring is not automatically good, and a correlation between structure and quality is not a reorganisation plan.
- **Ops:** Yes. Evidence on organisation and quality exists (Nagappan et al., Cataldo et al.).
- **Why:** Once E6 exists it is a group-by, rarely needed.
- **Refs:** [Conway 1968](https://www.melconway.com/Home/Committees_Paper.html), [Cataldo et al. 2008](https://doi.org/10.1145/1414004.1414008), [MacCormack et al. 2012](https://doi.org/10.1016/j.respol.2012.04.011), [Nagappan et al. 2008](https://doi.org/10.1145/1368088.1368160)

### I4. Ownership and knowledge map · useful (for machines and services)
- **Q:** What has no owner, or depends on one person or one agent? Decides where to spread knowledge.
- **Read:** A treemap or table of parts by owner and concentration. Bad: critical part, one contributor.
- **Beyond:** Joins criticality and concentration.
- **Needs:** Ownership, or contribution history.
- **Shape:** `table`.
- **Get:** Declared `system` and machine metadata; repository history.
- **Misuse:** Commit share is a poor proxy for knowledge. Never rank individuals.
- **Ops:** Yes. A paging route that points to nobody.
- **Why:** "Who can act on this?" is part of why things are held up.
- **Refs:** [Bird et al. 2011](https://doi.org/10.1145/2025113.2025119)

### I5. Stakeholder map · don't build
- **Q:** Whose support does this need? Supports communication planning.
- **Read:** Usually a power-interest grid.
- **Beyond:** Nothing from operating data.
- **Needs:** Judgement. **Shape:** None. **Get:** A workshop.
- **Misuse:** A private judgement of people, unsuitable for a shared tool.
- **Ops:** No operational reading. Stakeholder-ready *status* is a Timeline and report concern.
- **Why:** It would hold no evidence.
- **Refs:** Mendelow 1991

### Graph analytics overlays

### J1. Centrality · *degree, betweenness, closeness, PageRank* · niche
- **Q:** Which nodes are structurally prominent? Supports choosing what to review.
- **Read:** A ranking whose meaning depends on the measure. Degree is direct exposure; betweenness is brokerage over shortest paths.
- **Beyond:** A single structural score for each node.
- **Needs:** A graph whose flow process matches the measure's assumptions.
- **Shape:** Node field on `graph`.
- **Get:** Brandes' algorithm; degree in SQL.
- **Misuse:** Borgatti shows each measure assumes a particular kind of flow. Betweenness assumes shortest-path transfer, and it **missed the bottleneck in X5**. Offer **fan-in and fan-out** by name and do not show a generic "importance" score.
- **Ops:** Fan-in on a service map is useful. The rest rarely is.
- **Why:** The measures people reach for answer a different question from the one they ask.
- **Refs:** [Freeman 1977](https://doi.org/10.2307/3033543), [Brandes 2001](https://doi.org/10.1080/0022250X.2001.9990249), [Borgatti 2005](https://doi.org/10.1016/j.socnet.2004.11.008)

### J2. Communities and modularity · useful (only for aggregation)
- **Q:** What are natural groups for collapsing a big graph? Supports readable overviews.
- **Read:** Dense groups, weakly connected to each other.
- **Beyond:** Finds grouping when no labels exist.
- **Needs:** A graph of at least moderate size.
- **Shape:** Node `group` on `graph`.
- **Get:** Leiden, only after declared groups (system, namespace, team) have been tried.
- **Misuse:** Modularity has a resolution limit and many near-equal partitions. Louvain may return badly connected communities. Never present them as real teams or subsystems.
- **Ops:** Grouping 300 services with no namespace labels.
- **Why:** A fallback for aggregation, as declared groups are better.
- **Refs:** [Newman & Girvan 2004](https://doi.org/10.1103/PhysRevE.69.026113), [Newman 2006](https://doi.org/10.1073/pnas.0601602103), [Blondel et al. 2008](https://doi.org/10.1088/1742-5468/2008/10/P10008), [Traag et al. 2019](https://doi.org/10.1038/s41598-019-41695-z), [Fortunato & Barthélemy 2007](https://doi.org/10.1073/pnas.0605965104), [Good et al. 2010](https://doi.org/10.1103/PhysRevE.81.046106)

### J3. Cycles, SCCs and feedback arc sets · **must-have** · partial (`precedence.py` finds cycles)
- **Q:** What is circular, and what is the smallest set of links to remove to break it? Decides how to untangle a deadlock or dependency knot.
- **Read:** Collapse each strongly connected component into one node, and what remains is a DAG. In a dependency graph a cycle is a defect. In a control system a cycle is **the point**, and must not be labelled a defect.
- **Beyond:** Identifies mutual dependence exactly.
- **Needs:** A directed graph.
- **Shape:** `table`, with an overlay on `graph`.
- **Get:** Tarjan (linear). Johnson for listing cycles, bounded because their number can be exponential. A greedy heuristic for feedback arcs, as the exact problem is NP-hard.
- **Misuse:** Cycles in a DFG may be concurrency rather than loops (X2). Layered layouts reverse edges to draw cycles, so a "backward" line may reflect the algorithm.
- **Ops:** Yes. Services A→B→C→A mean none can cold-start alone.
- **Why:** Needed by layout, wait-for and dependency checks alike.
- **Refs:** [Tarjan 1972](https://doi.org/10.1137/0201010), [Johnson 1975](https://doi.org/10.1137/0204007), [Eades et al. 1993](https://doi.org/10.1016/0020-0190(93)90079-O)

### J4. k-core · niche
- **Q:** What is the densely interdependent core? **Read:** Peel nodes below degree *k*. **Beyond:** A fast view of the core and periphery.
- **Needs:** A big graph. **Shape:** Node field. **Get:** Linear-time peeling.
- **Misuse:** A core is not necessarily important. **Ops:** Sometimes for a very large dependency graph.
- **Why:** Most ergostat graphs are too small to need it.
- **Refs:** [Seidman 1983](https://doi.org/10.1016/0378-8733(83)90028-X)

### J5. Motif analysis · don't build
- **Q:** Which small subgraphs are over-represented? **Read:** Frequency against a randomised null model. **Beyond:** Hints at design patterns across networks.
- **Needs:** A big graph and a defensible null model. **Shape:** `table`. **Get:** Enumeration.
- **Misuse:** Results depend heavily on the null model.
- **Ops:** No decision for an operator rests on it.
- **Why:** Research technique; searching directly for a known pattern (fan-in, retry loop) is more useful.
- **Refs:** [Milo et al. 2002](https://doi.org/10.1126/science.298.5594.824), [Milo et al. 2004](https://doi.org/10.1126/science.1089167)

### J6. Hierarchical edge bundling · niche
- **Q:** What are the high-level connection patterns in a hierarchy? **Read:** Curved bundles between groups. **Beyond:** Reduces clutter while keeping the hierarchy.
- **Needs:** A hierarchy plus adjacency. **Shape:** `graph` with `parent`. **Get:** Any.
- **Misuse:** Bundles hide individual edges and direction, so exact connections cannot be read.
- **Ops:** An overview of service calls by team. Aggregated edges do this more plainly.
- **Why:** Attractive, but an aggregate node with a count is more legible.
- **Refs:** [Holten 2006](https://doi.org/10.1109/TVCG.2006.147)

### J7. Graph diff · *topology change view* · **must-have** · not built
- **Q:** **What changed in the structure** between two times, or between declared and observed? Decides whether a change caused this incident.
- **Read:** Same layout for both. Added, removed and changed-weight edges are marked with both colour and line style. Rank by change in traffic or error rate.
- **Beyond:** Time-series charts show that something moved. A diff shows a **new dependency or route**.
- **Needs:** Two `graph` results on the same node identity.
- **Shape:** `graph` with `diff` field per node and edge.
- **Get:** Two windows of any graph source; a model version pair; C4 for declared versus observed.
- **Misuse:** An edge missing from a short window may just be rare. Require evidence over the baseline, and show "not seen for N" rather than "removed". Renames show as a remove plus an add.
- **Ops:** Yes. After a deploy, the API began calling a new cache and stopped calling the old one.
- **Why:** The strongest link between topology and "what changed?", the first question in an incident.
- **Refs:** [Beck et al. 2016](https://doi.org/10.1111/cgf.12791), [Burch et al. 2011](https://doi.org/10.1109/TVCG.2011.226)

### J8. Temporal network · *time-respecting paths, dynamic graph* · useful
- **Q:** Could this failure actually have propagated along this route, given **when** edges were active? Decides whether a hypothesis is possible.
- **Read:** A→B at 10:00 and B→C at 09:00 is not a path from A to C. Show by small multiples, a time slider or an edge timeline.
- **Beyond:** Rules out causal stories that a static aggregate falsely permits.
- **Needs:** Timestamped edges.
- **Shape:** `graph` with `time.mode: frames` or `events`.
- **Get:** The event log; windowed PromQL.
- **Misuse:** Aggregating over the window invents paths. Window choice changes the result, so show it.
- **Ops:** Yes. Excludes a suspected cascade because the downstream errors began first.
- **Why:** Cheap to compute from `causedby` and timestamps, and it stops false root-cause stories.
- **Refs:** [Holme & Saramäki 2012](https://doi.org/10.1016/j.physrep.2012.03.001), [Beck et al. 2016](https://doi.org/10.1111/cgf.12791), [Archambault et al. 2011](https://doi.org/10.1109/TVCG.2010.78)

### Layouts and encodings

A layout is a means of drawing. Position must not be read as data unless the layout assigns it a meaning. The fields are shortened here, since the "question" is which graph it suits.

### K1. Force-directed · *spring, stress* · niche
- **Use:** Undirected graphs under about 100 nodes where no direction or hierarchy exists.
- **Read:** Closeness suggests connection, but **distance and side have no defined meaning**.
- **Limits:** Unstable (X10), and slow at scale: stress takes 0.9 s at 100 nodes and 13 s at 400 [measured].
- **Misuse:** Readers infer clusters from a random start. Avoid it for directed flow. **Shape:** `graph`. **Ops:** Rarely the right choice here.
- **Why:** Most ergostat graphs are directed, so a layered layout serves better.
- **Refs:** [Fruchterman & Reingold 1991](https://doi.org/10.1002/spe.4380211102), [Kamada & Kawai 1989](https://doi.org/10.1016/0020-0190(89)90102-6)

### K2. Layered (Sugiyama) · **must-have** (default) · exists through ELK
- **Use:** All directed graphs: process maps, DAGs, service maps, wait-for.
- **Read:** Direction reads as flow. Phases: remove cycles, assign layers, reduce crossings, place nodes.
- **Limits:** 200 nodes and 600 edges in 0.36 s; 800 and 2,400 in 1.7 s, but already about 22,600 px wide [measured]. Compute is not the limit. **Legibility** is.
- **Misuse:** Reversed edges and layer position may imply an order that does not exist. Mark edges reversed by cycle breaking. **Shape:** `graph`. **Ops:** Yes, the default.
- **Why:** Matches the meaning of nearly every graph here, and is already bundled.
- **Refs:** [Sugiyama et al. 1981](https://doi.org/10.1109/TSMC.1981.4308636), [Gansner et al. 1993](https://doi.org/10.1109/32.221135), [Domrös et al. 2023](https://arxiv.org/abs/2311.00533)

### K3. Orthogonal · niche as a layout, used for routing
- **Use:** Box-and-line engineering diagrams. **Read:** Right-angle edges with few bends.
- **Limits:** Compaction is hard in general. ELK layered and libavoid already route this way.
- **Misuse:** A grid implies a regularity the system may not have. **Shape:** `graph`. **Ops:** Yes, through K2.
- **Why:** Already present as an edge-routing mode.
- **Refs:** [Tamassia 1987](https://doi.org/10.1137/0216030), Di Battista et al. 1999

### K4. Radial · useful (focus views only)
- **Use:** One focal node with rings by hop count: blast radius, ego graph.
- **Read:** Ring is distance from focus, and **that meaning is real**. Angle is arbitrary.
- **Limits:** Outer rings crowd beyond 2 or 3 hops.
- **Misuse:** Using it with no focal node. **Shape:** `graph` with `focus`. **Ops:** Impact around a failing service.
- **Why:** The one case where position honestly encodes a value.
- **Refs:** [Herman et al. 2000](https://doi.org/10.1109/2945.841119)

### K5. Arc diagram · niche
- **Use:** Nodes on a line, edges as arcs; suits sequences and repeats. **Read:** Node order is everything.
- **Limits:** Paths are hard to follow.
- **Misuse:** Arbitrary order creates false patterns. **Shape:** `graph`. **Ops:** Repeated rework in a single item's sequence.
- **Why:** A sequence diagram or matrix is more familiar.
- **Refs:** [Wattenberg 2002](https://doi.org/10.1109/INFVIS.2002.1173155)

### K6. Chord diagram · don't build
- **Use:** Flows between a few groups. **Read:** Ribbon width.
- **Limits:** Angle and area are read poorly, and direction is weak beyond a handful of groups.
- **Misuse:** Decorative. **Shape:** `graph`. **Ops:** Traffic between a few teams or regions.
- **Why:** A matrix shows the same data more accurately.
- **Refs:** [Krzywinski et al. 2009](https://doi.org/10.1101/gr.092759.109)

### K7. Hive plot · niche
- **Use:** Comparing large networks with a **deterministic** layout: nodes on axes by a chosen property.
- **Read:** Position is data, so two plots are comparable.
- **Limits:** Needs teaching; not widely recognised by operators.
- **Misuse:** Poor axis choice hides structure. **Shape:** `graph`. **Ops:** Comparing fleet topology across periods.
- **Why:** A sound idea that fails the recognised-diagram rule for this audience.
- **Refs:** [Krzywinski et al. 2011](https://doi.org/10.1093/bib/bbr069)

### K8. Matrix view
See **E7**. It is the required fallback once a graph exceeds the node-link budget.

### K9. Treemap · useful (for hierarchy with size)
- **Use:** Where capacity, cost or work sits within a hierarchy. **Read:** Area is size, colour is a second measure.
- **Limits:** Hides relations, and small values vanish.
- **Misuse:** Colour and area competing; comparing distant rectangles. **Shape:** `table` with a `parent` dimension. **Ops:** Backlog by system and team, sized by count and coloured by age.
- **Why:** Shows composition at a glance, with no edges to untangle.
- **Refs:** [Shneiderman 1992](https://doi.org/10.1145/102377.115768)

### K10. Sunburst · don't build
- **Use:** The same as a treemap, in polar form. **Read:** Arc length by ring.
- **Limits:** Angles are harder to compare than lengths, and outer rings get more area for the same value.
- **Misuse:** Chosen for looks. **Shape:** `table`. **Ops:** No advantage over K9.
- **Why:** K9 does this better.
- **Refs:** [Stasko & Zhang 2000](https://doi.org/10.1109/INFVIS.2000.885091)

## 12. Shared infrastructure

### 12.1 The `graph` result shape

**The catalog's position.** "A shape exists only if a chart needs a contract no other shape can satisfy", and structure was placed in page diagrams. The rule is good. Its conclusion holds for Dynamics and Blocks and fails for everything else.

**Why two tables are not enough.** A graph has a contract a `table` cannot state:

1. **Referential integrity.** Every edge end must name a node, and a node may have no edges. An isolated service is a finding, and an edge list loses it.
2. **Identity across results.** Diffing and time scrubbing need stable node IDs.
3. **Edge meaning.** "Depends on", "was followed by" and "sends traffic to" license different inferences.
4. **Whether paths are real.** This is the important one. A precedence chain holds transitively. A DFG or service-map path does not (X1). The renderer must know this to refuse or warn when someone traces a path.
5. **Completeness.** A graph cut to fit has hidden nodes, and any reachability or blast radius computed from it is wrong. A table has no way to say so.

**Evidence that the need is already here.** Three producers return graphs, each with its own field names: `process.py` (`nodes`, `edges` with `source`, `target`), `precedence.py` (`items`, `edges` with `from`, `to`) and `graph.py` (`nodes`, `edges`, `kind`). None can reach a Dashboard panel. Grafana reached the same conclusion with its nodes and edges frames [Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/).

**The shape.** Columnar, like the other shapes, inside the existing envelope:

```
kind:      process | state | dependency | wait_for | impact | service
           | sequence | trace | lineage | conformance    a closed list (§13.3)
directed:  true
nodes: {
  id:      [...]            stable across windows and versions
  label:   [...]
  type?:   [...]            service | state | item | person | external ...
  group?:  [...]            a declared group: system, namespace, team
  parent?: [...]            hierarchy, for collapse and drill-down
  fields:  [{ name, unit, role?, values }]
}                           role: rate | errors | latency | utilisation | wait
                                  | count | age | slack | exposure
edges: {
  id:       [...]           multi-edges allowed
  source:   [...]           must exist in nodes.id
  target:   [...]
  relation: [...]           calls | follows | blocks | owns | selects | caused ...
  evidence: [...]           observed | declared | both | inferred | simulated
  first_seen?, last_seen?: [...]
  n?:       [...]           observations behind the edge
  confidence?: [...]        required when evidence = inferred
  fields:   [{ name, unit, role?, values }]
}
semantics: {
  paths_real: bool          false: a route through two edges is not evidence
  acyclic:    bool | null   checked by the server, not assumed
  focus?:     [node ids]
}
time: {
  mode:   snapshot | window | frames | events | intervals
  since, until
  frames?: { t: [...], edge_values: {field: [[...], ...]}, node_values: {...} }
}
omitted: { nodes, edges, weight_share, how }    empty only if complete
diff?:   { against, nodes: [state...], edges: [state...] }   added | removed | changed | same
```

**Rules.**

- **Layout is never in the result.** A saved position is a page preference. The one exception is true coordinates (geography).
- **`paths_real` is mandatory.** There is no default. Each producer must state it.
- **`omitted` must be honest.** Reachability, impact and cycles run on the **full** graph on the server, then the result is cut for display.
- **Algorithms return existing shapes.** Cycles, cut sets, variants and centrality return a `table`. Overlays are fields on `graph`.
- **Dynamics and Blocks do not consume this shape.** Their notation stays in their renderers.
- **No graph query language.** The sources stay as they are:

```
A  prometheus  sum by (client, server)(rate(traces_service_graph_request_total[5m]))
B  analysis    graph(A, from="client", to="server", kind="service")

C  model       waits(kind="ticket")
D  model       impact(of="service.auth", hops=3)
E  model       process(kind="ticket", by="states")
```

The `sql` source can return a `table`, turned into a graph by the same `graph()` transform.

**Cardinality.** A `from`/`to` counter has up to *n²* series. Prometheus warns against high-cardinality labels [Prometheus](https://prometheus.io/docs/practices/naming/). Use states and service names as labels, and **never item IDs**. Per-item graphs come from SQL or the log.

### 12.2 Layout engine

**Keep ELK.** It is already loaded on every page (1.6 MB, `elk.bundled.js`), needs no build step, and drives the Dynamics, Blocks and Process views. Adding Cytoscape or D3-force would add weight to solve a problem we do not have.

| Graph | Layout | Implementation |
|---|---|---|
| Directed, up to the budget | ELK layered, with model order | Exists |
| One focus and its neighbourhood | Radial rings by hop | About 100 lines of plain SVG, no library [unsure of the size] |
| Over budget | Matrix | Existing heatmap renderer |
| Sequence, waterfall, Marey | Fixed axes, no graph layout | Own code on the existing plot stack |
| Undirected and small | ELK stress, under 100 nodes | Exists; rarely needed |

**Do not run a large layout on the main thread.** `util.js` creates `new ELK()` with no worker. Layered at the panel budget takes tens to a few hundred milliseconds, which is fine. A layout that could exceed about 200 ms should move to a Web Worker, which elkjs supports [elkjs](https://github.com/kieler/elkjs). The ELK paper itself notes elkjs is slower than Java ELK on larger graphs [Domrös et al. 2023](https://arxiv.org/abs/2311.00533).

### 12.3 Performance limits

ELK times in milliseconds (X9). Node 24 on one laptop, one run, no rendering. Browser times will differ, so treat these as orders of magnitude.

| Nodes | Edges | Layered | Stress | Force |
|---:|---:|---:|---:|---:|
| 50 | 150 | 142 | 282 | 272 |
| 100 | 300 | 214 | 948 | 849 |
| 200 | 600 | 355 | 3,390 | 3,235 |
| 400 | 1,200 | 688 | 13,529 | 12,894 |
| 800 | 1,200 | 767 | stopped at 45 s | 42,978 |
| 800 | 2,400 | 1,699 | stopped at 25 s | stopped at 25 s |

Layered stayed under 2 seconds in every case. **The real limit is the reader:** at 800 nodes and 2,400 edges the drawing was about 22,600 px wide.

**Proposed budgets.**

| Where | Nodes | Edges | Over budget |
|---|---:|---:|---|
| Dashboard panel | 40 | 100 | Collapse by group, then top-N with "+k more" |
| Page view | 60 for maps, 200 for dependencies | 160 for maps, 600 for dependencies | Collapse, or offer the matrix |
| Matrix | about 300 rows `[unsure]` | any | Group rows |
| Time scrubbing | same as the view | same as the view, 60 frames | Coarsen the step |
| Server graph for analysis | not limited separately | 50,000 `[unsure]` | Refuse with a reason |

The page budgets match what exists (`process.py` caps 60 nodes and 160 edges; the Items Graph caps 600 cards). Grafana's default is 200 visible nodes and it notes layered may be slow past 500 [Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/).

### 12.4 Aggregation and semantic zoom

Follow overview, then zoom and filter, then details on demand [Shneiderman 1996](https://doi.org/10.1109/VL.1996.545307). Aggregation must be **declared before inferred** [Elmqvist & Fekete 2010](https://doi.org/10.1109/TVCG.2009.84):

1. **Declared hierarchy first:** system → namespace → service → instance; or kind → state → item.
2. **Then by role:** fold leaves that have one neighbour into "+12 clients".
3. **Then by weight:** keep the top edges, and fold the rest into a visible "other" with its share.
4. **Communities only as a last resort,** labelled as inferred (J2).

**Semantic zoom** changes *what* is drawn, not only its size:

| Zoom | Node shows | Edge shows |
|---|---|---|
| Far | Group, health colour, count | Aggregated, width by rate |
| Middle | Name, one number | Direction, width |
| Near | Name, RED or wait stats | Rate, errors, latency labels |
| Click | Side panel with time series | Time series for that edge |

**Rules that keep aggregation honest:**

- An aggregated edge states how many edges it holds.
- A sum is valid for counts and rates. **Latency cannot be summed or averaged across edges:** merge histograms, or show the worst with its name.
- **Keep the outlier visible.** One red service in a green group must turn the group's marker red, or aggregation hides the incident.
- Filtering recomputes from events where possible, to avoid van der Aalst's invisible gaps (X4). If it cannot, the node states "20 went by routes not shown".

### 12.5 Time scrubbing

1. **One layout per scrub session,** computed over the **union** of nodes and edges in the window (X10).
2. **Frames carry values only:** edge and node fields on a fixed topology. 160 edges × 60 frames × 1 field is 9,600 numbers, small enough to send at once.
3. **Absent edges are ghosted**, so appearance and disappearance can be seen without any node moving.
4. **The scrubber is tied to a time-series strip**, and must share one "now" with every chart on the page. I did not check whether the charts share a cursor today.
5. **Prefer small multiples or a diff for comparison,** and use animation only for exploring. Archambault et al. compare these directly [Archambault et al. 2011](https://doi.org/10.1109/TVCG.2010.78); my recollection is that small multiples were generally faster `[unsure]`.
6. **As-of correctness.** A scrubbed graph must show the structure *as it was*, including the model version. Do not draw today's declared structure on last month's traffic.

## 13. Relationship to Blocks, Dynamics and the recognised-diagram rule

### 13.1 Each view answers a different question

| View | Discipline | Unit | Asks |
|---|---|---|---|
| **Dynamics** | System dynamics | Stocks, flows, feedback | Why does this behave this way over time? |
| **Blocks** | Control engineering | Signals, controllers, plants | Is this held to its goal, and is the loop good? |
| **Process** | Process mining | Activities and cases | What path does work really take? |
| **Items Graph, Timeline** | Project scheduling | Items and precedence | What must happen before this finishes? |
| **Service map** (a panel; a Diagram view only if a traffic source is attached) | SRE and observability | Services and traffic | What talks to what, and what is unhealthy? |
| **Graph panels** | Each diagram's own | As named | One question, from a query |

### 13.2 Keeping the two disciplines true

- **Never overlay** a process map or service map on Dynamics or Blocks. A process-map edge is a count of successions, a Dynamics flow is a rate into a stock, and a Blocks arrow is a signal. They look alike and mean different things.
- **Cross-link instead.** A stock counted from a state links to that state in the Process view; a controller links to its block. Selection can carry across, with each view keeping its notation.
- **Keep the algebra, skip the extra notations.** Signal-flow graphs, structural controllability and STPA run on the same model and report in tables or in Blocks' own notation. Do not add bond graphs, P&ID or RBDs, each of which looks close enough to Blocks to confuse it.
- **A cycle has opposite meanings.** In Dynamics and Blocks it is the feedback the product exists to show. In a dependency graph it is a defect. The `kind` decides the wording. A generic "cycles found" warning must never appear on a control model.
- **Queueing is the proper bridge.** Little's law and the utilisation law connect a process map's times to Dynamics' stocks and flows. They should be numbers that both views can cite, without merging the drawings.

### 13.3 Applying the recognised-diagram rule

The form is `graph`, but **the panel config must name a `kind` from a closed list**, each tied to a discipline and a reference. No "generic network" option exists. An unknown kind is refused with one sentence, in line with the catalog's verdicts.

| `kind` | Recognised as | Community |
|---|---|---|
| `process` | Process map / DFG | Process mining |
| `state` | State transition diagram | Software engineering |
| `conformance` | Conformance view | Process mining |
| `dependency` | Precedence network | Project management |
| `wait_for` | Wait-for graph | Operating systems |
| `impact` | Dependency / blast-radius graph | SRE |
| `service` | Service map | SRE |
| `sequence` | Sequence diagram | All of software |
| `trace` | Trace waterfall | Observability |
| `lineage` | Lineage graph | Data engineering |

Each kind fixes the encodings: which layout, whether a path may be traced, what a cycle means. A **"wait-for" with weighted arcs from a correlation query is refused**, because the query cannot have produced that relation.

## 14. Rankings, workflows and placement

### 14.1 Top 20

Ranked by how often the question arises × how much the answer changes a decision × how much of the data ergostat already holds.

| Rank | Diagram | Entry | State | Why here |
|---:|---|---|---|---|
| 1 | Process map, with rework corrected | C1 | Exists, fix | The core view of real work, and it currently overstates rework |
| 2 | Bottleneck overlay | D2 | New | Decides where capacity goes |
| 3 | Wait-for graph | E11 | New | The most direct answer to "what is holding everything up?" |
| 4 | Variant explorer | C6 | New | The honest view of actual paths |
| 5 | Declared versus observed | C4 | New | Compares intent with evidence |
| 6 | Impact graph | E10 | New | "What breaks if this fails?" |
| 7 | Service map | F1 | New | Runtime traffic, which no view draws today |
| 8 | Sequence diagram | A12 | New | "Why isn't this one done?" |
| 9 | Dependency DAG | E1 | Exists | Precedence |
| 10 | Critical path | E3 | Exists | What sets the date |
| 11 | Gantt with dependencies | E5 | Exists | Status across time |
| 12 | Cycles and SCCs | J3 | Partial | Required by layout, deadlock and dependency checks |
| 13 | Graph diff | J7 | New | "What changed?" |
| 14 | Adjacency / transition matrix | E7 | New | The answer to the hairball |
| 15 | Trace or run waterfall | F3 | New | One execution's time |
| 16 | Absorbing Markov analysis | B4 | New | Turns routing into expected attempts and completion share |
| 17 | Marey chart | C8 | New | Overtaking, batching, stalls |
| 18 | Flow-efficiency timeline | D6 | New | Work against waiting |
| 19 | Dominators and articulation points | E12 | New | Proven single points of failure |
| 20 | DSM | E6 | New | Modularity at scale |

**Close but out:** dotted chart (C5, cheap, and close to Marey), fault tree (G4, high value but hand-authored), STPA table (G11, valuable once hazards are declared), structural controllability (H4, belongs in `ergostat check` and should be done regardless, since it is a check rather than a diagram).

### 14.2 Analytical workflows

Each step says what it decides, so the chain stops as soon as the question is answered.

#### "What is holding everything up?"

1. **Stat and line:** are WIP and age rising while throughput is flat? If not, nothing systemic is wrong. Stop.
2. **Wait-for graph (E11):** rank roots by the work behind them.
3. **Age histogram with open items censored:** is the root's wait unusual or normal?
4. **Sequence diagram (A12)** on one blocked item: confirm the wait is real and see who was last to act.
5. **Bottleneck overlay (D2):** if there is no single root, a capacity constraint is the likely cause.
6. **Outcome:** a list of to-dos by root, grouped by who can act on them.

*Trap:* a stale `blocked_by`. Step 4 catches it.

#### "Why isn't this done?"

1. **The item's state and age** against its kind's survival curve: is it actually late?
2. **Precedence (E1, E3):** is it waiting on something? Follow to the root. If it is critical, its delay moves the end date.
3. **Sequence diagram (A12):** where did the time go?
4. **Variant (C6):** is this path common, or an exception? How long does that path usually take?
5. **Queue position and capacity (D2):** is it simply waiting its turn at a busy step?
6. **Levelled Gantt (E5):** when will it finish, with its assumption stated.

#### "What breaks if this fails?"

1. **Impact graph (E10)** from the focal node, split into hard, soft and unknown.
2. **Dominators (E12):** is anything cut off entirely?
3. **Edge rates over the last 7 to 30 days:** is each dependency live? Mark stale ones.
4. **Past incidents and events on the same axis:** did this really propagate before? (J8 removes impossible chains.)
5. **For modelled stocks, a what-if simulation:** how fast does the backlog grow, and when does it breach the goal?
6. **Outcome:** expected reach, its confidence, and which fallback to test.

*Trap:* reachability is an upper bound on structure and says nothing of retries or fallbacks.

#### "What path does work actually take versus the path we declared?"

1. **Conformance view (C4):** fitness and precision, and the top deviations.
2. **Variants (C6):** the real paths, with duration and outcome.
3. **Process map (C1), with concurrency marked:** where do they diverge?
4. **Compare outcomes:** are the deviating items faster, slower or more often reverted?
5. **Graph diff over time (J7):** did this deviation start at a change?
6. **Decide:** fix the process, change the declaration, or accept the exception. A deviation with better outcomes is a finding about the declaration.

#### "Where is the bottleneck?"

1. **Throughput against WIP** with bounds (D2): is the system past its knee?
2. **Utilisation and wait per station** on the process map or service map.
3. **Queue before, starvation after:** confirm that the suspect is constraining.
4. **Time series of utilisation by station:** is the bottleneck stable, or does it shift?
5. **Flow efficiency (D6):** if the top wait is a person or an external party, more machine capacity will do nothing.
6. **Queueing or what-if (D1):** predict the gain, including the **next** bottleneck.
7. **After the change:** a before-and-after comparison checks the prediction.

*Trap:* with finite buffers the longest queue may be far from the constraint, and betweenness points elsewhere altogether (X5).

#### During an incident: "what changed, and where?"

1. **Service map (F1), last 15 minutes:** the deepest unhealthy node.
2. **Graph diff (J7)** against the same time yesterday: any new edges?
3. **Event marks** on the time series: a deployment or config change before onset?
4. **Time-respecting check (J8):** did the suspect's errors start first?
5. **Waterfall (F3)** of a failing request, if traces exist.
6. **Impact (E10):** who to tell.

### 14.3 Where each belongs

No new pages are proposed.

**Dashboard panels** (query-driven, bounded, one question):

| Panel | Form | Shape |
|---|---|---|
| Blockers: top roots | `graph` (`wait_for`) or a table | `graph` / `table` |
| Service health map | `graph` (`service`) | `graph` |
| Small process map for one kind | `graph` (`process`) | `graph` |
| Impact of one named part | `graph` (`impact`) | `graph` |
| Top variants | table or bar | `table` |
| Transition or dependency matrix | heatmap | `table` |
| Marey and dotted charts | new XY options | `points` |
| Flow efficiency by step | bar | `table` |
| Bottleneck ranking | bar or table | `table` |

**Existing pages:**

| Page | Gets |
|---|---|
| **Diagram, Process view** (it replaced Wiring) | Rework fix, concurrency marks, variants, conformance, bottleneck overlay, graph diff |
| **Items, Graph and Timeline** | Wait-for mode, critical path (exists), swimlane grouping, SCC marks |
| **An item's page** | Sequence diagram, above its events |
| **Diagram page, other** | A service-map view only once a traffic source is attached and the panel proves too small |
| **Model / Check** | Workflow soundness, structural controllability, lineage of a goal's number |
| **Dynamics, Blocks** | Nothing drawn. Links out only |

**Do not build:** BPMN or UML activity editors, GRAFCET/SFC, process-algebra views, DEVS, activity cycle diagrams, bond graphs, P&ID, Ishikawa, stakeholder maps, per-person communication graphs, motif analysis, chord, sunburst, a Granger network drawing, a generic "importance" score, and a general-purpose graph explorer. Sankey stays cut, apart from an optional outcome split that a stacked bar already covers.

### 14.4 What to do first

1. **Fix the rework flag in `process.py`** so a line counts as rework only when an item actually returns to a step it has already visited. Do it first, since a wrong number is being displayed today.
2. **Say what filtering hides** on the affected nodes (X4).
3. **Define `graph`** with `paths_real` and `omitted`, and adapt the three existing producers. No visual change.
4. **Add the `waits` and `impact` model queries.** They need no new data.
5. **Variants and conformance** on the Process view.
6. **Add the service map as a panel kind.** `diagram-options.md` proposed it as Wiring's replacement, but the Process view took that place. Make it a Diagram view only if a traffic source is attached and a panel proves too small.
7. **Add the graph form to the Dashboard**, restricted to named kinds, with budgets.
8. **Graph diff and time scrubbing** with a fixed union layout.

### 14.5 Open questions and limits of this research

- **Diagram choice was not tested with users.** Rankings are my judgement from the literature, the code and the checks above. `diagram-options.md` says user flows come first, and this report does not replace that.
- **Budgets marked `[unsure]`** are engineering estimates. The ELK timings were not taken in a browser, and include no SVG rendering cost.
- **Concurrency detection** by "both orders are common" is a heuristic. It can mislabel genuine alternation as parallel work, and needs testing on real kinds.
- **The X checks are synthetic.** They show that an error *can* occur and how large it can be. They do not show how often it occurs in ergostat's own data. I did not read any live record.
- **Sources labelled [R] or [K]** were not reread for this report. Claims resting on them, particularly on individual study results, should be checked before being repeated as fact.
- **Some standards were not confirmed** at the publisher: the IEC and ISA entries marked [K] could have newer editions.

## 15. References

Evidence labels are defined at the top. DOIs labelled [R] resolved in Crossref on 2026-11-23 to the stated first author and title, and to the year where the record gives one. A few non-DOI [R] entries were confirmed from the publisher's page.

| Evidence | Reference | Work |
|---|---|---|
| R | [Ajmone Marsan et al. 1984](https://doi.org/10.1145/190.191) | *A class of generalized stochastic Petri nets* |
| R | [Alur et al. 1995](https://doi.org/10.1016/0304-3975(94)00202-T) | *The algorithmic analysis of hybrid systems* |
| K | Anderson 2010 | *Kanban* |
| K | ANSI/ISA-5.1 | Instrumentation symbols and identification |
| R | [Archambault et al. 2011](https://doi.org/10.1109/TVCG.2010.78) | *Animation, small multiples, and the effect of mental map preservation in dynamic graphs* |
| R | [Barnett et al. 2009](https://doi.org/10.1103/PhysRevLett.103.238701) | *Granger causality and transfer entropy are equivalent for Gaussian variables* |
| R | [Baskett et al. 1975](https://doi.org/10.1145/321879.321887) | *Open, closed, and mixed networks of queues* |
| R | [Beck et al. 2016](https://doi.org/10.1111/cgf.12791) | *A taxonomy and survey of dynamic graph visualization* |
| R | [Behrisch et al. 2016](https://doi.org/10.1111/cgf.12935) | *Matrix reordering methods for table and network visualization* |
| R | [Beschastnikh et al. 2016](https://doi.org/10.1145/2927299.2940294) | *Debugging distributed systems* |
| R | [Bird et al. 2011](https://doi.org/10.1145/2025113.2025119) | *Don't touch my code!* |
| R | [Blondel et al. 2008](https://doi.org/10.1088/1742-5468/2008/10/P10008) | *Fast unfolding of communities in large networks* |
| R | [Bolch et al. 2006](https://doi.org/10.1002/0471791571) | *Queueing Networks and Markov Chains* |
| R | [Borgatti 2005](https://doi.org/10.1016/j.socnet.2004.11.008) | *Centrality and network flow* |
| R | [Brandes 2001](https://doi.org/10.1080/0022250X.2001.9990249) | *A faster algorithm for betweenness centrality* |
| R | [Browning 2001](https://doi.org/10.1109/17.946528) | *Applying the design structure matrix* |
| R | [Burch et al. 2011](https://doi.org/10.1109/TVCG.2011.226) | *Parallel edge splatting for scalable dynamic graph visualization* |
| O | [C4 model](https://c4model.com/) | Documentation |
| R | [Carmona et al. 2018](https://doi.org/10.1007/978-3-319-99414-7) | *Conformance Checking* |
| R | [Cataldo et al. 2008](https://doi.org/10.1145/1414004.1414008) | *Socio-technical congruence* |
| S | [Chow et al. 2014](https://www.usenix.org/node/186168) | *The Mystery Machine*, OSDI |
| R | [Commoner et al. 1971](https://doi.org/10.1016/S0022-0000(71)80013-2) | *Marked directed graphs* |
| K | [Conway 1968](https://www.melconway.com/Home/Committees_Paper.html) | *How do committees invent?* |
| R | [Cornelissen et al. 2009](https://doi.org/10.1109/TSE.2009.28) | *A systematic survey of program comprehension through dynamic analysis* |
| S | [Cowan et al. 2012](https://arxiv.org/abs/1106.2573) | *Nodal dynamics, not degree distributions, determine the structural controllability of complex networks* (preprint record) |
| R | [David & Alla 2010](https://doi.org/10.1007/978-3-642-10669-9) | *Discrete, Continuous, and Hybrid Petri Nets* |
| R | [Denning & Buzen 1978](https://doi.org/10.1145/356733.356735) | *The operational analysis of queueing network models* |
| K | Di Battista et al. 1999 | *Graph Drawing: Algorithms for the Visualization of Graphs* |
| O | [Domrös et al. 2023](https://arxiv.org/abs/2311.00533) | *The Eclipse Layout Kernel* |
| R | [Eades et al. 1993](https://doi.org/10.1016/0020-0190(93)90079-O) | *A fast and effective heuristic for the feedback arc set problem* |
| S | [elkjs](https://github.com/kieler/elkjs) | Repository and README |
| R | [Elmqvist & Fekete 2010](https://doi.org/10.1109/TVCG.2009.84) | *Hierarchical aggregation for information visualization* |
| R | [Eppinger & Browning 2012](https://doi.org/10.7551/mitpress/8896.001.0001) | *Design Structure Matrix Methods and Applications* |
| R | [Ford & Fulkerson 1956](https://doi.org/10.4153/CJM-1956-045-5) | *Maximal flow through a network* |
| R | [Fortunato & Barthélemy 2007](https://doi.org/10.1073/pnas.0605965104) | *Resolution limit in community detection* |
| R | [Freeman 1977](https://doi.org/10.2307/3033543) | *A set of measures of centrality based on betweenness* |
| R | [Fruchterman & Reingold 1991](https://doi.org/10.1002/spe.4380211102) | *Graph drawing by force-directed placement* |
| R | [Gansner et al. 1993](https://doi.org/10.1109/32.221135) | *A technique for drawing directed graphs* |
| S | [Ghoniem et al. 2004](https://doi.org/10.1109/INFVIS.2004.1) | *A comparison of the readability of graphs using node-link and matrix-based representations* |
| R | [Ghoniem et al. 2005](https://doi.org/10.1057/palgrave.ivs.9500092) | *On the readability of graphs using node-link and matrix-based representations* |
| K | Goldratt 1997 | *Critical Chain* |
| R | [Good et al. 2010](https://doi.org/10.1103/PhysRevE.81.046106) | *Performance of modularity maximization in practical contexts* |
| R | [Gordon & Newell 1967](https://doi.org/10.1287/opre.15.2.254) | *Closed queuing systems with exponential servers* |
| O | [Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/) | Node graph visualization documentation |
| O | [Grafana Tempo](https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/) | Service graphs documentation |
| R | [Graham 1969](https://doi.org/10.1137/0117039) | *Bounds on multiprocessing timing anomalies* |
| R | [Granger 1969](https://doi.org/10.2307/1912791) | *Investigating causal relations by econometric models* |
| O | [Gregg](https://www.brendangregg.com/flamegraphs.html) | Flame Graphs |
| R | [Gregg 2016](https://doi.org/10.1145/2909476) | *The flame graph*, CACM |
| R | [Günther & van der Aalst 2007](https://doi.org/10.1007/978-3-540-75183-0_24) | *Fuzzy mining* |
| R | [Harel 1987](https://doi.org/10.1016/0167-6423(87)90035-9) | *Statecharts: a visual formalism for complex systems* |
| R | [Henzinger 1996](https://doi.org/10.1109/LICS.1996.561342) | *The theory of hybrid automata* |
| R | [Herman et al. 2000](https://doi.org/10.1109/2945.841119) | *Graph visualization and navigation in information visualization: a survey* |
| S | [Herroelen & Leus 2001](https://doi.org/10.1016/S0272-6963(01)00054-7) | *On the merits and pitfalls of critical chain scheduling* (abstract record) |
| K | Hoare 1978 | *Communicating sequential processes*, CACM |
| R | [Holme & Saramäki 2012](https://doi.org/10.1016/j.physrep.2012.03.001) | *Temporal networks* |
| R | [Holt 1972](https://doi.org/10.1145/356603.356607) | *Some deadlock properties of computer systems* |
| R | [Holten 2006](https://doi.org/10.1109/TVCG.2006.147) | *Hierarchical edge bundles* |
| R | [Hopcroft & Tarjan 1973](https://doi.org/10.1145/362248.362272) | *Algorithm 447: efficient algorithms for graph manipulation* |
| R | [Howard & Matheson 2005](https://doi.org/10.1287/deca.1050.0020) | *Influence diagrams* |
| O | [ICAO training material](https://www.icao.int/sites/default/files/SMI/TrainingDocs/Chapter%202%20Safety%20Management%20Fundamentals/2.6-05-SRM-Methodology-STPA.pdf) | *SRM Methodology: STPA* (states the four unsafe control action types) |
| S | IEC 60812 | Failure mode and effects analysis |
| K | IEC 60848; IEC 61131-3 | GRAFCET specification language; PLC programming languages (SFC) |
| S | IEC 61025 | *Fault tree analysis* |
| K | IEC 61078 | Reliability block diagrams |
| K | IEC 62502 | Event tree analysis |
| K | IEC/ISO 31010 | Risk assessment techniques (includes bow-tie) |
| K | Ishikawa | *Guide to Quality Control* |
| O | [Istio](https://istio.io/latest/docs/reference/config/metrics/) | Standard metrics reference |
| O | [ITU-T Z.120 (2011)](https://www.itu.int/rec/T-REC-Z.120) | *Message Sequence Chart* |
| R | [Jackson 1957](https://doi.org/10.1287/opre.5.4.518) | *Networks of waiting lines* |
| R | [Jackson 1963](https://doi.org/10.1287/mnsc.10.1.131) | *Jobshop-like queueing systems* |
| O | [Jaeger](https://www.jaegertracing.io/docs/latest/features/) | Features documentation |
| R | [Jensen & Kristensen 2009](https://doi.org/10.1007/b95112) | *Coloured Petri Nets* |
| R | [Johnson 1975](https://doi.org/10.1137/0204007) | *Finding all the elementary circuits of a directed graph* |
| R | [Kamada & Kawai 1989](https://doi.org/10.1016/0020-0190(89)90102-6) | *An algorithm for drawing general undirected graphs* |
| R | [Karnopp et al. 2012](https://doi.org/10.1002/9781118152812) | *System Dynamics: Modeling, Simulation, and Control of Mechatronic Systems* |
| R | [Karp & Miller 1969](https://doi.org/10.1016/S0022-0000(69)80011-5) | *Parallel program schemata* |
| R | [Kelley & Walker 1959](https://doi.org/10.1145/1460299.1460318) | *Critical-path planning and scheduling* |
| R | [Kelley 1961](https://doi.org/10.1287/opre.9.3.296) | *Critical-path planning and scheduling: mathematical basis* |
| O | [Kiali](https://kiali.io/docs/features/topology/) | Topology documentation |
| R | [Kingman 1961](https://doi.org/10.1017/S0305004100036094) | *The single server queue in heavy traffic* |
| R | [Krzywinski et al. 2009](https://doi.org/10.1101/gr.092759.109) | *Circos* |
| R | [Krzywinski et al. 2011](https://doi.org/10.1093/bib/bbr069) | *Hive plots: rational approach to visualizing networks* |
| O | [Kubernetes](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/) | Owners and dependents |
| R | [Lamport 1978](https://doi.org/10.1145/359545.359563) | *Time, clocks, and the ordering of events in a distributed system* |
| O | [Lazowska et al. 1984](https://homes.cs.washington.edu/~lazowska/qsp/) | *Quantitative System Performance* (full text from the authors) |
| R | [Leemans et al. 2013](https://doi.org/10.1007/978-3-642-38697-8_17) | *Discovering block-structured process models from event logs* |
| R | [Lengauer & Tarjan 1979](https://doi.org/10.1145/357062.357071) | *A fast algorithm for finding dominators in a flowgraph* |
| S | [Leveson & Thomas 2018](https://www.flighttestsafety.org/images/STPA_Handbook.pdf) | *STPA Handbook* (the copy found refused automated access) |
| R | [Leveson 2004](https://doi.org/10.1016/S0925-7535(03)00047-X) | *A new accident model for engineering safer systems* |
| R | [Leveson 2012](https://doi.org/10.7551/mitpress/8179.001.0001) | *Engineering a Safer World* |
| R | [Lin 1974](https://doi.org/10.1109/TAC.1974.1100557) | *Structural controllability* |
| R | [Little 1961](https://doi.org/10.1287/opre.9.3.383) | *A proof for the queuing formula L = λW* |
| R | [Little 2011](https://doi.org/10.1287/opre.1110.0940) | *Little's Law as viewed on its 50th anniversary* |
| R | [Liu et al. 2011](https://doi.org/10.1038/nature10011) | *Controllability of complex networks* |
| R | [MacCormack et al. 2012](https://doi.org/10.1016/j.respol.2012.04.011) | *Exploring the duality between product and organizational architectures* |
| R | [Malcolm et al. 1959](https://doi.org/10.1287/opre.7.5.646) | *Application of a technique for R&D program evaluation* (PERT) |
| R | [Mason 1953](https://doi.org/10.1109/JRPROC.1953.274449) | *Feedback theory: some properties of signal flow graphs* |
| K | Mendelow 1991 | Power-interest grid, as usually attributed |
| R | [Milo et al. 2002](https://doi.org/10.1126/science.298.5594.824) | *Network motifs* |
| R | [Milo et al. 2004](https://doi.org/10.1126/science.1089167) | *Superfamilies of evolved and designed networks* |
| R | [Molloy 1982](https://doi.org/10.1109/TC.1982.1676110) | *Performance analysis using stochastic Petri nets* |
| R | [Munzner 2014](https://doi.org/10.1201/b17511) | *Visualization Analysis and Design* |
| R | [Murata 1989](https://doi.org/10.1109/5.24143) | *Petri nets: Properties, analysis and applications*, Proc. IEEE |
| R | [Nagappan et al. 2008](https://doi.org/10.1145/1368088.1368160) | *The influence of organizational structure on software quality* |
| R | [Newman & Girvan 2004](https://doi.org/10.1103/PhysRevE.69.026113) | *Finding and evaluating community structure in networks* |
| R | [Newman 2006](https://doi.org/10.1073/pnas.0601602103) | *Modularity and community structure in networks* |
| R | [Newman 2018](https://doi.org/10.1093/oso/9780198805090.001.0001) | *Networks*, 2nd ed. |
| O | [OCEL 2.0](https://www.ocel-standard.org/) | Object-Centric Event Log standard |
| S | [Okoe et al. 2019](https://doi.org/10.1109/TVCG.2018.2865940) | *Node-link or adjacency matrices: old question, new insights* |
| R | [Olfati-Saber et al. 2007](https://doi.org/10.1109/JPROC.2006.887293) | *Consensus and cooperation in networked multi-agent systems* |
| O | [OMG 2014](https://www.omg.org/spec/BPMN/2.0.2/About-BPMN) | *Business Process Model and Notation*, version 2.0.2 |
| O | [OMG 2017](https://www.omg.org/spec/UML/2.5.1/About-UML) | *Unified Modeling Language*, version 2.5.1 |
| O | [OpenLineage](https://openlineage.io/docs/) | Documentation |
| O | [OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/) | Messaging spans semantic conventions (status: Development) |
| K | Paynter 1961 | *Analysis and Design of Engineering Systems* |
| R | [Pearl 1995](https://doi.org/10.1093/biomet/82.4.669) | *Causal diagrams for empirical research* |
| R | [Pearl 2009](https://doi.org/10.1017/CBO9780511803161) | *Causality*, 2nd ed. |
| O | [Prometheus](https://prometheus.io/docs/practices/naming/) | Metric and label naming |
| R | [Puterman 1994](https://doi.org/10.1002/9780470316887) | *Markov Decision Processes* |
| R | [Rabiner 1989](https://doi.org/10.1109/5.18626) | *A tutorial on hidden Markov models* |
| R | [Reiser & Lavenberg 1980](https://doi.org/10.1145/322186.322195) | *Mean-value analysis of closed multichain queuing networks* |
| R | [Riehmann et al. 2005](https://doi.org/10.1109/INFVIS.2005.1532152) | *Interactive Sankey diagrams* |
| R | [Rosvall & Bergstrom 2010](https://doi.org/10.1371/journal.pone.0008694) | *Mapping change in large networks* |
| K | Rother & Shook 1999 | *Learning to See* |
| R | [Runge et al. 2019](https://doi.org/10.1126/sciadv.aau4996) | *Detecting and quantifying causal associations in large nonlinear time series datasets* |
| R | [Schneier 1999](https://www.schneier.com/academic/archives/1999/12/attack_trees.html) | *Attack trees* |
| R | [Schreiber 2000](https://doi.org/10.1103/PhysRevLett.85.461) | *Measuring information transfer* |
| R | [Schruben 1983](https://doi.org/10.1145/182.358460) | *Simulation modeling with event graphs* |
| R | [Seidman 1983](https://doi.org/10.1016/0378-8733(83)90028-X) | *Network structure and minimum degree* |
| R | [Shneiderman 1992](https://doi.org/10.1145/102377.115768) | *Tree visualization with tree-maps* |
| R | [Shneiderman 1996](https://doi.org/10.1109/VL.1996.545307) | *The eyes have it* |
| O | [Sigelman et al. 2010](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) | *Dapper, a large-scale distributed systems tracing infrastructure* |
| R | [Soldani & Brogi 2022](https://doi.org/10.1145/3501297) | *Anomaly detection and failure root cause analysis in (micro)service-based cloud applications: a survey* |
| K | Song & van der Aalst 2007 | *Supporting process mining by showing events at a glance* |
| R | [Spirtes et al. 2001](https://doi.org/10.7551/mitpress/1754.001.0001) | *Causation, Prediction, and Search* |
| R | [Stasko & Zhang 2000](https://doi.org/10.1109/INFVIS.2000.885091) | *Focus+context display and navigation techniques for radial, space-filling hierarchy visualizations* |
| R | [Steward 1981](https://doi.org/10.1109/TEM.1981.6448589) | *The design structure system* |
| R | [Sugiyama et al. 1981](https://doi.org/10.1109/TSMC.1981.4308636) | *Methods for visual understanding of hierarchical system structures* |
| R | [Tamassia 1987](https://doi.org/10.1137/0216030) | *On embedding a graph in the grid with the minimum number of bends* |
| R | [Tarjan 1972](https://doi.org/10.1137/0201010) | *Depth-first search and linear graph algorithms* |
| K | Tocher 1963 | *The Art of Simulation* (activity cycle diagrams) |
| R | [Traag et al. 2019](https://doi.org/10.1038/s41598-019-41695-z) | *From Louvain to Leiden* |
| K | Tufte 1983 | *The Visual Display of Quantitative Information* (Marey's train schedule) |
| R | [van der Aalst 1998](https://doi.org/10.1142/S0218126698000043) | *The application of Petri nets to workflow management* |
| R | [van der Aalst 2016](https://doi.org/10.1007/978-3-662-49851-4) | *Process Mining: Data Science in Action* |
| O | [van der Aalst 2019](https://www.vdaalst.com/publications/p1101.pdf) | *A practitioner's guide to process mining: limitations of the directly-follows graph* |
| R | [van der Aalst 2019](https://doi.org/10.1007/978-3-030-30446-1_1) | *Object-centric process mining: dealing with divergence and convergence* |
| R | [van der Aalst et al. 2012](https://doi.org/10.1002/widm.1045) | *Replaying history on process models* |
| O | [Vesely et al. 1981](https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr0492/index.html) | *Fault Tree Handbook*, NUREG-0492 |
| O | [W3C 2013](https://www.w3.org/TR/prov-overview/) | *PROV-Overview* |
| R | [Wattenberg 2002](https://doi.org/10.1109/INFVIS.2002.1173155) | *Arc diagrams* |
| K | Weijters et al. 2006 | *Process mining with the HeuristicsMiner algorithm*, technical report |
| K | Zeigler et al. | *Theory of Modeling and Simulation* |

**Totals:** 155 references: 22 opened, 105 confirmed from a record, 9 from search only, 19 from memory. A reference with no link has no stable public URL that I confirmed.
