# Branches pruned on a real repository

A developer keeps branching and merging in `work/` (made on first run); a pruner deletes merged branches, woken only by its own loop's crossing.

```bash
cd examples/git-hygiene
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- The pruner has `on = ["loop.off@few-merged-branches"]`: it runs only when the loop goes off.

Shows: real git, event-triggered agents.
