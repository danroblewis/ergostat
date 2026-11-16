"""The stand-in researcher's notebook: hypotheses about what would make squeeze's images smaller
(or better) without breaking anything, each with the code the stand-in developer writes for it.

Each change wraps one stage of squeeze (prepare or choose), so kept changes stack. Some ideas are
good, some do nothing, some trade one thing for another, one is broken: the experiments decide.
With FACTORY_AI=claude, a Claude Code session proposes its own ideas and writes its own code."""

IDEAS = [
    {"key": "transparent-on-white", "title": "Put transparent images on white before JPEG",
     "idea": "JPEG has no transparency: converting a logo to RGB keeps whatever colour sits under its transparent "
             "pixels (black). Flatten onto white first.",
     "code": '''
_prepare_before_white = prepare
def prepare(image, settings):
    if image.mode in ("RGBA", "LA", "P"):
        from PIL import Image
        rgba = image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    return _prepare_before_white(image, settings)
'''},
    {"key": "jpeg-optimize", "title": "Turn on the JPEG encoder's optimised tables and progressive scan",
     "idea": "Optimised Huffman tables and progressive encoding cost a little time and save a few percent, losslessly.",
     "code": '''
_choose_before_optimize = choose
def choose(image, settings):
    image, fmt, options = _choose_before_optimize(image, settings)
    if fmt == "JPEG":
        options = {**options, "optimize": True, "progressive": True}
    return image, fmt, options
'''},
    {"key": "png-for-flat", "title": "Store flat images (few colours) as palette PNG",
     "idea": "Screenshots, line art and logos have a few hundred colours at most; a palette PNG stores them exactly, "
             "and smaller than JPEG smears them.",
     "code": '''
_choose_before_png = choose
def choose(image, settings):
    colours = image.getcolors(256)
    if colours is not None:
        return image.convert("P", palette=1, colors=256), "PNG", {"optimize": True}
    return _choose_before_png(image, settings)
'''},
    {"key": "keep-gray", "title": "Keep grayscale images grayscale",
     "idea": "A grayscale photo converted to RGB stores the same values three times; JPEG of one channel is smaller.",
     "code": '''
_prepare_before_gray = prepare
def prepare(image, settings):
    if image.mode == "L":
        return image
    return _prepare_before_gray(image, settings)
'''},
    {"key": "webp-photos", "title": "Store photos as WebP",
     "idea": "WebP's lossy mode is typically 25-35% smaller than JPEG at the same quality.",
     "code": '''
_choose_before_webp = choose
def choose(image, settings):
    image, fmt, options = _choose_before_webp(image, settings)
    if fmt == "JPEG":
        return image, "WEBP", {"quality": options.get("quality", 80), "method": 4}
    return image, fmt, options
'''},
    {"key": "strip-nothing", "title": "Strip metadata",
     "idea": "Camera metadata can be tens of kilobytes; drop it.",
     "code": '''
_prepare_before_strip = prepare
def prepare(image, settings):
    image.info.clear()
    return _prepare_before_strip(image, settings)
'''},
    {"key": "shrink-big", "title": "Downscale anything wider than 1200 pixels",
     "idea": "Big photos are rarely shown at full size; shrink them to 1200 pixels wide.",
     "code": '''
_prepare_before_shrink = prepare
def prepare(image, settings):
    if max(image.size) > 1200:
        k = 1200 / max(image.size)
        image = image.resize((int(image.size[0] * k), int(image.size[1] * k)))
    return _prepare_before_shrink(image, settings)
'''},
    {"key": "denoise-photos", "title": "Soften photo noise before encoding",
     "idea": "Sensor noise is expensive to encode and nobody wants it; a slight blur saves bytes.",
     "code": '''
_prepare_before_denoise = prepare
def prepare(image, settings):
    image = _prepare_before_denoise(image, settings)
    if image.getcolors(256) is None:
        from PIL import ImageFilter
        image = image.filter(ImageFilter.GaussianBlur(0.8))
    return image
'''},
    {"key": "fit-quality-per-image", "title": "Search each image's quality for the smallest that looks right",
     "idea": "One quality for every image is a compromise; search per image (encode a few times, keep the smallest "
             "within a quality budget).",
     "code": '''
_choose_before_search = choose
def choose(image, settings):
    image, fmt, options = _choose_before_search(image, settings)
    if fmt not in ("JPEG", "WEBP"):
        return image, fmt, options
    import io
    from PIL import Image, ImageChops, ImageStat
    best = options
    for q in (40, 55, 70):
        trial = dict(options, quality=q)
        buf = io.BytesIO()
        image.save(buf, fmt, **trial)
        back = Image.open(io.BytesIO(buf.getvalue())).convert(image.mode)
        diff = ImageStat.Stat(ImageChops.difference(image, back)).mean
        if sum(diff) / len(diff) < 2.0:
            best = trial
            break
    return image, fmt, best
'''},
    {"key": "fast-palette", "title": "Quantise every image to 256 colours",
     "idea": "A palette is smaller than full colour: quantise everything.",
     "code": '''
_choose_before_quantise = choose
def choose(image, settings):
    return image.quantize(256), "PNG", {"optimize": True}
'''},
    {"key": "alpha-mask", "title": "Keep a logo's transparency as a separate mask",
     "idea": "Store the alpha channel apart so logos stay transparent.",
     "code": '''
_prepare_before_mask = prepare
def prepare(image, settings):
    mask = image.getchannel("A")
    return _prepare_before_mask(image, settings)
'''},
]
