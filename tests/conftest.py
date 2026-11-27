import contextlib
import fcntl
import json
import multiprocessing.spawn
import os
import shutil
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
    config.addinivalue_line("markers", "flag(name): tests a path behind the feature flag NAME: skipped while it is off "
                                       "(ergostat/flags.py)")
    if os.environ.get("ERGOSTAT_COVERAGE"):            # the line tracer, only when asked for (dev/README.md, Coverage)
        from tests import coverage_lines
        coverage_lines.register(config)
    _vm_start(config)


def pytest_collection_modifyitems(config, items):
    _flagged_off(items)
    _broken_by_redesign(items)
    _slow_first(items)


BROKEN = Path(__file__).resolve().parent / "broken_by_redesign.txt"
BROKEN_REASON = "broken by the systems/projections redesign (tests/broken_by_redesign.txt)"


def broken_by_redesign(path: Path = BROKEN) -> list[str]:
    """The node ids in tests/broken_by_redesign.txt: one per line; a line starting with ``#`` is a comment (only a whole
    line: a node id may hold a ``#``), blank lines ignored."""
    if not path.exists():
        return []
    return [x for line in path.read_text().splitlines() if (x := line.strip()) and not x.startswith("#")]


def _broken_by_redesign(items):
    """Each test listed in tests/broken_by_redesign.txt skipped (the owner, 2026-11-26: the redesign breaks them; left
    broken for now); a listed file (no ``::``), every test in it. A listed id that names no test is ignored here;
    tests/test_broken_by_redesign.py fails on it."""
    listed = set(broken_by_redesign())
    for it in items:
        if it.nodeid in listed or it.nodeid.split("::", 1)[0] in listed:
            it.add_marker(pytest.mark.skip(reason=BROKEN_REASON))


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    """A listed file that does not even import (it loads a broken model at module level) is skipped, not an error."""
    report = yield
    if report.failed and isinstance(collector, pytest.Module) and collector.nodeid in set(broken_by_redesign()):
        report.outcome = "skipped"
        report.longrepr = (str(collector.path), 0, f"Skipped: {BROKEN_REASON}")
        report.result = []
    return report


def _flagged_off(items):
    """Each test marked ``flag(NAME)`` skipped while that flag is off (declared off and not in ERGOSTAT_FLAGS). A
    marker naming no declared flag stops the run: never read as off (a skip) or on. So does one on a test that drives a
    browser: the merge queue and the daily run count any skipped page test as a failure, and no build runs page tests
    with a branch's flags on, so a flagged browser test would be red while off and untested before landing."""
    from ergostat import flags
    for it in items:
        for m in it.iter_markers("flag"):
            name = m.args[0] if len(m.args) == 1 and not m.kwargs else None
            if _drives_browser(it):
                raise pytest.UsageError(f"{it.nodeid}: flag({name!r}) on a test that drives a browser: flagged "
                                        "browser tests are not supported (docs/DEVELOPMENT.md, Feature flags)")
            try:
                off = not isinstance(name, str) or not flags.on(name)
            except flags.UnknownFlag:
                raise pytest.UsageError(f"{it.nodeid}: flag({name!r}) is not declared in {flags.REL}") from None
            if not isinstance(name, str):
                raise pytest.UsageError(f"{it.nodeid}: the flag marker takes one name: flag('NAME')")
            if off:
                it.add_marker(pytest.mark.skip(reason=f"feature flag {name} is off"))


def _drives_browser(it) -> bool:
    """Whether a test drives a browser: it asks for a ``browser`` or ``page`` fixture, or its file names playwright
    (an import, importorskip, or a helper's call). A file that cannot be read counts as one (the worst case)."""
    if {"browser", "page"} & set(getattr(it, "fixturenames", ())):
        return True
    try:
        return "playwright" in Path(it.path).read_text(errors="replace")
    except (OSError, TypeError, AttributeError):
        return True


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


VM_BIN = shutil.which("victoria-metrics") or shutil.which("victoria-metrics-prod") or \
    next((b for b in ("/opt/homebrew/bin/victoria-metrics", "/usr/local/bin/victoria-metrics") if os.access(b, os.X_OK)), None)
VM_ENV = "VM_FOR_ERGOSTAT_TESTS"   # the run's VictoriaMetrics, for its workers (not ERGOSTAT_: the home fixture clears those)
_VM: dict = {}                 # this process's VictoriaMetrics: {"url": ...} (clean_env passes it on); the run's: "stop"


@contextlib.contextmanager
def vm_server(d: Path, retention: str = "100y"):
    """A VictoriaMetrics started from VM_BIN with its data in ``d``, keeping ``retention``, answering at the URL it
    gives, stopped (and its data removed) after. The readings' only store (NOTES.md, 2026-11-25): none is a failure,
    never a skip."""
    from ergostat import storage
    from tests.ports import free_port
    if not VM_BIN:
        raise pytest.UsageError("victoria-metrics is not installed (brew install victoriametrics; the dev image has it): "
                                "every reading is kept there, and the suite starts its own")
    d.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with open(d / "vm.log", "w") as log:
        proc = subprocess.Popen([VM_BIN, f"-storageDataPath={d / 'data'}", f"-httpListenAddr=127.0.0.1:{port}",
                                 f"-retentionPeriod={retention}", "-search.disableCache", "-search.latencyOffset=0s",
                                 "-memory.allowedBytes=512MB", "-loggerLevel=ERROR"],
                                stdout=subprocess.DEVNULL, stderr=log, start_new_session=True,
                                env={**os.environ, "GOMAXPROCS": "4"})
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            if storage.answers(url):
                break
            assert proc.poll() is None, (d / "vm.log").read_text()[-2000:]
            time.sleep(0.1)
        else:
            raise pytest.UsageError("VictoriaMetrics did not answer within 30 s")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        shutil.rmtree(d, ignore_errors=True)


def _vm_start(config) -> None:
    """One VictoriaMetrics for the whole run, started by the process that runs it (under xdist, the controller,
    before its workers start, so they inherit its address in VM_ENV): one server, not one a worker, keeps a parallel
    run within the watchdog's memory bound. Each test's record has a project label of its own there."""
    if os.environ.get("PYTEST_XDIST_WORKER") or os.environ.get(VM_ENV):
        return
    cm = vm_server(Path(tempfile.mkdtemp(prefix="ergostat-tests-vm-")))
    os.environ[VM_ENV] = cm.__enter__()
    _VM["stop"] = cm


def _vm_stop() -> None:
    cm = _VM.pop("stop", None)
    if cm is not None:
        os.environ.pop(VM_ENV, None)
        cm.__exit__(None, None, None)


def pytest_unconfigure(config):
    _vm_stop()


@pytest.fixture(scope="session", autouse=True)
def vm():
    """This run's VictoriaMetrics (``_vm_start``), its URL: every test's record keeps its readings there, each under
    its own ``project`` label (its home's: storage.metrics_project). Named in the environment (ERGOSTAT_METRICS_URL)
    before any other fixture, so a module's fixture, and every process a test starts, writes there too."""
    url = os.environ[VM_ENV]
    _VM["url"] = url
    was = os.environ.get("ERGOSTAT_METRICS_URL")
    os.environ["ERGOSTAT_METRICS_URL"] = url
    try:
        yield url
    finally:
        _VM.pop("url", None)
        if was is None:
            os.environ.pop("ERGOSTAT_METRICS_URL", None)
        else:
            os.environ["ERGOSTAT_METRICS_URL"] = was


def victoria(d: Path):
    """A store of readings in this process's VictoriaMetrics under a project label of its own (a test's stand-alone
    store, beside any Project's)."""
    import uuid

    from ergostat.victoria import Victoria
    Path(d).mkdir(parents=True, exist_ok=True)
    return Victoria(_VM["url"], Path(d), project=f"test-{uuid.uuid4().hex[:10]}")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch, vm):
    """Each test's own ergostat home, and nothing inherited from an ergostat running these tests: a suite run as a
    block of an engine (the factory's merge queue) inherits its ERGOSTAT_SOCKET, ERGOSTAT_RUN and the rest, and a
    test's CLI would then talk to that engine instead of its own. Its readings go to this process's VictoriaMetrics
    (``vm``), under a project label of this home's alone."""
    for k in [k for k in os.environ if k.startswith("ERGOSTAT_") and k != "ERGOSTAT_FLAGS"]:   # (flags: as collected)
        monkeypatch.delenv(k)
    monkeypatch.setenv("ERGOSTAT_CALL_RETRY", "5")    # a run outliving its test's engine gives up soon (rs-calls)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ERGOSTAT_METRICS_URL", vm)
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


_FACTORY_READ: set = set()     # (record, VictoriaMetrics) whose readings this process has made sure of


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
        p = Project(model.load(self.model), self.record, note=False)
        self.readings(p)
        return p

    def readings(self, p) -> None:
        """Its readings in this process's VictoriaMetrics (the build wrote them to its builder's: under xdist, maybe
        another worker's), written once a process from what the build kept (readings.json.gz)."""
        key = (str(self.record), _VM.get("url"))
        if key in _FACTORY_READ or not (self.model.parent / "readings.json.gz").exists():
            return
        import gzip
        if p.measurements.first_time() is None:
            rows = json.loads(gzip.decompress((self.model.parent / "readings.json.gz").read_bytes()))
            p.measurements.add_many([tuple(r) for r in rows])
        _FACTORY_READ.add(key)

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
    return {**{k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_") or k == "ERGOSTAT_SUITE_WATCH"},
            **({"ERGOSTAT_METRICS_URL": _VM["url"]} if "url" in _VM else {}), **more}


def build_factory_state(out: Path, *args: str) -> dict:
    got = subprocess.run([sys.executable, str(here().parent / "scripts/factory_fixture.py"), str(out), *args],
                         check=True, capture_output=True, text=True, timeout=900, env=clean_env())
    return json.loads(got.stdout)


@pytest.fixture(scope="session")
def factory_state(request, tmp_path_factory, vm) -> FactoryState:
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
