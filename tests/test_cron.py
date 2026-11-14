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
    assert a.cron == "0 3 * * *" and a.schedule == "daily at 03:00"
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('"0 3 * * *"', '"0 3 * *"'))
    with pytest.raises(model.ModelError, match="five fields"):
        model.load(repo.path)


def test_a_day_field_with_a_step_counts_as_unrestricted_as_in_vixie_cron():
    c = Cron("0 0 */2 * 1")                              # odd days AND Mondays, not either
    assert not c.matches(at("2026-11-03 00:00")) and not c.matches(at("2026-11-16 00:00")) and c.matches(at("2026-11-09 00:00"))


def test_rare_and_impossible_schedules():
    nxt = datetime.fromtimestamp(Cron("0 0 29 2 *").next_after(at("2028-03-01 00:00").timestamp()))
    assert nxt == at("2032-02-29 00:00")
    with pytest.raises(CronError, match="never matches"):
        Cron("0 0 31 2 *").next_after(at("2026-11-14 00:00").timestamp())


def test_the_hour_the_clocks_repeat_runs_twice(monkeypatch):
    import time as _t
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    _t.tzset()
    try:
        c = Cron("*/5 * * * *")
        t = datetime(2026, 11, 1, 1, 2).timestamp()       # 01:02 PDT, an hour before the clocks go back
        steps = []
        for _ in range(15):
            n = c.next_after(t)
            steps.append(n - t)
            t = n
        assert steps[0] == 180 and all(s == 300 for s in steps[1:])
    finally:
        monkeypatch.undo()
        _t.tzset()
