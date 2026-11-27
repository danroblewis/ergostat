"""The factory's sessions kept (dev/bin/sessions.py): Claude Code's own session file, from a folder of its own mounted
as its projects folder, copied (the token scrubbed, capped) into run/sessions/ and named by a `session` item related
to its gap, whose lines ergostat's transcript reader records as claude.* events; and status.py's terminal view."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ergostat import model as mdl
from ergostat import transcripts as tr
from ergostat.spec import items as its
from ergostat.store import Project
from tests.test_factory import BIN, ROOT, Factory, module, ready

FIXTURE = ROOT / "tests" / "fixtures" / "factory-session.jsonl"
TOKEN = "sk-ant-oat01-FIXTURE-TOKEN-xyz"


@pytest.fixture
def mods(tmp_path, monkeypatch):
    """fac and sessions as the programs import them, in a model's folder of tmp_path."""
    monkeypatch.chdir(tmp_path)
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    sessions = module("sessions")
    monkeypatch.setitem(sys.modules, "sessions", sessions)
    monkeypatch.setenv("ERGOSTAT_ITEM", "gap/alpha-thing")
    cfg = {"paths": {"run": str(tmp_path / "run"), "live": str(tmp_path / "live")},
           "ai": {"mode": "container", "implementor_model": "opus", "implementor_session_usd": 5.0}}
    return fac, sessions, cfg


def said(capsys) -> list[dict]:
    return [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]


def test_a_session_file_is_copied_scrubbed_and_recorded_as_a_session_item(mods, capsys, monkeypatch):
    fac, sessions, cfg = mods
    fake = type(sys)("agents")
    fake.token = lambda cfg: TOKEN
    got = {}

    def run(cfg, role, brief, work, keep=None):         # as agents.session: Claude Code writes its file, then answers
        got["keep"] = keep
        keep.copy.tok = TOKEN
        keep.copy.src.write_bytes(FIXTURE.read_bytes())
        return {"type": "result", "subtype": "success", "is_error": False, "result": "Done", "total_cost_usd": 0.42,
                "num_turns": 3}
    fake.session = run
    monkeypatch.setitem(sys.modules, "agents", fake)
    out = fac.session(cfg, "implementor", "brief", Path.cwd())
    assert out["total_cost_usd"] == 0.42 and out["result"] == "Done"           # the result and cost as before
    keep = got["keep"]
    assert keep.id == "session/alpha-thing-implementor-1" and keep.dest.name == "alpha-thing-implementor-1.jsonl"
    assert keep.raw.parent == Path(cfg["paths"]["live"]) / "sessions"           # Claude Code's folder: outside run/
    text = keep.dest.read_text()
    assert TOKEN not in text and "[token]" in text and len(text.splitlines()) == 6
    lines = said(capsys)
    start = next(x for x in lines if x.get("event") == "session.started")
    assert start["item"] == keep.id and start["data"]["gap"] == "gap/alpha-thing" and start["data"]["round"] == 1
    assert start["data"]["transcript"] == "file:run/sessions/alpha-thing-implementor-1.jsonl"
    end = next(x for x in lines if x.get("event") == "session.ended")["data"]
    assert end["cost"] == 0.42 and end["turns"] == 3 and end["tools_used"] == {"Bash": 1, "Edit": 1}
    assert not end["truncated"] and end["lines"] == 6
    assert any(x.get("type") == "result" and x.get("total_cost_usd") == 0.42 for x in lines)   # the run still charged
    assert not any(TOKEN in json.dumps(x) for x in lines)

    fac.session(cfg, "implementor", "brief", Path.cwd())                        # the next one: its own number
    assert got["keep"].id == "session/alpha-thing-implementor-2"

    def crash(*a, keep=None, **k):
        raise RuntimeError("the implementor session ran past 10s and was killed")
    fake.session = crash
    with pytest.raises(RuntimeError):
        fac.session(cfg, "implementor", "brief", Path.cwd())
    bad = [x for x in said(capsys) if x.get("event") == "session.errored"]
    assert bad and "ran past" in bad[0]["data"]["error"] and bad[0]["data"]["cost"] is None


def test_the_copy_is_capped_and_asserts_the_token_gone(tmp_path, mods):
    _, sessions, _ = mods
    src, dest = tmp_path / "src.jsonl", tmp_path / "dest.jsonl"
    src.write_text("".join(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "x" * 1000}]}}) + "\n" for _ in range(50)) + '{"type": "user", "half')
    c = sessions.Copy(src, dest, cap=10_000)
    c.step()
    lines = dest.read_text().splitlines()
    assert dest.stat().st_size <= 10_000 + 200 and json.loads(lines[-1])["subtype"] == "truncated"
    assert c.cut and c.turns == 50                                               # counted on, past the cap
    assert c.step() == 0 and c.offset < src.stat().st_size                      # a line half written: not yet
    c2 = sessions.Copy(src, tmp_path / "d2.jsonl")
    c2.tok = "x" * 1000                                                          # scrubbed before it is written
    c2.step()
    assert "x" * 1000 not in (tmp_path / "d2.jsonl").read_text()
    c3 = sessions.Copy(src, tmp_path / "d3.jsonl")
    c3.tok = "x" * 1000
    sessions.scrub, was = (lambda text, tok: text), sessions.scrub              # a scrub that missed it: refused
    try:
        with pytest.raises(AssertionError, match="token"):
            c3.step()
    finally:
        sessions.scrub = was


def model_with_sessions(tmp_path: Path) -> Project:
    """A project with the root model's session kind and the kinds it relates to."""
    root = yaml.safe_load((ROOT / "ergostat.yaml").read_text())
    kinds = {k: root["projections"][k] for k in ("session", "gap", "research", "review", "situation", "milestone")}
    for k in kinds.values():
        k.pop("join", None)
        k["on"] = k.pop(True)                                                   # (YAML 1.1 reads `on:` as true)
    (tmp_path / "ergostat.yaml").write_text(yaml.safe_dump({"projections": kinds}))
    return Project(mdl.load(tmp_path))


def test_a_kept_session_folds_into_its_conversation_by_cores_reader(tmp_path):
    p = model_with_sessions(tmp_path)
    (tmp_path / "run" / "sessions").mkdir(parents=True)
    (tmp_path / "run" / "sessions" / "alpha-thing-implementor-1.jsonl").write_bytes(FIXTURE.read_bytes())
    sid = "session/alpha-thing-implementor-1"
    p.events.add("gap.found", item="gap/alpha-thing", data={"title": "Alpha thing"})
    p.events.add("session.started", item=sid, source="implementor",
                 data={"role": "implementor", "round": 1, "gap": "gap/alpha-thing",
                       "transcript": "file:run/sessions/alpha-thing-implementor-1.jsonl"})
    assert tr.Ingester(p, p.model.spec).once() == 6
    p.events.add("session.ended", item=sid, data={"cost": 0.42, "turns": 3})
    d = its.detail(p.events, p.model.spec, sid)
    f = d["fields"]
    assert d["state"] == "done" and f["cost"] == 0.42
    assert [m["text"] for m in f["messages"] if m["role"] == "assistant"] == ["I'll look at the code first.",
                                                                            "Done: app.py says world."]
    assert [c["name"] for c in f["tool_calls"]] == ["Bash", "Edit"] and f["tokens_out"] == 60
    gap = its.detail(p.events, p.model.spec, "gap/alpha-thing")
    assert [sid] in gap["relations"]["in"].values(), "the gap's page links its sessions"
    assert d["relations"]["out"]["gap"] == ["gap/alpha-thing"]


def test_the_stand_in_keeps_each_sessions_conversation_on_the_gap(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    said, lines = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    assert [x["event"] for x in lines if x.get("event")] == ["gap.started", "session.started", "session.ended", "gap.built"]
    s = f.item("session/alpha-thing-implementor-1")
    assert s["state"] == "done" and s["fields"]["gap"] == ["gap/alpha-thing"] and s["fields"]["role"] == "implementor"
    path = f.model / s["fields"]["transcript"][5:]
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert rows[0]["type"] == "user" and "alpha-thing" in rows[0]["message"]["content"]    # the brief, first
    f.run("review.py", gid)
    assert f.item("session/alpha-thing-reviewer-1")["state"] == "done"

    def status(*args):
        r = subprocess.run([sys.executable, str(BIN / "status.py"), "session", *args], cwd=f.model, env=f.env,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout
    rc, out = status("gap/alpha-thing", "implementor", "1")
    assert rc == 0 and "[prompt]" in out and "  -> Read: /work/README.md" in out and "  <- the stand-in read it" in out
    assert "[claude] wrote standin/" in out
    rc, out = status("alpha-thing")
    assert rc == 0 and "alpha-thing-implementor-1" in out and "== alpha-thing-reviewer-1" in out   # listed; the latest
    assert "[claude] The stand-in read the diff" in out
    assert status("alpha-thing", "planner")[0] == 1


def test_the_container_mounts_only_the_sessions_own_folder(tmp_path, mods):
    fac, sessions, cfg = mods
    agents = module("agents")
    keep = sessions.Session(cfg, "reviewer", None)
    args = agents.run_args({**cfg, "ai": {"reviewer_model": "opus", "reviewer_session_usd": 1}}, "reviewer",
                           tmp_path / "work", "n", keep)
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    assert mounts == [f"{tmp_path / 'work'}:/work:ro", f"{keep.raw}:/home/dev/.claude/projects"]
    hosts = [m.split(":", 1)[0] for m in mounts]                                  # the host side of each mount
    assert not any(h == str(Path.home()) or h.startswith(str(Path.home() / ".claude")) for h in hosts) and "run" not in keep.raw.parts
    assert args[args.index("--session-id") + 1] == keep.sid and args[args.index("--output-format") + 1] == "json"
    assert keep.copy.src == keep.raw / "-work" / f"{keep.sid}.jsonl"           # where Claude Code writes it for /work
