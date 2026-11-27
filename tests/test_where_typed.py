"""``where:`` compares typed JSON values (SPEC §6): numbers as numbers, strings as strings, booleans as booleans;
check notes each bare number or boolean written in one, since its meaning changed from comparing text."""

import textwrap

from ergostat.spec import read
from ergostat.spec.items import Item, matches


def item(**fields) -> Item:
    return Item("t/1", "t", "open", fields)


def test_numbers_match_as_numbers_strings_as_strings_booleans_as_booleans():
    assert matches(item(n=1.0), {"n": 1}) and matches(item(n=1), {"n": 1.0})
    assert not matches(item(n="1"), {"n": 1}) and not matches(item(n=1), {"n": "1"})
    assert matches(item(team="core"), {"team": "core"}) and matches(item(team="core"), {"team": ["x", "core"]})
    assert matches(item(ok=True), {"ok": True}) and not matches(item(ok=1), {"ok": True})
    assert not matches(item(ok=True), {"ok": 1}) and not matches(item(ok=True), {"ok": "True"})
    assert matches(item(), {"gone": None}) and not matches(item(gone=0), {"gone": None})
    assert matches(item(lease={"back": "triage"}), {"lease.back": "triage"})
    assert matches(item(tags=["a", 1]), {"tags": [["a", 1.0]]})


def test_check_notes_where_values_whose_meaning_changed(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""\
        name: t
        projections:
          ticket:
            match:
              key: ticket/*
            states: [open, done]
        stocks:
          urgent:
            unit: tickets
            sensor:
              projection: ticket
              state: open
              where:
                priority: 1
                team: core
                quoted: "1"
          flagged:
            unit: tickets
            sensor:
              projection: ticket
              state: open
              where: {flag: true}
        """))
    _, ps = read(tmp_path / "ergostat.yaml")
    notes = [p for p in ps if p.code == "where-typed"]
    assert sorted((p.where.line, p.about) for p in notes) == [(14, "stock.urgent"), (22, "stock.flagged")], \
        [(str(p), p.about) for p in notes]
    assert '"1" (quoted)' in notes[0].message and "a number" in notes[0].message
    assert all(p.level == "finding" for p in notes)


def test_a_filter_typed_as_text_matches_the_field_whichever_type_it_holds():
    from ergostat.spec.items import typed_too
    w = typed_too({"priority": ["1"], "team": ["core"], "ok": ["true"]})
    assert matches(item(priority=1, team="core", ok=True), w) and matches(item(priority="1", team="core", ok="true"), w)
    assert not matches(item(priority=2, team="core", ok=True), w)
