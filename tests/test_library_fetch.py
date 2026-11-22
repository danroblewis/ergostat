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
from ergostat.library import author, fetch, sources, tree
from ergostat.spec import files, read
from ergostat.spec.load import load
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
GREET = "template: greet\ndescription: Greetings waiting.\nstocks:\n  waiting: {unit: things}\nflows:\n  added: {to: waiting}\n"
OTHER = "template: other\ndescription: Another.\nstocks:\n  more: {unit: things}\n"
USES = {"hi": {"use": "greet"}}


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
    return json.loads((d / "libraries.lock").read_text())["libraries"]


@pytest.fixture
def calls(monkeypatch):
    """Every git process fetch starts: its argv and its pid (its process group)."""
    got, real = [], fetch._start

    def rec(args, tmp, stdout):
        p = real(args, tmp, stdout)
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
    args = next(a for a, _ in calls if "fetch" in a)
    i = args.index("--end-of-options")
    assert args[i + 1:] == [up.as_uri(), "v1"] and args.index("fetch") < i
    assert any("check-ref-format" in a and a[-1] == "v1" for a, _ in calls)


def test_fetch_holds_lock_across_write(tmp_path, capsys, monkeypatch):
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up), "b": lib(up)})
    real, procs = fetch._swap, []

    def between(*a, **k):                    # a's copy extracted, its lock entry not yet written: b's fetch starts
        p = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "library", "fetch", "b"], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        procs.append(p)
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [lines.put(x) for x in iter(p.stderr.readline, "")], daemon=True).start()
        assert "waiting for the libraries lock" in lines.get(timeout=30)
        assert p.poll() is None
        return real(*a, **k)
    monkeypatch.setattr(fetch, "_swap", between)
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


def test_failed_lock_write_keeps_old_copy_and_entry(tmp_path, capsys, monkeypatch):
    up, d = owned(tmp_path, capsys, version="main")
    was, text = entries(d)["a"], (d / "libraries.lock").read_text()
    commit(up, {"greet.yaml": GREET.replace("Greetings waiting.", "Changed.")})

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(fetch, "_write_lock", boom)
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
    lock.write_text(json.dumps({"libraries": {}}))
    _refused(d, "library-unlocked")
    e = json.loads(text)
    del e["libraries"]["a"]["tree"]
    lock.write_text(json.dumps(e))
    _refused(d, "library-unlocked")
    lock.write_text(text[:-5])
    _refused(d, "library-lock-unreadable")
    calls.clear()                                         # fetch stops too: never read as an empty lock
    rc, _, err = run_fetch(d, capsys, "--update")
    assert rc == 2 and "cannot be read" in err and calls == [] and lock.read_text() == text[:-5]
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


def test_untrusted_use_refused(tmp_path, capsys):
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)}, USES)
    assert run_fetch(d, capsys)[0] == 0
    spec, ps = read(d / "ergostat.yaml")
    assert [p.code for p in ps if p.level == "error"] == ["library-untrusted"]
    assert not [s for s in spec.stocks if s.startswith("hi-")] and "hi" not in spec.uses
    assert "greet" in json.dumps(author.library(d))       # found and listed, never expanded


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
    assert "library-altered" in p.stdout and "not a regular file" in p.stdout, p.stdout + p.stderr


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


def test_symlink_hashed_not_followed(tmp_path, capsys):
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
    assert rc == 1 and "a link out of the copy" in err and not (d2 / ".libraries" / "a").exists()
    assert not (d2 / "libraries.lock").exists()
    for members, said in [([("l", tarfile.SYMTYPE, "sub"), ("l/x.yaml", tarfile.REGTYPE, b"x")], "members under it"),
                          ([("x.yaml", tarfile.REGTYPE, b"x"), ("h", tarfile.LNKTYPE, "x.yaml")], "not a folder"),
                          ([("p", tarfile.FIFOTYPE, None)], "not a folder"),
                          ([("/abs", tarfile.REGTYPE, b"x")], "not a plain relative path"),
                          ([("a/../../b", tarfile.REGTYPE, b"x")], "not a plain relative path"),
                          # each reads as the copy's top, but x/y goes through x/s: two levels up on disk
                          ([("x", tarfile.DIRTYPE, None), ("x/s", tarfile.SYMTYPE, ".."),
                            ("x/y", tarfile.SYMTYPE, "s/../..")], "through another link"),
                          ([("x/y", tarfile.SYMTYPE, "s/../.."), ("x/s", tarfile.SYMTYPE, "..")], "through another link"),
                          ([("x/y", tarfile.SYMTYPE, "./../.."), ("x/s", tarfile.SYMTYPE, "..")], "out of the copy")]:
        with pytest.raises(tree.Refused, match=said):
            tree.extract(_tar(*members), str(tmp_path / f"x{len(os.listdir(tmp_path))}"))
    ok = tmp_path / "ok"                                   # a link to a link inside, and one up to the top: kept
    tree.extract(_tar(("x/s", tarfile.SYMTYPE, ".."), ("x/y", tarfile.SYMTYPE, "s"), ("g", tarfile.REGTYPE, b"g")),
                 str(ok))
    assert os.path.realpath(ok / "x" / "y") == str(ok.resolve())


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
    monkeypatch.setattr(fetch, "CEILING", 1 << 20)
    rc, _, err = run_fetch(d, capsys)
    assert rc == 1 and "not fetched" in err
    _gone(calls)
    _clean(d)
    monkeypatch.setattr(fetch, "CEILING", 100 << 20)
    small = upstream(tmp_path, {"greet.yaml": GREET, "b.yaml": OTHER, "c.yaml": OTHER}, "small")
    d = model(fresh(tmp_path, "s"), {"a": lib(small)})
    for attr, value, said in [("MAX_ENTRIES", 2, "entries in the archive"), ("MAX_BYTES", 60, "by the headers")]:
        with monkeypatch.context() as m:
            m.setattr(tree, attr, value)
            rc, _, err = run_fetch(d, capsys)
            assert rc == 1 and said in err, err
            _clean(d)
    with monkeypatch.context() as m:
        m.setattr(tree, "declared", lambda _: 0)
        m.setattr(tree, "MAX_BYTES", 60)
        rc, _, err = run_fetch(d, capsys)
        assert rc == 1 and "as written" in err, err
        _clean(d)
    many = model(fresh(tmp_path, "m"), {f"l{i}": lib(small) for i in range(17)})
    assert [c for c, _ in errors(many)] == ["too-many-libraries"]
    calls.clear()
    assert run_fetch(many, capsys)[0] == 2 and calls == []
    _, d = owned(fresh(tmp_path, "o"), capsys)
    (d / ".libraries" / "a" / "planted.yaml").write_bytes(b"#" * 2000)
    monkeypatch.setattr(tree, "MAX_BYTES", 1000)
    got = dict(errors(d))
    assert "bytes (the cap)" in got["library-altered"] and "hash" not in got["library-altered"]


def test_stalled_git_is_killed_by_the_timeout(tmp_path, capsys, calls, monkeypatch):
    """A git that never ends (a stand-in that blocks, with a child in its group): past the time limit the whole group
    is killed and the temporary folder removed; for fetch (the poll) and for archive (the timer)."""
    up = upstream(tmp_path)
    d = model(tmp_path, {"a": lib(up)})
    monkeypatch.setattr(fetch, "TIMEOUT", 1.0)
    real = fetch.argv
    for stalled in ("fetch", "archive"):
        calls.clear()
        monkeypatch.setattr(fetch, "argv", lambda *a, s=stalled: ["sh", "-c", "sleep 60 & sleep 60"] if a[0] == s
                            else real(*a))
        rc, _, err = run_fetch(d, capsys)
        assert rc == 1 and "took longer than 1s" in err, err
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
    monkeypatch.setattr(fetch, "argv", lambda *a: ["sh", "-c", "sleep 60 & sleep 60"] if a[0] == "fetch" else real(*a))
    rc, _, err = run_fetch(d, capsys)
    assert rc == 1 and "took longer than 1s" in err, err
    _gone(calls)
    _clean(d)
    monkeypatch.setattr(fetch, "argv", real)
    calls.clear()
    rc, _, err = run_fetch(d, capsys)
    assert rc == 0, err
    assert set(json.loads((d / "libraries.lock").read_text())["libraries"]) == {"a"}
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
    assert sources.url("https://h.example:8443/a/b.git") and sources.url("file:///srv/lib")
    assert sources.ref("v1.2/x") and sources.ref("a" * 40) and sources.sub("sub/dir") == "sub/dir"
    for bad in ("https://h/r\n", "https://h/r ", "https://h:/r", "https://h:x/r", "file://h/r", "HTTPS://h/r"):
        with pytest.raises(sources.Bad):
            sources.url(bad)
    for bad in ("main\n", "/main", "main/", ".main", "main.", "a//b", "A" * 201, "v 1"):
        with pytest.raises(sources.Bad):
            sources.ref(bad)
    for bad in ("/abs", "a//b", "a/", "a/../b", "a\n"):
        with pytest.raises(sources.Bad):
            sources.sub(bad)
