# flake-compute-output-ended-after-last-out: test_ended_after_last_out stops failing under load

`tests/test_compute_output.py::test_ended_after_last_out` failed in 4 of the last 40 merge runs and passed alone each time, so the queue excuses it but pays for two reruns and risks a batch. It fails at its assertion near line 210, after `done`: it asserts a run is no longer listed, while other runs from the same test are still listed:

    AssertionError: assert '<run>' not in {'<run>': {'out': 6291456, 'err': 5}, ...}

Find the real cause. If the test reads state that the keeper or node updates asynchronously, wait for that state with the file's own `until`, bounded. If the code can truly keep a finished run listed, fix the code. Do not raise a timeout, skip, retry or quarantine the test.

Definition of done.
1. The cause is named in the record.
2. The test passes 30 times in a row while the machine is loaded with a CPU-bound background job (bounded, with a watchdog, started and stopped by pid).
3. The test still fails if the behavior it guards is broken (show this).
