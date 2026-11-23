# An autoscaler ergostat does not run

One deployment, `web`, and a horizontal pod autoscaler (HPA) that holds its CPU at a target. The HPA is the
cluster's, not ergostat's: ergostat only reads what a cluster exposes (the replicas, the CPU, the scaling events),
models the autoscaler as an **external** controller, identifies its law from that record, and judges the loop it
closes.

- `cluster.py` is the made-up cluster. Its world moves on the wall clock whenever anything reads it (`.sim.json`):
  requests that swell and fall, a pod's CPU per request, new pods that take 10 s to take load, and the HPA's documented
  rule (every sync, desired = ceil(replicas × utilisation / target), nothing within 10% of the target, up at most
  max(100%, +4 pods) a sync, down to the highest recommendation of its stabilisation window, 2 to 20 pods). Its windows
  are a third of the defaults (sync 5 s, stabilisation 100 s) so a few minutes show some scaling.
- `ergostat.yaml` has stocks for `replicas` (what the HPA sets) and `load` (CPU in use, in cores, moved by the
  traffic: a disturbance), the auxiliary `utilisation` (the HPA's metric, load / replicas), the goal it serves
  (`cpu-at-target`: utilisation ≤ 0.6, the HPA's own 10% as its tolerance), and the block `web-hpa`: `type: external`
  on the agent `kubernetes` (`external: true`), reading utilisation, moving `scale` (a two-way flow into replicas), and
  `identify: {input: auxiliary.utilisation, output: stock.replicas}`. The `rescales` use collects its scaling events
  (`SuccessfulRescale`, as `kubectl get events` shows them) as items of kind `rescale`.

```bash
cd examples/autoscaler
ergostat check        # ok; one finding: the modelling loop runs on its stand-ins
ergostat run          # prints the page's address
ergostat run --stop
```

## What to look at

Give it ten minutes or more: the law needs 40 points of both signals and three moves of replicas (its sensors read
every 5 s), and a longer record tells it better.

- **Blocks**: `web-hpa` is drawn in its loop as a controller, the target r (`cpu-at-target`) and the measured
  utilisation y going into it, the replicas u coming out into the process. Once its law is fitted the block writes
  it with a small *identified* mark (a staircase for a stepper), and its panel says the law, its delay, and its fit:
  the skill one step ahead and the R² run free on the quarter of the record held out.
- **The loop's panel** (`/api/loop-control?goal=cpu-at-target`): u is replicas, y utilisation, and the controller is
  `web-hpa`, external, with its identified law and fit, or why it has none yet ("its law is not identified: 24
  points of record on a 5s grid (at least 40)"). Beside it, the loop judged: how often and how far it was over its target, whether it
  oscillates, its excursions and how long each took to settle.
- **Agents**: `web-hpa` is listed as a program it does not run: "not run here", no runs, its roles the controller of
  `cpu-at-target` and the valve that moves `scale`. Nothing in the record is a run of it; its moves are read off the replicas.
- **Items**: each scaling event, as an item of kind `rescale`.

The rule is the HPA's, multiplicative and windowed; the laws ergostat fits are on-off, proportional, PI and
three-position step, so what it says is the nearest of those the record supports, and it differs from record to
record: on forty-minute records it came out mostly a stepper, up past about 0.67 to 0.70 (the target and its 10%
tolerance), down only far below it, and on one a PI law. Its fit is modest (a skill of about 0.2, an R² of about
0.5): read it as what the autoscaler did, beside the rule its description says it was configured with, not as that
rule recovered. The HPA's own rule as a law of its own is not in ergostat yet.

Not yet: stability margins for an external controller. They are worked out from a law written in the model
(`gain:` on a block), so the loop's panel shows none here, even where the process is identified; and in this demo
the process from replicas to utilisation (a division, not a lag) is not told apart by the record anyway.

## What ergostat adds

The autoscaler's own dashboard shows its target, its current and desired replicas, and its events. It does not say:

- what law it behaved as, in numbers, and how well that law predicts it (the fit on held-out record);
- how the loop is doing as a loop: time over target, oscillation, settling of each excursion, saturation at 20 pods;
- what will happen next: the closed-loop projection runs the identified law forward against the load;
- that it is one controller in a larger model (other loops, other systems acting on the same load), drawn in the same
  diagrams as the controllers ergostat does run.

Shows: an external block with `identify:`, an `external: true` agent, a setting (a two-way flow into a stock) moved by
a controller ergostat does not run, a disturbance, `collect` for a system's own events.
