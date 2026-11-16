# Branches pruned on a real repository

A developer keeps branching and merging in `work/` (made on first run, and the only place any git command here runs); a pruner deletes merged branches, run only while its goal is off.

```bash
cd examples/git-hygiene
ergostat check        # ok; one finding: the developer acts on its own (it is the load)
ergostat run          # prints the page's address
ergostat event -n 40  # loop.off, block.commanded, valve.opened, loop.holding
ergostat run --stop
rm -rf work           # the scratch repository, when you are done
```

Things to look at:

- `delete-merged` names its goal (`goal: few-merged-branches`): it runs when the fourth merged branch appears, deletes all but the newest, and the goal holds again. Nothing runs it on a timer.
- The developer moves two flows, so it says which with JSON lines (`{"out": "flow.merged", "moved": 1}`), and adds `branch.started` / `branch.merged` events.
- Items: each branch (`branch/feature-…`), `open` when started, `merged`, then `deleted` by `prune.sh` (`branch.deleted`). The stocks still count what git says.
- Every script refuses to run unless `work/` is a repository of its own; `prune.sh` uses `git branch -d`, which deletes only merged branches.

Shows: real git, a block run by its goal, a block with two outputs.
