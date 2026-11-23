"""Conformance lists (docs/proposals/conformance-stock.md §1): ``read(folder, names)`` reads ``<folder>/<name>.yaml``
for each name, in order, and validates it. The first problem raises ``ListError(name, why)``, and ``read`` never
returns part of the lists: a list that cannot be read stops the run. Never read by the model loader."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ergostat.durations import DurationError, parse_duration

NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
MAX_CASES_IN_LIST, MAX_LISTS, MAX_CASES = 500, 20, 500
MAX_TIMEOUT_S, DEFAULT_TIMEOUT_S = 600.0, 60.0
LIST_KEYS = {"list", "description", "cases"}
CASE_KEYS = {"check", "timeout", "asked", "from", "description"}


class ListError(ValueError):
    def __init__(self, name: str, why: str):
        super().__init__(f"conformance list {name!r}: {why}")
        self.name, self.why = name, why


@dataclass(frozen=True)
class Case:
    list: str
    name: str
    id: str
    check: str
    timeout_s: float
    asked: bool
    from_: str
    description: str


@dataclass(frozen=True)
class Lists:
    names: tuple[str, ...]
    cases: tuple[Case, ...]
    digest: str

    @property
    def declared(self) -> int:
        return len(self.cases)


class _Loader(yaml.SafeLoader):
    """Safe YAML that refuses a key given twice, so a repeated case name cannot hide a case."""


def _mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"key {key!r} given twice", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _text(name: str, where: str, value, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ListError(name, f"{where} must be {'a non-empty' if required else 'a'} string")
    return value


def _case(name: str, key, spec) -> Case:
    if not isinstance(key, str) or not NAME.fullmatch(key):
        raise ListError(name, f"case name {key!r} must match ^[a-z0-9][a-z0-9-]{{0,63}}$")
    if not isinstance(spec, dict):
        raise ListError(name, f"case {key}: must be a mapping with a check")
    if unknown := sorted(map(str, set(spec) - CASE_KEYS)):
        raise ListError(name, f"case {key}: unknown key {unknown[0]!r} (known: {', '.join(sorted(CASE_KEYS))})")
    if "check" not in spec:
        raise ListError(name, f"case {key}: no check")
    timeout = DEFAULT_TIMEOUT_S
    if spec.get("timeout") is not None:
        try:
            timeout = parse_duration(spec["timeout"], f"case {key}: timeout")
        except DurationError as e:
            raise ListError(name, str(e)) from None
        if not 0 < timeout <= MAX_TIMEOUT_S:               # also refuses a NaN
            raise ListError(name, f"case {key}: timeout {spec['timeout']!r} is over 10m")
    asked = spec.get("asked", True)
    if not isinstance(asked, bool):
        raise ListError(name, f"case {key}: asked must be true or false, not {asked!r}")
    return Case(name, key, f"case/{name}/{key}", _text(name, f"case {key}: check", spec["check"], True), timeout,
                asked, _text(name, f"case {key}: from", spec.get("from")),
                _text(name, f"case {key}: description", spec.get("description")))


def read(folder, names) -> Lists:
    if isinstance(names, str) or not names:
        raise ListError(str(names or ""), "names must be a non-empty list of list names")
    names = list(names)
    if len(names) > MAX_LISTS:
        raise ListError(names[MAX_LISTS], f"more than {MAX_LISTS} lists named ({len(names)})")
    cases: list[Case] = []
    digest = hashlib.sha256()
    for i, name in enumerate(names):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ListError(str(name), "list name must match ^[a-z0-9][a-z0-9-]{0,63}$")
        if name in names[:i]:
            raise ListError(name, "named more than once")
        path = Path(folder) / f"{name}.yaml"
        try:
            raw = path.read_bytes()
            data = yaml.load(raw.decode("utf-8"), Loader=_Loader)  # noqa: S506 (a SafeLoader subclass)
        except FileNotFoundError:
            raise ListError(name, f"file missing: {path}") from None
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            raise ListError(name, f"cannot read {path}: {e}") from None
        if not isinstance(data, dict):
            raise ListError(name, f"{path} is not a mapping of list, description and cases")
        if unknown := sorted(map(str, set(data) - LIST_KEYS)):
            raise ListError(name, f"unknown key {unknown[0]!r} (known: {', '.join(sorted(LIST_KEYS))})")
        if data.get("list") != name:
            raise ListError(name, f"list: is {data.get('list')!r}, not its file name {name!r}")
        _text(name, "description", data.get("description"))
        if not isinstance(data.get("cases"), dict):
            raise ListError(name, "cases must be a mapping of case name to case")
        if len(data["cases"]) > MAX_CASES_IN_LIST:
            raise ListError(name, f"cases: {len(data['cases'])}, more than {MAX_CASES_IN_LIST} in one list")
        if len(cases) + len(data["cases"]) > MAX_CASES:
            raise ListError(name, f"cases: more than {MAX_CASES} across the lists named")
        cases += [_case(name, key, spec) for key, spec in data["cases"].items()]
        digest.update(f"{name}\0{len(raw)}\0".encode() + raw)
    return Lists(tuple(names), tuple(cases), digest.hexdigest())
