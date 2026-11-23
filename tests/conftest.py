import contextlib
import fcntl
import json
import multiprocessing.spawn
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest

_DEV_BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
_preparation = multiprocessing.spawn.get_preparation_data


def _without_dev_bin(name):
    """What a spawned process starts from, less dev/bin: many tests put it on sys.path, a spawned process inherits that,
    and there dev/bin/queue.py hides the standard library's `queue`, which multiprocessing itself imports."""
    data = _preparation(name)
    data["sys_path"] = [x for x in data.get("sys_path", []) if not x or Path(x).resolve() != _DEV_BIN]
    return data


multiprocessing.spawn.get_preparation_data = _without_dev_bin

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
# the disk model with one goal of each word, once disk-usage reads 70: holding (disk-under-80), off (disk-under-50),
# open (disk-cleaned-nightly: its valve drains another stock) and unknown (inodes-under-90, never read)
FOUR_GOALS = DISK + """
[[controller]]
name = "disk-under-50"
holds = "disk-used"
setpoint = "<= 50"
reads = ["disk-usage"]
drives = ["delete-old-files"]
agent = "cleaner"

[[stock]]
name = "inodes-used"
unit = "%"
systems = ["host"]

[[flow]]
name = "inodes-freed"
from = "inodes-used"

[[sensor]]
name = "inode-usage"
measures = "inodes-used"
agent = "cleaner"

[[controller]]
name = "inodes-under-90"
holds = "inodes-used"
setpoint = "<= 90"
reads = ["inode-usage"]
drives = ["free-inodes"]
agent = "cleaner"

[[valve]]
name = "free-inodes"
flow = "inodes-freed"
agent = "cleaner"

[[controller]]
name = "disk-cleaned-nightly"
holds = "inodes-used"
setpoint = "<= 95"
reads = ["inode-usage"]
drives = ["delete-old-files"]
agent = "cleaner"
"""


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: takes 10 s or more; started first in a parallel run, so it is not the last to finish")
    config.addinivalue_line("markers", "serial: holds a time bound only on a quiet machine: run alone in a parallel run")
    if os.environ.get("ERGOSTAT_COVERAGE"):            # the line tracer, only when asked for (dev/README.md, Coverage)
        from tests import coverage_lines
        coverage_lines.register(config)


def pytest_collection_modifyitems(config, items):
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
    """Each test's own ergostat home, and nothing inherited from an ergostat running these tests: a suite run as a
    block of an engine (the factory's merge queue) inherits its ERGOSTAT_SOCKET, ERGOSTAT_RUN and the rest, and a
    test's CLI would then talk to that engine instead of its own."""
    for k in [k for k in os.environ if k.startswith("ERGOSTAT_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("ERGOSTAT_CALL_RETRY", "5")    # a run outliving its test's engine gives up soon (rs-calls)
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


class FactoryState:
    """scripts/factory_fixture.py's state directory: ``model`` (the repository), ``home`` (its ERGOSTAT_HOME),
    ``record`` (its state directory), ``stats`` (what the script said it wrote), ``digests`` (each record file's
    sha256 as built), ``project()``, and ``serve()``: a page server on it, a context manager giving its URL."""

    def __init__(self, out: Path, stats: dict, digests: dict | None = None):
        import hashlib
        self.model, self.home, self.record, self.stats = out / "model", out / "home", Path(stats["record"]), stats
        self.digests = digests if digests is not None else {
            str(f.relative_to(self.record)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(self.record.rglob("*")) if f.is_file() and f.name != "repo.json"}

    def project(self):
        from ergostat import model
        from ergostat.store import Project
        return Project(model.load(self.model), self.record, note=False)

    @contextlib.contextmanager
    def serve(self):
        from http.server import ThreadingHTTPServer

        from ergostat.web.server import handler
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.project()))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.server_address[1]}"
        finally:
            srv.shutdown()
            srv.server_close()


def clean_env(**more: str) -> dict:
    """This process's environment without what an ergostat running the suite gave it (its socket, run, home: as the
    ``home`` fixture clears for a test), but the watchdog's tag; a session fixture is set up before ``home`` runs."""
    return {**{k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_") or k == "ERGOSTAT_SUITE_WATCH"}, **more}


def build_factory_state(out: Path, *args: str) -> dict:
    got = subprocess.run([sys.executable, str(here().parent / "scripts/factory_fixture.py"), str(out), *args],
                         check=True, capture_output=True, text=True, timeout=900, env=clean_env())
    return json.loads(got.stdout)


@pytest.fixture(scope="session")
def factory_state(request, tmp_path_factory) -> FactoryState:
    """A factory-size state directory (seed 1, its record ending at this hour; tests/README.md), built once a run: under
    xdist by the first worker to ask, in the run's own temporary root, while the others wait on its lock, so a parallel
    run holds one copy, not one a worker. Its digests are taken as built. Skipped under a ``-m fast`` run."""
    if "fast" in (request.config.getoption("markexpr") or ""):
        pytest.skip("the factory-size state directory is not built in a -m fast run")
    root = tmp_path_factory.getbasetemp()
    root = root.parent if os.environ.get("PYTEST_XDIST_WORKER") else root     # (a worker's is <run's root>/<worker id>)
    said = root / "factory-state.json"
    with open(root / "factory-state.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)                    # (let go as the file closes, the build failed or not)
        if not said.exists():
            out = Path(tempfile.mkdtemp(prefix="factory-", dir=root)) / "state"
            built = FactoryState(out, build_factory_state(out, "--seed", "1", "--end", str(int(time.time()) // 3600 * 3600)))
            said.write_text(json.dumps({"out": str(out), "stats": built.stats, "digests": built.digests}))
        got = json.loads(said.read_text())
    return FactoryState(Path(got["out"]), got["stats"], got["digests"])
