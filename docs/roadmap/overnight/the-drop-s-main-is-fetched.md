# drop-fetch-serialised: the drop's main is fetched under a lock

depends-on: []

agents.drop() (dev/bin/agents.py:223-236) fetches the checkout's origin/main into <live>/drop.git refs/heads/main with nothing held. When several sessions start at once (nine fix gaps were leased together at 11-21 10:20), the fetches race and git fails with "cannot lock ref 'refs/heads/main': is at X but expected Y". The lease ends at once and the session never starts: gap/poor-identifications-proposed-projections-drawn-as-sure was leased and ended seven times this way and went stuck in fix for 6.4h.

## Definition of done

1. drop() holds an exclusive fcntl lock (a file under <live>, e.g. drop.git.lock) across the init check, the symbolic-ref and the fetch, so concurrent callers run one after another (lesson-1).
2. A fetch that still fails on a ref lock is retried a bounded number of times (at most 3, a hard ceiling, lesson-4) before raising; any other git error raises at once.
3. A session that fails in drop() gives its lease back with the error recorded, as today; nothing fails open (lesson-3).

## Acceptance tests

- tests/test_agents_drop.py::test_concurrent_drops_all_succeed: 8 threads call drop() at once against a checkout whose origin/main moves between calls; all return, and the drop's main equals the checkout's origin/main. It fails without the lock.
- tests/test_agents_drop.py::test_a_ref_lock_failure_is_retried_then_raised: a git stand-in that fails with 'cannot lock ref' every time; drop() raises after the bounded retries, and no more.

## Size budget

30 net lines outside tests and docs.

## Where it stopped

Built in full; nothing is left. Choices made with nobody to ask, each the more reversible one:

- "At most 3" is read as three fetches in all (agents.DROP_TRIES = 3: the first try and two more), the stricter
  reading of the ceiling. Between tries it waits 0.2s, then 0.4s.
- The lock is `<live>/drop.git.lock`, next to the drop. It is released when its file closes, so it is let go on any
  way out.
- Item 3 needs no new code: drop() still raises, and implement.main hands that to fac.guarded as before.
- With the retry in place, a race alone would not fail the concurrent test, so the test also counts how many of the
  drop's git steps run at once and requires exactly one. With the lock removed it failed (7 at once). With the retry
  made to catch every error, both raise tests failed.
- Size: 16 net lines in dev/bin/agents.py, and one sentence in dev/README.md.
