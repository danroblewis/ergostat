---
kind: lesson
about: the classes of mistake independent gate reviews keep finding in ergostat branches
use: every implementor brief (check your branch against each before saying built); every reviewer brief (look for each)
---
# What reviews keep finding

Each entry is a class of mistake that reached an independent review more than once, the shape it takes in ergostat,
and the check that catches it before review. Most first attempts that failed review failed on one of these.

## 1. Check, then write, without holding the lock
A state is read, a decision made, then written, with nothing held in between, so a concurrent writer slips in.
Seen as: an approval written over a denial; a carried change reopening an item being accepted; a run handed to a
process that was told to stop between the hold and the hand-over; a reviewer's verdict recorded after the change it
read had already been carried and judged again.
**Check:** for every read-decide-write, name the lock held across all three, or re-read inside the lock before writing.
Write a test that puts the competing write in the gap (monkeypatch the step between).

## 2. Ordering by wall time instead of by sequence
Comparing `at` timestamps to decide which came first: stamps taken at the start of a long pass, or after a slow call,
or equal to the second.
**Check:** order by the record's `seq`, or stamp what was read (the id or seq of the version judged) and compare for
equality. Never `>=` on times to mean "newer".

## 3. Failing open when something can't be read
A missing file, an unreadable ledger, a lookup that misses, a cause not found: treated as zero, empty, or fine.
Seen as: a budget that records nothing when a session times out; a cause chain that counts as empty when its run
isn't found; a cap checked as `spent >= cap` before a call that can cost more than what's left.
**Check:** list every input that can be missing; each must stop or count as the worst case. Charge the whole reserved
budget until the real cost is known; check `spent + most_this_call > cap` before calling.

## 4. A limit with a floor and no ceiling
Counts, concurrency, pool sizes, retries, rates read from config with a minimum and no maximum.
Seen as: `concurrency: 5000` spawning 5,000 processes (the machine has kernel-panicked from thread exhaustion);
a breaker-free loop running 212 times in 15 seconds; retries with no end.
**Check:** every number that multiplies processes, threads, calls or money has a hard maximum, enforced at config time
and again at run time (counting the ones still draining).

## 5. Stale state surviving under a reused id
Items are keyed by their subject, so a thing made again gets the same id and the fold merges old fields into it.
Seen as: an old `pass` applying to a new version; an old `revise` sticking forever; a cancelled id never cleared.
**Check:** when an item is made again, which old fields must be cleared? Test the same-id remake.

## 6. Work that keeps running after it was cancelled
A cancel or timeout answers "done" but the thread, child process or container keeps working.
Seen as: a daemon step that kept its git lock after cancel; containers left running when the engine killed the client;
a killed suite whose pytest kept going under `sh -c` as PID 1.
**Check:** on cancel or timeout, what actually stops? Kill the process group or container by name; `--init` in
containers; a test that cancels a hung step and shows the next item gets through.

## 7. Two things merged that each passed alone
Branches that pass their own suites conflict once merged: a new CLI flag not classified for the read-only fallback; a
daemon fix racing another fix's start-up.
**Check:** before saying built, merge origin/main into the branch and run the suites again.

## 8. A score or guarantee stated wider than the code supports
Docs and docstrings claiming "never", "each side ≤ 5%", "never the repair", "found" for a check that a trivial
change passes.
Seen as: a benchmark's "found" accepting `MIN(x, 1e9)` and an equation of `0`; planted hints that named the answer; an
"anytime-valid" bound that assumed independent stocks; a guard described as safe that was a denylist.
**Check:** for each claim in the docs, name the test that would fail if it were false. If there isn't one, narrow the
claim or write the test. Prefer allowlists to denylists for anything called a guard.

## 9. A test that can't fail
Tests that assert on a happy path, or with `A and B or C`, or that never exercise the window they're named for.
**Check:** for each new test, break the code it guards and watch it fail (say so in the report).

## 10. Load-dependent flakes blamed on the branch, or ignored
Timing tests that pass alone and fail under `-n 8` with other suites running.
**Check:** a test that fails under load is either a real race in ergostat (often: a first spawn, a lease renewal, a
fold read before a write is visible) or a fixed sleep in the test. Find which; never only raise the timeout.

## 11. Destructive operations on paths built from input
`rm -rf`, `git add -A`, `reset`, worktree creation, on a path made from a branch name, a request field or an empty
variable.
**Check:** validate names (`^[a-z0-9][a-z0-9-]{0,63}$`), resolve and confirm the path is under the expected root,
`"${VAR:?}"` in shell, and delete only what the code itself created (by name, never all-but-a-keep-list).

## 12. A fix round answers every finding, not only the blocking ones
Seen as: warm2: two non-blocking findings of round 1 (a stale SPEC sentence, a traceback on a bad --check-warm file)
ignored in the fix round, then blocking in round 2, parking the gap.
**Check:** list every finding of the review you are answering, blocking and not, and for each say in the report what
changed or why it stays; a non-blocking finding left unanswered becomes blocking in the next round.

## 13. Stay inside the gap: an unrelated failure is reported, not fixed in the branch
Seen as: continue-branch: a lease-renewal test failed under load; the implementor wrote its own lease fix into the
branch, and the review failed the gap on it.
**Check:** when a suite fails on something your change did not touch, name the test and why it is unrelated in your
report and stop there; a fix outside the definition of done belongs in its own gap
