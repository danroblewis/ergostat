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
so git works inside. `--print` shows the command without running it.

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
    tests/test_page_refresh.py
# every example, its pages checked with Playwright
scripts/in_container.sh uv run --with playwright==1.63.0 python scripts/demo_check.py
# the benchmarks (results under .out/, which git ignores)
scripts/in_container.sh uv run python scripts/scale_bench.py check 10 100 300 1000 --work /work/.out/scale
scripts/in_container.sh uv run python scripts/latency_bench.py synth 1 50 100 500 --label container
scripts/in_container.sh uv run python scripts/daemon_bench.py 20 170 --mode daemon --minutes 6.5 --work /work/.out/daemon
# the layout corpus
scripts/in_container.sh uv run --with playwright==1.63.0 python -m tests.layout_corpus /work/.out/corpus --generated 300
```

Write results under `/work` (here `/work/.out/`) to keep them: everything else in the container, `/tmp` included,
is gone when it ends.

## What stays on your computer

- The macOS sandbox tests: `tests/test_sandbox_attacks.py` tests `sandbox-exec` only on macOS; in the container it
  tests the Linux sandbox (bubblewrap). Run it in both places when the sandbox changes.
- Anything that needs your real credentials or services (an AI agent's sign-in, a real ticket system). Nothing of
  your home folder is in the container, by design.
- Running ergostat for real (`ergostat run` on your projects): the container is for development.
