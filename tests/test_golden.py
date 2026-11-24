"""tests/golden.py, with no browser: a reference that differs fails with a diff naming the root it is in, a missing
one is written and fails, the update mode writes, and the regenerate command runs the golden tests in that mode and
says which references changed (dev/records/golden-file-ui-tests.md)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests import golden

DRAWN = """section.cell aria-label="first"
  h3 "one"
  p "words"
  span "a"
  span "b"
  span "c"
section.cell aria-label="second"
  h3 "two"
  p "words"
"""


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(golden, "GOLDEN", tmp_path / "golden")
    monkeypatch.delenv(golden.ENV, raising=False)
    return tmp_path / "golden"


def test_the_same_drawing_passes(here):
    here.mkdir()
    (here / "page.txt").write_text(DRAWN)
    golden.compare("page", DRAWN.rstrip("\n"))


def test_a_change_fails_with_a_diff_that_names_its_root_and_the_command(here):
    here.mkdir()
    (here / "page.txt").write_text(DRAWN)
    with pytest.raises(pytest.fail.Exception) as got:
        golden.compare("page", DRAWN.replace('"two"', '"2"'))
    said = str(got.value)
    assert '-  h3 "two"\n+  h3 "2"' in said
    assert '@@ -5,5 +5,5 @@ section.cell aria-label="first"' in said    # git's hunk header: the line above at column 0
    assert "python -m tests.golden" in said
    assert (here / "page.txt").read_text() == DRAWN                          # the reference is left as it was


def test_a_missing_reference_is_written_and_fails(here):
    with pytest.raises(pytest.fail.Exception, match="had no reference"):
        golden.compare("page", DRAWN)
    assert (here / "page.txt").read_text() == DRAWN
    golden.compare("page", DRAWN)


@pytest.mark.parametrize("drawn", [None, "", "  \n"])
def test_nothing_drawn_fails_and_writes_nothing(here, monkeypatch, drawn):
    monkeypatch.setenv(golden.ENV, "update")
    with pytest.raises(pytest.fail.Exception, match="nothing was drawn"):
        golden.compare("page", drawn)
    assert not here.exists()


def test_the_update_mode_writes_what_was_drawn(here, monkeypatch):
    here.mkdir()
    (here / "page.txt").write_text(DRAWN)
    monkeypatch.setenv(golden.ENV, "update")
    golden.compare("page", DRAWN.replace("one", "1"))
    assert (here / "page.txt").read_text() == DRAWN.replace("one", "1")


@pytest.mark.parametrize("name", ["", "../x", "a/b", "a.txt"])
def test_a_reference_name_stays_in_the_folder(here, name):
    with pytest.raises(ValueError):
        golden.reference(name)


def test_the_regenerate_command_runs_the_golden_tests_in_update_mode_and_says_what_changed(here, capsys):
    here.mkdir()
    (here / "kept.txt").write_text("same\n")
    (here / "page.txt").write_text(DRAWN)
    asked = []

    def run(cmd, cwd, env):
        asked.append((cmd, env[golden.ENV]))
        (here / "page.txt").write_text(DRAWN.replace("one", "1"))
        (here / "new.txt").write_text("new\n")
        return SimpleNamespace(returncode=0)

    assert golden.regenerate(run=run) == 0
    cmd, mode = asked[0]
    assert mode == "update" and cmd[-1] == "tests/test_golden_pages.py" and "no:xdist" in cmd
    out = capsys.readouterr().out
    assert "new: tests/golden/new.txt" in out and "changed: tests/golden/page.txt" in out and "kept" not in out
    assert "2 of 3 references changed" in out


def test_the_regenerate_command_says_when_the_tests_did_not_pass(here, capsys):
    assert golden.regenerate(["tests/test_golden_pages.py::x"],
                             run=lambda cmd, cwd, env: SimpleNamespace(returncode=1)) == 1
    assert "ended with code 1" in capsys.readouterr().err


def test_every_golden_test_file_is_in_the_browser_suite():
    """A golden test the merge queue never runs could not fail on an unintended change (lesson 9)."""
    import tomllib
    suites = tomllib.loads((golden.ROOT / "dev" / "factory.toml").read_text())["suites"]
    for f in golden.TESTS:
        assert f in suites["browser"].split()
        assert f in suites["browser_paths"]
    assert "tests/golden/*" in suites["browser_paths"] and "tests/golden.py" in suites["browser_paths"]
