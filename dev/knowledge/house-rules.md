---
kind: rule
about: how work is done on ergostat, for every agent the factory runs
use: every implementor and reviewer brief
---
# House rules

## Process
- The definition of done is the branch's first commit (`dev/records/<branch>.md`; a branch begun before 2026-11-21
  keeps its `docs/roadmap/overnight/<branch>.md`, and `docs/` is for human readers): the gap, what done means,
  acceptance tests by name, and a size budget (net lines outside tests and docs). After that it changes only by
  appending "Where it stopped". An overrun needs a written reason.
- Done means: the acceptance tests exist and pass; the unit suite and the four browser files pass with rc 0 and no page
  test skipped for want of a port; ruff is clean; `demo_check` passes on any example touched; origin/main merged in and
  the suites run again.
- An independent, deliberately disagreeable review judges the branch against its definition, SPEC and these rules. Two
  failed reviews park the branch with "Where it stopped" saying exactly what is left; nothing partial reaches main.
- Report honestly: what failed, what was not run, numbers that did not improve. A smaller true claim beats a larger one
  a review will knock down (see review-lessons §8).
*About:* goal.first-pass-good, goal.few-fix-rounds.

## Machine
- Suites run one at a time through the shared slot script and under `scripts/suite_watch.py`. Any load test or
  benchmark is watchdogged: kill past 1,500 threads or 6 GB, and cap N. Thread exhaustion has panicked this Mac.
- macOS sandbox profiles: no `syscall-unix` rules; seatbelt filter lists of 5 entries or fewer (kernel panics).
- Never `git stash` (stashes are shared between worktrees). Never kill a process you didn't start; no broad `pkill`.
- To wait for a free machine, match real test processes: `ps -A -o command= | grep -E '^[^ ]*python[0-9.]* -m pytest'`.
*About:* goal.machine-quiet, goal.suite-threads-within, goal.threads-within.

## Code
- Modules small and single-purpose; the disciplines' own terms (system dynamics, control, queueing, process mining).
- No new pages or panels in the UI: show things through the diagrams, the system boxes and the Items tab.
- `docs/` is for human readers; agent material goes in the agent guide and skills. Keep SPEC, the agent guide and the
  gap's entry current with the change: the entry is written as the `## Entry` of its record (dev/records/<branch>.md),
  never in docs/GAPS.md, which the merge queue writes from the records as it lands (a branch editing it is refused).
- AI inside ergostat runs on haiku by default, with its cost recorded.
- Commits end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Outside the machine
- Nothing outward-facing except the gated push of a green, reviewed main. No issues, comments or messages to outside
  services. No secrets printed, logged or copied. No employer names or work-specific content in tracked files.
