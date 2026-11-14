# One program, three roles

A host's disk held under 80% by one Python program that measures, decides and cleans (simulated).

```bash
cd examples/disk-space
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- `ergostat agent disk-cleaner` lists the three roles it fills.
- Its JSON lines are the full protocol: see `ergostat help agents`.

Shows: JSON lines, one agent filling sensor, controller and valve.
