"""The dashboard's chart families (static/plots-*.js and the registry in panels.js) in a real browser, against known data:
a first-order system's exact frequency response, quartiles worked by hand, every option of every family, the four panel
states, and the batched query's renaming of what one query reads from another.

    uv run --with playwright==1.63.0 python -m pytest tests/test_plot_forms.py -n 4

PLOT_SHOTS=<directory> also saves a gallery of every family, in each theme and width.
"""

from __future__ import annotations

import base64
import cmath
import json
import math
import os
import random
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

try:
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
ORIGIN = "http://plots.test"
NOW = 1795400000.0
STEP = 720
PLOTS = ["math", "frame", "xy", "bar", "dist", "heat", "candle", "freq"]
SCRIPTS = ["elk.bundled.js", "uplot/uPlot.iife.min.js", "util.js", "charts.js", "frames.js", "panels.js", *[f"plots-{n}.js" for n in PLOTS]]
PAGE = (
    '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '<link rel="stylesheet" href="/static/style.css"><link rel="stylesheet" href="/static/panels.css">'
    '<link rel="stylesheet" href="/static/plots.css">'
    "<style>body{display:block;height:auto;padding:16px;background:var(--chrome)}</style></head>"
    '<body><div id="page" class="panel-grid"></div>' + "".join(f'<script src="/static/{n}"></script>' for n in SCRIPTS) + "</body></html>"
)
TYPES = {".js": "text/javascript", ".css": "text/css"}
META = {"now": NOW, "since": NOW - STEP * 119, "until": NOW, "step": STEP}
TIMES = [NOW - STEP * (119 - i) for i in range(120)]


def first_order(gain=2.0, corner=0.01, n=61, coherence=None):
    """G(s) = K / (1 + s/wc), exactly, from three decades below the corner to two above."""
    hz = [corner * 10 ** (-3 + 5 * i / (n - 1)) for i in range(n)]
    g = [gain / complex(1, f / corner) for f in hz]
    return {
        "hz": hz,
        "magnitude_db": [20 * math.log10(abs(z)) for z in g],
        "phase_deg": [math.degrees(cmath.phase(z)) for z in g],
        "re": [z.real for z in g],
        "im": [z.imag for z in g],
        "coherence": coherence or [0.97] * n,
    }


def third_order(n=121):
    """Three lags: the phase passes -180, so a wrapped phase would jump."""
    hz = [10 ** (-3 + 4 * i / (n - 1)) for i in range(n)]
    g = [4 / complex(1, f / 0.02) ** 3 for f in hz]
    wrapped = [math.degrees(cmath.phase(z)) for z in g]
    return {
        "hz": hz,
        "magnitude_db": [20 * math.log10(abs(z)) for z in g],
        "phase_deg": wrapped,
        "re": [z.real for z in g],
        "im": [z.imag for z in g],
        "coherence": [0.95 if not 50 <= i < 62 else 0.3 for i in range(n)],
    }


def wave(i, a=30.0, b=12.0, k=9.0):
    return a + b * math.sin(i / k) + 0.3 * b * math.sin(i / 2.3)


def time_result(rid="a", names=("ready", "review", "merged"), unit="items"):
    return {
        "id": rid,
        "times": TIMES,
        "unit": unit,
        "capped": 0,
        "read_log": False,
        "series": [
            {"name": n, "values": [None if 50 <= i < 54 else round(wave(i, 30 + 14 * k, 8 + 3 * k), 3) for i in range(120)]}
            for k, n in enumerate(names)
        ],
    }


def spiral():
    """A damped oscillator's trajectory: position against velocity, spiralling in to rest."""
    xs, ys = [], []
    for i in range(120):
        t = i / 6
        xs.append(round(40 * math.exp(-t / 9) * math.cos(t) + 50, 4))
        ys.append(round(-40 * math.exp(-t / 9) * math.sin(t) + 12, 4))
    return {
        "id": "a",
        "x": {"type": "query", "label": "gaps ready", "unit": "gaps", "scale": "number"},
        "unit": "gaps/h",
        "capped": 0,
        "read_log": False,
        "series": [{"name": "y", "xs": xs, "values": ys, "times": TIMES, "ids": None}],
    }


def scattered():
    r = random.Random(7)
    xs = [round(r.uniform(5, 400), 2) for _ in range(160)]
    return {
        "id": "a",
        "x": {"type": "field", "label": "net_lines", "unit": "lines", "scale": "number"},
        "unit": "usd",
        "capped": 0,
        "read_log": False,
        "series": [
            {
                "name": "ai_cost_usd",
                "xs": xs,
                "values": [round(0.02 * x + 0.6 + r.gauss(0, 1.1), 3) for x in xs],
                "times": TIMES[:40] * 4,
                "ids": [f"item-{i}" for i in range(160)],
                "sizes": [round(r.uniform(1, 40), 1) for _ in xs],
                "colors": [("small" if x < 150 else "large") for x in xs],
            }
        ],
    }


def binned():
    r = random.Random(3)
    edges = [i * 10.0 for i in range(21)]
    values = [r.gauss(95, 32) for _ in range(800)]
    counts = [sum(1 for v in values if edges[i] <= v < edges[i + 1]) for i in range(20)]
    return {
        "id": "a",
        "x": {"type": "bins", "label": "cycle time", "unit": "min", "scale": "number", "edges": edges},
        "unit": "",
        "capped": 0,
        "read_log": False,
        "series": [{"name": "count", "xs": [(edges[i] + edges[i + 1]) / 2 for i in range(20)], "values": counts, "ids": None}],
    }


def categories():
    return {
        "id": "a",
        "x": {"type": "category", "label": "state", "unit": "", "scale": "category"},
        "unit": "usd",
        "capped": 0,
        "read_log": False,
        "series": [
            {
                "name": "cost",
                "xs": ["ready", "building", "review", "merging", "merged", "failed"],
                "values": [12.5, 48.0, 31.25, 7.5, 96.0, 4.0],
                "ids": None,
            }
        ],
    }


def spread():
    r = random.Random(11)

    def pick(mu, sd, extra):
        return [round(r.gauss(mu, sd), 3) for _ in range(120)] + extra

    return {
        "id": "a",
        "times": TIMES + [NOW + i for i in range(1, 4)],
        "unit": "min",
        "capped": 0,
        "read_log": False,
        "series": [
            {"name": "ready", "values": pick(30, 6, [62, 66, 3])},
            {"name": "review", "values": pick(48, 12, [110, 2, 90])},
            {"name": "merging", "values": pick(18, 3, [40, 41, 1])},
        ],
    }


def candles(n=48):
    r = random.Random(5)
    t = [NOW - 3600 * (n - 1 - i) for i in range(n)]
    o, hi, lo, c, count, level = [], [], [], [], [], 100.0
    for i in range(n):
        if i == 20:
            for col in (o, hi, lo, c, count):
                col.append(None)
            continue
        op = level
        cl = op + r.gauss(0.25, 2.6)
        o.append(round(op, 2))
        c.append(round(cl, 2))
        hi.append(round(max(op, cl) + abs(r.gauss(0, 1.2)), 2))
        lo.append(round(min(op, cl) - abs(r.gauss(0, 1.2)), 2))
        count.append(r.randint(8, 70))
        level = cl
    return {
        "id": "a",
        "times": t,
        "unit": "usd",
        "capped": 0,
        "read_log": False,
        "series": [{"name": "cost", "open": o, "high": hi, "low": lo, "close": c, "count": count}],
    }


def frequency(fr=None, floor=0.6):
    """An empirical answer as query/frequency.py gives it: the floor is the server's, never the page's."""
    return {"id": "a", "frequency": fr or first_order(), "method": "empirical", "samples": 240, "unit": "", "read_log": False,
            "supported": True, "coherence_floor": floor}


CANDLE_META = {"now": NOW, "since": NOW - 3600 * 47, "until": NOW, "step": 3600}
DATA = {
    "line": time_result,
    "bar": categories,
    "scatter": scattered,
    "heatmap": scattered,
    "candlestick": candles,
    "histogram": binned,
    "box": spread,
    "stat": time_result,
    "table": time_result,
    "phase": spiral,
    "bode": lambda: frequency(third_order()),
    "nyquist": lambda: frequency(third_order()),
    "pole-zero": lambda: {
        **frequency(),
        "method": "model",
        "poles": [{"re": -0.5, "im": 0.8}, {"re": -0.5, "im": -0.8}, {"re": -1.4, "im": 0}],
        "zeros": [{"re": -2.0, "im": 0}],
    },
}
FAMILIES = list(DATA)
MOUNT = """([config, result, meta]) => {
  const el = chartPanel(config);
  document.getElementById('page').append(el);
  el.update([result], meta);
  window.last = el;
  return true;
}"""
PAINTED = """(id) => {
  const panel = document.querySelector(`[data-panel-id="${id}"]`);
  const c = panel.querySelector('.plot-base') || panel.querySelector('canvas');
  if (!c) return panel.querySelector('.panel-stat, .panel-data-table') ? 99 : 0;
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, seen = new Set();
  for (let i = 0; i < d.length; i += 44) if (d[i + 3]) seen.add(`${d[i]},${d[i + 1]},${d[i + 2]}`);
  return seen.size;
}"""
LEGEND_CLEAR = """() => {
  const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 && Math.min(a.bottom, b.bottom) -
      Math.max(a.top, b.top) > 0.5;
  const out = [];
  for (const p of document.querySelectorAll('.panel')) {
    const plot = p.querySelector('.plot-frame');
    if (!plot || !plot.getClientRects().length) continue;
    const box = plot.getBoundingClientRect();
    for (const el of p.querySelectorAll('.panel-legend, .panel-keys, .panel-head')) {
      if (el.getClientRects().length && hit(el.getBoundingClientRect(), box)) out.push(`${p.dataset.panelId}: ${el.className}`);
    }
    if ([...plot.children].some((c) => !c.matches('.plot-base, .plot-cursor'))) out.push(`${p.dataset.panelId}: something
      else on the plot`);
  }
  return out;
}"""
NO_SCROLL = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"


def config(form, options=None, pid="p", **extra):
    return {
        "id": pid,
        "title": f"{form} chart",
        "form": form,
        "options": options or {},
        "size": "m",
        "queries": [{"id": "a", "source": "series", "series": "x"}],
        "display": extra.pop("display", {}),
        **extra,
    }


def meta_for(form):
    return CANDLE_META if form == "candlestick" else META


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


class Site:
    def __init__(self, browser, width=1200, height=900, scheme="light"):
        self.context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.asked: list[dict] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.route(f"{ORIGIN}/**", self.serve)
        self.page.goto(f"{ORIGIN}/")

    def serve(self, route):
        path = urlparse(route.request.url).path
        if path == "/":
            route.fulfill(content_type="text/html", body=PAGE)
        elif path.startswith("/static/"):
            f = STATIC / path.removeprefix("/static/")
            route.fulfill(content_type=TYPES.get(f.suffix, "text/plain"), body=f.read_bytes())
        elif path == "/api/query":
            q = parse_qs(urlparse(route.request.url).query)["q"][0]
            payload = json.loads(base64.urlsafe_b64decode(q + "=" * (-len(q) % 4)))
            self.asked.append(payload)
            route.fulfill(json={**META, "results": [{**time_result(q_["id"]), "id": q_["id"]} for q_ in payload["queries"]]})
        else:
            route.fulfill(status=404, body="")

    def mount(self, cfg, result=None, meta=None):
        self.page.evaluate(MOUNT, [cfg, result if result is not None else DATA[cfg["form"]](), meta or meta_for(cfg["form"])])
        self.page.wait_for_function(
            '(id) => { const p = document.querySelector(`[data-panel-id="${id}"]`);'
            " return p.dataset.state !== 'loading' && (!p.plotView || p.plotView.frame.paints > 0); }",
            arg=cfg["id"],
        )

    def model(self):
        return self.page.evaluate("() => JSON.parse(JSON.stringify(last.plotView.model()))")

    def clear(self):
        self.page.evaluate("() => { for (const p of [...document.querySelectorAll('.panel')]) p.destroy(); }")

    def close(self):
        self.context.close()


@pytest.fixture
def site(browser):
    s = Site(browser)
    yield s
    assert not s.errors, s.errors
    s.close()


def test_every_family_is_registered_with_an_options_schema_the_editor_can_read(site):
    forms = site.page.evaluate("""() => Object.fromEntries(Object.entries(plotForms()).map(([k, f]) => [k, {
      label: f.label, group: f.group, needs: f.needs, options: f.options.map((o) => ({ key: o.key, type: o.type, choices:
      o.choices, def: o.default })) }]))""")
    assert set(forms) == set(FAMILIES)
    for name, f in forms.items():
        assert f["label"] and f["group"], name
        assert isinstance(f["needs"], dict), name
        for o in f["options"]:
            assert o["type"] in ("choice", "bool", "number", "field"), (name, o)
            if o["type"] == "choice" and not isinstance(o["def"], list):
                assert o["choices"][0] == o["def"], f"{name}.{o['key']}: the first value is the default"


@pytest.mark.parametrize(
    "old,form,options",
    [
        ("area", "line", {"fill": "area"}),
        ("stacked", "line", {"fill": "area", "stack": "stacked"}),
        ("step", "line", {"style": "step-after"}),
        ("bars", "bar", {"stack": "stacked"}),
        ("hbar", "bar", {"orientation": "horizontal"}),
        ("line", "line", None),
        ("scatter", "scatter", None),
    ],
)
def test_old_form_names_are_normalized(site, old, form, options):
    got = site.page.evaluate("(f) => normalizeForm({ id: 'p', form: f })", old)
    assert got["form"] == form
    assert got.get("options") == options


def test_normalizing_keeps_what_a_panel_chose(site):
    got = site.page.evaluate("() => normalizeForm({ form: 'stacked', options: { style: 'smooth', stack: 'percent' } })")
    assert got["options"] == {"fill": "area", "stack": "percent", "style": "smooth"}
    assert site.page.evaluate("() => normalizeForm({ form: 'bars', display: { stack: false } }).options.stack") == "none"


def option_values(site, family):
    return site.page.evaluate(
        """(name) => plotForms()[name].options.map((o) => ({ key: o.key,
      values: o.type === 'choice' ? (o.multiple ? [['last'], ['avg', 'max']] : o.choices)
        : o.type === 'number' ? [o.min, o.max] : o.key === 'size' ? [3, 'weight'] : ['series', 'tag'] }))""",
        family,
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_each_option_of_each_family_draws(browser, family):
    s = Site(browser)
    try:
        options = option_values(s, family)
        cases = [{}] + [{o["key"]: v} for o in options for v in o["values"]]
        for n, chosen in enumerate(cases):
            cfg = config(family, chosen, pid=f"c{n}")
            s.mount(cfg)
            s.page.locator(f'[data-panel-id="c{n}"]').scroll_into_view_if_needed()
            s.page.wait_for_function(
                "(id) => { const p = document.querySelector(`[data-panel-id=\"${id}\"]`); return p.dataset.state === 'drawn'; }",
                arg=f"c{n}",
            )
            s.page.wait_for_timeout(30)
            assert s.page.evaluate(PAINTED, f"c{n}") > 2, f"{family} {chosen} is blank"
            assert s.page.evaluate(LEGEND_CLEAR) == [], (family, chosen)
            s.clear()
        assert not s.errors, (family, s.errors)
    finally:
        s.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_the_gallery_has_no_page_scroll_and_nothing_on_a_plot(browser, scheme, width):
    s = Site(browser, width=width, height=1000 if width > 500 else 844, scheme=scheme)
    try:
        shown = [
            ("line", {"style": "smooth", "fill": "gradient"}),
            ("line", {"fill": "area", "stack": "percent"}),
            ("line", {"style": "step-middle"}),
            ("bar", {}),
            ("bar", {"orientation": "horizontal", "sort": "value-desc", "values": "on"}),
            ("scatter", {"trend": "linear"}),
            ("scatter", {"size": "weight", "color_by": "tag"}),
            ("phase", {}),
            ("heatmap", {}),
            ("heatmap", {"palette": "diverging", "scale": "log"}),
            ("histogram", {}),
            ("histogram", {"cumulative": "on", "normalize": "percent"}),
            ("box", {}),
            ("box", {"violin": "on", "orientation": "horizontal"}),
            ("candlestick", {"volume": "on"}),
            ("candlestick", {"style": "hollow"}),
            ("candlestick", {"style": "ohlc-bar", "up_is": "bad"}),
            ("bode", {}),
            ("nyquist", {}),
            ("nyquist", {"mirror": "on"}),
            ("pole-zero", {}),
            ("stat", {}),
            ("table", {"bars_in_cells": "on"}),
        ]
        for n, (form, options) in enumerate(shown):
            word = " ".join(str(v) for v in options.values())
            cfg = config(form, options, pid=f"g{n}")
            cfg["title"] = f"{form} {word}".strip()
            if form == "phase":
                cfg["queries"] = [
                    {"id": "a", "source": "series", "series": "y", "x": {"type": "query", "query": "b"}},
                    {"id": "b", "source": "series", "series": "x"},
                ]
            if form == "scatter" and "size" in options:
                cfg["display"] = {"x": {"label": "Net lines"}}
            s.mount(cfg)
            s.page.locator(f'[data-panel-id="g{n}"]').scroll_into_view_if_needed()
            s.page.wait_for_timeout(25)
            assert s.page.evaluate(PAINTED, f"g{n}") > 2, form
        assert s.page.evaluate(NO_SCROLL), "the page scrolls sideways"
        assert s.page.evaluate(LEGEND_CLEAR) == []
        out = os.environ.get("PLOT_SHOTS")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            s.page.evaluate("window.scrollTo(0, 0)")
            s.page.wait_for_timeout(100)
            s.page.screenshot(path=f"{out}/forms-{scheme}-{width}.png", full_page=True)
        assert not s.errors, s.errors
    finally:
        s.close()


def test_bode_of_a_first_order_system_reads_its_exact_response(site):
    site.mount(config("bode"), frequency(first_order(gain=2.0, corner=0.01)))
    m = site.model()
    at = min(m["pts"], key=lambda p: abs(math.log(p["hz"] / 0.01)))
    assert at["hz"] == pytest.approx(0.01, rel=1e-6)
    assert at["db"] == pytest.approx(20 * math.log10(2) - 10 * math.log10(2), abs=1e-6), "-3 dB at the corner"
    assert at["deg"] == pytest.approx(-45, abs=1e-6)
    decade = sorted(m["pts"], key=lambda p: p["hz"])[-13:]
    slope = (decade[-1]["db"] - decade[0]["db"]) / math.log10(decade[-1]["hz"] / decade[0]["hz"])
    assert slope == pytest.approx(-20, abs=0.1), "-20 dB per decade above the corner"
    assert m["panes"]["upperBottom"] < m["panes"]["lowerTop"], "magnitude over phase"
    assert m["panes"]["decades"] >= 4, "decades marked on the shared log axis"


def test_bode_carries_phase_past_180_degrees_and_says_where_it_is_unreliable(site):
    fr = third_order()
    site.mount(config("bode"), frequency(fr))
    m = site.model()
    degs = [p["deg"] for p in m["pts"]]
    assert min(degs) < -200, "three lags pass -180 degrees"
    assert all(abs(b - a) < 60 for a, b in zip(degs, degs[1:], strict=False)), "no jump of a turn"
    assert len(m["bands"]) == 1
    assert m["bands"][0][0] < fr["hz"][50] < fr["hz"][61] < m["bands"][0][1]
    assert "unreliable" in site.page.locator(".panel-legend").inner_text()


def test_bode_can_hide_low_coherence_and_says_it_did(site):
    site.mount(config("bode", {"coherence": "hide-low"}), frequency(third_order()))
    assert len(site.model()["pts"]) == 121 - 12
    assert "12 of 121 points hidden" in site.page.locator(".panel-legend").inner_text()


def test_bode_marks_unreliable_points_by_the_servers_floor_not_its_own(site):
    """dev/records/frequency-refuses-noise.md: the panel uses the floor the server sends, and says it."""
    site.mount(config("bode"), frequency(third_order(), floor=0.96))
    assert sum(p["low"] for p in site.model()["pts"]) == 121, "0.95 is under the server's 0.96"
    assert "coherence under 0.96" in site.page.locator(".panel-legend").inner_text()
    site.clear()
    site.mount(config("bode"), frequency(third_order(), floor=0.2))
    assert sum(p["low"] for p in site.model()["pts"]) == 0, "0.3 is over the server's 0.2"


def test_coherence_with_no_floor_sent_is_all_unreliable(site):
    site.mount(config("bode"), {**frequency(first_order()), "coherence_floor": None})
    assert all(p["low"] for p in site.model()["pts"])
    assert "none sent" in site.page.locator(".panel-legend").inner_text()


@pytest.mark.parametrize("form", ["bode", "nyquist"])
def test_a_record_the_server_refuses_is_said_and_no_curve_is_drawn(site, form):
    """dev/records/frequency-refuses-noise.md: the server's decision is shown, never redrawn as a response."""
    why = "no frequency is coherent past chance: the highest coherence is 0.81"
    empty = {k: [] for k in ("hz", "magnitude_db", "phase_deg", "re", "im", "coherence")}
    site.mount(config(form), {**frequency(empty, floor=0.97), "supported": False, "refused": why, "coherence_peak": 0.81})
    panel = site.page.locator(".panel")
    assert panel.get_attribute("data-state") == "empty"
    said = site.page.locator(".panel-message").inner_text()
    assert "cannot support a frequency response" in said and why in said
    assert site.page.locator(".plot-base").count() == 0
    site.clear()
    refused_with_points = {**frequency(third_order(), floor=0.5), "supported": False, "refused": why}
    site.mount(config(form), refused_with_points)
    assert site.page.locator(".plot-base").count() == 0, "a refused record is not drawn even if points came with it"


def test_bode_wrapped_phase_stays_within_a_turn(site):
    site.mount(config("bode", {"phase_wrap": "wrapped"}), frequency(third_order()))
    assert all(-180 <= p["deg"] <= 180 for p in site.model()["pts"])


def test_a_model_response_without_coherence_is_all_reliable(site):
    fr = {**first_order(), "coherence": None}
    site.mount(config("bode"), {**frequency(fr), "method": "model"})
    assert site.model()["bands"] == []
    assert "identified model" in site.page.locator(".panel-legend").inner_text()


def test_nyquist_has_equal_axes_the_critical_point_and_direction(site):
    fr = first_order(gain=2.0, corner=0.01)
    site.mount(config("nyquist"), frequency(fr))
    m = site.model()
    assert m["perX"] == pytest.approx(m["perY"], rel=1e-6), "one unit is the same length on both axes"
    assert m["arrows"] >= 2
    for p in m["pts"]:
        assert (p["re"] - 1) ** 2 + p["im"] ** 2 == pytest.approx(1, abs=1e-6), "a first-order lag is a circle through 0 and K"
    assert [p["hz"] for p in m["pts"]] == sorted(p["hz"] for p in m["pts"]), "drawn in order of rising frequency"
    x, y = m["minus1"]["x"], m["minus1"]["y"]
    colour = site.page.evaluate(
        """([x, y]) => { const c = last.querySelector('.plot-base'), r = devicePixelRatio;
      return [...c.getContext('2d').getImageData(Math.round(x * r), Math.round(y * r), 1, 1).data]; }""",
        [x, y],
    )
    assert colour[0] > 150 and colour[1] < 110, "the -1 point is marked in the failure ink"
    legend = site.page.locator(".panel-legend").inner_text()
    assert "critical point" in legend and "unit circle" in legend and "frequency increasing" in legend


def test_nyquist_options(site):
    site.mount(config("nyquist", {"unit_circle": "off", "mirror": "on", "coherence": "hide-low"}), frequency(third_order()))
    m = site.model()
    assert not m["circle"] and m["mirror"] and len(m["pts"]) == 109
    assert "unit circle" not in site.page.locator(".panel-legend").inner_text()


def test_pole_zero_uses_equal_axes_and_names_the_unstable_half(site):
    site.mount(config("pole-zero"))
    m = site.model()
    assert m["perX"] == pytest.approx(m["perY"], rel=1e-6)
    assert len(m["poles"]) == 3 and len(m["zeros"]) == 1
    assert "unstable" in site.page.locator(".panel-legend").inner_text()


def test_phase_portrait_is_joined_in_time_order_with_marks(site):
    r = spiral()
    order = list(range(120))
    random.Random(1).shuffle(order)
    one = r["series"][0]
    shuffled = {
        **r,
        "series": [
            {
                **one,
                "xs": [one["xs"][i] for i in order],
                "values": [one["values"][i] for i in order],
                "times": [one["times"][i] for i in order],
            }
        ],
    }
    site.mount(config("phase"), shuffled)
    m = site.model()
    assert m["start"]["x"] == pytest.approx(one["xs"][0]) and m["start"]["y"] == pytest.approx(one["values"][0])
    assert m["end"]["x"] == pytest.approx(one["xs"][-1]) and m["end"]["y"] == pytest.approx(one["values"][-1])
    assert m["marks"] >= 5, "direction marks along the path"
    legend = site.page.locator(".panel-legend").inner_text()
    assert "start" in legend and "end" in legend and "direction" in legend


def test_phase_options_turn_their_marks_off(site):
    site.mount(config("phase", {"direction": "off", "markers": "off", "fade": "off"}))
    m = site.model()
    assert m["marks"] == 0 and m["start"] is None


def test_quartiles_and_each_whisker_rule(site):
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100]
    result = {"id": "a", "times": TIMES[:11], "unit": "s", "series": [{"name": "x", "values": values}]}
    site.mount(config("box", pid="b1"), result)
    b = site.model()["boxes"][0]
    assert (b["q1"], b["median"], b["q3"]) == (3.5, 6, 8.5), "numpy's default quartiles"
    assert (b["lo"], b["hi"], b["outliers"]) == (1, 10, [100]), "Tukey: furthest value within 1.5 IQR"
    site.clear()
    site.mount(config("box", {"whiskers": "min-max"}, pid="b2"), result)
    b = site.model()["boxes"][0]
    assert (b["lo"], b["hi"], b["outliers"]) == (1, 100, [])
    site.clear()
    site.mount(config("box", {"whiskers": "p5-p95"}, pid="b3"), result)
    b = site.model()["boxes"][0]
    assert b["lo"] == pytest.approx(1.5) and b["hi"] == pytest.approx(55)


def test_a_box_given_its_statistics_draws_them_as_given(site):
    given = {"q1": 2, "median": 3, "q3": 5, "lo": 1, "hi": 9, "outliers": [20], "n": 50}
    site.mount(config("box"), {"id": "a", "times": TIMES[:1], "unit": "s", "series": [{"name": "x", "values": [3], "box": given}]})
    b = site.model()["boxes"][0]
    assert (b["q1"], b["median"], b["q3"], b["lo"], b["hi"], b["outliers"]) == (2, 3, 5, 1, 9, [20])
    assert "as given" in site.page.locator(".panel-legend").inner_text()


def test_a_box_from_the_answers_statistics_follows_the_whisker_rule(site):
    given = {"n": 5, "min": 1, "max": 100, "p5": 1.2, "q1": 2, "median": 3, "q3": 4, "p95": 80.8,
             "lo": 1, "hi": 4, "outliers": [100], "outliers_more": 0}
    result = {"id": "a", "x": {"type": "category", "label": "state", "unit": "", "scale": "category", "distribution": True}, "unit": "usd",
              "series": [{"name": "doing", "xs": ["doing"] * 5, "values": [1, 2, 3, 4, 100], "box": given}]}
    for n, (rule, lo, hi, out) in enumerate([("tukey", 1, 4, [100]), ("min-max", 1, 100, []), ("p5-p95", 1.2, 80.8, [1, 100])]):
        site.mount(config("box", {"whiskers": rule}, pid=f"w{n}"), result)
        b = site.model()["boxes"][0]
        assert (b["q1"], b["median"], b["q3"], b["lo"], b["hi"], b["outliers"]) == (2, 3, 4, lo, hi, out), rule
        site.clear()


@pytest.mark.parametrize("asked", [{}, {"group_by": "size"},
                                   {"x": {"type": "category", "by": "risk"}, "agg": "sum", "transform": "rate", "rate_per": "hour"}])
def test_box_asks_for_each_items_value_by_category(site, asked):
    q = {"id": "a", "source": "items", "kind": "k", "field": "cost", **asked}
    site.page.evaluate("(q) => queryPanels([{ id: 'p', form: 'box', queries: [q] }], {})", q)
    sent = site.asked[-1]["queries"][0]
    by = asked.get("x", {}).get("by") or asked.get("group_by") or "state"
    assert sent["agg"] == "none" and sent["x"] == {"type": "category", "by": by}
    assert not {"group_by", "transform", "rate_per"} & set(sent)


def test_choosing_box_in_the_editor_asks_for_each_items_value(site):
    site.page.add_script_tag(url="/static/panel-editor.js")
    site.page.evaluate("""() => { window.ed = openPanelEditor({ id: 'e', title: 'Box', form: 'line', display: {},
      queries: [{ id: 'a', source: 'items', kind: 'k', field: 'cost', agg: 'sum', transform: 'none' }] }, {}); }""")
    site.page.wait_for_function("document.querySelector('input[type=radio][value=box]')")
    site.page.wait_for_timeout(500)
    site.page.evaluate("document.querySelector('input[type=radio][value=box]').click()")
    site.page.wait_for_timeout(700)
    sent = site.asked[-1]["queries"][0]
    assert sent["agg"] == "none" and sent["x"] == {"type": "category", "by": "state"}


def test_a_spread_on_another_chart_says_so(site):
    result = {"id": "a", "x": {"type": "category", "label": "state", "scale": "category", "distribution": True}, "unit": "",
              "series": [{"name": "s", "xs": ["s"], "values": [1]}]}
    site.mount(config("bar"), result)
    assert site.page.locator(".panel").get_attribute("data-state") == "empty"
    assert "box plot" in site.page.locator(".panel-message").inner_text()


def test_histogram_normalizes_truly(site):
    edges = [0.0, 1.0, 2.0, 4.0]
    result = {
        "id": "a",
        "x": {"type": "bins", "label": "v", "unit": "s", "scale": "number", "edges": edges},
        "unit": "",
        "series": [{"name": "n", "xs": [0.5, 1.5, 3.0], "values": [2, 6, 2]}],
    }
    for options, want in [
        ({}, [2, 6, 2]),
        ({"normalize": "percent"}, [20, 60, 20]),
        ({"normalize": "density"}, [0.2, 0.6, 0.1]),
        ({"cumulative": "on"}, [2, 8, 10]),
        ({"cumulative": "on", "normalize": "percent"}, [20, 80, 100]),
        ({"cumulative": "on", "normalize": "density"}, [0.2, 0.8, 1.0]),
    ]:
        site.mount(config("histogram", options), result)
        assert site.model()["shaped"][0] == pytest.approx(want), options
        site.clear()


def test_histogram_bins_raw_values_counting_each_once_and_stacks(site):
    result = {
        "id": "a",
        "times": TIMES[:6],
        "unit": "s",
        "series": [{"name": "a", "values": [0, 1, 2, 3, 4, 10]}, {"name": "b", "values": [0, 0, 5, 5, 10, None]}],
    }
    site.mount(config("histogram", {"bins": 5, "stack": "stacked"}), result)
    m = site.model()
    assert m["edges"] == pytest.approx([0, 2, 4, 6, 8, 10])
    assert m["counts"] == [[2, 2, 1, 0, 1], [2, 0, 2, 0, 1]]
    assert m["tops"][1] == pytest.approx([4, 2, 3, 0, 2])


def test_heatmap_counts_every_point_and_labels_its_scale(site):
    site.mount(config("heatmap", {"y_bins": 8}))
    m = site.model()
    assert m["total"] == 160
    assert len(m["counts"][0]) == 8
    assert m["at"][0] == 0 and m["at"][2] == 1
    site.clear()
    site.mount(config("heatmap", {"scale": "log"}))
    m = site.model()
    assert m["at"][1] == pytest.approx(math.log(2) / math.log(1 + m["top"]))


def test_candles_skip_an_empty_bucket_and_mark_rises_by_open_and_close(site):
    r = candles()
    site.mount(config("candlestick", {"volume": "on"}), r, CANDLE_META)
    m = site.model()
    assert len(m["candles"]) == 47 and m["volume"] is True
    assert all(c["low"] <= min(c["open"], c["close"]) and c["high"] >= max(c["open"], c["close"]) for c in m["candles"])
    assert all(c["up"] == (c["close"] >= c["open"]) for c in m["candles"])


def test_a_candlestick_without_ohlc_says_what_it_needs(site):
    site.mount(config("candlestick"), time_result())
    assert site.page.locator(".panel").get_attribute("data-state") == "empty"
    assert "ohlc" in site.page.locator(".panel-message").inner_text()


def test_candlestick_asks_for_ohlc(site):
    site.page.evaluate(
        "() => queryPanels([{ id: 'p', form: 'candlestick', queries: [{ id: 'a', source: 'series', series: 'x', agg: 'avg' }] }], {})"
    )
    assert site.asked[-1]["queries"][0]["agg"] == "ohlc"


def test_bar_sorts_stacks_to_percent_and_keeps_values_off_the_plot(site):
    two = {
        **categories(),
        "series": [
            categories()["series"][0],
            {"name": "other cost", "xs": categories()["series"][0]["xs"], "values": [12.5, 16.0, 31.25, 2.5, 4.0, 4.0], "ids": None},
        ],
    }
    site.mount(config("bar", {"sort": "value-desc", "orientation": "horizontal", "values": "on"}), categories())
    m = site.model()
    assert m["order"][:2] == ["merged", "building"] and m["horizontal"] is True
    site.clear()
    site.mount(config("bar", {"stack": "percent"}), two)
    tops = [b["to"] for b in site.model()["bars"]]
    assert max(tops) == pytest.approx(100)
    site.clear()
    site.mount(config("bar", {"grouping": "overlaid"}), two)
    assert site.model()["lanes"] == 1


@pytest.mark.parametrize(
    "options",
    [
        {"style": "smooth"},
        {"style": "step-after"},
        {"style": "step-before"},
        {"fill": "gradient"},
        {"stack": "percent", "fill": "area"},
        {"points": "always"},
        {"width": 4},
        {"nulls": "connect"},
        {"nulls": "zero"},
        {"fill": "area", "stack": "stacked", "style": "smooth"},
    ],
)
def test_line_options_on_the_time_plot(site, options):
    site.mount(config("line", options))
    site.page.wait_for_selector(".u-over")
    assert site.page.evaluate("() => !last.plotView")
    assert site.page.evaluate(PAINTED, "p") > 2


def test_step_middle_turns_halfway_between_points(site):
    assert site.page.evaluate("() => plotTrace([[0, 0], [2, 4]], 'step-middle')") == [[0, 0], [1, 0], [1, 4], [2, 4]]
    assert site.page.evaluate("() => plotTrace([[0, 0], [2, 4]], 'step-after')") == [[0, 0], [2, 0], [2, 4]]
    assert site.page.evaluate("() => plotTrace([[0, 0], [2, 4]], 'step-before')") == [[0, 0], [0, 4], [2, 4]]


def test_a_smoothed_line_never_overshoots_its_points(site):
    ys = site.page.evaluate("() => plotTrace([[0, 0], [1, 10], [2, 10.5], [3, 0], [4, 0]], 'smooth').map((p) => p[1])")
    assert max(ys) <= 10.5 + 1e-9 and min(ys) >= -1e-9


def test_scatter_trend_is_least_squares(site):
    xs = [1, 2, 3, 4, 5]
    r = {
        "id": "a",
        "x": {"type": "field", "label": "a", "unit": ""},
        "unit": "",
        "series": [{"name": "y", "xs": xs, "values": [3 + 2 * x for x in xs], "times": None, "ids": None}],
    }
    site.mount(config("scatter", {"trend": "linear"}), r)
    fit = site.model()["fits"][0]
    assert fit["slope"] == pytest.approx(2) and fit["intercept"] == pytest.approx(3) and fit["r2"] == pytest.approx(1)


def test_scatter_asks_for_bubble_size_and_colour_with_its_x(site):
    site.page.evaluate("""() => queryPanels([{ id: 'p', form: 'scatter', options: { size: 'weight', color_by: 'state' },
      queries: [{ id: 'a', source: 'items', kind: 'k', field: 'y', x: { type: 'field', field: 'x' } }] }], {})""")
    assert site.asked[-1]["queries"][0]["x"] == {"type": "field", "field": "x", "size": "weight", "color_by": "state"}


def test_histogram_asks_for_its_number_of_bins(site):
    site.page.evaluate("""() => queryPanels([{ id: 'p', form: 'histogram', options: { bins: 7 },
      queries: [{ id: 'a', source: 'items', kind: 'k', field: 'y', x: { type: 'bins', field: 'y' } }] }], {})""")
    assert site.asked[-1]["queries"][0]["x"]["bins"] == 7


@pytest.mark.parametrize("family", [f for f in FAMILIES if f not in ("stat", "table")])
def test_the_four_states(browser, family):
    s = Site(browser)
    try:
        cfg = config(family)
        s.page.evaluate("(c) => { window.last = chartPanel(c); document.getElementById('page').append(last); }", cfg)
        state = "document.querySelector('.panel').dataset.state"
        assert s.page.evaluate(state) == "loading"
        s.page.evaluate("() => last.setState('late', 'waiting')")
        assert "Still loading" in s.page.locator(".panel-message").inner_text(), "a first load is never said as a failure"
        s.page.evaluate("() => last.update([{ id: 'a', error: 'no field named x' }], {})")
        assert s.page.evaluate(state) == "error" and "no field named x" in s.page.locator(".panel-message").inner_text()
        s.page.evaluate("([r, m]) => last.update([r], m)", [DATA[family](), meta_for(family)])
        s.page.wait_for_selector(".plot-base, .u-over")
        assert s.page.evaluate(state) == "drawn"
        s.page.evaluate("() => last.update([{ id: 'a', error: 'it broke' }], {})")
        assert s.page.locator(".panel-flag").inner_text() == "Error", "the drawing stays and the head says so"
        assert s.page.locator(".plot-base, .u-over").count() >= 1
        empty = {"id": "a", "times": TIMES, "unit": "", "series": [{"name": "x", "values": [None] * 120}]}
        if family in ("bode", "nyquist", "pole-zero"):
            empty = {"id": "a", "frequency": {"hz": [], "magnitude_db": [], "phase_deg": [], "re": [], "im": [], "coherence": []}}
        s.page.evaluate("(r) => last.update([r], {})", empty)
        assert s.page.evaluate(state) == "empty"
        assert not s.errors
    finally:
        s.close()


@pytest.mark.parametrize("family", ["scatter", "phase", "heatmap", "histogram", "box", "bode", "nyquist", "candlestick"])
def test_a_refresh_repaints_the_same_canvas(site, family):
    site.mount(config(family))
    site.page.evaluate("() => { window.kept = last.querySelector('.plot-base'); window.paints = last.plotView.frame.paints; }")
    site.page.evaluate("([r, m]) => last.update([r], m)", [DATA[family](), meta_for(family)])
    assert site.page.evaluate("() => last.querySelector('.plot-base') === kept && last.plotView.frame.paints > paints")


def test_the_cursor_is_read_in_the_head_and_marks_only_its_own_canvas(site):
    site.mount(config("bode"), frequency(first_order()))
    box = site.page.locator(".plot-cursor").bounding_box()
    before = site.page.evaluate("() => last.querySelector('.plot-base').toDataURL()")
    site.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 3)
    site.page.wait_for_function("document.querySelector('.panel-readout').textContent.includes('Hz')")
    assert "dB" in site.page.locator(".panel-readout").inner_text()
    assert site.page.evaluate("() => last.querySelector('.plot-base').toDataURL()") == before
    site.page.mouse.move(1, 1)
    site.page.wait_for_function("document.querySelector('.panel-readout').textContent === ''")


def test_a_theme_change_repaints(browser):
    s = Site(browser, scheme="light")
    try:
        s.mount(config("nyquist"))
        light = s.page.evaluate("() => last.querySelector('.plot-base').toDataURL()")
        s.page.emulate_media(color_scheme="dark")
        s.page.wait_for_function("(a) => last.querySelector('.plot-base').toDataURL() !== a", arg=light)
        assert not s.errors
    finally:
        s.close()


TWO = [
    {
        "id": pid,
        "form": "phase",
        "queries": [
            {"id": "a", "source": "series", "series": f"{pid}-y", "x": {"type": "query", "query": "b"}},
            {"id": "b", "source": "series", "series": f"{pid}-x"},
        ],
    }
    for pid in ("p1", "p2")
]


def test_two_panels_each_with_a_and_b_keep_their_own_x(site):
    got = site.page.evaluate(
        """async (c) => { const m = await queryPanels(c, {});
      return Object.fromEntries([...m].map(([k, v]) => [k, v.results.map((r) => r.id)])); }""",
        TWO,
    )
    sent = {q["id"]: q for q in site.asked[-1]["queries"]}
    assert len(sent) == 4, "both panels' a and b"
    for pid in ("p1", "p2"):
        y = next(q for q in sent.values() if q.get("series") == f"{pid}-y")
        assert sent[y["x"]["query"]]["series"] == f"{pid}-x"
    assert got == {"p1": ["a"], "p2": ["a"]}, "b is the X of a, and is not drawn as a series"


def test_a_hidden_query_used_as_an_x_is_still_sent(site):
    cfg = {
        "id": "p",
        "form": "phase",
        "queries": [
            {"id": "a", "source": "series", "series": "y", "x": {"type": "query", "query": "b"}},
            {"id": "b", "source": "series", "series": "x", "hidden": True},
            {"id": "c", "source": "series", "series": "unused", "hidden": True},
        ],
    }
    got = site.page.evaluate("async (c) => (await queryPanels([c], {})).get('p').results.map((r) => r.id)", cfg)
    sent = site.asked[-1]["queries"]
    assert {q["series"] for q in sent} == {"y", "x"}
    assert got == ["a"]


def test_a_query_feeding_a_hidden_query_is_drawn_itself(site):
    cfg = {
        "id": "p",
        "form": "line",
        "queries": [
            {"id": "a", "source": "series", "series": "y", "hidden": True, "x": {"type": "query", "query": "b"}},
            {"id": "b", "source": "series", "series": "x"},
        ],
    }
    got = site.page.evaluate("async (c) => (await queryPanels([c], {})).get('p').results.map((r) => r.id)", cfg)
    assert got == ["b"] and [q["series"] for q in site.asked[-1]["queries"]] == ["x"]


def test_a_frequency_querys_parts_are_sent_inside_it_and_not_drawn(site):
    cfg = {
        "id": "p",
        "form": "bode",
        "queries": [
            {
                "id": "f",
                "source": "frequency",
                "input": "u",
                "output": {"id": "zz", "label": "out", "source": "series", "series": "y"},
                "segments": 4,
            },
            {"id": "u", "source": "series", "series": "x", "label": "in"},
        ],
    }
    got = site.page.evaluate("async (c) => (await queryPanels([c], {})).get('p').results.map((r) => r.id)", cfg)
    sent = site.asked[-1]["queries"]
    assert (
        len(sent) == 1
        and sent[0]["input"] == {"source": "series", "series": "x"}
        and sent[0]["output"] == {"source": "series", "series": "y"}
    )
    assert got == ["f"]


def test_a_reference_to_nothing_is_not_taken_for_another_query(site):
    cfg = {"id": "p", "form": "phase", "queries": [{"id": "a", "source": "series", "series": "y", "x": {"type": "query", "query": "q0"}}]}
    site.page.evaluate("(c) => queryPanels([c], {})", cfg)
    assert site.asked[-1]["queries"][0]["x"]["query"] == "unknown:q0"


def test_a_panel_draws_only_its_shown_series_from_an_answer_with_its_x(site):
    cfg = {
        "id": "p",
        "title": "t",
        "form": "phase",
        "display": {},
        "queries": [
            {"id": "a", "source": "series", "series": "y", "x": {"type": "query", "query": "b"}},
            {"id": "b", "source": "series", "series": "x"},
        ],
    }
    site.page.evaluate(
        """([c, a, b, m]) => { window.last = chartPanel(c); document.getElementById('page').append(last); last.update([a, b], m); }""",
        [cfg, spiral(), {**time_result("b"), "id": "b"}, META],
    )
    site.page.wait_for_selector(".plot-base")
    assert len(site.model()["order"]) == 1


def test_stat_and_table_options(site):
    r = {
        "id": "a",
        "times": TIMES[:4],
        "unit": "items",
        "series": [{"name": "x", "values": [1, 2, 3, 10]}, {"name": "y", "values": [4, 4, 4, 4]}],
    }
    site.mount(
        config(
            "stat",
            {"value": "sum", "sparkline": "off", "delta": "off", "color": "thresholds"},
            pid="s",
            display={"thresholds": [{"value": 5}, {"value": 15}]},
        ),
        r,
    )
    nums = site.page.locator(".panel-stat-num")
    assert nums.nth(0).inner_text().startswith("16") and nums.nth(1).inner_text().startswith("16")
    assert "is-bad" in nums.nth(0).get_attribute("class")
    assert not site.page.locator(".panel-stat .panel-spark").first.is_visible()
    site.clear()
    site.mount(config("table", {"columns": ["max"], "sort": "max", "bars_in_cells": "on"}, pid="t"), r)
    assert site.page.locator(".panel-data-table thead th").all_inner_texts()[:2] == ["Series", "Max"]
    assert site.page.locator(".panel-data-table tbody tr").first.inner_text().startswith("x")
    assert site.page.locator("td.panel-cell-bar").count() == 2


COARSE = {"id": "a", "times": [NOW + 1200 * i for i in range(4)], "unit": "items",
          "series": [{"name": "slow", "values": [10, 20, None, 40]}]}
FINE = {"id": "b", "times": [NOW + 720 * i for i in range(5)], "unit": "items", "series": [{"name": "fast", "values": [1, 2, 3, 4, 5]}]}
MIXED_META = {"now": NOW + 3600, "since": NOW, "until": NOW + 3600, "step": 720}


def mixed(form="line", options=None):
    two = [{"id": "a", "source": "series", "series": "slow"}, {"id": "b", "source": "moves", "kind": "k"}]
    return {**config(form, options or {}), "queries": two}


def mount_two(site, cfg, *results):
    mounting = "([c, r, m]) => { window.last = chartPanel(c); document.getElementById('page').append(last); last.update(r, m); }"
    site.page.evaluate(mounting, [cfg, list(results), MIXED_META])
    site.page.wait_for_function("() => last.dataset.state !== 'loading'")


def test_queries_on_different_steps_each_keep_their_real_points(site):
    mount_two(site, mixed(), COARSE, FINE)
    site.page.wait_for_selector(".u-over")
    got = site.page.evaluate("""() => { const u = [...PLOTS].at(-1);
      const shown = (row) => Array.from(row, (v) => v === undefined ? 'none' : v);
      return { t: [...u.data[0]], a: shown(u.data[1]), b: shown(u.data[2]) }; }""")
    # union of 0, 1200, 2400, 3600 and 0, 720, 1440, 2160, 2880
    assert [x - NOW for x in got["t"]] == [0, 720, 1200, 1440, 2160, 2400, 2880, 3600]
    assert got["a"] == [10, "none", 20, "none", "none", None, "none", 40], "its own values, its empty bucket a gap, nothing invented"
    assert got["b"] == [1, 2, "none", 3, 4, "none", 5, "none"]


def test_the_coarser_line_is_drawn_between_its_own_points_and_not_across_its_gap(site):
    mount_two(site, mixed(), COARSE, {**FINE, "series": [{"name": "fast", "values": [1, 1, 1, 1, 1]}]})
    site.page.wait_for_selector(".u-over")
    site.page.wait_for_timeout(50)
    inked = """([from, to]) => { const u = [...PLOTS].at(-1), r = devicePixelRatio, hex = u.series[1].stroke();
      const want = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
      const t = u.data[0][0] + (from + to) / 2, v = u.data[1][u.data[0].indexOf(u.data[0][0] + from)];
      const w = u.data[1][u.data[0].indexOf(u.data[0][0] + to)] ?? v, x = Math.round(u.valToPos(t, 'x', true));
      const y = Math.round(u.valToPos((v + w) / 2, 'y', true)), d = u.ctx.getImageData(x - 2 * r, y - 5 * r, 4 * r, 10 * r).data;
      const near = (i) => Math.abs(d[i] - want[0]) + Math.abs(d[i + 1] - want[1]) + Math.abs(d[i + 2] - want[2]) < 60;
      for (let i = 0; i < d.length; i += 4) if (near(i)) return true;
      return false; }"""
    assert site.page.evaluate(inked, [0, 1200]), "joined between its own buckets, across the other query's times"
    assert not site.page.evaluate(inked, [1200, 3600]), "its empty bucket stays a gap"


def test_stacking_different_steps_sums_only_where_they_share_a_time_and_says_so(site):
    mount_two(site, mixed("line", {"fill": "area", "stack": "stacked"}), COARSE, FINE)
    site.page.wait_for_selector(".u-over")
    top = site.page.evaluate("() => Array.from([...PLOTS].at(-1).data[2], (v) => v === undefined ? 'none' : v)")
    assert top == [11, "none", "none", "none", "none", "none", "none", "none"]
    assert "1 of 8 times" in site.page.locator(".panel-warning").inner_text()


@pytest.mark.parametrize("family", FAMILIES)
def test_what_an_answer_says_of_itself_is_shown_beside_the_plot(browser, family):
    s = Site(browser)
    try:
        said = "only the latest 19971 of 90677 events were read"
        s.mount(config(family), {**DATA[family](), "note": said, "truncated": True})
        words = s.page.locator(".panel-warning")
        words.wait_for()
        assert "19971 of 90677" in words.inner_text()
        over = s.page.evaluate("""() => { const w = document.querySelector('.panel-warning').getBoundingClientRect();
          const p = document.querySelector('.plot-frame, .uplot, .panel-stats, .panel-table').getBoundingClientRect();
          return Math.min(w.bottom, p.bottom) - Math.max(w.top, p.top) > 0.5; }""")
        assert not over, "never over the plot"
        assert s.page.evaluate(NO_SCROLL)
        s.page.evaluate("([r, m]) => last.update([r], m)", [DATA[family](), meta_for(family)])
        assert s.page.locator(".panel-warning").is_hidden(), "gone when the answer no longer says it"
    finally:
        s.close()


def test_a_truncated_answer_with_no_note_still_says_so(site):
    site.mount(config("line"), {**time_result(), "truncated": True})
    assert "Only part of the record" in site.page.locator(".panel-warning").inner_text()


def test_busy_queries_are_asked_again_until_they_answer(browser):
    s = Site(browser)
    try:
        calls: list[list[str]] = []
        def serve(route):
            q = parse_qs(urlparse(route.request.url).query)["q"][0]
            body = json.loads(base64.urlsafe_b64decode(q + "=" * (-len(q) % 4)))
            ids = [x["id"] for x in body["queries"]]
            calls.append(ids)
            refused = {"error": "events: busy: the event log is being read"}
            results = [{**time_result(i), "id": i} if n < 4 else {"id": i, **refused} for n, i in enumerate(ids)]
            route.fulfill(json={**META, "results": results})
        s.page.route("**/api/query?*", serve)
        got = s.page.evaluate("""async () => { const c = Array.from({ length: 6 }, (_, i) => ({ id: `p${i}`, form: 'line',
          queries: [{ id: 'a', source: 'events', type: `t${i}` }] }));
          const m = await queryPanels(c, {}); return [...m.values()].map((v) => v.results[0].error || 'ok'); }""")
        assert got == ["ok"] * 6 and [len(c) for c in calls] == [6, 2], "only the refused are asked for again"
    finally:
        s.close()


def test_a_query_still_busy_after_the_retries_says_so(browser):
    s = Site(browser)
    try:
        calls = []
        def serve(route):
            calls.append(1)
            q = parse_qs(urlparse(route.request.url).query)["q"][0]
            body = json.loads(base64.urlsafe_b64decode(q + "=" * (-len(q) % 4)))
            route.fulfill(json={**META, "results": [{"id": x["id"], "error": "events: busy: try again"} for x in body["queries"]]})
        s.page.route("**/api/query?*", serve)
        got = s.page.evaluate("""async () => (await queryPanels([{ id: 'p', form: 'line',
          queries: [{ id: 'a', source: 'events' }] }], {})).get('p').results[0].error""")
        assert "busy" in got and len(calls) == 4, "bounded: the first and three more"
    finally:
        s.close()


def test_a_phase_portrait_marks_desired_levels_on_either_axis_and_every_form_is_named(site):
    cfg = config("phase", display={"thresholds": [{"value": 5, "label": "desired rate"}], "x": {"thresholds": [{"value": 45}]}})
    site.mount(cfg)
    assert site.model()["levels"] == {"x": 1, "y": 1}
    legend = site.page.locator(".panel-legend").inner_text()
    assert "desired rate" in legend and "desired X" in legend
    assert site.page.locator(".plot-base").get_attribute("role") == "img"
    assert site.page.locator(".plot-base").get_attribute("aria-label") == "Phase portrait: phase chart"


def test_a_stacked_percent_histogram_is_each_series_share_of_its_bin(site):
    edges = [0.0, 1.0, 2.0]
    x = {"type": "bins", "label": "v", "unit": "", "scale": "number", "edges": edges}
    two = {"id": "a", "x": x, "unit": "",
           "series": [{"name": "a", "xs": [0.5, 1.5], "values": [1, 6]}, {"name": "b", "xs": [0.5, 1.5], "values": [3, 2]}]}
    site.mount(config("histogram", {"normalize": "percent", "stack": "stacked"}), two)
    m = site.model()
    assert m["shaped"] == [[25, 75], [75, 25]] and m["tops"][1] == [100, 100]      # 1 of 4, 3 of 4; 6 of 8, 2 of 8
    site.clear()
    site.mount(config("histogram", {"normalize": "percent", "stack": "stacked", "cumulative": "on"}), two)
    m = site.model()                                                                # running: a 1, 7; b 3, 5
    assert m["shaped"][0] == pytest.approx([25, 58.3333], abs=1e-3) and m["tops"][1] == pytest.approx([100, 100])
    site.clear()
    site.mount(config("histogram", {"normalize": "density", "stack": "stacked"}), two)
    assert site.model()["tops"][1] == pytest.approx([1 / 3, 2 / 3]), "the stack's area is 1: 4 of 12 and 8 of 12"


def test_a_percent_bar_of_a_time_query_is_each_ones_share_of_the_whole(site):
    series = [{"name": n, "values": [9, v]} for n, v in (("ready", 10), ("review", 30), ("merged", 60))]
    answer = {"id": "a", "times": TIMES[:2], "unit": "items", "series": series}
    site.mount(config("bar", {"sort": "value-desc", "stack": "percent"}), answer)
    m = site.model()
    assert m["order"] == ["merged", "review", "ready"]
    assert [b["to"] for b in m["bars"]] == pytest.approx([60, 30, 10])


def test_a_percent_bar_of_one_series_of_categories_shares_the_whole(site):
    r = {"id": "a", "x": {"type": "category", "label": "state", "scale": "category"}, "unit": "usd",
         "series": [{"name": "c", "xs": ["a", "b"], "values": [1, 3]}]}
    site.mount(config("bar", {"stack": "percent"}), r)
    assert [b["to"] for b in site.model()["bars"]] == pytest.approx([25, 75])


def test_a_page_past_the_requests_limit_is_asked_in_several_on_one_window(site):
    panels = [{"id": f"p{i}", "form": "phase", "queries": [
        {"id": "a", "source": "series", "series": f"y{i}", "x": {"type": "query", "query": "b"}},
        {"id": "b", "source": "series", "series": f"x{i}"}]} for i in range(40)]
    asking = "async (c) => [...(await queryPanels(c, {})).values()].map((v) => v.results.map((r) => r.error || r.id))"
    got = site.page.evaluate(asking, panels)
    assert got == [["a"]] * 40
    assert len(site.asked) == 2 and all(len(b["queries"]) <= 64 for b in site.asked)
    assert site.asked[1]["until"] == META["until"], "the second part reads the same moment"
    for b in site.asked:
        ids = {q["id"] for q in b["queries"]}
        assert all(q["x"]["query"] in ids for q in b["queries"] if "x" in q), "each query is sent with its X"


def test_queries_in_different_units_say_so_and_claim_no_one_unit(site):
    cfg = {**config("line"), "queries": [{"id": "a", "source": "series", "series": "c"}, {"id": "b", "source": "series", "series": "n"}]}
    one = {"id": "a", "times": TIMES[:3], "unit": "usd", "series": [{"name": "c", "values": [1, 2, 3]}]}
    two = {"id": "b", "times": TIMES[:3], "unit": "items", "series": [{"name": "n", "values": [4, 5, 6]}]}
    mount_two(site, cfg, one, two)
    assert "different units (usd, items)" in site.page.locator(".panel-warning").inner_text()
    assert site.page.locator(".panel-unit").inner_text() == ""


def test_a_stat_of_a_sum_does_not_read_an_empty_last_bucket_as_zero(site):
    cfg = {**config("stat"), "queries": [{"id": "a", "source": "items", "kind": "k", "field": "cost", "agg": "sum"}]}
    r = {"id": "a", "times": TIMES[:4], "unit": "usd", "series": [{"name": "c", "values": [2.5, 7.25, 0, 0]}]}
    site.mount(cfg, r)
    assert site.page.locator(".panel-stat-num").inner_text() == "$7.25"
    assert "none since" in site.page.locator(".panel-stat-change").inner_text()
    site.clear()
    level = {**cfg, "id": "q", "queries": [{"id": "a", "source": "series", "series": "x", "agg": "last"}]}
    site.mount(level, r)
    assert site.page.locator(".panel-stat-num").inner_text() == "$0.00", "a level that reads 0 is 0"


def test_a_frequency_query_with_no_output_says_to_choose_it(site):
    fields = {"sources": {"series": {"series": [{"name": "x", "unit": ""}]}}, "aggregations": ["avg"], "transforms": ["none"]}
    site.page.route("**/api/query/fields", lambda r: r.fulfill(json=fields))
    site.page.add_script_tag(url="/static/panel-editor.js")
    site.page.evaluate("""() => { window.ed = openPanelEditor({ id: 'e', title: 'B', form: 'bode', display: {}, queries: [
      { id: 'a', source: 'series', series: 'x', hidden: true },
      { id: 'b', source: 'frequency', input: { source: 'series', series: 'x' }, output: {} }] }, {}); }""")
    site.page.wait_for_timeout(900)
    words = site.page.evaluate("[...document.querySelectorAll('.panel-message')].map((m) => m.textContent).join(' | ')")
    assert "output" in words and "hidden" not in words, words


def test_a_slow_first_answer_says_loading_and_a_failed_one_says_so(site):
    mounting = "(c) => { window.last = chartPanel(c); document.getElementById('page').append(last); last.setState('late', 'waiting 8s'); }"
    site.page.evaluate(mounting, config("line"))
    assert site.page.locator(".panel").get_attribute("data-state") == "loading"
    words = site.page.locator(".panel-message").inner_text()
    assert "Still loading" in words and "Could not" not in words
