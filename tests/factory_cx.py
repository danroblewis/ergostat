"""A small git repository and a complexity context on it, for the cx- families' tests (dev/bin/complexity.py)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
T0 = 1_787_904_000

FILES = {
    "ergostat/__init__.py": "",
    "ergostat/core.py": "# a comment\n\ndef add(a, b):\n    return a + b\n",
    "ergostat/web/page.py": "X = 1\n",
    "ergostat/web/static/main.js": "let a = 1;\n",
    "ergostat/web/static/elk.bundled.js": "var elk = 1;\nvar more = 2;\n",
    "dev/bin/tool.py": "def run():\n    return 0\n",
    "scripts/bench.py": "def bench():\n    return 0\n",
    "tests/test_s.py": "NAMES = ['run', 'bench']\n",
    "docs/x.md": "# Title\n\ntext\n",
}


def load(name: str):
    sys.path.insert(0, str(BIN))
    try:
        spec = importlib.util.spec_from_file_location(f"factory_{name}", BIN / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(BIN))


cx = load("complexity")
size = load("cx_size")


def git(repo: Path, *args: str, at: int | None = None) -> str:
    env = {**os.environ, **({"GIT_COMMITTER_DATE": f"{at} +0000", "GIT_AUTHOR_DATE": f"{at} +0000"} if at else {})}
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@localhost",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def family(**attrs) -> types.SimpleNamespace:
    """A family as a module would give it: only what it is given."""
    return types.SimpleNamespace(**attrs)


class Repo:
    """A git repository (main) of the fixture files and a run folder, with the families given (default: size)."""

    def __init__(self, tmp: Path, fams: dict | None = None):
        self.path, self.tmp = tmp / "repo", tmp
        self.path.mkdir(parents=True)
        git(self.path, "init", "-q", "-b", "main")
        self.shas: list[str] = []
        self.commit(FILES)
        self.ctx = cx.Ctx(self.path, tmp / "run" / "complexity", {"size": size} if fams is None else fams)

    def commit(self, files: dict[str, str]) -> str:
        for name, text in files.items():
            (self.path / name).parent.mkdir(parents=True, exist_ok=True)
            (self.path / name).write_text(text)
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "--allow-empty", "-m", f"c{len(self.shas)}", at=T0 + 3600 * len(self.shas))
        self.shas.append(git(self.path, "rev-parse", "HEAD"))
        return self.shas[-1]

    def config(self) -> dict[str, str]:
        """The environment and folder to run complexity.py in as the factory runs it."""
        conf = self.tmp / "factory.toml"
        conf.write_text(textwrap.dedent(f"""\
            [paths]
            checkout = "{self.path}"
            run = "{self.tmp / 'run'}"
            [git]
            base = "main"
            """))
        return {**os.environ, "FACTORY_CONFIG": str(conf)}

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(BIN / "complexity.py"), *args], capture_output=True, text=True,
                              env=self.config(), cwd=self.tmp, timeout=120)
