# queue-crash-ignores-test-names: a passing test's name is never read as a crash

`crashed()` in `dev/bin/queue.py` searches a whole suite log for `[Errno 28]`. `test_what_counts_as_a_crash` has that text in a parametrize id, so with verbose output every red unit run looks like a disk-full crash. A batch with one ordinary failure was given back as "crashed", with no test blamed, instead of being isolated.

Change. Crash markers are read only from lines that report a crash, never from result lines that name a test (PASSED, SKIPPED, XFAIL, XPASS). A FAILED line that reports a worker crash still counts.

Definition of done.
1. A test: a log with a PASSED line whose name contains `[Errno 28]`, plus an ordinary FAILED line, is not a crash.
2. The existing crash cases still pass.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1. `crashed()` (dev/bin/queue.py) now reads the log line by line through `crash_text()`: an
`INTERNALERROR>` line or a plain line (a traceback's `OSError: [Errno 28] ...`) is read whole; a line with PASSED,
SKIPPED, XFAIL or XPASS is not read; a FAILED or ERROR line is read only after its first " - " (the reason), so
`FAILED id - worker 'gw3' crashed` still counts and a FAILED test whose name holds `[Errno 28]` does not. The `re.M`
flag went because lines are now searched one at a time. dev/README.md's sentence on crashed() says so too.

Choice made with nobody to ask (the reversible one): the definition names only PASSED, SKIPPED, XFAIL and XPASS, but
a red run of `test_what_counts_as_a_crash` itself would print its `[Errno 28]` id on a FAILED line, so FAILED lines
are read only from their reason, as above. A test id that itself holds " - " would have its tail read as the reason;
no id in the tree does. Undo it by returning `line` for FAILING lines in `crash_text()`.

Tests: `test_a_passing_tests_name_is_no_crash` (done item 1: verbose, xdist, SKIPPED, XFAIL and XPASS lines naming
`[Errno 28]`, each with an ordinary FAILED line, are no crash; adding a worker-crash FAILED line makes it one), and
three new cases in `test_what_counts_as_a_crash`, whose old cases still pass (done item 2). With `crash_text()` taken
out of `crashed()`, 7 of them failed (the 5 new tests and the 2 FAILED-name cases). Nothing live was measured or
changed (done item 3). Net code outside tests/docs/dev: 0 (the change is under dev/).
