"""library-fetch-git: a library cloned by its git URL into ``.libraries/NAME`` and pinned in ``libraries.lock``."""

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from ergostat.library import fetch

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env=ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def _upstream(path, files):
    path.mkdir()
    _git(path, "-c", "init.defaultBranch=main", "init", "-q")
    return _commit(path, files)


def _commit(path, files):
    for name, body in files.items():
        if body is None:
            (path / name).unlink()
        else:
            (path / name).parent.mkdir(parents=True, exist_ok=True)
            (path / name).write_text(body)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "c")
    return _git(path, "rev-parse", "HEAD")


def _lock(root):
    return json.loads((root / "libraries.lock").read_text())


def _tmps(root):
    return [n for n in os.listdir(root / ".libraries") if n.startswith(".tmp-")]


def test_fetch_writes_lock(tmp_path):
    up, root = tmp_path / "up", tmp_path / "proj"
    commit = _upstream(up, {"t/one.yaml": "a: 1\n", "README": "x\n"})
    _git(up, "tag", "v1")
    root.mkdir()
    src = {"git": f"file://{up}", "version": "v1", "path": "t"}
    assert fetch.fetch(root, {"lib": src}) == {"lib": "fetched"}
    assert (root / ".libraries/lib/one.yaml").read_text() == "a: 1\n"
    assert not (root / ".libraries/lib/README").exists()
    entry = _lock(root)["lib"]
    assert entry == {**src, "commit": commit, "tree": fetch.tree.digest(root / ".libraries/lib")}
    assert fetch.fetch(root, {"lib": src}) == {"lib": "kept"}
    assert _tmps(root) == []
    # the tag moved upstream: a re-fetch of the missing copy is refused, the copy and lock untouched
    _commit(up, {"t/one.yaml": "a: 2\n"})
    _git(up, "tag", "-f", "v1")
    shutil.rmtree(root / ".libraries/lib")
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch(root, {"lib": src})
    assert e.value.code == "lock-mismatch"
    assert not (root / ".libraries/lib").exists() and _lock(root)["lib"] == entry and _tmps(root) == []
    # a locked commit that is not hex never reaches git; an unreadable lock stops the fetch
    (root / "libraries.lock").write_text(json.dumps({"lib": {**entry, "commit": "--upload-pack=touch /tmp/x"}}))
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch(root, {"lib": src})
    assert e.value.code == "bad-lock" and _tmps(root) == []
    (root / "libraries.lock").write_text("{not json")
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch(root, {"lib": src})
    assert e.value.code == "bad-lock" and not (root / ".libraries/lib").exists()
    # a changed version is resolved again
    (root / "libraries.lock").write_text(json.dumps({"lib": entry}))
    _git(up, "tag", "v2")
    assert fetch.fetch(root, {"lib": {**src, "version": "v2"}}) == {"lib": "fetched"}
    assert (root / ".libraries/lib/one.yaml").read_text() == "a: 2\n"


SECOND = """
import sys
from ergostat.library import fetch
print(fetch.fetch(sys.argv[1], {"two": {"git": sys.argv[2], "version": "main"}}), flush=True)
"""


def test_lock_held_across_write(tmp_path, monkeypatch):
    up, root = tmp_path / "up", tmp_path / "proj"
    _upstream(up, {"a": "1\n"})
    root.mkdir()
    real, seen = fetch.write_lock, []

    def held(at, locks):
        p = subprocess.Popen([sys.executable, "-c", SECOND, str(root), f"file://{up}"], stdout=subprocess.PIPE,
                             text=True, cwd=os.path.dirname(os.path.dirname(os.path.dirname(fetch.__file__))))
        seen.append(p.stdout.readline().strip())
        assert not (root / "libraries.lock").exists()
        real(at, locks)
        seen.append(p)

    monkeypatch.setattr(fetch, "write_lock", held)
    fetch.fetch(root, {"one": {"git": f"file://{up}", "version": "main"}})
    p = seen[1]
    assert p.wait(timeout=60) == 0, p.stdout.read()
    assert seen[0] == "waiting for the libraries lock"
    assert set(_lock(root)) == {"one", "two"}
    assert (root / ".libraries/one/a").exists() and (root / ".libraries/two/a").exists()


def test_update_drops_deleted_files(tmp_path):
    up, root = tmp_path / "up", tmp_path / "proj"
    _upstream(up, {"keep": "k\n", "gone": "g\n"})
    root.mkdir()
    src = {"lib": {"git": f"file://{up}", "version": "main"}}
    fetch.fetch(root, src)
    assert (root / ".libraries/lib/gone").exists()
    head = _commit(up, {"gone": None})
    (root / ".libraries/lib/stray").write_text("planted\n")
    assert fetch.fetch(root, src, update=True) == {"lib": "fetched"}
    assert sorted(os.listdir(root / ".libraries/lib")) == ["keep"]
    assert _lock(root)["lib"]["commit"] == head and _tmps(root) == []


def test_failed_lock_write_keeps_old(tmp_path, monkeypatch):
    up, root = tmp_path / "up", tmp_path / "proj"
    _upstream(up, {"a": "old\n"})
    root.mkdir()
    src = {"lib": {"git": f"file://{up}", "version": "main"}}
    fetch.fetch(root, src)
    before = (root / "libraries.lock").read_text()
    _commit(up, {"a": "new\n", "b": "added\n"})

    def broken(at, locks):
        raise OSError("disk full")

    monkeypatch.setattr(fetch, "write_lock", broken)
    with pytest.raises(OSError):
        fetch.fetch(root, src, update=True)
    assert sorted(os.listdir(root / ".libraries/lib")) == ["a"]
    assert (root / ".libraries/lib/a").read_text() == "old\n"
    assert (root / "libraries.lock").read_text() == before and _tmps(root) == []


FAKE = """#!/bin/sh
for a in "$@"; do
  if [ "$a" = "{at}" ]; then
    echo $$ >> {pids}
    sleep 300 &
    echo $! >> {pids}
    if [ -n "{big}" ]; then head -c 30000 /dev/zero > a; head -c 30000 /dev/zero > b; fi
    sleep 300
    exit 0
  fi
done
exec {git} "$@"
"""


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return bool(out) and not out.startswith("Z")


@pytest.mark.parametrize("waitid", [True, False])
@pytest.mark.parametrize("at", ["clone", "archive"])
@pytest.mark.parametrize("big", [False, True])
def test_stalled_and_large_git_killed(tmp_path, monkeypatch, waitid, at, big):
    up, root, bin_, pids = tmp_path / "up", tmp_path / "proj", tmp_path / "bin", tmp_path / "pids"
    _upstream(up, {"a": "1\n"})
    root.mkdir()
    bin_.mkdir()
    (bin_ / "git").write_text(FAKE.format(at=at, pids=pids, big="1" if big else "", git=shutil.which("git")))
    (bin_ / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setattr(fetch, "TIMEOUT", 30.0 if big else 1.0)
    monkeypatch.setattr(fetch, "SIZE", 20000)
    if not waitid:
        monkeypatch.delattr(os, "waitid", raising=False)
    t0 = time.monotonic()
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch(root, {"lib": {"git": f"file://{up}", "version": "main"}})
    assert e.value.code == "git-limit" and ("bytes" if big else "after") in str(e.value)
    assert time.monotonic() - t0 < 20
    started = [int(x) for x in pids.read_text().split()]
    assert len(started) == 2
    deadline = time.monotonic() + 5
    while any(map(_alive, started)) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(map(_alive, started))
    assert _tmps(root) == [] and not (root / ".libraries/lib").exists()


def test_linked_library_folder_refused(tmp_path):
    up, root, elsewhere = tmp_path / "up", tmp_path / "proj", tmp_path / "elsewhere"
    _upstream(up, {"a": "1\n"})
    root.mkdir()
    elsewhere.mkdir()
    (elsewhere / "keep").write_text("mine\n")
    src = {"lib": {"git": f"file://{up}", "version": "main"}}
    (root / ".libraries").symlink_to(elsewhere)
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch(root, src)
    assert e.value.code == "linked-library-folder"
    assert os.listdir(elsewhere) == ["keep"] and not (root / "libraries.lock").exists()
    (root / ".libraries").unlink()
    (root / ".libraries").mkdir()
    (root / ".libraries/lib").symlink_to(elsewhere)
    for update in (False, True):
        with pytest.raises(fetch.FetchError) as e:
            fetch.fetch(root, src, update=update)
        assert e.value.code == "linked-library-folder"
        assert os.listdir(elsewhere) == ["keep"] and (elsewhere / "keep").read_text() == "mine\n"
        assert _tmps(root) == [] and not (root / "libraries.lock").exists()
