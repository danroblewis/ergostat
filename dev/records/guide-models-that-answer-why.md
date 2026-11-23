# guide-models-that-answer-why: teach agents to build models that can say what is holding work up

The owner, 2026-11-22: when "why isn't this done?" lives in a work instance, as model configuration and scripts, "we should have some sort of documentation or guidance for the AI agents that manage and set up the system model and scripts, they should understand how to create the resources and manage the system so that it is able to answer these questions."

Change: a new section of `docs/AGENT-GUIDE.md` and a reference in the `ergostat-author` skill, which every agent setting up a model reads:
- What the question needs from a model: item kinds with honest states and finished states, `depends_on` and other relations, who or what takes each state, owners and people as blocks, gates, pools, leases, sensors of the real external state, and timestamps.
- How to bring in outside work (tickets, pull requests, alerts) so its waiting is visible, read-only by default.
- How to set up personal to-dos with `todo`, access-context batches and stakeholder updates.
- A worked example from a described process to a model that answers.
- **The check:** how the agent verifies its model. For each unfinished kind, run `ergostat why` and `ergostat held-up`, and treat "cannot tell" as a modelling gap to fix.
- Add a `check` finding for a kind whose waiting cannot be explained (no relation, nothing takes a state, no owner).

Definition of done: a fresh agent given only the guide and a described process builds a model on which `why` names the true root for three seeded stalls (run as a scripted acceptance on an example). Every command in the section is run by a test. No organisation's names.
