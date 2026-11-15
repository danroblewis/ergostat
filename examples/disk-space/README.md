# A disk kept under 80%

A host's disk (simulated) that the services' logs fill at a steady rate, and a cleaner that
ergostat runs while the disk is over its goal. The smallest loop there is, in one block:
`goal: disk-under-80` on the cleaner means "run while the goal is off, until the disk is back to
65%". ergostat puts the on/off controller in front of it (`keep-disk-under-80`).

- `usage.py` is the sensor: it prints the disk's usage, nothing else.
- `clean.py` is the block: it deletes a batch of old files and prints how many % it freed.
- `logs-written` is a flow nothing in the model sets: a disturbance, judged from the readings.

```bash
cd examples/disk-space
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at (within a minute):

- `ergostat event -n 40`: `loop.off` at 83%, then `block.commanded` and `valve.opened` (5% each)
  until the disk is at 65%, and `loop.holding`; then it fills again.
- `ergostat block` lists `keep-disk-under-80` as implied.
