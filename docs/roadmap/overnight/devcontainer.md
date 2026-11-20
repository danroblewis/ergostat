# devcontainer: heavy development work in a Linux container with hard limits

Branch `devcontainer`, from main at 214d864. Size: development infrastructure.

## The gap

This Mac has kernel-panicked three times under development work: twice from thread exhaustion (about 14,000
threads) in load benchmarks, once from a bug in a macOS `sandbox-exec` profile. The watchdog
(`scripts/suite_watch.py`) samples and kills, but it is a process on the same kernel and can be outrun. The Linux
sandbox (`ergostat/sandbox/bwrap.py`) and its attack suite have never run on Linux at all.

## Done when

A dev image (`Dockerfile`: Debian slim, Python 3.12+, uv, the locked dependencies installed in cached layers outside
the bind mount, Playwright 1.63.0 with Chromium and its system libraries, git, zsh, bubblewrap; a non-root user; no
secrets) and `compose.yaml` define one service, and `scripts/in_container.sh CMD...` runs any command in it with the
repository or any worktree (its git common directory too) bind-mounted at `/work`, under **hard limits** the kernel
enforces: `pids_limit` 4096, memory 12 GB (configurable), CPUs half the host's (configurable), `init`, a tmpfs on
`/tmp`, and no network (only the loopback device, which is all the suites and Playwright need; `--net` opts in).
The watchdog works inside (it reads `/proc` on Linux), as do the scripts that count threads with `ps -M`. CLAUDE.md
says when to use the container and what stays on the host; the overnight plan's gate text sends an agent's suite
runs through `scripts/in_container.sh` when Docker is up; `docs/DEVELOPMENT.md` says it for people.

## Acceptance tests

- `docker compose build` succeeds from a clean cache, and the image holds no secret (no host home, no tokens:
  the build context is only `pyproject.toml` and `uv.lock`).
- The unit suite and the browser suite pass inside under `scripts/suite_watch.py` with the same worker counts as
  the host; pass counts and wall times recorded below beside the host's.
- `tests/test_sandbox_attacks.py` runs inside on Linux (bwrap); its results are recorded below as they are,
  failures included.
- **The limits hold:** a thread bomb inside (bounded: stops at 10,000 threads or the first refusal) is refused at
  the `pids_limit`, and the host's thread count before, during and after is recorded and unchanged within noise.
- `tests/test_in_container.py`: the script's argument handling and the limits it passes (no Docker needed).

## Size budget

**300 net lines outside `tests/` and `docs/`** (Dockerfile, compose.yaml, the script, the watchdog's Linux path).

## Where it stopped

Everything is written; **nothing has run in a container yet.** The Docker Desktop engine did not come up in the 30
minutes it was polled (`docker info` every 30 s, 17:00 to 17:30), and the branch does not start it. Left, in order,
once the engine is up:

1. `scripts/in_container.sh true` (builds the image; first check that `ghcr.io/astral-sh/uv:0.12.19` and Playwright
   1.63.0's `install --with-deps` work on `python:3.12-slim-trixie`).
2. The unit and browser suites inside, against the host's figures below.
3. `tests/test_sandbox_attacks.py` inside. Unverified guess: bwrap needs `seccomp=unconfined` (user namespaces) and
   `systempaths=unconfined` (its own `/proc`), both set in `compose.yaml`; if Docker Desktop refuses either, say so.
   `scripts/latency_bench.py`'s `ps -axeww` is also untried on Linux procps.
4. The thread bomb, inside, with the host's thread count (`ps -M -A | wc -l`) before, during and after:
   `scripts/in_container.sh python3 -c "import threading as t; t.stack_size(65536); e = t.Event(); n = 0`
   `exec('try:\n while n < 10000: t.Thread(target=e.wait, daemon=True).start(); n += 1\nexcept RuntimeError as x: print(\"refused at\", n, x)\nelse: print(\"reached\", n)'); e.set()"`
5. Whether the bind mount is slow (a named volume for caches only if it is: the venv and uv cache are already in
   the image, outside `/work`).

Host figures (the 28-core Mac Studio, load 2 to 5, this branch, under `scripts/suite_watch.py`):

| Suite | Result | Wall | Peak threads | Peak RSS |
|---|---|---|---|---|
| unit, `-n 8` | 1623 passed, 13 skipped, 1 xfailed | 150 s | 385 | 2.6 GB |
| browser, `-n 4` | 200 passed, no skips | 463 s | 632 | 3.7 GB |
| `tests/test_sandbox_attacks.py` (seatbelt) | 30 passed, 1 xfailed | 15 s | 69 | 0.1 GB |

Size so far: about 108 net lines outside `tests/` and `docs/` (budget 300).
