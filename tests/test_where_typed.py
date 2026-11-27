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


def test_a_filter_typed_as_text_matches_the_field_whichever_type_it_holds():
    from ergostat.spec.items import typed_too
    w = typed_too({"priority": ["1"], "team": ["core"], "ok": ["true"]})
    assert matches(item(priority=1, team="core", ok=True), w) and matches(item(priority="1", team="core", ok="true"), w)
    assert not matches(item(priority=2, team="core", ok=True), w)
