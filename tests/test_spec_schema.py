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


@pytest.mark.parametrize("pool, ok", [
    (2, True), ({"now": "stock.reviewers", "most": 3}, True),
    (0, False), ({"now": "stock.reviewers"}, False), ({"most": 3}, False), ({"now": "stock.reviewers", "most": 0}, False),
    ({"now": "stock.reviewers", "most": True}, False), ({"now": "flow.x", "most": 3}, False),
    ({"now": "stock.reviewers.x", "most": 3}, False), ({"now": "stock.reviewers", "most": 3, "least": 1}, False),
])
def test_a_block_s_pool_is_a_number_or_a_stock_with_its_most(pool, ok):
    """SPEC §9.5: ``pool: N`` or ``pool: {now: stock.NAME, most: N}``, both keys and no others."""
    model = yaml.safe_load((ROOT / "docs/spec-examples/relations.yaml").read_text())
    model["blocks"]["reviewer"]["pool"] = pool
    assert (not list(VALIDATOR.iter_errors(model))) == ok


@pytest.mark.parametrize("faults, ok", [
    ({"healthy": "sensor.reviewers"}, True), ({"healthy": "goal.inbox-short"}, True), ({"healthy": "block.check.up"}, True),
    ({"healthy": "stock.reviewers", "after": "1m"}, False), ({}, False), ({"healthy": "reviewers"}, False),
    ({"healthy": 1}, False), ("sensor.reviewers", False),
])
def test_a_queue_s_faults_say_what_reads_healthy(faults, ok):
    """SPEC §9.5: ``takes: {..., faults: {healthy: sensor.NAME}}``, the one key ``healthy``, a reference."""
    model = yaml.safe_load((ROOT / "docs/spec-examples/relations.yaml").read_text())
    model["blocks"]["reviewer"]["takes"]["faults"] = faults
    assert (not list(VALIDATOR.iter_errors(model))) == ok


@pytest.mark.parametrize("starts_at, ok", [(["review"], True), ("review", True), ([3], False), ({"x": 1}, False)])
def test_a_relation_may_say_the_states_its_targets_stop_blocking_at(starts_at, ok):
    """SPEC §5a, *Relations*: ``starts_at``, a state or a list of them."""
    model = yaml.safe_load((ROOT / "docs/spec-examples/relations.yaml").read_text())
    model["items"]["ticket"]["relations"]["blocked_by"] = {"kind": "ticket", "starts_at": starts_at}
    assert (not list(VALIDATOR.iter_errors(model))) == ok


@pytest.mark.parametrize("path", sorted((ROOT / "tests/spec-invalid").glob("*.yaml")), ids=lambda p: p.stem)
def test_each_broken_file_is_refused(path):
    assert list(VALIDATOR.iter_errors(yaml.safe_load(path.read_text())))
