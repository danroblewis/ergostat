"""How far a goal is from its bound, in the one phrase every surface outside Blocks prints (state.off_by_words)."""

from ergostat.model import Controller
from ergostat.state import off_by_words


def words(setpoint, value, tolerance=0.0, unit=""):
    c = Controller(name="g", holds="s", setpoint=setpoint, tolerance=tolerance)
    return off_by_words(setpoint, c.error(value), tolerance, unit)


def test_past_a_ceiling_or_a_floor_it_is_off_by_the_distance_in_its_unit():
    assert words("<= 0", 36, unit="tickets") == "off by 36 tickets"
    assert words("<= 0", 0, unit="tickets") == "within its bound"
    assert words(">= 10", 4.5, unit="ideas") == "off by 5.5 ideas"
    assert words(">= 10", 12, unit="ideas") == "within its bound"
    assert off_by_words("≥ 10", 6.0, 0, "ideas") == "off by 6 ideas"   # the bound as the pages write it


def test_a_setpoint_with_a_band_says_short_over_or_within():
    assert words("== 180", 152, tolerance=5, unit="tickets") == "28 short of 180 tickets"
    assert words("== 80", 92, tolerance=5, unit="%") == "12 over 80%"
    assert words("== 80", 83, tolerance=5, unit="%") == "within its band"
    assert words("<= 5", 6, tolerance=1, unit="tickets") == "within its band"   # past a ceiling, inside its tolerance
    assert words("== 80", 80, unit="%") == "on its setpoint"


def test_a_goal_with_no_unit_says_the_bare_number_and_an_unknown_one_says_nothing():
    assert words("<= 3", 7) == "off by 4"
    assert words("== 10", 7) == "3 short of 10"
    assert off_by_words("<= 3", None) is None
    assert off_by_words("", -2.0) is None


def test_attention_and_the_dynamics_cards_print_the_states_phrase():
    from ergostat import state
    from ergostat.dynamics import attention as sd
    lp = {"status": "off", "stock": "backlog", "value": 12.0, "setpoint": "<= 5", "error": -7.0, "band": " (+1)",
          "off_by_words": "off by 7 tickets", "gaps": []}
    att = state.attention({"loops": {"short-backlog": lp}, "inbox": [], "hints": [], "agents": {}, "residuals": {}}, running=False)
    says = [a["says"] for a in att if a["what"] == "loop short-backlog"]
    assert says == ["backlog is 12, setpoint <= 5 (+1) (off by 7 tickets)"], att
    assert sd(att, {"loops": {"short-backlog": lp}})[0]["says"] == "backlog is 12, desired backlog = 5: off by 7 tickets"
