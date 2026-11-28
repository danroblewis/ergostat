"""A refused reload leaves a record (reload.noted, SPEC §9.1): model.refused when the files are refused (or refused
otherwise), model.taken when they load again; reload.json kept for the page's mark of the refusal now."""

from __future__ import annotations

from ergostat import reload as rl


def test_a_refusal_and_its_fix_are_events_and_the_same_errors_again_are_not(project):
    p = project
    assert rl.noted(p, None) is None                                   # loading, and nothing refused before: nothing
    bad = ["ergostat.yaml:3: flow x: no such stock"]
    e = rl.noted(p, bad, "v1")
    assert e["type"] == rl.REFUSED and e["data"]["errors"] == bad and e["data"]["running"] == "v1"
    assert e["data"]["where"] == "ergostat.yaml:3" and rl.read_state(p.dir)["errors"] == bad   # the page's mark
    assert rl.noted(p, bad, "v1") is None                              # the same errors again: nothing new
    worse = bad + ["ergostat.yaml:9: goal y: no such stock"]
    assert rl.noted(p, worse, "v1")["data"]["errors"] == worse          # other errors: recorded
    took = rl.noted(p, None)
    assert took["type"] == rl.MODEL_TAKEN and took["data"]["errors"] == worse and took["data"]["was_running"] == "v1"
    assert took["data"]["refused_since"] and rl.read_state(p.dir) is None
    assert rl.noted(p, None) is None
    assert [x["type"] for x in p.events.query(n=None, type="model.refused,model.taken")] == \
        [rl.REFUSED, rl.REFUSED, rl.MODEL_TAKEN]
