# suites-copy-their-checkout-into-the-container: the queue's suite containers read a copy, not the Mac's folder through Docker's file sharing

depends-on: []

On 2026-11-22 Docker Desktop's virtual machine (com.apple.Virtualization.VirtualMachine) held about 204,000 open files after 2.5 days, growing by roughly 30,000 an hour while the merge queue ran: its file sharing (virtiofs) keeps a handle on every file a container reads through a bind mount, even after the folder is deleted. Its per-process limit is 245,760; at 10:05 the engine's own sensors failed with ENFILE, and the coordinator had to restart Docker Desktop (10:17), which also restarts the owner's own containers. The merge queue's suites (`dev/bin/agents.py` `queued()`, `-v {work}:/work`) read the whole checkout, thousands of test files, about every ten minutes; session containers (`run_args`) bind-mount their clone the same way.

## Definition of done
1. A queue or triage suite container gets the checkout as a copy inside the container (for example `git archive` of the commit piped into the container, or a named Docker volume filled once per run), not a bind mount of the Mac's folder; what the suite writes back (coverage, logs) still reaches `run/` as today.
2. The VM's open-file count does not grow with the number of queue runs: a test (or a measured run recorded in the gap's record) shows its count after 10 queue runs within 1,000 of before.
3. Session containers are measured too; if they leak the same way, the record says how much, and a follow-up gap is named.
4. A sensor reads the VM's open-file count (macOS only; none elsewhere), with a goal below 150,000, so a leak shows on the model before it stops anything.

## Files to touch
`dev/bin/agents.py`, `dev/bin/fac.py`, `dev/model/resources.yaml`, tests.

## Size budget
80 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1) in a Linux container with no Docker, so nothing here was measured on Docker Desktop.

- **1, done.** `agents.queued()` (the queue's and flake triage's suite containers) no longer bind-mounts the checkout.
  On the Mac, `tar -C <checkout> --exclude ./.venv --no-xattrs --no-acls -cf - .` (with `COPYFILE_DISABLE=1`, so
  macOS's tar adds no `._` files) is piped into `docker run -i`, which unpacks it at /work before the suite's command.
  A copy that does not unpack exits 125, which `fac.suite` already reads as NotStarted (an infrastructure failure, no
  gap blamed). `run/coverage/` is still mounted at its own path, and logs are the container's output, so both still
  reach `run/`. The empty tmpfs over `.venv` is gone, since the copy has none. These choices were taken as the most
  reversible:
  - tar of the folder rather than `git archive` of the commit: triage's worktree holds an uncommitted merge
    (`--no-commit`), suites call git, and today's suites see untracked files. Tar keeps all three as they were.
  - the queue's checkout has its git directory inside it, so the git directory is in the copy and nothing of the
    checkout is mounted. Triage's worktree (`<worktrees>/.triage`) shares the checkout's git directory, which is
    outside it. That directory is still mounted read-only at its own path, as before (triage runs only after a failed
    queue run). If the sensor shows that it matters, copying it too is the next step.
  - each run now copies the whole checkout, its `.git` included, through a pipe. How long that takes on the Mac was
    not measured.
- **2, not shown.** No VM count was taken before and after 10 queue runs (there is no Docker Desktop here). The tests
  show only that the cause is gone: `test_a_queue_suite_reads_a_copy_of_the_checkout_never_the_macs_folder` checks
  that no `docker run` of a queue run mounts any folder of the checkout; that the suite sees the files, `.git` and
  untracked files but not `.venv`; that what it writes in /work stays out of the checkout; and that what it writes in
  `run/coverage/` reaches it. Left: on the Mac, read `python3 dev/bin/resources.py vm-open-files`, let 10 queue runs
  go, read it again, and add both numbers here.
- **3, not measured.** Session containers (`run_args`, `-v {work}:/work`) are unchanged and were not measured. They
  read through a bind mount the same way, so they very likely leak too, at a rate set by how much each session reads.
  Follow-up gap named: `sessions-copy-their-clone-into-the-container`. It would measure the sessions' share with the
  new sensor, and if that grows, give a session its clone as a copy and copy its commits back.
- **4, done.** `resources.py vm-open-files`: on macOS, the most open files held by any
  `com.apple.Virtualization.VirtualMachine` process (`pgrep -f`, then `lsof -n -P -F f -p <pids>`; the limit is per
  process). Off macOS, with no VM running, or when lsof fails, it gives no reading (the sensor fails and goes stale),
  never 0. It is a slow reading (taken with Docker's disk, at most every 10 minutes, with lsof limited to 90 s).
  `dev/model/resources.yaml` has the auxiliary `vm-open-files` and the goal `vm-open-files-within` (`<= 150000`). The
  goal shows on the model and feeds no gate (`machine-full` does not read it), so a leak is seen and nothing is
  stopped. Tests: `test_the_docker_vms_open_files_are_read_on_macos_only`, and `test_gates_respect_headroom` checks
  the goal and the sensor in the compiled model.
- **Check finding `missing-feedback goal.vm-open-files-within`, answered.** The goal's loop closes through a new
  `external` block, `restart-docker` (the coordinator restarts Docker Desktop, as on 2026-11-22 at 10:17). It reads the
  goal and sets `auxiliary.vm-open-files`. This was chosen over gating sessions in `machine-full` as the more
  reversible option: it states who acts today and stops nothing. `test_gates_respect_headroom` checks that the loop's
  actuator is `restart-docker`, that no block other than an external one reads the goal, and that the finding is
  gone. It failed with the block's `out:` removed.
- Files outside the list: `dev/bin/resources.py` (the sensor's program is there) and one sentence in
  `dev/README.md`. `dev/bin/fac.py` needed no change. Net lines in `dev/bin` and `dev/model`: +38.

## Where it stopped

Parked by the factory (review/suites-copy-their-checkout-into-the-container-1, 2026-11-22 10:54).

Done: definition item 1 (agents.queued pipes a tar of the checkout, minus .venv, with its git directory when inside it, into docker run -i, unpacked at /work; run/coverage still mounted; a failed unpack exits 125, NotStarted; tested with a fake docker that really unpacks) and item 4 (resources.py vm-open-files on macOS via pgrep and lsof, no reading elsewhere; auxiliary vm-open-files and goal vm-open-files-within <= 150000, feeding no gate; tested). Left: item 2, read `python3 dev/bin/resources.py vm-open-files` on the coordinator's Mac with this branch's queued() in use, let 10 queue runs go, read it again, and record both (must be within 1,000); item 3, measure the same count across session containers' runs and record how much it grows, naming the follow-up gap with that number. Both need Docker Desktop on the Mac, which the implementor's Linux build has no access to, so another fix round cannot close them.
