"""Reading a file's ``uses:`` (SPEC §2a): each entry expanded by its template into ordinary parts, put in the
model as if they had been written, each pointing at the entry's ``use:`` line."""

from __future__ import annotations

from ..spec.ir import NAME
from ..spec.load import SECTIONS, Map, Problem, Where
from . import templates as tp
from .expand import MAX_DEPTH, USE_KEYS, ExpandError, Via, expand


def as_map(x, where: Where):
    """Plain data as the loader's maps, every line the ``use:`` line."""
    if isinstance(x, dict):
        m = Map({k: as_map(v, where) for k, v in x.items()})
        m.where, m.lines = where, {k: where for k in x}
        return m
    if isinstance(x, list):
        return [as_map(v, where) for v in x]
    return x


def library(doc) -> dict[str, tp.Template]:
    got = getattr(doc, "_templates", None)
    if got is None:
        got, notes = tp.find_all(doc.library)
        doc._templates, doc._template_notes = got, notes
        for n in notes:
            doc.problems.append(Problem("finding", n, None, "template-library"))
    return got


def take(doc, data: Map, defaults: dict, put, depth: int = 0, within: str | None = None) -> None:
    body = data["uses"]
    if not isinstance(body, dict):
        doc.problems.append(Problem("error", "uses: a map, each entry an instance's name: its use: and with:",
                                    data.at("uses"), "not-a-map"))
        return
    for inst, entry in body.items():
        w = body.at(inst) if hasattr(body, "at") else data.at("uses")
        one(doc, str(inst), entry, w, defaults, put, depth, within)


def one(doc, inst: str, entry, w: Where | None, defaults: dict, put, depth: int, within: str | None) -> None:
    def err(msg, where=None, code="bad-use"):
        doc.problems.append(Problem("error", f"use {inst}: {msg}", where or w, code, f"system.{inst}"))

    if not NAME.match(inst):
        return err("an instance's name is lowercase letters, digits and -, starting with a letter", code="bad-name")
    if ("uses", inst) in doc.defined:
        return err(f"defined twice: here and at {doc.defined[('uses', inst)]}", code="defined-twice")
    doc.defined[("uses", inst)] = w
    if not isinstance(entry, dict) or not entry.get("use"):
        return err("give it use: TEMPLATE (and with: its parameters)", code="missing-key")
    at = entry.at("use") if hasattr(entry, "at") else w
    for k in entry:
        if k not in USE_KEYS:
            err(f"unknown key {k!r} (known: {', '.join(sorted(USE_KEYS))}; the template's parameters go under with:)",
                entry.at(k) if hasattr(entry, "at") else w, "unknown-key")
    lib = library(doc)
    t = lib.get(str(entry["use"]))
    if t is None:
        broken = [n for n in getattr(doc, "_template_notes", []) if f"{entry['use']}." in n or "/" + str(entry["use"]) in n]
        return err(f"no template {entry['use']!r} (there are: {', '.join(sorted(lib)) or 'none'}; the owner's own come "
                   f"from library: in the main file)" + (f"; {broken[0]}" if broken else ""), at, "unknown-template")
    if t.once:
        prior = next((n for n, u in doc.uses.items() if u["template"] == t.name), None)
        if prior is not None:
            return err(f"{t.name} is used at most once a model (already as {prior}, at {doc.uses[prior]['where']})", at,
                       "used-twice")
    given = entry.get("with") or {}
    if not isinstance(given, dict):
        return err("with: a map of the template's parameters", entry.at("with"), "not-a-map")
    if depth > MAX_DEPTH:
        return err(f"templates using templates more than {MAX_DEPTH} deep (does {t.name} use itself?)", at, "template-cycle")
    try:
        made = expand(t, inst, dict(given))
    except ExpandError as e:
        for msg, key in getattr(e, "all", [(str(e), e.key)]):
            err(msg, given.at(key) if key and hasattr(given, "at") else at, "bad-param")
        return
    via = Via(at.file if at else doc.root, at.line if at else 1, t.name, inst)
    parent = entry.get("within") or within or (None if t.once else defaults.get("system"))   # once a model: the model's
    parent = None if parent == inst else parent
    system = {**made.system, **({"description": str(entry["description"])} if entry.get("description") else {}),
              **({"within": str(parent)} if parent else {})}
    if not (t.once and ("systems", inst) in doc.defined):     # a once template's system, when the model declares it, is the model's
        put("systems", inst, as_map(system, via), via, {})
        if t.once:
            doc.soft.add(("systems", inst))
    for section, entries in made.sections.items():
        if section == "uses":
            continue
        if section not in SECTIONS:
            err(f"template {t.name} writes {section}:, which is not a section", at, "bad-template")
            continue
        for name, got in entries.items():
            put(section, name, as_map(got, via), via, {})
    doc.uses[inst] = {"template": t.name, "path": str(t.path), "owners": not t.builtin, "values": made.values,
                      "standins": made.standins, "where": via, "within": parent, "depth": depth}
    if made.standins:
        doc.problems.append(Problem("finding", f"use {inst}: runs on free stand-ins ({'; '.join(made.standins)}); "
                                    f"give them under with: to run it for real", via, "template-stand-in", f"system.{inst}"))
    for sub, e in (made.sections.get("uses") or {}).items():
        one(doc, sub, as_map(e, via), via, {}, put, depth + 1, inst)
