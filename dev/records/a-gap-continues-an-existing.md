## Entry

section: The factory (ergostat on ergostat)

- **A gap continues an existing branch, with main merged in by the factory** (awaiting its gate; branch
  `factory/continue-branch3`, the salvage of `continue-branch`; its definition is
  `docs/roadmap/overnight/continue-branch.md`, and `continue-branch2.md` and `continue-branch3.md` hold where the later
  rounds stopped). A request may name `continues: <branch>`;
  implement.py merges origin/main before each session (a clean merge committed by the program, a conflicted one handed
  to the session with its conflict list), and gate 1 reads the continued branch's own definition and holds it to the
  main merged at its build. Main (1f013ba) is merged into the branch. Left: the factory's fast suites on the merged
  tree, and gate 1 for this salvage, which the coordinator judges by hand (its first commit is continue-branch.md).
