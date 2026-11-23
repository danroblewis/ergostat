"""library-fetch-tree: the ``libraries:`` allowlist, the walked copy's hash, and the tar extraction's refusals."""

import io
import os
import subprocess
import sys
import tarfile
import unicodedata

import pytest

from ergostat.library import sources, tree
from ergostat.spec import files

GOOD = {"git": "https://example.org/lib/one.git", "version": "v1.2", "path": "templates"}


def _refused(entry=None, name="lib", libraries=None):
    with pytest.raises(sources.SourceError) as e:
        sources.check(libraries if libraries is not None else {name: {**GOOD, **(entry or {})}})
    return e.value


def test_sources_allowlist():
    assert sources.check({"lib": GOOD, "two": {"git": "file:///srv/libs/two", "version": "main"}}) == {
        "lib": GOOD, "two": {"git": "file:///srv/libs/two", "version": "main"}}
    for name in ("a\n", "../x"):
        assert _refused(name=name).code == "bad-library-source"
    for git in ("ext::sh -c x", "ssh://example.org/x.git", "https://user@example.org/x.git",
                "https://u:p@example.org/x", "http://example.org/x.git", "https://example.org/x.git?q",
                "https://example.org/x.git#frag", "https://example.org/../x", "file:///srv/../etc", "file://host/x",
                "https://example.org/x\n"):
        e = _refused({"git": git})
        assert (e.code, e.field) == ("bad-library-source", "libraries.lib.git"), git
    for version in ("--upload-pack=x", "a..b", "x@{1}", "main\n", "-b", ".hidden", "a/.b", "x.lock", "a//b", "x/"):
        e = _refused({"version": version})
        assert (e.code, e.field) == ("bad-library-source", "libraries.lib.version"), version
    for path in ("../up", "/abs", "a/../b", "a\n", "-x"):
        assert _refused({"path": path}).field == "libraries.lib.path", path
    assert _refused({"extra": "x"}).field == "libraries.lib: an entry of git, version, path and trust only"
    assert _refused({"trust": "anyone"}).field == "libraries.lib.trust"
    assert sources.check({"lib": {**GOOD, "trust": "owner"}})["lib"]["trust"] == "owner"
    assert _refused({"version": None}).field == "libraries.lib.version"
    assert _refused({"git": 7}).field == "libraries.lib.git"
    sixteen = {f"l{i}": GOOD for i in range(16)}
    assert len(sources.check(sixteen)) == 16
    e = _refused(libraries={**sixteen, "l16": GOOD})
    assert (e.code, e.field) == ("too-many-libraries", "libraries")


def test_link_and_exec_bit_change_hash(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "run.sh").write_text("echo hi\n")
    (tmp_path / "a").write_text("a")
    (tmp_path / "b").write_text("a")
    os.symlink("a", tmp_path / "ln")
    first = tree.digest(tmp_path)
    assert tree.digest(tmp_path) == first
    assert files.tree(tmp_path)["ln"] == ("link", "a")
    os.unlink(tmp_path / "ln")
    os.symlink("b", tmp_path / "ln")
    retargeted = tree.digest(tmp_path)
    assert retargeted != first
    os.chmod(tmp_path / "d" / "run.sh", 0o755)
    assert files.tree(tmp_path)["d/run.sh"][0] == "exec"
    assert tree.digest(tmp_path) != retargeted
    os.unlink(tmp_path / "ln")
    (tmp_path / "ln").write_text("b")           # a file with the link's target as its bytes: not the same
    assert tree.digest(tmp_path) != retargeted


def _tar(*members, sizes=None) -> io.BytesIO:
    """A tar of (name, kind, body) members: kind 'f', 'x' (exec), 'd', 'l' (body: target), 'h' (hardlink), 'c'."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, kind, body in members:
            m = tarfile.TarInfo(name)
            m.type = {"f": tarfile.REGTYPE, "x": tarfile.REGTYPE, "d": tarfile.DIRTYPE, "l": tarfile.SYMTYPE,
                      "h": tarfile.LNKTYPE, "c": tarfile.CHRTYPE, "p": tarfile.FIFOTYPE}[kind]
            m.mode = 0o755 if kind in "xd" else 0o644
            if kind in "lh":
                m.linkname = body
                tf.addfile(m)
            elif kind in "fx":
                m.size = len(body)
                tf.addfile(m, io.BytesIO(body))
            else:
                tf.addfile(m)
    buf.seek(0)
    return buf


def _refuses(tmp_path, *members, **kw):
    dest = tmp_path / "copy"
    with pytest.raises(files.TreeError) as e:
        tree.extract(_tar(*members), dest, **kw)
    assert not dest.exists()
    return e.value


def test_extract_refuses_escaping_links(tmp_path):
    dest = tmp_path / "ok"
    tree.extract(_tar(("x", "d", None), ("x/a", "f", b"A"), ("x/run", "x", b"#!"), ("x/l", "l", "a"),
                      ("x/up", "l", "../x/a"), ("y/z", "f", b"Z")), dest)
    got = files.tree(dest)
    assert got["x/l"] == ("link", "a") and got["x/run"][0] == "exec" and got["x/a"] == ("file", b"A")
    assert got["y"] == ("dir", None) and got["y/z"] == ("file", b"Z")
    s, y = ("x/s", "l", ".."), ("x/y", "l", "s/../..")
    for order in ((s, y), (y, s)):
        assert "through a link" in str(_refuses(tmp_path, ("x", "d", None), *order))
    assert "leaves the copy" in str(_refuses(tmp_path, ("x/y", "l", "../..")))
    assert "absolute" in str(_refuses(tmp_path, ("x/y", "l", "/etc")))
    assert "through a link" in str(_refuses(tmp_path, ("x/a", "l", "b"), ("x/b", "l", ".")))
    assert "through a link" in str(_refuses(tmp_path, ("x/s", "l", "."), ("x/y", "l", "S/../..")))
    assert _refuses(tmp_path, ("x/s", "l", "."), ("x/S", "f", b"")).code == "bad-library-tree"
    assert "under a link" in str(_refuses(tmp_path, ("x/s", "l", "."), ("x/S/f", "f", b"")))
    nfc, nfd = unicodedata.normalize("NFC", "x/é"), unicodedata.normalize("NFD", "x/é")
    assert nfc != nfd
    assert _refuses(tmp_path, (nfc, "l", "."), (nfd + "/f", "f", b"")).code == "bad-library-tree"
    assert _refuses(tmp_path, (nfc, "f", b""), (nfd, "f", b"")).code == "bad-library-tree"
    assert "under a link" in str(_refuses(tmp_path, ("x/s", "l", "."), ("x/s/f", "f", b"")))
    for bad in (("/abs", "f", b""), ("a/../b", "f", b""), ("../b", "f", b""), ("a//b", "f", b""),
                ("h", "h", "x"), ("c", "c", None), ("p", "p", None)):
        assert _refuses(tmp_path, ("x", "f", b""), bad).code == "bad-library-tree", bad
    assert _refuses(tmp_path, ("x", "f", b"1"), ("x", "f", b"2")).code == "bad-library-tree"
    (tmp_path / "there").mkdir()
    with pytest.raises(FileExistsError):
        tree.extract(_tar(("x", "f", b"")), tmp_path / "there")


def test_caps_and_written_bytes(tmp_path, monkeypatch):
    three = [(f"f{i}", "f", b"abcd") for i in range(3)]
    tree.extract(_tar(*three), tmp_path / "fits", max_entries=3, max_bytes=12)
    assert _refuses(tmp_path, *three, max_entries=2).code == "library-too-big"
    assert _refuses(tmp_path, ("d/e/f", "f", b""), max_entries=2).code == "library-too-big"
    assert "declared" in str(_refuses(tmp_path, *three, max_bytes=11))
    monkeypatch.setattr(tree, "_declared", lambda m: 0)
    e = _refuses(tmp_path, *three, max_bytes=11)
    assert e.code == "library-too-big" and "written" in str(e)
    with pytest.raises(files.TreeError) as e:
        files.tree(tmp_path / "fits", max_entries=2)
    assert e.value.code == "library-too-big"
    with pytest.raises(files.TreeError) as e:
        files.tree(tmp_path / "fits", max_bytes=11)
    assert e.value.code == "library-too-big"
    assert len(files.tree(tmp_path / "fits", max_entries=3, max_bytes=12)) == 3
    deep = tmp_path / "deep"
    deep.joinpath(*["d"] * (files.DEPTH + 1)).mkdir(parents=True)
    with pytest.raises(files.TreeError):
        files.tree(deep)


_FIFO = """
import os, sys
from ergostat.library import tree
from ergostat.spec import files
os.mkfifo(os.path.join(sys.argv[1], "pipe"))
try:
    tree.digest(sys.argv[1])
except files.TreeError as e:
    print(e.code, e.path)
"""


def test_fifo_refused_without_hanging(tmp_path):
    (tmp_path / "a").write_text("a")
    out = subprocess.run([sys.executable, "-c", _FIFO, str(tmp_path)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["bad-library-tree", "pipe"]


def test_not_read_while_replaying(tmp_path):
    with files.replay({}, lambda h: None), pytest.raises(files.NotKept):
        files.tree(tmp_path)
