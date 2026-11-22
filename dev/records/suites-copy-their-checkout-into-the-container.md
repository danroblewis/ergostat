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
