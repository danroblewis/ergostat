import json
import threading
import urllib.request

from ergostat import graph, state
from ergostat.cli import main


def test_the_control_graph_has_pipes_through_the_valve_and_the_loop(project):
    project.measurements.add("sensor/disk-usage", 70)
    g = graph.control(project.model, state.snapshot(project), project.model.members(None))
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    assert kinds["flow:cleaned"] == "valve" and kinds["flow:logs-written"] == "disturbance"
    assert kinds["cloud:cleaned:out"] == "cloud" and kinds["cloud:logs-written:in"] == "cloud"
    pipes = {(e["source"], e["target"]) for e in g["edges"] if e["kind"] == "pipe"}
    assert ("stock:disk-used", "flow:cleaned") in pipes and ("flow:logs-written", "stock:disk-used") in pipes
    assert g["loops"]["disk-under-80"]["status"] == "holding"
    assert ("controller:disk-under-80", "flow:cleaned") in {(e["source"], e["target"]) for e in g["edges"] if e["kind"] == "action"}
    assert all(e["source"] in kinds and e["target"] in kinds for e in g["edges"])


def test_around_a_part_selects_its_neighbours(project):
    near = graph.select(project.model, around="valve/delete-old-files")
    assert {"delete-old-files", "cleaned", "disk-used", "disk-under-80"} <= near
    assert graph.select(project.model, around="loop/disk-under-80") == {"disk-under-80", "disk-used", "disk-usage",
                                                                       "delete-old-files", "cleaned", "logs-written"}


def test_the_wiring_graph_links_agents_through_parts(repo, project):
    text = repo.path.joinpath("ergostat.toml").read_text().replace('agent = "cleaner"\n\n[[valve]]', 'agent = "decider"\n\n[[valve]]')
    text += '\n[[agent]]\nname = "decider"\nkind = "rule"\n'
    repo.write("ergostat.toml", text)
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    g = graph.wiring(p.model, p, state.snapshot(p), p.model.members(None))
    vias = {(e["source"], e["target"]): e["via"] for e in g["edges"]}
    assert vias[("agent:cleaner", "agent:decider")] == ["sensor disk-usage"]
    assert vias[("agent:decider", "agent:cleaner")] == ["valve delete-old-files"]


def run_cli(repo, *args, capsys=None):
    rc = main(["-C", str(repo.path), *args])
    out = capsys.readouterr().out if capsys else ""
    return rc, out


def test_the_cli_topics_answer(repo, project, capsys):
    project.measurements.add("sensor/disk-usage", 85)
    rc, out = run_cli(repo, capsys=capsys)
    assert rc == 0 and "not running" in out and "disk-under-80" in out and "off by 5" in out
    for args, expect in [(["check"], "1 stock ·"), (["loop"], "disk-under-80"), (["loop", "disk-under-80"], "FILLED BY"),
                         (["agent"], "cleaner"), (["agent", "cleaner"], "fills"), (["system"], "host"),
                         (["system", "host"], "loop disk-under-80"), (["system", "--all", "--wiring"], "cleaner"),
                         (["stock"], "disk-used"), (["valve"], "delete-old-files"), (["disturbance"], "logs-written"),
                         (["sensor", "disk-usage"], "85"), (["residual"], "two readings"), (["event"], ""), (["item"], "")]:
        rc, out = run_cli(repo, *args, capsys=capsys)
        assert rc == 0 and expect in out, (args, out)


def test_the_cli_json_and_unknown_names(repo, project, capsys):
    rc, out = run_cli(repo, "loop", "--json", capsys=capsys)
    assert rc == 0 and json.loads(out)["disk-under-80"]["status"] == "unknown"
    assert run_cli(repo, "loop", "nope", capsys=capsys)[0] == 2
    assert run_cli(repo, "system", "nope", capsys=capsys)[0] == 2
    assert run_cli(repo, "--since", "soon", capsys=capsys)[0] == 2


def test_no_model_says_how_to_start(tmp_path, capsys):
    import pytest
    with pytest.raises(SystemExit):
        main(["-C", str(tmp_path)])
    assert "ergostat chat" in capsys.readouterr().err


def test_the_web_api_serves_what_the_cli_shows(project):
    from ergostat.web import serve
    project.measurements.add("sensor/disk-usage", 70)
    server, url = serve(project, 18781)
    try:
        def get(path):
            with urllib.request.urlopen(url + path, timeout=10) as r:
                return r.status, r.read()
        st, body = get("/api/status")
        assert st == 200 and json.loads(body)["loops"]["disk-under-80"]["status"] == "holding"
        assert json.loads(get("/api/graph?view=control")[1])["kind"] == "control"
        assert json.loads(get("/api/graph?view=wiring")[1])["kind"] == "wiring"
        assert json.loads(get("/api/part/stock/disk-used")[1])["now"]["value"] == 70
        assert "cleaner" in json.loads(get("/api/agents")[1])
        parts = json.loads(get("/api/parts")[1])
        assert [x["name"] for x in parts["valve"]] == ["delete-old-files"] and parts["sensor"][0]["reading"] == 70
        assert parts["system"][0]["name"] == "host" and parts["disturbance"][0]["name"] == "logs-written"
        assert json.loads(get("/api/loops/disk-under-80")[1])["status"] == "holding"
        assert get("/")[0] == 200 and b"elk.bundled.js" in get("/")[1]
        try:
            get("/api/part/stock/nope")
            raise AssertionError("404 expected")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_threads_share_the_stores_without_locking_up(project):
    errs = []

    def hammer(i):
        try:
            for j in range(40):
                project.events.add("x.y.z", item=f"i{i}", data={"j": j})
                project.measurements.add("sensor/disk-usage", j)
                state.snapshot(project)
        except Exception as e:      # pragma: no cover
            errs.append(e)
    ts = [threading.Thread(target=hammer, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert not errs and not any(t.is_alive() for t in ts)
    assert project.events.count() == 240


def test_the_model_history_records_what_changed(repo, project, capsys):
    from ergostat import history, model
    from ergostat.store import Project
    first = history.note(project)
    assert first["data"]["first"] and history.note(project) is None and history.changes(project, 0) == []
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('setpoint = "<= 80"', 'setpoint = "<= 70"')
               + '\n[[stock]]\nname = "inodes"\n')
    p = Project(model.load(repo.path))
    (ch,) = [history.note(p)]
    assert ch["data"]["added"] == ["stock:inodes"] and ch["data"]["changed"] == ["controller:disk-under-80"]
    rc, out = run_cli(repo, "--since", "1h", capsys=capsys)
    assert "1 change" in out and "+stock:inodes" in out and "~controller:disk-under-80" in out


def test_a_loop_as_a_text_block_diagram(repo, project, capsys):
    project.measurements.add("sensor/disk-usage", 70)
    rc, out = run_cli(repo, "system", "--all", "--blocks", capsys=capsys)
    assert rc == 0 and "r: ≤ 80 ─▶(Σ)─e=0─▶[ disk-under-80 · program ]─u─▶[ delete-old-files ]─▶(−)─▶[ ∫ disk-used 70 % ]" in out
    assert "d: logs-written" in out and "▲−" in out and "[ disk-usage reads 70 ]◀" in out


def test_a_field_added_with_its_default_is_not_a_change(project):
    from ergostat import history
    before = history.fingerprints(project.model)
    project.model.agents["cleaner"].timeout = 300.0          # the default: nothing declared it
    assert history.fingerprints(project.model) == before
    project.model.agents["cleaner"].timeout = 30.0
    assert history.fingerprints(project.model)["agent:cleaner"] != before["agent:cleaner"]


def test_at_looks_at_a_past_moment(project):
    import time as t

    from ergostat import state
    now = t.time()
    project.measurements.add("sensor/disk-usage", 70, at=now - 600)
    project.measurements.add("sensor/disk-usage", 90, at=now - 10)
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "off"
    past = state.snapshot(project, now=now - 300)
    assert past["loops"]["disk-under-80"]["status"] == "holding" and past["stocks"]["disk-used"]["value"] == 70
    assert not past["live"]


def test_agent_now_runs_it_once_and_says_what_it_said(repo, project, capsys):
    repo.write("clean.py", """
        import json
        print(json.dumps({"sensor": "disk-usage", "value": 91}))
        print(json.dumps({"controller": "disk-under-80", "decision": "free 20"}))
        print(json.dumps({"valve": "delete-old-files", "amount": 20}))
    """)
    rc, out = run_cli(repo, "agent", "cleaner", "--now", capsys=capsys)
    assert rc == 0 and "1 reading, 1 opening, 1 decision" in out and "disk-usage = 91" in out and "valve.opened" in out
    assert run_cli(repo, "agent", "nobody", "--now", capsys=capsys)[0] == 2


def test_chat_briefs_claude_with_the_model(repo, tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "claude").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n')
    (fake / "claude").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "CAPTURE": str(tmp_path / "args")}
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(repo.path), "chat", "add a backup loop"],
                       env=env, capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr
    args = (tmp_path / "args").read_text()
    assert "--append-system-prompt" in args and "You are this system's Supervisor" in args
    assert 'name = "disk-under-80"' in args and args.rstrip().endswith("add a backup loop")


def test_cycles_among_agents_and_whether_a_loop_declares_them(repo):
    text = repo.path.joinpath("ergostat.toml").read_text().replace('agent = "cleaner"\n\n[[valve]]', 'agent = "decider"\n\n[[valve]]')
    text += '\n[[agent]]\nname = "decider"\nkind = "rule"\n'
    repo.write("ergostat.toml", text)
    from ergostat import model, state
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    g = graph.wiring(p.model, p, state.snapshot(p), p.model.members(None))
    (cy,) = g["cycles"]
    assert sorted(cy["agents"]) == ["cleaner", "decider"] and cy["loop"] == "disk-under-80"
    # two agents that pass events back and forth, with no loop between them
    m = p.model
    m.agents["pinger"] = model.Agent("pinger", "program", "true", 1.0, ["pong.*"])
    m.agents["ponger"] = model.Agent("ponger", "program", "true", 1.0, ["ping.*"])
    edges = [{"source": "agent:pinger", "target": "agent:ponger", "via": ["event ping.sent"]},
             {"source": "agent:ponger", "target": "agent:pinger", "via": ["event pong.sent"]}]
    (loose,) = graph.cycles(m, edges)
    assert loose["loop"] is None and loose["agents"] == ["pinger", "ponger"]


def test_the_ai_controller_example_turns_an_answer_into_lines(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "claude").write_text('#!/bin/sh\ncat > /dev/null\n'
                                 'echo \'Sure. {"decision": "rewrite install.md", "act": true, "amount": 1, "why": "flags changed"}\'\n')
    (fake / "claude").chmod(0o755)
    (tmp_path / "prompt.md").write_text("Decide.")
    ctx = {"roles": [{"kind": "controller", "name": "docs-current"}, {"kind": "valve", "name": "rewrite-page"}],
           "controllers": {"docs-current": {"setpoint": "<= 3", "value": 5, "error": -2}}, "state": {}, "trigger": None}
    script = Path(__file__).resolve().parents[1] / "examples" / "ai-controller.sh"
    r = subprocess.run([str(script), str(tmp_path / "prompt.md")], input=json.dumps(ctx), capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}, timeout=60)
    lines = [json.loads(x) for x in r.stdout.splitlines()]
    assert r.returncode == 0, r.stderr
    assert lines == [{"controller": "docs-current", "decision": "rewrite install.md", "why": "flags changed"},
                     {"valve": "rewrite-page", "amount": 1.0}]


def test_a_person_records_what_they_did(repo, capsys):
    text = repo.path.joinpath("ergostat.toml").read_text().replace('agent = "cleaner"\n\n[[agent]]', 'agent = "me"\n\n[[agent]]')
    repo.write("ergostat.toml", text + '\n[[agent]]\nname = "me"\nkind = "person"\n')
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    assert p.model.valves["delete-old-files"].mode == "manual"           # a person's valve is manual unless said
    rc, out = run_cli(repo, "valve", "delete-old-files", "--opened", "5", "--note", "cleared /tmp", capsys=capsys)
    assert rc == 0 and "recorded, as me" in out
    (e,) = p.events.query(type="valve.opened")
    assert e["source"] == "me" and e["data"] == {"amount": 5.0, "flow": "cleaned", "note": "cleared /tmp"}
    assert run_cli(repo, "sensor", "disk-usage", "--read", "50", capsys=capsys)[0] == 2      # filled by a program
    assert run_cli(repo, "valve", "delete-old-files", "--opened", "-1", capsys=capsys)[0] == 1  # refused, as for any agent


def test_a_snapshot_is_one_file_holding_the_answers_the_page_asks_for(project):
    import json as _json
    import re as _re

    from ergostat.web.snapshot import build, key
    project.measurements.add("sensor/disk-usage", 70.0)
    html = build(project)
    assert '<script src="' not in html and '<link rel="stylesheet"' not in html      # nothing fetched
    assert html.lower().count("<script") == html.lower().count("</script>")          # no script closed early
    body = _re.search(r"window\.SNAPSHOT = (.*?);</script>", html, _re.S).group(1)
    data = _json.loads(body.replace("<\\/", "</"))["data"]
    for k in ("status", "graph", "graph?view=control", "graph?system=host&view=wiring", "loops/disk-under-80",
              "agents/cleaner", "part/valve/delete-old-files", "part/disturbance/logs-written", "projects"):
        assert k in data, k
    assert key("graph", {"view": "control", "system": "", "around": "undefined", "since": "1h"}) == "graph?view=control"
