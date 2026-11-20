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

Done, with Linux findings left for their own branches. The engine was down for the first session (17:00 to 17:30);
the owner started it, and the branch was rebased onto origin/main (145d00e) and verified at 21:20 to 22:10.

- **Build:** 74 s from a clean cache; Python 3.12.16, uv 0.12.19, Playwright 1.63.0's Chromium; pillow and numpy
  added to the cache after image-squeeze's `bin/py` failed offline.
- **Limits proved:** a thread bomb refused at 4,094 threads (`pids.max` 4096); a memory bomb OOM-killed at
  1,792 MB under a 2g cap; the host's threads 2,818 before, 2,856 peak, 2,807 after (others' suites running).
- **Suites inside:** unit 1698 passed, 12 failed, 14 skipped (164 s); browser 217 passed, 1 failed, no skips
  (565 s), the failure being a test writing pictures beside the checkout (`/` inside; `SPLIT_SHOTS` now set).
  Host figures and the full table: docs/DEVELOPMENT.md, *Measured*.
- **Linux findings (docs/GAPS.md):** the segmented log misses seals within one mtime tick (5 to 6 conformance cases);
  dash's fork makes a daemon's recorded pid the shell's; the sandbox attack suite passes 26 of 31 under bwrap, and the
  five failures assert macOS behaviour (probed: no escape). Fixing them is ergostat's work, not this branch's.
- **Not done:** the benchmarks and the layout corpus were not run inside (documented, not measured).
