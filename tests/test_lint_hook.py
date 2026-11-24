"""Lint is fixed by a pre-commit hook and never tested or reviewed (dev/records/lint-in-a-pre-commit-hook.md): a build
session's clone formats and fixes its staged Python files before each commit, the merge queue and the implementor's
fast suites run no ruff, and the reviewer is told lint and style are out of scope."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.test_factory import ROOT, Factory, approved_gaps, merges, module, ready

FACTORY = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())

BAD = "import os\nimport sys\nx=[1,2 ,3]\ndef f( a ):\n    return a+1\nprint( sys.argv,x , f(1))\n"
GOOD = "import sys\n\nx = [1, 2, 3]\n\n\ndef f(a):\n    return a + 1\n\n\nprint(sys.argv, x, f(1))\n"


def agents():
    sys.modules.setdefault("fac", module("fac"))
    return module("agents")


def git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120, env=env)


def repo_with_hook(tmp: Path, cfg: dict) -> tuple[Path, dict]:
    """A clone-like repository with ergostat's ruff settings (its pyproject.toml), the hook written by
    agents.precommit from ``cfg``; the environment a session commits in (uv on the running venv, never a sync)."""
    work = tmp / "work"
    work.mkdir()
    shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": sys.prefix, "UV_NO_SYNC": "1", "RUFF_CACHE_DIR": str(tmp / "ruff"),
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com"}
    assert git(work, "init", "-q", "-b", "main").returncode == 0
    assert git(work, "add", "pyproject.toml").returncode == 0
    assert git(work, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "start", env=env).returncode == 0
    agents().precommit(cfg, work)
    return work, env


def test_a_commit_with_fixable_lint_lands_formatted(tmp_path):
    """Done 1: with the factory's own [suites] precommit, a commit of badly formatted Python with fixable lint (an unused
    import) lands formatted and fixed; a file with lint ruff cannot fix is committed anyway, never refused."""
    assert FACTORY["suites"]["precommit"].strip()
    work, env = repo_with_hook(tmp_path, FACTORY)
    assert os.access(work / ".git" / "hooks" / "pre-commit", os.X_OK)
    (work / "bad.py").write_text(BAD)
    (work / "notes.txt").write_text("x=[1,2 ,3]\n")                     # (not Python: committed as written)
    assert git(work, "add", "bad.py", "notes.txt").returncode == 0
    r = git(work, "commit", "-q", "-m", "lint", env=env)
    assert r.returncode == 0, r.stderr
    assert git(work, "show", "HEAD:bad.py").stdout == GOOD, r.stderr
    assert git(work, "show", "HEAD:notes.txt").stdout == "x=[1,2 ,3]\n"
    assert not git(work, "status", "--porcelain").stdout                # (the fix is what was committed, nothing left)
    (work / "worse.py").write_text("print( undefined_name )\n")          # F821: no fix exists
    assert git(work, "add", "worse.py").returncode == 0
    r = git(work, "commit", "-q", "-m", "unfixable", env=env)
    assert r.returncode == 0, r.stderr
    assert git(work, "show", "HEAD:worse.py").stdout == "print(undefined_name)\n"


def test_a_conflicted_merge_the_session_commits_leaves_mains_files_as_main_had_them(tmp_path):
    """The factory's merge of main conflicts and the session finishes it with `git commit --no-edit`: the hook skips that
    commit, so a Python file only main changed (badly formatted there) lands as main had it, not reformatted into the
    gap's diff; the session's next commit is formatted again."""
    work, env = repo_with_hook(tmp_path, FACTORY)
    off = ("-c", "core.hooksPath=/dev/null")                            # (main's own commits, made without the hook)
    (work / "both.txt").write_text("base\n")
    (work / "mains.py").write_text("x=1\n")
    assert git(work, "add", "both.txt", "mains.py").returncode == 0
    assert git(work, *off, "commit", "-q", "-m", "base", env=env).returncode == 0
    assert git(work, "checkout", "-q", "-b", "gap").returncode == 0
    (work / "both.txt").write_text("gap\n")
    assert git(work, *off, "commit", "-q", "-am", "gap", env=env).returncode == 0
    assert git(work, "checkout", "-q", "main").returncode == 0
    (work / "both.txt").write_text("main\n")
    (work / "mains.py").write_text(BAD)
    assert git(work, *off, "commit", "-q", "-am", "main", env=env).returncode == 0
    assert git(work, "checkout", "-q", "gap").returncode == 0
    assert git(work, "merge", "-q", "--no-edit", "main", env=env).returncode != 0      # (the conflict, left in progress)
    (work / "both.txt").write_text("resolved\n")
    assert git(work, "add", "both.txt").returncode == 0
    r = git(work, "commit", "--no-edit", env=env)
    assert r.returncode == 0, r.stderr
    assert git(work, "show", "HEAD:mains.py").stdout == BAD
    assert not git(work, "diff", "--name-only", "main", "HEAD", "--", "mains.py").stdout
    (work / "own.py").write_text(BAD)
    assert git(work, "add", "own.py").returncode == 0
    assert git(work, "commit", "-q", "-m", "own", env=env).returncode == 0
    assert git(work, "show", "HEAD:own.py").stdout == GOOD


def test_no_precommit_setting_writes_no_hook(tmp_path):
    for i, cfg in enumerate(({"suites": {}}, {"suites": {"precommit": "  "}}, {})):
        work = tmp_path / str(i)
        work.mkdir()
        assert git(work, "init", "-q").returncode == 0
        assert agents().precommit(cfg, work) is None
        assert not (work / ".git" / "hooks" / "pre-commit").exists()


def test_a_failing_precommit_command_never_refuses_the_commit(tmp_path):
    work, env = repo_with_hook(tmp_path, {"suites": {"precommit": "exit 3"}})
    (work / "a.py").write_text("x=1\n")
    assert git(work, "add", "a.py").returncode == 0
    r = git(work, "commit", "-q", "-m", "a", env=env)
    assert r.returncode == 0 and git(work, "show", "HEAD:a.py").stdout == "x=1\n"
    assert "[suites] precommit failed" in r.stderr


def test_the_factory_runs_no_lint_gate(monkeypatch):
    """Done 2, as configured: the factory's own settings turn the lint step off for the queue and the implementor; set
    again, it comes back."""
    assert not FACTORY["suites"]["ruff"].strip()
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    monkeypatch.setattr(sys, "path", [*sys.path, str(ROOT / "dev" / "bin")])   # (appended: never shadowing queue)
    onmain, queue = module("onmain"), module("queue")
    assert onmain.fast(FACTORY) == ("build",) and not queue.lint_on(FACTORY)
    on = {**FACTORY, "suites": {**FACTORY["suites"], "ruff": "uv run ruff check ."}}
    assert onmain.fast(on) == ("ruff", "build") and queue.lint_on(on)


def lintless(tmp_path: Path) -> tuple[Factory, Path]:
    """A factory whose suites each log their name to ``ran``, its ruff step failing were it run, then turned off."""
    ran = tmp_path / "ran"
    f = Factory(tmp_path / "f", unit=f"echo unit >> {ran}")
    text = f.config.read_text()
    for n in ("browser", "browser_ready", "demo"):
        text = text.replace(f'\n{n} = "true"', f'\n{n} = "echo {n} >> {ran}"')
    f.config.write_text(text.replace('\nruff = "true"', '\nruff = ""'))
    return f, ran


@pytest.mark.slow
def test_a_batch_with_lint_is_never_red_for_it(tmp_path):
    """Done 2: a batch whose gap adds Python with lint lands; the queue ran unit, browser and demo, never ruff."""
    f, ran = lintless(tmp_path)
    approved_gaps(f, {"q": 1}, edits={"q": "lint.py"})
    said, _ = f.run("queue.py", "gap/q")
    assert "gap.merged" in said and merges(f) == ["q"], said
    assert sorted(ran.read_text().split()) == ["browser", "demo", "unit"]
    ran_by = f.item("gap/q")["fields"]["suites_queue"]
    assert "ruff" not in ran_by and {"unit", "browser", "demo"} <= set(ran_by), ran_by


@pytest.mark.slow
def test_an_implementor_round_runs_no_ruff_and_its_clone_has_the_hook(tmp_path):
    f, ran = lintless(tmp_path)
    f.config.write_text(f.config.read_text().replace("[suites]\n", "[suites]\nprecommit = 'echo hooked \"$@\"'\n"))
    gid = ready(f)
    said, _ = f.run("implement.py", gid)
    assert "gap.built" in said and ran.read_text().split() == ["unit"]
    assert set(f.item(gid)["fields"]["suites_fast"]) == {"unit"}
    hooks = list((f.tmp / "live" / "sessions").glob("*-implementor-*/work/.git/hooks/pre-commit"))
    assert len(hooks) == 1 and "echo hooked" in hooks[0].read_text() and os.access(hooks[0], os.X_OK)


def test_the_reviewer_and_the_builders_are_told_lint_is_out_of_scope():
    """Done 3: the reviewer prompt puts lint and style out of scope; no build prompt or house rule asks for ruff."""
    reviewer = (ROOT / "dev" / "prompts" / "reviewer.md").read_text()
    assert "Lint and style are out of scope" in reviewer
    for p in ("dev/prompts/implementor.md", "dev/prompts/simplify.md", "dev/knowledge/house-rules.md"):
        text = (ROOT / p).read_text()
        assert "ruff is clean" not in text and "ruff check ergostat tests scripts` must be clean" not in text, p
        assert "ruff check ergostat tests scripts` clean" not in text, p
