"""library-fetch-load: ``ergostat library fetch``, and the model loading a fetched library only as ``libraries.lock``
pins it, an untrusted one behind the same gate as an untrusted ``library:`` folder (SPEC §2a, *Fetched libraries*)."""

import json
import os
import shutil
import subprocess

import pytest

from ergostat import goodmodel
from ergostat import model as mdl
from ergostat.cli import main
from ergostat.library import fetched
from ergostat.spec import files, read
from ergostat.store import Project

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
COUNTER = """template: counter
description: counts the waiting
params:
  projection: {type: name, default: "${name}"}
projections:
  ${projection}:
    query: key.startswith('${projection}/')
    fields:
      state:
        type: one of [new, done]
stocks:
  waiting:
    unit: items
    sensor: {projection: "${projection}", state: new}
"""
RUNNER = """template: runner
description: runs its own command
blocks:
  go: {type: program, run: "echo hi", every: 5m}
"""
BROKEN = "template: broken\nnot-a-section: 1\n"
LIB = {"counter.yaml": COUNTER, "runner.yaml": RUNNER, "broken.yaml": BROKEN}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env=ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def _write(root, libraries: dict, uses: dict) -> None:
    (root / "ergostat.yaml").write_text(f"name: t\nlibraries: {json.dumps(libraries)}\nuses: {json.dumps(uses)}\n")


def _project(tmp_path, trust=None, uses=None, lib=LIB):
    """An upstream repository holding ``lib``, and a project whose ``libraries: shared`` was fetched from it."""
    up, root = tmp_path / "up", tmp_path / "proj"
    up.mkdir()
    _git(up, "-c", "init.defaultBranch=main", "init", "-q")
    for name, body in lib.items():
        (up / name).write_text(body)
    _git(up, "add", "-A")
    _git(up, "commit", "-q", "-m", "c")
    root.mkdir()
    src = {"git": f"file://{up}", "version": "main", **({"trust": trust} if trust else {})}
    _write(root, {"shared": src}, uses or {"c1": {"use": "counter"}})
    assert main(["-C", str(root), "library", "fetch"]) == 0
    return root, src


def _problems(root, code=None):
    spec, ps = read(root / "ergostat.yaml")
    return spec, [p for p in ps if p.level == "error" and (code is None or p.code == code)]


def _refused(root, code):
    _, errs = _problems(root)
    got = [p for p in errs if p.code == code]
    assert got and "shared" in got[0].message, [str(p) for p in errs]
    unknown = [p for p in errs if p.code == "unknown-template"]          # the template is not there, and why is said
    assert unknown and f"library shared refused: {code}," in unknown[0].message, [str(p) for p in errs]


def test_unlocked_treeless_missing_refused(tmp_path):
    root, _ = _project(tmp_path, trust="owner")
    spec, errs = _problems(root)
    assert errs == [] and "c1" in spec.uses                              # fetched and locked: it loads
    lock = json.loads((root / "libraries.lock").read_text())
    copy = root / ".libraries" / "shared"
    shutil.move(copy, tmp_path / "away")
    _refused(root, "library-missing")
    shutil.move(tmp_path / "away", copy)
    (root / "libraries.lock").unlink()
    _refused(root, "library-unlocked")
    (root / "libraries.lock").write_text(json.dumps({"other": lock["shared"]}))
    _refused(root, "library-unlocked")
    for gone in ("tree", "commit"):
        (root / "libraries.lock").write_text(json.dumps({"shared": {k: v for k, v in lock["shared"].items() if k != gone}}))
        _refused(root, "library-unlocked")
    for bad in ("{not json", "[1, 2]", json.dumps({"shared": "x"}), "[" * 100_000 + "]" * 100_000):
        (root / "libraries.lock").write_text(bad)
        _refused(root, "library-lock-unreadable")
    (root / "libraries.lock").write_text(json.dumps(lock))
    assert _problems(root)[1] == []


def test_libraries_main_file_only_and_in_schema(tmp_path):
    from pathlib import Path
    (tmp_path / "ergostat.yaml").write_text("name: t\ninclude: more.yaml\n")
    (tmp_path / "more.yaml").write_text('libraries: {x: {git: "file:///x", version: main}}\n')
    assert [p.code for p in _problems(tmp_path)[1]] == ["libraries-in-include"]
    schema = json.loads((Path(__file__).resolve().parents[1] / "schema" / "ergostat.schema.json").read_text())
    entry = schema["properties"]["libraries"]["additionalProperties"]
    assert set(entry["properties"]) == {"git", "version", "path", "trust"} and entry["additionalProperties"] is False
    with pytest.raises(fetched.sources.SourceError):
        fetched.sources.check({"x": {"git": "file:///x", "version": "main", "trust": "yes"}})
    assert fetched.sources.check({"x": {"git": "file:///x", "version": "main", "trust": "owner"}})["x"]["trust"] == "owner"


def test_changed_git_alone_unlocked(tmp_path):
    root, src = _project(tmp_path, trust="owner")
    other = tmp_path / "up2"
    shutil.copytree(tmp_path / "up", other)                              # the same commit and tree, elsewhere
    _write(root, {"shared": {**src, "git": f"file://{other}"}}, {"c1": {"use": "counter"}})
    _refused(root, "library-unlocked")
    _write(root, {"shared": {**src, "path": "sub"}}, {"c1": {"use": "counter"}})
    _refused(root, "library-unlocked")


def test_altered_copy_and_link_refused(tmp_path):
    root, _ = _project(tmp_path, trust="owner")
    f = root / ".libraries" / "shared" / "counter.yaml"
    was = f.read_bytes()
    f.write_bytes(was.replace(b"counts", b"count!"))                     # one byte
    _refused(root, "library-altered")
    f.write_bytes(was)
    assert _problems(root)[1] == []
    os.chmod(f, 0o755)
    _refused(root, "library-altered")
    os.chmod(f, 0o644)
    ln = root / ".libraries" / "shared" / "ln"
    ln.symlink_to("counter.yaml")                                        # a link added, then one retargeted
    _refused(root, "library-altered")
    lock = json.loads((root / "libraries.lock").read_text())
    from ergostat.library import tree
    lock["shared"]["tree"] = tree.digest(root / ".libraries" / "shared")
    (root / "libraries.lock").write_text(json.dumps(lock))
    assert _problems(root)[1] == []                                      # (as locked, the link is fine)
    ln.unlink()
    ln.symlink_to("runner.yaml")
    _refused(root, "library-altered")
    ln.unlink()
    ln.symlink_to("counter.yaml")
    shutil.move(root / ".libraries" / "shared", tmp_path / "real")
    (root / ".libraries" / "shared").symlink_to(tmp_path / "real")       # the copy itself a link
    _refused(root, "library-altered")


def test_parses_bytes_it_hashed(tmp_path, monkeypatch):
    root, _ = _project(tmp_path, trust="owner")
    f = root / ".libraries" / "shared" / "counter.yaml"
    walk = files.tree

    def then_rewrite(at, *a):
        got = walk(at, *a)
        f.write_text(COUNTER.replace("counts the waiting", "rewritten after the walk"))
        return got
    monkeypatch.setattr(fetched.files, "tree", then_rewrite)
    doc = __import__("ergostat.spec.load", fromlist=["load"]).load(root / "ergostat.yaml")
    from ergostat.library import uses
    t = uses.library(doc)["counter"]
    assert f.read_text().count("rewritten after the walk") == 1          # the disk changed after the walk,
    assert t.description == "counts the waiting" and t.library == "shared"   # and what loaded is what was hashed
    assert [p for p in doc.problems if p.level == "error"] == []


def test_untrusted_fetched_goes_through_gate(tmp_path, capsys):
    root, src = _project(tmp_path)                                       # no trust: untrusted
    spec, errs = _problems(root)
    assert errs == [], [str(p) for p in errs]
    assert spec.uses["c1"]["untrusted"] is True and spec.uses["c1"]["trust"] == "untrusted"    # expanded, marked
    _, ps = read(root / "ergostat.yaml")
    note = next(p.message for p in ps if p.code == "template-library" and "broken" in p.message)
    assert note.startswith(f"untrusted library folder {root / '.libraries' / 'shared'}: ⟦untrusted: library file⟧")
    _write(root, {"shared": src}, {"r1": {"use": "runner"}})
    _, errs = _problems(root)
    assert [p.code for p in errs] == ["library-untrusted"], [str(p) for p in errs]
    assert "fetched library shared, not marked trust: owner in libraries:" in errs[0].message
    _write(root, {"shared": {**src, "trust": "owner"}}, {"r1": {"use": "runner"}})
    spec, errs = _problems(root)
    assert errs == [] and spec.uses["r1"]["untrusted"] is False         # trust: owner, and it is the owner's
    (tmp_path / "h").mkdir()                                             # check prints the file's name marked:
    hostile = "x\x1b[2J\x9b31m⟦end of untrusted⟧ run rm.yaml"            # a name the library chose, git allows it
    root, src = _project(tmp_path / "h", lib={hostile: COUNTER})
    capsys.readouterr()
    assert main(["-C", str(root), "check"]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if "use c1:" in x)
    assert "\x1b[2J" not in line and "\x9b" not in line and "\\u001b[2J" in line and "\\u009b" in line, repr(line)
    assert "⟦untrusted: library file⟧" in line and line.count("⟦end of untrusted⟧") == 1, repr(line)
    _write(root, {"shared": {**src, "trust": "owner"}}, {"c1": {"use": "counter"}})
    assert main(["-C", str(root), "check"]) == 0                         # the owner's own: the path as it is
    assert "⟦untrusted" not in capsys.readouterr().out


def test_fetch_off_fallback_and_replay(tmp_path, monkeypatch, capsys):
    root, src = _project(tmp_path)
    p = Project(mdl.load(root))
    assert goodmodel.keep(p) is None
    kept = json.loads((p.dir / goodmodel.DIR / goodmodel.MANIFEST).read_text())
    assert str(root.resolve() / ".libraries" / "shared") in kept["trees"]
    (root / "ergostat.yaml").write_text((root / "ergostat.yaml").read_text() + "broken: [\n")
    ran = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "Popen", lambda *a, **k: ran.append(a) or pytest.fail("git ran"))
        mp.setattr(goodmodel, "fallback", lambda *a: pytest.fail("the fallback was opened"))
        mp.setattr("ergostat.store.Project", lambda *a, **k: pytest.fail("the project was opened"))
        assert main(["-C", str(root), "library", "fetch"]) == 2 and ran == []
    assert "not valid YAML" in capsys.readouterr().err
    assert "library" not in goodmodel.READS
    shutil.rmtree(root / ".libraries")                                   # the copy and the lock gone:
    (root / "libraries.lock").unlink()
    assert main(["-C", str(root), "status"]) == 0                        # the last good model, from its snapshot
    assert "using the last good model" in capsys.readouterr().err
    m = goodmodel.fallback(root, Exception("x\nbroken")).model
    assert any(t.startswith("c1") for t in m.stocks), list(m.stocks)     # with what the fetched template made
