"""Leave pages of a running ergostat open in a real browser and record what they cost over time.

    uv run --with playwright==1.63.0 python scripts/page_watch.py http://127.0.0.1:8791 \
        --minutes 12 --every 30 --out /tmp/watch.json '#/diagram' '#/items' ...

Each page is opened in its own browser context (its own renderer), all at once, and sampled every
``--every`` seconds: the JS heap after a forced collection (what is retained, not garbage), DOM
nodes, event listeners, the main thread's busy time (Chromium's TaskDuration), and every long task
(over 50 ms) the page reports. Every response is counted with its size. Read only: GETs, as a reader
would make them, and nothing is clicked. The summary per page: heap and nodes at the start and the
end and their slope per 10 minutes, main-thread busy seconds per minute, long tasks' p50/p95/max,
and requests and kilobytes per minute (by path)."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from urllib.parse import urlsplit

LONGTASKS = """
window.__lt = [];
try {
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); })
    .observe({ type: "longtask", buffered: true });
} catch (e) {}
"""


def slope(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den if den else 0.0


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


async def watch(browser, base: str, route: str, seconds: float, every: float, speed: float) -> dict:
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await page.add_init_script(LONGTASKS)
    if speed != 1:                      # polling sped up: every interval shortened (the regression test's lever)
        await page.add_init_script(f"""(() => {{ window.ERGOSTAT_POLL_SPEED = {speed}; const si = window.setInterval;
          window.setInterval = (f, ms, ...a) => si(f, Math.max(50, (ms || 0) / {speed}), ...a); }})();""")
    cdp = await ctx.new_cdp_session(page)
    await cdp.send("Performance.enable")
    await cdp.send("Network.enable")
    reqs: dict[str, str] = {}
    sent: dict[str, float] = {}
    got: list[tuple[float, str, int, float]] = []          # when, url, bytes, seconds from asking to the last byte
    cdp.on("Network.requestWillBeSent", lambda e: (sent.__setitem__(e["requestId"], e["timestamp"]),
                                                   reqs.__setitem__(e["requestId"], e["request"]["url"])))
    cdp.on("Network.loadingFinished",
           lambda e: got.append((time.time(), reqs.pop(e["requestId"], "?"), int(e.get("encodedDataLength", 0)),
                                 e["timestamp"] - sent.pop(e["requestId"], e["timestamp"]))))
    t0 = time.time()
    await page.goto(base + "/" + route, wait_until="load", timeout=300_000)
    samples = []

    async def sample():
        await cdp.send("HeapProfiler.collectGarbage")
        m = {x["name"]: x["value"] for x in (await cdp.send("Performance.getMetrics"))["metrics"]}
        lt = await page.evaluate("window.__lt.length")
        samples.append({"t": time.time() - t0, "heap": m.get("JSHeapUsedSize", 0), "nodes": m.get("Nodes", 0),
                        "listeners": m.get("JSEventListeners", 0), "busy": m.get("TaskDuration", 0),
                        "script": m.get("ScriptDuration", 0), "layout": m.get("LayoutDuration", 0),
                        "documents": m.get("Documents", 0), "longtasks": lt})

    await asyncio.sleep(min(every, 10))
    await sample()
    while time.time() - t0 < seconds:
        await asyncio.sleep(every)
        await sample()
    lts = [d for _, d in await page.evaluate("window.__lt")]
    await ctx.close()
    warm = samples[1:] or samples                                # past the first load
    span_min = (warm[-1]["t"] - warm[0]["t"]) / 60 or 1
    t_first = t0 + warm[0]["t"]
    late = [g for g in got if g[0] >= t_first]
    by_path: dict[str, list[int]] = {}
    took: dict[str, list[float]] = {}
    for _, url, n, dt in late:
        by_path.setdefault(urlsplit(url).path, []).append(n)
        took.setdefault(urlsplit(url).path, []).append(dt)
    xs = [s["t"] / 60 for s in warm]
    return {
        "route": route,
        "minutes": round(span_min, 1),
        "heap_mb": [round(warm[0]["heap"] / 1e6, 1), round(warm[-1]["heap"] / 1e6, 1)],
        "heap_mb_per_10min": round(slope(xs, [s["heap"] / 1e6 for s in warm]) * 10, 2),
        "nodes": [int(warm[0]["nodes"]), int(warm[-1]["nodes"])],
        "nodes_per_10min": round(slope(xs, [s["nodes"] for s in warm]) * 10),
        "listeners": [int(warm[0]["listeners"]), int(warm[-1]["listeners"])],
        "busy_s_per_min": round((warm[-1]["busy"] - warm[0]["busy"]) / span_min, 2),
        "script_s_per_min": round((warm[-1]["script"] - warm[0]["script"]) / span_min, 2),
        "layout_s_per_min": round((warm[-1]["layout"] - warm[0]["layout"]) / span_min, 2),
        "longtasks": len(lts), "longtask_ms_p50": round(pct(lts, .5)), "longtask_ms_p95": round(pct(lts, .95)),
        "longtask_ms_max": round(max(lts, default=0)),
        "requests_per_min": round(len(late) / span_min, 1),
        "kb_per_min": round(sum(g[2] for g in late) / 1024 / span_min, 1),
        "by_path": {p: {"n_per_min": round(len(v) / span_min, 1), "kb_each": round(statistics.fmean(v) / 1024, 1),
                        "ms_p50": round(pct(took[p], .5) * 1000), "ms_p95": round(pct(took[p], .95) * 1000)}
                    for p, v in sorted(by_path.items(), key=lambda kv: -sum(kv[1]))},
        "samples": samples,
    }


async def main_async(a) -> list[dict]:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--enable-precise-memory-info", "--js-flags=--expose-gc"])
        out = await asyncio.gather(*(watch(browser, a.base, r, a.minutes * 60, a.every, a.speed) for r in a.routes))
        await browser.close()
    return list(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base")
    ap.add_argument("routes", nargs="+")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--every", type=float, default=30)
    ap.add_argument("--speed", type=float, default=1, help="shorten every setInterval by this factor")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = asyncio.run(main_async(a))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
    for r in res:
        print(f"{r['route']:<40} heap {r['heap_mb'][0]}→{r['heap_mb'][1]} MB ({r['heap_mb_per_10min']:+}/10m)  "
              f"nodes {r['nodes'][0]}→{r['nodes'][1]} ({r['nodes_per_10min']:+}/10m)  listeners {r['listeners'][0]}→{r['listeners'][1]}  "
              f"busy {r['busy_s_per_min']} s/min  long {r['longtasks']} p50 {r['longtask_ms_p50']} p95 {r['longtask_ms_p95']} "
              f"max {r['longtask_ms_max']} ms  {r['requests_per_min']} req/min {r['kb_per_min']} KB/min")


if __name__ == "__main__":
    main()
