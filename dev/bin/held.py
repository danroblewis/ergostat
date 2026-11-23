"""The quarantine as held on main as pushed (tests/quarantine.txt at the checkout's <remote>/<base>, never fetched here),
cross-checked with the flake items marked quarantined. `held.py NAME` prints one reading:

  quarantined             the tests listed
  quarantine-oldest-days  days (UTC) since the oldest `when` listed

A list that cannot be read (no ref, no file, a line not `test | who | when | why`) or a `when` that is not a date
(YYYY-MM-DD) gives no value (exit 1), never 0; so does quarantine-oldest-days with nothing listed. A listed test with
no flake item marked quarantined, or the reverse, is named on stderr (a record that cannot be read: said there too)."""

from __future__ import annotations

import datetime
import sys

import fac


def listed(text: str) -> dict[str, datetime.date]:
    """Each test listed and its `when`; ValueError on a line or date that cannot be read."""
    out = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            cols = [c.strip() for c in line.split("|")]
            if len(cols) < 4 or not cols[0]:
                raise ValueError(f"not `test | who | when | why`: {line!r}")
            out[cols[0]] = datetime.date.fromisoformat(cols[2])
    return out


def crosscheck(tests) -> None:
    try:
        marked = {it["fields"].get("test") for it in fac.items("flake") if it["fields"].get("quarantined")}
    except Exception as e:  # noqa: BLE001 - the count is the list's; the record unread is said, not a reading
        print(f"held: the flake items cannot be read ({e!r}), the list not cross-checked", file=sys.stderr)
        return
    for t in sorted(set(tests) - marked):
        print(f"held: listed, no flake item marked quarantined: {t}", file=sys.stderr)
    for t in sorted(marked - set(tests)):
        print(f"held: a flake item marked quarantined, not listed: {t}", file=sys.stderr)


def reading(name: str, cfg: dict, today: datetime.date) -> int:
    g = cfg.get("git", {})
    ref = f"refs/remotes/{g.get('remote', 'origin')}/{g.get('base', 'main')}"
    try:
        held = listed(fac.git(fac.path(cfg, "checkout"), "show", f"{ref}:tests/quarantine.txt"))
    except (RuntimeError, ValueError, OSError) as e:
        raise SystemExit(f"{name}: no value (the quarantine on {ref} cannot be read: {e})") from None
    crosscheck(held)
    if name == "quarantined":
        return len(held)
    if not held:
        raise SystemExit(f"{name}: no value (nothing quarantined on {ref})")
    return (today - min(held.values())).days


if __name__ == "__main__":
    if sys.argv[1:] not in (["quarantined"], ["quarantine-oldest-days"]):
        raise SystemExit("usage: held.py quarantined | quarantine-oldest-days")
    print(reading(sys.argv[1], fac.config(), datetime.datetime.now(datetime.UTC).date()))
