# Why model systems this way

For a team deciding whether ergostat is worth their time. It answers the three doubts in the order
they come: *is this useful?*, *would we actually use it?*, *would it make a difference?*

## The short version

We already measure almost everything: cloud monitoring, metrics and alert vendors, paging, error
tracking, the warehouse. Each holds its own measurements and its own rules, one system at a time.
None of them holds **the model that relates them**: which controller acts on what, what accumulates
where, what causes what and how much, and what will happen next. That model lives today in
engineers' heads and in design docs, and it is usually wrong in ways nobody can see.

ergostat holds that model, reads its numbers from the systems we already have, and keeps it honest
against what they measure. It replaces none of them.

It looks at a system from two perspectives, each in its discipline's own notation:

- **System dynamics: what is.** Stocks (what accumulates), flows (what fills and drains them),
  causes with their signs, feedback loops. The view for explaining a system and predicting it.
- **Control: what we control.** Controllers, actuators, processes, sensors, setpoints. The view
  for judging whether each control loop, ours or a vendor's, does its job.

The shift it argues for: from *monitoring and observability* (what happened, what is happening) to
*dynamics and controls* (why it happens, what will happen, what to change).

## "Is this useful? We already have monitoring."

Monitoring tells you a number went up. It does not tell you:

- **why**: which flows filled the stock, which loop failed to drain it, which change upstream
  started it hours earlier (a cause acting over time sits in a stock, and only a model shows it);
- **what next**: when the queue reaches its limit, whether the autoscaler will catch up, what next
  week looks like at this growth;
- **whether the controls work**: an autoscaler that oscillates, lags its load, sits pinned at its
  maximum or holds three times the capacity it needs looks healthy on every dashboard. Read as a
  control loop, each of those is visible and measurable.

The model is not a copy of the monitoring. It is the structure the monitoring's numbers fit into.

## "Would we use it?"

It starts on one laptop and asks for nothing: read-only sources (PromQL, a command, the cloud's
APIs), no agents posting anywhere, no infrastructure. The first model can be one service's queue
and the autoscaler in front of it. It grows a part at a time, and `ergostat check` says what the
model is missing as it grows.

What makes it stick is that the model shows up where work already happens: in **design docs and
proposals**, as a diagram and a simulation that explain the change; in **postmortems**, as the
structure that explains the incident; in **planning**, as the forecast.

Run on a server later, it can take part in the control: as another controller beside the existing
ones, or running AI agents and scripts that do work when a goal is off, each measured on whether
it helped.

## "Would it make a difference?"

Where the impact comes from:

- **Explaining systems coherently.** Proposal and design docs built on a model that has been
  checked against the record, not on a whiteboard sketch.
- **Projection.** Capacity planning and cost reduction from a model calibrated on real data:
  how much the load will grow, what the fleet needs, where it is overprovisioned.
- **Predicting failures.** Stocks heading for a limit, loops that answer more slowly than they did,
  high-risk changes (an unreviewed flag ramp raises the alert rate hours later): found before the
  outage, and planned around, for example into maintenance windows.
- **Fixing the controls we already pay for.** Autoscalers, alert rules and escalation policies
  modelled as controllers, identified from what they actually did, shown where they are
  inefficient or wrong, with a proposed change and its simulated effect.
- **Removing redundancy.** A model of what each vendor and service controls shows where two do
  the same job, or fight over the same process.
- **Long-term health of what we sell.** Product features as stocks with their inflows and drains
  (adoption, regressions, churn), watched over months where other tools watch minutes.
- **Clearer expectations.** For product and project managers: what the system can deliver, how
  fast, at what cost, as a simulation rather than a promise. Projects such as a software factory
  become a model with measurable goals.

## What to look at

- `examples/the-job`: a senior engineer's job (reviews, alerts, flag ramps, documents, customer
  tickets) as a running system, with its morning brief and ledger. Simulated, so it runs anywhere.
- `examples/image-squeeze`: a service and an AI lab that improves it, measured on a benchmark and
  on live traffic.
- [QUICKSTART.md](QUICKSTART.md): ten minutes from install to your own model.
- [proposals/external-systems.md](proposals/external-systems.md): modelling the control systems
  that already run elsewhere (a Kubernetes autoscaler, alert rules) as observed controllers.
