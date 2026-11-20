"""What leaving refused expiries out costs (``leases/fold.py`` ``refused_expiries``): the measures, the estimates and the
block models read what each item refused from the item index, never folding an item again, so many expired items
with long transcripts cost them about what they cost before refused expiries were left out."""

import textwrap
import time
import uuid

from ergostat import model as mdl
from ergostat.leases import EXPIRED, TAKEN, fold, measures
from ergostat.numbers import blockmodels, etamodel
from ergostat.numbers import observe as ob
from ergostat.store import Project

from .test_closedloop import TAKES

ITEMS, LINES = 300, 200


def busy(tmp_path):
    """``ITEMS`` jobs, each taken and expired, each with a transcript of ``LINES`` lines."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(TAKES))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    evs = []
    for i in range(ITEMS):
        t, run, job = now - 3000 + i, uuid.uuid4().hex, f"job/{i}"
        lease = {"item": job, "run": run, "block": "developer", "fence": 1}
        evs.append({"type": "job.opened", "item": job, "source": "t", "at": t - 100})
        evs.append({"type": TAKEN, "item": job, "source": "ergostat", "at": t - 50,
                    "data": {**lease, "ttl": 10, "max": 3, "back": "ready"}})
        evs += [{"type": "claude.assistant", "item": job, "source": "claude", "at": t - 40 + j * 0.001,
                 "data": {"text": "x" * 200}} for j in range(LINES)]
        evs.append({"type": EXPIRED, "item": job, "source": "ergostat", "at": t, "data": {**lease, "state": "ready"}})
    evs += [{"type": "agent.ran", "item": "developer", "at": now - 2000 + i * 50,
             "data": {"exit": 0, "seconds": 60.0, "item": f"job/{i}"}} for i in range(20)]
    p.events.add_many(evs)
    return p, p.model.spec, now


def fastest(f, n: int = 3) -> float:
    best = float("inf")
    for _ in range(n):
        t0 = time.perf_counter()
        f()
        best = min(best, time.perf_counter() - t0)
    return best


def test_many_expired_items_with_long_transcripts_cost_about_what_they_did(tmp_path, monkeypatch):
    p, spec, now = busy(tmp_path)
    reads = {
        "measures.counts": lambda: measures.counts(p, spec, now=now),
        "measures.counts@developer": lambda: measures.counts(p, spec, "developer", now=now),
        "etamodel.read": lambda: etamodel.read(p, spec, ["job"], now),
        "blockmodels.identify": lambda: blockmodels.identify(p, spec, ob.measured(p, ob.Grid(now - 3600, now, 60))),
    }
    assert measures.counts(p, spec, now=now)["expired"] == ITEMS                # (and the index caught up)
    query = p.events.query
    per_item = []

    def counting(**kw):
        if kw.get("item", "").startswith("job/"):
            per_item.append(kw["item"])
        return query(**kw)
    monkeypatch.setattr(p.events, "query", counting)
    now_cost = {k: fastest(f) for k, f in reads.items()}
    assert not per_item, "no item's events read again, its transcript least of all"
    monkeypatch.setattr(p.events, "query", query)
    for m in (measures, etamodel, blockmodels):                              # as on main: nothing left out
        monkeypatch.setattr(fold, "refused_expiries", lambda *a, **k: set())
        if hasattr(m, "refused_expiries"):
            monkeypatch.setattr(m, "refused_expiries", lambda *a, **k: set())
    before = {k: fastest(f) for k, f in reads.items()}
    for k in reads:
        assert now_cost[k] <= 2 * before[k] + 0.05, f"{k}: {now_cost[k]:.3f}s, against {before[k]:.3f}s without"
