"""The sensors-by-part cache of ``state._sensor_for``: another model swapping it between the check and the read never
hands a call another model's sensors (review lesson 1)."""
from types import SimpleNamespace

from ergostat import state


def _model(**measures):
    return SimpleNamespace(sensors={name: SimpleNamespace(name=name, measures=part) for name, part in measures.items()})


class _Swapping(dict):
    """A model's sensors whose length, once asked twice, first lets another model take the cache: the competing
    write, put in the gap between the cache's check and its read."""

    def __init__(self, other, *a, **kw):
        super().__init__(*a, **kw)
        self.other, self.asked = other, 0

    def __len__(self):
        self.asked += 1
        if self.asked == 2:
            state._sensor_for(self.other, "queue")
        return super().__len__()


def test_a_model_taking_the_cache_between_its_check_and_its_read_does_not_change_the_answer(monkeypatch):
    monkeypatch.setattr(state, "_BY", (None, 0, {}))
    other = _model(theirs="queue")
    mine = SimpleNamespace(sensors=_Swapping(other, {"ours": SimpleNamespace(name="ours", measures="queue")}))
    assert [s.name for s in state._sensor_for(mine, "queue")] == ["ours"]    # builds the cache (len asked once)
    assert [s.name for s in state._sensor_for(mine, "queue")] == ["ours"]    # the other model swaps it mid-call
    assert [s.name for s in state._sensor_for(other, "queue")] == ["theirs"]


def test_two_models_asked_in_turn_each_get_their_own_sensors(monkeypatch):
    monkeypatch.setattr(state, "_BY", (None, 0, {}))
    a, b = _model(x="stock", y="flow"), _model(z="stock")
    for _ in range(3):
        assert [s.name for s in state._sensor_for(a, "stock")] == ["x"]
        assert [s.name for s in state._sensor_for(b, "stock")] == ["z"]
        assert state._sensor_for(b, "flow") == []
    a.sensors["w"] = SimpleNamespace(name="w", measures="stock")            # a sensor added: the cache is built again
    assert [s.name for s in state._sensor_for(a, "stock")] == ["x", "w"]
