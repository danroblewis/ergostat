# demo-observed-external-controller: A demo has an observed external controller (an autoscaler), identified and judged

depends-on: []

Problem (R12 piece 4): ergostat is meant to sit on top of existing control systems and join them 'as another controller' (intent.md; docs/proposals/external-systems.md), but no demo has an observed external controller, so the claim that it can model, identify and judge a vendor's control loop (a Kubernetes autoscaler) is never shown.
Change (demo work): add to a demo (big's api system or a small new demo beside the kube simulation) a simulated horizontal autoscaler that ergostat does not run: it reads a request rate or utilisation, sets replicas with the autoscaler's usual rule (target utilisation, stabilisation window, scale-up/down limits), and emits only what a real cluster would expose (metrics and scaling events). The model declares it as an external block (the agents: entry `external: true`, an observed controller with its inputs and outputs), with stocks for replicas and load, the goal it serves, and sensors reading its metrics. ergostat identifies its law from the record, shows it in Blocks as a controller with its identified law and fit, and judges the loop (holding, oscillating, margins when the process is identified). The README says what to look at and what ergostat adds that the autoscaler's own dashboard does not.
Definition of done:
1. In the demo, Blocks draws the autoscaler as an external controller in its control loop with r (target), y (utilisation) and u (replicas).
2. /api/loop-control for its goal returns an identified law for the external controller with its fit, or says why not.
3. The Agents page lists it as external and not run by ergostat, with no runs of its own.
4. `ergostat check` passes; the demo's README has the walkthrough.
Files: demos/<demo> (model, simulator, README.md), tests/test_demo_check.py; no page code unless a defect is found (file it separately).
Acceptance tests: a demo test asserting 1-3.
Budget: 200 net lines in the demo.

Milestone: r12-fewer-pages-better-demos. Owner items: R12 piece 4. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. A small new demo, `examples/autoscaler` (cluster.py, ergostat.yaml, README.md, .gitignore), not big's api
system: big is the layout corpus, so the most reversible choice was a demo of its own that removes cleanly. `demos/` in
"Files" is read as `examples/`, where the demos live. The kube simulation (`~/orchestra-kube-sim`) is not in this
clone, so the cluster is simulated in `cluster.py` with the HPA's documented rule (target, 10% tolerance, scale-up limit
max(100%, +4), scale-down stabilisation window, min and max, pods that take 10 s to be ready), its windows a third of the
defaults. It exposes replicas, utilisation, CPU in use and its scaling events (taken in by a `collect` use).

- **A defect found and fixed here, in the smallest form** (not page code: the loop's analysis): `/api/loop-control` never
  gave an external controller's identified law; it said "web-hpa reads more than its goal's error: its own map, not a
  linear law" while Blocks drew the law identified. `ergostat/control/loop.py` `external()` (17 lines) now puts the
  law, its numbers and its fit (skill, R², points) in `controller.identified` and says it, or says why there is none.
  It could not be filed as a gap of its own from this headless session; it is written here and in SPEC §12d instead.
  Reverting it is those lines and the two tests that need them.
- **Found, not fixed (filed here for a gap of its own):** Blocks draws an external block that reads its goal
  (`in: goal.X`) and steps a setting as an *integral controller* ("K_i is not written") and never as identified: the
  integral-controller branch in `blockdiagram.py` comes before the identified-law one. The demo's block reads
  `auxiliary.utilisation` (what an HPA reads) and the goal's r is drawn into it, so the demo is not affected.
- **Not built:** margins for an external controller's identified law (`lti.margins` takes a law written in the model);
  the README and SPEC say so, and GAPS lists it as left. The process from replicas to utilisation is not told apart on
  the demo's record anyway.
- The law identified varies by record: on 40-minute records it came out a stepper (up past 0.67-0.70) three times and PI
  once, with a modest fit (skill about 0.2, R² about 0.5); the README says that rather than claiming the HPA's rule is
  recovered.
- The Agents page has no "external" word of its own: the block's row says "not run here" with no count of runs (that
  is what the page writes for an agent with no command). The test asserts the data that row is drawn from, not the page.
- Not run here (the session's tool refused them): `ergostat run` on the demo, `scripts/demo_check.py autoscaler`, and
  the browser files; `ergostat check --json` was run, inside the acceptance test.
