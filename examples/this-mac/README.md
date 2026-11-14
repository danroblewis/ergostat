# This machine, measured for real

Disk use, ~/Downloads and the load, read every 30 seconds and changed by nobody: the loops are held by you, with manual valves. It only reads.

```bash
cd examples/this-mac
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- One agent (you, the owner) fills two controllers and two valves.
- Record what you did: `ergostat valve tidy-downloads --opened 40 --note "emptied it"`.

Shows: a person filling several loops, manual valves, read-only measurement.
