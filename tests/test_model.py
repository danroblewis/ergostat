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
    assert errors[0].startswith("sensor disk-usage: 'disk-usd' is neither a stock nor a flow; declare it")


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


def test_the_error_is_r_minus_y_and_zero_on_the_satisfied_side():
    c = model.Controller(name="c", holds="s", setpoint="<= 80")
    assert c.error(70) == 0 and c.error(85) == -5          # too high: negative, as e = r − y
    assert model.Controller(name="c", holds="s", setpoint=">= 3").error(1) == 2
    assert model.Controller(name="c", holds="s", setpoint="== 0").error(2) == -2


def test_the_tolerance_is_a_hysteresis_band_on_the_side_that_matters():
    c = model.Controller(name="c", holds="s", setpoint="<= 10", tolerance=2)
    assert c.status(11) == "holding" and c.status(13) == "off"           # off only past 10 + 2
    assert c.status(11, was_off=True) == "off" and c.status(10, was_off=True) == "holding"   # back only at 10
    assert c.band_text() == " (+2)" and model.Controller(name="c", holds="s", setpoint=">= 1", tolerance=1).band_text() == " (−1)"


def test_a_strict_bound_counts_the_bound_as_outside():
    assert model.Controller(name="c", holds="s", setpoint="< 10").status(10) == "off"
    assert model.Controller(name="c", holds="s", setpoint="<= 10").status(10) == "holding"
    assert model.Controller(name="c", holds="s", setpoint="> 0").status(0) == "off"


def test_a_system_brings_what_is_attached_to_its_stocks():
    m = parse(DISK)
    assert m.members("host") == {"disk-used", "logs-written", "cleaned", "delete-old-files", "disk-usage", "disk-under-80"}
    assert m.system_names() == ["host"] and m.members(None) >= m.members("host")


def test_the_ladder_runs_from_person_to_rule():
    assert model.KINDS == ("person", "ai", "narrow-ai", "decision", "program", "rule")
    assert parse(DISK).agents["cleaner"].rung == 4


def test_the_guides_shipped_with_ergostat_match_the_docs():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / "ergostat/help/agents.md").read_text() == (root / "docs/writing-agents.md").read_text()
    assert (root / "ergostat/help/ai-agents.md").read_text() == (root / "docs/ai-agents.md").read_text()


def test_a_disturbance_may_name_the_agent_whose_doing_it_is(repo):
    from ergostat import graph, model, state
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text().replace('into = "disk-used"', 'into = "disk-used"\nagent = "writer"')
    text += '\n[[agent]]\nname = "writer"\nkind = "program"\ncommand = "true"\nevery = "1m"\n'
    repo.write("ergostat.toml", text)
    m = model.load(repo.path)
    assert m.flows["logs-written"].agent == "writer"
    assert not [x for _, x in model.check(m) if "writer" in x]                 # a load, not an agent filling nothing
    p = Project(m)
    snap = state.snapshot(p)
    parts = graph.select(m, None, None, 1)
    (d,) = [n for n in graph.control(m, snap, parts)["nodes"] if n["id"] == "flow:logs-written"]
    assert d["agent"]["name"] == "writer"
    w = graph.wiring(m, p, snap, parts)
    assert any(e["source"] == "agent:writer" and e["target"] == "agent:cleaner" for e in w["edges"])
    repo.write("ergostat.toml", text.replace('agent = "writer"\n', 'agent = "nobody"\n', 1))
    assert any("nobody" in x for lv, x in model.check(model.load(repo.path)) if lv == "error")


def test_an_open_loop_reads_nothing_and_is_judged_by_what_watches_its_stock(repo):
    from ergostat import graph, model, state
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text().replace('reads = ["disk-usage"]\n', 'open_loop = true\n')
    repo.write("ergostat.toml", text)
    m = model.load(repo.path)
    (lp,) = m.loops()
    assert lp.open_loop and lp.closes and lp.sensors == ["disk-usage"]          # watched by the stock's sensor
    p = Project(m)
    p.measurements.add("sensor/disk-usage", 90.0)
    snap = state.snapshot(p)
    assert snap["loops"]["disk-under-80"]["status"] == "off"
    g = graph.control(m, snap, graph.select(m, None, None, 1))
    assert not [e for e in g["edges"] if e["kind"] == "signal"]                  # nothing fed back
    assert g["loops"]["disk-under-80"]["openLoop"]
    w = graph.wiring(m, p, snap, graph.select(m, None, None, 1))
    assert not w["cycles"]
    repo.write("ergostat.toml", text.replace("open_loop = true\n", 'open_loop = true\nreads = ["disk-usage"]\n'))
    assert any("open_loop reads nothing" in x for _, x in model.check(model.load(repo.path)))
