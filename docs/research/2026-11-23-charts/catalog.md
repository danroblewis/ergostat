# ergostat chart catalog

Merged 2026-11-23 from four research reports: [`control-classical.md`](control-classical.md) (cited **CC**), [`control-modern.md`](control-modern.md) (**CM**), [`system-dynamics.md`](system-dynamics.md) (**SD**) and [`network-diagrams.md`](network-diagrams.md) (**ND**). A citation such as "CC F4" or "SD 10" points to that report's entry, which holds the claim, its evidence label and its references. "Exists" was checked against `origin/main` at `dc47a763`.

## 1. Summary: what to build first and why

**The decision.** Fix the two wrong numbers on screen today, build the *trust layer*, then the loop, flow and graph views that need no model, then the model charts. Do not start by adding chart types. Of the 88 charts kept, 42 are must-haves, and only 17 of those are entirely new. Most of the numerical work is already on main (identification, margins, Harris, oscillation, Kaplan-Meier, Theil, Loops That Matter, Monte Carlo, what-if, process map, critical path). It is stranded behind individual pages, in forms the new data sources cannot reach.

**Six findings drive the order.**

1. **The Process view reports concurrency as rework (confirmed on main).** `process()` in `ergostat/process.py` calls any line to an earlier step rework, without asking whether the item had been there. Two items doing `x, y` and `y, x` trigger it. On 100 jobs running three steps in random order, none repeated, it flagged 3 lines and 100 passages. The fix is B1 (§7.2).
2. **The frequency charts on main pass noise.** `plots-freq.js` ignores the server's coherence floor and uses a fixed 0.6. On unrelated noise with the default 4 segments, about 7% of frequencies passed it, and 98% of 1,024-sample records had a frequency above even the server's 95% floor (60 runs each). A per-frequency test cannot be the refusal `model-data-source` requires (G5, B2).
3. **Charts can be wrong in ways the reader cannot see.** Closed-loop regression returned -1/C, the inverse of the controller, instead of the plant (CC finding 2). A 60 s oscillation has amplitude zero in a 60 s `rate()` (CM fact 3). So every result carries a **verdict**: ok, warn or refuse, with a reason.
4. **Graphs mislead in their own ways.** Five routes through one step draw 25 paths, 20 of them invented (ND X1). Betweenness picks a station at 71% utilisation over the true bottleneck at 95% (ND X5). A shared driver produced 41 of 56 false Granger edges (ND X7). One added edge moved 88% of nodes under a recomputed layout (ND X10). So paths come from variants, bottlenecks from queueing measurements, and scrubbing from one fixed layout.
5. **The item data needs two corrections before it is built on.** `item-metrics-from-the-log` does not count arrivals (a move with no `from`, and Prometheus treats an empty label as absent) or items the index forgets when events are pruned (`Index._reconcile`), so reconciliation would report a false leak (§7.3). And a histogram observes a duration only when an item leaves, so it omits stuck work: "why isn't this done?" must use SQL with open items censored (SD 33, 35).
6. **The most direct answers were missing, and need one new shape.** The wait-for graph, variants and the impact graph answer the owner's named questions, largely from data already held (ND E11, C6, E10). "Two signals" folds into `series` and `graph` is added for eight named kinds, so the set stays at six shapes rather than nineteen (§2).

**Build first:**

| Order | Item | Why now |
|---:|---|---|
| 1 | `fix-process-rework-flag` | A wrong number people act on, shown today. Small, depends on nothing |
| 2 | `frequency-refuses-noise` | The same, for Bode and Nyquist |
| 3 | `result-frames-and-verdicts` | Every later chart needs it; 45 open charts depend on the verdict alone |
| 4 | `item-metrics-that-balance` | Cheap now, a data migration later |
| 5 | `analysis-source-and-window-guard` | The only route to spectra, alignment and correlation, which PromQL lacks |
| 6 | `graph-result-and-panel` | Lets the existing process, dependency and schedule graphs reach a panel, and every new graph view builds on it |

**Only B1 and B2 come before the trust layer.** Both correct a number already displayed, and neither needs the new frames.

**What this catalog deliberately does not do.** It adds no page, no visual query builder, no general graph explorer and no composite health score. It does not put Bode in front of operators as a default view, and it never draws Granger results as a network. It cuts 38 entries covering the reports' other charts (§3.3), including Lyapunov exponents, recurrence plots, Ziegler-Nichols, Sobol indices, Sankey, BPMN and generic centrality, because none would change a decision for someone running a software system.

**Six things need the owner** (§7.4): the default dashboard on SQLite; `rate()` semantics on VictoriaMetrics; the minimum record for an oscillation verdict; the meaning of "rework" in the SPEC; where runtime traffic for a service map comes from; and whether new diagram kinds proceed against the recorded "not planned" position.

---

## 2. Result shapes

### 2.1 The rule

A shape exists only if a chart needs a **contract no other shape can satisfy**. Anything else is a **role** on a field (this series is the setpoint), **metadata** in the envelope (simulated, with this verdict), a **computation** producing an existing shape (an ensemble summarised to bands), a **source's internal view** (item spans in SQL), or a **page diagram** with its own renderer (Dynamics, Blocks).

### 2.2 The six shapes

Every result is one frame: `{shape, fields, meta}`. Fields are typed columns, so a PromQL and a SQL result of the same shape draw the same chart.

#### `series`: values over a shared time axis

```
time:    [t0, t1, ...]                 ascending, regular or with explicit gaps (null)
series:  [{ key, labels, unit, values: [...],
            role?,                     sp | pv | op | mv | limit_hi | limit_lo | mode |
                                       input | output | open | high | low | close
            lower?, upper?,            a band, same length as values
            level? }]                  the band's probability, e.g. 0.9
x_kind:  "time" | "relative"           relative: seconds from an aligned event
```

Two signals is a `series` with roles `input` and `output`. A loop is a `series` with roles `sp`, `pv`, `op`, `mv` and limits. A fan is a `series` with bands.

#### `table`: dimensions to measures

```
dims:     [{ name, type: string|number|time, edges? }]    a row's dim values are unique
measures: [{ name, unit, lower?, upper? }]
rows:     [[dim..., measure...], ...]
```

A grid is a `table` with two dimensions, which may be sent as a dense matrix (an encoding, not a shape). Item spans returned by SQL are a `table` with `entered` and `left` time columns.

#### `points`: one row per observation, X and Y both numeric

```
x, y:   { name, unit, values: [...] }
order?: "time" | "x"                  present: the order is the content, and is drawn
t?:     [...]                         the time of each point, when ordered by time
lower?, upper?: [...]                 a band on y
step?:  bool                          a step curve (survival)
group?: [...]                         a series key per point
```

Ordered by `time` is a trajectory (phase portrait, hysteresis). Ordered by `x` with a band is an estimated curve (spectrum, correlogram).

#### `distribution`: how values are spread

```
form: "bins" | "samples" | "quartiles" | "survival"
bins:      { edges: [...], counts: [...] }
samples:   [...]                      bounded
quartiles: { min, q1, median, q3, max, n }
survival:  { t: [...], s: [...], lower: [...], upper: [...], at_risk: [...] }
over_time?: { time: [...], counts: [[...], ...] }   histogram buckets in each time step
censored:  n                          open items counted at their current age
competing?: { reason: n }             e.g. cancelled, never treated as censored
```

A Prometheus histogram (`_bucket` by `le`) arrives as `bins` with `over_time`.

#### `response`: how a system responds

```
system?:    { form: "fopdt"|"ipdt"|"rational", gain, tau, delay,
              poles: [[re, im], ...], zeros: [...], dt? }
frequency?: { hz: [...], re: [...], im: [...], magnitude_db: [...], phase_deg: [...],
              coherence?: [...], floor?, lower_db?, upper_db? }
path:       { input, output }
operating_point: { ... }
```

Bode and Nyquist require `frequency`; pole-zero requires `system`. A model supplies both; an estimate from data supplies `frequency` with `coherence`, and `provenance` says which. For a process with dead time, `poles` are those of the **discrete** model at the stated `dt`, since a continuous delay has no finite pole set.

#### `graph`: nodes and edges of a named diagram kind

```
kind:   process | conformance | dependency | wait_for | impact | service | sequence | lineage
nodes: {
  id:      [...]                 stable across windows and versions
  label:   [...]
  type?:   [...]                 service | state | item | external ...
  group?:  [...]                 a declared group: system, namespace, team
  parent?: [...]                 for collapse and drill-down
  fields:  [{ name, unit, role?, values }]
}                                role: rate | errors | latency | utilisation | wait | count
                                       | age | slack | exposure
edges: {
  id:       [...]                multi-edges allowed
  source, target: [...]          each must exist in nodes.id; checked by the server
  relation: [...]                calls | follows | blocks | owns | caused ...
  evidence: [...]                observed | declared | both | inferred | simulated
  n?, first_seen?, last_seen?: [...]
  t?:       [...]                required when time.mode = events
  confidence?: [...]             required when evidence = inferred
  fields:   [{ name, unit, role?, values }]
}
semantics: {
  paths_real: bool               required, no default: is a route through two edges evidence?
  acyclic:    bool | null        checked by the server
  focus?:     [node ids]
}
time: {
  mode:   snapshot | window | frames | events
  since, until, as_of?           as_of: the model version the structure is drawn from
  frames?: { t: [...], node_values: {field: [[...]]}, edge_values: {field: [[...]]} }
}
omitted: { nodes, edges, weight_share, how }     empty only if the graph is complete
diff?:   { against, nodes: [state...], edges: [state...] }   added | not_seen | changed | same
```

Each kind is a recognised diagram, and fixes how it is drawn and read. An unknown kind is refused.

| `kind` | Recognised as | Layout | `paths_real` | A cycle means |
|---|---|---|---|---|
| `process` | Process map (DFG) | Layered | false | A return or concurrency: test which |
| `conformance` | Conformance view | Layered | false | As `process` |
| `dependency` | Precedence network | Layered | true | A defect |
| `wait_for` | Wait-for graph | Layered | true | Deadlock if each resource has one unit; otherwise only possible |
| `impact` | Blast-radius graph | Radial by hop | from its source | Shared fate |
| `service` | Service map | Layered | false | Normal, flagged for cold start |
| `sequence` | Sequence diagram | Fixed axes | true | Not applicable |
| `lineage` | Lineage graph | Layered | true | A defect |

**Rules.**

- **Layout is never in the result.** The panel computes it with the ELK bundle already on every page, which needs no build step. A layout that may exceed about 200 ms runs in a Web Worker.
- **One layout per time session.** It is computed over the **union** of nodes and edges in the window and keyed on that set. Frames carry values only, absent edges are ghosted, and no node moves while scrubbing (ND X10).
- **Analysis runs on the full graph.** Reachability, impact and cycles are computed on the server before the result is cut for display, and `omitted` says what was cut.
- **Algorithms return existing shapes.** Cycles, cut sets and variants are a `table`; overlays are fields on `graph`.
- **Budgets** (ND §12.3): a panel draws 40 nodes and 100 edges, a page 60 and 160 for maps or 200 and 600 for dependencies. Over budget, collapse by declared group, then by role, then by weight into a visible "other"; offer the matrix (chart 77).
- **Aggregation stays honest.** An aggregated edge says how many it holds. Counts and rates may be summed; latency may not. One unhealthy member marks its group.
- **No graph query language, and no item ID as a label.** A graph comes from the `model` source, or from `graph()` in the `analysis` source over a PromQL or SQL result.
- **Dynamics and Blocks do not consume this shape**, and no `graph` is overlaid on them. They link to each other by selection.

### 2.3 The envelope, on every result

```
meta: {
  source, query,
  provenance: observed | derived | fitted | declared | simulated | hypothesis,
  verdict:    { level: ok | warn | refuse,
                reasons: [{ code, says, fix }] },
  sampling:   { scrape_s, step_s, range_windows_s: [...], observable_period_s: [lo, hi] },
  n, n_effective,
  model?:     { id, version, origin, fit, tests_passed, tests_not_run, validity },
  runs?:      { n, seed, paired, invalid, stopped },
  balance?:   { stock, status: holds | fails | unknown, residual }
}
```

A result with `verdict.level = refuse` holds no drawable data. The panel shows `says` and `fix`.

`provenance` is drawn on the chart: a simulated line is never styled like a measured one (SD infrastructure 5).

### 2.4 How each proposed shape was resolved

| Proposed | By | Resolution | Why |
|---|---|---|---|
| Time series | gap | **`series`** | |
| Dimensions to measures | gap | **`table`** | |
| Points | gap | **`points`** | |
| Distribution | gap | **`distribution`** | Gains `survival`, `censored` and `over_time` |
| Two signals | gap | `series` with roles `input`, `output` | A pair of aligned series; no chart needs more |
| Transfer function | gap | **`response`** (`system`) | Same charts as a frequency response |
| `LOOP` | CC | `series` with roles | A chart declares the roles it needs |
| `FREQUENCY RESPONSE` | CC | `response` (`frequency`) | Differs from a model's only in provenance and coherence |
| `FAMILY` | CC | A sweep, returned as `table` or `points` | Computation, not a contract |
| `GRAPH`, structure graph | CC, SD, ND | **`graph`**, for eight named kinds. Dynamics and Blocks stay page diagrams | See below |
| `CURVE±` | CM | Optional `lower`, `upper` on any numeric field | Uncertainty should be available everywhere |
| `GRID` | CM | `table` with two dimensions | Dense encoding on the wire |
| `TRAJ`, ordered points | CM, SD | `points` with `order: "time"` | One flag |
| `SS` | CM | Rejected | No must-have chart reads A, B, C, D. The model source computes from them and returns `table` or `response` |
| Ensemble | SD | Computation, summarised to `series` or `table` | Charts need bands, a bounded sample of runs, or a paired difference. Runs stay on the server |
| Item spans | SD | SQL view `item_spans`; returns `table` | Input to transforms, not a chart contract |

**Why `graph` is now a shape, and only narrowly.** The first version of this catalog rejected a graph shape. ND's challenge holds, for two reasons that meet the rule in §2.1:

1. **A table cannot state whether a path is real.** A precedence chain holds transitively, while a process-map or service-map route does not. The renderer has to know this to refuse a traced path.
2. **A cut graph must say what it cut.** Reachability on a truncated edge list is silently wrong, so completeness belongs in the contract, along with edge ends that must exist and isolated nodes that must survive.

The practical need is also real: `process.py`, `precedence.py` and `graph.py` return three incompatible graphs, and none can reach a panel.

ND's other arguments do not need a shape: edge meaning and stable identity could be columns. Three parts of its proposal are narrowed here. **`trace` is dropped** until a trace source exists, and a waterfall is a `table` of spans. **`state` folds into `process`**, which already reads by states, and into `conformance`. **The `intervals` time mode is dropped**, since the Gantt stays on the Timeline page and spans are a `table`.

The first version's concern stands for Dynamics and Blocks: each keeps its own renderer and notation, and neither reads this shape.

### 2.5 Which family takes which shape

This is the table `chart-result-shapes` requires to be tested. "roles" means the shape applies only when those roles are present.

| Family | `series` | `table` | `points` | `distribution` | `response` | `graph` |
|---|---|---|---|---|---|---|
| line | yes | numeric dim | yes | no | no | no |
| bar | yes | yes | no | `bins` | no | no |
| stat | yes | one row | no | no | no | no |
| table | yes | yes | yes | yes | no | nodes or edges |
| scatter | roles `input`, `output` | two measures | yes | no | no | no |
| phase | roles `input`, `output` | no | `order: time` | no | no | no |
| histogram | yes (values) | no | no | `bins`, `samples` | no | no |
| box | no | no | no | `samples`, `quartiles` | no | no |
| heatmap | no | two dims | yes (counts) | `over_time` | no | as a matrix |
| candlestick | roles `open`, `high`, `low`, `close` | no | no | no | no | no |
| bode | no | no | no | no | `frequency` | no |
| nyquist | no | no | no | no | `frequency` | no |
| pole-zero | no | no | no | no | `system` | no |
| survival (new option of line) | no | no | no | `survival` | no | no |
| Marey, dotted (new options of scatter) | no | no | `order: time`, `group` | no | no | no |
| graph (new, draws its named `kind`) | no | no | no | no | no | yes |

Reshape messages are one sentence and name the fix, for example: "A phase portrait needs two signals in time: add a second query and mark one as input."

### 2.6 Four data source types

The owner's model (a connection, a text language, a typed result) holds for all four. None has a visual builder.

| Type | Language | Returns | Gap |
|---|---|---|---|
| `prometheus` | PromQL | `series`, `table`, `distribution` | `data-source-model`, `metrics-store-with-labels` |
| `sql` | SELECT over stable views | `table`, `points`, `series` | `sql-source-over-item-views` |
| `model` | Small call syntax: `bode(goal="x")`, `fan(stock="y", h=8h)`, `waits(kind="ticket")`, `impact(of="service.auth", hops=3)` | `response`, `series`, `table`, `graph` | `model-data-source` |
| `analysis` | Small call syntax over a panel's other queries | any | New (B5) |

The `analysis` source is how named transforms stay text-only and pluggable, in the way Grafana's server-side expressions work:

```
A  prometheus   sum(ergostat_items{kind="$kind",state="review"})
B  analysis     psd(A, detrend="linear")
```

`chart-result-shapes` allows client-side transforms "only where a query language cannot do it". Keep that for **reshaping** (pivot, join by field, group). Analysis runs on the server because it must re-read the signal at raw resolution (guardrail G1), is bounded, and must be tested once.

---

## 3. The catalog

### 3.1 Legend

**Status.** *exists*: drawn today, in the place named or as a dashboard form. *needs work*: an engine or a chart on another page exists, but it is not available as a typed panel, or lacks its guard. *new*: nothing usable on main.

**Priority.** *must*: a core question cannot be answered well without it. *useful*: changes a decision in a narrower case, or needs a trustworthy model first. *niche*: not scheduled; build only when someone asks.

**Needs** (infrastructure, §4): **VD** verdict, **MD** model source, **AN** analysis source, **SG** signal access and window guard, **RL** loop roles, **SP** item spans, **EV** event marks, **EN** paired ensembles, **LG** conservation ledger, **XP** experiment path, **GH** goal history, **GR** graph shape and form, **AG** graph aggregation and budgets, **FL** fixed layout over time.

### 3.2 The table

| ID | Chart | Discipline | Question it answers | Shape | How to get the data | Status | Priority | Needs | Source |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | Loop trend (scope) | Control | What did the loop try to do, and what happened? | `series` (sp, pv, op, mv) | PromQL | needs work: `loopScope` on the loop panel, no role-bound panel | must | RL, SG, VD | CC A1 |
| 2 | Behavior over time, with event marks | SD | Which pattern is this, and what happened when it changed? | `series` | PromQL + event marks | needs work: line exists, panels have no marks | must | EV | SD 8 |
| 3 | Stock-flow reconciliation | SD | Does the stock equal its inflows minus outflows? If not, what leaks? | `series` | PromQL + `reconcile`; SQL for exact | needs work: one-step residuals in `numbers/residuals.py`, no chart | must | AN, LG, SG, VD | SD 10 |
| 4 | Little's law check (exact and naive) | Flow | Do WIP, rate and time agree? | `table` | SQL (exact); PromQL (naive form only) | new | must | SP, LG, VD | SD 32, CM 50 |
| 5 | Goal gap and tracking error, with goal history | SD + Control | Is the gap closing, or did the goal move? | `series` | PromQL + `gap` | needs work: goal drawn today, its history is not | must | RL, GH, VD | SD 11, CC A6 |
| 6 | Saturation and windup timeline | Control | Could the controller act at all? | `series`, `table` | PromQL | needs work: `monitor.saturation` gives a share | must | RL, VD | CC F4, CM 33 |
| 7 | Control effort and churn | Control | Is the actuator worked hard for no gain? | `series`, `table` | PromQL | new | must | RL, SG | CC A7 |
| 8 | Commanded vs actual (OP-MV) | Control | Is the actuator doing what it was told? | `points` (ordered) | PromQL | needs work: phase form draws it, no verdict | must | RL, VD | CC F2, CM 29 |
| 9 | Oscillation verdict | Control | Is it oscillating, at what period: self-sustained, forced, or noise? | `table`, `series` | PromQL + `oscillation` | needs work: `monitor.oscillation` has period and regularity, no driver check | must | AN, SG, EV, VD | CC F3, CM 22 |
| 10 | Power spectrum and spectrogram | Control | What periods are present, and since when? | `points`, `table` | PromQL + `psd`, `spectrogram` | new (Welch code exists in `query/frequency.py`) | must | AN, SG, VD | CC B9, CM 15 |
| 11 | Event-aligned response | Control + Ident | What typically follows this kind of event? | `series` (relative time, band) | PromQL + events + `align` | new | must | AN, EV, SG, VD | CM 46, CC A5, A4 |
| 12 | Step response (test or model) | Control | How fast and cleanly does it respond? | `series` | Model; active experiment | needs work: `stepChart`, `control/steptest.py`, not a panel | must | MD, XP, VD | CC A2, D1, CM 16 |
| 13 | Operating curve (load vs latency) | Flow + Control | How near the knee are we, and does one tuning hold? | `points` | PromQL + `settled_bins` | new | must | AN, SG, VD | CC G2, CM 48, SD 38 |
| 14 | Phase portrait | Control + SD | Does it spiral in, cycle, or settle somewhere bad? | `points` (ordered) | PromQL (two queries, paired) | exists | must | VD | CC G3, CM 18, SD 12 |
| 15 | Offered load vs goodput | Flow | Does throughput collapse, and recover when load falls? | `points` (ordered) | PromQL + `pair` | needs work: needs first-attempt and retry series, and the refusal | must | AN, EV, VD | CM 52, CC G3 |
| 16 | Latency heatmap | Flow | What do percentiles hide: modes, bands, a tail? | `distribution` (over time) | PromQL (`_bucket` by `le`) | needs work: heatmap bins points, does not read `le` | must | VD | CM 53 |
| 17 | Cumulative flow / N-curves | Flow + SD | Which stage is piling up? | `series` | PromQL on transitions; SQL for exact | needs work: `flowChart` on Items, not a panel | must | LG | SD 31, CM 51 |
| 18 | Aging WIP | Flow | Which open items are at risk now? | `points` | SQL + `survival` | new | must | SP, VD | SD 33 |
| 19 | Survival curve of work items | Flow | How long do items last, counting those still open? | `distribution` (survival) | SQL + `survival` | needs work: `numbers/survival.py`, no chart | must | SP, AN, VD | SD 35 |
| 20 | Delay profile | SD | How long is this delay, what shape, material or information? | `distribution` | SQL (material); PromQL + `ccf` (information) | new | must | SP, AN, VD | SD 29 |
| 21 | Delay budget around a loop | Control | Which part of the loop's delay can be removed? | `table` (bar, and labels on Blocks edges) | Model structure + config + PromQL | new | must | RL, SG, MD | CC G5 |
| 22 | Fleet loop scorecard | Control | Of all loops, which deserve attention now? | `table` | PromQL + transforms, cached | needs work: `monitor.performance` per loop | must | RL, AN, LG, VD | CC F6 |
| 23 | Stock-and-flow diagram | SD | Where does work accumulate and what moves it? | page diagram | Model structure | exists (Dynamics) | must | none | SD 2 |
| 24 | Block diagram | Control | What is measured, decided and moved? | page diagram | Model structure | exists (Blocks) | must | none | CC E1 |
| 25 | Data adequacy card | Ident | Can this record support a model at all? | `table` | PromQL + `adequacy` | needs work: `numbers/identify.py`, `ident.judge` | must | AN, MD, VD | CM 9 |
| 26 | Model vs held-out data, with Theil and residuals | Ident + SD | Does it reproduce data it never saw, and what kind of error remains? | `series`, `points` | Simulation + PromQL | needs work: Theil and `judge` exist, not a panel | must | MD, VD | CM 10, 11, SD 24, 25, 28 |
| 27 | Model test scorecard | SD | What has this model been tested for, and what has not? | `table` | Model structure + simulation | needs work: `numbers/extremes.py` and checks, no scorecard | must | MD | SD 26, 27 |
| 28 | Model-residual change chart | SPC | Did the system depart from its expected dynamics? | `series` | PromQL + `residual_chart` | new | must | AN, EV, VD | CM 39-41, 45, SD 36 |
| 29 | Policy comparison (paired difference) | SD | Does this change beat doing nothing, by how much, when? | `series` (difference, band) | Simulation | needs work: what-if is drawn, no paired difference | must | EN, MD, VD | SD 19 |
| 30 | Monte Carlo fan | SD | Given what we do not know, what range is plausible? | `series` (bands) | Simulation | needs work: `numbers/sensitivity.py` fan on Dynamics, not a panel | must | EN, MD | SD 18 |
| 66 | Process map (directly-follows graph) | Process mining | What steps does work go through, and where does time go? | `graph` (process) | Model source over `process.py` | needs work: Process view exists, its rework flag is wrong (B1) | must | GR, AG, VD | ND C1 |
| 67 | Wait-for graph | Operating systems | What is everything waiting on right now, and is any of it circular? | `graph` (wait_for) | Model: `waits()` over relations, leases, states | new | must | GR, MD, VD | ND E11, J3 |
| 68 | Variant explorer | Process mining | What complete paths does work really take, and which are slow? | `table` | SQL over moves | new | must | SP, VD | ND C6 |
| 69 | Conformance (declared vs observed) | Process mining | Where does work leave the declared path, and at what cost? | `graph` (conformance) | Model structure + SQL over moves | new | must | GR, SP, MD, VD | ND C4, B1 |
| 70 | Bottleneck overlay | Queueing | Which resource limits throughput, and what would more of it gain? | `graph` fields, `points` (bounds) | SQL over spans and leases; PromQL for services | new | must | GR, SP, AN, VD | ND D2 |
| 71 | Impact graph (blast radius) | SRE | What could break or slip if this fails? | `graph` (impact) | Model: `impact()` over relations or the service map | new | must | GR, MD, AG, VD | ND E10, E8 |
| 72 | Service map | SRE | What talks to what, and which link is unhealthy now? | `graph` (service) | PromQL (caller and callee labels) + `graph()` | new; needs a traffic source | must | GR, AG, FL, VD | ND F1 |
| 73 | Sequence diagram | Software | In what order did this item's events happen, and who waited on whom? | `graph` (sequence) | Event log, following `causedby`, bounded | new | must | GR, VD | ND A12, A13, A14 |
| 74 | Dependency graph | Scheduling | What must finish before what? | `graph` (dependency) | Item relations | exists (Items Graph) | must | GR | ND E1 |
| 75 | Critical path, with the levelled end | Scheduling | Which chain sets the finish date? | `graph` fields | `precedence.py` | exists (Items Graph) | must | GR | ND E3 |
| 76 | Gantt with dependencies | Scheduling | What happened, what is running, what is projected? | page diagram | `precedence.py` | exists (Timeline) | must | none | ND E5 |
| 77 | Adjacency matrix / DSM | Graph + Systems eng. | Who connects to whom when a node-link drawing is unreadable? | `graph`, drawn by heatmap | Any `graph` result | new | must | GR, AG | ND E7, E6 |
| 31 | Bode plot | Control | At which time scales does feedback work? | `response` | Model (default); PromQL + `response` | needs work: default to model, coherence gate (G5) | useful | MD, VD | CC B1 |
| 32 | Sensitivity S and T (with PS, CS) | Control | Where does this loop amplify disturbances? | `response` | Model | needs work: `lti.margins` gives Ms only | useful | MD | CC B4, B5 |
| 33 | Gain and margin across load | Control | Is the loop still safe at the coming peak? | `points`, `table` | Model + PromQL + `settled_bins` | needs work: `lti.margins`, `lti.robust` at one point | useful | MD, AN | CC B7, CM 31 |
| 34 | Pole-zero map with mode table | Control | Is the fitted model stable, slow or over-fitted? | `response` | Model | needs work: form exists, needs z-plane from the model | useful | MD | CC C2, CM 1 |
| 35 | Empirical frequency response and coherence | Ident | Can a response be measured here, and at which frequencies? | `response` | PromQL + `response` | needs work: `query/frequency.py`, fix the gate | useful | VD | CC B8, CM 14 |
| 36 | Cross-correlogram | Ident | How long after A moves does B move? | `points` (band) | PromQL + `ccf` | new | useful | AN, SG, VD | CC G1, CM 13 |
| 37 | Harris index | Control | Could better feedback reduce variance, given the delay? | `table` | PromQL + `harris` | needs work: `monitor.harris` on the loop panel | useful | RL, AN, VD | CC F1, CM 36 |
| 38 | Shared oscillation map | Control | Which signals share one oscillation? | `table` (signal by frequency) | PromQL + `psd`, batch | new | useful | AN, SG, VD | CC F7, CM 37 |
| 39 | Cascade view | Control | Are nested loops separated enough in speed? | `series` | PromQL + model structure | new | useful | RL, MD | CC E3 |
| 40 | Tuning map | Control | Across the knobs I have, where is it stable and robust? | `table` (two parameters) | Simulation sweep | new | useful | EN, MD, VD | CC D4 |
| 41 | Rate balance and tipping | SD | Where do inflow and outflow balance, and where is the point of no return? | `points` | Simulation; PromQL + transform if overload was seen | new | useful | MD, EN, VD | SD 13, CM 19, 20 |
| 42 | Causal loop diagram (derived) | SD | What feedback could produce this? | page diagram | Model structure | new | useful | MD | SD 1 |
| 43 | Loop dominance (LTM) | SD | Which loop drives the model now? | `series` | Simulation + model structure | needs work: `loopDominance` on Dynamics, needs fit gate | useful | MD, VD | SD 15 |
| 44 | Causes strip and loop list | SD | What drives this variable, and which loops is it in? | page diagram | Model structure | exists (Dynamics side panel) | useful | none | SD 6 |
| 45 | Model boundary table | SD | What does the model explain, take as given, ignore? | `table` | Model structure | new | useful | MD | SD 5 |
| 46 | Graphical function with observed points | SD | What curve is assumed, and does data cover it? | `points` | Model structure + PromQL | new | useful | MD | SD 7 |
| 47 | Reference mode | SD | What behavior are we explaining, stated before the fit? | `series` | PromQL + declared path | new | useful | GH | SD 9 |
| 48 | Tornado and statistical screening | SD | Which assumption moves this outcome, and when? | `table`, `series` | Simulation | new | useful | EN, MD | SD 20, 22 |
| 49 | Parameter identifiability profile | SD + Ident | Does the data determine this parameter? | `points` | Simulation | new | useful | MD, EN | SD 23 |
| 50 | Cycle-time scatter, open items shown | Flow | Is predictability changing? Are there clusters? | `points` | SQL | needs work: `cycleChart` omits open items | useful | SP | SD 34 |
| 51 | Throughput forecast | Flow | When will these finish? | `distribution` | SQL + `numbers/eta.py` | needs work: estimates exist, no chart | useful | SP, VD | SD 37 |
| 52 | Age bands over time | SD + Flow | Is old work being starved behind new? | `series` | SQL | new | useful | SP | SD 30 |
| 53 | Rework chart | SD | How much apparent progress will come back? | `series` | SQL; simulation for the hidden stock | new | useful | SP, MD | SD 40 |
| 54 | Counterfactual impact | SPC | What would have happened without the change? | `series` (band) | PromQL + `impact`, declared controls | new | useful | AN, EV, VD | CM 47 |
| 55 | Experiment planner | Ident | What is the smallest safe test that answers this? | `series`, `points` | Active experiment | needs work: step tests run, no planner | useful | XP, MD | CM 17, CC G6 |
| 56 | Can this knob move this stock? | Control | Is the actuator connected to the state at all? | `table` | Model structure | new | useful | MD | CM 2, 4, ND H4 |
| 64 | Flow efficiency by step | Flow | How much of lead time is work, and how much is waiting? | `table` (bar) | SQL over spans and leases | new | useful | SP | SD 39, ND D6 |
| 78 | Graph diff | SRE | What changed in the structure between two times? | `graph` with `diff` | Two windows of any graph source | new | useful | GR, FL, VD | ND J7 |
| 79 | Expected visits and completion share | Process mining | How many attempts per item, and what share finishes? | `table` | SQL over moves | new | useful | SP, VD | ND B3, B4 |
| 80 | Marey and dotted charts | Flow | Who overtakes, stalls or lands in batches? | `points` (ordered, grouped) | SQL over `item_spans` | new | useful | SP | ND C8, C5 |
| 81 | Dominators and articulation points | Graph | Which single node does every path pass through? | `table`, overlay on `graph` | Model over the dependency or service graph | new | useful | GR, MD, VD | ND E12 |
| 82 | Time-respecting path check | Graph | Could this failure really have spread this way, given when edges were active? | `table`, overlay on `graph` | Event log; windowed PromQL | new | useful | GR, EV, VD | ND J8 |
| 83 | Workflow soundness check | Process mining | From every state, can an item still finish? | `table` | Model structure, in `ergostat check` | new | useful | MD | ND A1, A2, A5 |
| 84 | Unsafe control actions (STPA) | Safety | Which control action could lead to a loss? | `table` | Model structure + declared hazards | new | useful | MD | ND G11 |
| 85 | Lineage of a number | Data | Where did this number come from, and what depends on it? | `graph` (lineage) | Panel query, series, sensor, goal | new | useful | GR, MD | ND F7 |
| 86 | Trace or run waterfall | SRE | Where did this one execution spend its time? | `table` (spans) | Trace source; `causedby` for own runs | new; needs a trace source for requests | useful | SP | ND F3 |
| 87 | Fan-out and join waits across kinds | Process mining | Where does a parent wait on the last of its children? | `graph` (process), `table` | Process view's `caused` lines + spans | needs work: lines drawn, join wait not measured | useful | GR, SP | ND C7 |
| 88 | Queueing network prediction | Queueing | What would this capacity change do, including the next bottleneck? | `table`, fields on `graph` | Routing from moves; simulation or MVA | new | useful | GR, MD, VD | ND D1 |
| 89 | Ownership and concentration | Organisation | What has no owner, or only one who can act? | `table` | Declared systems and machines | new | useful | MD | ND I4 |
| 57 | Nyquist plot | Control | Stability when Bode margins are ambiguous | `response` | Model | exists | niche | MD | CC B2 |
| 58 | Root locus | Control | How do poles move with one gain? | `table` | Model | new | niche | MD | CC C1 |
| 59 | Relative gain array | Control | Will these loops fight? | `table` | Active experiment | needs work: `control/rga.py`, text only | niche | XP | CC E5, CM 6 |
| 61 | Idle index `[unsure]` | Control | Is the loop too slow? | `table` | PromQL + transform | new | niche | AN, RL | CC F5 |
| 62 | Ranked lead-lag hypotheses (a list, never a network) | Ident | Which signal should I look at first? | `table` | PromQL + transform | new | niche | AN, VD | CM 44, ND G12 |
| 90 | Fault tree cut sets | Reliability | What combinations of failures cause this outage? | `table` | Hand-declared, seeded by chart 81 | new | niche | MD | ND G4 |
| 91 | Kubernetes resource graph | SRE | Where did this rollout stall? | `graph` | Kubernetes API, read-only | new; needs that source | niche | GR | ND F9 |

Generic forms already on main (bar, stat, table, scatter, histogram, box, candlestick) stay as they are and are covered by §2.5. Candlestick gets no further investment. **Useful and niche charts not named in a build item (§7.1) are deliberately unscheduled:** each waits until someone needs its answer, on the infrastructure listed.

### 3.3 Cut

These appear in the reports and are **not** in the catalog. If someone asks, the answer is the reason below.

| Chart | Report rating | Why cut |
|---|---|---|
| Nichols chart (CC B3) | niche | No operations decision is better served by it than by S and margins |
| Loop shaping view (CC B6) | niche | Software controllers have few knobs; use the tuning map |
| Signal-flow graph (CC E2, ND H2) | niche | **Reconsidered, stays cut.** ND agrees: keep the algebra, since a second notation beside Blocks states the same fact |
| Ziegler-Nichols (CC D2) | niche | Unsafe as a procedure. Ms 2.43-4.07 against 1.59 for SIMC. Answered by guardrail G10 |
| Relay autotuning (CC D3) | niche | Deliberately perturbs live traffic; a step test is safer |
| Describing function (CC G4, CM 23) | niche | Simulation of the real discrete controller is simpler and more accurate |
| Impulse response as a chart (CC A3) | niche | By-product of chart 12 |
| Feedforward view (CC E4) | useful | Answer "would acting early help?" with a policy comparison (chart 29) |
| Actuator staircase test (CC G6) | useful | Compute deadband from declared config; chart 55 covers the rare test |
| Hankel singular values (CM 3) | niche | Models are small, and balanced states destroy named stocks |
| Singular value and directionality plots (CM 5, 8) | niche | Need a validated MIMO model nobody will have |
| Model order curve (CM 12) | useful | Run automatically; report the chosen order in the fit |
| Lyapunov function and exponent (CM 24, 25) | niche | "Is it chaotic?" changes no decision; algorithms return a number for noise |
| Recurrence plot (CM 26) | niche | Striking pictures, few decisions |
| Delay embedding (CM 27) | niche | Coloured noise produces convincing shapes |
| Poincaré section (CM 21) | niche | Too few clean cycles before someone intervenes |
| Surrogate test as a chart (CM 28) | useful | Kept as a check inside `oscillation`, not shown |
| Early-warning indicators (CM 30) | niche | Reported false-alarm fractions of 0% to 93%. Do not alert on this |
| MPC horizon view (CM 32) | useful | No predictive controller exists to chart |
| Adaptive parameter trace (CM 35) | useful | ergostat does not self-tune. Revisit if it ever does |
| Shewhart, standalone CUSUM and EWMA (CM 38-40) | niche, useful | Delivered through chart 28, on residuals |
| T² and SPE monitoring (CM 43) | niche | Poor fit with churning label sets; contributions smear |
| Variance-time and AIMD plots (CM 54, 55) | niche | Specialist; a load test or fairness index answers it |
| Pathway participation, eigenvalue elasticity (SD 16, 17) | niche | LTM answers the question for discrete models |
| Morris and Sobol (SD 21) | niche | Tornado plus screening answers real questions |
| Sankey and alluvial (SD 41, ND D4, D5) | niche | **Reconsidered, stays cut.** A Sankey of a process map **invents routes** (ND X1). Its one honest use, the outcomes of work arriving in a window, is a stacked bar |
| Flight simulator (SD 42) | niche | A product of its own |
| Step-response matrix, fault signature matrix, Kalman innovations (CM 7, 34, 42) | useful | Need a designed test per input, a declared fault model, or a charted estimator; none exists. The observer is opt-in. Revisit if one does |
| BPMN, UML activity, GRAFCET, process algebra, DEVS, activity cycle (ND A6, A8-A11, A15) | niche, don't build | A statement of intent or a specialist notation. Item kinds are already the declaration |
| Coloured, timed and stochastic Petri nets; statecharts, HMM, MDP, hybrid automata (ND A3, A4, B2, B5-B7) | niche | Need a modelling specialist, or data that seldom exists. The soundness check (chart 83) keeps the useful part |
| Heuristic and fuzzy miners, inductive miner as a view (ND C2, C3) | niche, useful | Variants and the filter cover this at ergostat's scale. Keep only concurrency detection |
| Max-flow, PERT, critical chain, topological layers, commit graph, kanban map, geographic map (ND D3, D7, D8, E2, E4, E9, E13) | niche | Need capacities or estimates nobody holds, or another tool already draws them |
| Static call graph, flame graph, trace graph, network topology, C4 (ND F2, F4, F5, F6, F8) | niche, don't build | Owned by IDEs, profilers, trace backends and network tools. Link out |
| Bayesian network, influence diagram, event tree, attack tree, RBD, FMEA, bow-tie, Ishikawa (ND G2, G3, G5-G10) | niche, don't build | Parameters are seldom defensible, or the diagram holds opinion rather than evidence. An RBD would also be mistaken for Blocks |
| Bond graph, P&ID, consensus view (ND H1, H3, H5) | niche, don't build | Their central invariants have no counterpart in software queues |
| RACI, communication network, Conway view, stakeholder map (ND I1, I2, I3, I5) | niche, don't build | A table suffices, or the view invites ranking people |
| Generic centrality, k-core, motifs, edge bundling, community detection as a finding (ND J1, J2, J4-J6) | niche, don't build | **Betweenness picks the wrong bottleneck** (G37). Fan-in and fan-out stay, by name |
| Force, orthogonal, arc, chord, hive, sunburst, treemap (ND K1, K3, K5-K7, K9, K10) | niche, don't build | Layered, radial and the matrix cover ergostat's graphs. A sorted table shows composition |

Merged rather than cut: swimlanes (ND A14) are a group-by on charts 73 and 76; the state diagram (ND B1) is the declared half of chart 69; the causal DAG (ND G1) is the stated assumption behind chart 54's controls; cycles and SCCs (ND J3) are overlays on charts 67 and 74; the radial layout (ND K4) is how chart 71 draws; concurrency detection (ND C3) is a transform; subsystem and policy-structure diagrams (SD 3, 4) are the existing Dynamics and Blocks views; archetypes (SD 14) are worded candidates on a loop, never a chart; USL (CM 49) is a fit option on chart 13, for load tests only; the stock-and-flow dashboard (SD 43) is the Dashboard.

### 3.4 Where the reports disagreed

Rows from ND name its rating in the Why column.

| Chart | CC | CM | SD | Decision | Why |
|---|---|---|---|---|---|
| Operating curve | must | must | useful | **must** | The only check on whether any linear chart is valid at the current load |
| Phase portrait | must | must | useful | **must** | Already built. The only view of metastability and hunting from two ordinary series |
| Commanded vs actual | must | useful | | **must** | Software, unlike process plants, usually records the actuator, so the test is nearly free |
| Reconciliation | | (Little only) | must, rank 1 | **must, and gates** | Cheap, and every stock chart depends on it |
| Residual diagnostics | | must | useful | **must, not a gate for SD models** | Merged into chart 26. SD models are not expected to fit noise (SD 25); identified control models are |
| Cross-correlogram | must | useful | | **useful** | Closed-loop and seasonal data make it the commonest false finding (52% in CM 13). Event alignment gives delay with less risk |
| Sensitivity S and T | must | | | **useful** | Needs a validated model. Ms already gates tuning proposals on main; the curve explains a retune rather than triggering one |
| Margin vs load | must | useful | | **useful** | Needs a local model at several loads, which passive data rarely gives. Chart 13 shows the gain change without a model |
| Tuning map | must | | | **useful** | Most loops have one or two knobs, and a paired comparison of current vs proposed answers the decision |
| Cascade view | must | | | **useful** | Only when nested loops are modelled |
| Delay budget | must | | | **must, as a bar** | CC calls it a composite it proposes, not a named chart. The owner allows recognised diagrams only, so it is an ordinary bar plus labels on Blocks edges |
| Causal loop diagram | | | must | **useful** | Loops are already listed beside the stock-and-flow view, and a CLD hides accumulation. Worth deriving later, never hand-drawn |
| Loop dominance | | | must | **useful** | It describes the model, is undefined at equilibrium, and only counts once the fit passes. Already built, so this costs nothing |
| RGA | niche | useful | | **niche** | Needs a designed test per input. A shared oscillation (chart 38) finds fighting loops with no experiment |
| Root locus | useful | | | **niche** | A critical-gain number covers most uses; no engine on main |
| Bode | useful | | | **useful, model only** | Owner's decision. CC calls this its most disputable call; the owner settled it |
| Nyquist | niche | | | **niche, kept** | Already built. Its answer is better read as a margin |
| Step and impulse estimate | must (step), niche (impulse) | must | | **must, one chart** | Impulse is a by-product |
| Process behavior chart | | niche as Shewhart | useful | **inside chart 28** | Raw XmR on autocorrelated telemetry false-alarms. Allowed for low-rate counts (weekly) after an autocorrelation check |
| Little's law on a window | | needs small end backlog | exact identity | **SD is right** | Holds exactly over a finite window when W counts time inside it (Little 2011). CM's form uses completed durations, which is the naive form. Show both |
| Service map | | | | **must, once a source exists** | ND must. Nothing on main draws runtime traffic, but it needs caller and callee labels (§7.4 item 5) |
| Graph diff | | | | **useful** | ND must. It pays only once a graph has a baseline worth comparing; event marks answer "what changed?" first |
| Cycles and SCCs | | | | **overlay, not a chart** | ND must. Required by the wait-for and dependency views, and meaningless alone |
| Adjacency matrix / DSM | | | | **must, one chart** | ND rates the matrix must and DSM useful. A DSM is the matrix with a stated ordering |
| Value stream map | | | | **useful, as a bar** | SD useful, ND useful as a strip, first catalog niche. The flow-efficiency number decides; the factory icons do not |
| Fault tree | | | | **niche** | ND useful. It must be hand-authored, and chart 81 finds single points of failure for free |
| Treemap | | | | **cut** | ND useful. A sorted table answers the same question |
| Causal map | | useful | | **a ranked list, niche** | ND niche, "never a picture". With no true link, 96% of runs still produced a false edge (ND X7) |

---

## 4. Shared infrastructure

Ordered by how many open charts (not yet "exists") each piece unlocks, counted from the table in §3.2. The base gaps (`data-source-model`, `chart-result-shapes`) underlie everything and are not counted.

| Order | Piece | Charts (must) | What it is | State on main |
|---:|---|---|---|---|
| 1 | **VD: Verdicts** | 45 (29) | The envelope of §2.3. Closed list of reason codes, each with a sentence and a fix. "Cannot say" is a normal result | Scattered: `frequency.Refused`, `identify` holds, `ident.judge` |
| 2 | **MD: Model source** | 34 (10) | One source over the existing control, numbers and precedence code. Every answer carries version, origin, fit and validity | Engines exist; `query/shaped.py` has a first path to a goal's process |
| 3 | **AN: Analysis source** | 19 (12) | Named, tested transforms (list below) | `transforms.py` has only rate, delta, cumulative and moving average |
| 4 | **SP: Item spans** | 16 (7) | SQL view: one row per item per state, `entered`, `left` (null if open), re-entry number, terminal reason | `moves` in the item index holds the data |
| 5 | **GR: Graph shape and form** | 15 (8) | The `graph` result, named kinds, the panel form, ELK in a worker, the three producers adapted | Three incompatible graphs; ELK bundled, on the main thread |
| 6 | **SG: Signal access and window guard** | 10 (8) | Re-reads at raw resolution on one grid, with a gap mask. Records scrape, step and every range window. Computes the observable period band | Gap handling exists in `frequency.py`; no window ledger |
| 7 | **RL: Loop roles** | 10 (7) | Binds a goal's setpoint, measurement, controller output, actuator, limits and mode to series. Inferred bindings are labelled hypotheses | The goal and its block already know these; not exposed to panels |
| 8 | **EV: Event marks** | 7 (5) | Deployments, config and goal changes, incidents and experiments as marks on any time axis, each **scheduled or reactive** | None on panels |
| 9 | **EN: Paired ensembles** | 6 (2) | Per-draw results, so a difference between two policies has an honest band | `closedloop.risk` shares a seed but returns only marginal bands |
| 10 | **LG: Conservation ledger** | 4 (4) | For each stock: its flows, residual, tolerance and method. Dependent charts read its status and lower their confidence | None |
| 11 | **AG: Graph aggregation and budgets** | 4 (4) | Collapse by declared group, then role, then weight, with an honest `omitted`; semantic zoom | `process.py` caps nodes and edges and says so |
| 12 | **XP: Experiment path** | 3 (1) | Gated actions with limits, abort and rollback | Built: `steptest`, owner approval |
| 13 | **GH: Goal history** | 2 (1) | Versioned goals and reference modes with author and time | Model versions exist; no goal series |
| 14 | **FL: Fixed layout over time** | 2 (1) | One layout over the union of a window, frames of values, ghosted absent edges | None |

**Named transforms, by how many charts use them.** Each is tested once on a hand-worked record and reuses existing code where it can.

| Transform | Used by charts | Reuses |
|---|---|---|
| `pair` (join two signals on one grid) | 8, 13, 14, 15, 33, 46 | `query/shaped.py` |
| `align` (event-aligned windows, median and band, placebo) | 11, 12, 28, 54 | `control/experiments.py` windows |
| `psd`, `spectrogram` | 9, 10, 38 | `query/frequency.py` |
| `survival` (Kaplan-Meier, competing risks) | 18, 19, 20, 51 | `numbers/survival.py` |
| `settled_bins` (keep settled segments, bin by load, n per bin) | 13, 33 | `control/loop.steady` |
| `oscillation` (period, regularity, envelope, driver check) | 9, 22 | `control/monitor.py` |
| `ccf` (prewhitened, with band) | 20, 36 | `control/ident.acf` |
| `reconcile`, `little` | 3, 4, 17, 22 | `numbers/residuals.py` for model stocks |
| `residual_chart` (EWMA or CUSUM on residuals, achieved false-alarm rate) | 28 | New |
| `adequacy` | 25 | `numbers/identify.py` |
| `harris` | 22, 37 | `control/monitor.py` |
| `impact` | 54 | New |
| `graph` (a `table` to a `graph` of a named kind) | 72, 77, 78 | New |
| `variants` (ordered paths, count, duration, outcome) | 68, 69, 79 | `process.Window` steps |
| `concurrent` (both orders common, neither depends on the other) `[unsure: a heuristic]` | 66, 68, 69 | New |
| `waits`, `reach` (full graph, then cut) | 67, 71, 81, 82 | `precedence.py`, item relations |

---

## 5. Analytical workflows

Each step says what would stop or redirect you. A workflow on a stock begins with chart 3, and a failed balance lowers confidence on everything after it. Numbers are chart IDs from §3.2.

### 5.1 Is this loop healthy?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 22 Scorecard | Which loop? | Pick the worst by impact, not by a blended score |
| 2 | 1 Loop trend | Is the signal complete? | Missing role: **not assessable**, name the instrument to add |
| 3 | 6 Saturation | At a limit? | **Capacity problem.** Stop: tuning advice is suppressed (G7) |
| 4 | 9 Oscillation | Cycling? | Go to 5.2 |
| 5 | 5 Goal gap | Persistent bias, or did the goal move? | Bias: integral action or capacity. Moved: goal erosion |
| 6 | 7 Effort | High churn for little error removed? | **Over-tuned**, or noise is driving the actuator |

**Output:** healthy, capacity problem, dynamics problem, or not assessable, with the evidence for each flag.

### 5.2 Why is it oscillating?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 10 Spectrum | Real, and observable at this scrape and window? | Period inside a `rate()` null: re-query raw (G1) |
| 2 | 9 Verdict | Steady amplitude or wandering envelope? | Wandering: resonant noise, not a limit cycle |
| 3 | 11 Aligned on schedules | Does a cron, batch or upstream match the period? | **Forced.** Fix the driver, not the loop |
| 4 | 38 Shared map | Do other loops share it? | Find the common cause before retuning any victim |
| 5 | 8 Commanded vs actual | Deadband, cooldown or stick-jump? | **Actuator nonlinearity** |
| 6 | 21 Delay budget | Has delay grown against the margin? | Remove delay first: usually the cheapest fix |
| 7 | 40 or 29 | In simulation, does lower gain or less delay remove it? | **Excess gain or delay**, then canary |

**Output:** self-sustained, forced, resonant noise or inconclusive. A forced signal also has steady amplitude, so step 3 is required (CM 22).

### 5.3 Why isn't this done? (one item)

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 18 Aging WIP, 19 Survival | Is it actually late, counting open items? | No: it is on track, say so |
| 2 | 67 Wait-for, 74 Dependencies | Is it waiting on something? Follow to the root | Check the target is unfinished: `blocked_by` goes stale (G40) |
| 3 | 75 Critical path | Does its delay move the end date? | No: it has slack, and may not be urgent |
| 4 | 73 Sequence | Where did the time go, and who acted last? | A long gap names the wait |
| 5 | 68 Variants | Is this path common? How long does it usually take? | Rare path: an exception, name it |
| 6 | 20 Delay profile, 17 CFD | Typical wait? Is the stage congested for everyone? | Yes: go to 5.4. No: item-specific |
| 7 | 76 Gantt (levelled) | When will it finish? | State the assumption |

**Output:** current stage, time over expected, what it waits on, item-specific or systemic, and what would release it.

### 5.4 What is holding everything up? (the system)

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 3 Reconciliation | Can the counts be trusted? | Fails: fix the data first |
| 2 | 17 CFD, 18 Aging | Are WIP and age rising while throughput is flat? | No: nothing systemic. Stop |
| 3 | 67 Wait-for | Which roots hold the most work behind them? | **A root found:** check it with step 4 |
| 4 | 73 Sequence on one blocked item | Is the wait real? Who acted last? | Stale link: remove it from the count |
| 5 | 70 Bottleneck | No single root? Is a capacity constraint the cause? | Go to 5.9 |
| 6 | Blocks and Dynamics views | Which rule or loop keeps it there? | Name the policy |
| 7 | 43 Loop dominance, if the fit passes | Is that loop dominant now? | |

**Output:** a list of what to unblock, ranked by the work behind each root and grouped by who can act, or a named constraint with evidence.

### 5.5 Did this change help?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 3 Reconciliation | Did instrumentation change instead? | Stop: the comparison is invalid |
| 2 | 11 Aligned on the change | Was it scheduled or reactive? | Reactive: regression to the mean is likely (G14) |
| 3 | 28 Residual chart | Did it depart from expected dynamics? When? | Shift predates the change: **not this change** |
| 4 | 6, 7 Saturation, effort | Did it move the outcome, or only move the effort? | A flat output with a busier actuator is not a gain |
| 5 | 19 Survival, before and after | Whole distribution, or only the tail? | |
| 6 | 54 Counterfactual, if valid controls exist | How large, with what interval? | |

**Output:** changed, not detected or confounded, with effect size and interval. "Not detected" states the smallest effect the data could have shown (CM W1).

### 5.6 Will this policy help?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 47 Reference mode | What do we expect, stated **before** simulating? | |
| 2 | 25, 26, 27 Adequacy, fit, tests | Is the model fit for this question? | No: stop and say what is missing |
| 3 | 45 Boundary, 56 Reachability | Does the policy act on something the model explains and the knob can move? | No: the model cannot answer |
| 4 | 29 Paired comparison | Better than nothing, over a horizon of 3x the longest delay? | Watch for worse-before-better and for early gains that reverse |
| 5 | 30 Fan, 48 Screening | Does the gain survive uncertainty? Which assumption reverses it? | Straddles the threshold: measure that parameter first |
| 6 | 27 Extreme conditions | Does it fail badly under stress? | |
| 7 | After shipping: 28 | Record the prediction, then judge it | Main's `judge` already scores changes on later data |

**Output:** expected effect with range, time to payoff, the assumption it depends on, and the observation that would prove it wrong.

### 5.7 What breaks if this fails?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 71 Impact | What is downstream: hard, soft or unknown? | Label it "could be affected" (G41) |
| 2 | 81 Dominators | Is anything cut off entirely? | A proven single point of failure, given the graph is complete |
| 3 | 72 Service map, edge rates over 7 to 30 days | Is each dependency live? | Mark stale edges by last seen |
| 4 | 82 Time-respecting check, on past incidents | Did it really propagate this way? | Impossible chains are removed |
| 5 | 29 Policy comparison, for modelled stocks | How fast does the backlog grow, and when does it breach the goal? | |

**Output:** expected reach with confidence, what is unknown, and which fallback to test.

### 5.8 What path does work actually take, versus the path we declared?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 69 Conformance | Fitness and precision together. What are the top deviations? | High fitness alone proves little |
| 2 | 68 Variants | What are the real paths, with duration and outcome? | **Never** read a path off the map (G35) |
| 3 | 66 Process map, concurrency marked | Where do they diverge? | A backward line may be concurrency (G34) |
| 4 | 68, by outcome | Are deviating items faster, slower, more often reverted? | Better outcomes: the declaration is wrong |
| 5 | 78 Graph diff | Did the deviation start at a change? | Go to 5.5 |

**Output:** fix the process, change the declaration, or accept the exception, with the evidence for that choice.

### 5.9 Where is the bottleneck?

| Step | Chart | Question | If so |
|---|---|---|---|
| 1 | 70 Bottleneck (bounds) | Is throughput past the knee for this WIP? | Past it: more WIP adds only delay |
| 2 | 70, utilisation and wait per station | Which station is most utilised, with a queue? | **Never** use centrality (G37) |
| 3 | 17 CFD | Does a queue build before it, and starvation after? | No: it is blocked from downstream, look there |
| 4 | 70 over time | Is it stable, or does it move? | Moving: fix the variability first |
| 5 | 64 Flow efficiency | Is the top wait a person or an external party? | More machine capacity will do nothing |
| 6 | 88 Queueing, or 29 | What would the change gain, and what is the **next** bottleneck? | |
| 7 | After the change: 5.5 | Did the prediction hold? | |

**Output:** the constraint, its evidence, the expected gain, and where the constraint moves next.

---

## 6. Guardrails

**Refuse** returns no drawable result, with the reason and the fix. **Warn** draws it with the warning on the chart. Each is a reason code in the verdict, and each needs a test.

| ID | Misuse | Trigger | Action |
|---|---|---|---|
| | **Signals and sampling** | | |
| G1 | **`rate()` window hides an oscillation.** A boxcar of width W removes period W and its harmonics (CC B9, CM fact 3) | A period of interest is near W/k, or the query has a range window and the chart is spectral | **Warn**, mark each null on the axis. `analysis` re-reads raw, and **refuses** a spectrum if raw is unavailable |
| G2 | Aliasing | Period below 2x max(scrape, step) | **Refuse** that band: shade it as not observable |
| G3 | Confusing a dashboard's window with one inside the loop | Delay budget | Count only windows the **controller consumes**. In-loop windows do cost margin: Ms 1.59 to 6.10 as W grew from 0 to 8 on the reference loop (CC G5) |
| G4 | Mixed windows across signals create false lag | Series in one panel have different windows or steps | **Warn**, print each window |
| | **Identification and frequency** | | |
| G5 | **Drawing a frequency response from noise** | Server floor not used, or no frequency survives correction across frequencies, or too few segments | **Refuse.** Use the server's floor, never a fixed 0.6. Apply a false-discovery correction over frequencies. One segment gives coherence exactly 1 (CM 14) |
| G6 | **Plant gain from closed-loop data** | Closed loop, no external excitation | **Refuse** the "plant" label (CC finding 2, CM 9) |
| G7 | Tuning a saturated loop | Time at limit above threshold | **Suppress** tuning advice, and exclude those segments from estimators |
| G8 | One margin for a nonlinear loop | A margin without an operating point | **Refuse** to show the number without it |
| G9 | Harris index without a delay | Delay missing or uncertain | **Refuse** without one; show the range over the delay's uncertainty. The same data gave 0.55, 0.81 and 0.95 (CC F1) |
| G10 | Ziegler-Nichols as advice | Anyone asks | **Refuse** as a recommendation; explain with the Ms comparison |
| G11 | Diagnosing stiction from OP-PV | MV absent | **Warn** "ambiguous". Linear dynamics also produce ellipses (CC F2) |
| G12 | Fitted poles read as physics | Interval crosses the stability boundary, or near-cancelling pairs | **Refuse** "stable"; warn of over-fit |
| | **Statistics and causation** | | |
| G13 | Limits on autocorrelated data (34% false alarms at phi = 0.9, CM 38) | Lag-1 autocorrelation above threshold | **Refuse** raw limits; chart residuals |
| G14 | Events chosen because the metric moved | Reactive events in an aligned or before/after view | **Warn**; test against random placebo times; show n |
| G15 | Correlation read as cause, or searching many pairs (52% false positives at phi = 0.9, CM 13) | Lag or map views | Prewhiten, draw a band, say "leads", correct for pairs searched, report how many |
| G16 | Calling a spectral peak a limit cycle, or cron a control problem | Oscillation verdict | Three-way verdict plus "inconclusive"; a driver check is required |
| G17 | "Metastable" without evidence | Trigger not ended, or one trajectory | **Refuse** the label; say "observed path" (CC G3, CM 52) |
| | **Stocks, flows and delays** | | |
| G18 | Forcing a balance with a plug flow | Reconciliation fails | **Never** add a balancing flow. Report "unexplained flow", and lower confidence on dependent charts |
| G19 | Treating a Prometheus residual as exact | `increase()` extrapolates | **Warn** with a tolerance; offer the SQL form |
| G20 | **Completed-only durations**, including `histogram_quantile` on `time_in_state` | A delay percentile while open items are older than it | **Warn** with how many open items are older. Use chart 19 |
| G21 | Cancelled items treated as censored | Survival | Competing risk. Cut off the curve at small at-risk n. If it never falls below 15%, **p85 is undefined, and says so** (SD 35) |
| G22 | Averaging percentiles, or a p99 inside a wide bucket | Histogram queries | **Warn**; show bucket bounds; aggregate buckets before the quantile |
| G23 | Binding a counter's rate to a stock, or a gauge to a flow | Model binding | **Refuse** (owner's rule: stocks are gauges, flows are counters) |
| G24 | A generated ID as a metric label | Metric write | **Refuse** at the cardinality guard |
| G25 | A horizontal CFD reading as cycle time | Non-FIFO or re-entry | Hide the readout unless the discipline is declared FIFO |
| | **Models and simulation** | | |
| G26 | Fan or policy result from a model that failed its tests | Fit or tests failing or not run | **Refuse** a recommendation; draw it labelled "unvalidated" only on request |
| G27 | Comparing unpaired runs, or differencing two fans | Policy comparison | **Refuse** unless paired by draw, with the same runs valid in both arms |
| G28 | Horizon shorter than the slowest delay | Below about 3x | **Warn**: short horizons reward fixes that fail |
| G29 | Bands read as total uncertainty | Every fan | Label "parameter uncertainty only", state each prior's source, warn on bimodal outcomes |
| G30 | Dominance or an archetype read as fact about the system | LTM, archetypes | Label "in the model"; grey out equilibrium, never plot zero; name an archetype only as a candidate with a falsifying test |
| G31 | A single "validated" badge or health score | Scorecards | **Never** compute one. Keep "not run" and "not assessable" visible |
| G32 | Extrapolating past observed load | Operating curve, tipping point | Draw unobserved regions as assumed. **Refuse** a numeric tipping point the data never reached |
| G33 | An active experiment without limits | Any step or dither | **Refuse** without declared limits, abort condition, rollback and owner approval |
| | **Graphs and process maps** | | |
| G34 | **Concurrency reported as rework** | A line to an earlier step on an item that had not been there | Count rework **only on a repeated step**; mark likely concurrent pairs (B1, ND X2, X3) |
| G35 | **Invented process-map paths.** k routes through one hub draw k² paths (ND X1) | Tracing a route on a graph with `paths_real: false` | **Refuse** to report the route as taken; open the variants containing it |
| G36 | Filtering leaves invisible gaps: 100 enter a step, 80 leave (ND X4) | A frequency filter is on | State on the node what went by routes not shown |
| G37 | **Betweenness choosing the wrong bottleneck** (ND X5) | Any request to rank by centrality | **Not offered.** Bottlenecks come from utilisation, wait, and queue before with starvation after. Fan-in and fan-out stay, by name |
| G38 | **False Granger edges** (41 of 56 with a shared driver, ND X7) | A lead-lag result | **Never drawn as a network.** A ranked `table`, conditioned on other series, corrected for tests. **Refuse** non-stationary input. A `wait_for` or `dependency` kind built from correlation is refused |
| G39 | **Unstable layouts when scrubbing** (88% of nodes moved by one edge, ND X10) | Any change of frame | One layout over the union of the window; values only per frame; absent edges ghosted |
| G40 | Stale edges shown as live | A `blocked_by` to finished work, or an edge not seen lately | Check the target; show last seen and the wait's age. Say "not seen for N", never "removed" |
| G41 | Reachability read as impact | Impact graph | Label "could be affected", give the graph's age. Retries and fallbacks reduce reach; uninstrumented paths add to it |
| G42 | Critical path read as the finish date | Work shares limited capacity | Show the levelled end beside it: 9 against 13 in ND X6 |
| G43 | Analysis on a truncated graph | `omitted` not empty | Compute on the full graph; **refuse** an answer if the full graph is over its limit |
| G44 | A cycle called a defect on a control model | Cycle findings | The `kind` sets the wording. Feedback in Dynamics and Blocks is never a warning |
| G45 | Averaging latency across aggregated edges | Collapsed groups | Merge histograms, or show the worst by name. One unhealthy member marks the group |
| G46 | Ranking people | Wait-for roots, ownership | Label the *thing* awaited. No per-person views |
| G47 | Today's structure drawn on last month's traffic | Scrubbing or comparing past windows | Draw the structure `as_of` that time |
| G48 | Low-rate edges missing under trace sampling (2.3% chance at 24 calls, 1/1024, ND X8) | A service map from sampled traces | **Warn**; do not read absence as no dependency |

---

## 7. Proposed build order

Not filed. Sized for one factory work item each. "Unlocks" lists chart IDs from §3.2.

### 7.1 Work items

One list, in order. **B1 and B2 come before the trust layer**, because each corrects a number displayed today and needs nothing else. B3 to B5 are the trust layer.

| # | Name | Delivers | Unlocks | Depends on |
|---:|---|---|---|---|
| B1 | `fix-process-rework-flag` | Rework counted only on a repeated step, with a count of returns (§7.2) | 66 (correct) | none |
| B2 | `frequency-refuses-noise` | The panel uses the server's floor, not 0.6; a correction across frequencies; the refusal (G5) | 35 (correct) | none |
| B3 | `result-frames-and-verdicts` | The six shapes, the envelope, roles on fields, the tested family-by-shape table, verdict display in the panel | 14, 16 | `data-source-model`, `chart-result-shapes` (amended), `panel-editor-sidebar-simplified` |
| B4 | `item-metrics-that-balance` | Arrivals and forgotten items counted as transitions, a test that gauge change equals net transitions | 17 | `item-metrics-from-the-log` (amended), `metrics-store-with-labels` |
| B5 | `analysis-source-and-window-guard` | The `analysis` type and its call language; raw re-read on one grid, window ledger, observable period band (G1 to G4); `pair`, `psd`, `spectrogram`, `ccf` | 10, 36 | B3 |
| B6 | `graph-result-and-panel` | `graph`, the three producers adapted, named kinds, ELK in a worker, budgets and aggregation, matrix fallback | 74, 75, 77 | B1, B3 |
| B7 | `loop-roles-and-loop-panels` | A goal's roles exposed to panels, plus goal history | 1, 5, 6, 7, 8 | B3, B5, `dashboard-variables` |
| B8 | `stock-flow-reconciliation` | `reconcile`, the conservation ledger, lowered confidence on dependent charts | 3 | B4, B5 |
| B9 | `item-spans-and-censored-delays` | `item_spans` view, `survival`, `little`, G20, G21 | 4, 18, 19, 20, 50, 51, 52, 64, 80 | `sql-source-over-item-views`, B3, B5 |
| B10 | `wait-for-impact-and-sequence` | `waits()`, `impact()`, SCC overlay, dominators, the sequence diagram | 67, 71, 73, 81 | B6 |
| B11 | `variants-and-conformance` | Variants, concurrency marks, declared vs observed, filter honesty (G36), soundness | 66, 68, 69, 79, 83, 87 | B1, B6, B9 |
| B12 | `event-marks-and-aligned-response` | Event marks on every time axis (scheduled or reactive), `align`, placebo test | 2, 11 | B5 |
| B13 | `bottleneck-and-operating-curve` | Utilisation, wait and bounds per station; `settled_bins`; operating curve; load vs goodput with its refusal | 13, 15, 70, 33 | B5, B6, B9, B12 |
| B14 | `loop-diagnosis-and-scorecard` | Three-way oscillation verdict with driver check, delay budget, shared map, fleet scorecard | 9, 21, 22, 37, 38 | B7, B8, B12 |
| B15 | `service-map-diff-and-time` | Service map from caller and callee labels, the fixed union layout, frames, graph diff, time-respecting check | 72, 78, 82 | B6, B12, a traffic source |
| B16 | `model-trust-panels` | Adequacy, step response, held-out fit with Theil and residuals, test scorecard, on the `model` source | 12, 25, 26, 27, 31, 32, 34 | `model-data-source` (amended), B2, B3, B5 |
| B17 | `paired-policy-comparison` | Per-draw results from `closedloop.risk`, paired difference, fan and tornado panels, G26 to G29 | 29, 30, 48 | B16 |
| B18 | `change-verdict` | `residual_chart`, before/after, counterfactual with declared controls | 28, 54 | B12, B16 |

**The order in one line:** B1 and B2 now; B3 to B6; then B7 to B12 in parallel; then B13 to B15; then B16 to B18.

B16 can start as soon as `model-data-source`, B2 and B3 are in, and may run alongside B7 to B12 if there is capacity. It is later only because its charts mean little until the data they rest on can be trusted. B15 waits for a traffic source; without one, its diff and fixed layout can still ship on process maps.

### 7.2 The confirmed bug: concurrency reported as rework

**Confirmed** on `origin/main` at `dc47a763`, by running the real code on a synthetic record in a scratch copy.

**Where.** `ergostat/process.py`, function `process()`, line 474:

```python
e["rework"] = e["kind"] == "follows" and (e["source"] == e["target"] or place(e["target"]) < place(e["source"]))
```

An edge is rework if its target sits earlier in a *global* order of steps: the declared order by states, or each type's median position by events. Nothing asks whether this item had been at the target. The code does what SPEC §5b's table says, so the definition is at fault as well. The same SPEC says elsewhere that "rework is a repeated step".

**Smallest failing case.** Two items, two event types, nothing repeated: `job/0` does `s.x, s.y` and `job/1` does `s.y, s.x`. With `by="events"`, the line `s.y > s.x` has `rework = True`. Both types have median position 0.5, the tie breaks by name, and one direction becomes "backward".

| Case | Main | Patched |
|---|---|---|
| Two items, opposite order, none repeated | 1 rework line | 0 |
| 100 jobs, 3 concurrent steps, none repeated | 3 lines, 100 passages | 0 |
| By states: `a, c, b, d`, none repeated | 1 line (`c > b`) | 0 |
| By states: `a, b, c, b, d`, a real return | 1 line (`c > b`) | 1 line, 1 return |

ND measured 94 passages on its own random log; the count depends on the draw, the defect does not. The by-states case shows the bug is not limited to concurrent events: any out-of-order first visit is flagged.

**The fix (13 changed lines in `process.py`, tried on the scratch copy; the 12 tests in `tests/test_process.py` still pass).** While walking each item's pairs, keep the set of steps it has already been at, seeded with the states it entered before the window. A passage is a **return** only if its target is in that set.

```python
seen = set(w.earlier.get(id, ()))        # per item; earlier = states entered before the window
...
if a != START: seen.add(a)
if b != END and b in seen: e["returns"] += 1
...
e["rework"] = e["kind"] == "follows" and e["returns"] > 0
e["backward"] = e["kind"] == "follows" and place(e["target"]) < place(e["source"])   # layout only
```

**Also in B1.** `process.js` shows `returns` rather than the line's whole count, since one line can mix real returns with first visits, and its legend (line 479) changes wording. SPEC §5b's definition changes. Add the four cases above as tests.

**Limit.** By events, the window is all the code reads, so a return to a step seen before the window is missed (an undercount, never a false alarm). A type that legitimately repeats, such as a note, still counts as a return, as it does today.

### 7.3 Amendments to the listed gaps

If a gap is already in progress, make its amendment a follow-up instead.

| Gap | Amendment | Why |
|---|---|---|
| `chart-result-shapes` | Six shapes, with the envelope. "Two signals" becomes `series` with roles. Client-side transforms stay for reshaping only | §2 |
| `data-source-model` | Results carry `meta.sampling`. A source type declares its counter semantics | G1, G19, and §7.4 item 2 |
| `item-metrics-from-the-log` | Name the two edges of the system with reserved states: an arrival (a move with no `from` in the index) is `from="(new)"`, and an item the index forgets is `to="(gone)"`. Backfill must state what pruned history it cannot recover. Say that `time_in_state` is observed at exit | Otherwise reconciliation reports a false leak, and the histogram is read as if it included open items |
| `sql-source-over-item-views` | Add `item_spans` with open items, re-entry number and terminal reason | Survival, aging and exact Little's law need it |
| `model-data-source` | Takes B2's refusal as given. Pole-zero of a delayed process uses the discrete model and states `dt` | Done-condition 3 ("uncorrelated input and output yields the refusal") **cannot be met** by a per-frequency floor: 98% of noise records in the check above had a frequency above it |
| `dashboard-variables` | Safe interpolation also covers the `analysis` and `model` languages | Its done-condition 2 |
| `retire-old-query-forms` | Add dependencies on B5 and `model-data-source`, and carry over the answers `query/shaped.py` builds and the `include_open` option of `query/sources.py` | PromQL alone cannot produce paired, binned, OHLC or frequency answers, so phase, scatter, candlestick and Bode would lose their data route, and durations would lose the open items |

A reconciliation query for B8, on the amended metrics. `or vector(0)` matters: a state nothing has left yet would otherwise make the whole expression empty.

```promql
(
    sum(ergostat_items{kind="$kind", state="$state"})
  - sum(ergostat_items{kind="$kind", state="$state"} offset 1h)
)
- (
    (sum(increase(ergostat_item_transitions_total{kind="$kind", to="$state"}[1h]))   or vector(0))
  - (sum(increase(ergostat_item_transitions_total{kind="$kind", from="$state"}[1h])) or vector(0))
)
```

### 7.4 Not reconciled: needs the owner

1. **The default dashboard on SQLite.** `metrics-store-with-labels` says PromQL panels on SQLite only say what is needed. `retire-old-query-forms` makes the default dashboard use only data-source queries. Together, a default install shows an empty dashboard. Falling back to SQL for item charts would contradict "PromQL is primary". **Recommendation:** make the supervised VictoriaMetrics the default store for new installs, and keep existing installs on the old forms until they migrate.
2. **`rate()` and `increase()` semantics.** The reports describe Prometheus, which extrapolates to the window edges. VictoriaMetrics, the recommended store, is understood to compute these differently `[unsure: not covered by the reports; check before relying on it]`. Tolerances in G19, and the window nulls in G1, must be tested on the actual store.
3. **The minimum record for an oscillation verdict.** `control/monitor.py` accepts four periods. The reports suggest about 10 `[unsure: rule of thumb]`. Neither has been tested on real ergostat loops. **Recommendation:** keep four for detection, require ten before the three-way verdict, and tune both on the factory's own record.
4. **What "rework" means.** SPEC §5b defines it as a line to an earlier step, and elsewhere as a repeated step. B1 takes the second, which changes what the Process view shows and needs a SPEC change. **Recommendation:** adopt "a return to a step this item has already been at"; a backward line that is not a return keeps its direction but loses the ↺.
5. **Where runtime traffic comes from.** Nothing on main draws it, and a service map needs series with caller and callee labels (from tracing or a mesh). **Recommendation:** ship the map as a panel kind that says what it needs, and build B15's traffic half only when such a source is attached.
6. **New diagrams against the recorded position.** `docs/proposals/diagram-options.md` records new diagram types as "not planned", with user flows first, and ND's rankings were not tested with users. **Recommendation:** treat B10 and B11 as answers to the owner's named questions, and hold the rest of the graph views until those two have been used.

---

## Appendix A: claims carried as unsure

These stay marked until checked. Do not quote them in product copy as established.

| Claim | Source |
|---|---|
| Sample at least 4-10 times per closed-loop rise time | CC A1 `[unsure]` |
| At least about 10 periods for a spectrum; 8+ samples per period for oscillation detection | CC B9, F3 `[unsure]` |
| Harris needs 500-2000 samples, AR order about 10-30 | CC F1 `[unsure]` |
| Inner loop should be 3-10x faster than outer | CC E3 `[unsure]` |
| Gain varying more than about 2x means one tuning is suspect | CC G2 `[unsure]` |
| The idle index applies to software loops | CC F5 `[unsure]` |
| Idle index, Harris and stiction methods transfer to software at all | CC §11: inference, no published validation found |
| ergostat models will be large enough to need model reduction | CM 3 `[UNSURE]` |
| A second equilibrium at high backlog is the shape of a metastable failure | CM 19 `[UNSURE]`: needs model support per system |
| The describing function's low-pass assumption holds for HPA | CM 23 `[UNSURE]` |
| Early-warning indicators work in production software | CM 30 `[UNSURE]` |
| Wavelets add little over a spectrogram | CM exclusions `[UNSURE]` |
| "About 10 cycles" and "30 crossings" | CM verification notes: rules of thumb |
| Howard 1988 as the origin of the tornado chart | SD 20 *(unverified)* |
| The names "structure assessment" and "parameter assessment" in Sterman's 12 tests | SD 26 *(unverified)* |
| Survival analysis applied to flow metrics | SD 35: the report's inference, no standard flow reference found |
| TLA+-style tools serve the coloured Petri net audience better | ND A3 `[unsure]` |
| A Marey chart should cap at about 200 lines | ND C8 `[unsure]` |
| A radial layout is about 100 lines of plain SVG | ND §12.2 `[unsure]` |
| Budgets of about 300 matrix rows and 50,000 server edges | ND §12.3 `[unsure]` |
| Small multiples are generally faster than animation | ND §12.5 `[unsure]` |
| "Both orders are common" detects concurrency | ND §14.5: a heuristic; can mislabel real alternation |
| ND's ELK timings carry over to a browser | ND §12.3: Node, a single run, no rendering |
| VictoriaMetrics computes `rate()` and `increase()` differently from Prometheus | This catalog, §7.4 `[unsure]` |

**Checked for this catalog:** the coherence figures in §1 and G5 (the Welch estimator from `query/frequency.py` on main, run on independent Gaussian noise, 60 runs per configuration), and the rework cases in §7.2 (`process()` from main and a patched copy, on a synthetic record in a scratch directory). Everything else numeric is from the reports, which state how each was obtained. Their simulations are small illustrations, not measurements of real systems.

## Appendix B: references

All references are in the source reports, with their evidence labels: [classical](control-classical.md#references), [modern](control-modern.md#references), [system dynamics](system-dynamics.md#sources), [network diagrams](network-diagrams.md#15-references). The ones this catalog leans on most:

- Little, [*Little's Law as viewed on its 50th anniversary*](https://doi.org/10.1287/opre.1110.0940) (2011)
- Forssell & Ljung, [*Closed-loop identification revisited*](https://doi.org/10.1016/S0005-1098(99)00022-9) (1999)
- Bronson et al., [*Metastable Failures in Distributed Systems*](https://doi.org/10.1145/3458336.3465286) (2021)
- Schoenberg, Davidsen & Eberlein, [*Understanding model behavior using the Loops that Matter method*](https://doi.org/10.1002/sdr.1658) (2020)
- van der Aalst, [*A practitioner's guide to process mining: limitations of the directly-follows graph*](https://www.vdaalst.com/publications/p1101.pdf) (2019), cited in ND C1
- Denning & Buzen, [*The operational analysis of queueing network models*](https://doi.org/10.1145/356733.356735) (1978)
- Holt, [*Some deadlock properties of computer systems*](https://doi.org/10.1145/356603.356607) (1972)
- Borgatti, [*Centrality and network flow*](https://doi.org/10.1016/j.socnet.2004.11.008) (2005)
- [Prometheus query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
