# This machine, measured for real

Disk use, ~/Downloads and the load, read every 30 seconds and changed by nobody: the sensors only read (`bin/meter.sh`), and the two loops are held by you. ergostat never acts on this machine.

```bash
cd examples/this-mac
ergostat check        # ok, no findings
ergostat run          # prints the page's address
ergostat              # both loops holding, unless your disk is over 90% or ~/Downloads over 500
ergostat run --stop
```

Things to look at:

- `free-space` and `tidy-downloads` are `person` blocks naming their goals: while a goal is off, ergostat asks you (`person.asked` in `ergostat event`) and waits.
- Say what you did: `ergostat block tidy-downloads --done 40 --note "emptied it"` records it as a `valve.opened` on `flow.tidied`; the next reading judges it.
- One agent, `owner` (a person), fills both blocks: the only reason for an `agents:` entry.
- On a tidy machine both goals hold and nothing is asked. To see an ask, run a copy with a tighter `hold:` (say `"<= 0"` on `downloads-tidy`).

Shows: a person filling several loops, read-only measurement.
