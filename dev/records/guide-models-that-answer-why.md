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

## Where it stopped

Built in round 1 (about 55 net lines of code outside tests, docs and dev):

- `docs/AGENT-GUIDE.md` §3l, *Why isn't this done*: what the question needs from a model (honest and finished
  states, relations, who or what takes each state, people, gates, pools, leases with a `budget:`, sensors of the real
  state, timestamps), outside work brought in read-only, to-dos, access-context batches and stakeholder updates, a
  worked example from a described process to its model, and the check. The `ergostat-author` skill sends every agent
  that sets up or changes item kinds to it. SPEC §5a, *What the model must say for why*, says the rules.
- `check`'s `wait-unexplained` (`ergostat/spec/waits.py`, a finding): a kind with no precedence relation and a state
  its items rest in, unfinished, that no block takes and where no one is named (its first state, or one no event
  moves an item out of).
- `ergostat/why/blocks.py`: a working state's owner is whoever records the move to its next state (before a side exit
  or a move back), not the first event by name. Without it the worked example's review said "whoever records
  change.dropped", so the guide's answer would have been wrong; it is three lines, and no earlier test pinned the old
  order.
- `tests/test_why_guide.py` (10 tests): the scripted acceptance (the guide's model read from the guide, three stalls
  seeded: a dependency chain to a change on hold, the build gate shut by its sensor, a dead lease holding the
  releaser's pool; `why` names each true root and `held-up` lists them with no unknown); every command in the section
  run in order with rc 0, with the to-do and batch answers checked; every inline command matched to one that runs;
  the finding found and not found as its rule says; no shipped example has it. Break-tested once, both breaks together: with
  the finding's call removed and the owner order put back to by-name, three tests fail (the finding's test, and the
  two that read the owner).

Choices made with nobody to ask, each the most reversible:

- "A fresh agent given only the guide": no agent session was run (no network here). The acceptance runs the guide's
  own worked model, as a fresh agent following it would write it. A run with a real agent (for example as a request
  in `scripts/authoring_bench.py`) is not done.
- "`todo`" is read as a kind the owner declares, not a command: ergostat ships no unit of work (invariant 12), and no
  `todo` command exists. Stakeholder updates are to-dos with a non-precedence `covers` relation, written from `why`'s
  summary.
- The finding judges only kinds whose finished states `messages: done:` declares: with them inferred from the record
  the model cannot say which states finish (on the shipped examples the wider rule fired on cyclic kinds, such as a
  page that goes current and stale, that are never done). "No owner" is read as no event moving the items on, since
  the model has no other owner of a state. A kind with a precedence relation is not found even when its first state
  is untaken (the definition's three conditions together); `why` then says `nothing` for the chain's bottom item, and
  the guide's check catches that.
- A gate whose every input reads 0 is said by `why` as `closed` (held), not `gate`; the acceptance takes either, since
  the root (the gate, the factor at 0, what sets it) is the same.

Not run here: the whole unit suite and the four browser files (the factory runs them). Run here, each passing:
`tests/test_why_guide.py`, `tests/test_why.py`, `tests/test_held_up.py`, `tests/test_spec_items.py`,
`tests/test_chains.py`, `tests/test_dashboards_doc.py`, `tests/test_item_about.py`, `tests/test_faults_healthy.py`,
`tests/test_coherence.py`; ruff clean. No example touched, so no `demo_check`. `main` is the branch's base, so the
merge of main is empty. Commands refused in this session: running `ergostat` directly and Python heredoc scripts
(`uv run ergostat -C /tmp/w1 ...`, `python3 - <<'EOF'`), and `ls examples`; worked around only by running the same
through the test file.
