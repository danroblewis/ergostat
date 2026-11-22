"""Finding and reading templates: ergostat's own, and the owner's folders of their own.

A template file is YAML: ``template:`` (its name), ``description:``, ``reading:`` (what it is in control theory and
in system dynamics), ``params:`` (each with ``description``, ``type``, and ``default`` or ``stand-in`` or
``required``), ``example:`` (a ``uses:`` entry), and then the ordinary sections (``items:``, ``stocks:``, ``flows:``,
``auxiliaries:``, ``parameters:``, ``goals:``, ``blocks:``, ``systems:``, ``uses:``). ``exports:`` (optional) lists the
refs of its parts meant to be read from outside an instance (``stock.waiting``, or an inner use's ``stock.inner-x``);
absent, every part is exported."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..spec import files
from . import untrusted as ut

HERE = Path(__file__).resolve().parent / "templates"
ENV = "ERGOSTAT_LIBRARY"
BODY = ("items", "systems", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents", "workspaces", "actions",
        "uses")
HEAD = {"template", "description", "reading", "params", "example", "standins", "once", "exports"}
EXPORT = re.compile(r"^(stock|flow|goal|auxiliary|block)\.([a-z][a-z0-9-]*)$")      # what an exports: entry may name
EXPORT_SECTIONS = {"stock": "stocks", "flow": "flows", "goal": "goals", "auxiliary": "auxiliaries", "block": "blocks"}
TYPES = ("string", "number", "integer", "duration", "setpoint", "command", "url", "cron", "bool", "name", "names",
         "reference", "list", "strings", "map", "glob", "rung", "path", "any")
SAFE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")     # an untrusted template's name and its parameters' names


class TemplateError(Exception):
    pass


@dataclass
class Param:
    name: str
    type: str = "string"
    description: str = ""
    default: object = None
    standin: object = None              # what stands in, free and offline, when it is left out (said in a finding)
    required: bool = False
    has_default: bool = False
    choices: list | None = None
    min: float | None = None            # a number's least and most (an ExpandError names the bound)
    max: float | None = None


@dataclass
class Template:
    name: str
    path: Path
    builtin: bool
    description: str = ""
    reading: str = ""
    example: str = ""
    once: bool = False                  # used at most once a model; its parts keep the names written in it, unprefixed
    params: dict[str, Param] = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    trust: str = "untrusted"            # ergostat, owner or untrusted (SPEC §2a): anything not known counts as untrusted
    exports: list[str] | None = None    # the refs readable from outside an instance; None: every part

    @property
    def untrusted(self) -> bool:
        """Not ergostat's and not the owner's (``trust``, the one attribute): its text is marked, its parts bounded."""
        return not trusted(self)

    def summary(self) -> dict:
        return {"template": self.name, "description": self.description, **({"once": True} if self.once else {}),
                "from": "ergostat" if self.builtin else str(self.path), "trust": self.trust,
                **({"exports": list(self.exports)} if self.exports is not None else {}),
                "params": {n: {k: v for k, v in (("type", p.type), ("description", p.description),
                                                ("default", p.default if p.has_default else None),
                                                ("stand-in", p.standin), ("required", p.required or None),
                                                ("choices", p.choices), ("min", p.min), ("max", p.max))
                                     if v is not None}
                           for n, p in self.params.items()}}


class _Loader(yaml.SafeLoader):
    """YAML 1.2 booleans only (yes and no stay words), as the model's own files are read."""


_Loader.yaml_implicit_resolvers = {k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:bool"]
                                   for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", __import__("re").compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                              list("tTfF"))


def trusted(t: Template) -> bool:
    """Ergostat's own, or from a folder the owner wrote as a path or marked ``trust: owner``; nothing else is."""
    return getattr(t, "trust", None) in ("ergostat", "owner")


def read(path: Path, builtin: bool, trust: str = "untrusted") -> Template:
    try:
        data = yaml.load(files.read_text(path), Loader=_Loader)  # noqa: S506 (a SafeLoader subclass)
    except (OSError, yaml.YAMLError) as e:
        raise TemplateError(f"template {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("template"), str):
        raise TemplateError(f"template {path}: a map starting template: NAME")
    unknown = set(data) - HEAD - set(BODY)
    if unknown:
        raise TemplateError(f"template {path}: unknown section {sorted(unknown)[0]!r} (known: "
                            f"{', '.join(sorted(HEAD | set(BODY)))})")
    t = Template(data["template"], path, builtin, str(data.get("description") or "").strip(),
                 str(data.get("reading") or "").strip(), str(data.get("example") or "").strip(),
                 data.get("once") is True)
    for n, spec in (data.get("params") or {}).items():
        spec = spec if isinstance(spec, dict) else {"default": spec}
        ty = str(spec.get("type") or "string")
        if ty not in TYPES:
            raise TemplateError(f"template {t.name}: param {n}: type {ty!r} (known: {', '.join(TYPES)})")
        for k in ("min", "max"):
            if k in spec and ty == "duration":           # a duration's bounds: durations (1m, 1d), kept in hours
                from .expand import ExpandError, hours
                try:
                    spec = {**spec, k: hours(spec[k])}
                except ExpandError as e:
                    raise TemplateError(f"template {t.name}: param {n}: {k}: {e}") from None
            elif k in spec and (ty not in ("number", "integer") or isinstance(spec[k], bool)
                                or not isinstance(spec[k], int | float)):
                raise TemplateError(f"template {t.name}: param {n}: {k}: a number, on a number, integer or duration param")
        t.params[str(n)] = Param(str(n), ty, str(spec.get("description") or "").strip(), spec.get("default"),
                                 spec.get("stand-in"), bool(spec.get("required")), "default" in spec,
                                 spec.get("choices"), spec.get("min"), spec.get("max"))
    t.body = {k: data[k] for k in BODY if data.get(k) is not None}
    t.trust = "ergostat" if builtin else trust
    bad = [n for n in (t.name, *t.params) if not SAFE.match(n)] if t.untrusted else []
    if bad:
        raise TemplateError(f"template {path}: name {bad[0]!r} refused: an untrusted template's name and its parameters' "
                            f"names are lowercase letters, digits and -, starting with a letter, at most 64")
    if "exports" in data:
        t.exports = exports(t, data["exports"])
    return t


def exports(t: Template, given) -> list[str]:
    """``exports:``: each a ref to a part written in the template's own sections, or to an inner use's part by its
    template-local name (``stock.INNER-x``, which that use's template must export too, or it stays internal)."""
    if not isinstance(given, list):
        raise TemplateError(f"template {t.name}: exports: a list of its parts' refs (stock.x, goal.y)")
    inner = [str(k) for k in t.body.get("uses") or {}]
    for x in given:
        m = EXPORT.match(x) if isinstance(x, str) else None
        if m is None or (t.untrusted and not SAFE.match(m.group(2))):
            raise TemplateError(f"template {t.name}: exports: {x!r} is not a ref (stock.x, flow.x, goal.x, auxiliary.x, "
                                f"block.x; a name of lowercase letters, digits and -, at most 64)")
        if m.group(2) not in (t.body.get(EXPORT_SECTIONS[m.group(1)]) or {}) and \
                not any(m.group(2).startswith(u + "-") for u in inner):
            raise TemplateError(f"template {t.name}: exports: {x} is not a part it defines (none is written under "
                                f"{EXPORT_SECTIONS[m.group(1)]}:, and no use of it is named for its start)")
    return [str(x) for x in given]


def folders(extra: list[Path] | None = None) -> list[Path]:
    """The owner's folders first (``library:`` in the main file, then ``$ERGOSTAT_LIBRARY``), then ergostat's own."""
    out = list(extra or [])
    for x in (os.environ.get(ENV) or "").split(os.pathsep):
        if x.strip():
            out.append(Path(x.strip()).expanduser())
    return [*out, HERE]


def _forms(p) -> set[str]:
    return {os.path.normpath(os.path.abspath(p)), os.path.realpath(p)}


def within(f: Path, bad: set[Path]) -> Path | None:
    """The untrusted folder ``f`` lies under, or None."""
    fs = _forms(f)
    for b in sorted(bad, key=str):
        if any(x == y or x.startswith(y.rstrip(os.sep) + os.sep) for x in fs for y in _forms(b)):
            return b
    return None


def find_all(extra: list[Path] | None = None, untrusted: set[Path] | None = None) -> tuple[dict[str, Template], list[str]]:
    """Every template, by name: an owner's template shadows ergostat's own of the same name (said in the notes),
    and the first folder wins between the owner's own. A folder in ``untrusted`` is read after every trusted one, so its
    templates never shadow a trusted one, whatever the order (said, marked). Also what could not be read, and what was
    shadowed; a note from an untrusted folder has its library text marked. A file under any untrusted folder is
    untrusted, even when a trusted folder (its parent) also reaches it."""
    got: dict[str, Template] = {}
    notes: list[str] = []
    bad = {d for d in untrusted or () if d != HERE}
    order = folders(extra)
    for d in [x for x in order if x not in bad] + [x for x in order if x in bad]:
        if not files.is_dir(d):
            if d != HERE:
                notes.append(f"{'untrusted ' if d in bad else ''}library folder {ut.escape(d) if d in bad else d} does not exist")
            continue
        for f in sorted([*files.glob(d, "*.yaml"), *files.glob(d, "*.yml"), *files.glob(d, "*/template.yaml")]):
            # Trust is the file's own: under any untrusted folder (as written or with links followed), it is untrusted,
            # whichever folder reached it; a trusted folder leaves it to the untrusted pass.
            owner = None if d == HERE else within(f, bad)
            if owner is not None and d not in bad:
                continue
            try:
                t = read(f, d == HERE, "owner" if owner is None else "untrusted")
            except TemplateError as e:
                notes.append(ut.note(owner, str(e)) if owner is not None else str(e))
                continue
            was = got.get(t.name)
            if was is not None and trusted(was) != trusted(t):          # the trusted one, whichever came first
                kept, skipped = (was, t) if trusted(was) else (t, was)
                said = (f"template {t.name}: {skipped.path} (from a folder not marked trusted) is not used; "
                        f"{"ergostat's own" if kept.builtin else kept.path} is")
                notes.append(ut.note(within(skipped.path, bad) or "", said))
                got[t.name] = kept
                continue
            if t.name in got:
                if t.builtin and not got[t.name].builtin:
                    notes.append(f"template {t.name}: {got[t.name].path} is used in place of ergostat's own")
                continue
            got[t.name] = t
    return got, notes
