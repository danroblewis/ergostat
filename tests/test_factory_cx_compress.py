"""The compress family (dev/records/cx-compress-tree.md, dev/bin/cx_compress.py): one fixed raw-LZMA2 compressor and
the code scope's Python packed as streams (logic, prose, as written) and the share said again far away."""

from __future__ import annotations

import json
import lzma
import random
import re
import subprocess
import sys
import types

import pytest

from .factory_cx import BIN, ROOT, Repo, cx, load

cxc = load("cx_compress")
LOGIC, PROSE, CODE = "complexity-lzma-logic", "complexity-lzma-prose", "complexity-lzma-code"
SHARE, PER_FILE = "complexity-repeat-share", "complexity-repeat-share-per-file"


def repo(tmp_path) -> Repo:
    return Repo(tmp_path, {"compress": cxc})


def values(r: Repo, sha: str) -> dict:
    doc = cx.measure(r.ctx, sha)
    assert doc["families"]["compress"]["state"] == "ok", doc["families"]["compress"]["error"]
    return doc["values"]


def code(n: int, seed: int) -> str:
    """About n bytes of Python that compresses as real code does, not as a run of one line."""
    rnd, out, i = random.Random(seed), [], 0
    while sum(map(len, out)) < n:
        a, b = rnd.choice("xyzuvw"), rnd.randrange(10 ** 6)
        out.append(f"def f{seed}_{i}({a}, k={b}):\n    return {a} * {rnd.randrange(997)} + k // {rnd.randrange(1, 89)}\n")
        i += 1
    return "".join(out)


def test_filter_is_preset_6_written_out():
    data = code(200_000, 1).encode()
    six = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA2, "preset": 6}])
    assert cxc.packed(data, 8 << 20) == len(six)
    assert cxc.FAR == 32 << 20 and cxc.NEAR == 64 << 10 and set(cxc.FILTER) == {
        "id", "lc", "lp", "pb", "mode", "mf", "nice_len", "depth"}


@pytest.mark.slow
def test_window_fitted_to_the_input_gives_the_same_bytes():
    """packed() sizes the window to the input (a power of two, at most the one asked for): the bytes are those of
    the full window, on each Python file of the code scope and on the stream of them."""
    def full(data, window):
        return len(lzma.compress(data, format=lzma.FORMAT_RAW, filters=[cxc.FILTER | {"dict_size": window}]))
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "ergostat", "dev/bin", "scripts"], capture_output=True,
                           text=True, check=True).stdout.split()
    texts = [(ROOT / n).read_bytes() for n in sorted(names) if n.endswith(".py") and (ROOT / n).is_file()]
    assert len(texts) > 100
    for data in texts:
        assert cxc.packed(data) == full(data, cxc.FAR), data[:80]
    stream = b"\n".join(texts)[:3 << 20]
    assert cxc.packed(stream) == full(stream, cxc.FAR) and cxc.packed(stream, cxc.NEAR) == full(stream, cxc.NEAR)


def test_repeated_file_barely_grows_lzma(tmp_path):
    r = repo(tmp_path)
    big = code(100_000, 2)
    before = values(r, r.commit({"ergostat/big.py": big}))
    after = values(r, r.commit({"ergostat/copy.py": big}))
    assert before[CODE] < after[CODE] < before[CODE] * 1.10
    assert after[SHARE] > before[SHARE] + 0.1


def test_splitting_a_module_does_not_move_repeat_share(tmp_path):
    r = repo(tmp_path)
    b, c = code(40_000, 3), code(80_000, 4)
    whole = values(r, r.commit({"ergostat/mod.py": b + c + b}))
    split = values(r, r.commit({"ergostat/mod.py": b + c, "ergostat/mod2.py": b}))
    assert whole[SHARE] > 0.1
    assert abs(split[SHARE] - whole[SHARE]) < 0.005
    assert split[PER_FILE] > whole[PER_FILE] + 0.05


def test_docstring_only_change_moves_prose_not_logic(tmp_path):
    r = repo(tmp_path)
    one = values(r, r.commit({"ergostat/doc.py": '"""A module."""\n\n\ndef f(x):\n    """Twice x."""\n    return 2 * x\n'}))
    two = values(r, r.commit({"ergostat/doc.py": '"""A module that says much more about itself, at length."""\n\n\n'
                                                 'def f(x):\n    """Twice x, for any number x at all."""\n'
                                                 '    return 2 * x\n'}))
    assert one[LOGIC] == two[LOGIC] and two[PROSE] > one[PROSE]


def test_reformat_does_not_move_logic(tmp_path):
    r = repo(tmp_path)
    one = values(r, r.commit({"ergostat/fmt.py": "def g(a, b):\n    return a + b * 2\n\n\nX = [1, 2, 3]\n"}))
    two = values(r, r.commit({"ergostat/fmt.py": "def g( a,b ):\n  return (a+(b*2))\nX = [\n    1,\n    2,\n    3,\n]\n"}))
    assert one[LOGIC] == two[LOGIC] and one[CODE] != two[CODE]


def test_order_is_by_path():
    def row(path):
        return {"path": path, "vendored": False, "area": "product", "lang": "python",
                "m": {"logic": f"L{path}", "prose": f"P{path}", "unparsed": 0, "lzma": 1}}
    paths = ["ergostat/b.py", "ergostat/a/z.py", "ergostat/a.py", "dev/bin/q.py"]
    snap = types.SimpleNamespace(rows=[row(p) for p in paths], texts=lambda ps: {p: f"R{p}" for p in ps})
    for kind, mark in (("raw", "R"), ("logic", "L"), ("prose", "P")):
        assert cxc.stream(snap, {"lang": "python"}, kind) == "\n".join(mark + p for p in sorted(paths)).encode()


def test_input_over_the_window_fails_not_degrades(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="window"):
        cxc.packed(b"x" * (cxc.FAR + 1))
    r = repo(tmp_path)
    monkeypatch.setattr(cxc, "FAR", 64)                 # each fixture file fits; the stream of them does not
    doc = cx.measure(r.ctx, r.shas[0])
    entry = doc["families"]["compress"]
    assert entry["state"] == "failed" and "window" in entry["error"]
    assert not set(cxc.SERIES) & set(doc["values"])


def test_unparsable_file_counted_not_dropped(tmp_path):
    r = repo(tmp_path)
    good = values(r, r.shas[0])
    bad = values(r, r.commit({"ergostat/bad.py": "def broken(:\n    return 1\n"}))
    assert good["complexity-unparsed-files"] == 0 and bad["complexity-unparsed-files"] == 1
    snap = cx.snapshot(r.ctx, r.shas[1], r.ctx.families)
    assert b"def broken(:\n    return 1\n" in cxc.stream(snap, cxc.PY, "logic")
    assert bad[LOGIC] > good[LOGIC]


def test_empty_blob_first_seen_outside_python_is_measured(tmp_path):
    r = repo(tmp_path)
    r.commit({"docs/empty.txt": "", "ergostat/__init__.py": "", "ergostat/zz.py": ""})
    rows = cx.Snap(r.ctx, r.shas[1], 2, 0, [("docs/empty.txt", "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")], {},
                   r.ctx.families).rows                 # (the empty blob cached as a text file's: no measures)
    assert rows[0]["m"] == {}
    assert values(r, r.shas[1])["complexity-unparsed-files"] == 0


def test_env_names_python_and_library(tmp_path):
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert re.fullmatch(r"\d+\.\d+\.\d+\S*", cxc.liblzma()), cxc.liblzma()
    assert cxc.ENV().startswith(f"py{py}-liblzma{cxc.liblzma()}-")
    r = repo(tmp_path)
    doc = cx.measure(r.ctx, r.shas[0])
    assert doc["families"]["compress"]["env"] == cxc.ENV()
    assert doc["detail"]["compress"] == {"python": py, "liblzma": cxc.liblzma()}


@pytest.mark.slow
def test_the_model_parts_split_no_system():
    """The family's parts read in the root model, in the complexity system, which shows the logic stock; and
    they split neither it nor code-health (check: system-splits), as they did when tied to nothing outside."""
    from ergostat.spec import architecture, read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    assert spec.stocks[LOGIC].system == spec.auxiliaries[SHARE].system == "complexity"
    assert [str(r) for r in spec.show["complexity"]] == ["stock.complexity-lzma-logic"], spec.show["complexity"]
    said = []
    architecture.splits(spec, lambda kind, text, where: said.append((where, text)))
    assert [x for x in said if x[0] in ("system.code-health", "system.complexity")] == []


COST = """
import json, resource, sys, time
sys.path.insert(0, sys.argv[1])
import complexity as cx
fams = {"compress": cx.families()["compress"]}
ctx = cx.Ctx(cx.Path(sys.argv[2]), cx.Path(sys.argv[3]), fams)
def cpu():
    kids = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time() + kids.ru_utime + kids.ru_stime
out = {}
for sha in sys.argv[4:]:
    t0, c0 = time.monotonic(), cpu()
    doc = cx.measure(ctx, sha)
    out[sha] = [doc["families"]["compress"]["state"], round(cpu() - c0, 2), round(time.monotonic() - t0, 2)]
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"runs": out, "mb": rss / (1 << 20 if sys.platform == "darwin" else 1 << 10)}))
"""


@pytest.mark.slow
@pytest.mark.serial
def test_cost_at_todays_size(tmp_path):
    """Definition point 6: one commit of this repository with a cold cache, then its parent with the cache warm (as a
    backfill measures each commit after the one before it). The 12 s bound is the warm one, in CPU seconds (the
    measure's and its git children's: one core); the cold one, paid once per VERSION or ENV, is held under 60 s."""
    shas = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD", "HEAD~1"], capture_output=True, text=True,
                          check=True).stdout.split()
    got = json.loads(subprocess.run([sys.executable, "-c", COST, str(BIN), str(ROOT), str(tmp_path), *shas],
                                    capture_output=True, text=True, check=True, timeout=300).stdout)
    (cold, warm) = got["runs"].values()                # (state, CPU seconds with git's, wall seconds)
    assert cold[0] == warm[0] == "ok" and warm[1] < 12 and cold[1] < 60 and got["mb"] < 500, (cold, warm, got["mb"])
