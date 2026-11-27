import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

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
        assert get("/")[0] == 200 and b'<div id="root"></div>' in get("/")[1]
        try:
            get("/api/part/stock/nope")
            raise AssertionError("404 expected")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
        server.server_close()


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


def test_a_search_or_filter_that_matches_nothing_answers_empty_and_a_match_is_counted_whole():
    """What the Items page's count beside its search box and the Record's 'Nothing matches' are read from (the browser
    half is tests/test_items_page.py): a search's ``matched`` counts every match of a kind, past the newest per_kind
    listed, and holds no kind for a miss, so the page draws no kind; a kind matched by name keeps all of its items."""
    from ergostat.web.server import _as_listed
    its = [{"id": f"ticket/{n}", "projection": "ticket", "fields": {"title": f"t{n}"}} for n in range(1, 31)]
    got = {"projections": [{"name": "ticket", "show": ["title"]}, {"name": "bug", "show": []}],
           "items": [*its, {"id": "bug/1", "projection": "bug", "fields": {}}]}
    assert _as_listed(got, "zzqx", 25, True)["matched"] == {}
    one = _as_listed(got, "ticket/2", 25, True)            # ticket/2 and ticket/20..29: eleven, all counted
    assert one["matched"] == {"ticket": 11} and len(one["items"]) == 11
    assert _as_listed(got, " TICKET ", 25, True)["matched"] == {"ticket": 30}   # by the kind's name: all 30, 25 listed
    assert len(_as_listed(got, "ticket", 25, True)["items"]) == 25


def test_the_record_answers_a_type_that_matches_nothing_with_no_events(project):
    """The Record's 'Nothing matches “zzz” · clear' is drawn on an empty answer to its type filter: the answer must be
    empty for a miss, and the record's events come back once the filter is cleared."""
    from ergostat.web import serve
    project.events.add("cleanup.done", item="disk/1")
    server, url = serve(project, free_port())
    try:
        def events(query):
            with urllib.request.urlopen(url + "/api/events?n=80" + query, timeout=10) as r:
                return json.loads(r.read())
        assert events("&type=zzz") == []
        assert [e["type"] for e in events("&type=cleanup.done")] == ["cleanup.done"]
        assert events("")
    finally:
        server.shutdown()
        server.server_close()




def test_a_process_view_with_no_projections_is_answered_empty_and_the_page_says_so_over_the_canvas(tmp_path):
    """big has no projections: its Process answer is empty, so the page takes its empty branch, whose words give the
    reason and Dynamics, laid over the canvas (not below it). The browser half of this check, the text's box inside the
    canvas's, is tests/test_diagram_rendering.py::test_process_view_with_no_kinds_says_so_inside_the_canvas."""
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
        g = json.loads(get("/api/graph?view=process"))
    finally:
        server.shutdown()
        server.server_close()
    assert not g["nodes"] and not g["projections"], g                  # nothing to draw: the empty branch
    app = (root / "ergostat" / "web" / "ui" / "src" / "components" / "diagram" / "useLayout.ts").read_text()
    assert "No projections here: its parts are counted by sensors." in app




def test_an_off_goal_reaches_the_side_list_as_a_named_goal_with_its_stock(project):
    """What the side list's goal button reads: an off goal's attention entry names the goal, and its loop names its
    stock."""
    from ergostat.web.server import Live, api
    project.measurements.add("sensor/disk-usage", 95.0)
    st = api(Live(project), "status", {})
    assert st["loops"]["disk-under-80"]["status"] == "off" and st["loops"]["disk-under-80"]["stock"]
    off = [a for a in st["attention"] if a["what"] == "goal disk-under-80" and a["level"] == "bad"]
    assert off, st["attention"]


def test_static_files_are_versioned_and_the_page_is_revalidated(project):
    """After an update the browser runs the new scripts without a manual reload: the app's files are named by their
    content's hash and kept for good, a vendored file asked for with its current version is kept for good, and the
    page itself is always asked again (no-cache, with an ETag)."""
    import re
    from http.server import ThreadingHTTPServer

    from ergostat.web import server
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
        assert refs and all(r.startswith(b"/static/app/assets/") for r in refs), refs  # every script and stylesheet
        assert get(refs[0].decode())[1]["Cache-Control"] == server.FOREVER          # named by its hash: kept for good
        (project.dir / "notes.md").write_text("# N\n")
        code, headers, body = get("/api/file/notes.md", Accept="text/html")      # a Markdown file's page
        marked = re.search(rb'src="(/static/marked\.min\.js\?v=[^"]+)"', body).group(1).decode()
        assert code == 200 and get(marked)[1]["Cache-Control"] == server.FOREVER
        assert get("/static/marked.min.js")[1]["Cache-Control"] == "no-cache"      # unversioned: asked again each time
        assert get("/static/marked.min.js?v=old")[1]["Cache-Control"] == "no-cache"
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


def test_the_projects_summary_counts_goals(monkeypatch, capsys):
    import types

    from ergostat import projects
    from ergostat.cli import running
    g = {"system": 1, "open": 0, "unknown": 0, "own": {}}
    row = {"name": "p", "running": False, "web": None, "repo": "/r", "loops": 3, "goals": g, "goals_off": ["x"]}
    monkeypatch.setattr(projects, "known", lambda: [row, {**row, "name": "q", "loops": 0, "goals_off": []}])
    running.cmd_projects(types.SimpleNamespace(json=False))
    out = capsys.readouterr().out
    assert "GOALS" in out and "1 goal off: x" in out and "no goals" in out and "loop" not in out, out


def test_an_attention_entry_about_a_goal_names_it_as_a_field(project):
    """/api/status: an off goal's entry, and a hint about it, read 'goal NAME' and carry goal: NAME; none says 'loop '."""
    from ergostat.web import server
    project.measurements.add("sensor/disk-usage", 90)
    live = server.Live(project)
    att = server.api(live, "status", {})["attention"]
    mine = [a for a in att if a.get("goal") == "disk-under-80"]
    assert mine and all(a["what"] == "goal disk-under-80" for a in mine) and mine[0]["level"] == "bad", att
    assert not [a for a in att if a["what"].startswith("loop ")], att
    snap = {**server.st.snapshot(project), "hints": [{"controller": "disk-under-80", "goal": "disk-under-80",
                                                       "says": "goal disk-under-80 was off 60% of the time"}]}
    hint = [a for a in server.st.attention(snap) if a["level"] == "hint"]
    assert hint == [{"level": "hint", "what": "goal disk-under-80", "goal": "disk-under-80",   # (named once: its heading)
                     "says": "was off 60% of the time"}], hint


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
projections:
  epic:
    match:
      key: epic/*
    system: planning
    states: [planned, underway, shipped]
    relations: {after: epic}
  goal:
    match:
      key: goal/*
    system: planning
    states: [open, met]
    relations: {serves: {projection: epic, precedence: false}}
  ticket:
    match:
      key: ticket/*
    system: delivery
    states: [todo, doing, done]
    events:
      ticket.started:
        state: set('doing')
    otherwise: rest
    relations: {blocked_by: ticket, parent: epic}
  note:
    match:
      key: note/*
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


def _timeless(x):
    """An answer without what says when it was taken (the snapshot's moment is not the test's)."""
    return {k: v for k, v in x.items() if k not in ("now", "since", "at")} if isinstance(x, dict) else x


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
