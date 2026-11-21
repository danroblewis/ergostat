"""Reading a file's ``uses:`` (SPEC §2a): each entry expanded by its template into ordinary parts, put in the
model as if they had been written, each pointing at the entry's ``use:`` line."""

from __future__ import annotations

from ..spec.ir import NAME
from ..spec.load import SECTIONS, Map, Problem, Where
from . import templates as tp
from . import trust
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
        got, notes = tp.find_all(doc.library, getattr(doc, "untrusted", ()))
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


class Chain:
    """An owner's ``use:`` and every use under it, expanded whole before anything of it is put (SPEC §2a)."""

    def __init__(self):
        self.steps: list[tuple] = []      # in order: (put, section, name, entry, via), (problem, p), (use, inst, record), (soft, key)
        self.checks: list[tuple] = []     # what was made under an untrusted template: (that template, section, name, entry)
        self.names: list[tuple] = []      # the uses this chain marked defined


def one(doc, inst: str, entry, w: Where | None, defaults: dict, put, depth: int, within: str | None) -> None:
    """One owner's entry: its whole chain planned; held and making anything trust.py refuses, none of it is put."""
    chain = Chain()
    plan(doc, chain, inst, entry, w, defaults, depth, within, None)
    for u, section, name, made in chain.checks:
        path = trust.refused(section, name, made)
        if path is None:
            continue
        for key in chain.names[1:]:
            doc.defined.pop(key, None)
        at = entry.at("use") if hasattr(entry, "at") else w
        doc.problems.append(Problem(
            "error", f"use {inst}: refused, and nothing of it is in the model: it makes {path}, under template {u.name} "
            f"from {u.path.parent}, a library folder not marked trusted, and a use of such a folder may make only "
            f"structure (SPEC §2a). Only the owner can mark a folder trusted, after reading it.", at, "library-untrusted",
            f"system.{inst}"))
        return
    for step in chain.steps:
        if step[0] == "put":
            put(*step[1:], {})
        elif step[0] == "problem":
            doc.problems.append(step[1])
        elif step[0] == "use":
            doc.uses[step[1]] = step[2]
        else:
            doc.soft.add(step[1])


def plan(doc, chain: Chain, inst: str, entry, w: Where | None, defaults: dict, depth: int, within: str | None,
         under: tp.Template | None) -> None:
    def err(msg, where=None, code="bad-use"):
        chain.steps.append(("problem", Problem("error", f"use {inst}: {msg}", where or w, code, f"system.{inst}")))

    if not NAME.match(inst):
        return err("an instance's name is lowercase letters, digits and -, starting with a letter", code="bad-name")
    if ("uses", inst) in doc.defined:
        return err(f"defined twice: here and at {doc.defined[('uses', inst)]}", code="defined-twice")
    doc.defined[("uses", inst)] = w
    chain.names.append(("uses", inst))
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
        uses = {**doc.uses, **{s[1]: s[2] for s in chain.steps if s[0] == "use"}}
        prior = next((n for n, u in uses.items() if u["template"] == t.name), None)
        if prior is not None:
            return err(f"{t.name} is used at most once a model (already as {prior}, at {uses[prior]['where']})", at,
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
    under = under or (None if tp.trusted(t) else t)          # from the first untrusted template down, all is checked
    if under is not None:
        chain.checks += [(under, "systems", inst, system),
                         *((under, s, n, x) for s, entries in made.sections.items() for n, x in entries.items())]
    if not (t.once and ("systems", inst) in doc.defined):     # a once template's system, when the model declares it, is the model's
        chain.steps.append(("put", "systems", inst, as_map(system, via), via))
        if t.once:
            chain.steps.append(("soft", ("systems", inst)))
    for section, entries in made.sections.items():
        if section == "uses":
            continue
        if section not in SECTIONS:
            err(f"template {t.name} writes {section}:, which is not a section", at, "bad-template")
            continue
        for name, got in entries.items():
            chain.steps.append(("put", section, name, as_map(got, via), via))
    chain.steps.append(("use", inst, {"template": t.name, "path": str(t.path), "owners": not t.builtin, "once": t.once,
                                      "values": made.values, "standins": made.standins, "where": via, "within": parent,
                                      "depth": depth, "trust": t.trust}))
    if made.standins:
        chain.steps.append(("problem", Problem("finding", f"use {inst}: runs on free stand-ins ({'; '.join(made.standins)}); "
                                               f"give them under with: to run it for real", via, "template-stand-in",
                                               f"system.{inst}")))
    for sub, e in (made.sections.get("uses") or {}).items():
        plan(doc, chain, sub, as_map(e, via), via, {}, depth + 1, inst, under)
