"""The compute worker's package and protocol (SPEC §12s): the directory, its zipapp and ``ergostat worker --stdio``
each answer hello then pong under ``python3 -I``; the package imports only the standard library and itself; the node
id is kept; seq rises by one a line; another version ends it and an unknown type does not; nothing is written outside
its root."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.compute_pipe import WORKER, Pipe, image_python


def _copy(tmp: Path) -> Path:
    dst = tmp / "pkg" / "worker"
    shutil.copytree(WORKER, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def _env(tmp: Path) -> dict:
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    return {**os.environ, "HOME": str(home)}


def _pack(tmp: Path) -> Path:
    out = tmp / "pkg" / "worker.pyz"
    out.parent.mkdir(exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "ergostat", "worker", "--pack", str(out)], capture_output=True, text=True,
                       timeout=60, env=_env(tmp))
    assert r.returncode == 0, r.stderr
    return out


def _hello_then_pong(argv: list[str], tmp: Path, cwd: Path | None = None) -> dict:
    w = Pipe(argv, env=_env(tmp), cwd=str(cwd or tmp))
    try:
        hello = w.read()
        assert hello and hello["type"] == "hello" and hello["v"] == 1 and hello["seq"] == 1, (hello, w.stderr())
        w.send({"type": "ping", "id": "p1"})
        pong = w.until("pong")[-1]
        assert pong["id"] == "p1" and pong["v"] == 1
    finally:
        rc = w.close()
    assert rc == 0, w.stderr()
    return hello


def test_the_directory_answers_hello_then_pong_under_isolated_python(tmp_path):
    """``python3 -I DIR``: Python puts the directory first on the path even in isolated mode; __main__ also puts it
    there itself when it is missing (the CLI's load by path), so either way its siblings are found."""
    hello = _hello_then_pong([image_python(), "-I", str(_copy(tmp_path)), "--stdio", "--root", str(tmp_path / "r")],
                             tmp_path)
    assert set(hello) == {"v", "seq", "type", "worker", "node", "cpus", "memory", "disk", "arch", "os", "backends",
                          "images", "labels", "slots", "runs"}
    assert re.fullmatch(r"[0-9a-f]{32}", hello["node"])
    assert isinstance(hello["cpus"], int) and 0 < hello["slots"] <= min(hello["cpus"], 64)
    assert isinstance(hello["disk"]["root"], int) and hello["os"] in ("linux", "darwin")
    assert hello["backends"] == [] and hello["images"] == [] and hello["runs"] == [] and hello["labels"] == {}


def test_the_zipapp_answers_hello_then_pong_under_isolated_python(tmp_path):
    pyz = _pack(tmp_path)
    import zipfile
    assert sorted(zipfile.ZipFile(pyz).namelist()) == sorted(p.name for p in WORKER.glob("*.py"))
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "labels.json").write_text('{"gpu": "none"}')
    hello = _hello_then_pong([image_python(), "-I", str(pyz), "--stdio", "--root", str(tmp_path / "r")], tmp_path)
    assert hello["labels"] == {"gpu": "none"}


def test_the_cli_entry_answers_hello_then_pong_under_isolated_python(tmp_path):
    _hello_then_pong([sys.executable, "-I", "-m", "ergostat", "worker", "--stdio", "--root", str(tmp_path / "r")],
                     tmp_path)


def _outside(source: str, siblings: set[str]) -> list[str]:
    """The imports of ``source`` that are neither the standard library nor a sibling module (relative ones too)."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [("." * node.level) + (node.module or "")]
        elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in (
                "__import__", "import_module", "spec_from_file_location"):
            names = ["(a dynamic import)"]
        else:
            continue
        bad += [n for n in names if n.split(".")[0] not in sys.stdlib_module_names | siblings]
    return bad


def test_no_module_of_the_package_imports_outside_the_standard_library_and_itself():
    mods = sorted(WORKER.glob("*.py"))
    siblings = {p.stem for p in mods} - {"__main__"}
    assert {"__main__", "frames", "serve"} <= {p.stem for p in mods}
    assert not (WORKER / "__init__.py").exists()        # flat: run as a folder, never imported as ergostat's package
    for p in mods:
        assert _outside(p.read_text(), siblings) == [], p.name
    # the check itself can fail: each of these is caught
    for planted in ("import yaml", "from ergostat import model", "from . import frames", "import ergostat.cli",
                    "__import__('yaml')", "from frames import x\nimport pathlib, requests"):
        assert _outside(planted, siblings), planted


def test_the_node_id_persists_and_names_no_host_or_user(tmp_path):
    root = tmp_path / "r"
    argv = [image_python(), "-I", str(_copy(tmp_path)), "--stdio", "--root", str(root)]
    first, again = _hello_then_pong(argv, tmp_path)["node"], _hello_then_pong(argv, tmp_path)["node"]
    assert first == again == (root / "node").read_text().strip()
    assert sorted(p.name for p in root.iterdir()) == ["node"]
    for who in (socket.gethostname(), os.environ.get("USER") or "", os.environ.get("LOGNAME") or ""):
        assert not who or who.lower() not in first
    (root / "node").write_text("not-an-id\n")           # unreadable: said, and the worker ends (never a new id)
    w = Pipe(argv, env=_env(tmp_path))
    f = w.read()
    assert f["type"] == "error" and "node id" in f["why"] and w.close() == 1
    assert (root / "node").read_text() == "not-an-id\n"


def test_seq_rises_by_one_per_line_beats_included(tmp_path):
    w = Pipe([image_python(), "-I", str(_copy(tmp_path)), "--stdio", "--root", str(tmp_path / "r"), "--beat", "0.1"],
             env=_env(tmp_path))
    try:
        got = [w.read()]
        for i in range(5):
            w.send({"type": "ping", "id": i})
            got += w.until("pong")
        got += w.until("beat") + w.until("beat")
        assert [f["seq"] for f in got] == list(range(1, len(got) + 1))
        assert [f["id"] for f in got if f["type"] == "pong"] == list(range(5))
        beat = next(f for f in got if f["type"] == "beat")
        assert beat["free"] == got[0]["slots"] and isinstance(beat["disk"]["root"], int) and beat["runs"] == {}
        w.send({"type": "ping", "id": "late"}, seq=w.seq + 2)     # a frame missing in between: said, and it ends
        bad = w.until("error")[-1]
        assert "seq" in bad["why"] and bad["id"] == "late"
        assert w.p.wait(10) == 1
    finally:
        w.close()


def test_another_version_ends_it_and_an_unknown_type_does_not(tmp_path):
    w = Pipe([image_python(), "-I", str(_copy(tmp_path)), "--stdio", "--root", str(tmp_path / "r")], env=_env(tmp_path))
    try:
        assert w.read()["type"] == "hello"
        w.send({"type": "teleport", "id": "t"})
        err = w.until("error")[-1]
        assert err["id"] == "t" and "unknown type" in err["why"]
        w.send({"type": "ping"})                            # a request with no id: said, not ended
        assert w.until("error")[-1]["id"] is None
        w.send({"type": "ping", "id": 7})
        assert w.until("pong")[-1]["id"] == 7
        w.seq += 1
        w.send(b'{"v": 2, "seq": %d, "type": "ping", "id": "v2"}\n' % w.seq)
        err = w.until("error")[-1]
        assert err["id"] == "v2" and "v2" in err["why"]
        assert w.p.wait(10) == 1 and w.read(1) is None      # it ended, and said nothing after
    finally:
        w.close()
    spec = importlib.util.spec_from_file_location("worker_frames", WORKER / "frames.py")
    frames = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frames)                         # every other line that is not a frame ends it too
    ok = {"v": 1, "seq": 1, "type": "ping", "id": 1}
    assert frames.decode(json.dumps(ok).encode() + b"\n", 1) == ok
    for line in (b"x" * (frames.MAX + 1), b"{nope", b"[1]", b"", json.dumps({**ok, "v": True}).encode(),
                 json.dumps({k: v for k, v in ok.items() if k != "v"}).encode(), json.dumps({**ok, "seq": 2}).encode(),
                 json.dumps({**ok, "type": ""}).encode()):
        with pytest.raises(frames.Bad):
            frames.decode(line, 1)


def _files(top: Path) -> dict:
    return {str(p.relative_to(top)): (p.stat().st_size, p.stat().st_mtime_ns) for p in top.rglob("*")}


def test_nothing_is_written_outside_the_root(tmp_path):
    """No --root: the default under HOME, and nothing else written there or in the folder it starts in. The zipapp
    writes nothing beside itself. The directory run plainly gets one file beside it, Python's own cache of __main__
    (written by Python before any line of the worker runs, which isolated mode cannot turn off); with -B, none. The
    worker's own modules are never cached (it sets sys.dont_write_bytecode first)."""
    pyz, pkg = _pack(tmp_path), _copy(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _env(tmp_path)
    root = "home/.local/state/ergostat-worker"
    cache = f"pkg/worker/__pycache__/__main__.{sys.implementation.cache_tag}.pyc"
    for flags, what, beside in ((["-I"], pkg, {"pkg/worker", "pkg/worker/__pycache__", cache}),
                                (["-I", "-B"], pkg, set()), (["-I"], pyz, set())):
        shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
        before = _files(tmp_path)
        _hello_then_pong([image_python(), *flags, str(what), "--stdio"], tmp_path, cwd=cwd)
        after = _files(tmp_path)
        changed = {k for k in after if before.get(k) != after[k]} - beside
        assert all(k == root or k.startswith(root + "/") or root.startswith(k + "/") for k in changed), \
            (flags, what.name, sorted(changed))
        assert set(after) - set(before) - beside <= {"home/.local", "home/.local/state", root, root + "/node"}
        assert (tmp_path / root / "node").is_file() and set(before) <= set(after)
