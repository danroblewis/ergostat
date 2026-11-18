"""What the control diagram draws badly, measured in a browser: lines through a part that is not one of
their ends, lines running on top of another (lines merging into, or splitting from, one end are a net
and allowed), and lines far longer than the distance they cover.

    uv run --with playwright python scripts/diagram_audit.py URL [VIEW ...]

URL is a running ergostat page (http://127.0.0.1:8781); each VIEW is the diagram's query, like
open=factory or system=product (default: the whole thing, each system opened, each drawn alone).
It drives the Chrome installed on this machine. Exits 1 when a line crosses a part or detours."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AUDIT = (Path(__file__).parent / "diagram_audit.js").read_text()
url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8781"
views = sys.argv[2:]
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    if not views:
        pg.goto(f"{url}/diagram")
        pg.wait_for_timeout(3000)
        tree = pg.evaluate("() => S.graph?.tree || {}")
        views = ["", "open=*", *(f"open={s}" for s in tree), *(f"system={s}" for s in tree)]
    for v in views:
        pg.goto(f"{url}/diagram?{v}")
        pg.wait_for_timeout(4500)
        r = pg.evaluate(AUDIT)
        print(f"[{v or 'default'}] through {len(r['through'])}, overlap {len(r['overlap'])}, detour {len(r['detour'])}")
        for k in ("through", "overlap", "detour"):
            for x in r[k][:6]:
                print("   ", k, x)
        bad += len(r["through"]) + len(r["detour"])
    b.close()
sys.exit(1 if bad else 0)
