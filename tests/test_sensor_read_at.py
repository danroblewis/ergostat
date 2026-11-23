"""``ergostat sensor S --read V --at T`` is refused: ``--at`` views the past and records nothing, so a reading is never
silently recorded at the present time while the person believes it went in at T."""

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.store import Project

MODEL = """
name: rd
stocks:
  q: {unit: items, sensor: {manual: true}}
"""


def _repo(tmp_path):
    d = tmp_path / "rd"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return d


def _readings(d):
    return Project(mdl.load(d)).measurements.range("sensor/q.main", 0)


@pytest.mark.parametrize("where", ["before", "after"])
def test_read_with_at_refused_and_nothing_written(tmp_path, capsys, where):
    d = _repo(tmp_path)
    args = ["-C", str(d), "--at", "1d", "sensor", "q", "--read", "5"] if where == "before" else \
        ["-C", str(d), "sensor", "q", "--read", "5", "--at", "1d"]
    assert main(args) == 2
    err = capsys.readouterr().err
    assert "--at views the past and records nothing" in err
    assert "--backfill" not in err, "no --backfill option exists to name"
    assert _readings(d) == []


def test_read_without_at_unchanged(tmp_path, capsys):
    d = _repo(tmp_path)
    before = time.time()
    assert main(["-C", str(d), "sensor", "q", "--read", "5"]) == 0
    assert "recorded: q.main = 5" in capsys.readouterr().out
    got = _readings(d)
    assert [v for _, v in got] == [5.0] and got[0][0] >= before - 1
