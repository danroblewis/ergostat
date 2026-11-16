# Modelling the control systems that already exist

Status: proposed 2026-11-16; to be built after the model-improvement work (equations, simulation,
fit, identification) lands, because it stands on it.

## The problem

Most of the control in a company already runs elsewhere: Kubernetes (the horizontal pod autoscaler,
the cluster autoscaler, deployments rolling out), alerting and paging vendors (alert rules, escalation
policies), cloud autoscaling groups, feature-flag ramps. ergostat will not reimplement them. Today it
can only treat them as clouds (where material comes from or goes) or disturbances (pushes nothing
controls), which says nothing about how they work. The owner wants them modelled as what they are,
controllers and processes, so their behaviour can be explained, predicted, and shown to be
inefficient or wrong, with a fix proposed.

ergostat also keeps running its own blocks (AI agents, scripts): both matter.

## The idea: observed controllers

An **observed controller** is a block ergostat does not run (`type: external`, which exists): it
measures something and sets something, and both are read from where they already live.

```yaml
sources:
  metrics: {type: prometheus, url: https://…}        # Chronosphere and most vendors speak PromQL
  k8s: {type: kubernetes, context: prod}             # read-only

blocks:
  hpa-checkout:
    type: external
    law: kubernetes-hpa                               # a known law, from the library below
    params: {target: 0.6, min: 3, max: 40, stabilize-down: 300s}
    in: auxiliary.cpu-utilisation                     # what it reads (a sensor on the metric)
    out: stock.replicas                               # what it sets (read from the cluster)
```

- **Its inputs and outputs are measured,** through read-only sources: PromQL (Prometheus,
  Chronosphere, Grafana Mimir; Google Cloud's managed Prometheus), the Kubernetes API (an HPA's
  status, a deployment's replicas, events), cloud monitoring APIs (Google Cloud Monitoring,
  CloudWatch), paging APIs (incidents, escalations). Nothing is written.
- **Its law is declared where it is known.** The HPA's is public:
  desired = ceil(current × metric / target), bounded, with stabilisation windows. A **library of
  known controllers** ships with ergostat as model fragments with their equations and parameters:
  the HPA, the cluster autoscaler, a rolling deployment, an alert rule with its `for:` duration, an
  escalation policy. You include one and bind it to your metrics.
- **Where the law isn't known, it is identified** from the record (the control tools: gain, time
  constant, delay, dead band), and where it is declared, **the declaration is tested** against
  what the controller actually did: the fit says whether it behaves as configured.
- **Then the control analysis applies to it** like any loop: oscillation (scaling up and down),
  sluggishness (lag behind load), saturation (pinned at max), over-provisioning (replicas held far
  above what the load needs), and interference between loops that act on the same process (an HPA
  and a cluster autoscaler; two alert rules on one symptom). Each finding can carry a proposal: a
  parameter change, with the simulated effect.

## The process side

What the observed controllers act on (load, latency, queue depth, error rate) is modelled as
stocks, flows and auxiliaries bound to metrics, with equations estimated from the record (the
foundation's calibration). Candidate structure from metrics alone is the system-identification
work Orchestra did (Kalman filtering with a linear noise approximation): to be ported after this.

## A demo without work access

`~/orchestra-kube-sim`, a faux Kubernetes system with an HPA loop and request rates exported to
Prometheus, is the first target: model its HPA as an observed controller, identify it, find where
it oscillates or over-provisions, propose a change, and show the projection.

## What it answers when people ask "why model it again?"

The vendors hold measurements and their own rules, one system each. None holds the model that
relates them: which controller acts on what, how they interact, what will happen next. ergostat
reads from them and holds that model. It replaces none of them.
