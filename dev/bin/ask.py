"""A research question for the factory's researcher (dev/bin/research.py), from the coordinator; run in the
instance's folder. The answer lands in run/research/<name>.md, its summary on the item (`ergostat item ID`).

    ask.py "How does the queue decide a flake?\""""

from __future__ import annotations

import sys
import time
import uuid

sys.dont_write_bytecode = True
import fac  # noqa: E402


def main(argv: list[str]) -> int:
    question = " ".join(" ".join(argv).split())
    if not question or question.startswith("-"):
        raise SystemExit(__doc__)
    fac.cli(fac.config())
    rid = f"research/{fac.slug(question, 40) or 'question'}-{uuid.uuid4().hex[:6]}"
    fac.add("research.asked", rid, question=question, asked_by="coordinator", asked_at=time.time())
    print(rid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
