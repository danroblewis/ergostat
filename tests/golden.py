"""Golden files: a page's rendered structure saved as a reference text file, which a test compares against.

A test renders a page, reads it into text with ``STRUCTURE`` (one line per element, indented: its tag and classes,
an allowlist of attributes, where a Dashboard cell sits on the grid, and its own words; a hidden element is one line
with no children) and calls ``compare(name, text)``. The reference is ``tests/golden/<name>.txt``: a change to it
shows in review as an ordinary line diff, and a failing test prints that diff.

An intended change regenerates every reference by a command, never by editing assertions:

    uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m tests.golden

which runs the golden tests with ``ERGOSTAT_GOLDEN=update`` (each writes what it drew) and says which references
changed; read ``git diff tests/golden`` and commit it. A reference that is missing is written and its test fails,
so a run never passes on nothing to compare with.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
ENV = "ERGOSTAT_GOLDEN"
TESTS = ["tests/test_golden_pages.py"]          # the files whose tests compare against a reference
COMMAND = "uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m tests.golden"

# the page's structure as text: the attributes are an allowlist, so a style, a size or a generated id never enters
STRUCTURE = """(selector) => {
  const KEEP = ["data-panel", "data-panel-id", "data-state", "data-act", "role", "aria-label", "aria-expanded",
                "aria-hidden", "title", "href", "type", "tabindex"];
  const AT = ["--x", "--y", "--w", "--h"];
  const lines = [];
  const words = (el) => [...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE)
    .map((n) => n.textContent.replace(/\\s+/g, " ").trim()).filter(Boolean).join(" ");
  const walk = (el, depth) => {
    const tag = el.tagName.toLowerCase();
    if (tag === "script" || tag === "style") return;
    const hidden = el.hidden || getComputedStyle(el).display === "none";
    const at = AT.map((v) => el.style.getPropertyValue(v).trim());
    const said = [tag + [...el.classList].sort().map((c) => `.${c}`).join("")];
    if (at.every(Boolean)) said.push(`at=${at[0]},${at[1]} size=${at[2]}x${at[3]}`);
    for (const a of KEEP) if (el.hasAttribute(a)) said.push(`${a}=${JSON.stringify(el.getAttribute(a))}`);
    if (hidden) said.push("(hidden)");
    const text = words(el);
    if (text) said.push(JSON.stringify(text));
    lines.push("  ".repeat(depth) + said.join(" "));
    if (!hidden) for (const c of el.children) walk(c, depth + 1);
  };
  const roots = [...document.querySelectorAll(selector)];
  if (!roots.length) return null;
  roots.forEach((r) => walk(r, 0));        // each root at column 0: the line git and diff() name a hunk by
  return lines.join("\\n");
}"""


def updating() -> bool:
    return os.environ.get(ENV) == "update"


def reference(name: str) -> Path:
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError(f"a golden file's name is letters, digits, - and _: {name!r}")
    return GOLDEN / f"{name}.txt"


def diff(saved: str, now: str, name: str) -> str:
    """The unified diff of a reference against what was drawn, each hunk headed by the root it is in (the nearest
    line above it at column 0, as git's default hunk header names it), so a change says which panel it is in."""
    old = saved.splitlines(keepends=True)
    out = []
    for line in difflib.unified_diff(old, now.splitlines(keepends=True),
                                     fromfile=f"tests/golden/{name}.txt (saved)", tofile=f"{name} (drawn now)"):
        if line.startswith("@@ -"):
            start = int(line[4:].split(",")[0].split(" ")[0])
            above = [x for x in old[:max(start - 1, 0)] if x[:1] not in ("", " ", "\n")]
            line = line.rstrip("\n") + (f" {above[-1].strip()}" if above else "") + "\n"
        out.append(line)
    return "".join(out)


def compare(name: str, text: str | None) -> None:
    """Fail unless ``text`` is the saved reference ``name``; under ``ERGOSTAT_GOLDEN=update``, write it instead."""
    import pytest

    if not text or not text.strip():
        pytest.fail(f"{name}: nothing was drawn to compare (the page's structure read as empty)")
    path, now = reference(name), text.rstrip("\n") + "\n"
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(now, encoding="utf-8")
        return
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(now, encoding="utf-8")
        pytest.fail(f"tests/golden/{name}.txt had no reference: written now from this run; read it, commit it and run again")
    saved = path.read_text(encoding="utf-8")
    if saved != now:
        pytest.fail(f"{name} is drawn differently from its reference:\n{diff(saved, now, name)}\n"
                    f"If the change is intended, regenerate the references with `{COMMAND}` and commit the diff.",
                    pytrace=False)


def contents() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(GOLDEN.glob("*.txt"))} if GOLDEN.is_dir() else {}


def regenerate(tests: list[str] | None = None, run=subprocess.run) -> int:
    """Run the golden tests in update mode, serially, and say which references changed. Returns pytest's code."""
    before = contents()
    rc = run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:xdist", "-o", "addopts=", *(tests or TESTS)],
             cwd=ROOT, env={**os.environ, ENV: "update"}).returncode
    after = contents()
    changed = sorted(n for n in after if before.get(n) != after[n])
    for n in changed:
        print(f"{'new' if n not in before else 'changed'}: tests/golden/{n}")
    print(f"{len(changed)} of {len(after)} references changed" + ("; read `git diff tests/golden` and commit it" if changed else ""))
    if rc:
        print(f"the golden tests ended with code {rc}: a reference they did not reach is not regenerated", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(regenerate(sys.argv[1:] or None))
