# daemon-demo

Jobs worked by one long-lived program, eight at once, instead of a process per job; and the finished jobs counted
by a second long-lived program, instead of a process per reading. `docs/DAEMONS.md` walks through both, and these
files are its examples, word for word.

- `bin/arrive.sh`: a stand-in for the outside, run every five seconds, opening one job that takes 1 to 4 seconds.
- `bin/worker.py`: the `worker` block's daemon. It works each job on a thread of its own, in a process of its own
  with the job's `ERGOSTAT_*` values, honours a cancel, and sends a heartbeat.
- `bin/count-files.sh`: the `finished` stock's sensor daemon, counting the files in `done/` with no process started
  per reading.

`ergostat run`, then the Agents page: the two daemons, each one process, however many jobs and readings.
