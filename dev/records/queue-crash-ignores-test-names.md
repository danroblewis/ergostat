# queue-crash-ignores-test-names: a passing test's name is never read as a crash

`crashed()` in `dev/bin/queue.py` searches a whole suite log for `[Errno 28]`. `test_what_counts_as_a_crash` has that text in a parametrize id, so with verbose output every red unit run looks like a disk-full crash. A batch with one ordinary failure was given back as "crashed", with no test blamed, instead of being isolated.

Change. Crash markers are read only from lines that report a crash, never from result lines that name a test (PASSED, SKIPPED, XFAIL, XPASS). A FAILED line that reports a worker crash still counts.

Definition of done.
1. A test: a log with a PASSED line whose name contains `[Errno 28]`, plus an ordinary FAILED line, is not a crash.
2. The existing crash cases still pass.
3. Do not measure or change the live instance in the session.
