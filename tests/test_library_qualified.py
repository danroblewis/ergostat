"""``use: LIB/TEMPLATE`` (SPEC §2a): a fetched library's template named with its library, so two libraries may each
offer one name; a bare name offered by more than one source is found ambiguous. Libraries are local ``file://``
repositories made in ``tmp_path``."""

import yaml

from ergostat.library import author
from ergostat.spec import read

from .test_library_fetch import lib, run_fetch, upstream

KEEP = "template: keep-under\ndescription: {L}'s.\nstocks:\n  {l}level: {{unit: things}}\n"
OUTER = ("template: outer\ndescription: Outer.\nuses:\n  in: {use: keep-under}\n  q: {use: b/keep-under}\n")


def project(tmp_path, capsys, uses, order=("a", "b"), extra=None) -> tuple:
    """Libraries a and b (trust: owner), each offering keep-under (its stock alevel or blevel); a also outer, b also
    only-b; fetched, then the uses written."""
    puts = {"a": {"keep.yaml": KEEP.format(L="A", l="a"), "outer.yaml": OUTER},
            "b": {"keep.yaml": KEEP.format(L="B", l="b"), "only.yaml": "template: only-b\nstocks:\n  x: {unit: things}\n"}}
    libs = {n: lib(upstream(tmp_path, puts[n], n), trust="owner") for n in order}
    d = tmp_path / "proj"
    d.mkdir()
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "q", "libraries": libs}, sort_keys=False))
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "q", "libraries": {**libs, **(extra or {})},
                                                     **({"uses": uses} if uses else {})}, sort_keys=False))
    spec, ps = read(d / "ergostat.yaml")
    return d, spec, ps


def test_qualified_use_picks_library(tmp_path, capsys):
    _, spec, ps = project(tmp_path, capsys, {"x": {"use": "a/keep-under"}, "y": {"use": "b/keep-under"}})
    assert [p for p in ps if p.level == "error"] == []
    assert {"x-alevel", "y-blevel"} <= set(spec.stocks) and not {"x-blevel", "y-alevel"} & set(spec.stocks)
    assert spec.uses["x"]["library"] == "a" and spec.uses["y"]["library"] == "b"
    assert spec.uses["x"]["where"].template == "a/keep-under" and spec.uses["y"]["where"].template == "b/keep-under"
    assert not [p for p in ps if p.code == "template-ambiguous"]


def test_bare_name_ambiguous_finding(tmp_path, capsys):
    _, spec, ps = project(tmp_path, capsys, {"z": {"use": "keep-under"}, "w": {"use": "only-b"}})
    assert [p for p in ps if p.level == "error"] == []
    assert "z-alevel" in spec.stocks and spec.uses["z"]["library"] == "a"          # resolved as before: a, first
    got = [p for p in ps if p.code == "template-ambiguous"]
    assert len(got) == 1 and got[0].level == "finding" and got[0].about == "system.z", got
    for said in ("library a", "library b", "ergostat's own", "a/keep-under or b/keep-under"):
        assert said in got[0].message, got[0].message


def test_unknown_library_or_template_said(tmp_path, capsys):
    up = upstream(tmp_path, {"keep.yaml": KEEP.format(L="R", l="r")}, "r")
    _, spec, ps = project(tmp_path, capsys, {"c": {"use": "c/keep-under"}, "n": {"use": "a/nope"},
                                             "r": {"use": "r/keep-under"}}, extra={"r": lib(up, trust="owner")})
    got = {p.about: p.message for p in ps if p.code == "unknown-template"}
    assert "'c' is not a library loaded (libraries: a, b, r)" in got["system.c"], got
    assert "library a offers no template 'nope' (it offers: keep-under, outer)" in got["system.n"], got
    assert "'r' is not a library loaded" in got["system.r"] and "library r refused: library-unlocked" in got["system.r"]
    assert not {"c", "n", "r"} & set(spec.uses)


def test_inner_bare_name_resolves_in_own_library(tmp_path, capsys):
    """b first, so a bare keep-under at the top is b's; inside a's outer it is a's, and b/keep-under there is b's."""
    _, spec, ps = project(tmp_path, capsys, {"o": {"use": "a/outer"}, "t": {"use": "keep-under"}}, order=("b", "a"))
    assert [p for p in ps if p.level == "error"] == []
    assert "t-blevel" in spec.stocks
    inner = {u: r["library"] for u, r in spec.uses.items() if r.get("above") == "o"}
    assert len(inner) == 2 and sorted(inner.values()) == ["a", "b"], inner
    for u, lb in inner.items():
        assert f"{u}-{lb}level" in spec.stocks and spec.uses[u]["where"].template == f"{lb}/keep-under"
    assert [p.about for p in ps if p.code == "template-ambiguous"] == ["system.t"]      # never the library's own


def test_add_use_writes_qualified_name(tmp_path, capsys):
    d, _, _ = project(tmp_path, capsys, None)
    listed = [t["template"] for t in author.library(d)["templates"]]
    assert {"a/keep-under", "b/keep-under", "a/outer", "b/only-b"} <= set(listed), listed
    assert "keep-under" not in listed                     # ergostat's, shadowed by a's: no name would reach it
    assert author.library(d, "b/keep-under")["template"] == "b/keep-under"
    for given, written in [("keep-under", "a/keep-under"), ("only-b", "b/only-b"), ("b/keep-under", "b/keep-under")]:
        got = author.add(d, given.replace("/", "-"), given, write=True)
        assert got["ok"] and f"use: {written}\n" in (d / "ergostat.yaml").read_text(), (given, got)
    spec, ps = read(d / "ergostat.yaml")
    assert "b-keep-under-blevel" in spec.stocks and "keep-under-alevel" in spec.stocks
