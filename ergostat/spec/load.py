"""Reading ``ergostat.yaml`` and the files it includes into one merged document, keeping where each
thing was written (file and line), so every error can point at it (SPEC §2)."""

from __future__ import annotations

import contextlib
import contextvars
import glob
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import files

FILE = "ergostat.yaml"
SECTIONS = ("sources", "systems", "items", "parameters", "auxiliaries", "variables", "stocks", "flows", "goals", "blocks", "agents",
            "loops", "claims", "contexts", "actions", "workspaces", "leases", "daemons")
SINGULAR = {"auxiliaries": "auxiliary", "variables": "auxiliary", "claims": "check",   # variables: the old name of auxiliaries
            "contexts": "context", "actions": "action", "workspaces": "workspace", "leases": "lease terms of",
            "daemons": "daemon"}
TOP = {"name", "purpose", "include", "keep", "messages", "storage", "intake", "web", "notify",
       "defaults", "uses", "library", "remotes", *SECTIONS}


TEXTS: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ergostat_spec_texts", default=None)


@contextlib.contextmanager
def texts(over: dict):
    """Read these files' text from ``over`` (path → text) instead of the disk, in this thread only: a
    change tried on the model before it is written (a proposal simulated, or checked)."""
    tok = TEXTS.set({Path(k).resolve(): v for k, v in over.items()})
    try:
        yield
    finally:
        TEXTS.reset(tok)


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
    from .yaml12 import ambiguous

    class Loader(yaml.SafeLoader):
        key = False                      # constructing a mapping's key

        def construct_object(self, node, deep=False):
            got = super().construct_object(node, deep=deep)
            if isinstance(node, yaml.ScalarNode) and node.style is None:        # plain, not quoted
                said = ambiguous(node.value, got, self.key)
                if said:
                    problems.append(Problem("finding", said, Where(path, node.start_mark.line + 1), "yaml-1.1"))
            return got

    def mapping(loader, node, deep=False):
        m = Map()
        m.where = Where(path, node.start_mark.line + 1)
        m.lines = {}
        loader.flatten_mapping(node)
        for k_node, v_node in node.value:
            loader.key = True
            try:
                k = loader.construct_object(k_node, deep=True)
            finally:
                loader.key = False
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
    messages: object = None          # messages: how the owner's messages are routed (SPEC §12h), in one file
    messages_at: Where | None = None
    storage: object = None
    purpose: str = ""                # what the whole model is for (main file only): goals trace to it (SPEC §4a)
    intake: object = None            # intake: what may push events to the running ergostat (main file only)
    web: object = None               # web: the page's public names and their login (main file only)
    notify: object = None            # notify: where what waits on a person is sent (main file only)
    sections: dict[str, dict[str, Map]] = field(default_factory=lambda: {s: {} for s in SECTIONS})
    defined: dict[tuple[str, str], Where] = field(default_factory=dict)
    defaults: dict[tuple[str, str], dict] = field(default_factory=dict)   # what the defining file's defaults: were
    problems: list[Problem] = field(default_factory=list)
    library: list[Path] = field(default_factory=list)   # the owner's folders of templates (library:, main file only)
    uses: dict[str, dict] = field(default_factory=dict)  # each template instance: its template, values, stand-ins, where
    remotes: dict[str, dict] = field(default_factory=dict)  # each remote system: its url, version, parts (SPEC §4c)
    soft: set[tuple[str, str]] = field(default_factory=set)  # what a once template made that a declaration may replace


def read_file(path: Path, problems: list[Problem]):
    try:
        over = TEXTS.get()
        text = over[path.resolve()] if over and path.resolve() in over else files.read_text(path)
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
        if "purpose" in data:
            if top:
                doc.purpose = str(data["purpose"] or "")
            else:
                doc.problems.append(Problem("error", "purpose: belongs in the main file only", data.at("purpose"),
                                            "purpose-in-include"))
        if "storage" in data:
            if top:
                doc.storage = data["storage"]
            else:
                doc.problems.append(Problem("error", "storage: belongs in the main file only", data.at("storage"), "storage-in-include"))
        if "intake" in data:
            if top:
                doc.intake = data["intake"]
            else:
                doc.problems.append(Problem("error", "intake: belongs in the main file only", data.at("intake"), "intake-in-include"))
        if "web" in data:
            if top:
                doc.web = data["web"]
            else:
                doc.problems.append(Problem("error", "web: belongs in the main file only", data.at("web"), "web-in-include"))
        if "notify" in data:
            if top:
                doc.notify = data["notify"]
            else:
                doc.problems.append(Problem("error", "notify: belongs in the main file only", data.at("notify"), "notify-in-include"))
        if "keep" in data:
            if top:
                doc.keep = data["keep"]
            else:
                doc.problems.append(Problem("error", "keep: belongs in the main file only", data.at("keep"), "keep-in-include"))
        if "messages" in data:
            if doc.messages is not None:
                doc.problems.append(Problem("error", f"messages: is written twice (here and at {doc.messages_at}); keep one",
                                            data.at("messages"), "defined-twice"))
            else:
                doc.messages, doc.messages_at = data["messages"], data.at("messages")
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict) or set(defaults) - {"system"}:
            doc.problems.append(Problem("error", "defaults: may only set system:", data.at("defaults"), "bad-defaults"))
            defaults = {}
        if "library" in data:
            if top:
                lib = data["library"]
                lib = [lib] if isinstance(lib, str) else lib
                if not isinstance(lib, list) or not all(isinstance(x, str) for x in lib):
                    doc.problems.append(Problem("error", "library: a folder of templates, or a list of them", data.at("library"),
                                                "bad-library"))
                else:
                    doc.library = [(path.parent / Path(x).expanduser()).resolve() for x in lib]
            else:
                doc.problems.append(Problem("error", "library: belongs in the main file only", data.at("library"),
                                            "library-in-include"))
        for section in SECTIONS:
            body = data.get(section)
            if body is None:
                continue
            if not isinstance(body, dict):
                doc.problems.append(Problem("error", f"{section}: must be a map, each entry keyed by its name",
                                            data.at(section), "not-a-map"))
                continue
            for name, entry in body.items():
                put(section, name, entry, body.at(name), defaults)
        if data.get("uses") is not None:
            from ..library import uses
            uses.take(doc, data, defaults, put)
        if data.get("remotes") is not None:
            from ..remote import compose
            compose.take(doc, data, defaults, put)
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
            hits = files.glob(path.parent, pat) if glob.has_magic(pat) else [full]
            if not hits:
                doc.problems.append(Problem("error", f"include: {pat} matches no file", data.at("include"), "include-missing"))
            for h in hits:
                if not files.is_file(h):
                    doc.problems.append(Problem("error", f"include: {pat}: no such file", data.at("include"), "include-missing"))
                    continue
                take(h.resolve(), False, data.at("include"))

    def put(section: str, name, entry, w: Where | None, defaults: dict) -> None:
        if (section, name) in doc.soft:           # a once template's system, declared by the model too: the model's stands
            doc.soft.discard((section, name))
            doc.defined.pop((section, name))
        if (section, name) in doc.defined:
            first = doc.defined[(section, name)]
            one = SINGULAR.get(section, section[:-1])
            doc.problems.append(Problem("error", f"{one} {name} is defined twice: here and at {first}", w,
                                        "defined-twice", f"{one}.{name}"))
            return
        if entry is None:
            entry = Map()
            entry.where, entry.lines = w, {}
        doc.defined[(section, name)] = w
        doc.sections[section][name] = entry
        doc.defaults[(section, name)] = dict(defaults)

    take(main, True, None)
    if doc.remotes:                          # local references into each remote, checked against what it serves now
        from ..remote import compose
        compose.finish(doc, put)
    return doc


def find(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / FILE).is_file():
            return d / FILE
    return None
