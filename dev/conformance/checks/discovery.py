"""The checks of ergostat's discovery list (dev/conformance/discovery.yaml): ``discovery.py CASE [--scale=S]
[--family=F]``.

Each runs its algorithm in-process on a record simulated here by a seeded truth written apart from the code it checks
(a fake Prometheus on 127.0.0.1, started and stopped by the check, for the draft). ``--scale`` multiplies each stated
tolerance (0: none, so the check is seen to fail); ``--family`` names the family or form expected instead of the
truth's (a wrong one: unmet). Exit 0: found within tolerance. 1: not found, or outside it. 2: the check's own error."""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import sys
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OPT = {"scale": 1.0, "family": None}


class Unmet(Exception):          # found nothing, or outside its tolerance: exit 1
    pass


def need(ok, why: str) -> None:
    if not ok:
        raise Unmet(why)


def near(got, want: float, rel: float, what: str) -> None:
    tol = rel * OPT["scale"]
    need(got is not None and abs(got - want) <= tol * abs(want), f"{what} {got}, not within {tol:.0%} of {want:g}")


def family(want: str, got) -> None:
    want = OPT["family"] or want
    need(got == want, f"found {got}, not {want}")


def project(tmp: Path, text: str):
    from ergostat import model as mdl
    from ergostat.store import Project
    (tmp / "m").mkdir()
    (tmp / "m" / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp / "m"))


def prometheus_draft(tmp: Path) -> None:
    from ergostat.spec import discover as dc
    from ergostat.spec import read
    meta = {"jobs_queue_depth": [{"type": "gauge", "help": "waiting"}], "jobs_enqueued_total": [{"type": "counter"}],
            "jobs_processed_total": [{"type": "counter"}], "go_goroutines": [{"type": "gauge"}]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"status": "success", "data": meta if self.path.startswith("/api/v1/metadata") else {}})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())
    srv = HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        text, _ = dc.from_prometheus(f"http://127.0.0.1:{srv.server_address[1]}")
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(5)
    (tmp / "draft.yaml").write_text(text)
    spec, problems = read(tmp / "draft.yaml")
    need(not [x for x in problems if x.level == "error"], f"the draft does not compile: {problems}")
    need(set(spec.stocks) == {"jobs-queue-depth"}, f"stocks {sorted(spec.stocks)}, not the gauge alone")
    ends = {(f.source, f.target) for f in spec.flows.values()}
    need(ends == {(None, "jobs-queue-depth"), ("jobs-queue-depth", None)}, f"no flow into and out of the stock: {ends}")


LOOP = """\
stocks:
  queue: {unit: jobs, sensor: {manual: true}}
flows:
  arrivals: {to: queue}
  served: {from: queue, sensor: {manual: true}}
"""


def unwritten_loop(tmp: Path) -> None:
    from ergostat.spec import discover as dc
    p, now, rnd = project(tmp, LOOP), time.time(), random.Random(11)
    for k in range(240):                          # 6h, every 90s; the consumer follows the queue 3 readings (270s) on
        t = now - 6 * 3600 + k * 90
        p.measurements.add("sensor/queue.main", 50 + 40 * math.sin(k / 12) + rnd.gauss(0, 2), t)
        p.measurements.add("sensor/served.main", 100 + 80 * math.sin((k - 3) / 12) + rnd.gauss(0, 4), t)
    found = [f for f in dc.loops(p, p.model.spec, now=now) if f["kind"] == "loop"]
    need([(f["stock"], f["flow"], f["known"]) for f in found] == [("queue", "served", False)], f"loops found: {found}")
    need(abs(found[0]["delay"] - 270) <= 180 * OPT["scale"], f"delay {found[0]['delay']}s, not within 180s of 270s")
    prop = dc.proposal(found, p.model.spec)
    need("goals:" in prop and "type: external" in prop and "out: flow.served" in prop, f"no goal and block: {prop}")


H, K, TAU, THETA = 10.0, 0.2, 60.0, 20.0


def steps(n: int, rnd, every: int, base: float = 25.0) -> list[float]:
    out = []
    for k in range(n):
        out.append(base + rnd.choice([-6, -3, 3, 6]) if k % every == 0 else out[-1])
    return out


def process(integrating: bool) -> None:
    from ergostat.control import ident
    rnd, n, d = random.Random(3), 720, round(THETA / H)
    u = steps(n, rnd, 24) if not integrating else [1.0 if (k // 40) % 2 else -1.0 for k in range(n)]
    a, x, y = math.exp(-H / TAU), (K * u[0] if not integrating else 0.0), []
    for k in range(n):                            # zero-order hold through the lag, d samples late
        y.append((x if not integrating else 0.01 * x) + rnd.gauss(0, 0.004 if not integrating else 0.01))
        ud = u[max(0, k - d)]
        x = a * x + (1 - a) * K * ud if not integrating else x + H * ud
    r = ident.identify(H, [k * H for k in range(n)], u, y)
    family("integrating" if integrating else "fopdt", r.get("form"))
    if integrating:
        near(r["K"], 0.01, 0.10, "k")
    else:
        near(r["K"], K, 0.05, "K")
        near(r["tau"], TAU, 0.15, "tau")


def law_record(fam: str, seed: int = 5, n: int = 1200, change_at: int | None = None):
    """xs, us and dt of a controller of ``fam`` on a seeded input, written apart from extlaw."""
    rnd, xs, us = random.Random(seed), [], []
    if fam in ("proportional", "pi"):
        y, u = 40.0, 5.0
        for i in range(n):
            if fam == "proportional":
                y += rnd.gauss(0, 1) + 0.05 * (8 - y)
                xs.append(y)
                us.append(2.0 + 0.5 * xs[max(0, i - 2)] + rnd.gauss(0, 0.05))
            else:
                y += (2 * u + 10 * math.sin(i / 60) - y) * 0.1 + rnd.gauss(0, 0.5)
                xs.append(y)
                x, xp = xs[max(0, i - 1)], xs[max(0, i - 2)]
                u = u - 0.8 * (x - xp) - 0.2 * (x - 50) if abs(x - 50) > 1 else u
                us.append(u)
        return xs, us, 10.0
    up, down, reps, since, run_up, run_dn, firing = 0.7, 0.4, 4, 10 ** 6, 0, 0, 0
    for k in range(n):
        if fam == "onoff":                        # an alert: on above 300 for 45s, off below 250
            x = 240 + 90 * math.sin(2 * math.pi * k / 130) * (0.6 + 0.4 * math.sin(k / 211)) + rnd.gauss(0, 15)
            run_up = run_up + 1 if x > 300 else 0
            firing = 1 if not firing and run_up >= 4 else 0 if firing and x < 250 else firing
            xs.append(x)
            us.append(float(firing))
            continue
        if k == change_at:
            up, down = 0.6, 0.3
        load = 3 + 2.5 * math.sin(2 * math.pi * k / 400) + 1.5 * math.sin(2 * math.pi * k / 97) + rnd.gauss(0, 0.3)
        util = max(0.0, load / reps + rnd.gauss(0, 0.03))
        since += 1
        run_up, run_dn = (run_up + 1 if util > up else 0), (run_dn + 1 if util < down else 0)
        if reps < 20 and run_up >= 3 and since >= 4:              # a stepper: one more pod past 0.7 for 30s ...
            reps, since = reps + 1, 0
        elif reps > 2 and run_dn >= 5 and since >= 20:           # ... one fewer under 0.4 for 60s, 5m after a move
            reps, since = reps - 1, 0
        xs.append(util)
        us.append(float(reps))
    return xs, us, 15.0


def law(fam: str):
    def check(tmp: Path) -> None:
        from ergostat.numbers import extlaw as el
        best, laws, why = el.fit(*law_record(fam))
        family(fam, best.family if best else why)
    return check


def law_changed(tmp: Path) -> None:
    from ergostat.numbers import extlaw as el
    changed = getattr(el, "changed", None)
    need(callable(changed), "no test of a law changed: extlaw has no changed(xs, us, dt)")
    need(changed(*law_record("stepper", change_at=600)), "a controller retuned halfway is not said changed")
    alarms = sum(bool(changed(*law_record("stepper", seed=s))) for s in range(30))
    need(alarms <= 1, f"{alarms} false alarms over 30 unchanged seeds (at most 1)")


HPA = """\
stocks:
  replicas: {unit: pods, sensor: {manual: true}}
auxiliaries:
  utilisation: {unit: pods/pods, sensor: {manual: true}}
flows:
  scale: {to: replicas, two-way: true}
blocks:
  hpa:
    type: external
    in: auxiliary.utilisation
    out: flow.scale
    identify: {input: auxiliary.utilisation, output: stock.replicas}
    law: {kind: kubernetes-hpa, target: 0.7, min: 2, max: 20, stabilize-down: 5m}
"""


def law_kubernetes_hpa(tmp: Path) -> None:
    from ergostat.numbers import extlaw as el
    from ergostat.spec import read
    (tmp / "hpa.yaml").write_text(HPA)
    spec, problems = read(tmp / "hpa.yaml")
    need(not [x for x in problems if x.level == "error"], f"law: kubernetes-hpa not accepted: {problems}")
    rnd, reps, wants, xs, us = random.Random(9), 4, [], [], []
    for k in range(1200):                         # the HPA's documented rule, every 15s, stabilised down over 5m
        load = 3 + 2.5 * math.sin(2 * math.pi * k / 400) + rnd.gauss(0, 0.3)
        util = max(0.0, load / reps + rnd.gauss(0, 0.03))
        wants = (wants + [math.ceil(reps * util / 0.7) if abs(util / 0.7 - 1) > 0.1 else reps])[-20:]
        xs.append(util)
        us.append(float(reps))
        reps = min(20, max(2, wants[-1] if wants[-1] > reps else max(wants)))
    best, _, why = el.fit(xs, us, 15.0)
    family("ratio", best.family if best else why)
    near(best.p.get("target"), 0.7, 0.10, "target")


CHAIN = """\
parameters:
  r: {value: 3, unit: 1/h}
  k: {value: 2, unit: 1/h}
stocks:
  upstream: {unit: jobs, sensor: {manual: true}}
  downstream: {unit: jobs, sensor: {manual: true}}
flows:
  arrivals: {to: upstream, sensor: {manual: true}}
  moving:
    from: upstream
    to: downstream
    driven-by: +stock.upstream
    equation: r * stock.upstream
  done: {from: downstream, driven-by: +stock.downstream, equation: k * stock.downstream}
"""


def structure_from_residuals(tmp: Path) -> None:
    """A chain missing the stock in transit between its two stocks (0.1h, first order): the residuals propose it."""
    from ergostat.numbers import observe as ob
    from ergostat.numbers import structural as stc
    p, now, rnd = project(tmp, CHAIN), time.time(), random.Random(0)
    start, dt, tau = now - 7200, 1 / 3600, 0.1
    rates = [rnd.choice((10.0, 20.0, 30.0, 40.0)) for _ in range(13)]       # a step every ten minutes
    up, transit, down = rates[0] / 3, rates[0] * tau, rates[0] / 2           # at equilibrium
    for sec in range(7200):
        a = rates[sec // 600]
        if sec % 30 == 0:
            p.measurements.add("sensor/arrivals.main", a, at=start + sec)
        if sec % 60 == 59:
            p.measurements.add("sensor/upstream.main", up + rnd.gauss(0, 0.02), at=start + sec)
            p.measurements.add("sensor/downstream.main", down + rnd.gauss(0, 0.02), at=start + sec)
        out = transit / tau
        up, transit, down = up + (a - 3 * up) * dt, transit + (3 * up - out) * dt, down + (out - 2 * down) * dt
    found, _ = stc.find(p, p.model.spec, ob.measured(p, ob.reference(p, now)))
    got = [x for x in found if x.get("code") == "residual-hidden-stock" and x.get("target") == "stock.downstream"]
    family("residual-hidden-stock", got[0]["code"] if got else [x.get("code") for x in found])
    need(any(x.startswith("stock.") for x in got[0].get("new_parts") or []), f"no stock added: {got[0].get('new_parts')}")
    near((got[0].get("residual") or {}).get("tau"), tau, 0.5, "tau (h)")    # τ is tried at ½, 1 and 2 times the lag


CASES = {"prometheus-draft": prometheus_draft, "unwritten-loop": unwritten_loop,
         "process-fopdt": lambda tmp: process(False), "process-integrating": lambda tmp: process(True),
         **{f"law-{f}": law(f) for f in ("onoff", "proportional", "pi", "stepper")},
         "law-changed": law_changed, "law-kubernetes-hpa": law_kubernetes_hpa,
         "structure-from-residuals": structure_from_residuals}


def main(argv: list[str]) -> int:
    opts = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    if not argv or argv[0] not in CASES or len(opts) != len(argv) - 1 or not set(opts) <= set(OPT):
        print(f"usage: discovery.py {{{','.join(CASES)}}} [--scale=S] [--family=F]", file=sys.stderr)
        return 2
    try:
        OPT.update(scale=float(opts.get("scale", 1.0)), family=opts.get("family"))
        tmp, home = Path(tempfile.mkdtemp(prefix="conformance-discovery-")), os.environ.get("ERGOSTAT_HOME")
        try:
            os.environ["ERGOSTAT_HOME"] = str(tmp / "home")
            sys.path.insert(0, str(ROOT))
            CASES[argv[0]](tmp)
        finally:
            os.environ.pop("ERGOSTAT_HOME") if home is None else os.environ.update(ERGOSTAT_HOME=home)
            shutil.rmtree(tmp, ignore_errors=True)
            OPT.update(scale=1.0, family=None)
    except Unmet as e:
        print(f"unmet: {e}", file=sys.stderr)
        return 1
    except Exception as e:                        # the check's own error: broken, never read as unmet
        print(f"broken: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print("met")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
