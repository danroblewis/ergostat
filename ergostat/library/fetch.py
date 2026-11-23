"""``ergostat library fetch`` (SPEC §2a): each library cloned by git into a new folder under ``.libraries``, its copy
swapped in and pinned in ``libraries.lock`` by commit and tree hash, all under one ``flock`` on ``.libraries/.flock``.
Git runs with ergostat's safe environment (``sandbox/git.py``), https and file only, no redirects, credentials or ssh,
the URL and ref after ``--end-of-options``; each process in its own group, killed past the size ceiling or the time
limit."""

from __future__ import annotations

import fcntl
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

from ..sandbox.git import ENV, SAFE
from ..spec.files import TreeError
from . import sources, tree

CEILING = 100 << 20                 # a clone's folder, and any one file git writes (RLIMIT_FSIZE)
TIMEOUT = 120.0                     # seconds, for each git process
POLL = 0.25
LOCK, DIR = "libraries.lock", ".libraries"
OPTS = ["-c", "http.followRedirects=false", "-c", "credential.helper=", "-c", "core.sshCommand=false"]


class FetchError(Exception):
    pass


def argv(*args: str) -> list[str]:
    return ["git", *SAFE, *OPTS, *args]


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (CEILING, CEILING))


def _start(args: list[str], tmp: str, stdout) -> subprocess.Popen:
    """One git process: its own session (group), the file size cap, ergostat's git environment."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, **ENV, "GIT_ALLOW_PROTOCOL": "https:file",
           "GIT_DIR": os.path.join(tmp, "repo.git")}
    with open(os.path.join(tmp, "err"), "ab") as err:
        return subprocess.Popen(argv(*args), cwd=tmp, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=err,
                                start_new_session=True, preexec_fn=_limits)


def _kill(p: subprocess.Popen) -> int:
    """The whole group killed, then the leader reaped. Every process ends here, its leader not yet reaped (running,
    or exited and waited for with ``WNOWAIT``), so the group id is still its own: any child it left dies too."""
    if p.returncode is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return p.wait()


def _exited(p: subprocess.Popen, block: bool = False) -> bool:
    """Whether the leader has exited, leaving it unreaped. Where ``os.waitid`` is missing (macOS on Python 3.12) the
    leader is reaped and its group killed at once: while any child is left in it, the group id is not given out again."""
    if not hasattr(os, "waitid"):
        if (p.wait() if block else p.poll()) is None:
            return False
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        return True
    try:
        return os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOWAIT | (0 if block else os.WNOHANG)) is not None
    except ChildProcessError:                      # (reaped already, by the timer's kill)
        return True


def _size(d: str) -> int:
    n = 0
    for top, dirs, fs in os.walk(d):
        for f in dirs + fs:
            try:
                n += os.lstat(os.path.join(top, f)).st_size
            except OSError:
                pass
    return n


def _git(tmp: str, *args: str, out: bool = False) -> tuple[int, str]:
    """Run git to its end, polling the folder's size every ``POLL``: past ``CEILING`` or ``TIMEOUT`` the group is
    killed. Its exit code, and its output when asked."""
    path = os.path.join(tmp, "out")
    with open(path, "wb") as fo:
        p = _start(list(args), tmp, fo if out else subprocess.DEVNULL)
    end = time.monotonic() + TIMEOUT
    while not _exited(p):
        why = f"took longer than {TIMEOUT:g}s" if time.monotonic() > end else \
            f"passed the {CEILING}-byte ceiling" if _size(tmp) > CEILING else None
        if why:
            _kill(p)
            raise FetchError(f"git {args[0]} {why}, and was stopped")
        time.sleep(POLL)
    rc = _kill(p)
    with open(path, encoding="utf-8", errors="replace") as f:
        return rc, f.read(4096).strip()


def _said(tmp: str) -> str:
    try:
        with open(os.path.join(tmp, "err"), encoding="utf-8", errors="replace") as f:
            return " ".join(f.read(2000).split()[-30:])
    except OSError:
        return ""


def _archive(tmp: str, commit: str, path: str) -> None:
    """``git archive`` streamed into ``TMP/copy``: the time limit and the group kill hold here too, and a refusal of
    the stream kills the group."""
    p = _start(["archive", "--format=tar", commit, *(["--", path] if path else [])], tmp, subprocess.PIPE)
    late: list[bool] = []
    timer = threading.Timer(TIMEOUT, lambda: (late.append(True), _kill(p)))
    timer.start()
    try:
        tree.extract(p.stdout, os.path.join(tmp, "copy"), tree.ENTRIES, tree.BYTES, path)
        p.stdout.read()
        _exited(p, block=True)
    except BaseException:
        _kill(p)
        if late:
            raise FetchError(f"git archive took longer than {TIMEOUT:g}s, and was stopped") from None
        raise
    finally:
        timer.cancel()
        p.stdout.close()
    if _kill(p):
        why = f"took longer than {TIMEOUT:g}s, and was stopped" if late else "failed"
        raise FetchError(f"git archive {why}: {_said(tmp)}")


def clone(tmp: str, e: dict, locked: dict | None) -> tuple[str, str]:
    """A copy of ``e`` (or of its locked commit) in ``TMP/copy``: its commit and tree hash."""
    v = e["version"]
    if not sources.SHA.fullmatch(v) and _git(tmp, "check-ref-format", "--allow-onelevel", v)[0]:
        raise FetchError(f"version: {v!r} is not a ref name git accepts")
    _git(tmp, "init", "--bare", "-q", os.path.join(tmp, "repo.git"))
    want = locked["commit"] if locked else v
    if _git(tmp, "fetch", "--no-tags", "--depth", "1", "-q", "--end-of-options", e["git"], want)[0]:
        if not sources.SHA.fullmatch(want) or \
                _git(tmp, "fetch", "--no-tags", "-q", "--end-of-options", e["git"], v)[0]:
            raise FetchError(f"git fetch of {want} from {e['git']} failed: {_said(tmp)}")
    rc, commit = _git(tmp, "rev-parse", "--verify", "-q", "--end-of-options",
                      (want if sources.SHA.fullmatch(want) else "FETCH_HEAD") + "^{commit}", out=True)
    if rc or not sources.SHA.fullmatch(commit) or sources.SHA.fullmatch(want) and commit != want:
        raise FetchError(f"{want}: no such commit fetched from {e['git']}")
    _archive(tmp, commit, e.get("path", ""))
    return commit, tree.read(os.path.join(tmp, "copy"))[1]


def _within(root: str, p: str) -> str:
    """``p``, refused unless it resolves under ``root`` (the real ``.libraries``)."""
    if not os.path.realpath(p).startswith(os.path.realpath(root) + os.sep):
        raise FetchError(f"{p} is not under {root}")
    return p


def _remove(root: str, tmp: str) -> None:
    """Only the folder ``mkdtemp`` made (and ``old`` inside it)."""
    if os.path.basename(tmp).startswith(".tmp-"):
        shutil.rmtree(_within(root, tmp), ignore_errors=True)


def _write_lock(main_dir: str, entries: dict) -> None:
    fd, t = tempfile.mkstemp(prefix=f".{LOCK}.", dir=main_dir)
    with os.fdopen(fd, "w") as f:
        json.dump({"libraries": entries}, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(t, os.path.join(main_dir, LOCK))


def _swap(root: str, tmp: str, name: str, main_dir: str, entries: dict, entry: dict) -> None:
    """The old copy to ``TMP/old``, the new one in, the lock written; on any failure the old copy back."""
    dest, old, new = (_within(root, os.path.join(root, name)), os.path.join(tmp, "old"), os.path.join(tmp, "copy"))
    had = os.path.lexists(dest)
    if had:
        os.rename(dest, old)
    try:
        os.rename(new, dest)
        try:
            _write_lock(main_dir, {**entries, name: entry})
        except BaseException:
            os.rename(dest, new)
            raise
    except BaseException:
        if had:
            os.rename(old, dest)
        raise
    entries[name] = entry


def _folder(main_dir: str) -> str:
    root = os.path.join(main_dir, DIR)
    try:
        st = os.lstat(root)
    except FileNotFoundError:
        os.mkdir(root, 0o755)
        st = os.lstat(root)
    if not stat.S_ISDIR(st.st_mode):
        raise FetchError(f"{root} is a link or not a folder: refused")
    return root


def _read_lock(main_dir: str) -> dict:
    try:
        with open(os.path.join(main_dir, LOCK), encoding="utf-8") as f:
            got = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise FetchError(f"{LOCK} cannot be read ({e}): fix or remove it") from None
    if not isinstance(got, dict) or not isinstance(got.get("libraries"), dict) or \
            not all(isinstance(x, dict) for x in got["libraries"].values()):
        raise FetchError(f"{LOCK} is not {{\"libraries\": {{NAME: {{...}}}}}}: fix or remove it")
    return got["libraries"]


def run(main_dir: str, cfg: dict, names: list[str], update: bool) -> int:
    """Fetch ``names`` (all when none) of the checked ``cfg``, one after another, under the libraries lock."""
    root = _folder(main_dir)
    fd = os.open(os.path.join(root, ".flock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("waiting for the libraries lock", file=sys.stderr, flush=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
        entries, rc = _read_lock(main_dir), 0
        for name in names or list(cfg):
            e, lk = {"path": "", **cfg[name]}, entries.get(name)
            same = lk is not None and all(lk.get(k) == e[k] for k in ("git", "version", "path"))
            locked = lk if same and sources.SHA.fullmatch(str(lk.get("commit"))) and isinstance(lk.get("tree"), str) \
                else None                          # (a commit not 40 or 64 hex never reaches git: resolved again)
            dest = _within(root, os.path.join(root, name))
            if os.path.islink(dest):
                raise FetchError(f"{dest} is a link: refused")
            if locked and not update:
                try:
                    if tree.read(dest)[1] == locked["tree"]:
                        print(f"library {name}: up to date at {locked['commit'][:12]}")
                        continue
                except (OSError, TreeError):
                    pass
            else:
                locked = None
            tmp = _within(root, tempfile.mkdtemp(prefix=".tmp-", dir=root))
            try:
                commit, h = clone(tmp, e, locked)
                if locked and (commit, h) != (locked["commit"], locked["tree"]):
                    raise FetchError(f"the locked commit {locked['commit'][:12]} now reads as {commit[:12]} {h}, not "
                                     f"the lock's tree: refused, the copy left as it was")
                _swap(root, tmp, name, main_dir, entries, {"git": e["git"], "version": e["version"], "path": e["path"],
                                                           "commit": commit, "tree": h})
                print(f"library {name}: {e['version']} at {commit[:12]} ({h[:19]})")
            except (FetchError, TreeError, tarfile.TarError, OSError) as x:
                print(f"library {name}: not fetched: {x}", file=sys.stderr)
                rc = 1
            finally:
                _remove(root, tmp)
        return rc
    finally:
        os.close(fd)
