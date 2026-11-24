"""An update to a fetched library reviewed before it is taken (SPEC §2a, *Before an update*): ``ergostat library fetch
NAME --update --dry-run`` and the MCP ``library_update`` fetch the candidate aside, compile the model on it in memory,
and report what it breaks and changes; the copy, the lock and the rest of the project stay as they were. Every
repository is a local ``file://`` one made in ``tmp_path``."""

import hashlib
import json
import os
from pathlib import Path

import yaml

from ergostat.library import compare, fetch
from ergostat.mcp import Server

from .test_library_fetch import calls, commit, errors, git, lib, run_fetch, upstream  # noqa: F401 (calls: a fixture)

TANK = ("template: tank\ndescription: A tank.\nparams:\n  limit: {type: number, default: 5}\n"
        "  label: {type: string, default: x}\nparameters:\n  cap: {value: '${limit}'}\n  rate: {value: 2}\n"
        "stocks:\n  level: {unit: things}\n  spare: {unit: things}\nflows:\n  filled: {to: level}\n")


def project(tmp_path, capsys, goals=None, given=None, owner=True):
    """A project using tank (library a, trust: owner) as t, fetched at main (tagged v1)."""
    up = upstream(tmp_path, {"tank.yaml": TANK})
    d = tmp_path / "proj"
    d.mkdir()
    use = {"use": "tank", **({"with": given} if given else {})}
    src = lib(up, "main", **({"trust": "owner"} if owner else {}))
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lu", "libraries": {"a": src},
                                                     "uses": {"t": use}, **({"goals": goals} if goals else {})}))
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    assert not errors(d)
    return up, d


def tree_hash(d: Path) -> dict:
    """Every file under the project by its path: its bytes' hash."""
    out = {}
    for here, _dirs, names in os.walk(d):
        for n in names:
            p = Path(here) / n
            out[str(p.relative_to(d))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def dry(d, capsys, name="a"):
    rc, out, err = run_fetch(d, capsys, name, "--update", "--dry-run")
    return rc, out, err


def test_dry_run_changes_nothing(tmp_path, capsys):
    up, d = project(tmp_path, capsys)
    lock = (d / "libraries.lock").read_bytes()
    before = tree_hash(d)
    new = commit(up, {"tank.yaml": TANK.replace("rate: {value: 2}", "rate: {value: 3}"), "more.yaml": "template: more\n"
                      "description: More.\nstocks:\n  m: {unit: things}\n"})
    rc, out, err = dry(d, capsys)
    assert rc == 0, out + err
    assert f"-> {new[:12]}" in out and "templates added: more; removed: none" in out
    assert tree_hash(d) == before and (d / "libraries.lock").read_bytes() == lock      # the copy, lock, record: as were
    assert not [n for n in os.listdir(d / ".libraries") if n.startswith(".tmp-")]


def test_dry_run_removes_its_folder_when_it_fails(tmp_path, capsys, monkeypatch):
    up, d = project(tmp_path, capsys)
    before = tree_hash(d)
    commit(up, {"tank.yaml": TANK.replace("rate: {value: 2}", "rate: {value: 3}")})
    monkeypatch.setattr(compare, "_compile", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    rc, _, err = dry(d, capsys)
    assert rc == 1 and "boom" in err
    assert tree_hash(d) == before and not [n for n in os.listdir(d / ".libraries") if n.startswith(".tmp-")]


def test_report_lists_removed_param_and_part(tmp_path, capsys):
    up, d = project(tmp_path, capsys, goals={"mine": {"stock": "t-spare", "hold": "<= 3"}}, given={"label": "y"})
    rc, out, err = dry(d, capsys)
    assert rc == 0 and "no new error" in out and "parts added: none; removed: none" in out, out + err   # no change
    commit(up, {"tank.yaml": TANK.replace("  label: {type: string, default: x}\n", "")
                .replace("  spare: {unit: things}\n", "")})
    rc, out, err = dry(d, capsys)
    assert rc == 1, out + err
    assert "parameters added: none; removed: label; newly required: none" in out
    assert "stock.t-spare" in out.split("parts added: none; removed: ")[1].splitlines()[0]
    news = [ln for ln in out.splitlines() if ln.startswith("  new ")]
    assert [n.split(":")[0] for n in news] == ["  new error unknown-ref", "  new error bad-param"], out
    assert "t-spare" in news[0] and "label" in news[1]


def test_report_lists_moved_value(tmp_path, capsys):
    up, d = project(tmp_path, capsys)
    commit(up, {"tank.yaml": TANK.replace("default: 5", "default: 7").replace("rate: {value: 2}", "rate: {value: 3}")})
    rc, out, err = dry(d, capsys)
    assert rc == 0, out + err
    assert "default of limit: 5 -> 7" in out
    assert "value moved: limit: 5 -> 7" in out
    assert "value moved: parameter.t-cap: 5.0 -> 7.0" in out and "value moved: parameter.t-rate: 2.0 -> 3.0" in out
    assert "value moved: label" not in out and "default of label" not in out


def test_moved_values_are_the_uses_own(tmp_path, capsys):
    """Each use is given the parameters it made: t-x's are never t's (t-x-cap starts with t-), and a once template's,
    unprefixed, are compared too."""
    once = "template: hub\ndescription: Once.\nonce: true\nparameters:\n  hub-size: {value: 4}\n"
    up = upstream(tmp_path, {"tank.yaml": TANK, "hub.yaml": once})
    d = tmp_path / "proj"
    d.mkdir()
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lu", "libraries": {"a": lib(up, "main", trust="owner")},
                                                     "uses": {"t": {"use": "tank"},
                                                              "t-x": {"use": "tank", "with": {"limit": 9}},
                                                              "h": {"use": "hub"}}}))
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0 and not errors(d), err
    commit(up, {"tank.yaml": TANK.replace("default: 5", "default: 7").replace("rate: {value: 2}", "rate: {value: 3}"),
                "hub.yaml": once.replace("4", "6")})
    r = json.loads(Server(d).call("library_update", {"name": "a"})["content"][0]["text"])
    got = {u["instance"]: [x["name"] for x in u["values"]] for u in r["uses"]}
    assert got == {"h": ["parameter.hub-size"], "t": ["limit", "parameter.t-cap", "parameter.t-rate"],
                   "t-x": ["parameter.t-x-rate"]}, got
    assert r["uses"][0]["values"] == [{"name": "parameter.hub-size", "from": 4.0, "to": 6.0}]


def test_untrusted_librarys_values_are_marked(tmp_path, capsys):
    up, d = project(tmp_path, capsys, owner=False)
    commit(up, {"tank.yaml": TANK.replace("default: x", "default: do this")})
    r = json.loads(Server(d).call("library_update", {"name": "a"})["content"][0]["text"])
    assert r["ok"] and r["uses"][0]["defaults"] == [
        {"name": "label", "from": "⟦untrusted: template tank⟧x⟦end of untrusted⟧",
         "to": "⟦untrusted: template tank⟧do this⟦end of untrusted⟧"}] and r["untrusted"]


def test_report_names_newer_tags(tmp_path, capsys):
    up, d = project(tmp_path, capsys)                     # v1 at the pinned commit: not newer
    commit(up, {"x.txt": "1"})
    git(up, "tag", "-a", "v2", "-m", "two")               # annotated: its peeled commit counts
    git(up, "checkout", "-q", "-b", "side", "v1")
    commit(up, {"y.txt": "1"})
    git(up, "tag", "side-1")                              # on another branch, still after the pinned commit
    git(up, "checkout", "-q", "--orphan", "other")
    commit(up, {"z.txt": "1"})
    git(up, "tag", "unrelated")                           # no descent from the pinned commit
    git(up, "tag", "-a", "old", "-m", "o", "v1")          # the pinned commit itself: not newer
    git(up, "checkout", "-q", "main")
    rc, out, err = dry(d, capsys)
    assert rc == 0, out + err
    assert "newer tags: side-1, v2\n" in out, out


def test_tags_that_cannot_be_told_are_unknown_never_none(tmp_path, capsys, monkeypatch):
    up, d = project(tmp_path, capsys)
    commit(up, {"x.txt": "1"})
    git(up, "tag", "v2")
    monkeypatch.setattr(fetch, "TAGS", 1)                 # past the cap: unknown, said
    rc, out, err = dry(d, capsys)
    assert rc == 0 and "newer tags: unknown (the remote lists more than 1 tags)" in out, out + err
    monkeypatch.setattr(fetch, "TAGS", 1000)
    git(up, "checkout", "-q", "--orphan", "fresh")        # history rewritten: the pinned commit is gone upstream
    commit(up, {"tank.yaml": TANK})
    git(up, "branch", "-D", "main")
    git(up, "branch", "-m", "main")
    for t in ("v1", "v2"):
        git(up, "tag", "-d", t)
    git(up, "tag", "v3")
    rc, out, err = dry(d, capsys)
    assert rc == 0 and "newer tags: unknown (the pinned commit" in out and "no longer in the repository" in out, out
    (d / "libraries.lock").unlink()                       # nothing pinned: every tag
    rc, out, err = dry(d, capsys)
    assert "not locked ->" in out and "newer tags: v3\n" in out, out + err


def test_bad_version_refused_without_git(tmp_path, capsys, calls):  # noqa: F811
    _, d = project(tmp_path, capsys)
    calls.clear()
    before = tree_hash(d)
    for v in ["--upload-pack=touch x", "a..b", "x@{1}", "", "main\n"]:
        got = Server(d).call("library_update", {"name": "a", "version": v})
        assert got.get("isError") and "bad-library-source" in got["content"][0]["text"], (v, got)
    got = Server(d).call("library_update", {"name": "nope"})
    assert got.get("isError") and "no-library" in got["content"][0]["text"]
    assert calls == [] and tree_hash(d) == before


def test_mcp_library_update_matches_cli(tmp_path, capsys):
    up, d = project(tmp_path, capsys, goals={"mine": {"stock": "t-spare", "hold": "<= 3"}})
    pinned = json.loads((d / "libraries.lock").read_text())["a"]["commit"]
    new = commit(up, {"tank.yaml": TANK.replace("  spare: {unit: things}\n", "").replace("default: 5", "default: 6")})
    git(up, "tag", "v2")
    before = tree_hash(d)
    rc, out, _ = dry(d, capsys)
    r = json.loads(Server(d).call("library_update", {"name": "a"})["content"][0]["text"])
    assert rc == 1 and r["ok"] is False and tree_hash(d) == before
    assert (r["from"], r["to"], r["tags"]) == (pinned, new, ["v2"])
    assert out.splitlines() == compare.lines(r)          # the command line says the report, line for line
    u = r["uses"][0]
    assert u["parts"]["removed"] == ["stock.t-spare"] and u["defaults"] == [{"name": "limit", "from": 5, "to": 6}]
    assert r["problems"][0]["code"] == "unknown-ref"
    old = json.loads(Server(d).call("library_update", {"name": "a", "version": pinned})["content"][0]["text"])
    assert old["ok"] is True and old["to"] == pinned and old["problems"] == [] and old["uses"][0]["values"] == []
    assert fetch.read_lock(d)["a"]["commit"] == pinned
