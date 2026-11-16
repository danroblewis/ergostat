"""One tick of customers: a batch of images arrives and is served.

Every image goes through production (run/prod). While an experiment runs, the same images also go
through the candidate build (run/candidate), so the two are compared image by image, on exactly
the same pictures; and for the share of images the rollout gives it, the candidate's answer is the
one served. What was served is what the product's sensors read (world/read.py):

    quality        SSIM of what was served (1.0: identical), the 10th percentile over the last 48
                   images: nine in ten look at least this good (an average would hide bad photos
                   behind screenshots, which look perfect at any setting)
    bytes-per-mp   kilobytes served per megapixel, over the same images: what we make smaller
    failures       % of those images the service failed on
    time           95th percentile milliseconds to compress one
    batch-*        the same of the ten images this tick served (the slowest, for time): what the
                   windows above smooth
    flat-share     how much of the mix is flat images (screenshots, line art, logos): the disturbance

and, while a candidate runs, the comparison, as 90% confidence bounds over the images both saw:

    bytes-saved    % fewer bytes than production (low, high)
    quality-change SSIM gained over production (low, high)
    candidate-failures, candidate-time, paired (images compared)

Prints the mix it served from, the auxiliary this block sets (an input from outside the model)."""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import images  # noqa: E402

RUN = ROOT / "run"
STATE, WINDOW = RUN / "world" / "state.json", RUN / "world" / "window.json"
BATCH, KEEP, RECENT = 10, 400, 48


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def serve(build: Path, batch: list, settings: dict) -> list[dict]:
    try:
        p = subprocess.run([sys.executable, str(HERE / "serve.py"), str(build)], input=json.dumps({"images": batch, "settings": settings}),
                           capture_output=True, text=True, timeout=120)
        got = json.loads(p.stdout) if p.returncode == 0 else None
    except (subprocess.TimeoutExpired, ValueError):
        got = None
    return got if isinstance(got, list) and len(got) == len(batch) else [{"error": "the build crashed or hung"}] * len(batch)


def bounds(xs: list[float]) -> tuple[float, float, float]:
    """Mean and a 90% confidence interval (normal approximation; wide when there are few)."""
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else 0.0), -1e9, 1e9
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    half = 1.645 * sd / math.sqrt(n) if n >= 6 else 1e9
    return m, m - half, m + half


def p95(xs: list[float]) -> float:
    return sorted(xs)[int(0.95 * (len(xs) - 1))] if xs else 0.0


def tick() -> dict:
    if not (RUN / "prod" / "squeeze.py").exists():
        subprocess.run([sys.executable, str(ROOT / "bin" / "lab.py"), "init"], check=True, capture_output=True)
    now = time.time()
    settings = load(RUN / "settings.json", {"quality": 80})
    rollout = load(RUN / "rollout.json", {"candidate": None, "share": 0.0})
    n = load(STATE, {}).get("ticks", 0) + 1
    batch = images.batch(now, BATCH, seed=int(now))
    prod = serve(RUN / "prod", batch, settings)
    cid = rollout.get("candidate") if (RUN / "candidate" / "squeeze.py").exists() else None
    # the candidate runs at production's quality plus the matcher's offset: compared at equal quality
    offset = float(rollout.get("offset") or 0) if rollout.get("offset_for") == cid else 0.0   # the matcher's, for this candidate
    csettings = {**settings, "quality": max(1, min(100, round(float(settings.get("quality", 80)) + offset)))}
    cand = serve(RUN / "candidate", batch, csettings) if cid else [None] * len(batch)
    rng = random.Random(int(now))
    window = load(WINDOW, [])
    before = load(STATE, {}).get("candidate") or {}
    pn = int(before.get("paired", 0)) if cid and before.get("id") == cid else 0   # each compared image numbered, from 0
    for (kind, seed), a, b in zip(batch, prod, cand, strict=True):
        mp = 1.92 if kind == "big-photo" else (0.2304 if kind == "logo" else 0.3072)
        share = float(rollout.get("share") or 0) if int(rollout.get("stage", -1)) >= 0 else 0.0   # served from its first stage
        served = "cand" if b is not None and rng.random() < share else "prod"
        window.append({"t": now, "kind": kind, "mp": mp, "prod": a, "cand": b, "cid": cid, "served": served,
                       **({"pn": pn} if b is not None else {})})
        pn += b is not None
    window = window[-KEEP:]
    save(WINDOW, window)

    recent = window[-RECENT:]
    def got(r):
        return r["cand"] if r["served"] == "cand" else r["prod"]
    ok = [(r, got(r)) for r in recent if "error" not in got(r)]
    state = {"ticks": n, "at": now, "settings": settings, "rollout": rollout, "mix": images.mix(now),
             "flat_share": round(images.flat_share(now), 3),
             "quality": round(sorted(x["ssim"] for _, x in ok)[int(0.1 * (len(ok) - 1))], 4) if ok else 0.0,
             "bytes_per_mp": round(sum(x["bytes"] for _, x in ok) / 1024 / max(1e-9, sum(r["mp"] for r, _ in ok)), 2) if ok else 0.0,
             "failures": round(100 * (len(recent) - len(ok)) / max(1, len(recent)), 1),
             "time": round(p95([x["ms"] for _, x in ok]), 1)}
    served = window[-BATCH:]                                     # what this tick served: the window's newest images
    bok = [(r, got(r)) for r in served if "error" not in got(r)]
    state["batch"] = {"quality": round(sorted(x["ssim"] for _, x in bok)[int(0.1 * (len(bok) - 1))], 4) if bok else 0.0,
                      "bytes": round(sum(x["bytes"] for _, x in bok) / 1024 / max(1e-9, sum(r["mp"] for r, _ in bok)), 2) if bok else 0.0,
                      "failures": round(100 * (len(served) - len(bok)) / max(1, len(served)), 1),
                      "time": round(max([x["ms"] for _, x in bok], default=0.0), 1)}
    pairs = [r for r in window if cid and r["cid"] == cid and r["cand"] is not None]
    since = int(rollout.get("matched_since") or 0)               # the images seen since the matcher last moved
    both = [r for r in pairs if r.get("pn", 0) >= since and "error" not in r["prod"] and "error" not in r["cand"]][-80:]
    # bytes saved as a share of what production served (so a big image weighs what it costs): the
    # mean of these is the saving in total bytes, and its spread gives the confidence interval
    avg = sum(r["prod"]["bytes"] for r in both) / len(both) if both else 1.0
    saved = [100 * (r["prod"]["bytes"] - r["cand"]["bytes"]) / avg for r in both]
    dq = [r["cand"]["ssim"] - r["prod"]["ssim"] for r in both]
    _, sl, sh = bounds(saved)
    _, ql, qh = bounds(dq)
    state["candidate"] = {"id": cid, "paired": pn if cid else 0, "failures": sum(1 for r in pairs if "error" in r["cand"]),
                          "quality_mean": round(sum(dq[-20:]) / len(dq[-20:]), 4) if dq else 0.0,
                          "settings": csettings if cid else None,
                          "time": round(p95([r["cand"]["ms"] for r in both]), 1),
                          "bytes_saved": [round(max(-999, sl), 2), round(min(999, sh), 2)] if cid else [0, 0],
                          "quality_change": [round(max(-1, ql), 4), round(min(1, qh), 4)] if cid else [0, 0],
                          "by_kind": {k: {"n": sum(1 for r in both if r["kind"] == k),
                                          "saved": round(100 * (1 - sum(r["cand"]["bytes"] for r in both if r["kind"] == k)
                                                                / max(1, sum(r["prod"]["bytes"] for r in both if r["kind"] == k))), 1),
                                          "quality_change": round(sum(r["cand"]["ssim"] - r["prod"]["ssim"] for r in both if r["kind"] == k)
                                                                  / max(1, sum(1 for r in both if r["kind"] == k)), 4)}
                                      for k in images.KINDS if any(r["kind"] == k for r in both)}}
    state["by_kind"] = {k: {"quality": round(sum(x["ssim"] for r, x in ok if r["kind"] == k) / max(1, sum(1 for r, _ in ok if r["kind"] == k)), 4),
                            "kb_per_mp": round(sum(x["bytes"] for r, x in ok if r["kind"] == k) / 1024
                                               / max(1e-9, sum(r["mp"] for r, _ in ok if r["kind"] == k)), 1)}
                        for k in images.KINDS if any(r["kind"] == k for r, _ in ok)}
    save(STATE, state)
    return state


if __name__ == "__main__":
    s = tick()
    c = s["candidate"]
    print(f"q{s['settings'].get('quality')}: quality {s['quality']}, {s['bytes_per_mp']} KB/MP, failures {s['failures']}%, "
          f"p95 {s['time']}ms" + (f"; candidate {c['id']} at {s['rollout'].get('share', 0):.0%} (q{c['settings']['quality']}): "
                                  f"saves {c['bytes_saved']}%, quality {c['quality_mean']:+} over {c['paired']}" if c["id"] else ""),
          file=sys.stderr)
    print(json.dumps({"out": "auxiliary.flat-share", "value": s["flat_share"]}))
