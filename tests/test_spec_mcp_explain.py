"""``ergostat explain`` says what the spec's examples are in sentences, and ``ergostat mcp`` answers
the protocol and its tools."""

import io
import json
import shutil
from pathlib import Path

from ergostat.mcp import serve
from ergostat.spec import load
from ergostat.spec.explain import explain

ROOT = Path(__file__).parent.parent


def test_explain_the_production_example_names_the_missing_loop():
    text = explain(load(ROOT / "docs/spec-examples/production.yaml"))
    assert "Goal disk-headroom (critical)" in text
    disk = text.split("Goal disk-headroom")[1]
    assert "Missing feedback" in disk
    assert "rotate-when-big runs rotate while the goal is off, until stock.logs <= 300" in text




def rpc(tmp_path, *msgs):
    shutil.copy(ROOT / "docs/spec-tests/fixtures/first-loop.yaml", tmp_path / "ergostat.yaml")
    out = io.StringIO()
    serve(tmp_path, io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n"), out)
    return [json.loads(x) for x in out.getvalue().splitlines()]




