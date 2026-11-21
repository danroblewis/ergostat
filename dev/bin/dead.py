"""dead letters: every few minutes, each gap that became a dead letter (its runs failed past their attempts in a way
its block did not catch: killed, lost) is parked with where it stopped, from its lease's history, so no gap is left
stuck. The coordinator takes it up again with a new definition or `ergostat lease ITEM --redrive`. A gap whose last
failing tests all fail on main too (`main_broken_tests`, onmain.py) is said to have died on main's failures, not its
own."""

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
        review.park(cfg, gap, "Its runs failed past their attempts (a dead letter):\n" + "\n".join(whys) +
                    on_main(gap["fields"]), "dead-letters", where="dead-letter", kind="kill-rule")
    return 0


def on_main(f: dict) -> str:
    """What to add when the gap's last failing tests are all main-broken: main's failures, not the gap's."""
    failed = set((f.get("suites_fast") or {}).get("tests") or [])
    broken = set(f.get("main_broken_tests") or [])
    if not failed or not failed <= broken:
        return ""
    return (f"\n\nIts runs died only on tests that fail on main too (main-broken: {', '.join(sorted(failed))}, on main "
            f"{str(f.get('built_main') or '')[:12]}): main's failures, not the gap's. Fix them on main, then redrive it.")


if __name__ == "__main__":
    sys.exit(main())
