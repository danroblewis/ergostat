# Developing ergostat in a container

Heavy development work (the benchmarks, load tests, the layout corpus, the Linux sandbox tests, and preferably
the routine suites) runs in a Docker container with hard limits, so a runaway test exhausts a Linux VM and not
your computer's kernel. On macOS this matters: this project's load benchmarks have kernel-panicked a Mac twice by
thread exhaustion (about 14,000 threads), and the watchdog (`scripts/suite_watch.py`), being a process on the same
kernel, can be outrun. Inside the container the kernel itself refuses the 4,097th process or thread.

## What you need

Docker (on macOS, Docker Desktop with its engine running). The first run builds the image (`Dockerfile`, a few
minutes); later runs reuse it and rebuild only when `pyproject.toml`, `uv.lock` or the `Dockerfile` change.

## Running a command

```sh
scripts/in_container.sh CMD ...
```

runs `CMD` in the `dev` service (`compose.yaml`) with this checkout, or any worktree, at `/work`:

| Limit | Default | Change with |
|---|---|---|
| processes and threads (`pids_limit`) | 4096 | `ERGOSTAT_PIDS` |
| memory, no swap beyond it | 12g | `ERGOSTAT_MEM` |
| CPUs | half the computer's, at most the Docker VM's | `ERGOSTAT_CPUS` |
| `/tmp` (a tmpfs, counted as memory) | 4g | `ERGOSTAT_TMP` |
| network | none: only the loopback device | `--net` |

An init process reaps whatever a test leaves behind, and the container is removed when the command ends.
`ERGOSTAT_WORK=DIR` mounts another checkout or worktree; a worktree's git directory is mounted at its own path,
so git works inside. `--print` shows the command without running it. You run inside as your own uid; as root
(`ERGOSTAT_UID=0`, or uid 0 outside), the container runs as uid 1000 instead, an ordinary user all the same.

`--sandbox` uses the `sandbox` service instead: the same, with Docker's syscall filter (seccomp) and its masked
`/proc` paths turned off, which bubblewrap needs for its namespaces. Use it only for the Linux sandbox's tests; in
the ordinary service those tests skip, saying so.

**The container limits resources; it is not a security boundary.** Your checkout and its git directory are
mounted read-write, so whatever a command inside writes there (a git hook, a `.git/config` setting, a script in
the tree) runs on your computer the next time you use git or the file. Run nothing inside that you would not run
on your computer.

The image holds Python 3.12, uv, the locked dependencies (in `/opt/venv`, not your checkout's `.venv`),
Playwright 1.63.0 with Chromium, git, zsh and bubblewrap, and runs as an ordinary user. It holds no secrets: the
build sees only `pyproject.toml` and `uv.lock`. Without a network, `uv` works from the image's cache
(`UV_OFFLINE=1`), so a dependency added to `uv.lock` needs the image rebuilt, which the script does.

## The standard runs

```sh
# the unit suite
scripts/in_container.sh uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal
# the browser suite
scripts/in_container.sh uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m pytest -q \
    -n 4 --dist worksteal tests/test_diagram_rendering.py tests/test_page_polling.py tests/test_items_page.py \
    tests/test_page_refresh.py tests/test_keyboard_story.py
# every example, its pages checked with Playwright
scripts/in_container.sh uv run --with playwright==1.63.0 python scripts/demo_check.py
# the benchmarks (results under .out/, which git ignores)
scripts/in_container.sh uv run python scripts/scale_bench.py check 10 100 300 1000 --work /work/.out/scale
scripts/in_container.sh uv run python scripts/latency_bench.py synth 1 50 100 500 --label container
scripts/in_container.sh uv run python scripts/daemon_bench.py 20 170 --mode daemon --minutes 6.5 --work /work/.out/daemon
# the Linux sandbox's attack suite (bubblewrap; needs --sandbox)
scripts/in_container.sh --sandbox uv run python -m pytest -q tests/test_sandbox_attacks.py
# the layout corpus
scripts/in_container.sh uv run --with playwright==1.63.0 python -m tests.layout_corpus /work/.out/corpus --generated 300
```

Write results under `/work` (here `/work/.out/`) to keep them: everything else in the container, `/tmp` included,
is gone when it ends.

Python's bytecode caches go to `/tmp/pycache` inside (`PYTHONPYCACHEPREFIX`, compose.yaml), never to the
checkout's `__pycache__` folders: the host writes those too, and a run on each side at once once left a truncated
cache ("marshal data too short", every worker failing to collect). Inside, a run compiles afresh (a second or two).

## Measured (2026-11-19)

On the 28-core Mac Studio, Docker Desktop 29.1.2 (a 24-CPU VM), the container at 14 CPUs and 12 GB, with other
agents' suites running on the host (load 3 to 7). Wall times include starting the container (about 1 s; the first
build took 74 s).

| Run | In the container | On the host |
|---|---|---|
| unit, `-n 8` (after the review fixes, same commit both sides) | rc 0: 1682 passed, 34 skipped, 8 xfailed, 2 xpassed; 162 s; peak 378 threads, 1.6 GB | rc 0: 1712 passed, 13 skipped, 1 xfailed; 157 s; peak 371 threads, 2.1 GB |
| browser, `-n 4` | 217 passed, 1 failed (fixed since: `SPLIT_SHOTS`; that test then passed 5 runs of 5), no skips; 565 s; peak 556 threads, 4.1 GB | 200 passed, no skips; 463 s; peak 632 threads, 3.7 GB (\*) |
| `tests/test_sandbox_attacks.py` (`--sandbox`) | 26 passed, 5 failed (bwrap); now 26 passed, 4 xfailed, 1 xpassed | 30 passed, 1 xfailed (seatbelt) |
| after `linuxfix`: unit, `-n 8` | rc 0: 1695 passed, 34 skipped, no xfail; 166 s | rc 0: 1715 passed, 13 skipped, 1 xfailed; 169 s |
| after `linuxfix`: browser, `-n 4`, one file at a time | | rc 0: 180 + 17 + 13 + 8 passed |
| after `linuxfix`: `tests/test_sandbox_attacks.py` | 31 passed (`--sandbox`) | 30 passed, 1 xfailed (in the unit run) |

The unit suite's 1,726 tests are the same on both sides; inside, 20 more skip (the attack suite, without
`--sandbox`); since `linuxfix` nothing is an expected failure on Linux. (\*) The browser suite's host figure is from main
at 214d864, before the rebase brought 18 browser tests: the host stayed busy with the merge
queue's suites, so it was not rerun beside them. Inside, all 218 browser tests ran. Per test the container is about as fast as the host: the unit suite 162 s
against 157 s, the browser suite 2.6 s a test against 2.3 s.

The bind mount is not the bottleneck (the venv and the uv cache live in the image), so there is no named volume.

**The limits hold.** A thread bomb inside (stopped at 10,000 or the first refusal) was refused at 4,094 threads
(`pids.current` 4096 = `pids.max`); a memory bomb under `ERGOSTAT_MEM=2g` was killed by the kernel's OOM killer at
1,792 MB held. The host's threads meanwhile: 2,818 before, 2,856 at the peak, 2,807 after (other agents' suites
were running; nothing of the bomb reached the host).

**No known failures on Linux.** The fifteen the container first found (docs/GAPS.md) are fixed: 9 `[segments]` cases
in `tests/test_store_conformance.py` (the segmented log watched its directory's mtime, which Linux keeps to a jiffy;
it now keeps a layout token), `tests/test_daemons.py::test_daemons_on_the_agents_api` (Debian's `/bin/sh`, dash,
forks where macOS's execs; a daemon's simple command now runs with `exec`), and 5 in `tests/test_sandbox_attacks.py`
that asserted macOS behaviour (each has a Linux form now). A failure in the container is real.

When Docker is down, run the same commands on your computer, without `scripts/in_container.sh`, under
`scripts/suite_watch.py` as always.

## Looking at a running demo

Two scripts let you (or a session) start one demo, leave it running and walk its pages in Chromium, the way a
person would look at them:

```sh
# start one demo from a fresh copy under /tmp; prints {"demo", "url", "copy", "log"} as one JSON line
uv run python scripts/demo_up.py start the-job [--port 8801]
# walk it: a JSON list of steps (a file, - for stdin, or the list itself); screenshots into a folder that exists
mkdir -p /tmp/shots
uv run --with playwright==1.63.0 python scripts/walk.py --shots /tmp/shots \
    '[{"goto": "http://127.0.0.1:8801/diagram"}, {"wait": 1500}, {"shot": "diagram.png"}, {"text": "body"}]'
# stop it
uv run python scripts/demo_up.py stop the-job
```

`demo_up.py` takes a demo's name: a folder of `examples/` that holds an `ergostat.yaml`. Anything else (a path,
`..`) is refused before anything is copied. It runs the copy the way `demo_check.py` does: offline against the demo's
fakes, with an `ERGOSTAT_HOME` of its own beside the copy. It waits up to 90 s for the page to answer, and refuses a
second start of a demo that is still running. Without `--port` it picks a free port (never 8790, the owner's page).
A start whose `ergostat run` fails (a model with errors) is reported at once.
`stop` asks the runner to stop and gives it 70 s. Then it stops, with SIGTERM and then SIGKILL, whatever is left: the
runner, the agent runs and daemons it was seen to have started (each one in a session of its own), and the process
groups they lead. It finds them by reading /proc, or `ps` where there is no /proc. Where it can list neither, it does
nothing and exits 1. If anything is still alive afterwards, it exits 1 and keeps the demo's record. It looks for them
before it asks, then every half second while it waits, so a process that the runner starts after the last look and
leaves behind when it ends is not seen.

`walk.py` runs its steps in one page, 1440x900 unless `--size` says otherwise. The steps are `goto`, `size`
(`[W, H]`), `dark` (true or false), `wait` (milliseconds or a selector), `click`, `hover`, `fill` (`[SEL, TEXT]`),
`press` (a key, or `[SEL, KEY]`), `scroll` (`[DX, DY]` or a selector), `shot` (a name such as `diagram.png`,
matching `^[a-z0-9][a-z0-9._-]{0,63}\.png$`, written into `--shots`; `"full": true` for the whole page) and `text`
(a selector; printed cut at 6,000 characters). A step that fails is printed and the walk goes on. Console errors and
failed requests are printed at the end. The exit code is 0 when every step ran and 2 otherwise. Malformed steps or a
bad shot name are refused with 2 before Chromium starts. Chromium gets no proxy for 127.0.0.1 and localhost; when
`HTTPS_PROXY` is set, it is the proxy for every other host.

## What stays on your computer

- The macOS sandbox tests: `tests/test_sandbox_attacks.py` tests `sandbox-exec` only on macOS; in the container it
  tests the Linux sandbox (bubblewrap). Run it in both places when the sandbox changes.
- Anything that needs your real credentials or services (an AI agent's sign-in, a real ticket system). Nothing of
  your home folder is in the container, by design.
- Running ergostat for real (`ergostat run` on your projects): the container is for development.
