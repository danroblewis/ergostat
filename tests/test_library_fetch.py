"""Libraries fetched by git URL (SPEC §2a): ``ergostat library fetch`` clones each ``libraries:`` entry into
``.libraries/NAME`` under one flock, pinned in ``libraries.lock`` by commit and tree hash; load checks the copy against
the lock every time, and parses the bytes it hashed. Every repository here is a local ``file://`` one, made in
``tmp_path``."""

import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest
import yaml

from ergostat import goodmodel
from ergostat import model as mdl
from ergostat.cli import build, main
from ergostat.library import author, fetch, sources, tree, untrusted
from ergostat.spec import files, read
from ergostat.spec.load import load
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
GREET = "template: greet\ndescription: Greetings waiting.\nstocks:\n  waiting: {unit: things}\nflows:\n  added: {to: waiting}\n"
OTHER = "template: other\ndescription: Another.\nstocks:\n  more: {unit: things}\n"
USES = {"hi": {"use": "greet"}}
NFD_E, NFC_E = "e" + chr(0x301), chr(0xE9)               # one name to a normalization-insensitive disk (APFS)


def git(cwd, *a) -> str:
    env = {"PATH": os.environ["PATH"], "HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *a], cwd=cwd, env=env,
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(r: Path, put: dict | None = None, msg: str = "c") -> str:
    for k, v in (put or {}).items():
        (r / k).parent.mkdir(parents=True, exist_ok=True)
        (r / k).write_bytes(v) if isinstance(v, bytes) else (r / k).write_text(v)
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", msg)
    return git(r, "rev-parse", "HEAD")


def upstream(tmp_path, put: dict | None = None, name: str = "up") -> Path:
    r = tmp_path / name
    r.mkdir()
    git(r, "init", "-q")
    commit(r, put or {"greet.yaml": GREET})
    git(r, "tag", "v1")
    return r


def lib(up: Path, version: str = "v1", **kw) -> dict:
    return {"git": up.as_uri(), "version": version, **kw}


def fresh(tmp_path, name: str) -> Path:
    (tmp_path / name).mkdir()
    return tmp_path / name


def model(tmp_path, libs, uses=None) -> Path:
    d = tmp_path / "proj"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": libs, **({"uses": uses} if uses else {})}))
    return d


def run_fetch(d: Path, capsys, *a) -> tuple[int, str, str]:
    capsys.readouterr()
    rc = main(["-C", str(d), "library", "fetch", *a])
    got = capsys.readouterr()
    return rc, got.out, got.err


def errors(d: Path) -> list[tuple[str, str]]:
    _, ps = read(d / "ergostat.yaml")
    return [(p.code, p.message) for p in ps if p.level == "error"]


def entries(d: Path) -> dict:
    return json.loads((d / "libraries.lock").read_text())


@pytest.fixture
def calls(monkeypatch):
    """Every git process fetch starts: its argv and its pid (its process group)."""
    got, real = [], fetch._start

    def rec(args, *rest):
        p = real(args, *rest)
        got.append((list(args), p.pid))
        return p
    monkeypatch.setattr(fetch, "_start", rec)
    return got


def owned(tmp_path, capsys, put=None, version="v1"):
    """A project using greet from library a (trust: owner), fetched."""
    up = upstream(tmp_path, put)
    d = model(tmp_path, {"a": lib(up, version, trust="owner")}, USES)
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    return up, d


def test_fetch_locks_and_load_uses_it(tmp_path, capsys, calls):
    up, d = owned(tmp_path, capsys)
    e = entries(d)["a"]
    assert e["commit"] == git(up, "rev-parse", "v1^{commit}") and e["git"] == up.as_uri() and e["version"] == "v1"
    assert e["tree"] == tree.read(d / ".libraries" / "a")[1] and e["tree"].startswith("sha256:")
    assert set(e) == {"git", "version", "commit", "tree"}  # no path: given, and trust: is not the lock's
    spec, ps = read(d / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], ps
    assert "hi-waiting" in spec.stocks and spec.uses["hi"]["library"] == "a"
    capsys.readouterr()
    assert main(["-C", str(d), "check"]) == 0
    assert "use hi: template greet from library a" in capsys.readouterr().out
    calls.clear()
    rc, out, _ = run_fetch(d, capsys)                    # locked, copy whole: nothing to do, no git
    assert rc == 0 and "up to date" in out and calls == []


BAD = [("../x", None, None, None), ("Bad", None, None, None), ("a\n", None, None, None),
       *((None, u, None, None) for u in ["ext::sh -c touch x", "ssh://-oProxyCommand=touch x/r", "https://u:p@h/r",
                                         "http://h/r", "https://-h/r", "file://rel", "https://h/r?q", "https://h/r\n",
                                         "h:path", "https://h/r#f", "file:///a/../b"]),
       *((None, None, v, None) for v in ["--upload-pack=touch x", "-c", "a..b", "x@{1}", "x.lock", "main\n", 1.0]),
       (None, None, None, "../up")]


def test_bad_name_and_scheme_refused(tmp_path, capsys, calls, monkeypatch):
    up = upstream(tmp_path)
    monkeypatch.chdir(tmp_path)
    for name, url, version, path in BAD:
        e = {"git": url or up.as_uri(), "version": version or "v1", **({"path": path} if path else {})}
        d = model(tmp_path, {name or "a": e})
        assert [c for c, _ in errors(d)] == ["bad-library-source"], (name, url, version, path, errors(d))
        rc, _, err = run_fetch(d, capsys)
        assert rc == 2 and "bad-library-source" in err, (name, url, version, path, err)
        assert calls == [] and not (tmp_path / "x").exists() and not (d / ".libraries").exists()
    d = model(tmp_path, {"a": lib(up)})                   # the good one: URL and REF after --end-of-options
    assert run_fetch(d, capsys)[0] == 0
    args = next(a for a, _ in calls if a[0] == "clone")
    i = args.index("--end-of-options")
    assert args[i + 1] == up.as_uri() and len(args) == i + 3
    args = next(a for a, _ in calls if a[0] == "rev-parse")
    assert args[args.index("--end-of-options") + 1:] == ["v1^{commit}"]
    assert any("check-ref-format" in a and a[-1] == "v1" for a, _ in calls)


def test_fetch_holds_lock_across_write(tmp_path, capsys, monkeypatch):
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up), "b": lib(up)})
    real, procs = fetch.write_lock, []

    def between(*a, **k):                    # a's copy extracted, its lock entry not yet written: b's fetch starts
        p = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "library", "fetch", "b"], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        procs.append(p)
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [lines.put(x) for x in iter(p.stderr.readline, "")], daemon=True).start()
        assert "waiting for the libraries lock" in lines.get(timeout=30)
        assert p.poll() is None
        return real(*a, **k)
    monkeypatch.setattr(fetch, "write_lock", between)
    try:
        rc, _, err = run_fetch(d, capsys, "a")
        assert rc == 0, err
        assert procs[0].wait(timeout=60) == 0, procs[0].stdout.read()
        assert set(entries(d)) == {"a", "b"}
        assert (d / ".libraries" / "a" / "greet.yaml").is_file() and (d / ".libraries" / "b" / "greet.yaml").is_file()
    finally:
        for p in procs:
            p.kill()
            p.wait()


def test_update_remake_drops_deleted_files(tmp_path, capsys):
    up, d = owned(tmp_path, capsys, {"greet.yaml": GREET, "b.yaml": OTHER}, version="main")
    copy = d / ".libraries" / "a"
    was = entries(d)["a"]
    assert (copy / "b.yaml").is_file()
    git(up, "rm", "-q", "b.yaml")
    commit(up, {}, "drop b")
    (copy / "stray.yaml").write_text(OTHER)
    rc, _, err = run_fetch(d, capsys, "--update")
    assert rc == 0, err
    assert not (copy / "b.yaml").exists() and not (copy / "stray.yaml").exists()
    now = entries(d)["a"]
    assert now["commit"] != was["commit"] and now["tree"] != was["tree"]
    assert errors(d) == []


def test_refetch_restores_the_locked_commit_after_the_branch_moved(tmp_path, capsys, calls):
    up, d = owned(tmp_path, capsys, version="main")
    copy, was, text = d / ".libraries" / "a", entries(d)["a"], (d / "libraries.lock").read_text()
    commit(up, {"greet.yaml": GREET.replace("Greetings waiting.", "Moved on.")})   # main moved upstream
    shutil.rmtree(copy)
    calls.clear()
    rc, _, err = run_fetch(d, capsys)                     # no --update: the copy comes back as it was locked
    assert rc == 0, err
    assert (copy / "greet.yaml").read_text() == GREET and tree.read(copy)[1] == was["tree"]
    assert (d / "libraries.lock").read_text() == text and errors(d) == []
    args = next(a for a, _ in calls if a[0] == "rev-parse")
    assert args[-1] == was["commit"] + "^{commit}"
    rc, _, err = run_fetch(d, capsys, "--update")         # --update moves the pin
    assert rc == 0 and entries(d)["a"]["commit"] != was["commit"], err
    assert "Moved on." in (copy / "greet.yaml").read_text()


def test_failed_lock_write_keeps_old_copy_and_entry(tmp_path, capsys, monkeypatch):
    up, d = owned(tmp_path, capsys, version="main")
    was, text = entries(d)["a"], (d / "libraries.lock").read_text()
    commit(up, {"greet.yaml": GREET.replace("Greetings waiting.", "Changed.")})

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(fetch, "write_lock", boom)
    rc, _, err = run_fetch(d, capsys, "--update")
    assert rc == 1 and "disk full" in err
    assert (d / "libraries.lock").read_text() == text and tree.read(d / ".libraries" / "a")[1] == was["tree"]
    assert [x for x in os.listdir(d / ".libraries") if x.startswith(".tmp-")] == []
    assert errors(d) == []


def test_changed_git_alone_is_unlocked(tmp_path, capsys):
    up, d = owned(tmp_path, capsys)
    other = tmp_path / "other"
    shutil.copytree(up, other)                            # the same commit, the same tree: only git: differs
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": {"a": lib(other, trust="owner")},
                                                     "uses": USES}))
    got = dict(errors(d))
    assert "library-unlocked" in got
    assert "library a refused: library-unlocked" in got["unknown-template"]


def _refused(d: Path, code: str) -> None:
    spec, ps = read(d / "ergostat.yaml")
    got = {p.code: p.message for p in ps if p.level == "error"}
    assert code in got, got
    assert f"library a refused: {code}" in got["unknown-template"]
    assert "hi-waiting" not in spec.stocks


def test_missing_unlocked_and_treeless_refused(tmp_path, capsys, calls):
    """Five cases, each asserted: copy deleted; lock file deleted; entry removed; entry without tree; lock not JSON."""
    _, d = owned(tmp_path, capsys)
    lock, copy, save = d / "libraries.lock", d / ".libraries" / "a", tmp_path / "save"
    text = lock.read_text()
    shutil.copytree(copy, save, symlinks=True)
    assert errors(d) == []
    shutil.rmtree(copy)
    _refused(d, "library-missing")
    shutil.copytree(save, copy, symlinks=True)
    lock.unlink()
    _refused(d, "library-unlocked")
    lock.write_text(json.dumps({}))
    _refused(d, "library-unlocked")
    e = json.loads(text)
    del e["a"]["tree"]
    lock.write_text(json.dumps(e))
    _refused(d, "library-unlocked")
    lock.write_text(text[:-5])
    _refused(d, "library-lock-unreadable")
    calls.clear()                                         # fetch stops too: never read as an empty lock
    rc, _, err = run_fetch(d, capsys, "--update")
    assert rc == 2 and "bad-lock" in err and calls == [] and lock.read_text() == text[:-5]
    lock.write_text(text)
    assert errors(d) == []


def test_altered_copy_refused(tmp_path, capsys):
    _, d = owned(tmp_path, capsys)
    f = d / ".libraries" / "a" / "greet.yaml"
    f.write_text(GREET.replace("things", "thing5"))
    _refused(d, "library-altered")
    f.write_text(GREET)
    assert errors(d) == []
    f.chmod(0o755)                                        # the exec bit is hashed
    _refused(d, "library-altered")
    rc, out, err = run_fetch(d, capsys)                   # a copy not the lock's is fetched again, not kept
    assert rc == 0 and "up to date" not in out, err
    assert errors(d) == []


def test_untrusted_use_through_the_gate(tmp_path, capsys):
    """Without trust: owner, a structure-only use expands, marked untrusted, as from an untrusted folder
    (library-fetch-load; tests/test_library_fetch_load.py has the refused program-block case)."""
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)}, USES)
    assert run_fetch(d, capsys)[0] == 0
    spec, ps = read(d / "ergostat.yaml")
    assert [p.code for p in ps if p.level == "error"] == []
    assert "hi-waiting" in spec.stocks and spec.uses["hi"]["untrusted"] is True
    assert "greet" in json.dumps(author.library(d))


def test_load_parses_the_bytes_it_hashed(tmp_path, capsys, monkeypatch):
    _, d = owned(tmp_path, capsys)
    real = files.tree

    def then_edit(*a):
        got = real(*a)
        f = d / ".libraries" / "a" / "greet.yaml"
        f.write_text(f.read_text().replace("Greetings waiting.", "Rewritten on disk."))
        return got
    monkeypatch.setattr(files, "tree", then_edit)
    doc = load(d / "ergostat.yaml")
    assert doc._templates["greet"].description == "Greetings waiting."


def test_fifo_in_copy_refused_without_hanging(tmp_path, capsys):
    _, d = owned(tmp_path, capsys)
    os.mkfifo(d / ".libraries" / "a" / "pipe.yaml")
    code = ("import sys, pathlib; from ergostat.spec import read; _, ps = read(pathlib.Path(sys.argv[1])); "
            "print([(p.code, p.message) for p in ps if p.level == 'error'])")
    p = subprocess.run([sys.executable, "-c", code, str(d / "ergostat.yaml")], cwd=ROOT, capture_output=True,
                       text=True, timeout=20)
    assert "library-altered" in p.stdout and "a FIFO, socket or device" in p.stdout, p.stdout + p.stderr


def _tar(*members) -> io.BytesIO:
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w") as t:
        for name, kind, extra in members:
            m = tarfile.TarInfo(name)
            m.type = kind
            if kind == tarfile.SYMTYPE or kind == tarfile.LNKTYPE:
                m.linkname = extra
                t.addfile(m)
            else:
                m.size = len(extra or b"")
                t.addfile(m, io.BytesIO(extra or b""))
    b.seek(0)
    return b


def test_symlink_hashed_not_followed(tmp_path, capsys, monkeypatch):
    up = upstream(tmp_path)
    (up / "same.yaml").symlink_to("greet.yaml")
    commit(up)
    git(up, "tag", "-f", "v1")
    d = model(tmp_path, {"a": lib(up, trust="owner")}, USES)
    assert run_fetch(d, capsys)[0] == 0
    link = d / ".libraries" / "a" / "same.yaml"
    assert link.is_symlink() and errors(d) == []
    link.unlink()
    link.symlink_to("other.yaml")
    _refused(d, "library-altered")
    out = upstream(tmp_path, {"greet.yaml": GREET}, "out")     # a link out of the copy: refused at fetch
    (out / "esc").symlink_to("../../x")
    commit(out)
    git(out, "tag", "-f", "v1")
    d2 = model(fresh(tmp_path, "two"), {"a": lib(out)})
    rc, _, err = run_fetch(d2, capsys)
    assert rc == 1 and "leaves the copy" in err and not (d2 / ".libraries" / "a").exists()
    assert not (d2 / "libraries.lock").exists()
    for members, said in [([("l", tarfile.SYMTYPE, "sub"), ("l/x.yaml", tarfile.REGTYPE, b"x")], "under a link"),
                          ([("x.yaml", tarfile.REGTYPE, b"x"), ("h", tarfile.LNKTYPE, "x.yaml")], "hardlink"),
                          ([("p", tarfile.FIFOTYPE, None)], "FIFO"),
                          ([("/abs", tarfile.REGTYPE, b"x")], "an absolute name"),
                          ([("a/../../b", tarfile.REGTYPE, b"x")], "an absolute name"),
                          # each reads as the copy's top, but x/y goes through x/s: two levels up on disk
                          ([("x", tarfile.DIRTYPE, None), ("x/s", tarfile.SYMTYPE, ".."),
                            ("x/y", tarfile.SYMTYPE, "s/../..")], "passes through a link"),
                          ([("x/y", tarfile.SYMTYPE, "s/../.."), ("x/s", tarfile.SYMTYPE, "..")], "passes through a link"),
                          ([("x/y", tarfile.SYMTYPE, "./../.."), ("x/s", tarfile.SYMTYPE, "..")], "leaves the copy"),
                          # the same on a case- or normalization-insensitive disk (APFS): x/s opens x/S, NFC opens NFD
                          ([("x/S", tarfile.SYMTYPE, ".."), ("x/y", tarfile.SYMTYPE, "s/../..")], "passes through a link"),
                          ([("x/" + NFD_E, tarfile.SYMTYPE, ".."), ("x/y", tarfile.SYMTYPE, NFC_E + "/../..")],
                           "passes through a link"),
                          ([("L", tarfile.SYMTYPE, "sub"), ("l/x.yaml", tarfile.REGTYPE, b"x")], "under a link")]:
        with pytest.raises(files.TreeError, match=said):
            tree.extract(_tar(*members), str(tmp_path / f"x{len(os.listdir(tmp_path))}"))
    with monkeypatch.context() as m:                       # the text check gone, where it resolves still refuses
        m.setattr(tree, "_inside", lambda *a: None)
        with pytest.raises(files.TreeError, match="its realpath leaves the copy"):
            tree.extract(_tar(("x", tarfile.DIRTYPE, None), ("x/s", tarfile.SYMTYPE, ".."),
                              ("x/y", tarfile.SYMTYPE, "s/../..")), str(tmp_path / "bypass"))
    ok = tmp_path / "ok"                                   # a link up to the top: kept
    tree.extract(_tar(("x/s", tarfile.SYMTYPE, ".."), ("g", tarfile.REGTYPE, b"g")), str(ok))
    assert os.path.realpath(ok / "x" / "s") == str(ok.resolve())


def _clean(d: Path) -> None:
    lib_dir = d / ".libraries"
    assert [x for x in os.listdir(lib_dir) if x.startswith(".tmp-")] == []
    assert not (lib_dir / "a").exists() and not (d / "libraries.lock").exists()


def _gone(calls) -> None:
    """Every group fetch started is empty. (A killed child, reparented, is a zombie in its group until init reaps it:
    waited for, up to 10 s, never a fixed sleep; a live one would hold the group past that.)"""
    assert calls
    for _, pid in calls:
        end = time.monotonic() + 10
        while time.monotonic() < end:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with pytest.raises(ProcessLookupError):
            os.killpg(pid, 0)


def test_caps_refuse_large(tmp_path, capsys, calls, monkeypatch):
    up = upstream(tmp_path, {"greet.yaml": GREET, "big.bin": os.urandom(3 << 20)})
    d = model(tmp_path, {"a": lib(up)})
    with monkeypatch.context() as m:
        m.setattr(fetch, "SIZE", 1 << 20)
        rc, _, err = run_fetch(d, capsys)
    assert rc == 1 and "not fetched" in err
    _gone(calls)
    _clean(d)
    small = upstream(tmp_path, {"greet.yaml": GREET, "b.yaml": OTHER, "c.yaml": OTHER}, "small")
    d = model(fresh(tmp_path, "s"), {"a": lib(small)})
    for attr, value, said in [("ENTRIES", 2, "more than 2 entries"), ("BYTES", 60, "byte cap (declared)")]:
        with monkeypatch.context() as m:
            m.setattr(tree, attr, value)
            rc, _, err = run_fetch(d, capsys)
            assert rc == 1 and said in err, err
            _clean(d)
    with monkeypatch.context() as m:
        m.setattr(tree, "_declared", lambda _: 0)
        m.setattr(tree, "BYTES", 60)
        rc, _, err = run_fetch(d, capsys)
        assert rc == 1 and "byte cap (written)" in err, err
        _clean(d)
    many = model(fresh(tmp_path, "m"), {f"l{i}": lib(small) for i in range(17)})
    assert [c for c, _ in errors(many)] == ["too-many-libraries"]
    calls.clear()
    assert run_fetch(many, capsys)[0] == 2 and calls == []
    _, d = owned(fresh(tmp_path, "o"), capsys)
    (d / ".libraries" / "a" / "planted.yaml").write_bytes(b"#" * 2000)
    monkeypatch.setattr(tree, "BYTES", 1000)
    got = dict(errors(d))
    assert "past the byte cap" in got["library-altered"] and "hash" not in got["library-altered"]


def test_stalled_git_is_killed_by_the_timeout(tmp_path, capsys, calls, monkeypatch):
    """A git that never ends (a stand-in that blocks, with a child in its group): past the time limit the whole group
    is killed and the temporary folder removed; for clone and for archive."""
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)})
    monkeypatch.setattr(fetch, "TIMEOUT", 1.0)
    real = fetch.argv
    for stalled in ("clone", "archive"):
        calls.clear()
        monkeypatch.setattr(fetch, "argv", lambda *a, s=stalled: ["sh", "-c", "sleep 60 & sleep 60"] if a[0] == s
                            else real(*a))
        rc, _, err = run_fetch(d, capsys)
        assert rc == 1 and "still running after 1.0 s" in err, err
        _gone(calls)
        _clean(d)


def test_fetch_without_waitid(tmp_path, capsys, calls, monkeypatch):
    """Where ``os.waitid`` is missing (macOS on Python 3.12): a fetch still locks, and a stalled git's group is still
    killed. Fails with AttributeError if fetch calls ``os.waitid`` unguarded."""
    monkeypatch.delattr(os, "waitid", raising=False)
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)})
    real = fetch.argv
    monkeypatch.setattr(fetch, "TIMEOUT", 1.0)
    monkeypatch.setattr(fetch, "argv", lambda *a: ["sh", "-c", "sleep 60 & sleep 60"] if a[0] == "clone" else real(*a))
    rc, _, err = run_fetch(d, capsys)
    assert rc == 1 and "still running after 1.0 s" in err, err
    _gone(calls)
    _clean(d)
    monkeypatch.setattr(fetch, "argv", real)
    calls.clear()
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    assert set(entries(d)) == {"a"}
    _gone(calls)


def test_library_folder_link_refused(tmp_path, capsys):
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)})
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep").write_text("k")
    (d / ".libraries").symlink_to(target)
    rc, _, err = run_fetch(d, capsys)
    assert rc == 2 and "link" in err and sorted(os.listdir(target)) == ["keep"]
    (d / ".libraries").unlink()
    (d / ".libraries").mkdir()
    (d / ".libraries" / "a").symlink_to(target)
    rc, _, err = run_fetch(d, capsys)
    assert rc == 2 and "link" in err and sorted(os.listdir(target)) == ["keep"]
    assert not (d / "libraries.lock").exists()


def _kept(tmp_path, capsys) -> Path:
    _, d = owned(tmp_path, capsys)
    assert goodmodel.keep(Project(mdl.load(d))) is None
    with open(d / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")
    return d


def test_fetch_refused_under_fallback(tmp_path, capsys, calls, monkeypatch):
    d = _kept(tmp_path, capsys)
    lock, listing = (d / "libraries.lock").read_text(), sorted(os.listdir(d / ".libraries"))

    def no(*a):
        raise AssertionError("fallback called")
    monkeypatch.setattr(goodmodel, "fallback", no)
    calls.clear()
    rc, _, err = run_fetch(d, capsys, "--update")
    assert rc == 2 and "not valid YAML" in err and calls == []
    assert (d / "libraries.lock").read_text() == lock and sorted(os.listdir(d / ".libraries")) == listing
    assert "library" not in goodmodel.READS
    assert not goodmodel.reads(build().parse_args(["library", "fetch"]))
    assert not goodmodel.reads(build().parse_args(["library", "fetch", "a", "--update"]))


def test_fallback_reads_library_from_snapshot(tmp_path, capsys):
    d = _kept(tmp_path, capsys)
    shutil.rmtree(d / ".libraries" / "a")
    capsys.readouterr()
    assert main(["-C", str(d), "stock"]) == 0
    got = capsys.readouterr()
    assert "using the last good model" in got.err and "hi-waiting" in got.out, got


def test_sources_are_whole_matches():
    """Each allowlist matches the whole value: a good one with anything after it is refused."""
    def field(**e):
        try:
            sources.check({"a": {"git": "file:///srv/lib", "version": "main", **e}})
        except sources.SourceError as x:
            return x.field
    assert field(git="https://h.example:8443/a/b.git") is None and field(version="v1.2/x") is None
    assert field(version="a" * 40) is None and field(version="a" * 64) is None and field(path="sub/dir") is None
    for bad in ("https://h/r\n", "https://h/r ", "https://h:/r", "https://h:x/r", "file://h/r", "HTTPS://h/r"):
        assert field(git=bad) == "libraries.a.git", bad
    for bad in ("main\n", "/main", "main/", ".main", "main.", "a//b", "A" * 201, "v 1"):
        assert field(version=bad) == "libraries.a.version", bad
    for bad in ("/abs", "a//b", "a/", "a/../b", "a\n"):
        assert field(path=bad) == "libraries.a.path", bad


def test_interrupted_git_is_killed(tmp_path, capsys, calls, monkeypatch):
    """An interrupt (Ctrl-C) while fetch polls a git: git is in a session of its own, so the signal never reaches it;
    its group is killed on the way out and the temporary folder removed."""
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)})
    real = fetch.argv
    monkeypatch.setattr(fetch, "argv", lambda *a: ["sh", "-c", "sleep 60 & sleep 60"] if a[0] == "clone" else real(*a))

    def interrupt(_):                                     # (only once the stalled clone runs, not the git before it)
        if any(a[0] == "clone" for a, _ in calls):
            raise KeyboardInterrupt
        return 0
    monkeypatch.setattr(fetch, "_size", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_fetch(d, capsys)
    _gone([c for c in calls if c[0][0] == "clone"])
    _clean(d)


def two(tmp_path, capsys) -> tuple[Path, dict]:
    """Libraries a (greet, trust: owner) and b (other, untrusted), fetched; their lock entries."""
    up, up2 = upstream(tmp_path), upstream(tmp_path, {"other.yaml": OTHER}, "up2")
    d = model(tmp_path, {"a": lib(up, trust="owner"), "b": lib(up2)})
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    return d, entries(d)


def said(d: Path, capsys, *a) -> tuple[int, str, str]:
    capsys.readouterr()
    rc = main(["-C", str(d), *a])
    got = capsys.readouterr()
    return rc, got.out, got.err


def test_check_lists_each_library(tmp_path, capsys):
    d, e = two(tmp_path, capsys)
    rc, out, _ = said(d, capsys, "check")
    assert rc == 0, out
    got = [x for x in out.splitlines() if x.startswith("library ")]
    assert got == [f"library a: {tmp_path.joinpath('up').as_uri()} @ v1 (commit {e['a']['commit'][:12]}), trust owner, "
                   f"1 template; programs: greet owner's shell",
                   f"library b: {tmp_path.joinpath('up2').as_uri()} @ v1 (commit {e['b']['commit'][:12]}), trust "
                   f"untrusted, 1 template; programs: other sandbox or refused"], out
    rc, out, _ = said(d, capsys, "check", "--json")
    notes = [f for f in json.loads(out)["found"] if f["code"] == "library"]
    assert [(f["level"], f["about"]) for f in notes] == [("note", "library.a"), ("note", "library.b")]
    assert rc == 0 and json.loads(out)["ok"] is True
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf"}))      # no libraries: no line
    rc, out, _ = said(d, capsys, "check")
    assert rc == 0 and "library " not in out, out


def test_listing_says_refused_library(tmp_path, capsys):
    d, e = two(tmp_path, capsys)
    (d / ".libraries" / "a" / "greet.yaml").write_text(GREET.replace("things", "thing5"))
    (d / ".libraries" / "b" / "other.yaml").write_text(OTHER.replace("things", "thing5"))
    rc, out, _ = said(d, capsys, "check")
    assert rc == 1                                        # the refusals are errors; the listing lines are notes
    a = next(x for x in out.splitlines() if x.startswith("library a:"))
    assert a.endswith("0 templates; programs: none offered; refused, library-altered: .libraries/a is not what "
                      "libraries.lock pinned (its tree hash differs)") and e["a"]["commit"][:12] in a, a
    b = next(x for x in out.splitlines() if x.startswith("library b:"))
    assert "refused, library-altered: ⟦untrusted: library file⟧.libraries/b is not" in b, b
    assert untrusted.SAYS in out
    rc, out, _ = said(d, capsys, "library")
    assert rc == 0 and a in out.splitlines() and b in out.splitlines(), out


def test_listing_says_refused_section(tmp_path, capsys):
    """One malformed entry refuses the whole libraries: map (sources.check): each entry, the good one too, is listed
    as refused with the section's code and field, never as no libraries; ``ergostat library`` exits 1."""
    d, _ = two(tmp_path, capsys)
    good = lib(tmp_path / "up", trust="owner")
    libs = {"a": good, "c": {"git": 5, "x": "y"}, "e": {"git": "\x1b[2J", "version": "v1"}}
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": libs}))
    why = "refused, bad-library-source: the libraries: section is refused at libraries.c: an entry of git, version, path"
    rc, out, _ = said(d, capsys, "check")
    got = [x for x in out.splitlines() if x.startswith("library ")]
    assert rc == 1 and len(got) == 3 and all(why in x for x in got), out
    assert got[0].startswith(f"library a: {good['git']} @ v1 (commit not pinned), trust owner, 0 templates"), got
    assert got[1].startswith("library c: no git URL @ no version (commit not pinned), trust untrusted"), got
    assert got[2].startswith("library e: \\u001b[2J @ v1") and "\x1b" not in out, got
    rc, out, err = said(d, capsys, "library")
    assert rc == 1 and out.splitlines() == got and "has no libraries" not in out, out
    assert "refused, bad-library-source" in err, err
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": ["a"]}))   # not a map: nothing to list
    rc, out, err = said(d, capsys, "library")
    assert rc == 1 and out == "" and "libraries: refused, bad-library-source" in err, (out, err)


def test_templates_tool_carries_library_pin(tmp_path, capsys):
    d, e = two(tmp_path, capsys)
    got = {t["template"]: t for t in author.library(d)["templates"]}
    assert got["a/greet"]["library"] == {"name": "a", "version": "v1", "commit": e["a"]["commit"][:12]}
    assert got["b/other"]["library"] == {"name": "b", "version": "v1", "commit": e["b"]["commit"][:12]}
    assert got["a/greet"]["description"] == "Greetings waiting." and "untrusted" not in got["a/greet"]
    assert got["b/other"]["untrusted"] is True and got["b/other"]["description"].startswith("⟦untrusted: template other⟧")
    assert all("library" not in t for n, t in got.items() if n not in ("a/greet", "b/other"))   # ergostat's own: none
    one = author.library(d, "b/other")
    assert one["library"] == got["b/other"]["library"] and one["untrusted"] is True


def test_library_listing_offline(tmp_path, capsys, monkeypatch):
    d = _kept(tmp_path, capsys)                           # library a fetched, its model kept, then the YAML broken
    commit_a = entries(d)["a"]["commit"][:12]

    def no(*a, **k):
        raise AssertionError("a process was started")
    monkeypatch.setattr(fetch, "_start", no)
    monkeypatch.setattr(subprocess, "Popen", no)
    before = {p: p.read_bytes() for p in d.rglob("*") if p.is_file()}
    rc, out, err = said(d, capsys, "library")
    assert rc == 0 and "using the last good model" in err, err
    assert out.splitlines() == [f"library a: {tmp_path.joinpath('up').as_uri()} @ v1 (commit {commit_a}), trust owner, "
                                f"1 template; programs: greet owner's shell"]
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": {"a": lib(tmp_path / "up", trust="owner")},
                                                     "uses": USES}))
    before[d / "ergostat.yaml"] = (d / "ergostat.yaml").read_bytes()
    rc, out2, err = said(d, capsys, "library")
    assert rc == 0 and out2 == out and "last good" not in err, err
    assert {p: p.read_bytes() for p in d.rglob("*") if p.is_file()} == before


def test_path_fetches_its_folder_and_a_missing_one_is_reported(tmp_path, capsys):
    """``path:`` takes one folder of the repository (nested too); a path not in the commit makes git archive fail:
    said as git's failure for that library, and the libraries after it are still fetched."""
    up = upstream(tmp_path, {"lib/sub/greet.yaml": GREET, "top.yaml": OTHER})
    d = model(tmp_path, {"a": lib(up, path="nope", trust="owner"), "b": lib(up, path="lib/sub", trust="owner"),
                         "c": lib(up, path="lib", trust="owner")})
    rc, _, err = run_fetch(d, capsys)
    assert rc == 1 and "library a: not fetched: git-failed: archive" in err and "Traceback" not in err, err
    assert set(entries(d)) == {"b", "c"} and entries(d)["b"]["path"] == "lib/sub"
    assert sorted(os.listdir(d / ".libraries" / "b")) == ["greet.yaml"]
    assert sorted(os.listdir(d / ".libraries" / "c")) == ["sub"]
    assert [x for x in os.listdir(d / ".libraries") if x.startswith(".tmp-")] == []
    (d / "ergostat.yaml").write_text(yaml.safe_dump({"name": "lf", "libraries": {"b": lib(up, path="lib/sub",
                                                                                          trust="owner")}, "uses": USES}))
    spec, ps = read(d / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], ps
    assert "hi-waiting" in spec.stocks
