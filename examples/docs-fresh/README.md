# Docs kept in step with the code

Developers merge changes, and each can make a page stale. A cheap decision (`page-picker`)
decides how many pages to rewrite and which first, and commands an AI session (`doc-writer`,
simulated by `writer.py`) that rewrites at most two pages a run. Each rewrite is a pull request,
so it waits for a person (`mode: advise`).

```bash
cd examples/docs-fresh
ergostat check                       # ok; one finding: developers act on their own (the load, intended)
ergostat run                         # prints the page's address
ergostat block doc-writer --approve  # approve the rewrite the picker asked for (again for each one)
ergostat event -n 60                 # loop.off, block.advised, block.commanded, valve.opened, loop.holding
ergostat                             # what needs attention
ergostat run --stop
```

Things to look at:

- The picker reads the goal's error and the measured rate of code changes (`flow.code-changes`):
  feedforward. It asks for one more page when the code is changing fast.
- `block.commanded` shows what was asked and what the writer's `max: 2` allowed: saturation.
- Without approvals the goal stays off: the loop is closed through a person.
- The Agents page puts each machine on the ladder: the writer (ai), the picker (`kind: decision`).

Items: each doc page (`page/api/auth.md`), recorded `stale` by the scanner when a change
outdates it and `current` again by the writer, with its PR.

Shows: an AI block driven by a decision block, feedforward, `max`, advise mode.
