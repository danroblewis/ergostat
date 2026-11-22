"""PROTOTYPE evidence (docs/proposals/dynamics-bundled-connectors.md; removed with the prototype): the three views the
proposal names drawn as main draws them and with ?bundle=1, light and dark, their screenshots kept for the proposal,
and the layout rules' counts (tests/layout_rules.py) on both: connector crossings down, no more sign collisions and no
more lines through parts. Counts go to /tmp/bundle-evidence.json."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from tests import layout_rules as rules
from tests.test_diagram_rendering import GEOMETRY, READY, ROOT, browser, free_port  # noqa: F401  (browser: the fixture)

CASES = [("ticket-factory", "view=dynamics&open=factory,modelling", "tf-factory"),
         ("software-factory", "view=dynamics", "sf-top"),
         ("software-factory", "view=dynamics&system=product", "sf-product")]
SHOTS = ROOT / "docs" / "proposals" / "img"
BRANCHES = "() => S.sdBranches || []"


def serve(tmp, name):
    d = tmp / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            return proc, url
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"{name}: the page never answered")


def counts(geo: dict, branches: list) -> dict:
    trunks = {b["trunk"]: b["pts"] for b in branches if b.get("trunk")}     # a bundle's line: its trunk as drawn
    geo = {**geo, "edges": [{**e, "pts": trunks.get(e["id"], e["pts"])} for e in geo["edges"]]
           + [b for b in branches if not b.get("trunk")]}
    es = geo["edges"]
    group = {e["id"]: e.get("bundle") or e["id"] for e in es}
    cross, pairs = 0, {}
    for i, a in enumerate(es):                          # a connector crossing any other line (each point once); the
        for b in es[i + 1:]:                            # branches of one bundle and its trunk are one line
            if (a["kind"] == "pipe" and b["kind"] == "pipe") or group[a["id"]] == group[b["id"]]:
                continue
            x = sum(rules.crosses(p, q, r, t) for p, q in rules.segs(a["pts"]) for r, t in rules.segs(b["pts"]))
            cross += x
            if x:
                kinds = sorted("branch" if e.get("bundle") else "trunk" if e["id"].startswith("bundle:") else e["kind"]
                               for e in (a, b))
                pairs["-".join(kinds)] = pairs.get("-".join(kinds), 0) + x
    found = rules.check(geo, ["label-collision", "line-through-part"])
    signs = sum(1 for x in found if x["rule"] == "label-collision" and x["severity"] == "minor")
    words = sum(1 for x in found if x["rule"] == "label-collision" and x["severity"] != "minor")
    through = sum(1 for x in found if x["rule"] == "line-through-part")
    module_lines = sum(1 for e in geo["edges"] if e["kind"] == "connector" and e.get("sourcePort") and e.get("targetPort"))
    return {"connector_crossings": cross, "sign_collisions": signs, "word_collisions": words, "line_through_part": through,
            "lines_between_closed_modules": module_lines, "bundles": len(trunks), "by_kind": pairs}


def test_bundled_connectors_prototype_cuts_crossings_without_more_collisions(browser, tmp_path):  # noqa: F811
    out, n = {}, 0
    SHOTS.mkdir(parents=True, exist_ok=True)
    served = {}
    try:
        for name, q, tag in CASES:
            if name not in served:
                served[name] = serve(tmp_path, name)
            url = served[name][1]
            for scheme in ("light", "dark"):
                pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme=scheme)
                for when, extra in (("before", ""), ("after", "&bundle=1&rows=last")):
                    n += 1
                    pg.goto(f"{url}/diagram?v={n}&{q}{extra}", timeout=240000)
                    pg.wait_for_function(READY, timeout=240000)
                    pg.wait_for_timeout(400)
                    pg.locator("svg.canvas").screenshot(path=str(SHOTS / f"bundled-{tag}-{when}-{scheme}.png"))
                    if scheme == "light":
                        out[f"{tag} {when}"] = counts(pg.evaluate(GEOMETRY), pg.evaluate(BRANCHES))
                    if tag == "sf-product" and scheme == "light" and when == "before":
                        out["into churn"] = pg.evaluate("() => S.graph.edges.filter((e) => /churn/.test(e.target))"
                                                        ".map((e) => `${e.kind} ${e.source} > ${e.target} ${e.polarity || ''}`)")
                pg.close()
    finally:
        for proc, _ in served.values():
            proc.terminate()
            proc.wait(10)
    with open(ROOT / ".scratch-shots.json", "w") as f:
        json.dump(out, f, indent=1)
    out.pop("into churn", None)
    total = {w: {k: sum(v[k] for t, v in out.items() if t.endswith(w)) for k in out[f"sf-top {w}"] if k != "by_kind"}
             for w in ("before", "after")}
    print("\n".join(f"{k}: {json.dumps(v)}" for k, v in {**out, **total}.items()))
    assert total["after"]["connector_crossings"] < total["before"]["connector_crossings"], (out, total)
    assert total["after"]["sign_collisions"] <= total["before"]["sign_collisions"], (out, total)
    assert total["after"]["line_through_part"] <= total["before"]["line_through_part"], (out, total)


def test_corpus_counts_main_against_the_prototype(browser, tmp_path):  # noqa: F811
    """Every example's Dynamics views as tests/layout_corpus.py draws them (whole, everything open, each system open, each
    alone), on main's drawing and on the prototype's: the counts summed, to /tmp/bundle-corpus.json."""
    from tests import diagram_corpus as corpus
    from tests.test_diagram_rendering import EXAMPLES
    variants = (("before", ""), ("after", "&bundle=1&rows=last"), ("after-plain", "&bundle=1"))
    sums: dict = {w: {} for w, _ in variants}
    views, changed, n, rows = 0, 0, 0, []
    for name in EXAMPLES:
        proc, url = serve(tmp_path, name)
        try:
            pg = browser.new_page(viewport={"width": 1440, "height": 900})
            n += 1
            pg.goto(f"{url}/diagram?v={n}&view=dynamics", timeout=240000)
            try:
                pg.wait_for_function(READY, timeout=60000)
            except Exception:                         # (nothing to draw)
                pg.close()
                continue
            tree = pg.evaluate("() => S.graph.tree || {}")
            for q in corpus.views_of("dynamics", tree):
                got = {}
                for when, extra in variants:
                    n += 1
                    pg.goto(f"{url}/diagram?v={n}&{q}{extra}", timeout=240000)
                    pg.wait_for_function(READY, timeout=240000)
                    pg.wait_for_timeout(150)
                    got[when] = counts(pg.evaluate(GEOMETRY), pg.evaluate(BRANCHES))
                views += 1
                changed += bool(got["after"]["bundles"])
                if got["after"]["bundles"]:
                    rows.append({"model": name, "view": q, **{w: {k: v for k, v in c.items() if k != "by_kind"}
                                                              for w, c in got.items()}})
                for when, c in got.items():
                    for k, v in c.items():
                        if k != "by_kind":
                            sums[when][k] = sums[when].get(k, 0) + v
            pg.close()
        finally:
            proc.terminate()
            proc.wait(10)
    res = {"views": views, "views_with_a_bundle": changed, **sums, "rows": rows}
    with open(ROOT / ".scratch-corpus.json", "w") as f:
        json.dump(res, f, indent=1)
    print("CORPUS", json.dumps(res))
    assert sums["after"]["connector_crossings"] < sums["before"]["connector_crossings"], res
