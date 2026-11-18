"""YAML 1.1 readings (SPEC §2, *Which YAML*): every plain value YAML 1.1 and 1.2 read differently is a yaml-1.1
finding at its file and line, saying what it is read as and the quoted form to write; quoted values, and values both
read alike, are not."""

import textwrap

import yaml

from ergostat.spec import read
from ergostat.spec.yaml12 import ambiguous


def test_each_ambiguous_scalar_says_what_it_is_read_as_and_what_to_write():
    for text, says in (("9:30", '570'), ("18:00", "1080"), ("010", "10 for the number"), ("1_000", "1000"),
                       ("0b101", "5"), ("2026-11-18", "a date"), ("1e3", "1000 for the number"), ("0o17", "15")):
        msg = ambiguous(text, yaml.safe_load(text))
        assert msg and says in msg and f'"{text}" (quoted)' in msg, (text, msg)
    for word in ("yes", "no", "on", "off"):
        assert "boolean" in ambiguous(word, word) and ambiguous(word, word, key=True) is None
    for same in ("09:30", "0x1F", "007", "1.5", "-2", "5m", "true", "~", ".inf", "abc"):
        assert ambiguous(same, yaml.safe_load(same)) is None, same


def test_check_warns_at_the_line_and_not_on_quoted_values(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""\
        name: t
        stocks:
          queue:
            unit: things
            description: opened 2026-11-18
            sensor: {run: echo 1, every: 1m}
        blocks:
          staffing:
            type: schedule
            table:
              9:30: 3
              "18:00": 1
        parameters:
          k:
            value: 010
          j:
            value: "1e3"
            description: on
        """))
    _, ps = read(tmp_path / "ergostat.yaml")
    got = {(p.where.line, p.message.split(" ", 1)[0]) for p in ps if p.code == "yaml-1.1"}
    assert got == {(11, "9:30"), (15, "010"), (18, "on")}, got
    assert all(p.level == "finding" for p in ps if p.code == "yaml-1.1")
