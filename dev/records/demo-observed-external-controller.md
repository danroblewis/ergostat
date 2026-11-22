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
