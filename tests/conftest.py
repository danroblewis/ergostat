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
