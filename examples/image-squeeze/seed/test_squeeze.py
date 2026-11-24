"""squeeze's own tests: python3 test_squeeze.py (Pillow is all they need)."""

import io

from PIL import Image, ImageDraw

import squeeze


def sample(mode="RGB", size=(64, 48)):
    img = Image.new(mode, size, (200, 120, 40) if mode == "RGB" else 128)
    if mode == "RGB":
        ImageDraw.Draw(img).rectangle([8, 8, 40, 30], fill=(20, 60, 200))
    return img


def opens(data):
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def test_it_makes_something_that_opens():
    data, fmt = squeeze.compress(sample(), {"quality": 80})
    assert isinstance(data, bytes) and data and fmt
    assert opens(data).size == (64, 48)


def test_lower_quality_is_not_bigger():
    a, _ = squeeze.compress(sample(size=(200, 150)), {"quality": 90})
    b, _ = squeeze.compress(sample(size=(200, 150)), {"quality": 30})
    assert len(b) <= len(a)


def test_grayscale_and_transparent_images_compress():
    for mode, size in (("L", (64, 48)), ("RGBA", (64, 64))):
        data, _ = squeeze.compress(Image.new(mode, size), {"quality": 80})
        assert opens(data).size == size


if __name__ == "__main__":
    import time
    began, passed, failed = time.monotonic(), 0, 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except Exception as e:                      # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    # the summary pytest ends with, which use: regressions reads (python -m ergostat.regressions counts)
    print(f"{passed} passed, {failed} failed in {time.monotonic() - began:.2f}s")
    raise SystemExit(1 if failed else 0)
