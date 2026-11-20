"""The briefs: what an implementor's or a reviewer's session is given, assembled from a template in dev/prompts/ and
the gap (its definition, its GAPS entry, the guides it names, the findings of its earlier reviews, the diff for a
reviewer), and the record of what went in, so the model can learn which context drives first-pass yield.

A reviewer is never given the implementor's reasoning: no session text, no transcript, only the work itself."""

from __future__ import annotations

import re
from pathlib import Path

import fac

ALWAYS = {"implementor": ["CLAUDE.md", "NOTES.md"], "reviewer": ["CLAUDE.md", "NOTES.md"]}
DOC = re.compile(r"\b((?:docs|examples|scripts|tests|ergostat)/[\w./-]+\.(?:md|py|yaml))\b")
DIFF_MOST = 60_000           # characters of the diff a reviewer is given whole; past it, the stat and the files


def definition_text(cfg: dict, where: str, worktree: Path | None = None) -> str:
    """A definition's text: a file, a REF:PATH in the checkout, or the text itself."""
    repo = fac.path(cfg, "checkout")
    if worktree and (worktree / where).is_file():
        return (worktree / where).read_text()
    if Path(where).is_file():
        return Path(where).read_text()
    if re.match(r"^[\w./-]+:[\w./-]+\.md$", where) and fac.git_ok(repo, "cat-file", "-e", where):
        return fac.git(repo, "show", where)
    return where


def gaps_entry(cfg: dict, title: str) -> str:
    """The gap's whole entry in GAPS.md on main (the bullet and what is indented under it)."""
    if not title:
        return ""
    text = fac.git(fac.path(cfg, "checkout"), "show", f"{cfg['git']['base']}:docs/GAPS.md", check=False)
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        if line.startswith(f"- **{title}"):
            out.append(line)
            for nxt in lines[i + 1:]:
                if nxt.startswith(("- ", "#")) or not nxt.strip():
                    break
                out.append(nxt)
            break
    return "\n".join(out)


def findings_text(findings: list) -> str:
    if not findings:
        return "(none: this is the first round)"
    return "\n".join(f"- {f}" for f in findings)


def assemble(cfg: dict, role: str, gap: dict, worktree: Path, **extra) -> tuple[str, dict]:
    """(the brief, what it was made of)."""
    f = gap["fields"]
    template = fac.HERE / "prompts" / f"{role}.md"
    definition = extra.pop("definition", None) or definition_text(cfg, str(f.get("definition", "")), worktree)
    entry = gaps_entry(cfg, f.get("title", ""))
    named = sorted({m for m in DOC.findall(definition + "\n" + entry) if (worktree / m).exists()})
    guides = ALWAYS[role] + [g for g in named if g not in ALWAYS[role]]
    findings = list(f.get("findings") or [])
    values = {
        "gap": gap["id"], "title": f.get("title", gap["id"]), "branch": fac.branch_of(gap), "worktree": str(worktree),
        "base": cfg["git"]["base"], "definition": definition.strip(), "gaps_entry": entry or "(not in GAPS.md)",
        "guides": "\n".join(f"- {g}" for g in guides), "findings": findings_text(findings),
        "definition_path": f"{fac.DEFS}/{fac.branch_of(gap)}.md", "budget": str(fac.budget_of(definition)),
        "round": str(int(f.get("rounds") or 0) + 1), **{k: str(v) for k, v in extra.items()},
    }
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template.read_text())
    context = {"role": role, "template": f"dev/prompts/{role}.md", "guides": guides, "files": named,
               "findings": len(findings), "definition_chars": len(definition), "gaps_entry": bool(entry),
               "brief_chars": len(text), "brief_tokens": len(text) // 4,
               "diff_chars": len(extra.get("diff", "")), "model": cfg["ai"][f"{role}_model"]}
    return text, context


def save(cfg: dict, role: str, gap: dict, text: str) -> str:
    """Kept in the instance's run/ folder (never in git): a file field of the item."""
    d = fac.run_dir(cfg, "briefs")
    n = len(list(d.glob(f"{fac.branch_of(gap)}-{role}-*.md"))) + 1
    p = d / f"{fac.branch_of(gap)}-{role}-{n}.md"
    p.write_text(text)
    try:
        return f"file:{p.relative_to(fac.MODEL)}"
    except ValueError:
        return str(p)
