import json
import re
import threading
import urllib.error
import urllib.request

from ergostat import graph, state
from ergostat.cli import main
from tests.ports import free_port


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


WIRED = """
[[agent]]
name = "decider"
kind = "rule"
command = "true"
on = ["loop.off@disk-under-80"]

[[agent]]
name = "notifier"
kind = "program"
command = "true"
on = ["cleanup.done"]

[[agent]]
name = "auditor"
kind = "program"
command = "true"
on = ["agent.failed@cleaner"]

[[agent]]
name = "ghost"
kind = "person"
"""


def wired(repo):
    """The disk model with a controller agent woken by its loop, a listener, an auditor that never
    hears anything and a person who never shows up; and a record crafted to prove some of it."""
    text = repo.path.joinpath("ergostat.toml").read_text().replace('agent = "cleaner"\n\n[[valve]]', 'agent = "decider"\n\n[[valve]]')
    repo.write("ergostat.toml", text + WIRED)
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    import time
    now = time.time()
    ev = p.events.add
    ev("old.thing", source="long-gone", at=now - 3 * 86400)                       # outside the window
    run = ev("agent.started", item="cleaner", source="ergostat", at=now - 600)       # the cleaner reads the disk ...
    off = ev("loop.off", item="disk-under-80", source="ergostat", causedby=run["id"], at=now - 599)   # ... and it is off
    ev("agent.started", item="decider", source="ergostat", causedby=off["id"], at=now - 598)          # woken by it
    ev("cleanup.done", item="disk", source="cleaner", causedby=run["id"], at=now - 590)
    ev("agent.started", item="notifier", source="ergostat", at=now - 580)           # ran after it: it listens for it
    ev("cleanup.done", item="disk", source="cleaner", at=now - 100)                 # heard, but nothing ran after
    inv = ev("invoice.sent", item="invoice/7", source="billing/2", at=now - 300)    # machines the model never names
    ev("mail.sent", item="invoice/7", source="mailer", causedby=inv["id"], at=now - 299)
    return p


def test_the_wiring_is_what_the_record_shows(repo):
    p = wired(repo)
    g = graph.wiring(p.model, p, state.snapshot(p), p.model.members(None))
    nodes = {n["label"]: n for n in g["nodes"]}
    edges = {(e["source"].split(":", 1)[1], e["target"].split(":", 1)[1]): e for e in g["edges"]}
    assert "long-gone" not in nodes                                                  # only the window
    assert nodes["ghost"]["silent"] and nodes["ghost"]["declared"] and nodes["auditor"]["silent"]
    assert nodes["billing"]["seen"] and not nodes["billing"]["declared"] and nodes["billing"]["instances"] == ["2"]
    assert nodes["cleaner"]["runs"] == 1 and {x["type"]: x["count"] for x in nodes["cleaner"]["published"]} == {"cleanup.done": 2}
    assert nodes["notifier"]["heard"] == {"cleanup.done": 2}
    # caused by: the cleaner's run caused ergostat's loop.off, which woke the decider; both declared
    e = edges[("cleaner", "ergostat")]
    assert e["seen"] and e["declared"] and e["evidence"] == ["caused-by"]
    assert [(t["type"], t["how"], t["count"], t["publisher"]) for t in e["types"]] == [("loop.off", "run", 1, "ergostat")]
    e = edges[("ergostat", "decider")]
    assert e["seen"] and e["declared"] and e["types"][0]["type"] == "loop.off" and e["types"][0]["how"] == "sent"
    assert any("listens for loop.off@disk-under-80" in x for x in e["declaredAs"])
    # listened and ran: the notifier listens for cleanup.done and ran after the first, not the second
    e = edges[("cleaner", "notifier")]
    assert e["seen"] and e["undeclared"] and e["evidence"] == ["listened-and-ran"] and e["count"] == 1
    assert e["via"] == ["cleanup.done · 1 · undeclared"]
    # between machines the model never names: undeclared, from the instance's machine
    e = edges[("billing", "mailer")]
    assert e["undeclared"] and e["types"][0]["type"] == "invoice.sent" and e["types"][0]["publisher"] == "billing"
    # declared, never seen: the auditor listens for the cleaner's failures, and there were none
    e = edges[("cleaner", "auditor")]
    assert not e["seen"] and e["declared"] and e["id"].startswith("wire-unseen:") and e["via"] == ["declared, never seen"]
    assert ("decider", "cleaner") not in edges                       # a role handed on is not evidence by itself
    assert len(g["edges"]) == 5


def test_the_wiring_of_a_past_moment_and_a_window(repo):
    p = wired(repo)
    import time
    early = graph.wiring(p.model, p, state.snapshot(p, 120, time.time() - 595), p.model.members(None))
    labels = {n["label"]: n for n in early["nodes"]}
    assert labels["cleaner"]["runs"] == 1 and labels["decider"]["runs"] == 1 and labels["notifier"]["silent"]
    assert {(e["source"], e["target"]) for e in early["edges"] if e["seen"]} == {("agent:cleaner", "agent:ergostat"),
                                                                              ("agent:ergostat", "agent:decider")}
    late = graph.wiring(p.model, p, state.snapshot(p, 200), p.model.members(None))
    assert {n["label"] for n in late["nodes"] if n["seen"]} == {"cleaner"}          # only its second cleanup.done


def test_the_record_page_filters_by_machine_and_type(repo):
    p = wired(repo)
    assert [e["type"] for e in p.events.query(n=None, machine="billing")] == ["invoice.sent"]
    assert [e["type"] for e in p.events.query(n=None, type="invoice.sent,mail.*")] == ["invoice.sent", "mail.sent"]


def test_the_record_narrows_to_a_goal_and_its_window_and_the_filter_matches_item_and_source(repo):
    """A crossing's link (/record?about=<goal>&from=&to=) asks for the goal's events, its controller's, valves' and
    their agents', within the window; the filter box (match=) takes a type, an item or a source."""
    import time

    from ergostat.web import serve
    p = wired(repo)
    now = time.time()
    server, url = serve(p, free_port())
    try:
        def types(query):
            with urllib.request.urlopen(f"{url}/api/events?{query}", timeout=10) as r:
                return [e["type"] for e in json.loads(r.read())]
        assert types("about=disk-under-80") == ["loop.off", "cleanup.done", "cleanup.done"]   # the goal, its agents
        assert types(f"about=disk-under-80&from={now - 595}&to={now - 200}") == ["cleanup.done"]   # its window
        assert types("about=disk-under-80&match=loop.*") == ["loop.off"]                    # both: the goal's that match
        assert types("about=no-such-goal") == []                                              # never everything
        assert types("match=mailer") == ["mail.sent"]                                         # a source
        assert types("match=invoice/7") == ["invoice.sent", "mail.sent"]                      # an item
        assert types("match=invoice.*") == ["invoice.sent"]                                   # a type, as before
    finally:
        server.shutdown()
        server.server_close()


def test_the_goals_filtered_rows_are_not_lost_behind_more_than_n_newer_events_of_one_name(repo):
    """With about= and match= both, the match is asked with each name, so matching events older than the newest n
    of that name still show (never 'Nothing recorded yet.' while they exist)."""
    import time

    from ergostat.web import serve
    p = wired(repo)
    now = time.time()
    for i in range(5):                        # more than n newer events of the goal, and of its agent, none matching
        p.events.add("loop.on", item="disk-under-80", source="ergostat", at=now - 50 + i)
        p.events.add("scan.done", item="tmp", source="cleaner", at=now - 40 + i)
    server, url = serve(p, free_port())
    try:
        def types(query):
            with urllib.request.urlopen(f"{url}/api/events?{query}", timeout=10) as r:
                return [e["type"] for e in json.loads(r.read())]
        assert types("about=disk-under-80&match=loop.off&n=3") == ["loop.off"]                  # by type
        assert types("about=disk-under-80&match=disk&n=3") == ["cleanup.done", "cleanup.done"]   # by item
        assert types("about=disk-under-80&match=disk-under-80&n=3") == ["loop.on"] * 3           # the goal itself
    finally:
        server.shutdown()
        server.server_close()


def test_the_filter_box_keeps_the_addresss_item_and_machine(repo):
    """match= with item= or machine= (a valve's link, itemsets.js; a machine's) holds to both, never wider."""
    import time

    from ergostat.web import serve
    p = wired(repo)
    now = time.time()
    p.events.add("valve.opened", item="cleanup", source="ergostat", at=now - 20)
    p.events.add("valve.opened", item="other-valve", source="ergostat", at=now - 10)
    server, url = serve(p, free_port())
    try:
        def rows(query):
            with urllib.request.urlopen(f"{url}/api/events?{query}", timeout=10) as r:
                return [(e["type"], e["item"]) for e in json.loads(r.read())]
        assert rows("match=valve.opened&item=cleanup") == [("valve.opened", "cleanup")]          # one valve's, not all
        assert rows("match=invoice/7&machine=mailer") == [("mail.sent", "invoice/7")]             # the machine kept
        assert rows("match=invoice/7&machine=billing") == [("invoice.sent", "invoice/7")]         # and its instances
        assert rows("match=mail.*&machine=billing") == []
        assert rows("match=mailer&item=invoice/8") == []
        assert rows("about=disk-under-80&match=cleanup.done&machine=nobody") == []
    finally:
        server.shutdown()
        server.server_close()


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
                         (["system", "host"], "goal disk-under-80"), (["system", "--all", "--wiring"], "cleaner"),
                         (["stock"], "disk-used"), (["valve"], "delete-old-files"), (["disturbance"], "logs-written"),
                         (["sensor", "disk-usage"], "85"), (["residual"], "two readings"), (["event"], ""), (["item"], "")]:
        rc, out = run_cli(repo, *args, capsys=capsys)
        assert rc == 0 and expect in out, (args, out)


def test_the_cli_calls_what_is_held_a_goal(repo, project, capsys):
    """What show.py prints of a goal says 'goal NAME', never 'loop NAME'; the table's column is GOAL."""
    import re
    for args in (["system", "host"], ["system", "host", "--blocks"], ["loop", "disk-under-80"], ["loop"]):
        rc, out = run_cli(repo, *args, capsys=capsys)
        assert rc == 0 and ("goal disk-under-80" in out or "GOAL" in out), (args, out)
        assert not re.search(r"\bloop disk-under-80|\bLOOP\b", out), (args, out)


def test_the_status_says_the_models_purpose_its_systems_and_its_controlled_goals(tmp_path):
    """The diagram's caption reads these from /api/status: the model's purpose, its top-level systems, and the goals a
    controller holds (Blocks' control loops), each of them one of the status's loops."""
    import shutil
    from pathlib import Path

    from ergostat import model
    from ergostat.store import Project
    from ergostat.web import serve
    d = tmp_path / "the-job"
    shutil.copytree(Path(__file__).resolve().parent.parent / "examples" / "the-job", d,
                    ignore=shutil.ignore_patterns("run", "__pycache__"))
    f = d / "ergostat.yaml"
    f.write_text(f.read_text().replace("name: the-job\n", "name: the-job\npurpose: keep my work moving\n", 1))
    m = d / "job" / "messages.yaml"                    # one goal no controller holds: notes-reach-work, its block gone
    m.write_text(m.read_text().split("\nblocks:\n")[0] + "\n")
    server, url = serve(Project(model.load(d)), free_port())
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=30) as r:
            st = json.loads(r.read())
    finally:
        server.shutdown()
    assert st["purpose"] == "keep my work moving" and st["top"] == 2, (st.get("purpose"), st.get("top"))
    assert st["controlled"] and set(st["controlled"]) < set(st["loops"]), st["controlled"]
    assert st["controlled"] == sorted(st["controlled"])


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
    server, url = serve(project, free_port())
    try:
        def get(path):
            with urllib.request.urlopen(url + path, timeout=10) as r:
                return r.status, r.read()
        st, body = get("/api/status")
        assert st == 200 and json.loads(body)["loops"]["disk-under-80"]["status"] == "holding"
        s = json.loads(body)                                 # the header's window: how much of it is on record
        assert isinstance(s["recorded"], (int, float)) and 0 <= s["recorded"] < s["window"]
        assert json.loads(get("/api/graph?view=control")[1])["kind"] == "control"
        assert json.loads(get("/api/graph?view=wiring")[1])["kind"] == "process"     # the wiring's address: the process map
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


def test_the_loops_row_writes_shares_through_share_text_and_names_flapping_at_twenty():
    """Without a browser (the build's suite has none): the Loops row's time off goes through shareText, which writes
    '<1%' for a share that rounds to 0, no literal "0%" remains there, and flapping is named from FLAP_AT = 20 through
    the hysteresis (steadyWord). The behaviour itself is checked in the browser by
    tests/test_diagram_rendering.py::test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named."""
    import re

    from ergostat.web.server import STATIC
    util, pages = (STATIC / "util.js").read_text(), (STATIC / "pages.js").read_text()
    assert re.search(r'const shareText = .*x > 0 && x < 0\.005 \? "<1%"', util), "shareText no longer writes '<1%'"
    assert re.search(r"const FLAP_AT = 20;", util), "the flapping count is not 20"
    loops = pages[pages.index("async function pageLoops"):]
    loops = loops[:loops.index("\nasync function ", 1)]
    row = (STATIC / "goalrow.js").read_text()   # the Loops row is drawn by goalRow
    assert "shareText(g.off_share)" in row and '"0%"' not in row + loops, "time off is not written through shareText"
    assert "behaviour: word(g.name, g)" in loops and "g.behaviour ??" in row, "the row's behaviour skips the hysteresis"
    assert re.search(r"lp\.times_off >= FLAP_AT \? steadyWord\(n, `flapping \(", loops), "flapping not named in the row"


def test_only_the_record_folds_runs_of_identical_events():
    """Without a browser (the page test is tests/test_items_page.py::test_the_record_folds_runs_of_identical_events):
    a run's key is the event's type, source, item and shown data, and only the Record (local and remote) asks for
    the fold, so an item's own event list and a folded run's list show each event."""
    import re

    from ergostat.web.server import STATIC
    details, pages = (STATIC / "details.js").read_text(), (STATIC / "pages.js").read_text()
    assert "JSON.stringify([e.type, e.source, e.item, changeOf(e)])" in details
    assert re.search(r"if \(fold && last && last\.sig === sig\)", details)
    assert (details + pages).count("eventsTable(") == 6    # the definition, the Record's two, item, history, run
    assert (details + pages).count(", false, true)") == 2 and "eventsTable(run.slice().reverse(), false)" in details
    record = pages[pages.index("async function pageRecord"):]
    record = record[:record.index("\n}\n")]
    assert record.count("eventsTable(") == 2 and record.count(", false, true)") == 2


def test_api_status_counts_the_goals_off_with_modellings_own_beside_them(tmp_path, monkeypatch):
    from ergostat.web import serve
    from tests.test_goal_upkeep import seeded
    p = seeded(tmp_path, monkeypatch)
    server, url = serve(p, free_port())
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=10) as r:
            body = json.loads(r.read())
    finally:
        server.shutdown()
        server.server_close()
    got = body["goals_off"]
    assert got["own"] == {"modelling": 2} and got["system"] >= 1 and got == state.goals_off(state.snapshot(p))
    assert body["loops"]["model-fits"]["upkeep"] == "modelling" and "upkeep" not in body["loops"]["queue-short"]


OPEN_GOAL = '  queue-watched: {stock: queue, hold: "<= 5", system: shop}\n'      # no block holds it: open


def test_status_and_projects_print_the_one_count_api_status_gives(tmp_path, monkeypatch, capsys):
    """A system goal off, the modelling upkeep goals off and a goal open: `ergostat`, `ergostat projects` and
    /api/status say the same numbers, state.goals_off's, and the open goal is not counted off."""
    from types import SimpleNamespace

    from ergostat.web import serve
    from tests.test_goal_upkeep import MODEL, seeded
    monkeypatch.setattr("tests.test_goal_upkeep.MODEL", MODEL.replace("goals:\n", "goals:\n" + OPEN_GOAL))
    p = seeded(tmp_path, monkeypatch)
    server, url = serve(p, free_port())
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=10) as r:
            body = json.loads(r.read())
    finally:
        server.shutdown()
        server.server_close()
    g = body["goals_off"]
    assert body["loops"]["queue-watched"]["status"] == "open" and body["loops"]["queue-short"]["status"] == "off"
    assert g["system"] >= 1 and g["open"] >= 1 and g["own"] == {"modelling": 2}, g
    said = state.goals_said(g)
    assert said.startswith(f"{g['system']} goal") and f"{g['open']} open" in said and "model upkeep 2" in said, said
    rc, out = run_cli(SimpleNamespace(path=tmp_path / "repo"), capsys=capsys)
    assert rc == 0 and said in out.splitlines(), out
    rc, out = run_cli(SimpleNamespace(path=tmp_path / "repo"), "projects", capsys=capsys)
    assert rc == 0 and said in out, out
    rc, out = run_cli(SimpleNamespace(path=tmp_path / "repo"), "--json", capsys=capsys)
    assert json.loads(out)["goals_off"] == g


def test_status_of_one_system_counts_only_that_systems_goals(tmp_path, monkeypatch, capsys):
    """`ergostat --system shop` lists shop's goals, and its goals line and --json `goals_off` count those and no
    other system's (the modelling and upkeep goals off stay out), the one count over the narrowed map."""
    from types import SimpleNamespace

    from tests.test_goal_upkeep import MODEL, seeded
    monkeypatch.setattr("tests.test_goal_upkeep.MODEL", MODEL.replace("goals:\n", "goals:\n" + OPEN_GOAL))
    seeded(tmp_path, monkeypatch)
    ns = SimpleNamespace(path=tmp_path / "repo")
    rc, out = run_cli(ns, "--json", capsys=capsys)
    whole = json.loads(out)["goals_off"]
    rc, out = run_cli(ns, "--json", "--system", "shop", capsys=capsys)
    got = json.loads(out)
    assert set(got["loops"]) == {"queue-short", "queue-watched"}, sorted(got["loops"])
    assert got["goals_off"] == state.goals_off({"loops": got["loops"]}), got["goals_off"]
    assert got["goals_off"]["system"] == 1 and got["goals_off"]["open"] == 1 and not sum(got["goals_off"]["own"].values())
    assert whole["system"] > 1 and whole["own"] == {"modelling": 2}, whole     # the whole project's differs: a real narrowing
    rc, out = run_cli(ns, "--system", "shop", capsys=capsys)
    assert rc == 0 and "1 goal off · 1 open" in out.splitlines(), out


def test_no_page_code_counts_goals_by_their_status():
    """The page prints the server's count (state.goals_off) and never makes its own: every comparison of a goal's
    status or state with 'off' in util.js, pages.js and diagram.js is one of the allowed lines (row grouping or styling),
    and no filter by 'off' is counted (.length, reduce)."""
    import re
    from pathlib import Path
    static = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
    allowed = {                                          # the line, as it is; why it is not a count
        'const off = problems.filter((a) => a.state === "off").sort((a, b) => !!a.modelling - !!b.modelling);',  # rows grouped
        'const anyOff = Object.values(g.loops || {}).some((l) => l.status === "off");',  # whether suggestions start open
        ': Object.entries(st.loops || {}).filter(([, l]) => goalWord(l) === "off" && !l.upkeep)'
        '   // the goals the count counts',                  # the header's tooltip: the names, not a count
    }
    seen = []
    for f in ("util.js", "pages.js", "diagram.js"):
        for line in (static / f).read_text().splitlines():
            if re.search(r"""[=!]==?\s*["']off["']|["']off["']\s*[=!]==?|\[[^\]]*["']off["'][^\]]*\]\.includes""", line):
                seen.append(line.strip())
            assert not re.search(r"""filter\([^;]*["']off["'][^;]*\)\s*\.length""", line), (f, line)
    assert set(seen) <= allowed, set(seen) - allowed


def test_the_agents_answer_gives_each_agent_the_rung_the_page_groups_and_counts_it_under(project):
    """The Agents page's group headings ('program · 1') and its summary line both count agents by their rung, named by
    RUNG_NAMES in util.js: the answer's rung must be the index of the agent's kind there (the browser half of this
    check is tests/test_agents_page.py)."""
    import re
    from pathlib import Path

    from ergostat.model import KINDS
    from ergostat.web import serve
    util = (Path(__file__).resolve().parents[1] / "ergostat" / "web" / "static" / "util.js").read_text()
    names = json.loads(re.search(r"const RUNG_NAMES = (\[[^\]]*\]);", util).group(1))
    assert names == list(KINDS)                                  # the page's columns are the model's rungs, in order
    server, url = serve(project, free_port())
    try:
        with urllib.request.urlopen(url + "/api/agents", timeout=10) as r:
            agents = json.loads(r.read())
    finally:
        server.shutdown()
        server.server_close()
    assert agents and all(names[a["rung"]] == a["kind"] for a in agents.values()), agents
    assert sum(a["rung"] == names.index("program") for a in agents.values()) == 1    # the disk model's cleaner


def test_needs_attention_and_the_actions_page_say_one_sentence_of_what_a_person_may_do():
    """The sentence is defined once (pages.js MAY_DO); the Needs attention group shows that same constant, described
    by it (aria-describedby), with its empty form when nothing waits (the browser half is test_diagram_rendering.py)."""
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "ergostat" / "web" / "static"
    pages, diagram = (static / "pages.js").read_text(), (static / "diagram.js").read_text()
    said = "You can look at everything. Approving or denying these is the only thing that changes the system."
    assert f'const MAY_DO = "{said}";' in pages and said not in diagram
    assert '"aria-describedby": "may-do"' in diagram and 'key: "may-do" }, MAY_DO)' in diagram
    assert "Nothing waits for you. Looking never changes the system." in diagram


def test_a_link_s_window_is_the_one_the_api_is_asked_for_and_its_address_is_the_page(project):
    """A pasted link's ?window= is S.since (main.js reads it only when it names one of WINDOWS) and goes to the API as
    since=: each name must be a window the server reads as its seconds, never its 1h fallback. A link with ?select=,
    ?window= and ?filter= is still the page (the browser half of this check is tests/test_diagram_rendering.py::
    test_the_address_holds_what_is_chosen_and_the_window)."""
    import re
    from pathlib import Path

    from ergostat.web import serve
    main_js = (Path(__file__).resolve().parents[1] / "ergostat" / "web" / "static" / "main.js").read_text()
    windows = json.loads(re.search(r"const WINDOWS = (\{[^}]*\});", main_js).group(1))
    assert {"1h", "6h"} <= set(windows)
    server, url = serve(project, free_port())
    try:
        for name, secs in windows.items():
            with urllib.request.urlopen(f"{url}/api/loops/disk-under-80?since={name}", timeout=10) as r:
                lp = json.loads(r.read())
            assert abs(lp["until"] - lp["since"] - secs) < 1, (name, lp["since"], lp["until"])
        for path in ("/loops?select=disk-under-80&window=6h", "/diagram?view=dynamics&select=stock.disk-used&window=1d",
                     "/record?filter=valve.*&window=10m"):
            with urllib.request.urlopen(url + path, timeout=10) as r:
                assert r.status == 200 and b'name="ergostat-token"' in r.read(), path
    finally:
        server.shutdown()
        server.server_close()


def test_the_loop_answer_carries_what_the_panels_first_table_shows(tmp_path):
    """A controller's and a process's panel start with loopTable (control.js): rows law, process, held-out fit, time
    off, settling, saturation, the fit naming its measure. The image-squeeze tuner's loop answer holds every field
    those rows read, and a fit is a signed share, never clamped at 0 (the browser half of this check is
    tests/test_diagram_rendering.py::test_a_loops_controller_panel_starts_with_its_table_and_its_math_stays_inside)."""
    import re
    import shutil
    from pathlib import Path

    from ergostat import model
    from ergostat.control import loop
    from ergostat.store import Project
    root = Path(__file__).resolve().parents[1]
    js = (root / "ergostat" / "web" / "static" / "control.js").read_text()
    table = js[js.index("function loopTable"):js.index("/* ---- what is known of the process")]
    assert re.findall(r'\["([a-z -]+)", ', table) == ["law", "process", "held-out fit", "time off", "settling", "saturation"]
    assert 'const FIT = "NRMSE fit, 100% is perfect, below 0 is worse than the mean"' in js and "(${FIT})" in table
    rows = js[js.index("function identRows"):]
    assert "not identified: needs a step of u" in table and "Math.max(0" not in rows[:rows.index("\n}\n")]
    proc = js[js.index("function processSection"):]
    proc = proc[:proc.index("\n}\n")]
    assert not re.search(r"Math\.max\(0, Math\.round\([^)]*fit", proc) and "NRMSE fit ${pcFit(o.fit_val)} held out (${FIT})" in proc
    # a controller's tables are its own loops' only (as controlBox's), not a loop whose path merely runs through it
    blocks = (root / "ergostat" / "web" / "static" / "blocks.js").read_text()
    assert "d.controller?.block === n.id.slice(4) || (d.controllers || []).includes(n.id.slice(4))" in blocks
    assert "held.filter(own).map(loopTableBox)" in blocks
    # the table is drawn again when a proposal of its loop is answered (a browser test accepts one and sees it change)
    assert 'dispatchEvent(new CustomEvent("loop-answered", { detail: goal }))' in js and '"loop-answered", again' in js
    # each loop settled on its own; a process's identification (procs) right after its tables, before its words
    assert "mine.map((l) => loopControl(l).catch(" in blocks and "Promise.all(mine.map((l) => loopControl(l)))" not in blocks
    assert 'h("h2", {}, title), top, ...(n.role === "process" ? [procs] : [])]' in blocks and "kids.push(procs)" not in blocks
    shutil.copytree(root / "examples" / "image-squeeze", tmp_path / "x", ignore=shutil.ignore_patterns("run", "__pycache__"))
    d = loop.analyse(Project(model.load(tmp_path / "x")), "quality-held")
    assert d and not d.get("why"), d
    assert {"says", "law", "block"} <= set(d["controller"]) and d["controller"]["block"] == "tuner", d["controller"]
    assert "found" in d["identified"] and {"excursions", "saturation"} <= set(d["performance"]), d["performance"]
    assert {"count", "settling"} <= set(d["performance"]["excursions"]) and d["how"] in ("setting", "valve")


def test_a_process_view_with_no_kinds_is_answered_empty_and_the_page_says_so_over_the_canvas(tmp_path):
    """big has no kinds of item: its Process answer is empty, so the page takes its empty branch, whose words give the
    reason and Dynamics, laid over the canvas (not below it). The browser half of this check, the text's box inside the
    canvas's, is tests/test_diagram_rendering.py::test_process_view_with_no_kinds_says_so_inside_the_canvas."""
    import re
    import shutil
    from pathlib import Path

    from ergostat import model
    from ergostat.store import Project
    from ergostat.web import serve
    root = Path(__file__).resolve().parents[1]
    d = tmp_path / "big"
    shutil.copytree(root / "examples" / "big", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    server, url = serve(Project(model.load(d)), free_port())
    try:
        def get(path):
            with urllib.request.urlopen(url + path, timeout=10) as r:
                return r.read().decode()
        g, js, css = json.loads(get("/api/graph?view=process")), get("/static/diagram.js"), get("/static/style.css")
    finally:
        server.shutdown()
        server.server_close()
    assert not g["nodes"] and not g["kinds"], g                  # nothing to draw: the empty branch
    assert "No kinds of item in ${here}: its parts are counted by sensors. See `" in js
    assert re.search(r'go\(\{ view: "dynamics" \}\); \} \}, "Dynamics"\), "\."', js)    # where to look instead
    rule = re.search(r"\.canvas-wrap > \.empty \{([^}]*)\}", css)
    assert rule and all(p in rule.group(1) for p in ("position: absolute", "inset: 0", "align-items: center",
                                                       "justify-content: center")), rule


def test_every_page_header_links_to_the_diagrams_waiting_for_you_heading(project):
    """Each page's header carries 'N wait for you' (#waits) before its nav, a link to /diagram#waiting, and the
    Diagram's side list gives its 'Waiting for you' heading that id (the browser half: tests/test_diagram_rendering.py)."""
    import re
    from http.server import ThreadingHTTPServer

    from ergostat.web.server import STATIC, handler
    diagram = (STATIC / "diagram.js").read_text()
    assert re.search(r'h\("h3", \{[^}]*id: "waiting"[^}]*\}, "Waiting for you"', diagram), "the heading lost its id"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(project))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        for path in ("/items", "/agents", "/loops", "/record"):
            with urllib.request.urlopen(url + path, timeout=10) as r:
                header = r.read().decode().split("<header", 1)[1].split("</header>", 1)[0]
            link = re.search(r'<a id="waits"[^>]*href="/diagram#waiting"', header)
            assert link and link.start() < header.index("<nav"), path
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_side_panels_charts_say_being_worked_out_never_a_bare_ellipsis():
    """While a side-panel chart's numbers are asked for it says so in words: no element is made with the text '…' (or
    '\\u2026'), which reads as a stuck load, and the four charts of the panels start from the one placeholder (the
    browser half of this check is tests/test_diagram_rendering.py::test_no_panel_shows_a_leftover_ellipsis)."""
    import re
    from pathlib import Path

    charts = (Path(__file__).resolve().parents[1] / "ergostat" / "web" / "static" / "charts.js").read_text()
    assert not re.findall(r'''["'`](?:…|\\u2026|[^"'`\n]* (?:…|\\u2026))["'`]''', charts)
    assert 'const working = () => h("div", { class: "muted small" }, "being worked out");' in charts
    for chart in ("causesStrip", "loopDominance", "moduleCharts", "loopScope"):
        body = re.search(rf"\nfunction {chart}\(.*?\n}}\n", charts, re.S).group(0)
        assert "working()" in body, chart


def test_the_count_of_what_waits_sits_in_one_polite_live_region():
    """The header's 'N wait for you' link is inside an always-present aria-live='polite' region (so a count appearing
    from 0 is announced too), and the script writes its text through setText, which writes only a changed text. The
    browser half (the text written only when N changes) is test_diagram_rendering's
    test_a_changed_count_of_what_waits_is_announced."""
    import re

    from ergostat.web.server import STATIC
    html = (STATIC / "index.html").read_text()
    region = re.search(r'<span class="waits-said"([^>]*)>(.*?)</span>', html)
    assert region, "the waits link has no wrapping region"
    assert 'aria-live="polite"' in region.group(1) and 'aria-atomic="true"' in region.group(1)
    assert re.search(r'<a id="waits"[^>]*\bhidden\b', region.group(2)), "the link, not the region, is hidden at 0"
    util = (STATIC / "util.js").read_text()
    assert "setText(waits, `${n} wait for you`)" in util
    body = re.search(r"\nfunction setText\((\w+), (\w+)\) \{(.*?)\n\}", util, re.S)
    assert body and re.search(rf"if \({body.group(1)}\.textContent !== {body.group(2)}\)", body.group(3)), \
        "setText must write only a changed text"


def test_every_page_address_is_the_page_and_never_shadows_the_api_static_or_files(project):
    """Each page is a path (/items, /item/ID, /diagram?view=blocks): the server answers every one with the page,
    whatever the id holds (its / as %2F), and /api, /static and /file stay what they were."""
    import re
    from http.server import ThreadingHTTPServer

    from ergostat.web.server import STATIC, UI_PAGES, handler
    js = re.search(r"const UI_PAGES = \[([^\]]*)\]", (STATIC / "util.js").read_text()).group(1)
    assert tuple(re.findall(r'"([^"]+)"', js)) == UI_PAGES, "the page's and the server's lists of addresses differ"
    (project.dir / "notes.md").write_text("# Notes\n")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(project))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path, **headers):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, headers=headers), timeout=10) as r:
                return r.status, r.headers["Content-Type"], r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers["Content-Type"], e.read()
    try:
        for path in ("/", "/diagram", "/diagram?view=blocks&open=*", "/goals", "/loops", "/agents", "/items?kind=ticket&state=open",
                     "/item/ticket%2F7", "/item/a%20b%3Fc%23d%25e%26f%2Fg", "/item/%C3%BCn%C3%AF(1)!'*~", "/item/hypothesis/1",
                     "/record?type=x.y", "/model", "/check", "/guide?frame=3", "/fit", "/residuals"):
            code, ctype, body = get(path)
            assert code == 200 and ctype.startswith("text/html") and b'name="ergostat-token"' in body, path
            assert b'src="/static/util.js?v=' in body, path          # its scripts by absolute path: a deep address loads them
        code, ctype, body = get("/api/status")
        assert code == 200 and ctype == "application/json" and "loops" in json.loads(body)
        assert get("/api/nope/nope")[0] == 404 and get("/api/items/ticket%2F7")[1] == "application/json"
        assert get("/static/util.js")[0] == 200 and get("/static/nope.js")[0] == 404
        assert get("/file/notes.md")[2] == b"# Notes\n"
        code, ctype, body = get("/file/notes.md", Accept="text/html")
        assert code == 200 and b"marked.parse" in body and b"ergostat-token" not in body
        for path in ("/favicon.ico", "/nope", "/itemsx", "/util.js", "/static"):
            assert get(path)[0] == 404, path
    finally:
        srv.shutdown()
        srv.server_close()


def test_an_off_goal_reaches_the_side_list_as_a_named_goal_with_its_stock(project):
    """What the side list's goal button reads (diagram.js goalButton/showGoal): an off goal's attention entry is
    `loop NAME` and that loop names its stock. This is a stand-in without a browser, so the build collects a test.
    The button's behaviour is checked in tests/test_diagram_rendering.py
    (test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction)."""
    import json as _json
    import re as _re

    from ergostat.web.snapshot import build
    project.measurements.add("sensor/disk-usage", 95.0)
    html = build(project)
    data = _json.loads(_re.search(r"window\.SNAPSHOT = (.*?);</script>", html, _re.S).group(1).replace("<\\/", "</"))["data"]
    st = data["status"]
    assert st["loops"]["disk-under-80"]["status"] == "off" and st["loops"]["disk-under-80"]["stock"]
    off = [a for a in st["attention"] if a["what"] == "loop disk-under-80" and a["level"] == "bad"]
    assert off, st["attention"]
    assert "function showGoal(" in html and "goalButton(goal, what)" in html


def test_static_files_are_versioned_and_the_page_is_revalidated(project, tmp_path, monkeypatch):
    """After an update the browser runs the new scripts without a manual reload: every file the page loads is
    referenced with its content's version, a file asked for with its version is kept for good, and the page
    itself is always asked again (no-cache, with an ETag)."""
    import re
    import shutil
    from http.server import ThreadingHTTPServer

    from ergostat.web import server
    static = tmp_path / "static"
    shutil.copytree(server.STATIC, static)
    monkeypatch.setattr(server, "STATIC", static)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.handler(project))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path, **headers):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, headers=headers), timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
    try:
        code, headers, page = get("/diagram")
        assert code == 200 and headers["Cache-Control"] == "no-cache" and headers["ETag"]
        assert get("/diagram", **{"If-None-Match": headers["ETag"]})[0] == 304       # revalidated, not kept stale
        refs = re.findall(rb'(?:src|href)="(/static/[^"]+)"', page)
        assert refs and all(b"?v=" in r for r in refs), refs                          # every script and stylesheet
        assert re.search(rb'name="ergostat-assets" content="[^"]*libavoid/libavoid\.wasm', page)   # the worker's files
        util = next(r.decode() for r in refs if r.startswith(b"/static/util.js"))
        code, headers, _ = get(util)
        assert code == 200 and "immutable" in headers["Cache-Control"] and "max-age=31536000" in headers["Cache-Control"]
        assert get("/static/util.js")[1]["Cache-Control"] == "no-cache"              # unversioned: asked again each time
        assert get("/static/util.js?v=old")[1]["Cache-Control"] == "no-cache"
        (static / "util.js").write_text((static / "util.js").read_text() + "\n// an update\n")
        code, headers2, page2 = get("/diagram", **{"If-None-Match": headers["ETag"]})
        assert code == 200 and page2 != page                                          # the page names the new version
        util2 = next(r.decode() for r in re.findall(rb'(?:src|href)="(/static/[^"]+)"', page2) if r.startswith(b"/static/util.js"))
        assert util2 != util and get(util)[1]["Cache-Control"] == "no-cache"
        other = next(r for r in refs if r.startswith(b"/static/main.js"))
        assert other in page2                                                         # an unchanged file keeps its address
        (project.dir / "notes.md").write_text("# N\n")
        code, headers, body = get("/file/notes.md", Accept="text/html")          # a Markdown file's page: the same
        assert code == 200 and b'href="/static/style.css?v=' in body
    finally:
        srv.shutdown()
        srv.server_close()


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
    assert rc == 0 and "r: ≤ 80 ─▶(Σ)─e=0─▶[ disk-under-80 · program ]─u─▶[ delete-old-files ]─▶(−+)─▶[ ∫ disk-used 70 % ]" in out
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
    assert not graph.wiring(p.model, p, state.snapshot(p), p.model.members(None))["cycles"]   # nothing recorded yet
    # the cleaner reads, the loop goes off, the decider decides, the cleaner runs on its decision
    ev = p.events.add
    run = ev("agent.started", item="cleaner", source="ergostat")
    off = ev("loop.off", item="disk-under-80", source="ergostat", causedby=run["id"])
    dec = ev("agent.started", item="decider", source="ergostat", causedby=off["id"])
    said = ev("controller.decided", item="disk-under-80", source="decider", causedby=dec["id"], data={"decision": "clean"})
    ev("agent.started", item="cleaner", source="ergostat", causedby=said["id"])
    g = graph.wiring(p.model, p, state.snapshot(p), p.model.members(None))
    (cy,) = g["cycles"]
    assert sorted(cy["agents"]) == ["cleaner", "decider", "ergostat"] and cy["loop"] == "disk-under-80"
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
    for k in ("status", "graph", "graph?view=control", "graph?system=host&view=process", "loops/disk-under-80",
              "agents/cleaner", "part/valve/delete-old-files", "part/disturbance/logs-written", "projects"):
        assert k in data, k
    assert key("graph", {"view": "control", "system": "", "around": "undefined", "since": "1h"}) == "graph?view=control"


def test_a_snapshot_inlines_every_stylesheet_and_script_the_page_links(project, tmp_path, monkeypatch):
    import shutil

    from ergostat.web import snapshot
    static = tmp_path / "static"
    shutil.copytree(snapshot.STATIC, static)
    (static / "second-sheet.css").write_text(".second-sheet { color: var(--ink); } /* </style><b>not a tag */")
    (static / "second-script.js").write_text("window.secondScript = 1;")
    page = (static / "index.html").read_text()
    page = page.replace("</head>", '<link rel="stylesheet" href="/static/second-sheet.css">\n</head>', 1)
    page = page.replace("</body>", '<script src="/static/second-script.js"></script>\n</body>', 1)
    (static / "index.html").write_text(page)
    monkeypatch.setattr(snapshot, "STATIC", static)
    html = snapshot.build(project)
    assert '<link rel="stylesheet"' not in html and '<script src="' not in html      # nothing fetched
    assert ".second-sheet { color: var(--ink); }" in html and "window.secondScript = 1;" in html
    assert "</style><b>" not in html                                                 # a stylesheet cannot close its element
    assert html.count("<style>") == html.count("</style>") == page.count('rel="stylesheet"')


def test_a_snapshot_survives_html_in_the_record_and_odd_item_names(project):
    from ergostat.web.snapshot import build
    project.events.add("note.made", item="note/fix(1)", source="x", data={"text": "<!--<script>alert(1)</script>"})
    html = build(project)
    assert "<!--<script" not in html and "alert(1)</script>" not in html
    assert '"items/note%2Ffix(1)"' in html                     # the key the page's encodeURIComponent asks for
    assert html.count("</script>") == html.lower().count("<script")


def test_the_service_text_runs_this_repositorys_watcher(project):
    import plistlib

    from ergostat import service
    cmd = service.command(project.repo, ["--no-web"], "/opt/ergostat/bin/python")
    assert cmd[-4:] == ["ergostat.watcher", "-C", str(project.repo), "--no-web"]
    plist = plistlib.loads(service.launchd("my repo", project.repo, cmd, project.dir).encode())
    assert plist["ProgramArguments"] == cmd and plist["Label"] == "local.ergostat.my-repo"
    assert plist["KeepAlive"] is True                    # the watcher always; it leaves an engine stopped on purpose
    unit = service.systemd("t", project.repo, cmd, project.dir)
    assert "Restart=always" in unit and "ergostat.watcher" in unit


def test_the_page_shares_one_estimate_per_moment(project, monkeypatch):
    from ergostat.web import server
    live = server.Live(project)
    calls = []
    real = server.st.snapshot
    monkeypatch.setattr(server.st, "snapshot", lambda *a, **k: calls.append(1) or real(*a, **k))
    for path in ("status", "graph", "loops", "agents"):
        assert server.api(live, path, {}) is not None
    assert len(calls) == 1                                   # four requests of one moment, one estimate


def test_text_blocks_draw_an_open_loop_and_disturbances_both_ways(repo, capsys):
    text = repo.path.joinpath("ergostat.toml").read_text().replace('reads = ["disk-usage"]\n', 'open_loop = true\n')
    text += '\n[[disturbance]]\nname = "rotations"\nout_of = "disk-used"\n'
    repo.write("ergostat.toml", text)
    rc, out = run_cli(repo, "system", "--all", "--blocks", capsys=capsys)
    assert rc == 0 and "open loop" in out and "t: every 1s" in out
    assert "(−±)" in out and "not fed back" in out and "(Σ)" not in out
    rc, out = run_cli(repo, "status", capsys=capsys)                        # the alias
    assert rc == 0 and "disk-under-80" in out


def test_a_snapshot_without_logs_carries_no_unread_lines(project):
    from ergostat.web.snapshot import build
    project.events.add("agent.ran", item="cleaner", source="ergostat", data={"exit": 0, "unread": 1, "unread_lines": ["{secret oops"]})
    assert "secret oops" not in build(project) and "secret oops" in build(project, logs=True)


def test_reset_forgets_the_record_and_nothing_else(project, capsys):
    from ergostat.cli import main
    project.events.add("note.made", item="note/1")
    project.measurements.add("sensor/x", 1.0)
    (project.dir / "keep.txt").write_text("mine")
    assert main(["-C", str(project.repo), "reset"]) == 0                 # without --yes: says what, does nothing
    assert project.events.count() == 1
    assert main(["-C", str(project.repo), "reset", "--yes"]) == 0
    from ergostat import model as mdl
    from ergostat.store import Project
    p = Project(mdl.load(project.repo))
    assert p.events.count() == 0 and p.measurements.latest("sensor/x") is None
    assert (project.dir / "keep.txt").read_text() == "mine" and (project.dir / "repo.json").exists()


RELATED_MODEL = """
systems:
  planning: {description: what is planned}
  delivery: {description: what is built}
items:
  epic:
    id: epic/*
    system: planning
    states: [planned, underway, shipped]
    relations: {after: epic}
  goal:
    id: goal/*
    system: planning
    states: [open, met]
    relations: {serves: {kind: epic, precedence: false}}
  ticket:
    id: ticket/*
    system: delivery
    states: [todo, doing, done]
    on: {ticket.started: doing}
    relations: {blocked_by: ticket, parent: epic}
  note:
    id: note/*
    system: delivery
messages:
  done: {ticket: [done], epic: [shipped]}
"""


def related_project(tmp_path):
    """Related kinds in two systems: epics and goals in planning, tickets (and notes, unrelated) in delivery."""
    from ergostat import model as mdl
    from ergostat.store import Project
    (tmp_path / "ergostat.yaml").write_text(RELATED_MODEL)
    p = Project(mdl.load(tmp_path))
    import time
    ev, t = p.events, time.time() - 1800
    ev.add("epic.planned", item="epic/e1", data={"title": "first"}, at=t)
    ev.add("epic.planned", item="epic/e2", data={"title": "second", "after": "epic/e1"}, at=t + 1)
    ev.add("goal.set", item="goal/g", data={"title": "the goal", "serves": "epic/e2"}, at=t + 2)
    ev.add("ticket.planned", item="ticket/a", data={"title": "design", "parent": "epic/e1"}, at=t + 3)
    ev.add("ticket.planned", item="ticket/b", data={"title": "build", "parent": "epic/e1", "blocked_by": "ticket/a"}, at=t + 4)
    ev.add("ticket.started", item="ticket/a", at=t + 600)
    ev.add("note.made", item="note/n", at=t + 5)
    return p


def test_a_snapshot_holds_the_items_graph_the_page_asks_for(tmp_path):
    import re as _re

    from ergostat.web.snapshot import build, key
    html = build(related_project(tmp_path))
    data = json.loads(_re.search(r"window\.SNAPSHOT = (.*?);</script>", html, _re.S).group(1))["data"]
    listed = data["items"]
    # as pages.js: the kinds with relations or named by one, per system; and each alone (a kind chosen)
    rel = {n for k in listed["kinds"] for ts in (k["relations"] or {}).values() for n in (k["name"], *ts)}
    groups = {g["name"]: [n for n in g["kinds"] if n in rel] for g in listed["systems"]}
    assert groups["planning"] == ["epic", "goal"] and groups["delivery"] == ["ticket"]      # notes: no relations
    want = {key("items-graph", {"kinds": ",".join(ks)}) for ks in groups.values() if ks}
    want |= {key("items-graph", {"kinds": k["name"]}) for k in listed["kinds"]}    # a kind chosen: related or not
    own = {k["name"] for k in listed["kinds"] if k["name"].startswith("ergostat.")}    # ergostat's own kinds, alone too
    assert own and want == {"items-graph?kinds=epic,goal", "items-graph?kinds=epic", "items-graph?kinds=goal",
                            "items-graph?kinds=ticket", "items-graph?kinds=note", *(f"items-graph?kinds={k}" for k in own)}
    got = {k for k in data if k.startswith("items-graph")}
    assert got == want, got
    t = {x["id"]: x for x in data["items-graph?kinds=ticket"]["items"]}
    assert t["ticket/b"]["status"] == "blocked" and t["ticket/b"]["links"]["parent"] == ["epic/e1"]
    assert "epic/e1" in t and t["ticket/a"]["status"] == "active"                   # what its relations reach
    both = {x["id"] for x in data["items-graph?kinds=epic,goal"]["items"]}
    assert {"epic/e1", "epic/e2", "goal/g"} <= both and data["items-graph?kinds=epic,goal"]["asked"] == ["epic", "goal"]


def test_a_snapshot_holds_the_timeline_of_a_system_without_relations(tmp_path):
    # as pages.js: a system none of whose kinds has relations asks for its kinds that have items (the Timeline)
    import re as _re

    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    (tmp_path / "ergostat.yaml").write_text("systems:\n  desk: {description: the help desk}\nitems:\n"
                                            "  ticket: {id: ticket/*, system: desk}\n  call: {id: call/*, system: desk}\n"
                                            "  memo: {id: memo/*, system: desk}\n")
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/a", data={"title": "printer"})
    p.events.add("call.taken", item="call/c", data={"title": "a call"})
    data = json.loads(_re.search(r"window\.SNAPSHOT = (.*?);</script>", build(p), _re.S).group(1))["data"]
    got = data.get("items-graph?kinds=ticket,call") or data.get("items-graph?kinds=call,ticket")
    assert got is not None, sorted(k for k in data if k.startswith("items-graph"))
    assert {x["id"] for x in got["items"]} == {"ticket/a", "call/c"}                # memo: no items, not asked
    assert not any("memo" in k and "," in k for k in data if k.startswith("items-graph"))


def _snapshot_data(p) -> dict:
    import re as _re

    from ergostat.web.snapshot import build
    return json.loads(_re.search(r"window\.SNAPSHOT = (.*?);</script>", build(p), _re.S).group(1))["data"]


def _timeless(x):
    """An answer without what says when it was taken (the snapshot's moment is not the test's)."""
    return {k: v for k, v in x.items() if k not in ("now", "since", "at")} if isinstance(x, dict) else x


def test_a_snapshot_holds_each_kind_chosen_and_each_of_its_states(tmp_path, monkeypatch):
    from ergostat.web import server
    from ergostat.web.server import Live, api
    from ergostat.web.snapshot import key
    # the completion estimates come from a background worker, so the snapshot and a later live call could differ only
    # by when it finished (lesson-10): none in either, so the two answers are compared whole
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    p = related_project(tmp_path)
    data = _snapshot_data(p)
    kinds = {k["name"]: k for k in data["items"]["kinds"]}
    assert {"epic", "goal", "ticket", "note"} <= set(kinds)                       # and ergostat's own kinds
    want = []
    for name, k in kinds.items():
        want += [("items", {"kind": name}), ("items-graph", {"kinds": name})]
        want += [("items", {"kind": name, "state": s}) for s in k["states"]]
    live = Live(p)
    for path, params in want:
        k = key(path, params)
        assert k in data, k
        every = {"finished": ["show"]} if path == "items" else {}   # a snapshot holds the finished too (SPEC §5a)
        assert _timeless(data[k]) == _timeless(json.loads(json.dumps(
            api(live, path, {"since": ["1h"], **every, **{a: [b] for a, b in params.items()}}), default=str))), k
    ids = lambda k: sorted(i["id"] for i in data[k]["items"])                       # noqa: E731
    assert ids("items?kind=ticket") == ["ticket/a", "ticket/b"]
    assert ids("items?kind=ticket&state=doing") == ["ticket/a"]                     # ticket.started: doing
    assert ids("items?kind=ticket&state=todo") == ["ticket/b"]
    assert "note/n" in {i["id"] for i in data["items-graph?kinds=note"]["items"]}


def test_a_kind_whose_list_cannot_be_answered_is_left_out_of_the_snapshot(tmp_path, monkeypatch):
    from ergostat.web import snapshot
    real = snapshot.api
    every = {"finished": "show"}                                   # each items answer is asked with the finished too
    broken = [("items", {"kind": "ticket", **every}), ("items", {"kind": "epic", "state": "underway", **every}),
              ("items-graph", {"kinds": "note"})]

    seen = []

    def api(live, path, q):
        asked = {k: v[0] for k, v in q.items() if k != "since"}
        seen.append((path, asked))
        if (path, asked) in broken:
            raise RuntimeError("cannot be answered")
        return real(live, path, q)
    monkeypatch.setattr(snapshot, "api", api)
    data = _snapshot_data(related_project(tmp_path))
    for path, params in broken:
        assert (path, params) in seen, (path, params)                     # asked, so its absence is the failure's
        params = {k: v for k, v in params.items() if k != "finished"}                # held under the page's own key
        assert snapshot.key(path, params) not in data                                # absent, not empty
    assert ("items", {"kind": "ticket", "state": "doing", **every}) not in seen   # no states asked without the kind's own answer
    assert not any(k.startswith("items?kind=ticket") for k in data)    # its states, from its own answer: none to be had
    assert {"items", "items?kind=epic", "items?kind=epic&state=planned", "items?kind=goal", "items?kind=note",
            "items-graph?kinds=ticket", "items-graph?kinds=epic,goal", "status", "graph"} <= set(data)
    assert sorted(i["id"] for i in data["items?kind=epic"]["items"]) == ["epic/e1", "epic/e2"]


def test_the_items_graph_says_when_its_finish_is_still_being_worked_out(tmp_path, monkeypatch):
    """The legend's 'being worked out' (SPEC §5a Graph): pending while the estimates of now are not yet there;
    never at a moment travelled to, which has none to wait for; nor once they are."""
    import time as t

    from ergostat.web import eta_api, server
    live = server.Live(related_project(tmp_path))
    monkeypatch.setattr(eta_api, "estimates", lambda *a, **k: None)
    assert server.api(live, "items-graph", {"kinds": ["epic"]})["eta_pending"] is True
    past = server.api(live, "items-graph", {"kinds": ["epic"], "at": [str(t.time() - 600)]})
    assert past["eta_pending"] is False
    monkeypatch.setattr(eta_api, "estimates", lambda *a, **k: {"items": {}, "kinds": {}})
    assert server.api(live, "items-graph", {"kinds": ["epic"]})["eta_pending"] is False


def test_every_examples_loops_answer_carries_each_goals_word_and_row(tmp_path, monkeypatch):
    """The Goals page draws a goal's row from /api/loops alone (goalrow.js): every goal of every example says its word,
    the status's own, and its row's columns."""
    import shutil
    from pathlib import Path

    from ergostat import model
    from ergostat.store import Project
    from ergostat.web import server
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    seen = 0
    for ex in sorted((Path(__file__).resolve().parent.parent / "examples").glob("*/ergostat.yaml")):
        d = tmp_path / ex.parent.name
        shutil.copytree(ex.parent, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
        loops = server.api(server.Live(Project(model.load(d))), "loops", {})
        for name, lp in loops.items():
            assert lp["word"] == (lp["status"] if lp["status"] in state.WORDS else "unknown"), (ex, name, lp["word"])
            assert set(lp["row"]) == {"measure", "value", "unit", "bound_words", "trend", "expected"}, (ex, name)
            assert lp["row"]["measure"] == lp["stock"] and lp["row"]["value"] == lp["value"], (ex, name)
            seen += 1
    assert seen > 20, seen


GOAL_TEXT = [  # a goal's state made reader text in a page script: only goalrow.js may (goalWord, goalRow)
    re.compile(r"\bstatus\s*[!=]==?\s*[\"'](?:holding|off|open|unknown|stale)[\"']"),
    re.compile(r"[\"']holding[\"']"),
    re.compile(r"\b(?:statusEl|exceptional)\([^)]*\.status\b"),
]
NOT_A_GOAL = {  # (file, what the line says): states that are not a goal's
    ("details.js", "exceptional(n.status) ? statusEl(n.status)"),   # a system box's own state (openSystem)
    ("pages.js", 'x.how || "holding"'),                             # a lease still held
}


def test_no_page_script_words_a_goals_state_but_goalrow():
    """Every surface printing a goal's state asks goalWord or goalRow; a page mapping status to a word itself fails."""
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "ergostat" / "web" / "static"
    vendored = {"elk.bundled.js", "marked.min.js", "highlight.min.js", "goalrow.js"}
    found = [(f.name, line.strip()) for f in sorted(static.rglob("*.js")) if f.name not in vendored and "uplot" not in f.parts
             for line in f.read_text().splitlines() if any(r.search(line) for r in GOAL_TEXT)
             and not any(f.name == n and s in line for n, s in NOT_A_GOAL)]
    assert not found, found
    assert '<script src="/static/goalrow.js">' in (static / "index.html").read_text()
