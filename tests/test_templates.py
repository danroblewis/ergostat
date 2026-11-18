"""Templates (SPEC §2a): a use expands into ordinary parts named for its instance, one system per use, every part
pointing at the use: line; parameters are checked; the owner's own templates are found beside ergostat's; every
built-in template checks and runs on its stand-ins; the authoring tools write, try and show an instance."""

import json
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
    assert k.states == ["triage", "fix", "review", "done", "stuck"]
    assert k.on == {"tickets.stuck": "stuck", "tickets.triage-done": "fix", "tickets.fix-done": "review",
                    "tickets.review-done": "done"}
    assert spec.flows["tickets-arriving"].target == "tickets-triage"
    assert spec.flows["tickets-review-done"].target == "tickets-done"
    assert spec.flows["tickets-fix-stuck"].target == "tickets-stuck"
    assert "./fix.sh" in spec.blocks["tickets-fix"].params["run"] and "--run ''" in spec.blocks["tickets-triage"].params["run"]
    assert spec.blocks["tickets-fix"].goal == "tickets-fix-clear"


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


def test_with_every_default_each_runs_on_stand_ins(tmp_path):
    needs = {"keep-under": {"limit": 10}, "steps": {"steps": ["a", "b"]}}
    body = "name: t\nuses:\n" + "".join(f"  u-{n}:\n    use: {n}\n    with: {json.dumps(needs.get(n, {}))}\n"
                                         for n in sorted(tp.find_all()[0]))
    (tmp_path / "ergostat.yaml").write_text(body)
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    assert not [p for p in ps if p.code == "missing-feedback"], "every goal a template holds is served"


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
                                                             "collect"}
    one = json.loads(s.call("templates", {"name": "keep-under"})["content"][0]["text"])
    assert one["params"]["limit"]["required"] and "Control" in one["reading"]
    got = json.loads(s.call("add_use", {"instance": "disk", "template": "keep-under", "with": {"limit": 80},
                                        "write": True})["content"][0]["text"])
    assert got["ok"] and got["written"] == ["ergostat.yaml"]
    shown = json.loads(s.call("where_drawn", {"system": "disk"})["content"][0]["text"])
    assert shown["pages"]["dynamics"].endswith("/diagram?view=dynamics&system=disk") and "disk-level" in shown["drawn"]
    err = s.call("add_use", {"instance": "x", "template": "nope"})
    assert "no template 'nope'" in err["content"][0]["text"]
