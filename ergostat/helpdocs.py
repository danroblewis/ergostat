"""The guides shipped with ergostat, by name, for ``ergostat help NAME`` and the MCP tools: the
guides in ``help/``, the format (``spec``, docs/SPEC.md), the guidelines for improving a model
(``modelling``, docs/MODELLING.md), and the skills for AI agents (``skills/NAME/SKILL.md``). An
installed ergostat has the two documents copied into ``help/``; a clone reads them from ``docs/``."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = {"spec": "SPEC.md", "modelling": "MODELLING.md"}      # a guide that is a document in docs/


def guides() -> dict[str, Path]:
    out = {p.stem: p for p in sorted((HERE / "help").glob("*.md")) if p.stem not in DOCS}
    for name, doc in DOCS.items():
        here = HERE / "help" / f"{name}.md"
        out[name] = here if here.is_file() else HERE.parent / "docs" / doc
    for p in sorted((HERE / "skills").glob("*/SKILL.md")):
        out[p.parent.name] = p
    return dict(sorted(out.items()))


def read(name: str) -> str | None:
    p = guides().get(name)
    return p.read_text(encoding="utf-8") if p is not None and p.is_file() else None
