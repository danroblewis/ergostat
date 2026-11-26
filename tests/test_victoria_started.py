"""`ergostat run` starts ergostat's own VictoriaMetrics when the readings' store is the default local one and none
answers (storage.start_local): detached, its data under ~/.ergostat, so every command and project shares it. One the
owner named (url:, run:, ERGOSTAT_METRICS_URL) is theirs to start: then it only says how."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess

import pytest

from ergostat import storage


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def local(tmp_path, monkeypatch):
    """The default address moved to a free port, its data under tmp_path, no ERGOSTAT_METRICS_URL."""
    url = f"http://127.0.0.1:{free_port()}"
    monkeypatch.setattr(storage, "VM_URL", url)
    monkeypatch.setattr(storage, "DATA", tmp_path / "vm-data")
    monkeypatch.delenv(storage.URL_ENV, raising=False)
    yield url
    out = subprocess.run(["pgrep", "-f", f"httpListenAddr={url.split('://')[1]}"], capture_output=True, text=True).stdout
    for pid in out.split():
        os.kill(int(pid), signal.SIGTERM)


@pytest.mark.skipif(not any(map(shutil.which, storage.BINARIES)), reason="no victoria-metrics binary")
def test_none_answering_at_the_default_address_ergostat_starts_its_own_and_it_stays(local, tmp_path):
    assert not storage.answers(local)
    assert storage.start_local(storage.Storage()) is None
    assert storage.answers(local, wait=2)
    assert (tmp_path / "vm-data").is_dir() and (tmp_path / "victoria-metrics.log").is_file()
    assert storage.start_local(storage.Storage()) is None       # one answering: nothing more started


def test_without_a_binary_it_says_to_install_one(local, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    why = storage.start_local(storage.Storage())
    assert why and "brew install victoriametrics" in why and local in why


@pytest.mark.parametrize("named", ["url", "run", "env"])
def test_one_the_owner_named_is_never_started_by_ergostat(local, monkeypatch, named):
    other = f"http://127.0.0.1:{free_port()}"
    cfg = storage.Storage()
    if named == "url":
        cfg.url = other
    elif named == "run":
        cfg.run = "victoria-metrics -httpListenAddr=127.0.0.1:1"
    else:
        monkeypatch.setenv(storage.URL_ENV, other)
    started = []
    with monkeypatch.context() as m:                      # (undone before the fixture's own clean-up runs)
        m.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
        why = storage.start_local(cfg, wait=0.1)
    assert why and "no VictoriaMetrics answers" in why and started == []
