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
