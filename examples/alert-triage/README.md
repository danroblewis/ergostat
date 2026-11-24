# Alert triage: a workflow with a fan-out and a join, modelled well

Each alert from the pager is triaged by a narrow AI (noise is dismissed), its three lines of inquiry (logs, deploys,
metrics) are opened as facet items and investigated at once, the last facet to finish moves the alert on (the
join), an AI agent summarises it, and it is closed or escalated to the on-call engineer, who handles it or sends it
back for more investigation (the rework loop).

It is the reference model of [docs/MODELLING-WELL.md](../../docs/MODELLING-WELL.md): every part named for what it
is, with a unit and a description; an equation on every flow; one goal per loop; the AI and person steps marked;
the fan-out and the join done inside runs that hold the causing item's lease, so the Process view draws them.
`poor/` is the same workflow modelled badly on purpose, for the guide's side-by-side pictures.

Everything is a stand-in, so it runs anywhere and calls no AI: `bin/step.py` makes up each step's result in a second
or two, and `bin/watch.py` is the pager (an alert every few seconds, and the on-call's answers).

```bash
cp -r examples/alert-triage /tmp/alert-triage && cd /tmp/alert-triage
ergostat run              # then open the Diagram page: Dynamics, Blocks and Process
ergostat check            # after a minute: coherence, every kind
ergostat run --stop
```
