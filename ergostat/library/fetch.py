"""A library fetched by its ``git:`` URL into ``.libraries/NAME``, pinned in ``libraries.lock`` by commit and tree.

Everything from reading the lock to writing it is done under an exclusive flock on ``.libraries/.flock``, a file
opened O_NOFOLLOW and never replaced. Each library is cloned bare and archived into a fresh ``.libraries/.tmp-*``
folder (never over a copy), extracted there (``tree.extract``), hashed (``tree.digest``), swapped in by rename, and
its lock entry written; a failed lock write puts the old copy back. Git runs with ``sandbox/git.py``'s env and
``SAFE`` options, https and file only, no redirects, credential helper or ssh, each process in its own session under
a file-size rlimit, a poll of the folder's size and a time limit, past which its whole process group is killed."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import tempfile
import time

from ergostat.library import sources, tree
from ergostat.sandbox import git

LOCK, FOLDER = "libraries.lock", ".libraries"
SIZE, TIMEOUT = 100_000_000, 120.0
_HEX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_OPTS = ["-c", "http.followRedirects=false", "-c", "credential.helper=", "-c", "core.sshCommand=false"]


class FetchError(RuntimeError):
    """A fetch refused: ``code`` (bad-lock, linked-library-folder, bad-version, git-failed, git-limit, lock-mismatch)
    and ``name``, the library or file it is about."""

    def __init__(self, code: str, name: str, why: str):
        super().__init__(f"{code}: {name}: {why}")
        self.code, self.name = code, name


def _say(line: str) -> None:
    print(line, flush=True)


def fetch(root, libraries: dict, update: bool = False, say=_say) -> dict[str, str]:
    """Fetch each library in ``libraries`` (checked by ``sources.check``) under ``root``; returns name -> ``fetched``
    or ``kept``. An entry whose ``git``, ``version`` and ``path`` match the lock and whose copy is there is kept,
    unless ``update``. Otherwise its version is resolved again; without ``update``, a commit or tree other than the
    locked one is refused (``lock-mismatch``). The first refusal stops the fetch, with what was done before it kept."""
    wanted = sources.check(libraries)
    root = os.path.realpath(root)
    folder = os.path.join(root, FOLDER)
    if os.path.islink(folder):
        raise FetchError("linked-library-folder", FOLDER, "is a link")
    with contextlib.suppress(FileExistsError):
        os.mkdir(folder, 0o755)
    dfd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        lfd = os.open(".flock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=dfd)
    finally:
        os.close(dfd)
    try:
        try:
            fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say("waiting for the libraries lock")
            fcntl.flock(lfd, fcntl.LOCK_EX)
        return {name: _one(root, folder, name, src, update) for name, src in wanted.items()}
    finally:
        os.close(lfd)


def _one(root: str, folder: str, name: str, src: dict, update: bool) -> str:
    locks = read_lock(root)
    dest = _inside(folder, name)
    old = locks.get(name)
    same = old is not None and all(old.get(k) == src.get(k) for k in sources.KEYS)
    if same and not _HEX.fullmatch(str(old.get("commit"))):
        raise FetchError("bad-lock", name, "its locked commit is not hex")
    if same and not update and os.path.isdir(dest):
        return "kept"
    tmp = tempfile.mkdtemp(prefix=".tmp-", dir=folder)
    try:
        commit, digest = _get(tmp, src)
        if same and not update and (commit, digest) != (old.get("commit"), old.get("tree")):
            raise FetchError("lock-mismatch", name, f"resolved {commit} {digest}, locked {old.get('commit')} "
                             f"{old.get('tree')}; fetch with update to move it")
        had = os.path.isdir(dest)
        if had:
            os.rename(dest, os.path.join(tmp, "old"))
        os.rename(os.path.join(tmp, "copy"), dest)
        try:
            write_lock(root, {**locks, name: {**src, "commit": commit, "tree": digest}})
        except BaseException:
            os.rename(dest, os.path.join(tmp, "failed"))
            if had:
                os.rename(os.path.join(tmp, "old"), dest)
            raise
        return "fetched"
    finally:
        _remove(folder, tmp)


def _inside(folder: str, name: str) -> str:
    """``folder``/``name``, refused if it is a link or does not resolve to just that under ``folder``."""
    path = os.path.join(folder, name)
    if os.path.islink(path) or os.path.realpath(path) != os.path.join(os.path.realpath(folder), name):
        raise FetchError("linked-library-folder", f"{FOLDER}/{name}", "is a link or resolves elsewhere")
    return path


def _remove(folder: str, tmp: str) -> None:
    """Delete the temporary folder this fetch made, only once it is seen to be a ``.tmp-`` folder in ``folder``."""
    name = os.path.basename(tmp)
    if name.startswith(".tmp-") and os.path.dirname(tmp) == folder:
        shutil.rmtree(_inside(folder, name))


def _get(tmp: str, src: dict) -> tuple[str, str]:
    """Check the version with ``git check-ref-format``, clone ``src`` bare into ``tmp``, resolve the version, archive
    it (or its ``path``) and extract it to ``tmp``/copy; returns the commit and the copy's digest."""
    try:
        _run(["check-ref-format", "--allow-onelevel", src["version"]], tmp, tmp)
    except FetchError as e:
        if e.code != "git-failed":
            raise
        raise FetchError("bad-version", src["version"], "git check-ref-format refuses it") from None
    repo = os.path.join(tmp, "repo.git")
    _run(["clone", "--bare", "--quiet", "--template=", "--end-of-options", src["git"], repo], tmp, tmp)
    out = os.path.join(tmp, "out")
    with open(out, "w+b") as f:
        _run(["rev-parse", "--verify", "--quiet", "--end-of-options", src["version"] + "^{commit}"], tmp, tmp, repo, f)
        f.seek(0)
        commit = f.read().decode().strip()
    if not _HEX.fullmatch(commit):
        raise FetchError("git-failed", src["version"], f"resolved to {commit[:80]!r}")
    with open(out, "w+b") as f:
        what = commit + (":" + src["path"] if "path" in src else "")
        _run(["archive", "--format=tar", "--end-of-options", what], tmp, tmp, repo, f)
        f.seek(0)
        tree.extract(f, os.path.join(tmp, "copy"))
    return commit, tree.digest(os.path.join(tmp, "copy"))


def _limit() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (SIZE, SIZE))


def _run(args: list[str], cwd: str, watch: str, gitdir: str | None = None, out=None) -> None:
    """Run ``git ARGS`` in its own session; past ``TIMEOUT`` seconds or ``SIZE`` bytes under ``watch``, or on any
    exception here, its whole process group is killed while its leader is not yet reaped (so the group id is still
    its own). Where ``os.waitid`` is missing the leader is reaped by ``poll``, and the group killed only before."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), **git.ENV,
           "GIT_ALLOW_PROTOCOL": "https:file", **({"GIT_DIR": gitdir} if gitdir else {})}
    with tempfile.TemporaryFile() as err:
        p = subprocess.Popen(["git", *git.SAFE, *_OPTS, *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=out or subprocess.DEVNULL, stderr=err, start_new_session=True, preexec_fn=_limit)
        end = time.monotonic() + TIMEOUT
        try:
            while not _ended(p):
                if time.monotonic() > end:
                    raise FetchError("git-limit", args[0], f"still running after {TIMEOUT} s")
                if _size(watch) > SIZE:
                    raise FetchError("git-limit", args[0], f"wrote more than {SIZE} bytes")
                time.sleep(0.05)
        finally:
            if p.returncode is None:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        if p.returncode:
            err.seek(0)
            raise FetchError("git-failed", args[0], err.read()[-2000:].decode(errors="replace").strip())


def _ended(p: subprocess.Popen) -> bool:
    if hasattr(os, "waitid"):
        return os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    return p.poll() is not None


def _size(top: str) -> int:
    total = 0
    for here, _dirs, names in os.walk(top):
        for n in names:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(here, n)).st_size
    return total


def read_lock(root) -> dict:
    """``libraries.lock`` as name -> entry; missing is empty, anything unreadable or misshapen is ``bad-lock``."""
    try:
        with open(os.path.join(root, LOCK), encoding="utf-8") as f:
            got = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise FetchError("bad-lock", LOCK, f"unreadable: {e}") from None
    if not isinstance(got, dict) or not all(isinstance(v, dict) for v in got.values()):
        raise FetchError("bad-lock", LOCK, "not a map of name to entry")
    return got


def write_lock(root, locks: dict) -> None:
    """Write ``libraries.lock`` whole, by a rename from a new file beside it."""
    fd, new = tempfile.mkstemp(prefix=".libraries.lock.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(locks, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(new, os.path.join(root, LOCK))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(new)
        raise
