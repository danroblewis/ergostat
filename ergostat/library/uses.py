"""Reading a file's ``uses:`` (SPEC §2a): each entry expanded by its template into ordinary parts, put in the
model as if they had been written, each pointing at the entry's ``use:`` line."""

from __future__ import annotations

from ..spec.ir import NAME
from ..spec.load import SECTIONS, Map, Problem, Where
from . import templates as tp
from . import trust
from .expand import LIBRARY, MAX_DEPTH, USE_KEYS, ExpandError, Via, author, expand
from .untrusted import FILE, LABEL, mark


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
        got, notes = tp.find_all(doc.library, getattr(doc, "untrusted", ()), getattr(doc, "fetched", ()))
        doc._templates, doc._template_notes = got, notes
        for n in notes:
            doc.problems.append(Problem("finding", n, None, "template-library"))
    return got


def exports(t: tp.Template, inst: str, made) -> dict:
    """What the compiler's exports check reads (SPEC §2a): the refs of the parts this instance made itself (a name
    given wholly by a parameter is the owner's, never internal), and, when its template declares ``exports:``, the
    refs it exports, as made."""
    full = (lambda n: n) if t.once else (lambda n: f"{inst}-{n}")
    every = {f"{k}.{n}": t.once or n.startswith(inst + "-") for k, s in tp.EXPORT_SECTIONS.items()
             for n in made.sections.get(s) or {}}
    parts = sorted(x for x, own in every.items() if own)
    named = sorted(x for x, own in every.items() if not own)   # inside the instance (refers inward freely), never internal
    if t.exports is None:
        return {"parts": parts, "named": named, "exports": None}
    return {"parts": parts, "named": named, "exports": list(t.exports),
            "exported": sorted(f"{x.split('.', 1)[0]}.{full(x.split('.', 1)[1])}" for x in t.exports)}


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
        self.checks: list[tuple] = []     # made under an untrusted template: (that template, its writer, section, name,
        #                                   entry with its marks)
        self.names: list[tuple] = []      # the uses this chain marked defined
        self.forged = None                # (template, what) when a held template or value holds a mark's characters


def one(doc, inst: str, entry, w: Where | None, defaults: dict, put, depth: int, within: str | None) -> None:
    """One owner's entry: its whole chain planned; held and making anything trust.py refuses, none of it is put."""
    chain = Chain()
    plan(doc, chain, inst, entry, w, defaults, depth, within, None)
    held = {(s, n) for _, _, _, s, n, _ in chain.checks}
    for u, tw, tt, section, name, made in [*([chain.forged] if chain.forged else []), *chain.checks]:
        path = trust.refused(section, name, made, held, tw, tt) if section else name
        if path is None:
            continue
        for key in chain.names[1:]:
            doc.defined.pop(key, None)
        at = entry.at("use") if hasattr(entry, "at") else w
        text = isinstance(path, trust.Text)
        said = f"{path}, under template {u.name} from {u.path.parent}"          # its key, name and folder: the library's
        said = "".join(ch if ch.isprintable() else repr(ch)[1:-1] for ch in said)  # a newline written \n
        why = ("its ask, prompt, query and sources may hold only text the owner or a trusted template wrote, and this "
               "holds text the library wrote (R3)" if text else "a use of such a folder may make only structure, and "
               "run only the owner's own commands and ergostat's programs with checked arguments")
        lib = getattr(u, "library", None)
        src, fix = ((f"from the fetched library {lib}, not marked trust: owner in libraries:", "mark it trust: owner")
                    if lib else ("a library folder not marked trusted", "mark a folder trusted"))
        doc.problems.append(Problem(
            "error", f"use {inst}: refused, and nothing of it is in the model: it makes {mark(said, FILE)}, {src}, "
            f"and {why} (SPEC §2a). Only the owner can {fix}, after reading it.",
            at, "untrusted-text" if text else "library-unsandboxed" if path.endswith(".daemon") else "library-untrusted",
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
         under: tp.Template | None, writers: dict | None = None, above: str | None = None) -> None:
    """One instance of the chain; ``under``: the first untrusted template above it (or it), from which all is untrusted.
    ``writers``: who wrote each value of this entry's ``with:`` (None: the owner, at depth 0; SPEC §2a); ``above``: the
    instance whose template uses this one."""
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
        broken += [f"library {n} refused: {code}, {why}" for n, (code, why) in getattr(doc, "refused", {}).items()]
        return err(f"no template {entry['use']!r} (there are: {', '.join(sorted(lib)) or 'none'}; the owner's own come "
                   f"from library: in the main file)" + "".join(f"; {b}" for b in broken), at, "unknown-template")
    if t.once:
        uses = {**doc.uses, **{s[1]: s[2] for s in chain.steps if s[0] == "use"}}
        prior = next((n for n, u in uses.items() if u["template"] == t.name), None)
        if prior is not None:
            return err(f"{t.name} is used at most once a model (already as {prior}, at {uses[prior]['where']})", at,
                       "used-twice")
    under = under or (None if tp.trusted(t) else t)          # from the first untrusted template down, all is checked
    untrusted = under is not None                            # its own template, or any instance it sits inside
    label = LABEL.format(t.name) if tp.SAFE.match(t.name) else FILE     # (a label is never library text)
    said = (lambda x: mark(x, label)) if untrusted else str
    given = entry.get("with") or {}
    if not isinstance(given, dict):
        return err("with: a map of the template's parameters", entry.at("with"), "not-a-map")
    if depth > MAX_DEPTH:
        return err(f"templates using templates more than {MAX_DEPTH} deep (does {t.name} use itself?)", at, "template-cycle")
    try:
        made = expand(t, inst, dict(given), writers)
    except ExpandError as e:
        if getattr(e, "forged", False) and (under or not tp.trusted(t)):
            chain.forged = (under or t, None, None, None, "a text holding a control character only ergostat's marks use", None)
            return
        for msg, key in getattr(e, "all", [(str(e), e.key)]):
            err(said(msg), given.at(key) if key and hasattr(given, "at") else at, "bad-param")
        return
    via = Via(at.file if at else doc.root, at.line if at else 1, t.name, inst)
    parent = entry.get("within") or within or (None if t.once else defaults.get("system"))   # once a model: the model's
    parent = None if parent == inst else parent
    system = {**made.system, **({"description": str(entry["description"])} if entry.get("description") else {}),
              **({"within": str(parent)} if parent else {})}
    if under is not None:
        tw = author(t)
        named = trust.named(t)                                # its text may hold the instance's name: the library's
        tt = LIBRARY if trust.blind(t) else trust.NAMED if named else tw    # its own text may hold a value unmarked
        chain.checks += [(under, tw, tt, "systems", inst, system),
                         *((under, tw, tt, s, n, x) for s, entries in made.marked.items() for n, x in entries.items()),
                         *((under, tw, tt, "uses", n, x) for n, x in made.sections.get("uses", {}).items())]
    if not (t.once and ("systems", inst) in doc.defined):     # a once template's system, when the model declares it, is the model's
        chain.steps.append(("put", "systems", inst, as_map(system, via), via))
        if t.once:
            chain.steps.append(("soft", ("systems", inst)))
    for section, entries in made.sections.items():
        if section == "uses":
            continue
        if section not in SECTIONS:
            err(said(f"template {t.name} writes {section}:, which is not a section"), at, "bad-template")
            continue
        for name, got in entries.items():
            chain.steps.append(("put", section, name, as_map(got, via), via))
    chain.steps.append(("use", inst, {"template": t.name, "path": str(t.path), "owners": not t.builtin, "once": t.once,
                                      "values": made.values, "standins": made.standins, "where": via, "within": parent,
                                      "depth": depth, "trust": t.trust, "untrusted": untrusted, "outer": within,
                                      "above": above,
                                      "owner_runs": trust.owner_runs(made.marked or {}, author(t)) if untrusted else [],
                                      "library": t.library, **exports(t, inst, made)}))
    if made.standins:
        chain.steps.append(("problem", Problem("finding", f"use {inst}: runs on free stand-ins "
                                               f"({said('; '.join(made.standins))}); give them under with: to run it for "
                                               f"real", via, "template-stand-in", f"system.{inst}")))
    start = len(chain.steps)
    for sub, e in (made.sections.get("uses") or {}).items():
        given_on = made.writers.get(sub, {})
        if under is not None and named:                     # what it gives may hold the name: only the owner's known
            given_on = {k: w if w in trust.fine(trust.NAMED) else LIBRARY for k, w in given_on.items()}
        plan(doc, chain, sub, as_map(e, via), via, {}, depth + 1, inst, under, given_on, inst)
    unmade(t, inst, chain, start, at, said)


def unmade(t: tp.Template, inst: str, chain: Chain, start: int, at, said) -> None:
    """An ``exports:`` entry naming an inner use's part the expansion did not make (a typo, a wrong kind) is
    bad-template naming the entry (SPEC §2a); entries for its own sections' parts were checked when it was read."""
    rec = next((s[2] for s in chain.steps[:start] if s[0] == "use" and s[1] == inst), None)
    if rec is None or rec.get("exports") is None:
        return
    made = set(rec["parts"]).union(*(s[2].get("parts") or () for s in chain.steps[start:] if s[0] == "use"))
    own = {f"{k}.{n}" for k, sec in tp.EXPORT_SECTIONS.items() for n in t.body.get(sec) or {}}
    for x in rec["exports"]:
        kind, name = x.split(".", 1)
        if x not in own and (x if t.once else f"{kind}.{inst}-{name}") not in made:
            chain.steps.append(("problem", Problem("error", f"use {inst}: " + said(
                f"template {t.name} exports: {x}, which is not a part it or any of its uses makes"), at,
                "bad-template", f"system.{inst}")))
