"""This machine's own settings (SPEC §2): ``ergostat.local.yaml`` beside the main file, untracked, read after it and
over it, and allowed only the per-machine sections (``web:``, ``intake:``'s bind and allow)."""

import json
import textwrap
import urllib.error
import urllib.request

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.spec import read
from ergostat.store import Project
from tests.ports import free_port

NAME = "dev.example.org"
MODEL = """\
name: here
stocks:
  queue: {}
intake:
  hooks:
    jira: {event: ticket.found, item: "ticket/{issue.key}"}
"""


def folder(tmp_path, local: str | None):
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    if local is not None:
        (tmp_path / "ergostat.local.yaml").write_text(textwrap.dedent(local))
    return tmp_path


def status(url: str, host: str) -> int:
    req = urllib.request.Request(url + "/api/status", headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_web_from_the_local_file_is_used(tmp_path, capsys):
    from ergostat.web import serve
    d = folder(tmp_path, f"""\
        web: {{names: [{NAME}], open: read}}
        intake: {{bind: 0.0.0.0}}
        """)
    spec, problems = read(d / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], problems
    assert spec.web.names == [NAME] and spec.web.open
    assert spec.intake.bind == "0.0.0.0" and "jira" in spec.intake.hooks         # the model's hooks kept, bind over them
    assert d / "ergostat.local.yaml" not in [*spec.files]                         # never a model file (nothing edits it)
    server, url = serve(Project(mdl.load(d)), free_port())
    try:
        assert status(url, NAME) == 200                                           # the public name, read
    finally:
        server.shutdown()
        server.server_close()
    assert main(["-C", str(d), "check"]) == 0
    out = capsys.readouterr().out
    assert "web: from ergostat.local.yaml:1" in out and "intake: from ergostat.local.yaml:2" in out
    main(["-C", str(d), "check", "--json"])
    assert json.loads(capsys.readouterr().out)["local"] == {"web": "ergostat.local.yaml:1",
                                                             "intake": "ergostat.local.yaml:2"}


def test_a_model_key_in_the_local_file_is_an_error(tmp_path, capsys):
    d = folder(tmp_path, """\
        web: {names: [dev.example.org], open: read}
        stocks:
          backlog: {}
        intake:
          hooks: {}
        """)
    _, problems = read(d / "ergostat.yaml")
    errors = {(str(p.where), p.code) for p in problems if p.level == "error"}
    assert errors == {("ergostat.local.yaml:2", "not-per-machine"), ("ergostat.local.yaml:4", "not-per-machine")}
    assert main(["-C", str(d), "check"]) == 1
    out = capsys.readouterr().out
    assert "ergostat.local.yaml:2: 'stocks' is not a per-machine setting" in out
    (d / "ergostat.local.yaml").write_text("- web\n")
    _, problems = read(d / "ergostat.yaml")
    assert [(str(p.where), p.code) for p in problems if p.level == "error"] == [("ergostat.local.yaml:1", "not-a-map")]


def test_the_local_file_is_optional(tmp_path, capsys):
    d = folder(tmp_path, None)
    spec, problems = read(d / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"] and spec.local == {}
    assert spec.web.names == [] and spec.intake.bind == "127.0.0.1"
    assert main(["-C", str(d), "check"]) == 0 and "this machine's own" not in capsys.readouterr().out
    m = mdl.load(d)
    before = mdl.stamp(m)
    (d / "ergostat.local.yaml").write_text("web: {names: [dev.example.org], open: read}\n")
    assert mdl.stamp(m) != before                                                 # made later: the model is read again
