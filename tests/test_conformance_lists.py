"""Conformance list files: read in order with defaults, every limit refused by the list's name (conformance-list-files)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ergostat.library.run import conformance_lists as cl
from ergostat.library.run.conformance_lists import ListError, read

MODULE = Path(cl.__file__)


def write(folder: Path, name: str, text: str) -> Path:
    p = folder / f"{name}.yaml"
    p.write_text(text)
    return p


def cases_yaml(list_name: str, n: int, prefix: str = "c") -> str:
    return f"list: {list_name}\ncases:\n" + "".join(f"  {prefix}{i}:\n    check: 'true'\n" for i in range(n))


def refused(folder, names, name: str, *words: str) -> ListError:
    with pytest.raises(ListError) as e:
        read(folder, names)
    assert e.value.name == name, e.value
    for w in words:
        assert w in e.value.why, e.value.why
    return e.value


DIAGRAMS = """\
list: diagrams
description: the diagram types ergostat draws
cases:
  service-map:
    description: a service map
    from: docs/proposals/diagram-options.md:59
    asked: false
    check: python3 checks.py service-map
    timeout: 2m
  stock-and-flow:
    check: python3 checks.py stock-and-flow
"""
FORMATS = """\
list: model-formats
cases:
  xmile:
    check: python3 checks.py xmile
"""


def test_reads_two_lists_in_order_with_defaults(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS)
    write(tmp_path, "model-formats", FORMATS)
    got = read(tmp_path, ["model-formats", "diagrams"])
    assert [c.id for c in got.cases] == ["case/model-formats/xmile", "case/diagrams/service-map",
                                         "case/diagrams/stock-and-flow"]
    assert got.declared == 3
    xmile, smap, saf = got.cases
    assert (smap.list, smap.name, smap.check, smap.timeout_s, smap.asked) == (
        "diagrams", "service-map", "python3 checks.py service-map", 120.0, False)
    assert (smap.from_, smap.description) == ("docs/proposals/diagram-options.md:59", "a service map")
    assert (saf.timeout_s, saf.asked, saf.from_, saf.description) == (60.0, True, "", "")
    assert (xmile.timeout_s, xmile.asked) == (60.0, True)


def test_missing_list_file_refused_by_name(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS)
    refused(tmp_path, ["diagrams", "discovery"], "discovery", "missing")


def test_not_a_mapping_and_bad_yaml_refused(tmp_path):
    write(tmp_path, "diagrams", "- a\n- b\n")
    refused(tmp_path, ["diagrams"], "diagrams", "not a mapping")
    write(tmp_path, "diagrams", "list: [unclosed\n")
    refused(tmp_path, ["diagrams"], "diagrams", "cannot read")
    write(tmp_path, "diagrams", "")
    refused(tmp_path, ["diagrams"], "diagrams", "not a mapping")
    write(tmp_path, "diagrams", "list: diagrams\n")
    refused(tmp_path, ["diagrams"], "diagrams", "cases")


def test_list_name_must_match_file_name(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS.replace("list: diagrams", "list: charts"))
    refused(tmp_path, ["diagrams"], "diagrams", "list:", "charts")
    write(tmp_path, "diagrams", DIAGRAMS.replace("list: diagrams\n", ""))
    refused(tmp_path, ["diagrams"], "diagrams", "list:")


def test_name_repeated_in_names_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS)
    write(tmp_path, "model-formats", FORMATS)
    refused(tmp_path, ["diagrams", "model-formats", "diagrams"], "diagrams", "more than once")


def test_list_name_off_pattern_refused(tmp_path):
    (tmp_path / "sub").mkdir()
    write(tmp_path / "sub", "x", "list: x\ncases: {}\n")
    for bad in ["../sub/x", "Diagrams", "-x", "a" * 65, ""]:
        refused(tmp_path, [bad], bad, "must match")


def test_case_name_off_pattern_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS.replace("service-map:", "Service_Map:"))
    refused(tmp_path, ["diagrams"], "diagrams", "case name", "Service_Map")
    write(tmp_path, "diagrams", DIAGRAMS.replace("service-map:", "7:"))
    refused(tmp_path, ["diagrams"], "diagrams", "case name")


def test_case_without_check_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS.replace("    check: python3 checks.py stock-and-flow\n",
                                                 "    description: no check here\n"))
    refused(tmp_path, ["diagrams"], "diagrams", "stock-and-flow", "check")
    write(tmp_path, "diagrams", "list: diagrams\ncases:\n  bare:\n")
    refused(tmp_path, ["diagrams"], "diagrams", "bare", "check")
    write(tmp_path, "diagrams", "list: diagrams\ncases:\n  blank:\n    check: '  '\n")
    refused(tmp_path, ["diagrams"], "diagrams", "blank", "check")


def test_timeout_over_ten_minutes_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS.replace("timeout: 2m", "timeout: 10m"))
    assert read(tmp_path, ["diagrams"]).cases[0].timeout_s == 600.0
    for bad in ["11m", "601", "1h", ".inf"]:
        write(tmp_path, "diagrams", DIAGRAMS.replace("timeout: 2m", f"timeout: {bad}"))
        refused(tmp_path, ["diagrams"], "diagrams", "service-map", "timeout")


def test_timeout_unparseable_refused(tmp_path):
    for bad in ["soon", "-1m", "0", "true", ".nan", "[1]"]:
        write(tmp_path, "diagrams", DIAGRAMS.replace("timeout: 2m", f"timeout: {bad}"))
        refused(tmp_path, ["diagrams"], "diagrams", "service-map", "timeout")


def test_asked_not_a_bool_refused(tmp_path):
    for bad in ["'no'", "0", "maybe"]:
        write(tmp_path, "diagrams", DIAGRAMS.replace("asked: false", f"asked: {bad}"))
        refused(tmp_path, ["diagrams"], "diagrams", "service-map", "asked")


def test_unknown_key_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS.replace("    timeout: 2m\n", "    timeout: 2m\n    timout: 3m\n"))
    refused(tmp_path, ["diagrams"], "diagrams", "service-map", "timout")
    write(tmp_path, "diagrams", DIAGRAMS + "owner: someone\n")
    refused(tmp_path, ["diagrams"], "diagrams", "owner")


def test_case_name_given_twice_refused(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS + "  service-map:\n    check: 'false'\n")
    refused(tmp_path, ["diagrams"], "diagrams", "twice")


def test_list_over_500_cases_refused(tmp_path):
    write(tmp_path, "big", cases_yaml("big", 500))
    assert read(tmp_path, ["big"]).declared == 500
    write(tmp_path, "big", cases_yaml("big", 501))
    refused(tmp_path, ["big"], "big", "500")


def test_more_than_20_lists_refused(tmp_path):
    names = [f"l{i}" for i in range(21)]
    for n in names:
        write(tmp_path, n, cases_yaml(n, 1))
    assert read(tmp_path, names[:20]).declared == 20
    refused(tmp_path, names, "l20", "20 lists")


def test_500_cases_across_lists_refused(tmp_path):
    write(tmp_path, "a", cases_yaml("a", 300))
    write(tmp_path, "b", cases_yaml("b", 200))
    write(tmp_path, "c", cases_yaml("c", 1))
    assert read(tmp_path, ["a", "b"]).declared == 500
    refused(tmp_path, ["a", "b", "c"], "c", "500", "across")


def test_no_names_refused(tmp_path):
    with pytest.raises(ListError):
        read(tmp_path, [])
    with pytest.raises(ListError):
        read(tmp_path, "diagrams")


def test_digest_moves_only_with_named_files(tmp_path):
    write(tmp_path, "diagrams", DIAGRAMS)
    write(tmp_path, "model-formats", FORMATS)
    write(tmp_path, "other", cases_yaml("other", 2))
    names = ["diagrams", "model-formats"]
    first = read(tmp_path, names).digest
    assert read(tmp_path, names).digest == first
    write(tmp_path, "other", cases_yaml("other", 3))
    assert read(tmp_path, names).digest == first
    write(tmp_path, "model-formats", FORMATS + "# a comment only\n")
    second = read(tmp_path, names).digest
    assert second != first
    write(tmp_path, "diagrams", DIAGRAMS.replace("2m", "3m"))
    assert read(tmp_path, names).digest not in (first, second)


def test_module_small_and_apart_from_the_spec():
    text = MODULE.read_text()
    assert len(text.splitlines()) < 140
    imported = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert {m for m in imported if m.startswith("ergostat")} == {"ergostat.durations"}
    assert "parse_duration" in text
