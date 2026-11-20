"""dead letters: every few minutes, each gap that became a dead letter (its runs failed past their attempts in a way
its block did not catch: killed, lost) is parked with where it stopped, from its lease's history, so no gap is left
stuck. The coordinator takes it up again with a new definition or `ergostat lease ITEM --redrive`."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import fac  # noqa: E402
import review  # noqa: E402


def main() -> int:
    cfg = fac.config()
    for gap in fac.items("gap", "dead"):
        hist = (gap["fields"].get("lease") or {}).get("history") or []
        whys = [f"- attempt {h.get('fence')}: {h.get('how')} {h.get('why') or ''}".rstrip() for h in hist[-4:]]
        review.park(cfg, gap, "Its runs failed past their attempts (a dead letter):\n" + "\n".join(whys),
                    "dead-letters", where="dead-letter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
