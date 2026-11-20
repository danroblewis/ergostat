---
kind: decisions
about: the owner's standing product decisions that a change must respect
use: implementor, reviewer and planner briefs, when the gap's text names one of a decision's areas
---
# Decisions

- **One model, three drawings.** Dynamics (system dynamics), Blocks (control), Process (process map) stay separate, each
  in its discipline's traditional style. New ideas are shown by modelling them, not by new UI. *Areas: diagram, view,
  page, panel, ui, layout, drawing.*
- **Interventions are evidence of missing loops.** Alerts, approvals and notifications are counted as a stock that
  should trend down; suppressing one is never counted as a fix, and a temporary rise while a loop is built is fine.
  *Areas: intervention, alert, approval, notification, inbox.*
- **Human approval is for a system's early stages.** The approval ladder moves classes from a person to AI to a program
  as their record earns it. An AI approver needs a sound positive allowlist of what it may approve (a denylist guard was
  bypassed). *Areas: approval, approver, ladder, allowlist, gate, guard, inbox.*
- **Model changes are judged, then reviewed.** The judge tests by the record; structure and redesigns also get a
  reviewer's reading. Nothing structural is written without approval unless the owner names the class `auto`. *Areas:
  modelling, judge, improver, redesign, redesigner.*
- **Redesign runs on its own,** one system at a time, bounded by rests, turns and a daily cap that fails closed. *Areas:
  redesign, redesigner.*
- **Honest numbers over flattering ones.** Projections say "low confidence" when the model fits badly; benchmarks report
  what the evidence supports. *Areas: projection, estimate, benchmark, confidence.*
- **Daemons over a process per item** where a program stays up; the AI steps stay one process per run so their cost is
  measured per run. *Areas: daemon.*
- **The factory starts small.** One implementor, one reviewer; pools rise only after a streak of good results. *Areas:
  factory, pool.*
- **Security effort goes where code nobody vouched for runs** (the sandbox, repair). For the owner's own tooling, review
  for correctness and these rules rather than hardening. *Areas: sandbox, repair, security, guard, container.*
