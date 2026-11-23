import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/work")
from ergostat.numbers import eta, etamodel  # noqa: E402
from tests.eta_backtest import backtest  # noqa: E402
from tests.eta_synthetic import generate, project  # noqa: E402

T0 = 1_790_000_000.0


def gated(d, seed=0):
    p = project(d, pool=20)
    kw = dict(pool=20, gate=4, dev=3 * 3600.0, sigma=0.25, fail=0.1, rework=0.1)
    generate(p, T0, 24, rate=0.8, backlog=0, seed=3 + seed, prefix="h", stop_arrivals=16, **kw)
    generate(p, T0 + 86400, 60, rate=0, backlog=40, seed=4 + seed, prefix="b", **kw)
    return p


variants = {"old": (0.0, 0.0), "a": (30.0, 0.0), "b": (0.0, 0.9), "a+b": (30.0, 0.9)}
for seed in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
    d = Path(tempfile.mkdtemp())
    p = gated(d, seed)
    cuts = [T0 + 86400 + h * 3600 for h in (0.25, 2, 4)]
    print("measured", etamodel._measured(p, p.model.spec, p.model.spec.blocks["dev"], cuts[0]))
    for name, (mr, ms) in variants.items():
        etamodel.MIN_RUN, etamodel.MEASURED = mr, ms
        t = time.time()
        r = backtest(p, p.model.spec, ["ticket"], cuts, {"all": eta.Flags()}, runs=60, budget=6)["all"]
        print(seed, name, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != "kinds"},
              round(time.time() - t, 1), flush=True)
