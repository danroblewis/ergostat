from datetime import datetime

import pytest

from ergostat.cron import Cron, CronError


def at(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def test_fields_lists_ranges_and_steps():
    c = Cron("*/15 8-18 * * 1-5")
    assert c.matches(at("2026-11-16 08:30"))            # a Monday
    assert not c.matches(at("2026-11-16 08:31"))
    assert not c.matches(at("2026-11-15 08:30"))        # a Sunday
    assert Cron("0 3 * * 0").matches(at("2026-11-15 03:00")) and Cron("0 3 * * 7").matches(at("2026-11-15 03:00"))


def test_either_day_field_when_both_are_restricted():
    c = Cron("0 0 1 * 1")                               # the 1st, or any Monday
    assert c.matches(at("2026-12-01 00:00")) and c.matches(at("2026-11-16 00:00")) and not c.matches(at("2026-11-17 00:00"))


def test_next_after():
    c = Cron("30 2 * * *")
    nxt = datetime.fromtimestamp(c.next_after(at("2026-11-14 07:00").timestamp()))
    assert nxt == at("2026-11-15 02:30")


@pytest.mark.parametrize("bad", ["* * *", "61 * * * *", "* 24 * * *", "*/0 * * * *", "a * * * *"])
def test_refused(bad):
    with pytest.raises(CronError):
        Cron(bad)


def test_an_agent_takes_a_cron_schedule(repo):
    from ergostat import model
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('every = "1s"', 'cron = "0 3 * * *"'))
    a = model.load(repo.path).agents["cleaner"]
    assert a.cron == "0 3 * * *" and a.schedule == "cron 0 3 * * *"
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('"0 3 * * *"', '"0 3 * *"'))
    with pytest.raises(model.ModelError, match="five fields"):
        model.load(repo.path)
