"""A research question for the factory's researcher (dev/bin/research.py), from the coordinator; run in the
instance's folder. The answer lands in run/research/<name>.md, its summary on the item (`ergostat item ID`). With
--gap, the question is that gap's: once answered, its report is in the gap's implementor's, reviewer's and planner's
briefs (knowledge.py, "Research for this gap"); a gap the record does not hold is refused.

    ask.py [--gap GAP] "How does the queue decide a flake?\""""

from __future__ import annotations

import argparse
import sys
import time
import uuid

sys.dont_write_bytecode = True
import fac  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ask.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("words", nargs="*", help="the question")
    ap.add_argument("--gap", default="", help="the gap it is for, by branch or id")
    args = ap.parse_args(argv)
    question = " ".join(" ".join(args.words).split())
    if not question:
        raise SystemExit(__doc__)
    fac.cli(fac.config())
    gap = args.gap if not args.gap or args.gap.startswith("gap/") else f"gap/{args.gap}"
    if gap and gap not in {g["id"] for g in fac.items("gap")}:
        raise SystemExit(f"no such gap: {gap}")
    rid = f"research/{fac.slug(question, 40) or 'question'}-{uuid.uuid4().hex[:6]}"
    fac.add("research.asked", rid, question=question, asked_by="coordinator", asked_at=time.time(),
            **({"gap": gap} if gap else {}))
    print(rid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
