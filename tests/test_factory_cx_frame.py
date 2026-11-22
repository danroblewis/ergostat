"""The complexity frame (dev/records/cx-measure-frame.md): dev/bin/complexity.py's commit file, blob cache, families
measured apart (retried, recomputed on a new version or env, skipped off their stride), `value` that never computes,
and the first family, size (dev/bin/cx_size.py)."""

from __future__ import annotations

import importlib.util
import json

import pytest

from .factory_cx import ROOT, Repo, cx, family, git, size

TOKENS = "complexity-tokens"


def counted(f, calls: list, what: str = "per_file"):
    """A family like ``f`` whose ``what`` is counted into ``calls``."""
    attrs = {k: getattr(f, k) for k in ("VERSION", "ENV", "SERIES", "EVERY", "per_file", "per_commit") if hasattr(f, k)}
    inner = attrs[what]
    attrs[what] = lambda *a: calls.append(a) or inner(*a)
    return family(**attrs)


def series_of(name: str) -> dict:
    return {name: {"unit": "u", "part": False, "description": name}}


def test_commit_file_shape(tmp_path):
    r = Repo(tmp_path)
    r.commit({"ergostat/core.py": "def add(a, b):\n    return a - b\n"})
    r.commit({"scripts/more.py": "Y = 2\n"})
    for sha in r.shas:
        doc = cx.measure(r.ctx, sha)
        assert doc == json.loads((r.ctx.run / "commits" / f"{sha}.json").read_text())
        assert set(doc) == {"v", "sha", "seq", "at", "families", "values", "detail"} and doc["v"] == 1
        assert doc["sha"] == sha and len(sha) == 40
        assert doc["seq"] == int(git(r.path, "rev-list", "--count", "--first-parent", sha))
        assert doc["at"] == int(git(r.path, "show", "-s", "--format=%ct", sha))
        (entry,) = doc["families"].values()
        assert set(entry) == {"version", "env", "state", "error", "tries", "seconds"}
        assert entry["state"] == "ok" and entry["error"] is None and entry["tries"] == 1
        assert entry["env"] == size.ENV() and entry["version"] == size.VERSION
        assert set(doc["values"]) == set(size.SERIES) and doc["detail"] == {}
    assert [r.ctx.load(s)["seq"] for s in r.shas] == [1, 2, 3]
    assert not list((r.ctx.run / "commits").glob(".*.tmp"))


def test_reads_the_ref_not_the_working_files(tmp_path):
    r = Repo(tmp_path)
    before = cx.measure(r.ctx, r.shas[0])
    (r.path / "ergostat" / "core.py").write_text("def add(a, b):\n    return a + b + 1 + 2 + 3\n")
    (r.path / "ergostat" / "new.py").write_text("Z = 1\n")
    fresh = cx.Ctx(r.path, tmp_path / "run2", {"size": size})
    after = cx.measure(fresh, r.shas[0])
    assert after["values"] == before["values"]
    assert [x["path"] for x in cx.snapshot(fresh, r.shas[0], {"size": size}).rows] == sorted(
        git(r.path, "ls-tree", "-r", "--name-only", r.shas[0]).splitlines())


def test_blob_measured_once(tmp_path):
    calls: list = []
    r = Repo(tmp_path)
    r.ctx.families = {"size": counted(size, calls)}
    cx.measure(r.ctx, r.shas[0])
    blobs = {x.split()[2] for x in git(r.path, "ls-tree", "-r", r.shas[0]).splitlines()}
    assert len(calls) == len(blobs)
    calls.clear()
    r.commit({"ergostat/core.py": "def add(a, b):\n    return b + a\n"})
    cx.measure(r.ctx, r.shas[1])
    assert [c[0] for c in calls] == ["ergostat/core.py"]
    calls.clear()
    again = cx.Ctx(r.path, r.ctx.run, {"size": counted(size, calls)})      # (as a new process: the cache on disk)
    cx.snapshot(again, r.shas[1], again.families)
    assert calls == []
    (cache,) = (r.ctx.run / "blobs").iterdir()
    assert cache.name == f"size-v{size.VERSION}-{size.ENV()}.jsonl"
    assert all(set(json.loads(x)) == {"blob", "m"} for x in cache.read_text().splitlines())


def test_vendored_left_out_and_marked(tmp_path):
    r = Repo(tmp_path)
    plain = cx.measure(r.ctx, r.shas[0])["values"]
    r.commit({"ergostat/web/static/libavoid/libavoid.py": "VENDORED = [1, 2, 3]\n",
              "ergostat/web/static/libavoid/libavoid.wasm": "\0asm",
              "ergostat/web/static/other.wasm": "\0asm"})
    assert cx.measure(r.ctx, r.shas[1])["values"] == plain
    rows = {x["path"]: x for x in cx.snapshot(r.ctx, r.shas[1], r.ctx.families).rows}
    marked = {p for p, x in rows.items() if x["vendored"]}
    assert marked == {"ergostat/web/static/elk.bundled.js", "ergostat/web/static/libavoid/libavoid.py",
                      "ergostat/web/static/libavoid/libavoid.wasm", "ergostat/web/static/other.wasm"}
    assert rows["ergostat/web/static/libavoid/libavoid.py"]["m"]["tokens"] == 9       # measured, kept out of sums
    core = rows["ergostat/core.py"]
    assert {k: core[k] for k in ("area", "package", "lang", "vendored")} == {
        "area": "product", "package": "top", "lang": "python", "vendored": False}
    assert set(core) == {"path", "blob", "area", "package", "lang", "vendored", "m"}
    assert rows["ergostat/web/page.py"]["package"] == "web" and rows["dev/bin/tool.py"]["area"] == "factory"
    assert rows["docs/x.md"]["lang"] == "markdown" and rows["tests/test_s.py"]["area"] == "tests"
    assert plain["complexity-files-code"] == 5


def test_value_never_computes(tmp_path):
    r = Repo(tmp_path)
    measured = cx.measure(r.ctx, r.shas[0])["values"][TOKENS]
    r.commit({"ergostat/core.py": "A = 1\n"})
    r.commit({"ergostat/core.py": "A = 2\n"})

    def boom(*a):
        raise AssertionError("value computed")
    r.ctx.families = {"size": family(VERSION=1, SERIES=size.SERIES, per_file=boom, per_commit=boom, ENV=boom)}
    assert cx.value(r.ctx, TOKENS, r.shas[2]) == (r.shas[0], measured)
    assert not (r.ctx.run / "commits" / f"{r.shas[2]}.json").exists()
    with pytest.raises(cx.Missing, match="not a series"):
        cx.value(r.ctx, "complexity-nothing", r.shas[2])

    out = r.run("value", TOKENS)                                     # the CLI: the base, its newest measured parent
    assert out.returncode == 0 and out.stdout.splitlines()[-1] == str(measured) and r.shas[0] in out.stderr
    other = Repo(tmp_path / "none")
    none = other.run("value", TOKENS)
    assert none.returncode == 1 and none.stdout == "" and none.stderr.startswith(f"{TOKENS}: no value (")
    assert not list((tmp_path / "none" / "run" / "complexity" / "commits").iterdir())


def test_failed_family_is_retried_then_left(tmp_path):
    raised = {"flaky": 0, "broken": 0}

    def flaky(snap):
        raised["flaky"] += 1
        if raised["flaky"] == 1:
            raise RuntimeError("once")
        return {"complexity-flaky": 1}

    def broken(snap):
        raised["broken"] += 1
        raise RuntimeError("always")
    fams = {"broken": family(SERIES=series_of("complexity-broken"), per_commit=broken),
            "flaky": family(SERIES=series_of("complexity-flaky"), per_commit=flaky), "size": size}
    r = Repo(tmp_path, fams)
    sha = r.shas[0]
    tokens = None
    for n in range(1, 6):
        doc = cx.measure(r.ctx, sha)
        tokens = tokens or doc["values"][TOKENS]
        assert doc["values"][TOKENS] == tokens and doc["families"]["size"]["state"] == "ok"
        b, f = doc["families"]["broken"], doc["families"]["flaky"]
        assert b["state"] == "failed" and b["error"] == "RuntimeError: always" and b["tries"] == min(n, 3)
        assert raised["broken"] == min(n, 3) and "complexity-broken" not in doc["values"]
        assert (f["state"], f["tries"], raised["flaky"]) == (("failed", 1, 1) if n == 1 else ("ok", 2, 2))
        assert ("complexity-flaky" in doc["values"]) == (n > 1)
    with pytest.raises(cx.Missing, match="failed"):
        cx.value(r.ctx, "complexity-broken", sha)
    fams["broken"].VERSION = 2                                       # a new version is tried again
    assert cx.measure(r.ctx, sha)["families"]["broken"]["tries"] == 1


def test_version_or_env_recomputes_only_that_family(tmp_path):
    calls: list = []

    def fam(name):
        return family(VERSION=1, ENV=lambda: "e1", SERIES=series_of(f"complexity-{name}"),
                      per_file=lambda p, t: calls.append((name, "file")) or {f"n{name}": 1},
                      per_commit=lambda s: calls.append((name, "commit")) or {f"complexity-{name}": s.sum(f"n{name}")})
    fams = {"a": fam("a"), "b": fam("b")}
    r = Repo(tmp_path, fams)
    sha = r.shas[0]
    first = cx.measure(r.ctx, sha)
    calls.clear()
    assert cx.measure(r.ctx, sha) == first and calls == []
    fams["a"].VERSION = 2
    doc = cx.measure(r.ctx, sha)
    assert {n for n, _ in calls} == {"a"} and ("a", "commit") in calls and ("a", "file") in calls
    assert doc["families"]["a"]["version"] == 2 and doc["families"]["b"] == first["families"]["b"]
    calls.clear()
    fams["b"].ENV = lambda: "e2"
    doc = cx.measure(r.ctx, sha)
    assert {n for n, _ in calls} == {"b"} and doc["families"]["b"]["env"] == "e2"
    assert doc["values"] == first["values"]
    assert {p.name for p in (r.ctx.run / "blobs").iterdir()} == {"a-v1-e1.jsonl", "a-v2-e1.jsonl", "b-v1-e1.jsonl",
                                                                  "b-v1-e2.jsonl"}


def test_stride_family_skipped_off_stride(tmp_path):
    called: list = []
    fams = {"size": size, "slow": family(EVERY=2, SERIES=series_of("complexity-slow"),
                                         per_commit=lambda s: called.append(s.seq) or {"complexity-slow": s.seq})}
    r = Repo(tmp_path, fams)
    r.commit({"ergostat/a.py": "A = 1\n"})
    r.commit({"ergostat/b.py": "B = 1\n"})
    docs = [cx.measure(r.ctx, s) for s in r.shas]
    assert [d["families"]["slow"]["state"] for d in docs] == ["skipped", "ok", "skipped"] and called == [2]
    assert [d["families"]["size"]["state"] for d in docs] == ["ok"] * 3
    assert ["complexity-slow" in d["values"] for d in docs] == [False, True, False]
    assert cx.value(r.ctx, "complexity-slow", r.shas[2]) == (r.shas[1], 2)
    assert [h[0] for h in cx.history(r.ctx, "complexity-slow", r.shas[2])] == [2]
    assert [h[0] for h in cx.history(r.ctx, TOKENS, r.shas[2])] == [1, 2, 3]
    cx.measure(r.ctx, r.shas[2])
    assert called == [2]                                              # (a skip stands)


def test_a_family_written_in_the_gap_is_kept(tmp_path):
    """lesson-1: another family's entry written while one family computes is kept by the merge (re-read in its lock)."""
    r = Repo(tmp_path)

    def meanwhile(snap):
        cx.measure(r.ctx, snap.sha, "size")
        return {"complexity-gap": 1}
    r.ctx.families = {"a": family(SERIES=series_of("complexity-gap"), per_commit=meanwhile), "size": size}
    doc = cx.measure(r.ctx, r.shas[0], "a")
    assert set(doc["families"]) == {"a", "size"} and {TOKENS, "complexity-gap"} <= set(doc["values"])


def test_fstring_is_one_token():
    import tokenize
    split = [t.type for t in tokenize.generate_tokens(iter(['x = f"a{b!r:>4}c"\n']).__next__)]
    assert tokenize.FSTRING_START in split                           # (the tokenizer does split it here)
    assert size.tokens('x = f"a{b!r:>4}c"\n') == size.tokens('x = "abc"\n') == 3
    assert size.tokens('x = f"a{f"{y}"}"  # c\n\n') == 3
    assert size.tokens("# only a comment\n\n") == 0
    assert size.tokens("if a:\n    b = 1\n") == 6


def test_lines_match_code_evidence(tmp_path):
    spec = importlib.util.spec_from_file_location("code_evidence", ROOT / "scripts" / "code_evidence.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    r = Repo(tmp_path)
    r.commit({"dev/bin/tool.py": "def run():\n\n    # c\n    x = 1\n    return x\n", "ergostat/web/static/a.js": "1\n"})
    for sha in r.shas:
        rows = ev.evidence(r.path, sha, {})
        doc = cx.measure(r.ctx, sha)
        assert doc["values"]["complexity-lines-code"] == sum(x["lines"] for x in rows) > 0
        assert doc["values"]["complexity-files-code"] == len(rows)


def test_the_commands(tmp_path):
    r = Repo(tmp_path)
    r.commit({"ergostat/core.py": "A = 1\n"})
    assert "\nsize: ok (tries 1" in "\n" + r.run("measure", r.shas[0]).stdout
    assert r.run("measure").returncode == 0 and r.run("measure", "--family", "nope").returncode == 2
    hist = r.run("history", TOKENS, "--last", "1").stdout.split()
    assert hist[:2] == ["2", r.shas[1]] and len(hist) == 4
    assert len(r.run("history", TOKENS).stdout.splitlines()) == 2
    rows = [json.loads(x) for x in r.run("rows").stdout.splitlines()]
    assert len(rows) == len(git(r.path, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    listed = [json.loads(x) for x in r.run("list", "--json").stdout.splitlines()]
    assert {x["name"]: (x["family"], x["part"]) for x in listed if x["family"] == "size"} == {
        TOKENS: ("size", True), "complexity-lines-code": ("size", False), "complexity-files-code": ("size", False)}
    assert set(listed[0]) == {"name", "unit", "family", "part", "description"}
    assert r.run("report", "nothing").returncode == 2


def test_series_named_for_their_parts():
    from ergostat.spec import read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    fams = cx.families()
    for f in fams.values():
        for name, s in f.SERIES.items():
            assert name.startswith("complexity-")
            assert (name in spec.stocks or name in spec.auxiliaries) == s["part"], name
    st = spec.stocks[TOKENS]
    assert st.system == "complexity" and "complexity.py record" in st.description
    assert spec.flows["complexity-tokens-grown"].target == TOKENS and spec.flows["complexity-tokens-distilled"].source \
        == TOKENS


@pytest.mark.slow
def test_ergostat_check_reports_no_new_finding(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main, spec_cmds
    from ergostat.numbers import extremes_cache
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(spec_cmds, "CHECK_WAIT", None)
    monkeypatch.setattr(extremes_cache, "BOUND", 900.0)

    def found(where, keep) -> set[str]:
        (where / "dev" / "model").mkdir(parents=True)
        for x in (ROOT / "dev").iterdir():
            if x.name != "model":
                (where / "dev" / x.name).symlink_to(x)
        for x in (ROOT / "dev" / "model").iterdir():
            if keep or not x.name.startswith("complexity"):
                (where / "dev" / "model" / x.name).write_text(x.read_text())
        (where / "ergostat.yaml").write_text((ROOT / "ergostat.yaml").read_text())
        main(["-C", str(where), "check", "--json"])
        got = json.loads(capsys.readouterr().out)
        assert got["ok"], [x for x in got["found"] if x["level"] == "error"]
        return {x["id"] for x in got["found"] if x["level"] != "error"}
    assert sorted(found(tmp_path / "now", True) - found(tmp_path / "before", False)) == []
