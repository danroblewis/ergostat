"""The behaviour reproduction charts: the harness as it was (black) against the designed Coordinator (grey,
dashed), from world/experiment.py's runs, in plain black and white, as 02's reference modes are drawn.

    uv run --with matplotlib python world/charts.py [--runs run/experiment] [--seed 1] [--out DIR]

writes model-*.png into DIR (docs/proposals/coordinator/img by default) and prints the table of every seed found.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # the example's own world/

import matplotlib

from world.experiment import lead  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent.parent / "docs" / "proposals" / "coordinator" / "img"
H = dict(color="black", lw=1.2, label="harness as it was")
D = dict(color="0.45", lw=1.4, ls="--", label="designed Coordinator")
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "font.family": "sans-serif"})


def load(runs: Path, pol: str, seed: int) -> dict:
    return json.loads((runs / f"{pol}-{seed}.json").read_text())


def per(r: dict, name: str, width: int, days: float) -> tuple[list[float], list[float]]:
    xs, ys = [], []
    for b in range(0, int(days * 24) + 8, width):
        xs.append((b + width / 2) / 24)
        ys.append(sum(r["counts"].get(str(h), {}).get(name, 0) for h in range(b, b + width)))
    return xs, ys


def marks(ax, r: dict, away: bool = True) -> None:
    """The owner's directions (dotted lines) and, lightly shaded, the hours the owner was away."""
    for d in r["dirs"]:
        ax.axvline(d / 24, color="black", lw=0.6, ls=":")
    if away:
        hs = r["hours"]
        start = None
        for h in hs:
            if not h["present"] and start is None:
                start = h["t"]
            if h["present"] and start is not None:
                ax.axvspan(start / 24, h["t"] / 24, color="0.93", lw=0)
                start = None


def rework(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True)
    for a, r, title in ((ax[0], h, "(a) harness as it was"), (ax[1], d, "(b) designed Coordinator")):
        x, add = per(r, "lines-added", 12, r["days"])
        _, rw = per(r, "lines-reworked", 12, r["days"])
        ys = [w / a_ if a_ >= 3000 else float("nan") for w, a_ in zip(rw, add, strict=True)]
        a.bar(x, ys, width=0.42, color="black" if r is h else "0.55", lw=0)
        marks(a, r, away=False)
        a.set_ylabel("reworked per\nline added")
        a.set_title(title, loc="left", fontsize=9)
        a.set_ylim(0, 0.6)
    ax[1].set_xlabel("days (dotted: a new direction from the owner; 12-hour buckets with 3,000 lines added or more)")
    fig.suptitle("Rework of landed work spikes at each direction and decays (RM1 → hoped-for (a))", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-rework.png", dpi=150)
    plt.close(fig)


BINS = [("at acceptance", -1, 0), ("< 1 h", 0, 1), ("1–6 h", 1, 6), ("6–24 h", 6, 24), ("1–3 d", 24, 72),
        ("> 3 d", 72, 1e9)]


def found_bins(r: dict) -> list[float]:
    f = r["log"].get("found", [])
    n = len(f) or 1
    out = []
    for _, lo, hi in BINS:
        if lo < 0:
            out.append(sum(1 for x in f if x[2] == "check") / n)
        else:
            out.append(sum(1 for x in f if x[2] != "check" and lo <= x[1] - x[0] < hi) / n)
    return out


def discovery(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.4))
    xs = range(len(BINS))
    ax.bar([x - 0.2 for x in xs], found_bins(h), width=0.38, color="black", label="harness as it was")
    ax.bar([x + 0.2 for x in xs], found_bins(d), width=0.38, color="white", edgecolor="black", hatch="///",
           label="designed Coordinator")
    ax.set_xticks(list(xs), [b[0] for b in BINS])
    ax.set_ylabel("share of the rework found")
    ax.set_xlabel("when it was found: before landing, or this long after")
    ax.legend(frameon=False)
    ax.set_title("Rework is found hours after landing; the design moves it before (RM2 → hoped-for (b))",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(out / "model-discovery.png", dpi=150)
    plt.close(fig)


def corrections(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True)
    for r, st in ((h, H), (d, D)):
        x, c = per(r, "corrections", 12, r["days"])
        _, m = per(r, "owner-messages", 12, r["days"])
        ax[0].step(x, [a / b if b >= 5 else float("nan") for a, b in zip(c, m, strict=True)], where="mid", **st)
        ax[1].plot([q["t"] / 24 for q in r["hours"]], [q["rules"] for q in r["hours"]], **st)
    _, lost = per(h, "lost-at-cut", 1, h["days"])
    cum, s = [], 0
    for v in lost:
        s += v
        cum.append(s)
    ax[1].plot([(i + 0.5) / 24 for i in range(len(cum))], cum, color="black", lw=0.8, ls=":",
               label="harness: corrections lost at a cut, never written")
    marks(ax[0], h, away=False)
    marks(ax[1], h, away=False)
    ax[0].set_ylabel("new corrections\nper owner message")
    ax[1].set_ylabel("standing rules\n(written, not retired)")
    ax[0].set_title("(a) corrections per owner message, 12-hour buckets", loc="left", fontsize=9)
    ax[1].set_title("(b) the stock of standing corrections", loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8)
    ax[1].legend(frameon=False, fontsize=8)
    ax[1].set_xlabel("days")
    fig.suptitle("Corrections reset at each direction; standing rules only grow (RM4 → hoped-for (c))", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-corrections.png", dpi=150)
    plt.close(fig)


def checking(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.2))
    for r, st in ((h, H), (d, D)):
        x, hid = per(r, "hidden-runs", 6, r["days"])
        _, tr = per(r, "test-runs", 6, r["days"])
        ax.step(x, [a / b if b >= 3 else float("nan") for a, b in zip(hid, tr, strict=True)], where="mid", **st)
    _, inc = per(h, "incidents", 1, h["days"])
    for i, v in enumerate(inc):
        if v:
            ax.plot([(i + 0.5) / 24], [1.04], marker="v", color="black", ms=4)
    marks(ax, h, away=False)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("test runs with the\nexit status not read")
    ax.set_xlabel("days (▼ a slip reported: the habit restored)")
    ax.legend(frameon=False, loc="center right")
    ax.set_title("Checking goes blind, is restored after an incident, drifts back (RM5 → hoped-for (d))",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(out / "model-checking.png", dpi=150)
    plt.close(fig)


def stalls(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for a, r, title in ((ax[0], h, "(a) harness as it was"), (ax[1], d, "(b) designed: a 40-minute lease")):
        st = r["log"].get("stalls", [])
        for present, mk in ((True, dict(marker="o", mfc="white", mec="black")), (False, dict(marker="o", mfc="black", mec="black"))):
            pts = [60 * (s[1] - s[0]) for s in st if s[2] == present]
            xs = [1 + (0.3 if present else -0.3) + 0.25 * ((i * 0.618) % 1 - 0.5) for i in range(len(pts))]
            a.plot(xs, pts, ls="none", ms=3.5, **mk, label="owner present" if present else "owner away")
        a.set_xticks([0.7, 1.3], ["away", "present"])
        a.set_xlim(0.2, 1.8)
        a.set_title(title, loc="left", fontsize=9)
        meds = {p: statistics.median([60 * (s[1] - s[0]) for s in st if s[2] == p] or [0]) for p in (True, False)}
        a.text(0.7, -18, f"median {meds[False]:.0f} min", ha="center", fontsize=8)
        a.text(1.3, -18, f"median {meds[True]:.0f} min", ha="center", fontsize=8)
    ax[0].set_ylabel("minutes silent before the stall\nwas noticed and its item requeued")
    ax[0].set_ylim(-28, None)
    ax[0].axhline(30, color="0.6", lw=0.6, ls=":")
    ax[1].axhline(40, color="0.6", lw=0.6, ls=":")
    fig.suptitle("Stalls go unnoticed while the owner is away (RM6 → hoped-for (e))", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-stalls.png", dpi=150)
    plt.close(fig)


def owner(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    for r, st in ((h, H), (d, D)):
        t = [q["t"] / 24 for q in r["hours"]]
        ax[0].step(t, [q["queue"] for q in r["hours"]], where="post", **st)
        ax[1].plot(t, [q["decisions"] for q in r["hours"]], **st)
    marks(ax[0], h)
    marks(ax[1], h)
    ax[0].axhline(3, color="0.6", lw=0.6, ls=":")
    ax[0].set_ylabel("blockers waiting\nfor the owner")
    ax[1].set_ylabel("proposed decisions\nawaiting confirmation")
    ax[0].set_title("(a) holds and questions open (dotted: S5, at most 3; shaded: the owner away)", loc="left",
                    fontsize=9)
    ax[1].set_title("(b) the batch queue", loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8)
    ax[1].set_xlabel("days")
    fig.suptitle("What waits for the owner has no outflow (RM8 → hoped-for (f))", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-owner.png", dpi=150)
    plt.close(fig)


def context(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    t = [q["t"] / 24 for q in h["hours"]]
    ax[0].plot(t, [q["window"] / 1000 for q in h["hours"]], **H)
    wins = d["log"].get("windows", [])
    if wins:
        ws = sorted(wins)
        p90 = ws[int(0.9 * len(ws))] / 1000
        ax[0].axhline(p90, **{**D, "label": f"designed: each worker's own window at its run's end, 9 in 10 under "
                                            f"{p90:.0f}k (largest {ws[-1] / 1000:.0f}k)"})
    ax[0].axhline(965, color="0.6", lw=0.6, ls=":")
    ax[0].set_ylabel("working context\n(k tokens)")
    ax[0].set_title("(a) the Coordinator's window (dotted: where the harness cuts)", loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8, loc="upper left", ncol=1)
    x, rr = per(h, "rereads", 1, h["days"])
    _, burst = per(h, "rereads-after-cut", 1, h["days"])
    ax[1].bar(x, rr, width=1 / 24, color="0.6", lw=0, label="harness: re-reads within the window")
    ax[1].bar(x, burst, width=1 / 24, color="black", lw=0, label="harness: re-reads after a cut")
    ax[1].set_ylabel("re-reads an hour")
    ax[1].set_title("(b) re-reading (the designed Coordinator re-reads the record before each act: no cut, no burst)",
                    loc="left", fontsize=9)
    ax[1].legend(frameon=False, fontsize=8, loc="upper right")
    ax[1].set_xlabel("days (the first ten)")
    ax[1].set_xlim(0, 10)
    ax[0].set_ylim(0, 1250)
    fig.suptitle("The window's sawtooth, and the burst of re-reading after each cut (RM9, RM11 → hoped-for (g))",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-context.png", dpi=150)
    plt.close(fig)


def code(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    for r, st in ((h, H), (d, D)):
        t = [q["t"] / 24 for q in r["hours"]]
        ax[0].plot(t, [q["lines"] / 1000 for q in r["hours"]], **st)
        ax[1].plot(t, [q["cv8"] for q in r["hours"]], **st)
    for p in h["log"].get("pruned", []):
        ax[0].annotate("the owner prunes", (p[0] / 24, 0), xytext=(p[0] / 24, 15), fontsize=7, ha="center",
                       arrowprops=dict(arrowstyle="->", lw=0.6))
    hs = d["hours"]
    start = None
    for q in hs + [{"t": hs[-1]["t"], "mode": "normal"}]:
        if q["mode"] == "consolidation" and start is None:
            start = q["t"]
        if q["mode"] != "consolidation" and start is not None:
            for a in ax:
                a.axvspan(start / 24, q["t"] / 24, color="0.9", lw=0)
            start = None
    ax[1].axhline(1.3, color="0.6", lw=0.6, ls=":")
    ax[1].axhline(1.1, color="0.6", lw=0.6, ls=":")
    marks(ax[0], h, away=False)
    ax[0].set_ylabel("code stock\n(k lines)")
    ax[1].set_ylabel("code per feature\nagainst expected (CV8)")
    ax[0].set_title("(a) the stock of code", loc="left", fontsize=9)
    ax[1].set_title("(b) CV8 (dotted: LP10 enters consolidation at 1.3, leaves at 1.1; shaded: consolidation)",
                    loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8)
    ax[1].set_xlabel("days")
    fig.suptitle("Code grows in steps and is pruned once, late, from outside (RM3 → balanced inside, LP10)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-code.png", dpi=150)
    plt.close(fig)


def throughput(h: dict, d: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    for r, st in ((h, H), (d, D)):
        x, acc = per(r, "accepted-direction", 1, r["days"])
        cum, s = [], 0
        for v in acc:
            s += v
            cum.append(s)
        ax[0].plot([(i + 1) / 24 for i in range(len(cum))], cum, **st)
        ax[1].step([q["t"] / 24 for q in r["hours"]], [q["leased"] for q in r["hours"]], where="post",
                   **{**st, "lw": 0.8})
    marks(ax[0], h, away=False)
    marks(ax[1], h)
    ax[0].set_ylabel("the owner's direction\nitems accepted")
    ax[1].set_ylabel("runs in flight")
    ax[0].set_title("(a) throughput of what the owner asked for (cumulative)", loc="left", fontsize=9)
    ax[1].set_title("(b) work in progress (shaded: the owner away; the design halves the AI pool then)",
                    loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8)
    ax[1].set_xlabel("days")
    fig.suptitle("What the controllers cost: the owner's work is delivered no later", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-throughput.png", dpi=150)
    plt.close(fig)


def cascade(d: dict, fixed: dict, h: dict, out: Path) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    for r, st in ((d, D), (fixed, dict(color="black", lw=0.8, ls=":", label="designed, LP2 off (h* held at 0.1)"))):
        hs = r["log"].get("h_star", [])
        ax[0].step([x[0] / 24 for x in hs], [x[1] for x in hs], where="post", **st)
    for r, st in ((h, H), (d, D), (fixed, dict(color="black", lw=0.8, ls=":", label="designed, LP2 off"))):
        ax[1].plot([q["t"] / 24 for q in r["hours"]], [q["cv1"] for q in r["hours"]], **st)
    ax[0].axhline(0.3, color="0.6", lw=0.6, ls=":")
    ax[1].axhline(0.1, color="0.6", lw=0.6, ls=":")
    marks(ax[0], d, away=False)
    marks(ax[1], d, away=False)
    ax[0].set_ylabel("h*: hidden rework\nallowed per item")
    ax[1].set_ylabel("CV1: escaped rework\n(a week's acceptances)")
    ax[0].set_title("(a) LP2's output, LP1's setpoint (dotted: the top of its band)", loc="left", fontsize=9)
    ax[1].set_title("(b) what LP2 holds (dotted: its limit, 0.1)", loc="left", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8)
    ax[1].legend(frameon=False, fontsize=8)
    ax[1].set_xlabel("days")
    fig.suptitle("The quality cascade: with CV1 under its limit, LP2 loosens review to the top of its band", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-cascade.png", dpi=150)
    plt.close(fig)


def table(runs: Path) -> None:
    """Each measure, over every seed found: the median and range."""
    rows: dict[str, dict[str, list[float]]] = {}
    for pol in ("harness", "designed", "designed-no-quality"):
        for f in sorted(runs.glob(f"{pol}-[0-9]*.json")):
            r = json.loads(f.read_text())
            c: dict = {}
            for v in r["counts"].values():
                for k, x in v.items():
                    c[k] = c.get(k, 0) + x
            f_ = r["log"].get("found", [])
            after = sorted(x[1] - x[0] for x in f_ if x[2] != "check")
            st = r["log"].get("stalls", [])
            away = [60 * (s[1] - s[0]) for s in st if not s[2]]
            m = {
                "escaped / accepted": c.get("escaped", 0) / max(c.get("accepted", 1), 1),
                "reworked per line added": c.get("lines-reworked", 0) / max(c.get("lines-added", 1), 1),
                "rework caught before landing": c.get("caught", 0) / max(len(f_), 1),
                "found by the owner (share of found after landing)": c.get("found-by-owner", 0) / max(len(after), 1),
                "median hours to find landed rework": statistics.median(after) if after else 0,
                "stalls noticed, owner away: median min": statistics.median(away) if away else 0,
                "stalls noticed, owner away: longest min": max(away) if away else 0,
                "test runs, exit status not read": c.get("hidden-runs", 0) / max(c.get("test-runs", 1), 1),
                "corrections": c.get("corrections", 0), "repeated corrections": c.get("repeats", 0),
                "standing rules at day 30": r["hours"][-1]["rules"],
                "decisions waiting at day 30": r["hours"][-1]["decisions"],
                "most blockers open at once": max(q["queue"] for q in r["hours"]),
                "interruptions a day": c.get("interruptions", 0) / r["days"],
                "harness cuts": c.get("cuts", 0), "CV8 at day 30": r["hours"][-1]["cv8"],
                "pruned by the owner": len(r["log"].get("pruned", [])),
                "direction items accepted": c.get("accepted-direction", 0),
                "all items accepted": c.get("accepted", 0),
                "leases expired on sound runs": c.get("false-expiries", 0),
                "hours to deliver 90% of a direction (median)": lead(r),
                "acceptance checks deeper than the tests": sum(c.get(f"depth-{x}", 0) for x in
                                                               ("inspection", "deep-review", "hold-point")),
            }
            for k, v in m.items():
                rows.setdefault(k, {}).setdefault(pol, []).append(v)
    n = len(next(iter(rows.values()))["harness"]) if rows else 0
    print(f"| measure ({n} seeds: median, range) | harness as it was | designed | designed, LP2 off |")
    print("|---|---|---|---|")
    for k, v in rows.items():
        def f(xs):
            xs = sorted(xs)
            md = statistics.median(xs)
            fmt = (lambda y: f"{y:.2f}") if max(abs(y) for y in xs) < 10 else (lambda y: f"{y:.0f}")
            return f"{fmt(md)} ({fmt(xs[0])}–{fmt(xs[-1])})"
        print(f"| {k} | {f(v['harness'])} | {f(v['designed'])} | {f(v['designed-no-quality'])} |")


LIVE = [("auxiliary.oldest-silence", "oldest silence\n(factory hours)"),
        ("auxiliary.unread-test-runs", "test runs with the\nexit status unread"),
        ("stock.owner-queue", "blockers waiting\nfor the owner"), ("stock.decisions-waiting", "decisions\nawaiting confirmation")]


def live(urls: dict[str, str], hours: float, hour_s: float, out: Path) -> None:
    """The two live runs as ergostat recorded them (its /api/series), on the factory's clock."""
    import urllib.request
    got = {}
    for pol, url in urls.items():
        refs = ",".join([*(r for r, _ in LIVE), "auxiliary.owner-present"])
        span = int(hours * hour_s)
        q = f"{url}/api/series?refs={refs}&since={span}s&points={max(20, span // 20)}"
        got[pol] = json.loads(urllib.request.urlopen(q, timeout=60).read())
    fig, ax = plt.subplots(len(LIVE), 1, figsize=(8, 7), sharex=True)
    for pol, st in (("harness", H), ("designed", D)):
        d = got[pol]
        t0 = d["times"][0]
        xs = [(t - t0) / hour_s / 24 for t in d["times"]]
        by = {s["ref"]: s["values"] for s in d["series"]}
        for a, (ref, label) in zip(ax, LIVE, strict=True):
            pts = [(x, v) for x, v in zip(xs, by[ref], strict=True) if v is not None]     # buckets with a reading
            a.plot([x for x, _ in pts], [v for _, v in pts], **st)
            a.set_ylabel(label)
        if pol == "harness":
            pres = by["auxiliary.owner-present"]
            start = None
            for x, v in zip(xs + [xs[-1]], pres + [1], strict=True):
                if v is not None and v < 0.5 and start is None:
                    start = x
                if (v is None or v >= 0.5) and start is not None:
                    for a in ax:
                        a.axvspan(start, x, color="0.93", lw=0)
                    start = None
    ax[0].axhline(0.7, color="0.6", lw=0.6, ls=":")
    ax[2].axhline(3, color="0.6", lw=0.6, ls=":")
    ax[0].legend(frameon=False, fontsize=8, loc="upper right")
    ax[-1].set_xlabel("factory days of each live run (shaded: the owner away, in the harness's run)")
    fig.suptitle("The same model run by ergostat: its own record of the two live runs", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "model-live.png", dpi=150)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=ROOT / "run" / "experiment")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--live", nargs=2, metavar=("HARNESS_URL", "DESIGNED_URL"), help="chart two live runs instead")
    ap.add_argument("--hours", type=float, default=96, help="--live: factory hours of record")
    ap.add_argument("--hour-seconds", type=float, default=30, help="--live: seconds per factory hour")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.live:
        live({"harness": a.live[0], "designed": a.live[1]}, a.hours, a.hour_seconds, a.out)
        return 0
    h, d = load(a.runs, "harness", a.seed), load(a.runs, "designed", a.seed)
    for f in (rework, discovery, corrections, checking, stalls, owner, context, code, throughput):
        f(h, d, a.out)
    cascade(d, load(a.runs, "designed-no-quality", a.seed), h, a.out)
    table(a.runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
