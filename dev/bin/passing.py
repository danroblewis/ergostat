"""The tests main passes: `passing.py tests-passing` prints the summed `passed` of the latest landed queue run on main
whose counts cover unit, browser and host (a run where browser was not run by rule is passed over), chosen by main's
first-parent seq, never by time; `passing.py tests-passing-change` prints the latest less the earliest such run within
the last measure.TREND seqs, each sha once, by measure.py's trend helper. Not cx-test-ratio's count (the tests defined
in the code): a skipped, deselected or broken test falls here though still defined. Counts "unknown" on the latest
full run, fewer than two full runs in the window, or no checkout: no value (exit 1), never zero."""

from __future__ import annotations

import sys

import fac
import measure

FULL = {"unit", "browser", "host"}


def full_runs(cfg: dict) -> dict[str, tuple[int, float | None]]:
    """{main_sha: (its seq, its runs' summed passed, None when unknown)} of each landed full run, each sha once."""
    repo = fac.path(cfg, "checkout")
    try:
        fac.git(repo, "rev-parse", "--verify", f"{cfg['git']['base']}^{{commit}}")
    except (RuntimeError, OSError) as e:
        raise SystemExit(f"tests-passing: no value (no checkout of main: {e})") from None
    out: dict[str, tuple[int, float | None]] = {}
    for g in fac.items("gap"):
        sha, ran = g["fields"].get("main_sha"), [r for r in g["fields"].get("queue_runs") or [] if r.get("landed")]
        if not sha or not ran or not FULL <= set(ran[-1].get("suites") or ()):    # (browser not run: passed over)
            continue
        passed = (ran[-1]["counts"] if isinstance(ran[-1].get("counts"), dict) else {}).get("passed")
        try:
            seq = int(fac.git(repo, "rev-list", "--count", "--first-parent", str(sha)))
        except (RuntimeError, ValueError):
            continue                                                              # (a sha the checkout lacks: not main's)
        out[str(sha)] = (seq, float(passed) if type(passed) is int else None)
    return out


if __name__ == "__main__":
    name, cfg = sys.argv[1], fac.config()
    if name not in ("tests-passing", "tests-passing-change"):
        raise SystemExit(f"passing.py: no measure {name!r}")
    runs = full_runs(cfg)
    window = measure.by_seq(cfg, runs)
    if not window or window[0][1] is None:
        raise SystemExit(f"{name}: no value (the latest full run on main has counts unknown, or there is none)")
    known = {sha: v for sha, v in runs.items() if v[1] is not None}
    print(window[0][1] if name == "tests-passing" else measure.code_change(name, known))
