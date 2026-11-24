"""Templates (SPEC §2a): a use expands into ordinary parts named for its instance, one system per use, every part
pointing at the use: line; parameters are checked; the owner's own templates are found beside ergostat's; every
built-in template checks and runs on its stand-ins; the authoring tools write, try and show an instance."""

import json
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ergostat.library import author
from ergostat.library import templates as tp
from ergostat.library.expand import Via
from ergostat.spec import read
from ergostat.spec.load import load

ROOT = Path(__file__).resolve().parent.parent


def project(tmp_path: Path, text: str, files: dict | None = None) -> Path:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    for name, body in (files or {}).items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(textwrap.dedent(body))
    return tmp_path / "ergostat.yaml"


def problems(path: Path, level: str = "error"):
    _, ps = read(path)
    return [p for p in ps if p.level == level]


RESPOND = """
name: t
systems:
  work: {}
uses:
  questions:
    use: respond-to
    within: work
    with:
      within: 2h
      answer: ./bin/answer.sh
"""


def test_a_use_expands_into_parts_named_for_the_instance(tmp_path):
    spec, ps = read(project(tmp_path, RESPOND))
    assert not [p for p in ps if p.level == "error"], ps
    assert "questions-waiting" in spec.stocks and "questions-oldest" in spec.auxiliaries
    f = spec.flows["questions-answered"]
    assert f.source == "questions-waiting"
    g = spec.goals["questions-on-time"]
    assert str(g.of) == "auxiliary.questions-oldest" and str(g.hold) == "<= 2"
    b = spec.blocks["questions-answer"]
    assert "--flow flow.questions-answered" in b.params["run"] and "./bin/answer.sh" in b.params["run"]
    assert spec.items["questions"].id == "questions/*"            # a name given whole by a parameter is not prefixed
    assert spec.within["questions"] == "work"                     # the instance is a system, within the one it names
    assert all(x.system == "questions" for x in (*spec.stocks.values(), *spec.flows.values(), spec.blocks["questions-answer"]))
    assert spec.uses["questions"]["template"] == "respond-to"


def test_every_part_it_makes_points_at_the_use_line(tmp_path):
    spec, _ = read(project(tmp_path, RESPOND))
    w = spec.stocks["questions-waiting"].where
    assert isinstance(w, Via) and w.line == 7 and w.template == "respond-to"
    assert str(w) == "ergostat.yaml:7 (use questions: respond-to)"


def test_an_error_in_what_it_makes_points_at_the_use_line(tmp_path):
    path = project(tmp_path, """
        name: t
        stocks:
          questions-waiting: {unit: x, sensor: {run: echo 1}}
        uses:
          questions:
            use: respond-to
        """)
    errs = problems(path)
    twice = [e for e in errs if e.code == "defined-twice"]
    assert twice and twice[0].where.line == 7 and "stock questions-waiting is defined twice" in twice[0].message


def test_parameters_are_checked_where_they_are_written(tmp_path):
    path = project(tmp_path, """
        name: t
        uses:
          disk:
            use: keep-under
            with:
              limt: 80
              every: soon
          nothing:
            use: no-such-template
        """)
    errs = {e.message: e.where.line for e in problems(path)}
    assert any("has no parameter 'limt' (did you mean limit?)" in m and ln == 7 for m, ln in errs.items()), errs
    assert any("with.limit: keep-under needs it" in m and ln == 5 for m, ln in errs.items()), errs
    assert any("with.every" in m and "not a duration" in m and ln == 8 for m, ln in errs.items()), errs
    assert any("no template 'no-such-template'" in m and ln == 10 for m, ln in errs.items()), errs


def test_a_use_in_an_included_file_takes_its_files_default_system(tmp_path):
    path = project(tmp_path, """
        name: t
        include: [parts/*.yaml]
        systems:
          ops: {}
        """, {"parts/disk.yaml": """
        defaults:
          system: ops
        uses:
          disk:
            use: keep-under
            with:
              limit: 80
        """})
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    assert spec.within["disk"] == "ops" and spec.stocks["disk-level"].system == "disk"
    assert spec.stocks["disk-level"].where.file.name == "disk.yaml"


def test_an_instance_named_twice_is_an_error(tmp_path):
    path = project(tmp_path, """
        name: t
        include: [more.yaml]
        uses:
          disk: {use: keep-under, with: {limit: 1}}
        """, {"more.yaml": """
        uses:
          disk: {use: keep-under, with: {limit: 2}}
        """})
    assert any(e.code == "defined-twice" and "use disk" in e.message for e in problems(path))


PRIVATE = """
template: nag
description: a private template that uses a built-in one
params:
  level:
    type: number
    default: 5
  who:
    type: strings
    default: [ana, ben]
stocks:
  counter:
    unit: things
    description: counted for ${who:json}
    sensor:
      run: echo ${level}
      every: 1m
flows:
  added: {to: counter}
uses:
  inner:
    use: keep-under
    with:
      limit: ${level}
      measure: echo ${level}
"""


def test_the_owners_templates_come_from_library_folders_and_may_use_ergostats(tmp_path):
    lib = tmp_path / "private"
    lib.mkdir()
    (lib / "nag.yaml").write_text(PRIVATE)
    (tmp_path / "proj").mkdir()
    path = project(tmp_path / "proj", """
        name: t
        library: ../private
        uses:
          n:
            use: nag
            with: {level: 7}
        """)
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    assert spec.stocks["n-counter"].sensors["main"].run == "echo 7"
    assert '["ana", "ben"]' in spec.stocks["n-counter"].description
    assert "n-inner-level" in spec.stocks and spec.within["n-inner"] == "n"
    assert str(spec.goals["n-inner-under"].hold) == "<= 7"
    assert spec.template_files == [lib / "nag.yaml"]


def test_an_owners_template_shadows_ergostats_and_says_so(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "collect.yaml").write_text("template: collect\ndescription: mine\nstocks:\n  x: {unit: u, sensor: {run: echo 1}}\n"
                                      "flows:\n  in: {to: x}\n")
    monkeypatch.setenv("ERGOSTAT_LIBRARY", str(lib))
    got, notes = tp.find_all()
    assert got["collect"].description == "mine" and any("in place of ergostat's own" in n for n in notes)


def test_each_unrolls_a_list_into_parts(tmp_path):
    spec, ps = read(project(tmp_path, """
        name: t
        uses:
          tickets:
            use: steps
            with:
              steps: [triage, {name: fix, run: ./fix.sh}, review]
        """))
    assert not [p for p in ps if p.level == "error"], ps
    k = spec.items["tickets"]
    assert k.states == ["triage", "leased", "fix", "review", "done", "dead"]     # a lease's own states, added
    assert k.on == {"tickets.triage-done": "fix", "tickets.fix-done": "review", "tickets.review-done": "done"}
    assert spec.flows["tickets-arriving"].target == "tickets-triage"
    assert (spec.flows["tickets-fix-taken"].source, spec.flows["tickets-fix-taken"].target) == ("tickets-fix", "tickets-fix-working")
    assert spec.flows["tickets-review-done"].source == "tickets-review-working"
    assert spec.flows["tickets-review-done"].target == "tickets-done"
    assert spec.flows["tickets-fix-retried"].target == "tickets-fix"
    assert spec.flows["tickets-fix-stuck"].target == "tickets-stuck"
    fix = spec.blocks["tickets-fix"]
    assert "./fix.sh" in fix.params["run"] and "--run ''" in spec.blocks["tickets-triage"].params["run"]
    assert fix.goal == "tickets-fix-clear" and not fix.every
    assert (fix.takes.kind, fix.takes.at, fix.takes.to, fix.pool, fix.lease.attempts) == ("tickets", ["fix"], ["review"], 2, 3)
    assert next(iter(spec.stocks["tickets-fix-working"].sensors.values())).items["where"] == {"lease.back": "fix"}


def test_a_step_may_be_an_ai_agent_in_a_workspace_with_gated_actions(tmp_path):
    (tmp_path / "repo").mkdir()
    spec, ps = read(project(tmp_path, """
        name: t
        uses:
          tickets:
            use: steps
            with:
              pool: 3
              tries: 2
              ai-ttl: 30m
              workspace: {repo: repo, size: 2}
              actions:
                - {name: push, run: "git push origin HEAD:refs/heads/{branch}", gate: approve}
              steps:
                - triage
                - {name: fix, prompt: prompts/fix.md, tools: [Read, Edit], actions: [push]}
        """, {"prompts/fix.md": "Fix it.\n"}))
    assert not [p for p in ps if p.level == "error"], ps
    fix, triage = spec.blocks["tickets-fix"], spec.blocks["tickets-triage"]
    assert fix.type == "ai" and "run" not in fix.params and fix.params["prompt"] == "prompts/fix.md"
    assert fix.params["workspace"] == "tickets-workspace" and fix.params["actions"] == ["tickets-push"]
    assert (fix.pool, fix.lease.ttl, fix.lease.attempts, fix.timeout) == (3, 1800.0, 2, 1800.0)
    assert triage.type == "program" and "workspace" not in triage.params and triage.lease.ttl is None
    assert spec.workspaces["tickets-workspace"].repo == "repo"
    assert spec.actions["tickets-push"].gate == "approve"


def test_a_value_may_be_chosen_by_a_condition(tmp_path):
    from ergostat.library.expand import DROP, Scope, walk
    sc = Scope({"p": ("x", False), "q": (None, False)})
    assert walk({"if": "${p}", "value": "a", "else": "b"}, sc) == "a"
    assert walk({"if": "${q}", "value": "a", "else": "b"}, sc) == "b"
    assert walk({"unless": "${p}", "value": "a"}, sc) is DROP
    assert walk({"k": {"if": "${q}", "value": "a"}}, sc) == {}


def test_a_key_left_empty_is_left_out_and_if_drops_an_entry(tmp_path):
    spec, ps = read(project(tmp_path, """
        name: t
        uses:
          disk:
            use: keep-under
            with: {limit: 80, rung: person}
          q:
            use: respond-to
            with: {escalate: false}
        """))
    assert not [p for p in ps if p.level == "error"], ps
    assert "disk-correct" not in spec.blocks and spec.blocks["disk-correct-by-hand"].type == "person"
    assert spec.stocks["disk-level"].limit is None                 # fails-at not given: no limit: key at all
    assert "q-escalate" not in spec.blocks and "q-answered-by-hand" not in spec.flows


def test_stand_ins_are_said_and_a_trial_may_force_them(tmp_path, monkeypatch):
    path = project(tmp_path, RESPOND)
    finds = [p for p in problems(path, "finding") if p.code == "template-stand-in"]
    assert finds and "command or url" in finds[0].message and "answer" not in finds[0].message.split("(")[1]
    monkeypatch.setenv("ERGOSTAT_STANDINS", "1")
    spec, _ = read(path)
    assert "./bin/answer.sh" not in spec.blocks["questions-answer"].params["run"]


@pytest.mark.parametrize("name", sorted(tp.find_all()[0]))
def test_every_built_in_template_checks_with_its_example(tmp_path, name):
    t = tp.find_all()[0][name]
    assert t.description and t.reading and t.example, "each says what it is, in both disciplines, with an example"
    assert "Control" in t.reading and "System dynamics" in t.reading
    (tmp_path / "ergostat.yaml").write_text("name: t\n" + t.example + "\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    assert spec.uses


def test_no_built_in_templates_description_names_a_spec_section():
    """A template's description is shown on the reader's pages (a part's panel): what it is, not where SPEC says so."""
    said = {n: t.description for n, t in tp.find_all()[0].items() if "SPEC §" in (t.description or "")}
    assert not said, said


def test_with_every_default_each_runs_on_stand_ins(tmp_path):
    needs = {"keep-under": {"limit": 10}, "steps": {"steps": ["a", "b"]}}
    body = "name: t\nuses:\n" + "".join(f"  u-{n}:\n    use: {n}\n    with: {json.dumps(needs.get(n, {}))}\n"
                                         for n in sorted(tp.find_all()[0]))
    (tmp_path / "ergostat.yaml").write_text(body)
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    assert not [p for p in ps if p.code == "missing-feedback"], "every goal a template holds is served"


def test_observed_autoscaler_on_stand_ins(tmp_path):
    spec, ps = read(project(tmp_path, "name: t\nuses:\n  web: {use: observed-autoscaler, with: {target: 0.6, max: 8}}\n"))
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    ext = [b for b in spec.blocks.values() if b.type == "external"]
    assert [b.name for b in ext] == ["web-hpa"] and ext[0].law.kind == "kubernetes-hpa"
    assert ext[0].law.params["target"] == 0.6 and (ext[0].law.params["min"], ext[0].law.params["max"]) == (1, 8)
    assert ext[0].law.params["every"] == 15.0 and ext[0].law.params["stabilize-down"] == 300.0   # the HPA's own, left out
    g = spec.goals["web-at-target"]
    assert str(g.of) == "auxiliary.web-utilisation" and str(g.hold) == "<= 0.6"
    assert "standin replicas" in spec.stocks["web-replicas"].sensors["main"].run
    assert not spec.auxiliaries["web-utilisation"].sensors, "left out: load / replicas, not measured"
    finds = [p.message for p in ps if p.code == "template-stand-in"]
    assert finds and "replicas or replicas-query" in finds[0] and "load or load-query" in finds[0], finds
    q = {"source": "prom", "promql": "sum(x)"}
    spec, ps = read(project(tmp_path, "name: t\nuses:\n  web:\n    use: observed-autoscaler\n    with:\n"
                            f"      utilisation-query: {json.dumps(q)}\n      replicas: echo 3\n"))
    assert spec.auxiliaries["web-utilisation"].sensors["main"].query == q
    assert spec.stocks["web-replicas"].sensors["main"].run == "echo 3"


def test_observed_autoscaler_stand_ins_follow_a_made_up_load(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    project(tmp_path, "name: s\n")
    args = ["--name", "w", "--target", "0.5", "--min", "2", "--max", "10"]
    load = float(run_lib(tmp_path, "standin", "load", *args).stdout)
    assert 0.5 * 6 * 0.5 <= load <= 0.5 * 6 * 1.5
    first = int(run_lib(tmp_path, "standin", "replicas", *args).stdout)
    assert 2 <= first <= 10 and abs(first - math.ceil(load / 0.5)) <= 1
    assert abs(int(run_lib(tmp_path, "standin", "replicas", *args).stdout) - first) <= 1, "one replica a reading"
    sig = float(run_lib(tmp_path, "standin", "signal", "--threshold", "100").stdout)
    assert run_lib(tmp_path, "standin", "firing", "--threshold", "100").stdout.strip() in ("0", "1") and 50 <= sig <= 150


def test_observed_autoscaler_blocks_loop(tmp_path):
    from types import SimpleNamespace

    from ergostat import blockdiagram as bd
    for given, y, key in (("{}", "proc", "auxiliary.web-utilisation"),     # load / replicas: y straight from its process
                          ("{utilisation: echo 0.5}", "sen", "meas.auxiliary.web-utilisation.main")):   # measured: its sensor
        spec, _ = read(project(tmp_path, f"name: t\nuses:\n  web: {{use: observed-autoscaler, with: {given}}}\n"))
        g = bd.diagram(SimpleNamespace(spec=spec), {})
        into = {e["signal"]["sym"]: e for e in g["edges"] if e["target"] == "blk:web-hpa"}
        out = [e for e in g["edges"] if e["source"] == "blk:web-hpa"]
        assert set(into) == {"r", "y"}, into
        assert into["r"]["source"] == "ref:web-at-target" and into["r"]["signal"]["sub"] == "web-at-target", into
        assert into["y"]["source"] == f"{y}:auxiliary.web-utilisation" and into["y"]["key"] == key, into
        assert [(e["signal"]["sym"], e["key"]) for e in out] == [("u", "stock.web-replicas")], out
        n = next(x for x in g["nodes"] if x["id"] == "blk:web-hpa")
        assert n["role"] == "controller" and n["declared"] == "declared kubernetes-hpa", n


@pytest.mark.slow
def test_observed_autoscaler_and_alert_rule_run_offline_and_draw_in_both_views(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.server import Live, api
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    for inst, tpl, part in (("web", "observed-autoscaler", "web-replicas"), ("slow", "alert-rule", "slow-firing")):
        root = tmp_path / inst
        root.mkdir()
        (root / "ergostat.yaml").write_text("name: p\n")
        given = {"every": "2s", **({"pages": "slow-page"} if inst == "slow" else {})}     # pages: the stock still reads
        got = author.trial(root, None, 12, {"instance": inst, "template": tpl, "given": given})
        assert got["check"]["ok"], got
        assert got["ran"]["stocks"][part]["sensors"], got["ran"]["stocks"]       # its stand-ins read, offline
        monkeypatch.setenv("ERGOSTAT_HOME", str(Path(got["scratch"]).parent / "home"))
        live = Live(Project(mdl.load(Path(got["scratch"]))))
        for view, node in (("dynamics", f"stock:{part}"), ("blocks", f"blk:{inst}-{'hpa' if inst == 'web' else 'rule'}")):
            ids = {n["id"] for n in api(live, "graph", {"view": [view]})["nodes"]}
            assert node in ids, (view, sorted(ids))
        monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))


def test_alert_rule_template_compiles(tmp_path):
    spec, ps = read(project(tmp_path, "name: t\nuses:\n  slow:\n    use: alert-rule\n"
                            "    with: {threshold: 300, for: 2m, pages: slow-page}\n"))
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    b = spec.blocks["slow-rule"]
    assert b.type == "external" and b.law.kind == "alert-rule"
    assert b.law.params == {"threshold": 300.0, "side": "above", "for": 120.0}
    idf = b.params["identify"]
    assert (str(idf["input"]), str(idf["output"])) == ("auxiliary.slow-signal", "stock.slow-firing")
    assert "standin signal" in spec.auxiliaries["slow-signal"].sensors["main"].run
    # pages makes no items (ergostat never runs the rule): the firing stock stays on its measured sensor or stand-in
    assert "standin firing" in spec.stocks["slow-firing"].sensors["main"].run
    assert not spec.stocks["slow-firing"].sensors["main"].items
    assert spec.items["slow-page"].states == ["firing", "resolved"]
    assert [p for p in ps if p.code == "template-stand-in"]
    spec, ps = read(project(tmp_path, "name: t\nuses:\n  slow: {use: alert-rule, with: {threshold: 5, side: below}}\n"))
    assert not [p for p in ps if p.level == "error"] and not [k for k in spec.items if not k.startswith("ergostat.")]
    assert "standin firing" in spec.stocks["slow-firing"].sensors["main"].run and spec.blocks["slow-rule"].law.params["side"] == "below"


def test_alert_rule_with_pages_reads_its_firing_stock_moving_with_the_signal(tmp_path, monkeypatch, capsys):
    import shlex

    from ergostat.library.run import standin
    spec, _ = read(project(tmp_path, "name: t\nuses:\n  slow: {use: alert-rule, with: {threshold: 100, pages: slow-page}}\n"))
    words = shlex.split(spec.stocks["slow-firing"].sensors["main"].run)
    args = words[words.index("standin") + 1:]
    assert args[0] == "firing", words
    seen = []
    for t in (450.0, 1350.0, 2250.0):                  # the made-up signal at its crest (150), trough (50), crest again
        monkeypatch.setattr(standin, "now", lambda t=t: t)
        assert standin.alert(args) == 0
        seen.append(capsys.readouterr().out.strip())
    assert seen == ["1", "0", "1"], seen


def run_lib(cwd: Path, *args, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ergostat.library.run", *args], cwd=cwd, input=stdin, capture_output=True,
                          text=True, env={**os.environ, **(env or {})})


def test_the_collector_says_each_record_once_from_its_cursor(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    project(tmp_path, "name: c\n")
    src = tmp_path / "src.sh"
    src.write_text('echo \'{"id": 1, "n": 1, "title": "a"}\'\necho \'{"id": 2, "n": 2}\'\n'
                   'echo "{\\"id\\": 3, \\"n\\": 3, \\"cursor\\": \\"$ERGOSTAT_CURSOR\\"}"\n')
    args = ["collect", "--name", "c", "--kind", "q", "--command", "sh src.sh", "--cursor-field", "n"]
    first = run_lib(tmp_path, *args)
    lines = [json.loads(x) for x in first.stdout.splitlines() if x.startswith("{")]
    assert [x["item"] for x in lines] == ["q/1", "q/2", "q/3"] and lines[0]["event"] == "q.arrived"
    assert lines[0]["data"]["title"] == "a" and float(first.stdout.splitlines()[-1]) == pytest.approx(18.0)
    again = run_lib(tmp_path, *args)
    assert not [x for x in again.stdout.splitlines() if x.startswith("{")], "nothing said twice, nothing before the cursor"


def test_the_collector_reads_an_event_field_and_a_url(tmp_path, monkeypatch):
    import http.server
    import threading
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    project(tmp_path, "name: c\n")
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen["auth"] = self.headers.get("Authorization")
            body = json.dumps({"data": {"items": [{"key": "a", "event": "answered"}, {"key": "b"}]}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = run_lib(tmp_path, "collect", "--name", "u", "--kind", "q", "--url", f"http://127.0.0.1:{srv.server_port}/x",
                    "--id-field", "key", "--path", "data", "--header", "Authorization: Bearer $TOK", env={"TOK": "s3"})
    finally:
        srv.shutdown()
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    assert [(x["event"], x["item"]) for x in lines] == [("q.answered", "q/a"), ("q.arrived", "q/b")], r.stderr
    assert seen["auth"] == "Bearer s3"


def test_the_stand_in_level_rises_and_its_correction_lowers_it(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    project(tmp_path, "name: s\n")
    v = float(run_lib(tmp_path, "standin", "level", "--name", "d", "--limit", "100").stdout)
    assert 89 < v < 95
    moved = json.loads(run_lib(tmp_path, "standin", "lower", "--name", "d", "--limit", "100").stdout)["moved"]
    assert moved == pytest.approx(10.0)
    assert float(run_lib(tmp_path, "standin", "level", "--name", "d", "--limit", "100").stdout) < v


def test_add_use_shows_the_diff_and_writes_only_when_asked(tmp_path):
    shutil_copy(tmp_path)
    root = tmp_path / "job"
    before = (root / "ergostat.yaml").read_text()
    got = author.add(root, "pings", "re-ping", {"every": "1d", "limit": 2}, file="job/pings.yaml", within="delivery")
    assert got["ok"] and got["written"] is False and "+  pings:" in got["diff"] and not (root / "job/pings.yaml").exists()
    assert (root / "ergostat.yaml").read_text() == before, "a new file job/*.yaml is already included"
    assert "pings-unanswered" in got["parts"]["stocks"]
    got = author.add(root, "pings", "re-ping", {"every": "1d", "limit": 2}, file="job/pings.yaml", within="delivery", write=True)
    assert got["written"] == ["job/pings.yaml"]
    spec, ps = read(root / "ergostat.yaml")
    assert spec.within["pings"] == "delivery" and not [p for p in ps if p.level == "error"]
    with pytest.raises(author.AuthorError):
        author.add(root, "pings", "re-ping", {}, file="job/pings.yaml")
    got = author.add(root, "pings", "re-ping", {"every": "2d"}, file="job/pings.yaml", replace=True, write=True)
    assert "every: 2d" in (root / "job/pings.yaml").read_text() and "limit" not in (root / "job/pings.yaml").read_text()
    bad = author.add(root, "other", "re-ping", {"every": "never"}, file="extra/other.yaml", write=True)
    assert not bad["ok"] and bad["written"] is False and not (root / "extra/other.yaml").exists()
    good = author.add(root, "other", "keep-under", {"limit": 3}, file="extra/other.yaml", write=True)
    assert good["written"] == ["extra/other.yaml", "ergostat.yaml"] and "  - extra/other.yaml" in (root / "ergostat.yaml").read_text()
    assert "other" in load(root / "ergostat.yaml").uses


def shutil_copy(tmp_path: Path) -> None:
    import shutil
    shutil.copytree(ROOT / "examples" / "the-job", tmp_path / "job", ignore=shutil.ignore_patterns("run", "outbox"))


def test_scaffold_writes_a_script_that_runs_as_it_is(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: s\n")
    for role, stdin in (("source", ""), ("answer", '{"id": "q/1", "fields": {}}'), ("measure", ""), ("render", "")):
        got = author.scaffold(tmp_path, role, f"bin/{role}.py")
        p = subprocess.run(got["command"], shell=True, cwd=tmp_path, input=stdin, capture_output=True, text=True)
        assert p.returncode == 0 and p.stdout.strip(), (role, p.stderr)
    outside = author.scaffold(tmp_path, "act", str(tmp_path.parent / "private-scripts" / "act.py"))
    assert outside["command"].startswith("python3 /")
    with pytest.raises(author.AuthorError):
        author.scaffold(tmp_path, "act", str(tmp_path.parent / "private-scripts" / "act.py"))


@pytest.mark.slow
def test_a_trial_runs_a_copy_and_says_what_moved(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    root = tmp_path / "p"
    root.mkdir()
    (root / "ergostat.yaml").write_text("name: p\n")
    got = author.trial(root, None, 22, {"instance": "q", "template": "respond-to",
                                        "given": {"poll": "5s", "stand-in-rate": 1000}})
    assert got["check"]["ok"], got
    ran = got["ran"]
    assert ran["items"]["q"]["by_state"].get("answered"), got["verdict"]
    assert ran["blocks"]["q-answer"]["moved"].get("q-answered"), ran["blocks"]
    assert (root / "ergostat.yaml").read_text() == "name: p\n", "the project itself is never touched"
    assert not (tmp_path / "home").exists() or not any((tmp_path / "home").iterdir()), "nor its record"


@pytest.mark.slow
def test_steps_lease_each_item_to_a_run_and_a_step_that_always_fails_makes_dead_letters(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.spec import items as its
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    root = tmp_path / "p"
    root.mkdir()
    (root / "ergostat.yaml").write_text("name: p\n")
    got = author.trial(root, None, 25, {"instance": "t", "template": "steps",
                                        "given": {"poll": "5s", "stand-in-rate": 1000, "tries": 2, "pool": 3,
                                                  "steps": ["a", {"name": "b", "run": "echo no >&2; exit 3"}]}})
    assert got["check"]["ok"], got
    ran = got["ran"]
    by = ran["items"]["t"]["by_state"]
    assert by.get("dead") and not by.get("done"), by          # through a, then given up on at b after two tries
    assert ran["blocks"]["t-a"]["moved"].get("t-a-done"), ran["blocks"]["t-a"]
    monkeypatch.setenv("ERGOSTAT_HOME", str(Path(got["scratch"]).parent / "home"))
    p = Project(mdl.load(Path(got["scratch"])))
    dead = [i for i in its.project(p.events, p.model.spec, "t") if i.state == "dead"]
    assert dead[0].fields["failed_at"] == "b" and dead[0].fields["lease"]["back"] == "b"
    assert [h["how"] for h in dead[0].fields["lease"]["history"]][-2:] == ["nack", "nack"]
    assert ran["stocks"]["t-stuck"]["sensors"], "the dead letters are counted"


@pytest.mark.slow
def test_respond_to_answers_leased_items_and_counts_their_age_from_arrival(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.spec import items as its
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    root = tmp_path / "p"
    root.mkdir()
    (root / "ergostat.yaml").write_text("name: p\n")
    flaky = 'echo "$ITEM_FIELDS" | grep -q error || { echo "not this time" >&2; exit 1; }'   # fails once, then answers
    got = author.trial(root, None, 25, {"instance": "q", "template": "respond-to",
                                        "given": {"poll": "5s", "stand-in-rate": 1000, "answer": flaky}})
    assert got["check"]["ok"], got
    monkeypatch.setenv("ERGOSTAT_HOME", str(Path(got["scratch"]).parent / "home"))
    p = Project(mdl.load(Path(got["scratch"])))
    spec = p.model.spec
    every = its.project(p.events, spec, "q")
    answered = [i for i in every if i.state == "answered"]
    assert answered, got["ran"]["items"]
    assert [h["how"] for h in answered[0].fields["lease"]["history"]] == ["nack", "ack"]
    assert answered[0].fields["error"] and answered[0].fields["failed_at"] == "waiting"
    s = next(iter(spec.auxiliaries["q-oldest"].sensors.values()))
    age, _ = its.measure(p.events, spec, s)
    open_ = [i for i in every if i.state != "answered"]
    if open_:                                     # the age is since arrival, not since it was last taken or given back
        import time
        assert age == pytest.approx(max(time.time() - i.first for i in open_) / 3600, abs=0.01)


def test_a_template_made_part_is_never_edited_in_place(tmp_path):
    from ergostat.numbers import yamledit as ye
    spec, _ = read(project(tmp_path, RESPOND))
    with pytest.raises(ye.EditError, match="made by template respond-to"):
        ye.own(spec.goals["questions-on-time"].where, "goal questions-on-time")


def test_the_mcp_server_lists_and_adds(tmp_path):
    from ergostat.mcp import TOOLS, Server
    names = {t["name"] for t in TOOLS}
    assert {"templates", "add_use", "scaffold", "try_use", "where_drawn"} <= names
    (tmp_path / "ergostat.yaml").write_text("name: s\n")
    s = Server(tmp_path)
    listed = json.loads(s.call("templates", {})["content"][0]["text"])
    assert {t["template"] for t in listed["templates"]} >= {"respond-to", "re-ping", "daily-report", "keep-under", "steps",
                                                             "collect", "observed-autoscaler", "alert-rule"}
    from ergostat import helpdocs
    adding = helpdocs.read("adding")                      # what `ergostat help adding` prints
    assert all(f"| `{n}` |" in adding and f"### {n}\n" in adding for n in ("observed-autoscaler", "alert-rule"))
    one = json.loads(s.call("templates", {"name": "keep-under"})["content"][0]["text"])
    assert one["params"]["limit"]["required"] and "Control" in one["reading"]
    got = json.loads(s.call("add_use", {"instance": "disk", "template": "keep-under", "with": {"limit": 80},
                                        "write": True})["content"][0]["text"])
    assert got["ok"] and got["written"] == ["ergostat.yaml"]
    shown = json.loads(s.call("where_drawn", {"system": "disk"})["content"][0]["text"])
    assert shown["pages"]["dynamics"].endswith("/diagram?view=dynamics&system=disk") and "disk-level" in shown["drawn"]
    err = s.call("add_use", {"instance": "x", "template": "nope"})
    assert "no template 'nope'" in err["content"][0]["text"]


def test_where_names_a_fields_field_with_a_dot():
    from ergostat.spec.items import Item, field_at, matches
    it = Item("t/1", "t")
    it.fields = {"lease": {"back": "fix", "holder": None}, "a.b": 1}
    assert field_at(it.fields, "lease.back") == "fix" and field_at(it.fields, "a.b") == 1 and field_at(it.fields, "x.y") is None
    assert matches(it, {"lease.back": "fix"}) and not matches(it, {"lease.back": ["triage", "review"]})
