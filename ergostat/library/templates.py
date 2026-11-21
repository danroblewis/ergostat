"""Finding and reading templates: ergostat's own, and the owner's folders of their own.

A template file is YAML: ``template:`` (its name), ``description:``, ``reading:`` (what it is in control theory and
in system dynamics), ``params:`` (each with ``description``, ``type``, and ``default`` or ``stand-in`` or
``required``), ``example:`` (a ``uses:`` entry), and then the ordinary sections (``items:``, ``stocks:``, ``flows:``,
``auxiliaries:``, ``parameters:``, ``goals:``, ``blocks:``, ``systems:``, ``uses:``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..spec import files

HERE = Path(__file__).resolve().parent / "templates"
ENV = "ERGOSTAT_LIBRARY"
BODY = ("items", "systems", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents", "workspaces", "actions",
        "uses")
HEAD = {"template", "description", "reading", "params", "example", "standins", "once"}
TYPES = ("string", "number", "integer", "duration", "setpoint", "command", "url", "cron", "bool", "name", "names",
         "reference", "list", "strings", "map", "glob", "rung", "path", "any")


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

    def summary(self) -> dict:
        return {"template": self.name, "description": self.description, **({"once": True} if self.once else {}),
                "from": "ergostat" if self.builtin else str(self.path), "trust": self.trust,
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
            if k in spec and (ty not in ("number", "integer") or isinstance(spec[k], bool)
                              or not isinstance(spec[k], int | float)):
                raise TemplateError(f"template {t.name}: param {n}: {k}: a number, on a number or integer param")
        t.params[str(n)] = Param(str(n), ty, str(spec.get("description") or "").strip(), spec.get("default"),
                                 spec.get("stand-in"), bool(spec.get("required")), "default" in spec,
                                 spec.get("choices"), spec.get("min"), spec.get("max"))
    t.body = {k: data[k] for k in BODY if data.get(k) is not None}
    t.trust = "ergostat" if builtin else trust
    return t


def folders(extra: list[Path] | None = None) -> list[Path]:
    """The owner's folders first (``library:`` in the main file, then ``$ERGOSTAT_LIBRARY``), then ergostat's own."""
    out = list(extra or [])
    for x in (os.environ.get(ENV) or "").split(os.pathsep):
        if x.strip():
            out.append(Path(x.strip()).expanduser())
    return [*out, HERE]


def find_all(extra: list[Path] | None = None, untrusted=()) -> tuple[dict[str, Template], list[str]]:
    """Every template, by name: an owner's template shadows ergostat's own of the same name (said in the notes),
    and the first folder wins between the owner's own. A template from a folder in ``untrusted`` never shadows a
    trusted one, wherever its folder is listed (SPEC §2a). Also what could not be read, and what was shadowed."""
    got: dict[str, Template] = {}
    notes: list[str] = []
    untrusted = {Path(u).resolve() for u in untrusted}
    for d in folders(extra):
        if not files.is_dir(d):
            if d != HERE:
                notes.append(f"library folder {d} does not exist")
            continue
        for f in sorted([*files.glob(d, "*.yaml"), *files.glob(d, "*.yml"), *files.glob(d, "*/template.yaml")]):
            try:
                t = read(f, d == HERE, "untrusted" if Path(d).resolve() in untrusted else "owner")
            except TemplateError as e:
                notes.append(str(e))
                continue
            was = got.get(t.name)
            if was is not None and trusted(was) != trusted(t):          # the trusted one, whichever came first
                kept, skipped = (was, t) if trusted(was) else (t, was)
                notes.append(f"template {t.name}: {skipped.path} (from a folder not marked trusted) is not used; "
                             f"{"ergostat's own" if kept.builtin else kept.path} is")
                got[t.name] = kept
                continue
            if t.name in got:
                if t.builtin and not got[t.name].builtin:
                    notes.append(f"template {t.name}: {got[t.name].path} is used in place of ergostat's own")
                continue
            got[t.name] = t
    return got, notes
