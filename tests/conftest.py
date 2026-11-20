import fcntl
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

DISK = """
name = "t"

[[stock]]
name = "disk-used"
unit = "%"
systems = ["host"]

[[disturbance]]
name = "logs-written"
into = "disk-used"

[[flow]]
name = "cleaned"
from = "disk-used"

[[sensor]]
name = "disk-usage"
measures = "disk-used"
agent = "cleaner"

[[controller]]
name = "disk-under-80"
holds = "disk-used"
setpoint = "<= 80"
tolerance = 2
reads = ["disk-usage"]
drives = ["delete-old-files"]
agent = "cleaner"

[[valve]]
name = "delete-old-files"
flow = "cleaned"
agent = "cleaner"

[[agent]]
name = "cleaner"
kind = "program"
command = "python3 clean.py"
every = "1s"
"""


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: takes 10 s or more; started first in a parallel run, so it is not the last to finish")
    config.addinivalue_line("markers", "serial: holds a time bound only on a quiet machine: run alone in a parallel run")


# Known failures on Linux, each with its GAPS entry, until the `linuxfix` branch lands: expected to fail, not
# required to (xfail, strict=False), so any other failure still shows. Exact test ids only.
_SEGMENTS = ("The segmented log misses a seal within one mtime tick on Linux "
             "(docs/GAPS.md, Runtime: Linux: two bugs the dev container found, 1)")
_SANDBOX = "The attack suite asserts macOS behaviour here (docs/GAPS.md, Running code: ... five places)"
LINUX_KNOWN = {
    **{f"tests/test_store_conformance.py::test_{t}[segments]": _SEGMENTS for t in (
        "a_second_instance_threads_and_processes_lose_nothing", "a_transcripts_lines_skipped_by_prefix",
        "history_survives_a_reopen", "ids_get_prefix_dedup_and_causes", "items_of_items_and_globs",
        "order_n_newest_and_filters", "prune_and_generation", "replace_puts_the_snapshot_where_the_last_one_was",
        "valves_controllers_and_runs")},
    "tests/test_daemons.py::test_daemons_on_the_agents_api": "dash forks for sh -c, so the recorded pid is the shell's "
    "(docs/GAPS.md, Runtime: Linux: two bugs the dev container found, 2)",
    **{f"tests/test_sandbox_attacks.py::test_{t}": _SANDBOX for t in (
        "dns_is_denied_inside", "the_process_list_is_denied", "another_processes_environment_is_unreadable",
        "a_pid_hopping_process_does_not_outlive_the_run[kill]",
        "the_toolchain_is_the_interpreters_own_folders_never_a_whole_prefix")},
}


def _linux_known(items):
    if sys.platform.startswith("linux"):
        for it in items:
            if it.nodeid in LINUX_KNOWN:        # first, ahead of a test's own (macOS) strict xfail
                it.add_marker(pytest.mark.xfail(reason=LINUX_KNOWN[it.nodeid], strict=False), append=False)


def pytest_collection_modifyitems(config, items):
    _linux_known(items)
    _slow_first(items)


def _slow_first(items):
    """Under xdist (``-n N --dist worksteal``), each slow test at the head of a worker's first share, one per worker
    while they last: worksteal hands worker i the i-th of N even, contiguous shares and steals only from their tails,
    so no slow test waits behind another or starts last. Each worker reorders its own collection the same way."""
    n = int(os.environ.get("PYTEST_XDIST_WORKER_COUNT") or 0)
    slow = [it for it in items if it.get_closest_marker("slow")]
    if n < 2 or not slow:
        return
    rest = [it for it in items if not it.get_closest_marker("slow")]
    left, sizes = len(items), []
    for i in range(n):                                      # (as WorkStealingScheduling.check_schedule splits them)
        sizes.append(left // (n - i))
        left -= sizes[-1]
    shares = [[] for _ in range(n)]
    for j, it in enumerate(slow):
        shares[j % n].append(it)
    out = []
    for share, size in zip(shares, sizes, strict=True):
        take = max(0, size - len(share))
        out += share + rest[:take]
        rest = rest[take:]
    items[:] = out + rest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """A page test's pages and contexts are closed when it ends, however it ends: one that fails before its own
    ``pg.close()`` would otherwise leave its page open in the module's browser, and a run with many failures grows
    without bound. The browser and the module's other fixtures stay."""
    b = item.funcargs.get("browser") if hasattr(item, "funcargs") else None
    before = {id(c) for c in b.contexts} if b is not None else set()
    try:
        return (yield)
    finally:
        if b is not None:
            for c in [c for c in b.contexts if id(c) not in before]:
                try:
                    c.close()
                except Exception:               # (already closed, or the browser gone)
                    pass


_LOCK: tuple | None = None


def _lock() -> tuple:
    """This parallel run's lock file (one run: xdist's id for it, the same in every worker), or () when serial."""
    uid = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if not uid or not os.environ.get("PYTEST_XDIST_WORKER"):
        return ()
    return (open(Path(tempfile.gettempdir()) / f"ergostat-tests-{uid}.lock", "a+"),)   # noqa: SIM115  (the worker's life)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Under xdist, a test marked ``serial`` (a time bound that holds only on a quiet machine) runs with nothing else
    of this run alongside: every test holds the run's lock shared, a serial one holds it alone. A serial test waits
    for a moment when no other test runs (late in the run, as the others drain) and holds the rest back while it
    runs; it never holds them back while it waits, so a long test under way does not stall every worker."""
    global _LOCK
    if _LOCK is None:
        _LOCK = _lock()
    if not _LOCK:
        return (yield)
    fcntl.flock(_LOCK[0], fcntl.LOCK_EX if item.get_closest_marker("serial") else fcntl.LOCK_SH)
    try:
        return (yield)
    finally:
        fcntl.flock(_LOCK[0], fcntl.LOCK_UN)


@pytest.fixture(autouse=True)
def _not_stopping():
    """``runner.STOPPING`` is process-wide, set by any engine's close: a test that closed one must not leave it set
    for whichever test its worker runs next (the order differs between workers and from a serial run)."""
    if "ergostat.runner" in sys.modules:
        sys.modules["ergostat.runner"].STOPPING.clear()
    yield


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def repo(tmp_path):
    """A repository with the disk model; write more files with repo.write(name, text)."""
    d = tmp_path / "repo"
    d.mkdir()
    (d / "ergostat.toml").write_text(DISK)

    class Repo:
        path = d

        def write(self, name, text):
            p = d / name
            p.write_text(textwrap.dedent(text))
            return p
    return Repo()


@pytest.fixture
def project(repo):
    from ergostat import model
    from ergostat.store import Project
    return Project(model.load(repo.path))


def here() -> Path:
    return Path(__file__).parent
