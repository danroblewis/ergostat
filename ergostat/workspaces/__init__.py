"""Workspace pools (SPEC §12k): the directories AI blocks' runs work in, one per item. A pool hands an item's run a
workspace (``pool.acquire``), the same one again on a retry, and takes it back when the item's lease ends
(``pool.release``): kept for the item while its work is under review, cleaned when it finishes, quarantined when it is
found dirty or broken. Each workspace is an item, ``ergostat.workspace/POOL-N``, folded from its events; the record is
the only store. How a workspace is made is the pool's backend: ``git.py`` (a worktree on the item's own branch) is the
first."""
