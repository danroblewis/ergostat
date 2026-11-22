# repair-verify: an applied fix verified by the runs after it, and its revert offered

The definition of done is `dev/records/repair-verify.md`; what the loop does is SPEC §12r (*Verifying*, *Reverting*).

What changed for the owner:

- An applied fix is no longer left as "applied" for good. `repair-settle` counts the runs of the failing block begun
  after the fix (by the record's order, not its clock). After `verify` of them finish well (3 by default, 1 to 50) the
  failure is **verified**: those runs went well, which is all it claims. A run that fails in a way the code may be to
  blame for makes it **regressed**.
- A regressed fix asks you, in the inbox, for the gated action `revert-fix`: "Approving reverts the applied fix COMMIT
  in your repository with one new commit (git revert); the program goes back to what it was before the fix." Approved,
  it reverts with one commit; refused by a dirty tree, a revert already in progress, or git failing, it says why and
  leaves your repository as it was (a failed revert is aborted and checked). Denied, the failure stays regressed for
  you to handle.
- A failure that comes back after it was verified is opened again, its last verdict cleared; one that comes back while
  the fix is being verified is counted, and judged by settle.
- Any gated action that runs past its timeout now has its whole process group killed, not only its shell.
