"""library-provenance-marks: values carry who wrote them, so a held chain may run the owner's own commands and pass
only short, checked library values as arguments to ergostat's own programs (SPEC §2a, SECURITY *Libraries you did not
write*)."""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path

import pytest

from ergostat.library import templates as tp
from ergostat.library import trust
from ergostat.library.expand import LIB, PY, VAR, F, mark
from ergostat.library.run import __main__ as run_main
from ergostat.spec import read
from ergostat.spec.load import load

ROOT = Path(__file__).resolve().parent.parent
CMD = "fetch tickets --all"


def write(root: Path, given: dict, lib: dict[str, str], own: dict[str, str] | None = None, use: str = "l") -> Path:
    for folder, temps in (("lib", lib), ("own", own or {})):
        (root / folder).mkdir(exist_ok=True)
        for name, text in temps.items():
            (root / folder / f"{name}.yaml").write_text(textwrap.dedent(text))
    (root / "ergostat.yaml").write_text(f"name: t\nlibrary: [{{folder: lib}}, own]\nuses:\n  u:\n    use: {use}\n"
                                        f"    with: {json.dumps(given)}\n")
    return root / "ergostat.yaml"


def errors(path: Path):
    _, ps = read(path)
    return [p for p in ps if p.level == "error"]


def refused_once(path: Path) -> str:
    """One library-untrusted error, at the owner's use: line, and nothing of the chain in the document."""
    errs = errors(path)
    assert [(e.code, e.where.line, e.where.file.name) for e in errs] == [("library-untrusted", 5, "ergostat.yaml")], errs
    doc = load(path)
    assert not [(s, n) for s, es in doc.sections.items() for n in es if n == "u" or n.startswith("u-")]
    assert not doc.uses and not [k for k in doc.defined if k[0] == "uses" and k[1].startswith("u-")]
    return errs[0].message


def compiles(path: Path):
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    return spec


def L(params: str = "cmd: {type: command}", body: str = "") -> str:
    return f"template: l\nparams:\n  {params}\n{body}"


COLLECT = "uses:\n  c:\n    use: collect\n    with: {{command: '${{cmd}}'{more}}}\n"


# ---- R1: the owner's commands


def test_owner_command_whole_slot_allowed(tmp_path):
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body="blocks:\n  b: {type: program, run: '${cmd}', every: 1m}\n")})
    # every: 1m is the library's own word: refused, though the run is the owner's
    assert "blocks.u-b.every" in refused_once(path)
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body="blocks:\n  b: {type: program, run: '${cmd}'}\n")})
    assert compiles(path).blocks["u-b"].params["run"] == CMD


def test_owner_command_through_builtin_allowed(tmp_path):
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=COLLECT.format(more=", kind: tickets"))})
    run = compiles(path).flows["u-c-arriving"].sensors
    run = next(iter(run.values())).run
    assert run.startswith(LIB + " collect ") and f"--command '{CMD}'" in run and "--kind tickets " in run, run


def test_library_every_refused(tmp_path):
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=COLLECT.format(more=", kind: tickets, poll: 1m"))})
    assert "flows.u-c-arriving.sensor.every" in refused_once(path)


def test_library_literal_equal_to_owner_command_refused(tmp_path):
    body = "blocks:\n  b: {type: program, run: '${cmd}'}\n" + COLLECT.replace("'${{cmd}}'", f"'{CMD}'").format(more="")
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=body)})
    assert "sensor.run" in refused_once(path)


def test_library_default_for_command_param_refused(tmp_path):
    path = write(tmp_path, {}, {"l": L("cmd: {type: command, default: ./x.sh}", "blocks:\n  b: {type: program, run: '${cmd}'}\n")})
    assert "blocks.u-b.run" in refused_once(path)


@pytest.mark.parametrize("body", ["blocks:\n  b: {type: program, run: '${cmd} | sh'}\n",
                                  COLLECT.replace("'${{cmd}}'", "'${{cmd}}; x'").format(more="")])
def test_library_text_around_owner_command_refused(tmp_path, body):
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=body)})
    assert ".run," in refused_once(path)


def test_owner_string_param_in_run_refused(tmp_path):
    path = write(tmp_path, {"s": CMD}, {"l": L("s: {type: string}", "blocks:\n  b: {type: program, run: '${s}'}\n")})
    assert "blocks.u-b.run" in refused_once(path)


def test_command_mark_lost_through_non_command_param(tmp_path):
    body = "uses:\n  c:\n    use: collect\n    with: {command: '${s}'}\n"
    path = write(tmp_path, {"s": CMD}, {"l": L("s: {type: string}", body)})
    assert "flows.u-c-arriving.sensor.run" in refused_once(path)
    # the same through a list's field, and a field of the owner's map: whose words a field holds can't be told
    body = "uses:\n  c:\n    use: collect\n    with: {command: '${m.run}'}\n"
    path = write(tmp_path, {"m": {"run": CMD}}, {"l": L("m: {type: map}", body)})
    assert "flows.u-c-arriving.sensor.run" in refused_once(path)


def test_nested_library_literal_refused(tmp_path):
    l2 = "template: l2\nitems:\n  k: {id: k/*}\nuses:\n  c:\n    use: collect\n    with: {command: ./fetch.sh}\n"
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body="stocks:\n  s: {unit: u}\nuses:\n  in:\n    use: l2\n"), "l2": l2})
    msg = refused_once(path)
    assert "u-in-c-arriving.sensor.run" in msg and "template l from" in msg
    spec, _ = read(path)
    assert not spec.stocks and not spec.flows and not spec.blocks and not [k for k in spec.items if k[:9] != "ergostat."]
    assert not [s for s in spec.systems if s.startswith("u")]


@pytest.mark.parametrize("own", ["params:\n  x: {type: name}\nstocks:\n  s: {unit: u}\nflows:\n  f:\n    to: s\n"
                                 "    sensor: {run: 'sh -c ${x:quote}'}\n",
                                 "params:\n  kind: {type: name}\nblocks:\n  b: {type: program, run: '${lib} each --kind ${kind}'}\n"])
def test_library_value_into_owner_folder_template_run_refused(tmp_path, own):
    name = "x" if "x:" in own else "kind"
    body = f"uses:\n  o:\n    use: of\n    with: {{{name}: tickets}}\n"
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=body)}, {"of": "template: of\n" + own})
    assert ".run," in refused_once(path)


# ---- R2: library values as arguments to ergostat's programs

REPING = "uses:\n  c:\n    use: re-ping\n    with: {{command: '${{cmd}}', ping: '${{cmd}}', take-over: 'false', {k}: {v}}}\n"
COLLECT_KV = "uses:\n  c:\n    use: collect\n    with: {{command: '${{cmd}}', {k}: {v}}}\n"


@pytest.mark.parametrize("template, key, value, ok", [
    ("collect", "kind", "rm\n", False), ("collect", "kind", "a" * 65, False), ("collect", "kind", "Tickets", False),
    ("re-ping", "every", "5m\n", False), ("re-ping", "every", " 5m", False), ("re-ping", "every", "1e3s", False),
    ("re-ping", "limit", "1e9", False), ("collect", "stand-in-rate", "nan", False),
    ("re-ping", "every", "0ms", False), ("re-ping", "limit", 101, False), ("collect", "stand-in-rate", 100000, False),
    ("collect", "kind", "tickets", True), ("re-ping", "every", "5m", True), ("re-ping", "every", "1.5h", True),
    ("re-ping", "limit", 3, True), ("collect", "kind", "a" * 64, True)])
def test_narrow_value_patterns(tmp_path, template, key, value, ok):
    body = (COLLECT_KV if template == "collect" else REPING).format(k=key, v=json.dumps(value))
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=body)})
    if ok:
        spec = compiles(path)
        assert spec.flows and spec.flows[next(f for f in spec.flows if f.endswith("-asked") or f.endswith("-arriving"))]
        return
    errs = errors(path)                    # refused by the gate, or by the parameter's own type: either way at the use
    assert errs and {(e.where.line, e.where.file.name) for e in errs} == {(5, "ergostat.yaml")}, errs
    spec, _ = read(path)
    assert not spec.flows and not spec.blocks, (spec.flows, spec.blocks)


def test_library_values_are_bounded_after_rate_and_count_flags():
    """lesson-4: a library's --every 0ms or a --limit past the bound is refused even though its text is narrow."""
    def slot(flag, how, text, ty="integer"):
        return f"{LIB} ping --kind k {flag} " + mark(("l", ty, "1"), how, text)
    assert trust.run_ok(slot("--limit", "", "100"), "e") and not trust.run_ok(slot("--limit", "", "101"), "e")
    assert trust.run_ok(slot("--every", "seconds", "60", "duration"), "e")
    assert not trust.run_ok(slot("--every", "seconds", "0", "duration"), "e")
    assert not trust.run_ok(slot("--every", "", "0ms", "duration"), "e")
    assert not trust.run_ok(slot("--limit", "", "100\n"), "e")          # fullmatch, not match
    assert not trust.run_ok(slot("--run", "", "3"), "e")                 # only after a data flag


def test_forged_owner_mark_refused(tmp_path):
    """Only expand makes marks: a library's text holding a forged owner-command mark is refused whole."""
    forged = '"\\0c,command,,0\\x02rm -rf ~\\x01"'
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=f"blocks:\n  b: {{type: program, run: {forged}}}\n")})
    msg = refused_once(path)
    assert "control character" in msg and "rm -rf" not in msg
    body = f"uses:\n  c:\n    use: collect\n    with: {{command: {forged}}}\n"
    path = write(tmp_path, {"cmd": CMD}, {"l": L(body=body)})
    assert "control character" in refused_once(path)


# ---- every built-in run slot, and every flag of ergostat's programs

BUILT = {"name", "python", "lib", "ergostat", "here", "folder"}
FLAG = re.compile(r"(?:^| )(--[a-z][a-z0-9-]*) $")


def slots(x):
    """Every run slot's text as the template writes it (a run, or a run's chosen value)."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "run" and isinstance(v, str):
                yield v
            elif k == "run" and isinstance(v, dict) and isinstance(v.get("value"), str):
                yield v["value"]
            else:
                yield from slots(v)
    elif isinstance(x, list):
        for v in x:
            yield from slots(v)


def kind_of(t, slot: str, m) -> str | None:
    """What a ${...} in a run slot is: a built-in name, a command, a narrow argument, or None (anything else)."""
    ref, how = m.group(1), m.group(2)
    p = t.params.get(ref.split(".")[0])
    if p is None and ref in BUILT:
        return "built-in"
    if p is None or "." in ref:
        return None
    if p.type == "command" and how in (None, "quote", "arg"):
        return "command"
    before, flag = slot[:m.start()], FLAG.search(slot[:m.start()])
    if p.type in trust.NARROW and slot.startswith("${lib} "):
        if how in (None, "seconds", "hours") and flag and flag.group(1) in trust.LIB_DATA_FLAGS:
            return "argument"
        if how == "arg" and f"--{ref}" in trust.LIB_DATA_FLAGS and before[-1:] in ("", " "):
            return "argument"
    return None


def checked(t) -> list[tuple[str, str, str]]:
    """Each ${p} of a run slot not a built-in name, a command or a narrow argument: (slot, the ${p}, its type)."""
    out = []
    for slot in slots(t.body):
        for m in VAR.finditer(slot):
            if kind_of(t, slot, m) is None:
                p = t.params.get(m.group(1).split(".")[0])
                out.append((slot, m.group(0), "field" if p is None or "." in m.group(1) else p.type))
    return out


SAMPLE = {"name": "tickets", "duration": "5m", "number": "3", "integer": "3", "bool": "true"}


def probe(t, slot: str, at, text: str, ok: str) -> str:
    """The slot as expand renders it, with the ${p} at ``at`` a library's value and every other ergostat's own."""
    def one(m, text=text):
        ref, how = m.group(1), m.group(2)
        p = t.params.get(ref.split(".")[0])
        if p is None and ref in BUILT:
            return {"lib": LIB, "python": PY, "ergostat": f"{PY} -m ergostat"}.get(ref, "x")
        ty = "any" if p is None else p.type
        if m.start() != at:
            return mark(("e", ty, "1"), how, "v")
        if p is None or "." in ref:
            return F + text
        if how == "arg":
            text = f"--{ref}" if ty == "bool" else f"--{ref} {text}"
        return mark(("l", ty, ok), how, text)
    return VAR.sub(one, slot)


def test_builtin_run_slots_take_narrow_values_only_as_arguments(tmp_path):
    got, _ = tp.find_all()
    built = [t for t in got.values() if t.builtin]
    assert {"collect", "re-ping", "modelling", "upkeep", "repair"} <= {t.name for t in built}
    seen = 0
    for t in built:
        for slot in slots(t.body):
            for m in VAR.finditer(slot):
                seen += 1
                kind, p = kind_of(t, slot, m), t.params.get(m.group(1).split(".")[0])
                if kind == "argument":       # a narrow value lands after a data flag; checked, and refused otherwise
                    text = "300" if m.group(2) in ("seconds", "hours") else SAMPLE[p.type]
                    assert trust.run_ok(probe(t, slot, m.start(), text, "1"), "e"), (t.name, slot, m.group(0))
                    assert not trust.run_ok(probe(t, slot, m.start(), "rm\n", "0"), "e"), (t.name, slot, m.group(0))
                elif kind is None:           # anything else: refused from a library, even a well-formed value
                    ty = "any" if p is None or "." in m.group(1) else p.type
                    text = "300" if m.group(2) in ("seconds", "hours") else SAMPLE.get(ty, "x")
                    assert not trust.run_ok(probe(t, slot, m.start(), text, "1" if ty in trust.NARROW else "0"), "e"), (
                        t.name, slot, m.group(0))
    assert seen > 40
    fixture = tmp_path / "fx.yaml"
    fixture.write_text("template: fx\nparams:\n  kind: {type: name}\n  title: {type: string}\nblocks:\n"
                       "  a: {type: program, run: 'sh -c ${kind}'}\n  b: {type: program, run: '${lib} x --run ${kind}'}\n"
                       "  c: {type: program, run: '${lib} report --title ${title:quote}'}\n")
    found = checked(tp.read(fixture, False, "owner"))
    assert [(s, r) for s, r, _ in found] == [("sh -c ${kind}", "${kind}"), ("${lib} x --run ${kind}", "${kind}"),
                                             ("${lib} report --title ${title:quote}", "${title:quote}")], found


ARGVS = [["collect"], ["each"], ["ping"], ["due"], ["report"], ["modelling", "requests"], ["modelling", "rules"],
         ["modelling", "ai"], ["modelling", "redesign"], ["modelling", "review"], ["upkeep", "tidy"],
         ["standin", "act"], ["standin", "level"]]


def options(monkeypatch, extra: str | None = None) -> dict[str, set[str]]:
    """Every option of every ergostat.library.run program's parser, caught as it is about to parse."""
    got: dict[str, set[str]] = {}

    def caught(self, args=None, namespace=None):
        if extra:
            self.add_argument(extra)
        got[self.prog] = {o for a in self._actions if not isinstance(a, argparse._HelpAction) for o in a.option_strings}
        raise SystemExit(0)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_known_args", caught)
    for argv in ARGVS:
        with pytest.raises(SystemExit):
            run_main.main(argv)
    return got


def unclassified(got: dict[str, set[str]]) -> list[str]:
    return sorted(f"{prog} {o}" for prog, opts in got.items() for o in opts
                  if o not in trust.LIB_DATA_FLAGS and o not in trust.LIB_EXEC_FLAGS)


def test_every_lib_flag_classified(monkeypatch):
    got = options(monkeypatch)
    sources = "".join(p.read_text() for p in (ROOT / "ergostat/library/run").glob("*.py"))
    assert len(got) == sources.count("argparse.ArgumentParser(")         # every parser reached
    assert unclassified(got) == [] and not trust.LIB_DATA_FLAGS & trust.LIB_EXEC_FLAGS
    assert {"--run", "--render", "--command"} <= trust.LIB_EXEC_FLAGS and {"--kind", "--every"} <= trust.LIB_DATA_FLAGS
    assert unclassified(options(monkeypatch, "--zzz-extra")) == [f"{p} --zzz-extra" for p in sorted(got)]


def test_refusal_never_suggests_with(tmp_path):
    """No refusal suggests with: or trust: owner, or quotes the refused value."""
    cases = [({"cmd": CMD}, L(body="blocks:\n  b: {type: program, run: '${cmd} | sh -c ./fetch.sh'}\n")),
             ({}, L("cmd: {type: command, default: ./fetch.sh}", "blocks:\n  b: {type: program, run: '${cmd}'}\n")),
             ({"s": CMD}, L("s: {type: string}", "blocks:\n  b: {type: program, run: '${s}'}\n")),
             ({"cmd": CMD}, L(body=COLLECT.replace("'${{cmd}}'", "./fetch.sh").format(more=", poll: 1m"))),
             ({"cmd": CMD}, L(body=COLLECT.format(more=", kind: \"rm\\n\""))),
             ({"cmd": CMD}, L(body='blocks:\n  b: {type: program, run: "\\0c,command,,0\\x02./fetch.sh\\x01"}\n'))]
    for i, (given, body) in enumerate(cases):
        (tmp_path / str(i)).mkdir()
        msg = refused_once(write(tmp_path / str(i), given, {"l": body}))
        for bad in ("with:", "trust: owner", CMD, "./fetch.sh", "sh -c", "rm\n", "rm\\n"):
            assert bad not in msg, (bad, msg)
