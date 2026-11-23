"""Welch's estimate against systems whose response is known exactly (ergostat/query/frequency.py)."""

from __future__ import annotations

import cmath
import math
import random

import pytest

from ergostat.query import frequency as fr


def noise(n, seed=1):
    r = random.Random(seed)
    return [r.gauss(0, 1) for _ in range(n)]


def near(got, hz):
    return min(range(len(got["frequency"]["hz"])), key=lambda i: abs(got["frequency"]["hz"][i] - hz))


def test_the_transform_matches_the_definition_for_every_factor():
    for n in (8, 9, 15, 25, 30, 60):
        a = [complex(x, y) for x, y in zip(noise(n, 2), noise(n, 3), strict=True)]
        want = [sum(a[t] * cmath.exp(-2j * math.pi * k * t / n) for t in range(n)) for k in range(n)]
        assert [abs(p - q) < 1e-9 for p, q in zip(fr.fft(a), want, strict=True)] == [True] * n


def test_a_pure_gain():
    x = noise(1024)
    f = fr.estimate(x, [2.5 * v for v in x], 1.0, 8)["frequency"]
    assert all(m == pytest.approx(20 * math.log10(2.5), abs=1e-6) for m in f["magnitude_db"])
    assert all(abs(p) < 1e-6 for p in f["phase_deg"]) and min(f["coherence"]) > 0.999999


def test_a_negative_gain_is_half_a_turn():
    x = noise(512)
    f = fr.estimate(x, [-v for v in x], 1.0, 4)["frequency"]
    assert all(abs(abs(p) - 180) < 1e-6 for p in f["phase_deg"])


def test_a_pure_delay_has_unit_gain_and_a_phase_falling_in_a_straight_line():
    d, dt = 3, 10.0
    x = noise(2048 + d)
    got = fr.estimate(x[d:], x[:-d], dt, 8)
    f = got["frequency"]
    for hz, m, ph in zip(f["hz"], f["magnitude_db"], f["phase_deg"], strict=True):
        if hz < 0.03:
            assert m == pytest.approx(0.0, abs=0.35)
            assert ph == pytest.approx(-360 * hz * d * dt, abs=4.0)
    assert min(f["phase_deg"]) < -360                 # unwrapped: past a whole turn (3 samples reach -540 at Nyquist)


def test_a_first_order_lag_at_its_corner_is_minus_three_db_and_minus_45_degrees():
    dt = 1.0
    tau = 1024 / (2 * math.pi * 8)                    # the corner falls exactly on the 8th of 1024 frequencies
    a = math.exp(-dt / tau)
    x = noise(20_000, 5)
    y, s = [], 0.0
    for v in x:
        s = a * s + (1 - a) * v
        y.append(s)
    got = fr.estimate(x[1000:], y[1000:], dt, 16)
    i = near(got, 1 / (2 * math.pi * tau))
    hz = got["frequency"]["hz"][i]
    want = (1 - a) / (1 - a * cmath.exp(-2j * math.pi * hz * dt))
    assert got["frequency"]["magnitude_db"][i] == pytest.approx(20 * math.log10(abs(want)), abs=0.5)
    assert got["frequency"]["phase_deg"][i] == pytest.approx(math.degrees(cmath.phase(want)), abs=4.0)
    assert abs(hz * 2 * math.pi * tau - 1) < 1e-9     # the bin is at the corner, so these are the textbook values
    assert got["frequency"]["magnitude_db"][i] == pytest.approx(-3.01, abs=0.5)
    assert got["frequency"]["phase_deg"][i] == pytest.approx(-45.0, abs=4.0)


def test_a_known_sinusoid_is_measured_at_its_frequency():
    n, dt, k = 1024, 2.0, 32
    hz = k / (256 * dt)
    x = [math.sin(2 * math.pi * hz * i * dt) for i in range(n)]
    y = [0.5 * math.sin(2 * math.pi * hz * i * dt - math.pi / 3) for i in range(n)]
    got = fr.estimate(x, y, dt, 7)
    i = near(got, hz)
    assert got["frequency"]["hz"][i] == pytest.approx(hz)
    assert got["frequency"]["magnitude_db"][i] == pytest.approx(20 * math.log10(0.5), abs=1e-3)
    assert got["frequency"]["phase_deg"][i] == pytest.approx(-60.0, abs=1e-3)
    assert len(got["frequency"]["hz"]) < 16 and "no power" in got["note"]   # the rest was never excited


def test_coherence_is_near_one_for_a_linear_system_and_low_for_unrelated_noise():
    x = noise(4096, 7)
    e = noise(4096, 8)
    linear = fr.estimate(x, [2 * a + 0.05 * b for a, b in zip(x, e, strict=True)], 1.0, 16)
    assert sum(linear["frequency"]["coherence"]) / len(linear["frequency"]["coherence"]) > 0.99
    apart = fr.estimate(x, e, 1.0, 16)
    c = apart["frequency"]["coherence"]
    assert sum(c) / len(c) < 0.15
    assert sum(v > apart["coherence_floor"] for v in c) / len(c) < 0.12    # about the 5% the floor promises


def test_a_gap_is_never_bridged():
    x = noise(1200, 9)
    y = [3 * v for v in x]
    gappy_x = x[:500] + [None] * 200 + x[700:]
    got = fr.estimate(gappy_x, y, 1.0, 4)
    assert got["samples"] == 1000
    assert all(m == pytest.approx(20 * math.log10(3), abs=1e-6) for m in got["frequency"]["magnitude_db"])
    assert got["segment_samples"] <= 500


def test_uneven_readings_resample_to_the_slower_signals_spacing():
    r = random.Random(4)
    n = 4000
    slow = [math.sin(2 * math.pi * i / 400) + 0.3 * math.sin(2 * math.pi * i / 170) for i in range(n)]
    xs: list = [None] * n
    i = 0
    while i < n:
        xs[i] = slow[i]
        i += r.choice((3, 4, 5))
    ux, uy, dt = fr.resample(xs, [2 * v for v in slow], 1.0)
    assert dt == 4.0 and len(ux) == len(uy) == n // 4
    got = fr.estimate(ux, uy, dt, 4)
    i = near(got, 1 / 400)
    assert got["frequency"]["magnitude_db"][i] == pytest.approx(20 * math.log10(2), abs=0.15)
    assert abs(got["frequency"]["phase_deg"][i]) < 3


def test_readings_further_apart_than_the_gap_limit_stay_a_gap():
    v = [float(i % 7) for i in range(100)]
    v[40:60] = [None] * 20
    filled = fr._filled(v, 3)
    assert filled[39] is not None and all(x is None for x in filled[40:60]) and filled[60] is not None
    assert fr._filled([1.0, None, None, 4.0], 3) == [1.0, 2.0, 3.0, 4.0]


@pytest.mark.parametrize("xs,ys,word", [
    ([5.0] * 200, noise(200), "input does not vary"),
    ([3.0 + 1e-13 * (i % 2) for i in range(200)], noise(200), "input does not vary"),
    (noise(200), [1.0] * 200, "output does not vary"),
    (noise(20), noise(20), "too few samples"),
    ([v if i % 10 else None for i, v in enumerate(noise(200))], noise(200), "too few samples"),
])
def test_what_cannot_be_estimated_is_refused_in_words(xs, ys, word):
    with pytest.raises(fr.Refused, match=word):
        fr.estimate(xs, ys, 1.0, 4)


def test_the_estimate_is_bounded():
    got = fr.estimate(noise(fr.MOST_SAMPLES), noise(fr.MOST_SAMPLES, 2), 1.0, 2)
    assert got["segment_samples"] <= fr.MOST_LENGTH and len(got["frequency"]["hz"]) <= fr.MOST_LENGTH // 2


def test_the_coherence_floor_follows_the_number_of_averages():
    assert fr.floor(1) == 1.0 and fr.floor(2) > 0.95
    assert fr.floor(16) == pytest.approx(1 - 0.05 ** (1 / (16 * 9 / 11 - 1)))
    assert fr.floor(64) < fr.floor(16) < fr.floor(4)
