# redesignbench: where the redesigner learns what to design

Branch `redesignbench`, from origin/main at fdf83b9.

**The owner's question:** "Where would the redesigner learn what it should be designing? How would it learn the
better things to add?" The agreed answer has three parts.

## 1. A benchmark

**Done when** `scripts/redesign_bench.py` takes models of known structure (the cases in `tests/redesign_cases/`),
removes a piece of each, makes the record from the full model (the recovery benchmark's truth run, `bench/truth.py`),
asks the redesigner (`numbers/redesigner.run`, nothing submitted) to repair the cut model, and scores each case: the
missing structure **found** (a structural match against the case's `expect`, by stocks' places and equation shapes,
never by the names the redesigner chose; a renamed stock followed by its `formerly:`), the **fit** before and after
(the scorecard's, like for like), whether its best change set **compiled**, the scorecard's **verdict**, and the
**cost** (calls, tokens, dollars, seconds). At least six cases: a capacity limit removed (a ticket-factory-like
queue), a rework loop removed, a delay removed, a goal (a balancing goal gap) removed, a stock merged into its
neighbours, an outflow missing. It runs on haiku by default with a total cap per run (`--cap`, $3), stops starting
cases once the cap is spent, and has `--stand-in`: a deterministic answer per case (the known repair, and for one
case nothing), so CI checks the harness with no AI. It prints a table and appends one JSON row per case (with the
run's label, the git commit and the settings) to a results file (`docs/redesign-bench.jsonl`), so changes to the
redesigner can be compared.

## 2. The redesigner's memory

**Done when** the redesigner's prompt has a section *What was proposed before for this system*: the past redesigns
of that system (newest first), each with its title, its summary, its edits' whys (cut), what became of it (proposed,
judged better or not with the scorecard's verdict and why, refused with why, accepted, dismissed with the owner's
reason, superseded) and any note; and the other changes the owner dismissed with a reason about its parts. Bounded
by count (`MEMORY_MOST`, 6) and characters (`MEMORY_CHARS`, 3,000). The guide says: never propose again what was
dismissed or judged not better, unless the record has changed in a way that answers the reason given.

## 3. Interventions as evidence of missing loops

**Done when** the prompt has a section *Interventions: evidence of missing loops*: the interventions (SPEC §12p:
held actions, a person's requests, advised commands, alarms, step tests, changes the owner decided) relevant to the
system, grouped by class with their count, cause, how they were answered and the notes given with the approvals or
denials; and the open modelling requests of the interventions loop (`inbox --requests`) for it, with their cause,
remedies and the notes given when they were worked on. Relevant means the class's cause names a part of the system
(a block, a goal, a stock it watches) or, for the whole model, everything. Bounded by count and characters as the
memory is. The guide says to read each as a loop the model lacks and to answer it with structure when the record
supports it.

## Then

Run the benchmark on haiku (capped at $3 a run) with the harness alone (before 2 and 3) and after them, the cases
seeded with the same history and interventions both times, and report the table: honest numbers, even if the gain
is small.

## Acceptance tests

- `tests/test_redesign_bench.py::test_the_stand_in_run_finds_each_repair_and_scores_the_harness`
- `tests/test_redesign_bench.py::test_a_structural_match_follows_renames_and_ignores_names`
- `tests/test_redesign_bench.py::test_the_cap_stops_new_cases_and_rows_are_appended`
- `tests/test_redesign_memory.py::test_the_memory_says_each_past_redesign_and_its_verdict`
- `tests/test_redesign_memory.py::test_the_memory_is_bounded_by_count_and_characters`
- `tests/test_redesign_memory.py::test_interventions_are_selected_per_system_with_their_notes`
- `tests/test_redesign_memory.py::test_the_prompt_carries_the_memory_and_the_interventions`

## Docs

SPEC §12e (*Redesign*: the memory, the interventions, the benchmark), the redesigner's guide
(`library/templates/modelling/redesigner.md`), `docs/AGENT-GUIDE.md`, and `docs/redesign-bench.md` (running it).

## Size budget

500 net lines outside `tests/`, `docs/` and the cases.
