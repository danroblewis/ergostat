"""An estimate is proposed only when the record says enough to make one (SPEC §12b; numbers/identify.py): several of
the slowest time constant it acts through, enough points, enough of them independent where the model and the record
disagree, and what it acts through moved several times; else it is held, inconclusive, with how much more record it
needs, and a block's proposal of such a value is held the same way and remembered until the record has grown."""

from __future__ import annotations

import re
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.numbers import estimate as es
from ergostat.numbers import identify as idf
from ergostat.numbers import improve as im
from ergostat.numbers import proposals as pr
from ergostat.store import Project

from .test_numbers import queue_project

PILE = """\
name: pile
parameters:
  rate:
    value: 4
    unit: things/h
    estimate: true
stocks:
  open:
    unit: experiments
    sensor:
      manual: true
  pile:
    unit: things
    sensor:
      manual: true
flows:
  comes:
    to: pile
    driven-by: +stock.open
    equation: rate * MIN(stock.open, 1)
  goes:
    from: pile
    sensor:
      manual: true
"""


def pile_project(tmp_path, open_of, minutes: int = 120, rate: float = 6.0, dead: float = 0.0):
    """While an experiment is open the pile fills at ``rate`` an hour (from ``dead`` hours after it opened, as a
    candidate is built before it is compared), and when it is decided what is there goes at once, read every 30 s:
    image-squeeze's images compared, in small."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(PILE))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    pile, opened, was = 0.0, None, 0
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        o = open_of(i)
        gone = pile if was and not o else 0.0
        pile -= gone
        opened = (opened if opened is not None else t) if o else None
        p.measurements.add("sensor/open.main", float(o), at=t)
        p.measurements.add("sensor/pile.main", pile, at=t)
        p.measurements.add("sensor/goes.main", gone * 3600 / 30, at=t)
        if o and t - opened >= dead * 3600:
            pile += rate * 30 / 3600
        was = o
    return p, {"at": now, "window": minutes * 60.0, "starts": now - minutes * 60}


def test_a_parameter_whose_input_held_one_value_is_held_until_it_moves(tmp_path):
    p, snap = pile_project(tmp_path, lambda i: 1)                       # one experiment open the whole record
    assert pr.make(p, snap) == []
    e = es.load(p, p.model.spec)["rate"]
    assert e["moves"] == 0 and e["refused"].startswith("held, inconclusive: too little record")
    assert "held one value" in e["refused"] and "the next experiment" in e["refused"]


def test_the_same_parameter_with_its_input_moving_is_proposed(tmp_path):
    p, snap = pile_project(tmp_path, lambda i: (i // 20) % 2)          # opened and decided every ten minutes, six times
    [x] = pr.make(p, snap)
    e = es.load(p, p.model.spec)["rate"]
    assert e["moves"] >= idf.MOVES and abs(x["parameters"]["rate"] - 6.0) < 0.3, (e, x["parameters"])


def test_a_short_record_whose_errors_drift_is_held_with_how_much_more_it_needs(tmp_path):
    """Each experiment is built for three minutes before it is compared: the model, which compares while one is open,
    runs ahead of the record in each, and over four experiments its errors drift together: few independent points, and
    a standard error widened for them, never what the points taken one by one would say."""
    p, snap = pile_project(tmp_path, lambda i: 1 if i % 30 < 20 else 0, minutes=45, dead=0.05)
    assert pr.make(p, snap) == []
    e = es.load(p, p.model.spec)["rate"]
    assert e["refused"].startswith("held, inconclusive: too little record") and "drift together" in e["refused"], e
    assert e["n_eff"] < idf.INDEPENDENT and e["se"] > 2 * e["se_naive"]           # widened for the drift
    assert idf.too_short(e)["needs"] > 0 and "more record" in e["refused"]


def test_a_blocks_value_from_too_short_a_record_is_held_inconclusive_and_remembered(tmp_path):
    p, _ = queue_project(tmp_path, k_true=3.0, minutes=20)              # the queue's time constant is 30 minutes
    raw = {"kind": "parameter", "parts": ["parameter.k"], "title": "k is 3",
           "edit": {"file": "ergostat.yaml", "replace": "    value: 2          # what we believe",
                    "with": "    value: 3          # what we believe"},
           "reasons": [{"says": "the replay of queue runs high", "evidence": "fit:stock.queue.um"}]}
    got = im.submit(p, "improver", raw)
    assert got["status"] == "not-proposed" and "too short to identify" in got["why"] and "more record" in got["why"]
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "inconclusive" and x["needs"] > 0
    other = {**raw["edit"], "with": "    value: 3.1        # what we believe"}
    again = im.submit(p, "improver", {**raw, "title": "k is 3.1", "edit": other})
    assert again["status"] == "not-proposed" and "held back" in again["why"]
    held = pr.stored(p)[got["id"]]
    assert held["held_until"] >= (x.get("decided") or x.get("made") or 0) + x["needs"] - 1   # at least what it said it needs


def test_the_words_the_calibration_page_rewrites_are_the_words_the_record_writes():
    """The calibration table (equations.js calNote) rewrites 'Nothing says the value written is wrong' into 'the
    record so far rejects <declared> but cannot yet settle a value' when the value written lies outside the estimate
    ± 3σ. It finds the words by a pattern; reworded here, the page would keep the old claim with nothing failing. So
    the pattern is read from the page and matched against each note that writes those words."""
    js = (Path(__file__).parents[1] / "ergostat/web/static/equations.js").read_text()
    pat = re.search(r"c\.note\.replace\(/(.+?)/,", js).group(1)                   # the page's own pattern
    short = idf.too_short({"value": 0.4, "se": 0.1, "n": 3, "window": 600.0})["says"]
    unmoved = es.judged({"value": 0.4, "se": 0.1, "not_exercised": {"says": "it held one value", "span": 600.0}}, 2.0)
    for note in (short, unmoved):
        assert re.search(pat, note), (pat, note)
