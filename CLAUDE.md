# Rules for working on ergostat

Ergostat keeps work going. It is a tool for drawing a control-system boundary around whatever
someone wants to keep working, and for designing, seeing and running the control system inside it.
The settled terms are in `NOTES.md`; read it first.

This project is at the design stage: there is no code and no spec yet. Build only what the owner
asks for. A question about what a user would want first is a discussion, not a request to build it.

## Invariants

These must not be broken without the owner's agreement, recorded in `NOTES.md` and said in the
commit.

1. **Work, not tasks.** Ergostat knows work: change in the world over time, seen as stocks and
   flows. It has no concept of task, ticket, issue or job, ships no unit of work, and treats none
   specially. Users build their own units of work as items.
2. **Three roles.** The control system is made of **sensors** (measure, never act),
   **controllers** (decide, to hold a setpoint) and **valves** (act). Nothing changes the world
   outside ergostat except through a valve.
3. **Agents fill roles; they are not roles.** An agent is whatever acts on the owner's behalf: a
   person, an AI agent, a narrow AI agent, a decision, a program or a rule. One agent may fill many
   roles. Filling a role never changes the role. Adding a role is designing the system, done by the
   owner or by the Supervisor on their behalf.
4. **Every agent shows its rung.** Never just "agent": always its kind (person, AI, narrow AI,
   decision, program, rule). A role whose agent is gone is retired, and that is shown as a success.
5. **The refactor path is the expected direction.** Roles start with the universal AI agent and
   move down the ladder, toward programs, rules and finally no work at all. The design must make
   each step visible and possible.
6. **Every agent is held to the same discipline**: measured, bounded, and acting only through
   valves the owner grants, whether it is a person or an AI.
7. **Disturbances are modelled.** A disturbance is an input no valve controls, measured or
   estimated. A residual (what the model fails to explain) is evidence, never silently ignored.
8. **One control system.** The diagram is one system that can be panned, zoomed and grouped.
   Disconnected parts are found by graph analysis, never separated by declaration.
9. **The diagram is primary.** Control-theory diagrams are a first-class part of the product, not
   an export. Everything else supports them.
10. **Events and metrics are kept apart.** Events (what happened: append-only, never edited) and
    metrics (time series: many, cheap) live in separate stores. Items are folds of events by id,
    rebuilt from the record.
11. **Defined and inferred stay distinguishable.** Everything in the model says whether it was
    declared or inferred from data, so that discovery can be added later without rewriting what
    people declared.
12. **Ergostat adds nothing of its own accord.** No built-in agents, no built-in units of work, no
    roles it was not asked for. An empty install runs nothing.

## Words

Use the terms in `NOTES.md` and no others for the same things: work, item, sensor, controller,
valve, disturbance, residual, agent, rung, retired, owner, Supervisor. Never "task", "worker" or
"machine" for these.

## Working here

- The repository is local only: no remote, never pushed.
- Never write an employer's names (systems, services, metrics, labels, ticket types, people) into
  tracked files; use generic stand-ins.
- Commit only when the owner asks. End commit messages with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
