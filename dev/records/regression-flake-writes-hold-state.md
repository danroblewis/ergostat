# regression-flake-writes-hold-state: A flake seen never takes a test out of main-broken, and a second break keeps the first clock

depends-on: []

Problem: the kind flake moves to seen on every flake.seen (ergostat.yaml:197-200) and four writers emit it without looking (dev/bin/onmain.py:74, queue.py:241-242, triage.py:76, manage.py:231), so a test still failing on main leaves main-broken; every flake.main-broken writes a fresh main_broken_at (onmain.py:92-94), restarting the repair clock; a flake fixed then seen again keeps its old times. Change: new dev/bin/flakes.py with one writer flakes.say(event, test, **data) that every flake writer calls. Under one lock file in the run dir it re-reads the item and writes synchronously with fac.add: flake.seen on a main-broken item writes flake.measured (counts times, no state move); flake.main-broken on a main-broken item updates main and unions gaps, leaving main_broken_at; either on a fixed item is a remake, a patch changeset setting times to 1 and removing main_fixed_at, fixed_by and green_passes; an unreadable item is written as today with the failure on stderr. Done: no other code emits flake.seen or flake.main-broken (grep test over dev/bin, which later writers such as merge-pipeline-browser-daily-on-main must also pass); the three state rules hold; two concurrent writers never lose a state; `ergostat check` has no errors. Files: dev/bin/flakes.py, dev/bin/{onmain,queue,triage,manage}.py, ergostat.yaml, tests/test_factory.py (five tests). Budget: 120 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: dev/bin/flakes.py and its four callers, the five tests in tests/test_factory.py, a comment on the flake
kind in ergostat.yaml, and a paragraph in dev/README.md (kept current with the change). That is 70 net lines outside
tests and docs, against a budget of 120. Nothing is left.

Choices made alone, each the more reversible:
- The write goes through `fac.ergostat("event", "--add", ...)`, the call fac.add makes, not through fac.add itself:
  fac.add takes only data, but the remake is a patch and `manage.py flake` records `--as coordinator`. fac.py is
  unchanged.
- A remake sets every field it is given (gaps become the new gaps, not a union with the old life's) and removes only
  the three fields the definition names. A seen remake keeps an old `main` and `main_broken_at` it is not given.
- When `ergostat item` says "no item", the flake is new and is written as given, with nothing on stderr. Any other
  failure is the unreadable case.
- The rules live in flakes.py only. The kind's `moves_from` was not used (not asked for).
- The grep test counts a quoted `flake.seen` or `flake.main-broken` anywhere in dev/bin outside flakes.py, except as
  flakes.say's first argument.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 13:29).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 668, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 13:29).

Its runs failed past their attempts (a dead letter):
- attempt 10: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 11: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 12: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 13: nack the run ended with gap/regression-flake-writes-hold-state still parked

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:06).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
