# Architecture: asking the hard questions of a large model

The owner, 2026-11-19: when models get large, ask the hard questions. Are our large systems actually several
smaller ones? Should small systems merge? Are the interfaces between systems rational? What systems should we
have for what we are trying to do, and does the model cover our intent? Answer them with the methods system
dynamics and control engineering use for very large systems, computed where possible. The computed measures are
the rule rung of the ladder; an AI reviewer comes later, and reads them.

This is the design, method by method: where each comes from, what ergostat can compute today from the model and
the record, what it cannot, and how its finding reads. The computed rung is built (`ergostat/spec/architecture.py`;
`check` notes `system-splits`, `systems-merge`, `interface`, `time-scales`, `purpose`; each system's size in
`explain` and its panel). The last section says what they find in the examples.

Every measure works on one graph: the model's causal links (`spec/causal.py`: flow to stock, `driven-by`, what
a goal is about, what a block reads and what it moves, sets or commands), undirected and counted, an implied
block's links taken as its goal's. A system's graph is its own parts with each subsystem drawn as one node (its
inside links a loop on that node). Nothing is simulated: the one measure that needs numbers (time constants)
evaluates the equations once, at the model's start.

## 1. The design structure matrix, and modularity clustering

**Source.** Steward, "The design structure system", *IEEE Trans. Eng. Mgmt.* 1981; Eppinger and Browning,
*Design Structure Matrix Methods and Applications*, MIT Press 2012 (clustering a component DSM into modules);
Newman and Girvan, "Finding and evaluating community structure in networks", *Phys. Rev. E* 2004 (modularity Q:
the share of links inside groups less what random links of the same degrees would put there; above about 0.3 is
structure) and Newman, *PNAS* 2006; Clauset, Newman and Moore 2004 (greedy agglomeration). In software the same pair is coupling and
cohesion (Stevens, Myers and Constantine 1974).

**Computed today.** Modularity clustering of the system's link graph, an analogue of clustering its DSM, not the
same algorithm (DSM clustering minimises a coordination cost over a reordered matrix; modularity compares links
inside groups with chance). Greedy modularity clustering joins the two linked groups whose joining raises Q most,
while one does; then a group of fewer than 4 parts joins the group it links to most, and two groups joined by more
than a tenth of the links inside the smaller are one. The tenth is a heuristic, set on the examples: it keeps a
pipeline's stages (each tied to the next by its flow) together, which modularity alone calls modules. What is left,
two groups or more at Q of 0.4 or more in a system (or the top level) of 20 parts or more, is read two ways. When
the groups are the system's own subsystems, it is **nearly decomposable** (Simon 1962): the shape of a good
hierarchy, each subsystem understood and redesigned alone. That is information, said by `explain`, never a note
asking for work. When some groups are loose parts in no subsystem of their own, `system-splits` names those. Two sibling systems with at least three links between them, and at least as many
as inside the smaller, are `systems-merge`.

**Not computed.** The strength of a link (how much of the effect's variance the cause explains) needs the record
and a fitted model; every link counts one. Partitioning by the record's co-movement (which parts change together)
is left for the AI rung.

**Reads.** `system lab: its parts fall into 6 clusters with 0 links between them (modularity 0.72):
[goal.ideas-ready, goal.one-running, ...]; [goal.done-as-meant, ...]; .... Each may be a system of its own
(systems:, and system: on its parts), redesigned on its own; or a link between them is missing.` (at most six
clusters listed). `explain system.job`: `It is nearly decomposable: its systems fall into 10 groups with 1 link
between them (modularity 0.88); each can be understood and redesigned alone.` And `system a: more of its links
go to b (3 links between them; 2 inside a, 6 inside b) than stay inside it: the boundary cuts through one system.`

## 2. Time-scale separation: singular perturbation and hierarchical control

**Source.** Kokotović, Khalil and O'Reilly, *Singular Perturbation Methods in Control*, 1986: when part of a system
settles much faster than the rest, the slow part sees the fast one as already settled, and each can be designed
on its own; Simon and Ando, "Aggregation of variables in dynamic systems", *Econometrica* 1961, and Simon, "The
architecture of complexity", 1962 (nearly decomposable systems); Mesarović, Macko and Takahara, *Theory of
Hierarchical, Multilevel Systems*, 1970; Skogestad and Postlethwaite, *Multivariable Feedback Control*, ch. 10
(cascade and hierarchical structures: the inner loop much faster than the outer, by a factor of 5 to 10).

**Computed today.** Each part's time constant as the model stands: a stock's own drain (1 over its Jacobian's
diagonal) and a delay's time, from one evaluation of the equations at the model's start (`numbers/extremes.py`,
`time_constants`, the same estimate the extreme-conditions tests size their runs by), and a goal's loop by its
identified process (`process: time-constant`). This is a screen, not the system's modes: each stock's own time
constant, not the eigenvalues of the whole. Within a system, its own parts sorted by time constant; a gap of more
than 10 times between neighbours (above 10, not at it), with the fast and slow parts linked within the system, is
`time-scales`, naming the fast and the slow. Two time scales that never meet have nothing to arrange.

**Not computed.** A stock with no equation (measured only) has no time constant; most observed models are mostly
such stocks, so the measure is silent on them until equations are fitted. A loop's closed-loop speed (its
controller's period, its answer time from the record: `back_in` on the loop's panel) is not yet used; nor are
the eigenvalues of the whole Jacobian (modes, not parts).

**Reads.** `system plant: its parts run on time scales 20 times apart: fast [stock.fast 6m], slow [stock.slow
1h59m], linked within it. Each stock's own time constant is a screen, not the system's modes; if they hold, the
fast settle before the slow move (singular perturbation), so they are a candidate inner system, given its setpoint
by the slow (hierarchical control).`

## 3. The relative gain array: interaction between loops

**Source.** Bristol, "On a new measure of interaction for multivariable process control", *IEEE TAC* 1966;
Skogestad and Postlethwaite ch. 3.4 and 10.6: Λ = G ⊙ (G⁻¹)ᵀ of the steady-state gains from each valve to each
held quantity; pair loops on λ near 1, never on a negative λ; large λ means the loops fight.

**Computed today.** Per system, from the step tests the owner approved (`control/rga.py`, SPEC §12d): each test
made of the system as it is now (its stamp of the system's process matches) gives every loop's Δu and Δy over the
last quarter of its hold; the latest 12 are fitted together by least squares (ΔY = ΔU Gᵀ, the other controllers
acting), and Λ = G ⊙ (G⁻¹)ᵀ is said as one line of `explain system.NAME`, on the pairing as built, with a negative
λ, a λ past 10 and, with two loops, a better pairing swapped. Not computed, and why: integrating loops, more than 8
loops, too few tests or a loop with none, collinear moves (ΔU's 1-norm condition past 100), singular gains.
Structurally, `competing-commands` (two controllers on one block) and `own-disturbance` are the extreme cases;
`interface` says when a block outside moves or commands what a system's own loops use (a reach-in: two
controllers on one path).

**Not computed.** A model with no systems has no relative gain array. The other pairings beyond a two-loop swap,
the array's frequency dependence, and a finding or request from it (it is said by `explain` only).

**Reads.** `Relative gain array: λ g1 1.25, g2 1.25 (each loop on its own u, from 2 step tests, the gains as held
over the last quarter of each hold).`

## 4. Loop dominance and eigenvalue elasticity: which parts matter, and aggregation

**Source.** Forrester, "Market growth as influenced by capital investment", 1968 and Richardson, "Dominant
structure", *SDR* 1986; Kampmann, "Feedback loop gains and system behaviour", 1996/2012; Saleh, Oliva, Kampmann and
Davidsen, "A comprehensive analytical approach for policy analysis of system dynamics models", *EJOR* 2010
(eigenvalue elasticity analysis); Schoenberg, Davidsen and Eberlein, "Loops That Matter", *SDR* 2020; for
aggregation, Simon and Ando 1961 and Iwasaki and Simon 1994.

**Computed today.** Loops That Matter on the replay (`numbers/dominance.py`, each loop's panel): which loop drives
each stock over the window. The count of loops inside each system and through it (`size`, below). The computed rung
of aggregation (`numbers/aggregation.py`, an `aggregate` row on a system's Dynamics panel, SPEC §12c): a linear
chain of a system's own stocks, each with its own drain, that no loop beyond each stock's own drove over the window
the page shows, every loop through it scored and named. It reads: `over the window (2026-11-20 09:00 to 2026-11-20
10:00) no feedback loop beyond each stock's own drove stock.ramps-briefed, stock.ramps-to-research: a candidate to
aggregate into one delay`. A candidate, not a finding: it says nothing beyond the window, and nothing is proposed.

**Not computed.** Eigenvalue elasticity needs the Jacobian over time and its eigenvectors: one Jacobian is already
taken for time constants, so the elasticities at the start are a small step; over the replay they are a
simulation, kept out of `check`. The proposal to aggregate (the chain replaced by one stock or one delay, judged
over a long record) is the AI rung's, with the computed candidates and LTM as its evidence.

## 5. Interface control documents: what crosses each boundary

**Source.** Systems engineering's interface management: NASA *Systems Engineering Handbook* (SP-2016-6105, §6.3)
and ISO/IEC/IEEE 15288 (an interface control document per boundary: what crosses, its units, its owner);
Parnas, "On the criteria to be used in decomposing systems into modules", 1972 (hide what changes; the interface
is what does not); in control, the cascade: an outer loop gives an inner one its setpoint, and nothing else.

**Computed today.** Each boundary's crossings are already worked out, never written (`Spec.interface`, SPEC §4a:
setpoint, command, action, signal, material, influence; `explain system.NAME` lists them). `interface` says what
crosses by kind, when one of three is true: material crosses through clouds on both sides (a flow to a cloud on
one side drives a flow from a cloud on the other, in one unit: what is conserved is lost at the boundary); a block
outside moves or commands what the system's own goals' loops use (filing work into a queue is not: that is how
systems hand work on); or ten or more information links cross it (a heuristic, set on the examples).

**Not computed.** Whether a crossing is stable (an ICD's point is a boundary that changes slowly): the model's
history (`history.py`) has every version, and how often each boundary's crossings changed is a count over it.

**Reads.** `system down: what crosses its boundary: 1 command, 1 influence. material crosses through clouds on both
sides: flow.shipped leaves for a cloud and flow.received arrives from one, driven by it; one flow from shipped's
stock to received's keeps what is conserved; block.boss (outside) commands block.kitter, which its own goals' loops
use: it reaches into its internals; a setpoint for one of its goals is the interface a hierarchy uses.`

## 6. The boundary chart and the subsystem diagram

**Source.** Sterman, *Business Dynamics*, 2000, ch. 3.5: the model boundary chart (endogenous, exogenous,
excluded) and the subsystem diagram (the model's main parts and the flows of material, money, people and
information between them).

**Computed today.** The boundary: `many-cloud-inflows` and `kind-enters-many-times` (`spec/chains.py`), and every
exogenous input (`numbers/extremes.py`'s inputs). The subsystem diagram is the Graph and Dynamics pages with every
system closed: each a box with its ports. Each system's size (parts, feedback loops inside and through it, levels of
systems within it) is in `explain` (`- incidents: 1 in, 0 out; 24 parts, 6 feedback loops inside`, and `Size:` on
`explain system.NAME`) and on the system's panel.

**Not computed.** What is excluded is not in the model by definition; the owner's intent (below) is where it is said.

## 7. Purpose and goal traceability

**Source.** Requirements traceability (Gotel and Finkelstein, "An analysis of the requirements traceability
problem", 1994): every requirement traced to a need, every need to something that meets it; in control, every
loop holds a goal for a reason. Sterman ch. 3.2: a model is built for a purpose, and judged against it.

**Computed today.** `purpose`, in a model with systems: a system with no `description` (its purpose); a described
system whose blocks act for no goal inside it (a system of stocks with no goal, a plant's sector, is normal and not
said); goals in no described system, when the model has no
`purpose:` (a top-level key, the main file only, kept small: one sentence of what the whole model is for).

**Not computed.** Whether a goal serves its system's purpose, or whether the goals together cover it, is a reading
of the words: the AI rung, with the descriptions and the goals as its input.

**Reads.** `system idle: is for "nothing yet", and its blocks act for no goal inside it: its purpose is not
measured`; `goals in-review-clear, nothing-ready-waits: in no system that says what it is for, and
the model has no purpose: to trace them to`.

## 8. Beer's Viable System Model, as a checklist for purpose coverage

**Source.** Beer, *Brain of the Firm*, 1972 and *The Heart of Enterprise*, 1979; Espejo and Reyes, *Organizational
Systems*, 2011. A viable system has five functions: S1 the operations that do the work; S2 coordination that damps
oscillation between them; S3 control of the operations now (resources, audit, S3*); S4 intelligence, the outside
and the future; S5 policy, identity and purpose. Each S1 is itself viable (recursion).

**Computed today.** Nothing as a finding. The structure answers parts of it: S1 are systems whose goals hold
stocks of the work; S2, which damps oscillation between the operations, shows as what they share and are
scheduled by (a pool, a lease tier) across systems; S3 as goals that set other
goals' setpoints (a cascade's outer loop, `inner_loops`); S3* as sensors that audit (claims, the intent judge); S4 as
a modelling loop (`use: modelling`: the model of the outside, improved); S5 as `purpose:` and the owner's accept
policy.

**Not computed.** The mapping is a judgement: the AI rung reads each system against the five, recursively, and
says which is missing (no S4 in a system that faces a changing outside; no S2 where two operations share a
resource and oscillate). Its evidence is the measures above.

**Would read.** `system delivery: S1 (the work) and S3 (the goals on it) are here, and nothing looks outside it
(S4): when the arrivals change, nothing in it notices.`

## The ladder

The computed measures are the rule rung: fast, deterministic, the same every time, and quiet when nothing is
found. The AI rung comes next, per system, not on the whole model at once: the redesign that failed on the-job
edited the whole model in one change. It takes one system's notes, its interface and its parts, proposes a change
to that system alone, and the judge tests it. The notes say where to start: loose parts that split are two redesigns;
a pair that should merge is one; a nearly decomposable system is already as many redesigns as its subsystems.

## What the examples say

Run over every example on main at 2ed2f16 (`ergostat check` and `explain`; each well under 50 ms), after the gate
review's fixes:

| Example | Notes |
|---|---|
| alert-triage | `interface@system.alerts`: block.investigate (in investigation) moves flow.alerts-investigated, between two of alerts' stocks, which alerts' loops use: a reach-in. (alerts and investigation have 5 links between them against 7 inside investigation: the nearest to a merge of any example, at 0.71 of the threshold.) |
| big | `purpose` on its six systems (none described) and on its 24 goals (traced to nothing). |
| deps, docs-fresh | `purpose`: the one system is not described; its goals are traced to nothing. |
| image-squeeze | `system-splits@system.lab`: six clusters with no link between them (ideas and experiments; done-as-meant; sessions and spend; claims; decisions; messages): the lab is several systems. `interface@system.lab`: 11 information links cross its boundary, a wide interface. |
| roadmap | `purpose`: its goals are in no system that says what it is for (system delivery is described and holds stocks but no goal). |
| small-requests | no note; `explain` says `work` is nearly decomposable: its five subsystems share no link. |
| the-job | no note; **`explain` says `job` is several systems**: nearly decomposable, ten groups with one link between them in all (a ramp that broke, in safety, drives the outages noticed, in incidents), at modularity 0.88, each subsystem understood and redesigned alone. That is a good hierarchy, not a defect: the redesign should go one subsystem at a time. Inside them nothing splits, merges or crosses badly. |
| backups, coordinator, disk-space, file-queue, first-loop, git-hygiene, ops, plain-crontab, software-factory, talking-scripts, this-mac, ticket-factory | nothing. |

No example has a `time-scales` note: few have equations, and where they do (ticket-factory's intake: 5 s, 15 s,
60 s) the time constants spread without a tenfold gap. No example has `systems-merge` (the highest ratios: alert-
triage 0.71, ticket-factory's factory and oversight 0.6, software-factory's delivery and intake 0.6).

Before the thresholds were set, a plain modularity threshold of 0.3 flagged every pipeline (ticket-factory's
review, small-requests' regressions) as splitting at each stage: a pipeline's stages are linked by one flow each,
which modularity alone calls modules. Merging groups tied by more than a tenth of the smaller's links (a heuristic,
set on these examples) is what keeps the stages of one pipeline together and leaves the-job's subsystems apart.
The generated scale model (`scripts/scale_model.py 100`) gets `system-splits` on each of its systems: half its
workflows are plain parts in the system (no subsystem of their own), half come from the `steps` template; the
plain ones are named.
