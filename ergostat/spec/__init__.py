"""The YAML model (docs/SPEC.md): read, compile, check, and turn into the objects the rest of
ergostat draws and records with."""

from __future__ import annotations

from pathlib import Path

from .compile import compile_doc
from .ir import Spec
from .load import FILE, Problem, SpecError, find
from .load import load as load_doc


def read(path: Path, extremes: bool = True) -> tuple[Spec, list[Problem]]:
    """The compiled model and every problem: errors (it must not run) and findings; ``extremes=False``
    without the extreme-conditions findings (``findings.late``), which are never errors."""
    from .findings import find as findings
    doc = load_doc(path)
    spec, problems = compile_doc(doc)
    if not any(p.level == "error" for p in problems):
        from ..promnames import names_for
        problems += names_for(spec).problems()        # two parts' PromQL names that cannot be kept apart: refused
    if not any(p.level == "error" for p in problems):
        from .routes import problems as addresses
        problems += addresses(spec)                   # shadowed names (findings), things with no address (errors)
    if not any(p.level == "error" for p in problems):
        problems += findings(spec, extremes)
    return spec, problems


def load(path: Path) -> Spec:
    """The compiled model, or SpecError listing every error."""
    spec, problems = read(path, extremes=False)
    errors = [p for p in problems if p.level == "error"]
    if errors:
        raise SpecError(errors)
    return spec


__all__ = ["FILE", "Problem", "Spec", "SpecError", "find", "load", "read"]
