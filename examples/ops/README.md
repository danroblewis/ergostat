# A small platform, several systems

One host's disk, a job queue and the database's backups, one file each (`host.yaml`,
`jobs.yaml`, `backups.yaml`, included from `ergostat.yaml`; each file's `defaults: system:` puts
its parts in its system). They overlap where the job workers' logs fill the host's disk.

Four loops, all simulated in one shared `.sim.json`:

- **disk-under-80** (host): `goal:` on the cleaner; it runs while the disk is over, down to 65%.
  The worker pool's logs are its disturbance.
- **queue-short** (jobs): not on/off. The `autoscaler` is an `expr` block that sizes the pool
  from the backlog (one worker per 5 jobs, 1 to 8); `pool.py` reads `command.amount` as the
  workers to run, and moves two flows: jobs done, and logs written to the disk.
- **backup-fresh** and **offsite-current** (backups): the same as `examples/backups`.

```bash
cd examples/ops
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

`check` reports one finding, and it is meant: `users` (a stand-in for the users, a burst of 30
jobs every 30 seconds) moves `jobs-arriving` on its own schedule, an open loop.

Things to look at (all four loops go off and come back within 90 seconds):

- `ergostat event -n 100 | grep -E 'loop|commanded'`: queue-short goes off at each burst and
  the autoscaler's command (the workers) rises with the backlog; the disk goes off as the logs
  fill it and is cleaned; a backup every 52 seconds, and a copy sent off site after the second.
- `ergostat block` shows the autoscaler next to the three implied on/off controllers.
- Pick a system at the top of the page's diagram to draw only its parts.
