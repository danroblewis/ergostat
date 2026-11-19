# architecture: the computed measures of a system architecture review

Branch `architecture`, from main at 2ed2f16. The owner's request: when models get large, ask the hard questions
(are large systems several smaller ones, should small ones merge, are the interfaces rational, what systems should
we have for what we are trying to do), with the methods system dynamics and control engineering use for very large
systems, computed where possible: the computed measures are the rule rung of the ladder; AI comes later. This
branch is the design doc and the computed rung. The per-system redesign and the daily larger-model review (GAPS'
`architecture` entry, after `redesign`) are not in it.

## Done when

`docs/proposals/architecture.md` grounds each method in its source, briefly (design structure matrix and
modularity clustering; time-scale separation, singular perturbation and hierarchical control; the relative gain
array; loop dominance and eigenvalue elasticity; interface control documents; the boundary chart and subsystem
diagram, Sterman ch. 3; purpose and goal traceability; Beer's Viable System Model as a checklist), and for each
says what ergostat computes today from the model and the record, what it cannot, and how the finding reads.
`check` reports five new notes (level `note`, never errors), worked out from the structure alone, with no run:
`system-splits` (a system, or a model with no systems, of 20 parts or more whose part graph falls into two or more
clusters, greedy modularity clustering with clusters joined by more than a tenth of the smaller's links merged, at
modularity 0.4 or more; the clusters named; a system whose subsystems are the clusters is said to be independent
systems held in one), `systems-merge` (two sibling systems with at least 3 links between them and at least as many
as inside the smaller), `interface` (per boundary, what crosses it by kind, said when material crosses through
clouds on both sides in one unit, a block outside moves or commands what the system's own goals' loops use, or 10
or more information links cross it), `time-scales` (within a system, its own parts' time constants, from one
evaluation of the equations at the model's start and the goals' identified processes, with a gap of more than 10x
between neighbours: the fast and slow parts named), and `purpose` (in a model with systems: a system with no
description, a described system with no goal inside it, and goals in no described system when the model has no
`purpose:`; a model-level `purpose:` key, main file only). Each system's size (parts, feedback loops inside and
through it, levels of systems within it) is in `explain` (the model's list of systems and `explain system.NAME`) and
in the system's panel on the Graph and Dynamics pages (one row, no new panel). SPEC (§4a, §12) says so. The measures
run on every example in well under half a second each. Part 3's report (findings per example, whether the-job is
flagged as several systems) is in the proposal, under "What the examples say".

## Acceptance tests

- `tests/test_architecture.py::test_a_system_of_two_clusters_is_said_to_split_naming_them` (and a cohesive chain is
  not)
- `tests/test_architecture.py::test_a_system_of_independent_subsystems_is_said_to_be_several`
- `tests/test_architecture.py::test_two_chatty_systems_are_said_to_merge`
- `tests/test_architecture.py::test_a_ten_times_gap_in_time_constants_is_a_candidate_for_a_hierarchy` (and a 5x gap is
  not)
- `tests/test_architecture.py::test_a_bad_interface_is_flagged` (clouds on both sides, a reach-in, a wide interface;
  a clean one is not)
- `tests/test_architecture.py::test_purpose_names_systems_without_one_and_goals_traced_to_none`
- `tests/test_architecture.py::test_a_purpose_belongs_to_the_main_file`
- `tests/test_architecture.py::test_system_size_in_explain_and_the_panel`
- `tests/test_architecture.py::test_the_clean_examples_have_no_architecture_notes_and_every_example_is_fast` (no
  notes on backups, coordinator, disk-space, file-queue, first-loop, git-hygiene, ops, plain-crontab,
  software-factory, talking-scripts, this-mac, ticket-factory; under 0.5 s on every example)
- the four suites, rc 0, no page test skipped; `demo_check` on the examples touched (none expected).

## Size budget

600 net non-test lines (outside `tests/` and `docs/`); expected about 300.
