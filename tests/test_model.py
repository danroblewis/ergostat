import pytest

from ergostat import model
from tests.conftest import DISK


def parse(text):
    import tomllib
    return model.parse(tomllib.loads(text))


def test_the_disk_model_has_one_closed_loop():
    m = parse(DISK)
    (lp,) = m.loops()
    assert lp.name == "disk-under-80" and lp.closes and lp.sensors == ["disk-usage"] and lp.valves == ["delete-old-files"]
    assert m.flows["logs-written"].disturbance and m.valve_of("cleaned").name == "delete-old-files"
    assert [r.name for r in m.roles_of("cleaner")] == ["disk-usage", "disk-under-80", "delete-old-files"]
    assert model.check(m) == []


def test_a_loop_without_a_valve_on_its_stock_cannot_close():
    m = parse(DISK.replace('drives = ["delete-old-files"]', "drives = []"))
    (lp,) = m.loops()
    assert not lp.closes and "none of its valves" in lp.gaps[0]
    assert any("cannot close" in msg for _, msg in model.check(m))


def test_errors_name_what_does_not_resolve():
    m = parse(DISK.replace('measures = "disk-used"', 'measures = "disk-usd"'))
    errors = [msg for lv, msg in model.check(m) if lv == "error"]
    assert errors == ["sensor disk-usage: 'disk-usd' is neither a stock nor a flow"]


@pytest.mark.parametrize("bad, says", [
    ('[[stok]]\nname = "x"', "unknown table 'stok'"),
    ('[[stock]]\nname = "Bad Name"', "a name is required"),
    ('[[stock]]\nname = "x"\ncolour = "red"', "unknown key 'colour'"),
    ('[[agent]]\nname = "x"\nkind = "robot"', "kind: one of"),
    ('[[controller]]\nname = "c"\nsetpoint = "about 80"', "setpoint: like"),
    ('[[disturbance]]\nname = "d"', "say which stock it pushes"),
])
def test_what_the_file_refuses(bad, says):
    with pytest.raises(model.ModelError, match=says):
        parse(bad)


def test_names_are_unique_across_parts():
    with pytest.raises(model.ModelError, match="already used by a stock"):
        parse('[[stock]]\nname = "x"\n[[flow]]\nname = "x"\nto = "x"')


def test_a_controller_error_is_signed_and_zero_inside_its_setpoint():
    c = model.Controller(name="c", holds="s", setpoint="<= 80")
    assert c.error(70) == 0 and c.error(85) == 5
    assert model.Controller(name="c", holds="s", setpoint=">= 3").error(1) == -2
    assert model.Controller(name="c", holds="s", setpoint="== 0").error(2) == 2


def test_a_system_brings_what_is_attached_to_its_stocks():
    m = parse(DISK)
    assert m.members("host") == {"disk-used", "logs-written", "cleaned", "delete-old-files", "disk-usage", "disk-under-80"}
    assert m.system_names() == ["host"] and m.members(None) >= m.members("host")


def test_the_ladder_runs_from_person_to_rule():
    assert model.KINDS == ("person", "ai", "narrow-ai", "decision", "program", "rule")
    assert parse(DISK).agents["cleaner"].rung == 4
