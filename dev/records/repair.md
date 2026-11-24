## Entry

section: Running code ergostat does not trust

- **Repair** (SPEC §12r; `docs/roadmap/overnight/repair2.md`): **built on branch `repair2`** (not merged): triage into
  `ergostat.failure` (sealed: M1), the fix by an AI with no tools in a disposable clone with its own `.git` (X1), tested
  in `ergostat.sandbox` (X2, M2, M3; a read-only re-run's hosts GET-only, M6), proposed as `apply-fix` with its impact
  report, the ladder's first rung (a person; a denial final), a daily cap that fails closed
  (M7), and applying by `--ff-only` onto the commit it was made on (M8). M4 is designed away (a fix changes only the
  program). Triage reads Python, Node, Java, Go and Ruby traces and notes an error a good run swallowed (M5) without
  moving any failure, and (`repair-log-events`) the last error-level log line of a good run with no project trace, in
  Python logging's default form or JSON, noted the same way; a Python traceback the tail cut is read from the run's
  own file, its last 64,000 characters (`repair-traces-more`). Done since (`repair-verify`): an applied fix verified
  by `verify` runs of its block begun after it, or regressed by a failed one, and a regressed fix's gated
  `revert-fix` (one `git revert`, aborted and checked when git fails). Done since
  (`ai-approver-for-repairs-needs-a`): the second rung, `approver: ai` (below). *Left*: a daemon's standard
  error is one stream for all its runs, so
  what a daemon swallows is still not seen; a program with uncommitted changes stays refused and is left to a person;
  a Python traceback that begins more than 64,000 characters before the end of the run's own file, and the traces of
  languages not read, still leave a failed run signed by how it ended.
