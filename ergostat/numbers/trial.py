"""A change to the model tried before it is written: the proposal's YAML edit applied in memory (never to
the file), the model compiled from that text, and replayed and projected on the same record as the model
as it is. What is simulated is exactly what Accept would write, so a structural change (a stock added, a
link taken away) is tried the same way as a parameter's value. Several proposals tried together are
their edits applied together; two that change the same lines conflict, and the later is left out."""

from __future__ import annotations

from pathlib import Path

from ..spec.compile import compile_doc
from ..spec.ir import Spec
from ..spec.load import load as load_doc
from ..spec.load import texts as override
from . import fit as ft
from . import observe as ob
from . import simulate as sim
from . import yamledit as ye


class TrialError(Exception):
    pass


def edits_of(x: dict) -> list[ye.Edit]:
    e = x.get("edit") or {}
    if "error" in e or not e.get("files"):
        raise TrialError(f"its edit cannot be made by ergostat ({e.get('error') or 'none'})")
    return [ye.Edit.from_dict(d) for d in e["files"]]


def texts_after(edits: list[ye.Edit]) -> dict[str, str]:
    try:
        return ye.apply_together(edits)
    except ye.EditError as err:
        raise TrialError(str(err)) from None


def compiled(main: Path, texts: dict[str, str], findings: bool = False) -> tuple[Spec, list]:
    """The model as it would be with these files' texts: its spec and its errors (and, with ``findings``,
    what ``check`` would find besides, as Accept checks it)."""
    with override(texts):
        doc = load_doc(main)
        spec, problems = compile_doc(doc)
        if findings and not any(p.level == "error" for p in problems):
            from ..spec.findings import find
            problems = problems + find(spec)
    return spec, [p for p in problems if p.level == "error"] if not findings else problems


def spec_after(p, edits: list[ye.Edit]) -> Spec:
    spec, errors = compiled(p.model.path, texts_after(edits))
    if errors:
        raise TrialError("the edit would leave the model with errors: " + "; ".join(str(e) for e in errors[:3]))
    return spec


def fit_of(spec: Spec, data: ob.Data) -> tuple[sim.Run, dict]:
    pl = sim.plan(spec)
    run = sim.replay(spec, data, pl)
    partial = sim.replay(spec, data, sim.plan(spec, integrate=set()))
    got = ft.compare(spec, data, run, partial)
    return run, {"total": ft._slim(got["total"]) if run.valid else None,
                 "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()},
                 "equations": {r: ft._slim(s) for r, s in got["partial"].items()},
                 "invalid": list(run.invalid)}


def combine(p, entries: list[dict]) -> tuple[list[dict], list[dict], list[ye.Edit]]:
    """Which of these proposals can be applied together, in order: the ones taken, the ones left out
    (with why: a conflict with one taken before, or an edit ergostat cannot make), and their edits."""
    taken, left, edits = [], [], []
    for x in entries:
        try:
            mine = edits_of(x)
        except TrialError as e:
            left.append({"id": x["id"], "why": str(e)})
            continue
        clash = next((y for y in taken if conflicts(x, y)), None)
        if clash is not None:
            left.append({"id": x["id"], "why": f"it conflicts with {clash['id']}, taken first"})
            continue
        try:
            ye.apply_together([*edits, *mine])
        except ye.EditError as e:
            left.append({"id": x["id"], "why": str(e)})
            continue
        taken.append(x)
        edits += mine
    return taken, left, edits


def conflicts(a: dict, b: dict) -> str | None:
    """Why two proposals cannot both be accepted as they are, or None: they change the same lines of a
    file, the same parameter, or the same part's equation."""
    if a["id"] == b["id"]:
        return None
    pa, pb = set(a.get("parameters") or {}), set(b.get("parameters") or {})
    if a.get("kind") == "parameter" and b.get("kind") == "parameter" and pa & pb:
        return f"both set {', '.join(sorted(pa & pb))}"
    if a.get("kind") == "equation" and b.get("kind") == "equation" and a.get("target") == b.get("target"):
        return f"both write {a['target']}'s equation"
    try:
        ea, eb = edits_of(a), edits_of(b)
    except TrialError:
        return None
    for x in ea:
        for y in eb:
            if x.file != y.file:
                continue
            for h in x.hunks:
                for k in y.hunks:
                    if ye.overlaps(h, k):
                        return f"both change {Path(x.file).name}:{min(h.line, k.line)}"
    return None
