"""squeeze: makes images small enough to serve, and still good to look at.

compress(image, settings) -> (data, format). The service calls it for every image customers send;
settings["quality"] (1..100) is the encoder quality the tuner sets as the mix of images changes.

It works in stages, each a function the pipeline looks up when it runs:

    prepare(image, settings) -> image                    what to do to the picture first
    choose(image, settings) -> image, format, options    how to store it

Everything here is policy, and the factory improves it one experiment at a time.
"""

import io


def prepare(image, settings):
    return image.convert("RGB")


def choose(image, settings):
    return image, "JPEG", {"quality": int(settings.get("quality", 80))}


def compress(image, settings):
    image = prepare(image, settings)
    image, fmt, options = choose(image, settings)
    out = io.BytesIO()
    image.save(out, fmt, **options)
    return out.getvalue(), fmt.lower()
