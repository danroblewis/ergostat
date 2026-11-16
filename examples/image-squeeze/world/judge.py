"""How good a compressed image is, judged against its original: SSIM (structural similarity,
1.0 is identical), on both images flattened onto white (transparency counts: a logo whose
background turned black is a bad logo), in grayscale, at full size (so an image made smaller
shows as detail lost)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def flatten(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, img).convert("L")
    return img.convert("L")


def ssim(a: Image.Image, b: Image.Image) -> float:
    a, b = flatten(a), flatten(b)
    if b.size != a.size:                                     # a smaller output is judged at the original's size
        b = b.resize(a.size, Image.Resampling.BICUBIC)
    scale = min(1.0, 1600 / max(a.size))
    if scale < 1:
        size = (max(8, int(a.size[0] * scale)), max(8, int(a.size[1] * scale)))
        a, b = a.resize(size, Image.Resampling.BOX), b.resize(size, Image.Resampling.BOX)
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    k = 8                                                    # 8×8 windows
    h, w = (x.shape[0] // k) * k, (x.shape[1] // k) * k
    xw = x[:h, :w].reshape(h // k, k, w // k, k).swapaxes(1, 2).reshape(-1, k * k)
    yw = y[:h, :w].reshape(h // k, k, w // k, k).swapaxes(1, 2).reshape(-1, k * k)
    mx, my = xw.mean(1), yw.mean(1)
    vx, vy = xw.var(1), yw.var(1)
    cov = ((xw - mx[:, None]) * (yw - my[:, None])).mean(1)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mx * my + c1) * (2 * cov + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return float(s.mean())


def decode(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img
