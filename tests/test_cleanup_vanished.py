"""A folder gone between cleanup's listing and its removal is skipped, and the rest are removed (dev/bin/cleanup.py
`remove`; dev/records/cleanup-starts-before-the-gate.md, 2)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def cleanup(monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    return module("cleanup")


def setup(tmp_path: Path, n: int) -> tuple[dict, list[Path]]:
    sessions = tmp_path / "live" / "sessions"
    sessions.mkdir(parents=True)
    old = time.time() - 3 * 86400
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime(old))
    found = []
    for i in range(n):
        d = sessions / f"gap-{i}-implementor-{stamp}-0a1b2c"
        (d / "work" / ".git" / "objects").mkdir(parents=True)
        (d / "work" / ".git" / "objects" / "pack").write_text("x")
        os.chmod(d / "work" / ".git" / "objects" / "pack", 0o444)
        os.utime(d, (old, old))
        found.append(d)
    cfg = {"paths": {"live": str(tmp_path / "live"), "checkout": str(tmp_path / "checkout"), "run": str(tmp_path)},
           "resources": {"session_keep_hours": 24}}
    return cfg, found


def test_a_folder_removed_mid_run_is_skipped_and_the_rest_are_removed(cleanup, tmp_path, monkeypatch, capsys):
    cfg, found = setup(tmp_path, 4)
    assert cleanup.sessions(cfg) == found
    monkeypatch.setattr(cleanup.fac, "config", lambda: cfg)
    real, calls = cleanup.remove, []

    def remove(cfg, d):                          # another hand removes the second and third once the first is going
        if not calls:
            shutil.rmtree(found[1])
            shutil.rmtree(found[2])
        calls.append(d)
        return real(cfg, d)

    monkeypatch.setattr(cleanup, "remove", remove)
    assert cleanup.main([]) == 0
    assert calls == found                                                   # every folder was tried, in order
    assert not any(d.exists() for d in found)
    out = capsys.readouterr().out
    assert f"{found[1]} was gone already: skipped" in out and f"{found[2]} was gone already: skipped" in out
    assert f"{found[0]} was gone already" not in out and f"{found[3]} was gone already" not in out
    assert "2 folders" in out and "2 gone already" in out


def test_remove_says_gone_and_still_raises_on_anything_else(cleanup, tmp_path, monkeypatch):
    cfg, found = setup(tmp_path, 1)
    shutil.rmtree(found[0])
    assert cleanup.remove(cfg, found[0]) is False                           # gone before it began
    sha = Path(cfg["paths"]["live"]) / ("a" * 40)
    assert cleanup.remove(cfg, sha) is False                                # an install gone: git refuses, skipped
    sha.mkdir()
    with pytest.raises(RuntimeError):                                       # one still there that git refuses: raised
        cleanup.remove(cfg, sha)
    with pytest.raises(ValueError):                                         # outside the sessions folder: raised
        cleanup.remove(cfg, tmp_path / "elsewhere")
    cfg2, kept = setup(tmp_path / "b", 1)
    inner = kept[0] / "work" / ".git" / "objects" / "pack"

    def rmtree(d, onexc):                    # a file in it vanishes under rmtree's feet: passed over, the rest removed
        onexc(os.unlink, str(inner) + ".gone", FileNotFoundError(2, "gone"))
        onexc(os.unlink, str(inner), PermissionError(13, "read-only"))     # (the read-only one made writable)
        assert not inner.exists()
        raise PermissionError(d)

    monkeypatch.setattr(cleanup.shutil, "rmtree", rmtree)
    with pytest.raises(PermissionError):                                    # a folder that cannot be removed: raised
        cleanup.remove(cfg2, kept[0])
