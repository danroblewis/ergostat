"""knowledge.module_map's sha-keyed cache (dev/bin/knowledge.py) with other sessions reading, writing and pruning
it at once: a file gone between the look and the read, a half-written file, and a prune racing another's."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.test_factory_knowledge import knowledge_module

knowledge = knowledge_module()


def setup(tmp_path: Path) -> tuple[dict, str, Path]:
    repo = tmp_path / "repo"
    (repo / "ergostat").mkdir(parents=True)
    (repo / "ergostat" / "thing.py").write_text('"""The thing."""\n')
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "main"], check=True, capture_output=True,
                         text=True).stdout.strip()
    cfg = {"paths": {"checkout": str(repo), "run": str(tmp_path / "run")}, "git": {"base": "main"}}
    return cfg, sha, tmp_path / "run" / "modules"


MAP = {"ergostat": [["thing.py", "The thing."]]}


def test_module_map_survives_its_cache_file_removed_between_check_and_read(tmp_path, monkeypatch):
    cfg, sha, d = setup(tmp_path)
    d.mkdir(parents=True)
    cache = d / f"{sha}.json"
    cache.write_text(json.dumps({"stale": []}))
    read = Path.read_text

    def gone_first(self, *a, **kw):                  # another session prunes it right after it was seen
        if self == cache and cache.exists():
            cache.unlink()
        return read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", gone_first)
    assert knowledge.module_map(cfg) == (sha, MAP)
    assert json.loads(read(cache)) == MAP            # made again, and cached


def test_module_map_rebuilds_on_a_partial_cache_file(tmp_path):
    cfg, sha, d = setup(tmp_path)
    d.mkdir(parents=True)
    (d / f"{sha}.json").write_text('{"ergostat": [["thi')
    assert knowledge.module_map(cfg) == (sha, MAP)
    assert json.loads((d / f"{sha}.json").read_text()) == MAP
    assert not list(d.glob("*.tmp"))                 # the temp file was renamed into place


def test_module_map_prune_skips_a_file_already_gone_and_keeps_its_own(tmp_path, monkeypatch):
    cfg, sha, d = setup(tmp_path)
    d.mkdir(parents=True)
    old = [d / f"{c * 40}.json" for c in "abc"]
    for n, p in enumerate(old, 1):
        p.write_text("{}")
        os.utime(p, (n * 100, n * 100))
    ghost = d / f"{'e' * 40}.json"                   # listed, then pruned by another session before its stat
    glob, replace = Path.glob, os.replace
    monkeypatch.setattr(Path, "glob", lambda self, pat: [ghost, *glob(self, pat)])

    def written_oldest(a, b):                        # its own file is the oldest when the prune runs
        replace(a, b)
        os.utime(b, (1, 1))

    monkeypatch.setattr(os, "replace", written_oldest)
    assert knowledge.module_map(cfg) == (sha, MAP)
    assert (d / f"{sha}.json").exists() and old[1].exists() and old[2].exists()
    assert not old[0].exists() and not ghost.exists()
