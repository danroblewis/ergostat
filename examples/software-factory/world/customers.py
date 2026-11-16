"""The market: one tick of customers using whatever textkit is deployed.

Each tick, the users send requests (more users, more requests, and a wider range of operations:
the long tail arrives as the product grows). Every answer is judged against the world's truth
(oracle.py). The world also probes each operation in demand with a fixed set of inputs, the way
an uptime check would, which is what the product's sensors read: how many operations in demand
are broken (wrong answers or errors), and how many do not exist yet.

Users come when what they ask for works and leave when it does not: signups grow with the share
of requests answered right (and slow as the market fills), churn with the share answered wrong. That is the product's own
stock-and-flow system, and the only place the factory's work shows as an outcome.

Prints what it moved (signups, churn) as JSON lines; keeps its state in run/world/."""

from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402

RUN = ROOT / "run"
STATE = RUN / "world" / "state.json"
COMPLAINTS = RUN / "world" / "complaints.json"
PROD = RUN / "prod" / "textkit.py"

START_USERS = 20.0
MARKET = 250.0              # everyone who could use textkit: growth slows as it fills
SIGNUP_RATE = 0.10          # per tick, of users, when every answer is right (word of mouth)
CHURN_RATE = 0.30           # per tick, of users, scaled by the share answered wrong
BASE_CHURN = 0.01           # per tick, of users, who leave anyway
PROBES = 24                 # the uptime check's inputs per operation


def demanded(users: float) -> list[str]:
    """The operations customers use: the most wanted first, more of the tail as there are more of them."""
    k = min(len(oracle.OPS), 6 + int(users // 12))
    return [f.__name__ for f in oracle.OPS[:k]]


def serve(reqs: list[dict]) -> list[dict]:
    if not PROD.exists():
        subprocess.run([sys.executable, str(ROOT / "bin" / "factory.py"), "init"], check=True, capture_output=True)
    try:
        p = subprocess.run([sys.executable, "-I", str(HERE / "serve.py"), str(PROD)], input=json.dumps(reqs),
                           capture_output=True, text=True, timeout=20, cwd=str(PROD.parent))
        return json.loads(p.stdout) if p.returncode == 0 else [{"error": f"the service crashed: {p.stderr[-200:]}"}] * len(reqs)
    except subprocess.TimeoutExpired:
        return [{"error": "no answer within 20s"}] * len(reqs)
    except ValueError:
        return [{"error": "the service answered nonsense"}] * len(reqs)


def judge(req: dict, ans: dict) -> tuple[str, dict]:
    want = oracle.BY_NAME[req["op"]](req["input"])
    if ans.get("missing"):
        return "missing", {}
    if "error" in ans:
        return "error", {"input": req["input"], "expected": want, "error": ans["error"]}
    if ans.get("got") != want:
        return "wrong", {"input": req["input"], "expected": want, "got": ans.get("got")}
    return "ok", {}


def tick() -> dict:
    state = json.loads(STATE.read_text()) if STATE.exists() else {"users": START_USERS, "ticks": 0}
    users = float(state["users"])
    ops = demanded(users)
    rng = random.Random(time.time_ns())
    weights = [1 / (i + 1) ** 0.8 for i in range(len(ops))]
    n = int(min(300, 10 + users * 2))
    reqs = [{"op": rng.choices(ops, weights)[0], "input": oracle.phrase(rng)} for _ in range(n)]
    probe_rng = random.Random(42)
    probes = [{"op": op, "input": oracle.phrase(probe_rng, digits=i % 3 == 0)} for op in ops for i in range(PROBES)]
    answers = serve(reqs + probes)

    per_op: dict[str, dict] = {op: {"asked": 0, "ok": 0, "wrong": 0, "error": 0, "missing": 0, "examples": []} for op in ops}
    for i, (req, ans) in enumerate(zip(reqs + probes, answers, strict=False)):
        verdict, ex = judge(req, ans)
        s = per_op[req["op"]]
        if i < len(reqs):
            s["asked"] += 1
            s[verdict] += 1
        elif verdict != "ok":
            s["probe_" + verdict] = s.get("probe_" + verdict, 0) + 1
        if ex and len(s["examples"]) < 4 and ex not in s["examples"]:
            s["examples"].append(ex)

    ok = sum(s["ok"] for s in per_op.values())
    ok_share = ok / max(1, len(reqs))
    missing = [op for op, s in per_op.items() if s["missing"] or s.get("probe_missing")]
    broken = [op for op, s in per_op.items() if op not in missing and
              (s["wrong"] or s["error"] or s.get("probe_wrong") or s.get("probe_error"))]
    signups = (users * SIGNUP_RATE * ok_share ** 3 + 0.5) * max(0.0, 1 - users / MARKET)
    churn = users * (BASE_CHURN + CHURN_RATE * (1 - ok_share) ** 1.5)
    users = max(1.0, users + signups - churn)

    complaints = {}
    for op in broken + missing:
        s = per_op[op]
        kind = "missing" if op in missing else "error" if (s["error"] or s.get("probe_error")) else "wrong"
        complaints[op] = {"kind": kind, "asked": s["asked"], "failed": s["wrong"] + s["error"] + s["missing"],
                          "examples": s["examples"], "description": oracle.DESCRIPTIONS[op]}
    state = {"users": round(users, 2), "ticks": state.get("ticks", 0) + 1, "at": time.time(), "demanded": ops,
             "broken": broken, "missing": missing, "requests": len(reqs), "ok_share": round(ok_share, 3),
             "signups": round(signups, 2), "churn": round(churn, 2)}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for path, data in ((STATE, state), (COMPLAINTS, complaints)):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(path)
    return state


if __name__ == "__main__":
    s = tick()
    print(f"{s['requests']} requests, {s['ok_share']:.0%} right; broken: {', '.join(s['broken']) or 'none'}; "
          f"missing: {', '.join(s['missing']) or 'none'}; users {s['users']}", file=sys.stderr)
    print(json.dumps({"out": "flow.signups", "moved": s["signups"]}))
    print(json.dumps({"out": "flow.churn", "moved": s["churn"]}))
