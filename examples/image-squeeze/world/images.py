"""The images customers send: drawn here, procedurally, so the example needs no downloads.

Six kinds, each with what makes it hard to compress well: photos (smooth with fine noise), big
photos (four times the pixels), grayscale photos (one channel stored as three is waste),
screenshots (flat colour and sharp text edges, which JPEG smears), line art (two colours), and
logos with a transparent background (which JPEG cannot hold at all).

The mix shifts over time, phase by phase (photo-heavy, then screenshot-heavy, then logos ...): the
disturbance the product's loops must ride through."""

from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

KINDS = ("photo", "big-photo", "gray-photo", "screenshot", "lineart", "logo")
PHASES = [  # the mix, one phase after another, each PHASE_SECONDS long
    {"photo": 6, "big-photo": 1, "gray-photo": 1, "screenshot": 1, "lineart": 1, "logo": 0},
    {"photo": 2, "big-photo": 0, "gray-photo": 1, "screenshot": 6, "lineart": 2, "logo": 1},
    {"photo": 3, "big-photo": 1, "gray-photo": 2, "screenshot": 1, "lineart": 1, "logo": 4},
    {"photo": 3, "big-photo": 2, "gray-photo": 1, "screenshot": 3, "lineart": 2, "logo": 2},
]
PHASE_SECONDS = 240
FLAT = ("screenshot", "lineart", "logo")


def mix(t: float) -> dict[str, int]:
    return PHASES[int(t // PHASE_SECONDS) % len(PHASES)]


def flat_share(t: float) -> float:
    m = mix(t)
    return sum(m[k] for k in FLAT) / sum(m.values())


def photo(rng: random.Random, w: int = 640, h: int = 480, gray: bool = False) -> Image.Image:
    nr = np.random.default_rng(rng.randrange(1 << 30))
    y, x = np.mgrid[0:h, 0:w] / max(w, h)
    base = np.stack([np.sin(x * nr.uniform(2, 6) + nr.uniform(0, 6)) * 60 + 128 + nr.uniform(-40, 40) for _ in range(3)], -1)
    for _ in range(rng.randint(4, 9)):                       # soft shapes: things in the picture
        cx, cy, r = nr.uniform(0, 1), nr.uniform(0, 0.75), nr.uniform(0.05, 0.3)
        blob = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r)))[..., None]
        base = base * (1 - blob) + blob * nr.uniform(20, 235, 3)
    base += nr.normal(0, nr.uniform(3, 9), base.shape)       # sensor noise, which costs bytes
    img = Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB").filter(ImageFilter.GaussianBlur(0.6))
    return img.convert("L") if gray else img


def screenshot(rng: random.Random, w: int = 640, h: int = 480) -> Image.Image:
    bg = rng.choice([(255, 255, 255), (246, 246, 248), (32, 34, 40)])
    ink = (30, 30, 30) if sum(bg) > 300 else (220, 220, 220)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 36], fill=rng.choice([(47, 111, 222), (40, 40, 48), (220, 60, 60)]))
    for _ in range(rng.randint(2, 5)):                       # panels and buttons
        x0, y0 = rng.randrange(0, w - 120), rng.randrange(44, h - 60)
        d.rectangle([x0, y0, x0 + rng.randrange(60, 220), y0 + rng.randrange(24, 90)],
                    fill=rng.choice([(230, 236, 250), (250, 240, 220), (60, 64, 72), (47, 111, 222)]))
    y = 50
    while y < h - 12:                                        # lines of "text": short dark strokes, sharp edged
        x = 16
        while x < w - 40 and rng.random() < 0.93:
            word = rng.randrange(10, 60)
            d.rectangle([x, y, x + word, y + 7], fill=ink)
            x += word + 7
        y += rng.choice([14, 16, 22])
    return img


def lineart(rng: random.Random, w: int = 640, h: int = 480) -> Image.Image:
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(12, 30)):
        if rng.random() < 0.5:
            d.line([rng.randrange(w), rng.randrange(h), rng.randrange(w), rng.randrange(h)], fill=(0, 0, 0), width=rng.choice([1, 2, 3]))
        else:
            x, y, r = rng.randrange(w), rng.randrange(h), rng.randrange(8, 90)
            d.ellipse([x - r, y - r, x + r, y + r], outline=(0, 0, 0), width=2)
    return img


def logo(rng: random.Random, w: int = 480, h: int = 480) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))            # transparent: what is behind it shows through
    d = ImageDraw.Draw(img)
    colours = [(rng.randrange(256), rng.randrange(256), rng.randrange(256), 255) for _ in range(3)]
    cx, cy = w // 2, h // 2
    d.ellipse([cx - 160, cy - 160, cx + 160, cy + 160], fill=colours[0])
    n = rng.randint(3, 8)
    pts = [(cx + 120 * math.cos(2 * math.pi * k / n), cy + 120 * math.sin(2 * math.pi * k / n)) for k in range(n)]
    d.polygon(pts, fill=colours[1])
    d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=colours[2])
    return img


def make(kind: str, seed: int) -> Image.Image:
    rng = random.Random(f"{kind}-{seed}")
    if kind == "photo":
        return photo(rng)
    if kind == "big-photo":
        return photo(rng, 1600, 1200)
    if kind == "gray-photo":
        return photo(rng, gray=True)
    if kind == "screenshot":
        return screenshot(rng)
    if kind == "lineart":
        return lineart(rng)
    return logo(rng)


def batch(t: float, n: int, seed: int) -> list[tuple[str, int]]:
    """Which images arrive in this tick: (kind, seed) pairs, drawn from the mix at time t."""
    rng = random.Random(seed)
    m = mix(t)
    kinds = [k for k in KINDS if m[k]]
    return [(rng.choices(kinds, [m[k] for k in kinds])[0], rng.randrange(1 << 30)) for _ in range(n)]
