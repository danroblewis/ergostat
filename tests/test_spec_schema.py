"""The draft specification's examples are valid against its JSON Schema, and the broken files are
refused: the spec (docs/SPEC.md) and the schema (schema/ergostat.schema.json) say the same thing."""

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema/ergostat.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def test_the_schema_is_a_valid_schema():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", sorted((ROOT / "docs/spec-examples").glob("*.yaml")), ids=lambda p: p.stem)
def test_each_example_in_the_spec_is_valid(path):
    errors = [e.message for e in VALIDATOR.iter_errors(yaml.safe_load(path.read_text()))]
    assert not errors, errors


@pytest.mark.parametrize("path", sorted((ROOT / "tests/spec-invalid").glob("*.yaml")), ids=lambda p: p.stem)
def test_each_broken_file_is_refused(path):
    assert list(VALIDATOR.iter_errors(yaml.safe_load(path.read_text())))
