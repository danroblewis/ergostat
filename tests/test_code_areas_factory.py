"""The factory's code areas (dev/bin/areas.py, the implementor's ``takes: {areas:}`` in dev/model/building.yaml;
dev/records/code-area-ownership.md): the map drawn from git's record of conflicted merges, the replay that counts
them with the map and without, the map as the model's own data, and the route switch that writes (or empties) each
gap's ``touches``."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
H = 3600
T0 = 1_790_000_000


@pytest.fixture
def areas():
    sys.path.insert(0, str(BIN))
    try:
        import areas as mod
        yield mod
    finally:
        sys.path.remove(str(BIN))


def git(repo: Path, *args: str, at: int | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    if at is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{at} +0000"
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env).stdout


def edit(repo: Path, path: str, line: int, text: str) -> None:
    p = repo / path
    rows = p.read_text().splitlines()
    rows[line] = text
    p.write_text("\n".join(rows) + "\n")


def gap(repo: Path, name: str, began: float, files: list[tuple[str, int]], named: str) -> None:
    git(repo, "checkout", "-q", "-b", f"factory/{name}", "main")
    (repo / "dev" / "records").mkdir(parents=True, exist_ok=True)
    (repo / "dev" / "records" / f"{name}.md").write_text(f"# {name}\n\nTouches {named}.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"{name}: the definition", at=int(T0 + began * H))
    for path, line in files:
        edit(repo, path, line, f"{name} was here")
    git(repo, "commit", "-q", "-am", f"{name}: the work", at=int(T0 + began * H + 60))
    git(repo, "checkout", "-q", "main")


def land(repo: Path, name: str, at: float) -> None:
    git(repo, "merge", "-q", "--no-ff", f"factory/{name}", "-m", f"Merge branch 'factory/{name}'", at=int(T0 + at * H))


@pytest.fixture
def history(tmp_path):
    """Three gaps: a (0h-10h) and b (2h-12h) both change ergostat/hot.py and docs/spec.md; a lands first and b's merge
    of main at 11h stops on both (git's `# Conflicts:` list); c (20h-25h) changes ergostat/cold.py and docs/spec.md,
    and conflicts with nothing. A fourth branch, d, is not merged."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for p in ("ergostat/hot.py", "ergostat/cold.py", "docs/spec.md"):
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text("".join(f"line {i}\n" for i in range(12)))
    (repo / "dev" / "records").mkdir(parents=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "start", at=T0 - H)
    gap(repo, "a", 0, [("ergostat/hot.py", 1), ("docs/spec.md", 1)], "ergostat/hot.py")
    gap(repo, "b", 2, [("ergostat/hot.py", 9), ("docs/spec.md", 9)], "ergostat/hot.py and docs/spec.md")
    land(repo, "a", 10)
    git(repo, "checkout", "-q", "factory/b")
    git(repo, "merge", "-q", "--no-ff", "main", "-m",
        "Merge main into the branch\n\n# Conflicts:\n#\tdocs/spec.md\n#\tergostat/hot.py\n", at=T0 + 11 * H)
    git(repo, "checkout", "-q", "main")
    land(repo, "b", 12)
    gap(repo, "c", 20, [("ergostat/cold.py", 1), ("docs/spec.md", 5)], "ergostat/cold.py")
    land(repo, "c", 25)
    gap(repo, "d", 26, [("ergostat/cold.py", 3)], "nothing")
    return repo


def test_the_map_is_drawn_from_the_conflict_history(areas, history):
    gaps = areas.history(history, "main")
    assert [(g["branch"], (g["began"] - T0) / H, (g["landed_at"] - T0) / H) for g in gaps] == [
        ("a", 0, 10), ("b", 2, 12), ("c", 20, 25)]
    b = gaps[1]
    assert b["conflicts"] == [{"at": T0 + 11 * H, "files": ["docs/spec.md", "ergostat/hot.py"]}]
    assert b["landed"] == ["dev/records/b.md", "docs/spec.md", "ergostat/hot.py"]
    assert b["named"] == ["docs/spec.md", "ergostat/hot.py"]
    amap, left = areas.draw(gaps, least=1, load=0.9)
    assert list(amap) == ["ergostat-hot-py"] and amap["ergostat-hot-py"]["paths"] == ["ergostat/hot.py"]
    assert amap["ergostat-hot-py"]["load"] == 0.8                     # 20 hours in flight over the history's 25
    assert left["docs/spec.md"]["load"] == 1.0 and "a lane would carry it in series" in left["docs/spec.md"]["why"]
    assert areas.draw(gaps, least=2, load=0.9) == ({}, {})            # named once: not hot at 2
    assert "ergostat-hot-py: {paths: [ergostat/hot.py]}" in areas.as_yaml(amap)


def test_a_replay_shows_fewer_conflict_send_backs(areas, history):
    """With the drawn map, b waits for a to land (8 hours) and no gap lands hot.py while b is in flight: its conflicted
    merge is gone. Without a map, the replay is the history: the one conflicted merge stays."""
    gaps = areas.history(history, "main")
    amap = {"ergostat-hot-py": {"paths": ["ergostat/hot.py"]}}
    for touches in ("landed", "named"):
        r = areas.replay(gaps, amap, touches)
        assert (r["conflicted_before"], r["conflicted_after"], r["added"]) == (1, 0, 0), r
        assert (r["gaps_waited"], r["wait_hours_total"], r["span_hours_after"]) == (1, 8.0, 25.0), r
    plain = areas.replay(gaps, {}, "landed")
    assert (plain["conflicted_before"], plain["conflicted_after"], plain["gaps_waited"]) == (1, 1, 0)
    late = areas.replay(gaps, amap, "landed", wait=3 * H)              # waited its most, then went: still collides
    assert late["conflicted_after"] == 1 and late["wait_hours_total"] == 3.0
    blind = areas.replay(gaps, {"x": {"paths": ["ergostat/cold.py"]}}, "landed")
    assert blind["conflicted_after"] == 1                              # a map of the wrong file avoids nothing


def test_the_map_is_the_models_data(areas):
    """The factory's map is the implementor's areas: in the model, compiled without a mistake, and what the replay reads."""
    from ergostat.spec import read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert not [str(p) for p in problems if p.level == "error" and "areas" in p.message]
    a = spec.blocks["implementor"].takes.areas
    assert a is not None and a.touches == "touches" and "fix" in a.holding and "approved" in a.holding
    declared = areas.model_map(ROOT / "dev" / "model" / "building.yaml")
    assert [x.name for x in a.map] == list(declared) and len(declared) >= 10
    assert all(x.owner == "lane" for x in a.map)
    assert all(not x.paths[0].startswith("docs/SPEC") for x in a.map)   # too shared to lane: left out


def gaps_now(**fields):
    return [{"id": "gap/x", "state": "ready", "fields": {"branch": "x", "touches": ["old"], **fields}},
            {"id": "gap/d", "state": "fix", "fields": {"branch": "d", "definition": "main:dev/records/d.md"}},
            {"id": "gap/m", "state": "merged", "fields": {"branch": "m", "touches": ["ergostat/hot.py"]}}]


def run_touches(areas, monkeypatch, history, route) -> list:
    import brief
    import fac
    said: list = []
    monkeypatch.setattr(fac, "path", lambda cfg, key: history if key == "checkout" else history / "nowhere")
    monkeypatch.setattr(fac, "say", lambda ev, item=None, **d: said.append((ev, item, d)))
    monkeypatch.setattr(brief, "definition_text", lambda cfg, where, branch: "See ergostat/hot.py." if where else "")
    assert areas.touches({"git": {"base": "main"}, "areas": {"route": route}}, gaps_now()) == len(said)
    return said


def test_the_route_switch_writes_or_empties_touches(areas, monkeypatch, history):
    """Off (the shipped setting): every gap's touches is emptied (said []: touching nothing), so the map holds no gap.
    On: a gap in flight or waiting gets its branch's files from main and the paths its definition names; one whose
    definition cannot be read is said unread (every area, never none); a merged one is left alone."""
    assert run_touches(areas, monkeypatch, history, False) == [
        ("gap.measured", "gap/x", {"touches": []}), ("gap.measured", "gap/d", {"touches": []}),
        ("gap.measured", "gap/m", {"touches": []})]
    assert run_touches(areas, monkeypatch, history, True) == [
        ("gap.measured", "gap/x", {"touches": {"unread": "ValueError: its definition cannot be read"}}),
        ("gap.measured", "gap/d", {"touches": ["dev/records/d.md", "ergostat/cold.py", "ergostat/hot.py"]})]
    with pytest.raises(ValueError):
        run_touches(areas, monkeypatch, history, "yes")


def test_a_gap_made_ready_is_routed_from_its_first_look(areas, monkeypatch, history):
    """The event that makes a gap ready (gap.defined: the planner's and the intake's plan.route, parks.ready_again)
    says its touches, so the implementor's first look routes it; unreadable is every area (the rule's None), never
    none; with the route off, []. The rule reads a gap with no touches said as every area too."""
    from contextlib import nullcontext

    import fac
    import manage
    import parks
    import plan

    from ergostat.leases.areas import touched
    from ergostat.spec import read
    said: list = []
    cfg = {"git": {"base": "main"}, "areas": {"route": True}}
    monkeypatch.setattr(fac, "config", lambda: cfg)
    monkeypatch.setattr(fac, "path", lambda c, key: history if key == "checkout" else history / "nowhere")
    monkeypatch.setattr(fac, "say", lambda ev, item=None, **d: said.append((ev, item, d)))
    rule = read(ROOT / "ergostat.yaml")[0].blocks["implementor"].takes.areas

    def ready(text, branch):
        said.clear()
        assert plan.route(f"gap/{branch}", text, branch=branch) == "ready"
        (ev, _, d), = said
        assert ev == "gap.defined"
        return d["touches"]
    assert ready("Touches dev/bin/queue.py.", "n") == ["dev/bin/queue.py"]                 # new: no branch yet
    assert touched(rule, {"touches": ready("Touches dev/bin/queue.py.", "n")}) == {"dev-bin-queue-py"}
    assert ready("Touches docs/x.md.", "d") == ["dev/records/d.md", "docs/x.md", "ergostat/cold.py"]  # and its branch
    assert "unread" in ready("  ", "e") and touched(rule, {"touches": ready("  ", "e")}) is None
    assert touched(rule, {}) is None and touched(rule, {"touches": None}) is None      # never said: every area
    cfg["areas"]["route"] = False
    assert ready("Touches dev/bin/queue.py.", "n") == []
    monkeypatch.setattr(fac, "config", lambda: (_ for _ in ()).throw(OSError("gone")))
    assert "unread" in ready("Touches dev/bin/queue.py.", "n")

    import brief
    monkeypatch.setattr(fac, "config", lambda: cfg)
    monkeypatch.setattr(brief, "definition_text", lambda c, where, branch: "See dev/bin/fac.py." if where else "")
    monkeypatch.setattr(manage, "continue_lock", lambda c: nullcontext())
    monkeypatch.setattr(manage, "record", lambda ev, item=None, **d: said.append((ev, item, d)))
    cfg["areas"]["route"] = True
    for fields, want in (({"definition": "run/defs/p.md"}, ["dev/bin/fac.py"]), ({}, None)):
        monkeypatch.setattr(manage, "item", lambda gid, f=fields: {"id": gid, "state": "parked", "fields": {
            "branch": "p", "parked_by": parks.ENV_PARK, **f}})
        said.clear()
        assert parks.ready_again(cfg, "gap/p", "met") == "gap/p"
        got = dict((ev, d) for ev, _, d in said)["gap.defined"]["touches"]
        assert got == want if want else "unread" in got


def test_the_intake_says_touches_after_its_definitions():
    """The intake's pass is where touches is written (no block of its own), after the gaps it defines are marked
    ready, and a failure there is said without undoing the intake's own work."""
    text = (BIN / "intake.py").read_text()
    main = text[text.index("def main() -> int:"):]
    assert main.index("areas.touches(cfg, list(known.values()))") > main.index("defined += 1")
    assert "except Exception as e:" in main[main.index("areas.touches"):]
