# Known gaps

What ergostat is known to lack, kept current as work lands. Each entry says where it came from and its
state: **open**, **in progress** (with the branch), or **done** (with the commit, then removed at the next
review). Newest decisions from the owner first within each section.

## Remote systems and libraries

- **Remote systems** (in progress, `remote`): a system run by another ergostat instance, composed into a
  local model. Its model is served by the remote instance and changes while it runs; its event log and
  metrics are queried where they live; its agents run on the remote machine, never locally. The local model
  reads it, links to its parts, and draws it as a subsystem; it never runs it. (Owner, 2026-11-18.)
- **Shared libraries** (open): templates and reference models shared between projects and people, by git URL
  or package, with versions, bringing their own scripts. For people modelling their own real systems.
- **External event logs** (open): systems that keep their own event log (Kafka, a ticket history, an incident
  log): copy in (works today through collectors), read in place, or mirror with a cursor that cites the
  original. Remote systems are the first case of reading in place.
- **Identifying existing controllers** (open; `docs/proposals/external-systems.md`): an autoscaler or alert
  rule modelled from its record.

## Modelling

- **One-line modelling loop** (open): `use: modelling` instead of about 150 lines copied into each example; a
  model built by an agent gets the improvement loop by default.
- **Built-in join** (open): move a parent item once all its sub-items reach a state (fork-join); today it
  takes a join block or an auxiliary.
- **Triggers on an event type** (open): a block started by an event type alone, not only by a state change.
- **Closed-loop simulation** (open): projection holds blocks still; simulating with the controllers running.
- **Operating modes, regime-scheduled thresholds, interlocks, risk gating** (open; designed in
  `docs/proposals/coordinator/08-modes-and-protection.md`).
- **Observer staleness and estimated stocks** (open; `coordinator/06-observer.md`).
- **Per-item and per-kind goals** (open).
- **Finding structure from residuals** (open; porting SD Lab's Kalman-LNA work; `parity/00-modeling-review.md`).
- **Proposals drawn dashed in both diagrams; proposals that state the behaviour they predict** (open).

## Runtime, scale and latency

- **Event-driven counts, a scheduler instead of a thread per reading, evaluation of what changed** (in
  progress, `scale2`). The old design kernel-panicked the machine at 14,000 threads.
- **Latency: push intake, notify-on-write, a local socket for calls from steps** (in progress, `latency`).
- **Warm workers instead of a process per item** (open; designed in the latency work).
- **What each run costs** (done on branch `runcost`, e26fcf4 and 4b39f0f, not merged yet): per run, its AI sessions' dollars (reported by Claude Code, or
  estimated from tokens), tokens and model, the CPU time and peak memory of its process tree (one shared sampler and
  its wait status), wall time and exit; series per block, `ergostat.cost.*` measures a goal can hold, the Agents page
  and `ergostat agent NAME`. Network bytes per process are left out (macOS has them only through `nettop`).
- **Extreme-conditions tests and calibration per part of the model** (open; the Check page's first status
  takes 13 s even on small models).
- **An engine per system; line routing for large diagrams** (open; `docs/proposals/scale.md`).
- **The IR and a Rust runtime** (open; `docs/proposals/ir-and-runtime.md`, 12 questions for the owner).
- **Should a run whose lease expired be killed?** (open question for the owner).

## Bugs

- **YAML 1.1 readings** (open): `9:30` is read as 570, `010` as 8, `1e3` as text; `check` should warn and the
  format should pin one YAML version.
- **`where:` compares strings** (open): a field holding `1.0` does not match `1`.
- **Listing projects writes `repo.json` into other projects' state folders** (open).
- **`try_use` trials can leave Claude sessions running** (open).
- **Three tests fail only under heavy load** (open): `test_a_selection_is_model_parts_and_survives_switching_view`,
  `test_a_page_left_open_does_not_grow`, `test_a_lease_held_by_a_run_survives_a_model_edit`.

## Interface

- **Process view: drag, pin and re-route** (in progress, `procdrag`).
- **Dark theme: the lighter correspondence colours are low in contrast** (open).

## The owner's work setup

- **A "report upstream" channel for the work agent** (open): scrubbed GitHub issues, filed only after the
  owner approves. The `ergostat` repository is public, which this depends on.
- **Remodel `the-job`** (open): equations, designed control laws, person steps marked, the coordinator's
  structure and behaviour tests.
