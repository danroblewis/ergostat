"""The implied id (SPEC §5a, docs/roadmap/systems-and-projections.md step 3): a projection that writes no ``id:``
matches its defined-in system's chain from the top level, its name, then ``*``; an ``id:`` written overrides it."""

import json
import textwrap
from pathlib import Path

from ergostat.cli import main
from ergostat.remote import serve
from ergostat.spec import read
from ergostat.spec.ir import SESSION


def model(root: Path, text: str, more: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in (more or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(textwrap.dedent(body))
    (root / "ergostat.yaml").write_text(textwrap.dedent(text))
    return root / "ergostat.yaml"


def ids(path: Path) -> tuple[dict[str, str], list]:
    spec, problems = read(path)
    errors = [p for p in problems if p.level == "error"]
    return {n: k.id for n, k in spec.items.items() if not n.startswith("ergostat.") and n != SESSION}, errors


SYSTEMS = """
name: t
systems:
  factory: {}
  intake: {within: factory}
"""


def test_a_projection_in_no_system_matches_its_name(tmp_path):
    got, errors = ids(model(tmp_path, "name: t\nprojections:\n  ticket:\n    states: [open, done]\n"))
    assert got == {"ticket": "ticket/*"} and not errors


def test_a_projection_in_a_top_level_system(tmp_path):
    got, errors = ids(model(tmp_path, SYSTEMS + "projections:\n  ticket: {system: factory}\n"))
    assert got == {"ticket": "factory/ticket/*"} and not errors


def test_a_projection_in_a_nested_system_by_its_system_key(tmp_path):
    got, errors = ids(model(tmp_path, SYSTEMS + "projections:\n  ticket: {system: intake, states: [open]}\n"))
    assert got == {"ticket": "factory/intake/ticket/*"} and not errors
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert spec.items["ticket"].matches("factory/intake/ticket/12") and not spec.items["ticket"].matches("ticket/12")


def test_a_projection_in_a_nested_system_by_its_files_defaults(tmp_path):
    path = model(tmp_path, SYSTEMS + "include: [intake.yaml]\n", {"intake.yaml": """
        defaults:
          system: intake
        projections:
          ticket: {states: [open]}
        """})
    got, errors = ids(path)
    assert got == {"ticket": "factory/intake/ticket/*"} and not errors


def test_a_system_named_only_by_a_part_is_top_level(tmp_path):
    got, errors = ids(model(tmp_path, "name: t\nprojections:\n  ticket: {system: ops}\n"))
    assert got == {"ticket": "ops/ticket/*"} and not errors


def test_an_id_written_overrides_and_is_checked_as_ever(tmp_path):
    got, errors = ids(model(tmp_path, SYSTEMS + "projections:\n  ticket: {system: intake, match: {key: jira/ticket/*}}\n"))
    assert got == {"ticket": "jira/ticket/*"} and not errors
    _, errors = ids(model(tmp_path, SYSTEMS + "projections:\n  ticket: {system: intake, match: {key: tickets}}\n"))
    assert [e.code for e in errors] == ["bad-id"]


def test_a_system_that_is_not_a_name_needs_an_id(tmp_path):
    _, errors = ids(model(tmp_path, "name: t\nprojections:\n  ticket: {system: Big Ops}\n"))
    assert "bad-id" in [e.code for e in errors]
    got, errors = ids(model(tmp_path, "name: t\nprojections:\n  ticket: {system: Big Ops, match: {key: ops/ticket/*}}\n"))
    assert got == {"ticket": "ops/ticket/*"} and "bad-id" not in [e.code for e in errors]


def test_systems_that_go_round_still_give_an_id(tmp_path):
    got, errors = ids(model(tmp_path, """
        name: t
        systems:
          a: {within: b}
          b: {within: a}
        projections:
          ticket: {system: a}
        """))
    assert "system-cycle" in [e.code for e in errors]
    assert got["ticket"] in ("a/ticket/*", "b/a/ticket/*")       # one within is dropped; the id never loops


def test_a_template_made_projection_is_named_by_its_short_name(tmp_path):
    path = model(tmp_path, """
        name: t
        library: [{folder: lib, trust: owner}]
        systems:
          factory: {}
        uses:
          u:
            use: shape
            within: factory
        """, {"lib/shape.yaml": """
        template: shape
        description: structure only
        projections:
          ticket:
            states: [open, done]
        stocks:
          open:
            unit: items
            sensor: {projection: "${name}-ticket", state: open}
        """})
    got, errors = ids(path)
    assert got == {"u-ticket": "factory/u/ticket/*"} and not errors, errors


def test_a_remote_serves_the_implied_id_written_out(tmp_path):
    path = model(tmp_path, SYSTEMS + "projections:\n  ticket: {system: intake, states: [open]}\n  pr: {match: {key: gh/pr/*}}\n")
    got = serve.model(path)["sections"]["projections"]
    assert got["ticket"]["match"] == {"key": "factory/intake/ticket/*"} and got["pr"]["match"] == {"key": "gh/pr/*"}


def test_check_passes_on_a_model_with_no_ids(tmp_path, capsys):
    model(tmp_path, SYSTEMS + textwrap.dedent("""
        projections:
          ticket:
            system: intake
            states: [open, done]
            events:
              ticket.closed:
                state: set('done')
            otherwise: rest
          note:
            states: [new]
        stocks:
          open-tickets:
            system: intake
            unit: tickets
            sensor: {projection: ticket, state: open}
        """))
    assert main(["-C", str(tmp_path), "check"]) == 0, capsys.readouterr()
    out = capsys.readouterr()
    assert "bad-id" not in out.out + out.err
    assert json.dumps(ids(tmp_path / "ergostat.yaml")[0]) == json.dumps(
        {"ticket": "factory/intake/ticket/*", "note": "note/*"})
