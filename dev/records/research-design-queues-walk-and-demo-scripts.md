# research-design-queues-walk-and-demo-scripts: Two scripts let a session start a demo and walk it in Chromium: demo_up.py and walk.py

depends-on: []

Problem: no factory session can look at a running demo. The design review's walker lives outside the repository (the design folder's browse.py), and the only demo runner, scripts/demo_check.py:150-187 (fresh_copy, OFFLINE), is a whole check that cannot be asked for one demo left running. Sessions run only allowlisted commands (dev/bin/agents.py:38-46), so without a named script no implementor, designer or researcher can open a page. Chromium is already in the image (Dockerfile: playwright==1.63.0, /opt/ms-playwright; tests/test_agents.py:25).

Change: add scripts/demo_up.py, which uses demo_check's fresh_copy and OFFLINE. `demo_up.py start DEMO [--port N]` copies examples/DEMO to a new folder under /tmp, runs it with `python -m ergostat -C COPY run --port N`, waits up to 90 s for its web to answer, and prints one JSON line {demo, url, copy, log}. `demo_up.py stop DEMO` stops it. A demo name must be a folder of examples/ that holds an ergostat.yaml; anything else is refused. Also add scripts/walk.py, the design review's walker brought in with tests. It reads a JSON list of steps (goto, size, dark, wait, click, hover, fill, press, scroll, shot, text) and runs them in one Chromium page, 1440x900 by default. Screenshots go to --shots DIR, which must exist, under names that match ^[a-z0-9][a-z0-9._-]{0,63}\.png$. Text is printed cut at 6000 characters, and console errors and failed requests at the end. It launches Chromium with no proxy for 127.0.0.1 and localhost, and with HTTPS_PROXY as Chromium's proxy for any other host when that is set. A step that fails is printed and the walk goes on. The exit code is 0 when every step ran, and 2 otherwise.

Definition of done:
1. demo_up.py start brings up any one of the-job, ticket-factory, image-squeeze, roadmap, software-factory and big, prints its URL, and stop ends it. A second start of the same demo is refused while the first runs.
2. An unknown demo name, a path, or `..` is refused before anything is copied.
3. walk.py runs every step kind, writes the named screenshots only under --shots, and refuses a shot name outside the pattern.
4. walk.py passes no proxy for loopback URLs and HTTPS_PROXY for others (unit-tested on the launch arguments).
5. docs/DEVELOPMENT.md says what the two scripts are for and how to run them.

Files to touch: scripts/demo_up.py (new), scripts/walk.py (new), scripts/demo_check.py (only if fresh_copy and OFFLINE must be importable without side effects), docs/DEVELOPMENT.md, tests/test_walk_scripts.py (new).

Acceptance tests (tests/test_walk_scripts.py):
- test_demo_up_refuses_unknown_and_paths
- test_demo_up_starts_and_stops_the_job (a real start of the-job on a free port: its /api/model answers, then stop)
- test_walk_runs_steps_against_a_local_page (a stdlib http.server fixture page: a click changes text, the text step prints it, and a shot file exists)
- test_walk_refuses_bad_shot_names
- test_walk_proxy_only_off_loopback
- test_walk_exit_code_on_failed_step
The browser tests run under `uv run --with playwright==1.63.0`, like the four browser files.

Size budget: 200 net lines (scripts only; tests and docs excluded).

Area: research-design-queues. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built: scripts/demo_up.py, scripts/walk.py, tests/test_walk_scripts.py (the six named tests, plus
test_walk_text_is_cut and test_demo_up_starts_and_stops_each_named_demo over the other five demos item 1 names), and a
"Looking at a running demo" section in docs/DEVELOPMENT.md. scripts/demo_check.py is unchanged: fresh_copy and OFFLINE
import without side effects as they are. All 12 tests pass (92.8 s, under the watchdog with playwright==1.63.0); ruff is clean;
main merged in (already up to date).

Decisions taken alone (the most reversible option each time):
- The page that ergostat run serves has no /api/model (only /remote/model, behind a remote token: ergostat/web/server.py
  `_answer` has no "model" head). The start test reads /api/status instead, the API demo_check reads first.
- `stop` runs `ergostat run --stop` (SIGTERM, 10 s). In the first test run the-job's runner had not stopped within those 10 s,
  so stop now waits up to 60 s more and then kills the runner's process group (it starts in its own session). The pid
  comes only from the ERGOSTAT_HOME that demo_up made for that copy.
- A start or stop holds an flock on /tmp/ergostat-demo-up/DEMO.lock from the "already running?" check until the state is
  written (lesson-1). A copy's --json that cannot be read counts as running (lesson-3). A copy that is gone counts as stopped.
- The copies under /tmp are not deleted by stop, as with demo_check: their logs stay readable.
- walk.py refuses malformed steps and bad shot names (rc 2) before Chromium starts, rather than as a failed step.
  Names are checked with fullmatch, so "x.png\n" is refused.
- Without HTTPS_PROXY Chromium is launched with --no-proxy-server. With it, the proxy has the bypass "127.0.0.1,localhost",
  and any user:password in the proxy URL is passed as Playwright's username and password.

Breaks seen to fail their tests (lesson-9): walk's exit code always 0 (test_walk_exit_code_on_failed_step), shot
names checked with match instead of fullmatch (test_walk_refuses_bad_shot_names), an empty proxy bypass
(test_walk_proxy_only_off_loopback), and demo_up's ergostat.yaml check removed (test_demo_up_refuses_unknown_and_paths).
The second-start refusal was not broken on purpose. Broken, it would start a second runner that the test's stop could not reach.

Left, outside this gap: sessions still cannot run the two scripts. They are not in the implementor's allowlist
(dev/bin/agents.py TOOLS), and this definition's files do not include it, so allowlisting them needs a gap of its own.
Not checked: the first test run's the-job runner (pid 740, its stop timed out at 10 s) was not seen to end. This session
cannot run ps; it had already been sent SIGTERM.

Overrun reason: the scripts are 290 lines against 200. About 30 are module docstrings that give the usage, the stop's wait-then-kill of the process group (lesson-6), the start lock (lesson-1), and walk's up-front refusal of malformed steps account for the rest.

Round 2 (answering review 1; every finding):
- Blocking, stop's SIGKILL reached only the runner's process group: fixed. stop now finds the runner's pid only while the
  runner holds its run.pid lock (a stale file's pid may be another's now). It records the runner and every descendant
  with its start time, once before `run --stop` and every 0.5 s while it waits. Then it sweeps whatever of them is
  still alive with the start time it was seen with: SIGTERM, then SIGKILL after 5 s, to each pid and to the groups they
  lead (never demo_up's own group). Left alive, or still running, means rc 1 and the state is kept. It does not call
  reap.stop as it is: that lists processes with ps, this container has no ps, and an empty list would read as nothing
  to stop (lesson-3). So demo_up reads /proc where there is one and falls back to reap.tree (ps) elsewhere, and uses
  reap.descendants. If it can list neither, stop does nothing and exits 1. New test
  test_demo_up_stop_ends_what_the_runner_left: a fake runner that ignores SIGTERM and holds run.pid's lock, with a
  child in its own session that also ignores SIGTERM. stop must end both. Broken on purpose (only the runner swept),
  the test fails, and the broken stop also returned 0 with the child alive. Not covered: a process the runner starts
  after the last look and leaves behind when it ends (said in docs/DEVELOPMENT.md).
- walk.py proxy user and password are now percent-decoded (unquote). The test asserts password "p@".
- demo_up start fails at once (rc 1, stopped, state removed) when `ergostat run` exits non-zero. New test
  test_demo_up_fails_at_once_when_run_fails.
- walk.py refuses a non-boolean dark (`{"dark": "false"}`) before Chromium starts. Asserted in
  test_walk_refuses_bad_shot_names.
- server.py from=/to= (a finding of another gap's review, ui-from-a-crossing-...): outside this gap, left alone.
Tests: tests/test_walk_scripts.py, 14 passed (202.6 s, under the watchdog with playwright==1.63.0, nothing left
behind). The file took 92.8 s in round 1; the reason for the difference was not looked into. ruff is clean. main was
merged in and was already up to date.
Refused here: a `cat >> ... <<EOF` append to this file (written with the edit tool instead).

Overrun reason: the scripts are 356 lines against 200. Round 1's 290 are explained above. The other 66 are the descendant sweep that stop needs so that agent runs and daemons in their own sessions do not survive it (lesson-6), the locked-pid read that keeps it off a reused pid, the /proc listing (this container has no ps, so reap.stop alone would fail open), and the fail-at-once on a failed run.
