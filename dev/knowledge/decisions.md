---
kind: decisions
about: the owner's standing product decisions that a change must respect
use: implementor and reviewer briefs, when the gap touches the area named
---
# Decisions

- **One model, three drawings.** Dynamics (system dynamics), Blocks (control), Process (process map) stay separate,
  each in its discipline's traditional style. New ideas are shown by modelling them, not by new UI.
- **Interventions are evidence of missing loops.** Alerts, approvals and notifications are counted as a stock that
  should trend down; suppressing one is never counted as a fix, and a temporary rise while a loop is built is fine.
- **Human approval is for a system's early stages.** The approval ladder moves classes from a person to AI to a
  program as their record earns it. An AI approver needs a sound positive allowlist of what it may approve (a
  denylist guard was bypassed).
- **Model changes are judged, then reviewed.** The judge tests by the record; structure and redesigns also get a
  reviewer's reading. Nothing structural is written without approval unless the owner names the class `auto`.
- **Redesign runs on its own,** one system at a time, bounded by rests, turns and a daily cap that fails closed.
- **Honest numbers over flattering ones.** Projections say "low confidence" when the model fits badly; benchmarks
  report what the evidence supports.
- **Daemons over a process per item** where a program stays up; the AI steps stay one process per run so their cost
  is measured per run.
- **The factory starts small.** One implementor, one reviewer; pools rise only after a streak of good results.
- **Security effort goes where code nobody vouched for runs** (the sandbox, repair). For the owner's own tooling,
  review for correctness and these rules rather than hardening.
