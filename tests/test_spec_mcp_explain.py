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


def test_explain_one_block_and_one_stock():
    spec = load(ROOT / "docs/spec-examples/first-loop.yaml")
    assert "Runs while goal inbox-short is off (through keep-inbox-short)" in explain(spec, "worker")
    assert "Drained by: processed" in explain(spec, "stock.inbox")


def rpc(tmp_path, *msgs):
    shutil.copy(ROOT / "docs/spec-examples/first-loop.yaml", tmp_path / "ergostat.yaml")
    out = io.StringIO()
    serve(tmp_path, io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n"), out)
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_mcp_initialize_list_and_call(tmp_path):
    got = rpc(tmp_path,
              {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
              {"jsonrpc": "2.0", "method": "notifications/initialized"},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
              {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "check", "arguments": {}}},
              {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_sensor",
                                                                             "arguments": {"sensor": "inbox", "value": 3}}},
              {"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert [g["id"] for g in got] == [1, 2, 3, 4, 5]          # no answer to the notification
    assert got[0]["result"]["serverInfo"]["name"] == "ergostat"
    names = {t["name"] for t in got[1]["result"]["tools"]}
    assert {"check", "explain", "status", "findings", "events", "spec"} <= names
    assert json.loads(got[2]["result"]["content"][0]["text"])["ok"] is True
    assert got[3]["result"]["isError"]                           # inbox.main runs a command: not manual
    assert got[4]["error"]["code"] == -32601


def test_an_agent_finds_the_improve_model_skill_and_the_residuals_over_mcp_and_in_help(tmp_path, capsys, monkeypatch):
    """The skill for reviewing a model ships with ergostat: the MCP tool improve_model returns it with
    the guidelines it applies (docs/MODELLING.md), residuals gives the evidence it reads, and
    ``ergostat help improve-model`` and ``ergostat help modelling`` print them."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    got = rpc(tmp_path,
              {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
              {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "improve_model", "arguments": {}}},
              {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "residuals", "arguments": {}}},
              {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "fit", "arguments": {}}})
    assert "improve_model" in got[0]["result"]["instructions"]
    assert {"improve_model", "residuals", "fit"} <= {t["name"] for t in got[1]["result"]["tools"]}
    fit = json.loads(got[4]["result"]["content"][0]["text"])
    assert set(fit["words"]) == {"r2", "mape", "um", "us", "uc"} and fit["proposals"] == []
    text = got[2]["result"]["content"][0]["text"]
    assert text.startswith("---\nname: improve-model\ndescription: ")        # a skill's frontmatter, as Claude Code reads it
    assert "never applies an edit without the owner's approval" in text and "# Improving a model" in text
    assert isinstance(json.loads(got[3]["result"]["content"][0]["text"]), dict)
    from ergostat.cli import main
    assert main(["help", "improve-model"]) == 0 and "## 4. Apply only with approval" in capsys.readouterr().out
    assert main(["help", "modelling"]) == 0 and "| What you see |" in capsys.readouterr().out
    assert main(["help"]) == 0 and "ergostat help improve-model" in capsys.readouterr().out
