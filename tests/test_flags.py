"""Feature flags (ergostat/flags.py; docs/DEVELOPMENT.md, Feature flags): a flagged path is unreachable while its
flag is off, its tests skip, and the change that turns it on runs the full checks (scripts/affected_tests.py, the
merge queue's browser step)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ergostat import flags

ROOT = Path(__file__).resolve().parent.parent
OFF = json.dumps({"board": {"on": False, "about": "a new board page"}})
ON = json.dumps({"board": {"on": True, "about": "a new board page"}})


def git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}   # (git sees only the fixture)
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


def branch(tmp: Path, start: dict[str, str], change: dict[str, str | None]) -> Path:
    """A repository whose main holds ``start`` and whose branch factory/x makes ``change`` (None: deleted)."""
    repo = tmp / "repo"
    for files in (start, change):
        for rel, text in files.items():
            p = repo / rel
            if text is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        if files is start:
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        else:
            git(repo, "checkout", "-qb", "factory/x")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "start" if files is start else "change")
    return repo


def gated(path: Path) -> list[str]:
    """A stand-in for code behind the flag: what it reached."""
    reached = []
    if flags.on("board", path):
        reached.append("board")
    return reached


def test_a_flagged_off_path_is_unreachable_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv(flags.ENV, raising=False)
    decl = tmp_path / "flags.json"
    decl.write_text(OFF)
    assert gated(decl) == []                                            # declared off: never reached
    monkeypatch.setenv(flags.ENV, "other, board")
    assert gated(decl) == ["board"]                                     # turned on for this process alone
    decl.write_text(ON)
    monkeypatch.delenv(flags.ENV)
    assert gated(decl) == ["board"]
    for bad in ("", "{", "[]", '{"Board": {"on": true, "about": "x"}}', '{"board": {"on": "yes", "about": "x"}}',
                '{"board": {"on": 1, "about": "x"}}', '{"board": {"on": true}}', '{"board": {"on": true, "about": " "}}',
                '{"board": {"on": true, "about": "x", "more": 1}}'):
        decl.write_text(bad)
        monkeypatch.setenv(flags.ENV, "board")
        assert gated(decl) == [], bad                                   # unreadable: off, the env var too
    assert gated(tmp_path / "none.json") == []                          # (no file at all)
    decl.write_text(OFF)
    with pytest.raises(flags.UnknownFlag):                              # a typo is never read as off or on
        flags.on("bored", decl)
    with pytest.raises(flags.UnknownFlag):                              # the env var never declares one
        monkeypatch.setenv(flags.ENV, "bored")
        flags.on("bored", decl)
    # the shipped file parses (parse raises otherwise: a malformed file would read every flag as off and skip every
    # flagged test silently); what it declares is the tree's own business, so a change may declare a flag
    assert isinstance(flags.parse(flags.FILE.read_text()), dict)
    assert flags.REL == str(flags.FILE.relative_to(ROOT))


PLAIN = Path(flags.__file__)                                   # (a file that drives no browser)


class Item:
    def __init__(self, *marks, path: Path = PLAIN, fixturenames: tuple = ()):
        self.nodeid, self.marks, self.added = "tests/test_x.py::t", list(marks), []
        self.path, self.fixturenames = path, fixturenames

    def iter_markers(self, name):
        return [m for m in self.marks if m.name == name]

    def add_marker(self, m):
        self.added.append(m)


def test_a_flagged_test_is_skipped_while_off_and_runs_when_on(tmp_path, monkeypatch):
    from tests.conftest import _flagged_off
    decl = tmp_path / "flags.json"
    monkeypatch.setattr(flags, "FILE", decl)
    monkeypatch.delenv(flags.ENV, raising=False)
    decl.write_text(OFF)
    off, plain = Item(pytest.mark.flag("board").mark), Item(pytest.mark.slow.mark)
    _flagged_off([off, plain])
    assert [m.name for m in off.added] == ["skip"] and "board is off" in off.added[0].kwargs["reason"]
    assert plain.added == []
    for on in (ON, None):                                               # declared on, or on for the run
        decl.write_text(on or OFF)
        if on is None:
            monkeypatch.setenv(flags.ENV, "board")
        it = Item(pytest.mark.flag("board").mark)
        _flagged_off([it])
        assert it.added == []
    for bad in (pytest.mark.flag("bored").mark, pytest.mark.flag().mark, pytest.mark.flag("board", "x").mark):
        with pytest.raises(pytest.UsageError):                          # never a silent skip
            _flagged_off([Item(bad)])


def test_a_flagged_browser_test_stops_the_run(tmp_path, monkeypatch):
    """The queue and the daily run count a skipped page test as a failure, and no build runs page tests with a
    branch's flags on: a flag marker on a test that drives a browser stops the run, never a skip."""
    from tests.conftest import _flagged_off
    decl = tmp_path / "flags.json"
    decl.write_text(OFF)
    monkeypatch.setattr(flags, "FILE", decl)
    monkeypatch.setenv(flags.ENV, "board")                              # (on, too: refused either way)
    page_file = tmp_path / "test_page.py"
    page_file.write_text("pw = pytest.importorskip('play" "wright.sync_api')\n")
    mark = pytest.mark.flag("board").mark
    for it in (Item(mark, fixturenames=("home", "page")), Item(mark, fixturenames=("browser",)),
               Item(mark, path=page_file), Item(mark, path=tmp_path / "gone.py")):
        with pytest.raises(pytest.UsageError, match="drives a browser"):
            _flagged_off([it])
    for it in (Item(mark, fixturenames=("home",)), Item(pytest.mark.slow.mark, path=page_file)):
        _flagged_off([it])                                              # a unit test, or no flag: as before
        assert it.added == []
    # a real run: a flagged page test (an undeclared flag, so nothing else could pass it) stops the run, rc 4, no skip
    page_file.write_text("import pytest\n\n\n@pytest.mark.flag('none-such')\ndef test_p(page):\n    pass\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "tests.conftest", "-p", "no:cacheprovider",
                        str(page_file)], cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 4 and "drives a browser" in r.stdout + r.stderr, r.stdout + r.stderr
    assert "SKIPPED" not in r.stdout


def test_turning_a_flag_on_is_found(tmp_path):
    assert flags.turned_on(None, None) == [] and flags.turned_on(None, OFF) == [] and flags.turned_on(OFF, OFF) == []
    assert flags.turned_on(OFF, ON) == ["flag board turned on"] and flags.turned_on(None, ON) == ["flag board turned on"]
    assert flags.turned_on(ON, ON) == [] and flags.turned_on(ON, None) == [] and flags.turned_on(ON, "{}") == []
    assert flags.turned_on(OFF, "{}") == ["flag board removed while off"]
    assert flags.turned_on(OFF, None) == ["flag board removed while off"]
    assert flags.turned_on("{", ON) == ["flag board turned on"] and flags.turned_on("{", OFF) == []
    assert flags.turned_on(OFF, "{")[0].startswith("ergostat/flags.json unreadable")
    repo = branch(tmp_path, {flags.REL: OFF, "a.py": ""}, {flags.REL: ON})
    assert flags.turned_on_between(repo, "main") == ["flag board turned on"]
    assert flags.turned_on_between(repo, "main", "main") == []
    assert flags.turned_on_between(repo, "no-such-ref")[0].startswith("ergostat/flags.json not read")


def affected(repo: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != flags.ENV}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "affected_tests.py"), "--", "sh", "-c",
                           'echo "flags=$ERGOSTAT_FLAGS" "$@"', "given"], cwd=repo, capture_output=True, text=True,
                          timeout=60, env=env)


def test_turning_a_flag_on_requires_the_full_suite(tmp_path):
    start = {flags.REL: OFF, "ergostat/foo.py": "x = 1\n", "tests/test_foo.py": ""}
    for case, change in (("on", {flags.REL: ON}), ("removed", {flags.REL: "{}"}), ("deleted", {flags.REL: None}),
                         ("unreadable", {flags.REL: "{"}), ("on-and-code", {flags.REL: ON, "ergostat/foo.py": "x = 2\n"})):
        r = affected(branch(tmp_path / case, start, change))
        assert r.returncode == 0, (case, r.stderr)
        assert r.stdout.splitlines()[-1] == "flags=", case                 # nothing selected: the whole suite
        assert "the full suite" in r.stdout, case
    # a branch that declares a new flag, off, runs its selection with that flag on, so its flagged tests run there
    r = affected(branch(tmp_path / "new", {"ergostat/foo.py": "x = 1\n", "tests/test_foo.py": ""},
                        {flags.REL: OFF, "ergostat/foo.py": "x = 2\n"}))
    assert r.returncode == 0 and r.stdout.splitlines()[-1] == "flags=board tests/test_foo.py", r.stdout
    # one whose flag stays off and declared selects as before, nothing turned on
    r = affected(branch(tmp_path / "off", start, {"ergostat/foo.py": "x = 2\n"}))
    assert r.returncode == 0 and r.stdout.splitlines()[-1] == "flags= tests/test_foo.py", r.stdout


def test_turning_a_flag_on_runs_browser_in_the_queue(tmp_path):
    from tests.test_queue_host import queue_module  # (dev/bin on the path, never the stdlib's queue)
    queue = queue_module()
    cfg = {"suites": {"browser_paths": ["ergostat/web/**"]}}
    repo = branch(tmp_path / "on", {flags.REL: OFF, "dev/a.py": ""}, {flags.REL: ON})
    assert queue.browser_wanted(cfg, repo, "main") is True                # no browser path touched, but turned on
    repo = branch(tmp_path / "off", {flags.REL: "{}", "dev/a.py": ""}, {flags.REL: OFF, "dev/a.py": "x\n"})
    assert queue.browser_wanted(cfg, repo, "main") is False               # declared off: as before
    repo = branch(tmp_path / "bad", {flags.REL: OFF, "dev/a.py": ""}, {flags.REL: "{"})
    assert queue.browser_wanted(cfg, repo, "main") is True                # unreadable: the worst case
