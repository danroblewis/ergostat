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
                                                                       "delete-old-files", "cleaned"}


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
    for args, expect in [(["check"], "1 stocks"), (["loop"], "disk-under-80"), (["loop", "disk-under-80"], "FILLED BY"),
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
