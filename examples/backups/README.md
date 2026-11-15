# Backups and off-site copies

Two loops on a simulated database (one simulated hour passes every two seconds):

- **backup-fresh**: the newest backup's age grows by a declared rate (`time-passing`, nothing
  runs it). When it is over a day (past 26h, with the tolerance), ergostat runs `backup-job`,
  which resets the age (`backed-up`) and adds one copy to send (`new-backups`): one block, two
  flows, reported as two JSON lines.
- **offsite-current**: when more than one copy is waiting, ergostat runs `offsite-sync`, which
  copies one per run.

The backup job is one loop's valve and the other loop's disturbance: each backup it takes makes
the off-site goal harder. Both loops are `goal:` on the block that acts; the sensors
(`age_check.py`, `offsite_lag.py`) only print their reading.

```bash
cd examples/backups
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at (the first backup is after about 12 seconds, then about every 52):

- `ergostat event -n 40`: `loop.off` on backup-fresh, `block.commanded` backup-job, two
  `valve.opened` (the age it removed, and one new backup), `loop.holding`. After the second
  backup, offsite-current goes off and one copy is sent.
- `ergostat block` lists the two implied on/off controllers, `keep-backup-fresh` and
  `keep-offsite-current`.
