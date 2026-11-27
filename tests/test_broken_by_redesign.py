"""tests/broken_by_redesign.txt names only tests that exist: a stale line (a test renamed or deleted, its line left
behind) fails here, so the list only shrinks as the redesign mends what it broke."""

import subprocess
import sys
from pathlib import Path

from tests.conftest import broken_by_redesign

ROOT = Path(__file__).resolve().parent.parent


def test_every_listed_test_exists():
    listed = broken_by_redesign()
    files = sorted({x.split("::", 1)[0] for x in listed})
    missing = [f for f in files if not (ROOT / f).is_file()]
    assert not missing, f"tests/broken_by_redesign.txt names files that do not exist: {missing}"
    if not files:
        return
    run = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                          "-p", "no:xdist", *files], cwd=ROOT, capture_output=True, text=True, timeout=300)
    found = {line.strip() for line in run.stdout.splitlines() if "::" in line}
    stale = [x for x in listed if "::" in x and x not in found]       # a listed file: it exists (above)
    assert not stale, "tests/broken_by_redesign.txt names tests that do not exist (remove the lines):\n" + "\n".join(stale)
