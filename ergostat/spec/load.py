"""Reading ``ergostat.yaml`` and the files it includes into one merged document, keeping where each
thing was written (file and line), so every error can point at it (SPEC §2)."""

from __future__ import annotations

import glob
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FILE = "ergostat.yaml"
SECTIONS = ("sources", "systems", "items", "stocks", "flows", "goals", "blocks", "agents")
TOP = {"name", "include", "keep", "defaults", *SECTIONS}


class SpecError(Exception):
    """One or more errors, each with where it was written."""

    def __init__(self, errors: list[Problem]):
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


@dataclass
class Where:
    file: Path
    line: int

    def __str__(self) -> str:
        return f"{self.file.name}:{self.line}"


@dataclass
class Problem:
    level: str                 # error, finding
    message: str
    where: Where | None = None
    code: str = ""             # a short name for the kind of problem: missing-feedback, unknown-key
    about: str = ""            # the reference it is about: goal.disk-headroom

    def __str__(self) -> str:
        return f"{self.where}: {self.message}" if self.where else self.message


class Map(dict):
    """A YAML mapping that remembers the line of each key, and its own."""

    where: Where | None = None
    lines: dict

    def at(self, key) -> Where | None:
        return self.lines.get(key, self.where) if hasattr(self, "lines") else self.where


def _loader(path: Path, problems: list[Problem]):
    class Loader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        m = Map()
        m.where = Where(path, node.start_mark.line + 1)
        m.lines = {}
        loader.flatten_mapping(node)
        for k_node, v_node in node.value:
            k = loader.construct_object(k_node, deep=True)
            if k in m:
                problems.append(Problem("error", f"{k!r} is written twice in the same map (the second would win silently)",
                                        Where(path, k_node.start_mark.line + 1), "duplicate-key"))
            m[k] = loader.construct_object(v_node, deep=True)
            m.lines[k] = Where(path, k_node.start_mark.line + 1)
        return m

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    # YAML 1.1 reads yes/no/on/off as booleans; the spec is YAML 1.2, where only true/false are
    Loader.yaml_implicit_resolvers = {k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:bool"]
                                      for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    import re
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                                 list("tTfF"))
    return Loader


@dataclass
class Document:
    """Everything the files say, merged: each section a map of name to its definition, and where
    each name was defined."""

    root: Path
    name: str
    files: list[Path] = field(default_factory=list)
    keep: object = None
    sections: dict[str, dict[str, Map]] = field(default_factory=lambda: {s: {} for s in SECTIONS})
    defined: dict[tuple[str, str], Where] = field(default_factory=dict)
    defaults: dict[tuple[str, str], dict] = field(default_factory=dict)   # what the defining file's defaults: were
    problems: list[Problem] = field(default_factory=list)


def read_file(path: Path, problems: list[Problem]):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        problems.append(Problem("error", f"cannot read {path}: {e.strerror or e}", None, "unreadable"))
        return None
    try:
        return yaml.load(text, Loader=_loader(path, problems))   # noqa: S506 (a SafeLoader subclass)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        what = getattr(e, "problem", None) or str(e)
        problems.append(Problem("error", f"not valid YAML: {what}", Where(path, mark.line + 1) if mark else Where(path, 1),
                                "yaml"))
        return None


def load(main: Path) -> Document:
    main = main.resolve()
    doc = Document(root=main.parent, name=main.parent.name)
    seen: set[Path] = set()

    def take(path: Path, top: bool, via: Where | None) -> None:
        if path in seen:
            doc.problems.append(Problem("error", f"{path.name} is included more than once (or includes itself)", via,
                                        "include-twice"))
            return
        seen.add(path)
        doc.files.append(path)
        data = read_file(path, doc.problems)
        if data is None:                     # an empty file, or one that did not read (already reported)
            return
        if not isinstance(data, dict):
            doc.problems.append(Problem("error", "the file must be a map of sections (stocks:, flows:, goals:, blocks: ...)",
                                        Where(path, 1), "not-a-map"))
            return
        for k in data:
            if k not in TOP:
                doc.problems.append(Problem("error", f"unknown section {k!r} (known: {', '.join(sorted(TOP))})",
                                            data.at(k), "unknown-key"))
        if "name" in data:
            if top:
                doc.name = str(data["name"])
            else:
                doc.problems.append(Problem("error", "name: belongs in the main file only", data.at("name"), "name-in-include"))
        if "keep" in data:
            if top:
                doc.keep = data["keep"]
            else:
                doc.problems.append(Problem("error", "keep: belongs in the main file only", data.at("keep"), "keep-in-include"))
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict) or set(defaults) - {"system"}:
            doc.problems.append(Problem("error", "defaults: may only set system:", data.at("defaults"), "bad-defaults"))
            defaults = {}
        for section in SECTIONS:
            body = data.get(section)
            if body is None:
                continue
            if not isinstance(body, dict):
                doc.problems.append(Problem("error", f"{section}: must be a map, each entry keyed by its name",
                                            data.at(section), "not-a-map"))
                continue
            for name, entry in body.items():
                w = body.at(name)
                if (section, name) in doc.defined:
                    first = doc.defined[(section, name)]
                    doc.problems.append(Problem("error", f"{section[:-1]} {name} is defined twice: here and at {first}", w,
                                                "defined-twice", f"{section[:-1]}.{name}"))
                    continue
                if entry is None:
                    entry = Map()
                    entry.where, entry.lines = w, {}
                doc.defined[(section, name)] = w
                doc.sections[section][name] = entry
                doc.defaults[(section, name)] = dict(defaults)
        inc = data.get("include")
        if inc is None:
            return
        if isinstance(inc, str):
            inc = [inc]
        if not isinstance(inc, list) or not all(isinstance(x, str) for x in inc):
            doc.problems.append(Problem("error", "include: a path, a glob, or a list of them", data.at("include"), "bad-include"))
            return
        for pat in inc:
            full = (path.parent / pat)
            hits = sorted(Path(p) for p in glob.glob(str(full), recursive=True)) if glob.has_magic(pat) else [full]
            if not hits:
                doc.problems.append(Problem("error", f"include: {pat} matches no file", data.at("include"), "include-missing"))
            for h in hits:
                if not h.is_file():
                    doc.problems.append(Problem("error", f"include: {pat}: no such file", data.at("include"), "include-missing"))
                    continue
                take(h.resolve(), False, data.at("include"))

    take(main, True, None)
    return doc


def find(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / FILE).is_file():
            return d / FILE
    return None
