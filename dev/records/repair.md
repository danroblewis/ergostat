## Entry

section: Running code ergostat does not trust

- **Repair** (SPEC §12r; `docs/roadmap/overnight/repair2.md`): **built on branch `repair2`** (not merged): triage into
  `ergostat.failure` (sealed: M1), the fix by an AI with no tools in a disposable clone with its own `.git` (X1), tested
  in `ergostat.sandbox` (X2, M2, M3; a read-only re-run's hosts GET-only, M6), proposed as `apply-fix` with its impact
  report, the ladder's first rung (a person; a denial final), a daily cap that fails closed
  (M7), and applying by `--ff-only` onto the commit it was made on (M8). M4 is designed away (a fix changes only the
  program). Triage reads Python, Node, Java and Go traces and notes an error a good run swallowed (M5) without moving
  any failure. Done since (`repair-verify`): an applied fix verified by `verify` runs of its block begun after it, or
  regressed by a failed one, and a regressed fix's gated `revert-fix` (one `git revert`, aborted and checked when git
  fails). Done since (`ai-approver-for-repairs-needs-a`): the second rung, `approver: ai` (below). *Left*: log
  events; the ladder's lower rungs (program, rule) and promoting a class automatically; a program with uncommitted
  changes is fixed from its committed text; a Python traceback more than 8,000 characters before the end of a failed
  run's output is now signed by how the run ended; a daemon's run hands back little or no standard error, so what a
  daemon swallows is not seen; Ruby and other languages are not read.
