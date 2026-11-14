# A small platform, several systems

One host's disk, the database's backups and a job queue, drawn as overlapping systems with nested outlines.

```bash
cd examples/ops
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- Pick a system at the top of the diagram to draw only its parts.
- Try `ergostat --since 7d` for the weekly view, and `ergostat snapshot` for one HTML file of all of it.

Shows: systems and outlines, a weekly status, snapshots.
