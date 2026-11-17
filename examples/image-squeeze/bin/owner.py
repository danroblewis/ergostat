"""The owner's decisions about squeeze, for the demo: made up for it (synthetic), proposed and confirmed once, as the
owner would on the Items page (Items -> ergostat.decision -> Confirm). The intent judge (intent.yaml) holds every
hypothesis that passes its tests to them before the rollout may keep it.

Two of the stand-in researcher's ideas go against them, and pass their tests: "Store photos as WebP" (squeeze writes
JPEG and PNG only) and "Downscale anything wider than 1200 pixels" (an image keeps its size). A third, "Strip
metadata", goes against the third decision in words the stand-in judge does not match (it says "strip", the decision
"stripping"): an AI judge (INTENT_MODEL=haiku) catches it, the free one does not."""

import json
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DONE = ROOT / "run" / "owner-decided"

DECISIONS = [
    {"text": "squeeze writes JPEG and PNG only", "scope": "formats",
     "reason": "a third of customers' viewers cannot open anything else",
     "rejected": "WebP output: customers' older viewers cannot open it",
     "words": "keep it to JPEG and PNG, whatever saves bytes; I'm not having support calls about WebP again"},
    {"text": "an image keeps its pixel size: squeeze never resizes what customers send", "scope": "formats",
     "reason": "customers lay their pages out by the size they uploaded",
     "rejected": "resize or downscale large images: their layouts break",
     "words": "don't touch the dimensions, ever; smaller files, same size"},
    {"text": "camera metadata is the customer's: squeeze keeps it", "scope": "formats",
     "reason": "photographers rely on the copyright and colour profile fields",
     "rejected": "stripping metadata to save bytes",
     "words": "metadata stays; we are not a privacy scrubber"},
]


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def sh(*args: str) -> dict:
    r = subprocess.run([*ergostat(), *args, "--json"], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main() -> None:
    import sys
    sys.stdin.read()
    if DONE.exists():
        print(json.dumps({"out": "flow.decided", "moved": 0}))
        return
    n = 0
    for d in DECISIONS:
        got = sh("decisions", "propose", d["text"], "--scope", d["scope"], "--reason", d["reason"], "--rejected",
                 d["rejected"], "--words", d["words"], "--as", "owner")
        if got.get("state", "proposed") == "proposed":
            sh("decisions", "confirm", got["item"], "--reason", "the owner's (synthetic, for the demo)")
        n += 1
    DONE.parent.mkdir(exist_ok=True)
    DONE.write_text("\n".join(d["text"] for d in DECISIONS) + "\n")
    print(json.dumps({"out": "flow.decided", "moved": n}))


if __name__ == "__main__":
    main()
