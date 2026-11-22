"""A line tracer for the unit suite (dev/README.md, *Coverage*), as a pytest plugin: off unless ``ERGOSTAT_COVERAGE``
names a folder (tests/conftest.py registers it then), and with no package: Python 3.12's ``sys.monitoring``, a LINE
event per line of code, each line disabled after its first hit, so a line costs one call however often it runs.

It records the lines run in this process of the files under ``ergostat/``, ``dev/bin/`` and ``scripts/``, and which
of those files were imported here, and each pytest process (each xdist worker, or the one process of a serial run)
writes them to ``<folder>/lines-<worker>.json`` when it ends. xdist's controller runs no test and writes nothing.
``scripts/coverage_report.py <folder>`` makes the report; the statements (the denominator) come from the files'
``ast`` there, so they do not depend on what ran.

Not seen: code run only in a child process (the daemons, ``python -m ergostat`` under a subprocess, a dev/bin program
called by its path)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOTS = ("ergostat", "dev/bin", "scripts")
NAME = "ergostat-coverage"                     # the tool's name in sys.monitoring
mon = sys.monitoring


class Tracer:
    """The lines run of the files under ``roots`` (paths from ``root``), by a sys.monitoring tool of its own."""

    def __init__(self, root: Path = ROOT, roots: tuple[str, ...] = ROOTS, tool: int = mon.COVERAGE_ID):
        self.root, self.tool = root.resolve(), tool
        self.under = tuple(str(self.root / r) + os.sep for r in roots)
        self.files: dict[str, str | None] = {}         # a code object's file name -> its path from root, or None
        self.lines: dict[str, set[int]] = {}

    def rel(self, filename: str) -> str | None:
        real = os.path.realpath(filename)
        return str(Path(real).relative_to(self.root)) if real.startswith(self.under) and real.endswith(".py") else None

    def _line(self, code, line: int):
        f = code.co_filename
        rel = self.files[f] if f in self.files else self.files.setdefault(f, self.rel(f))
        if rel is not None:
            self.lines.setdefault(rel, set()).add(line)
        return mon.DISABLE                              # (this line of this code object: never again)

    def start(self) -> Tracer:
        mon.use_tool_id(self.tool, NAME)                # (raises if the id is taken: never two tracers on one id)
        mon.register_callback(self.tool, mon.events.LINE, self._line)
        mon.set_events(self.tool, mon.events.LINE)
        return self

    def stop(self) -> None:
        mon.set_events(self.tool, mon.events.NO_EVENTS)
        mon.register_callback(self.tool, mon.events.LINE, None)
        mon.free_tool_id(self.tool)

    def imported(self) -> set[str]:
        """The traced files this process imported (as a module, or run a line of): a file in none of the workers'
        is reached by the tests, if at all, only in a child process."""
        got = {self.rel(f) for m in list(sys.modules.values()) if isinstance(f := getattr(m, "__file__", None), str)}
        return {r for r in got if r} | set(self.lines)

    def dump(self, folder: Path, worker: str) -> Path:
        out = {"worker": worker, "workers": int(os.environ.get("PYTEST_XDIST_WORKER_COUNT") or 0),
               "run": os.environ.get("PYTEST_XDIST_TESTRUNUID") or "",
               "lines": {f: sorted(ls) for f, ls in sorted(self.lines.items())}, "imported": sorted(self.imported())}
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / f"lines-{worker}.json"
        tmp = p.with_suffix(".new")
        tmp.write_text(json.dumps(out))
        tmp.replace(p)                                  # (whole, or not there: a reader never sees half a file)
        return p


class Plugin:
    def __init__(self, tracer: Tracer, folder: Path, worker: str):
        self.tracer, self.folder, self.worker = tracer, folder, worker

    def pytest_unconfigure(self, config):
        self.tracer.stop()
        self.tracer.dump(self.folder, self.worker)


def register(config) -> Plugin | None:
    """The plugin, started and registered, when ERGOSTAT_COVERAGE is set (read now: each test's ``home`` fixture
    clears the ERGOSTAT_ variables), and this process runs tests; else None, and nothing is registered."""
    folder = os.environ.get("ERGOSTAT_COVERAGE")
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not folder or (not worker and getattr(config.option, "numprocesses", None)):    # (xdist's controller)
        return None
    plugin = Plugin(Tracer().start(), Path(folder).resolve(), worker or "main")
    config.pluginmanager.register(plugin, NAME)
    return plugin
