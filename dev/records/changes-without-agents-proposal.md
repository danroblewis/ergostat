# changes-without-agents-proposal: Proposal: changes made by programs, rules and models instead of AI sessions

The owner: "what if we had a system rigorous enough that we no longer need to have the AI agents write code? ... We want to work all workers up the ladder, and we want to decompose our workers and delegate and split." Write `docs/proposals/changes-without-agents.md`.

Settle:
1. The worker ladder (agent, then script, then rules, then a declarative model) as a general core idea: a block's worker can be replaced by a cheaper one once it proves equivalent, and how that equivalence is shown (replaying past items and their recorded outcomes, shadow runs, agreement rates).
2. Which kinds of change can become data instead of code (dashboards, panels, workflows, thresholds, saved queries), and what the core needs for that.
3. Program-made code: conflict resolution in generated and append-only files, codemods and templates for repeated shapes, generation from declarations (schemas, routes, docs, test scaffolds).
4. Mining the record: how to find recurring change shapes from past merged gaps and their diffs, and how much of the recent work they cover. Measure it on a copy of this factory's record and state the share.
5. Routing: how an item is sent to the cheapest worker able to do it, with the agent as the fallback.
6. The minimum time from request to main for each lane, with numbers.
7. The build split: the gaps that follow, smallest valuable first (the merge-conflict resolver is the likely first).

Definition of done.
1. The proposal settles all seven with numbers from the record where it claims them.
2. At least one shape is shown end to end on recorded examples: the program's output against what the agent produced.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: written. `docs/proposals/changes-without-agents.md` settles the seven (§1–§7). No code changed (0 net lines).

- Done 1: each of the seven is settled, with numbers from the clone's git history (from 2026-11-21: 442 landed
  gaps, 769 merges of main into a branch, 818 hand resolutions in 395 of them). The share asked in item 4 is stated:
  no landed gap was of a shape a program reproduces whole; 26 of 442 (6%) were prose only, 50 (11%) changed no code
  outside tests; the two declared merge rules finish 55 of 395 conflicted merges (14%) and take 142 of 818 hand
  resolutions (17%). The page's *How each count was taken* gives each listing and search.
- Done 2: merge `dc3f5c13` (`tests/test_graph_cli_web.py`) shown end to end: the agent's 59 lines against the union
  rule's, and what landed; and `7ef0407c` (`docs/GAPS.md`) as the case the generated rule exists for. The union's
  output is read from git's combined diff of the three versions, not run: `git merge-file --union --object-id
  08aee01c:tests/test_graph_cli_web.py 278f54a4:tests/test_graph_cli_web.py b9341591:tests/test_graph_cli_web.py`
  was refused in this session. The first build gap's `test_union_matches_recorded_merge` is the machine check.
- Done 3: two owner's questions, each one sentence, with the default until answered.
- Decisions taken alone (each the reversible one, listed in the proposal): the window is the days the records exist;
  promotion is the owner's edit unless declared; the union rule only for test files at first; the resolver runs
  before the session, never over an agent's resolution.
- Not measured: request-to-definition time and the push wait (the live record's `in-open-hours`, `in-ready-hours`,
  `gate-push-wait-minutes`), and the session minutes the resolver saves; the live instance was not read. Also refused
  here: `git version`, and `git rev-list --count ... --grep=^#.Conflicts: --all-match HEAD` (counted from `git log`
  output instead).
- No test, page or example changed, so only ruff was run.

## Entry

section: The factory (ergostat on ergostat)

- **Changes made by programs, rules and models instead of AI sessions** (done as a proposal, on
  `changes-without-agents-proposal`; `docs/proposals/changes-without-agents.md`): the ladder made general (a block's
  cheaper candidate run in shadow, replayed on the record and promoted on its outcome-checked agreement, reusing
  repair's promotion rule); which changes become data (dashboards, thresholds and workflows are already; measures as
  queries and any model edit through Accept are not); conflict resolution by declared file classes (generated,
  union), measured on the factory's history: 395 of 769 merges of main into a branch needed a hand resolution, and
  the two rules finish 55 of them; one merge shown end to end; routing by states with an abstain outcome; the time
  to main per lane. *Left*: the seven build gaps of its §7, not yet filed (the merge resolver first); two owner's
  questions (promotion by the owner's edit or by itself; model edits as data instead of gaps).
