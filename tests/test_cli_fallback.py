"""The command line on the engine's last good model while the YAML is broken (SPEC §9.1): the model kept whole as one
snapshot, read back from that alone, by commands that read; commands that act refuse. Three earlier failures are
tested by name: AI models with prompt files never kept, commands run in a copy, includes mixed from disk."""

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.goodmodel import DIR, MANIFEST, OBJECTS, fallback, keep
from ergostat.spec import files
from ergostat.store import Project

MODEL = """
name: rz
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        values: [new, done]
    events:
      job-end:
        when: type == 'job.end'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
stocks:
  waiting: {unit: jobs, sensor: {projection: job, state: new, every: 1s}}
goals:
  few:
    stock: waiting
    hold: "<= 5"
"""


def _repo(tmp_path, text: str = MODEL) -> Path:
    d = tmp_path / "rz"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    return d


def _kept(d: Path) -> Project:
    p = Project(mdl.load(d))
    assert keep(p) is None                              # as the engine does when it takes a model
    return p


def _break(d: Path) -> None:
    with open(d / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")


def _broken(tmp_path, kept: bool = True) -> Path:
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    p.events.add_many([{"type": "job.made", "item": "job/1"}, {"type": "job.end", "item": "job/1"}], new=True)
    if kept:
        assert keep(p) is None
    _break(d)
    return d


def test_status_item_and_event_read_the_record_with_the_last_good_model_while_the_yaml_is_broken(tmp_path, capsys):
    d = _broken(tmp_path)
    assert main(["-C", str(d), "item", "job/1", "--json"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["state"] == "done"
    assert err.count("\n") == 1 and "using the last good model" in err and "ergostat.yaml:" in err and "YAML" in err
    assert main(["-C", str(d), "event", "--json"]) == 0
    assert {e["type"] for e in json.loads(capsys.readouterr().out)} >= {"job.made", "job.end"}
    assert main(["-C", str(d), "status"]) == 0
    out, err = capsys.readouterr()
    assert "rz" in out and "the edited model has errors" in out and "using the last good model" in err
    assert main(["-C", str(d), "stock", "waiting"]) == 0 and "last good" in capsys.readouterr().err


def test_acting_commands_refuse_naming_the_yaml_error(tmp_path, capsys):
    d = _broken(tmp_path)
    for argv, says in ((["event", "--add", "job.made", "--item", "job/2"], "event --add"),
                       (["block", "x", "--now"], "block --now"), (["accept", "p1"], "accept"),
                       (["lease", "job/1", "--nack", "busy"], "lease --nack")):
        with pytest.raises(SystemExit) as e:
            main(["-C", str(d), *argv])
        err = capsys.readouterr().err
        assert e.value.code == 2 and "not valid YAML" in err and "ergostat.yaml:" in err, argv
        assert f"ergostat {says} acts, so it never runs on the last good model" in err and "using" not in err, argv
    p = fallback(d, mdl.ModelError("x"))
    assert [e["item"] for e in p.events.query(n=None, type="job.made")] == ["job/1"]   # job/2 never recorded


def test_check_still_reports_the_edited_models_errors(tmp_path, capsys):
    d = _broken(tmp_path)
    assert main(["-C", str(d), "check"]) != 0
    out, err = capsys.readouterr()
    assert "last good" not in err and "not valid YAML" in (out + err)


def test_without_a_kept_model_a_broken_yaml_is_refused_as_before(tmp_path, capsys):
    d = _broken(tmp_path, kept=False)
    with pytest.raises(SystemExit) as e:
        main(["-C", str(d), "item", "--json"])
    err = capsys.readouterr().err
    assert e.value.code == 2 and "last good" not in err and "not valid YAML" in err


AI = MODEL + """
blocks:
  triage:
    type: ai
    prompt: prompts/triage.md
    in: {w: stock.waiting}
    every: 1h
"""


def test_an_ai_model_with_a_prompt_file_is_kept_and_read_back_after_the_prompt_is_gone(tmp_path, capsys):
    d = _repo(tmp_path, AI)
    (d / "prompts").mkdir()
    (d / "prompts" / "triage.md").write_text("Triage what came in.")
    p = _kept(d)
    kept = json.loads((p.dir / DIR / MANIFEST).read_text())["files"]
    h = kept[str(d.resolve() / "prompts" / "triage.md")]
    assert (p.dir / DIR / OBJECTS / h).read_text() == "Triage what came in."    # its bytes, by their hash
    shutil.rmtree(d / "prompts")                        # (live, the model no longer compiles: prompt-missing)
    _break(d)
    assert main(["-C", str(d), "block", "--json"]) == 0
    assert "triage" in capsys.readouterr().out


def test_the_fallback_is_the_repositorys_and_never_runs_anything(tmp_path, capsys, monkeypatch):
    d = _broken(tmp_path)
    p = fallback(d, mdl.ModelError("x"))
    assert p.repo == d.resolve() and p.model.path == d.resolve() / "ergostat.yaml"   # never a copy of the files
    assert not list((p.dir / DIR).rglob("*.yaml"))       # the store holds objects by hash, nothing to run in
    kept = json.loads((p.dir / DIR / MANIFEST).read_text())
    with files.replay(kept, lambda h: (p.dir / DIR / OBJECTS / h).read_bytes()):
        with pytest.raises(files.NotKept, match="without running anything"):
            subprocess.run(["true"], check=False)
        with pytest.raises(files.NotKept, match="read live"):
            (d / "ergostat.yaml").read_text()
    with pytest.raises(SystemExit):                     # and a command that would run something refuses
        main(["-C", str(d), "agent", "x", "--now"])
    assert "acts" in capsys.readouterr().err


GLOBBED = """
name: rz
include: [parts/*.yaml, plain.yaml]
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        values: [new, done]
"""


def test_includes_are_settled_from_the_snapshot_never_the_disk(tmp_path):
    d = _repo(tmp_path, GLOBBED)
    (d / "parts").mkdir()
    (d / "parts" / "a.yaml").write_text("stocks:\n  a: {unit: jobs, sensor: {projection: job, state: new, every: 1s}}\n")
    (d / "parts" / "b.yaml").write_text("stocks:\n  b: {unit: jobs, sensor: {projection: job, state: done, every: 1s}}\n")
    (d / "plain.yaml").write_text("goals:\n  few: {stock: a, hold: '<= 5'}\n")
    was = set(_kept(d).model.stocks)
    (d / "parts" / "c.yaml").write_text("stocks:\n  c: {unit: jobs}\n")    # a file the glob now matches
    (d / "parts" / "b.yaml").unlink()                    # a kept file deleted
    (d / "plain.yaml").unlink()                          # a plain include deleted
    _break(d)
    got = fallback(d, mdl.ModelError("x"))
    assert got is not None and set(got.model.stocks) == was == {"a", "b"} and "few" in got.model.spec.goals


def test_a_read_the_snapshot_does_not_hold_fails_the_fallback_never_reads_the_disk(tmp_path, capsys):
    d = _broken(tmp_path)
    p = fallback(d, mdl.ModelError("x"))
    kept = json.loads((p.dir / DIR / MANIFEST).read_text())
    with files.replay(kept, lambda h: (p.dir / DIR / OBJECTS / h).read_bytes()):
        with pytest.raises(files.NotKept):
            files.read_text(d / "other.yaml")
        with pytest.raises(files.NotKept):
            files.glob(d, "*.yaml")
    other = dict(kept, files={k: v for k, v in kept["files"].items() if not k.endswith("ergostat.yaml")})
    (p.dir / DIR / MANIFEST).write_text(json.dumps(other))   # its main file not held: refused, not read from disk
    capsys.readouterr()
    assert fallback(d, mdl.ModelError("x")) is None
    assert "could not be read back" in capsys.readouterr().err


def test_a_kept_file_altered_in_the_store_is_refused(tmp_path, capsys):
    d = _broken(tmp_path)
    p = fallback(d, mdl.ModelError("x"))
    for f in (p.dir / DIR / OBJECTS).iterdir():
        f.write_text(f.read_text() + "\n# altered\n")
    capsys.readouterr()
    assert fallback(d, mdl.ModelError("x")) is None and "altered" in capsys.readouterr().err


def test_every_example_is_kept_and_read_back_from_its_snapshot_alone(tmp_path):
    examples = sorted(Path(__file__).resolve().parent.parent.glob("examples/*/ergostat.yaml"))
    assert len(examples) >= 20
    for main_ in examples:
        d = tmp_path / main_.parent.name
        shutil.copytree(main_.parent, d, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
        p = Project(mdl.load(d))
        assert keep(p) is None, main_.parent.name
        for f in list(d.rglob("*")):                     # every file gone: what loads is the snapshot alone
            if f.is_file():
                f.unlink()
        (d / "ergostat.yaml").write_text("broken: [\n")
        got = fallback(d, mdl.ModelError("x"))
        assert got is not None and got.repo == d.resolve(), main_.parent.name
        assert set(got.model.stocks) == set(p.model.stocks) and set(got.model.spec.blocks) == set(p.model.spec.blocks)


@pytest.mark.slow
def test_the_engine_keeps_the_model_it_takes(tmp_path):
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    good = p.dir / DIR / MANIFEST
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        def until(f, t=60):
            end = time.monotonic() + t
            while time.monotonic() < end:
                if f():
                    return True
                time.sleep(0.2)
            return False
        assert until(good.is_file)
        first = json.loads(good.read_text())["files"]
        (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("<= 5", "<= 7"))
        assert until(lambda: json.loads(good.read_text())["files"] != first)   # the change it took, kept
        _break(d)
        time.sleep(3)                                    # (a change it refuses is never kept)
        h = json.loads(good.read_text())["files"][str(d.resolve() / "ergostat.yaml")]
        assert "<= 7" in (p.dir / DIR / OBJECTS / h).read_text()
    finally:
        subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--stop"], capture_output=True, timeout=60)
        if proc.poll() is None:
            proc.kill()


def test_every_flag_of_a_read_topic_is_called_acting_or_read_only():
    from ergostat.cli import build
    from ergostat.goodmodel import ACTS, READ_FLAGS, READ_WHAT, READS
    common = {"help", "C", "json", "system", "since", "at", "name", "version", "watch", "exit_code", "topic", "fn"}
    sub = next(a for a in build()._actions if a.dest == "topic")
    told = set(ACTS) | set(READ_FLAGS) | common
    untold = {f"{t} --{a.dest}" for t in READS if t in sub.choices for a in sub.choices[t]._actions if a.dest not in told}
    assert not untold, f"say whether each acts (goodmodel.ACTS) or only reads (goodmodel.READ_FLAGS): {sorted(untold)}"
    assert set(READ_WHAT) <= set(sub.choices) and not set(READ_WHAT) & READS      # (a topic read whole is in READS)
    untold = {f"{t} --{a.dest}" for t in READ_WHAT for a in sub.choices[t]._actions if a.dest not in told | {"what"}}
    assert not untold, f"say whether each acts (goodmodel.ACTS) or only reads (goodmodel.READ_FLAGS): {sorted(untold)}"
    for t, whats in READ_WHAT.items():                    # each subcommand named is one the topic has
        what = next(a for a in sub.choices[t]._actions if a.dest == "what")
        assert set(whats) <= set(what.choices), (t, whats)


def test_remote_proposals_reads_on_the_last_good_model_and_remote_token_does_not(tmp_path, capsys):
    from tests.test_remote_proposals import _made, _texts
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    assert keep(p) is None
    d = p.model.path.parent
    _break(d)
    capsys.readouterr()
    assert main(["-C", str(d), "remote", "proposals", "--json"]) == 0
    got = capsys.readouterr()
    assert [x["id"] for x in json.loads(got.out)] == [pid] and "using the last good model" in got.err
    for argv, says in ((["remote", "token", "x"], "remote"), (["remote", "refresh"], "remote"),
                       (["remote", "proposals", "--revoke"], "remote --revoke"), (["remote"], "remote")):
        with pytest.raises(SystemExit) as e:
            main(["-C", str(d), *argv])
        err = capsys.readouterr().err
        assert e.value.code == 2 and f"ergostat {says} acts, so it never runs on the last good model" in err, argv


def test_the_fallbacks_record_refuses_every_write_whatever_the_flags(tmp_path, capsys, monkeypatch):
    from ergostat import goodmodel
    d = _broken(tmp_path)
    p = fallback(d, mdl.ModelError("x"))
    for write in (lambda: p.events.add("job.made", item="job/3"), lambda: p.events.add_many([{"type": "x"}]),
                  lambda: p.measurements.add("s", 1.0)):
        with pytest.raises(goodmodel.ReadOnlyRecord):
            write()
    monkeypatch.setattr(goodmodel, "ACTS", tuple(a for a in goodmodel.ACTS if a not in ("requests", "made", "invest", "add")))
    capsys.readouterr()
    assert main(["-C", str(d), "event", "--add", "job.made", "--item", "job/3"]) == 2    # a flag the list missed
    assert "would write to the record" in capsys.readouterr().err
    from ergostat.inbox import interventions
    monkeypatch.setattr(interventions, "requests", lambda p, spec, now=None: p.events.add("model-request.opened"))
    assert main(["-C", str(d), "inbox", "--requests", "--made"]) == 2
    assert "would write to the record" in capsys.readouterr().err
    assert [e["item"] for e in Project(p.model, p.dir, note=False).events.query(n=None, type="job.made")] == ["job/1"]


def test_the_read_topics_run_on_the_fallback_without_writing(tmp_path, capsys):
    from ergostat.goodmodel import READS
    d = _broken(tmp_path)
    for t in sorted(x for x in READS if x and x not in ("status",)):
        argv = ["-C", str(d), t]
        try:
            rc = main(argv)
        except SystemExit as e:
            rc = e.code
        assert "would write" not in capsys.readouterr().err and rc in (0, 1), (t, rc)


def test_old_snapshot_objects_are_kept_one_generation_and_stale_tmp_files_cleared(tmp_path):
    d = _repo(tmp_path)
    p = _kept(d)
    objects = p.dir / DIR / OBJECTS
    first = set(os.listdir(objects))
    old = objects / "abc.123.tmp"
    old.write_text("x")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    for limit in ("<= 6", "<= 7"):
        (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("<= 5", limit))
        assert keep(Project(mdl.load(d))) is None
        if limit == "<= 6":
            assert first <= set(os.listdir(objects)), "a command reading the snapshot before keeps its objects"
    now = set(json.loads((p.dir / DIR / MANIFEST).read_text())["files"].values())
    assert (first - now) and not (first - now) & set(os.listdir(objects)), "two generations on, they go"
    assert not old.exists()


def test_a_missing_file_names_its_path_and_the_library_setting(tmp_path, capsys, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    d = _repo(tmp_path, MODEL + "uses:\n  modelling: {use: modelling}\n")
    _kept(d)
    _break(d)
    monkeypatch.setenv("ERGOSTAT_LIBRARY", str(lib))     # folders the snapshot never looked in
    assert fallback(d, mdl.ModelError("x")) is None
    err = capsys.readouterr().err
    assert str(lib) in err and "not in the last good model's snapshot" in err and "ERGOSTAT_LIBRARY" in err


@pytest.mark.slow
def test_an_engine_running_takes_event_add_from_a_run_while_the_yaml_is_broken(tmp_path):
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.monotonic() + 60
        while not (p.dir / DIR / MANIFEST).is_file() and time.monotonic() < end:
            time.sleep(0.2)
        _break(d)
        got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "event", "--add", "job.made", "--item",
                              "job/9"], capture_output=True, text=True, timeout=60)
        assert got.returncode == 0, got.stderr
        assert [e["item"] for e in p.events.query(n=None, type="job.made")] == ["job/9"]
    finally:
        subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--stop"], capture_output=True, timeout=60)
        if proc.poll() is None:
            proc.kill()
