"""measure.py's env-parks (dev/records/a-definition-s-done-items-the.md): the parks caused by done items the
implementor's container cannot do, counted beside first-pass-yield, which leaves out the failures they caused."""

from __future__ import annotations

import time

import pytest

from tests.test_factory_knowledge import Instance, size_measure

pytestmark = pytest.mark.slow
DAY = 86400
NEEDS = [{"item": 2, "needs": "owner", "why": "input files not in the repository"}]


def review(f: Instance, gid: str, verdict: str, at: float, rnd: int = 1, **more) -> None:
    rid = f"review/{gid[4:]}-{rnd}"
    f.fold([{"event": "review.written", "item": rid, "data": {"gap": gid, "round": rnd, "written_at": at,
                                                              "verdict": verdict, **more}}], None)


def test_env_parks_are_counted_and_left_out_of_first_pass_failures_they_caused(tmp_path):
    f, now = Instance(tmp_path), time.time()
    gaps = {"gap/env-a": NEEDS, "gap/plain-b": None, "gap/plain-c": None, "gap/env-f": NEEDS}
    for gid, needs in gaps.items():
        f.fold([{"event": "gap.requested", "item": gid, "data": {"title": gid, "env_needs": needs}}], None)
    review(f, "gap/env-a", "park", now - DAY, parked_for="needs")       # an env-park: not a first-pass failure
    review(f, "gap/plain-b", "merge", now - DAY)
    review(f, "gap/plain-c", "park", now - DAY, parked_for="needs")     # no env items: the implementor's failure
    review(f, "gap/env-f", "fix", now - DAY)                            # env items, but sent back: still a failure
    review(f, "gap/env-f", "park", now - DAY, rnd=2, parked_for="defect")            # a defect: not an env-park
    for gid, at in (("gap/env-d", now - DAY), ("gap/env-old", now - 20 * DAY)):    # parked at plan time
        f.fold([{"event": "gap.parked", "item": gid, "data": {"parked_for": "needs", "parked_by": "plan-env",
                                                              "env_needs": NEEDS, "env_parked_at": at}}], None)
    # (env-d readied and later parked by a review for a defect: its plan-time park still counts)
    f.fold([{"event": "gap.parked", "item": "gap/env-d", "data": {"parked_for": "defect", "parked_at": now}}], None)
    r = size_measure(f, "env-parks")
    assert r.returncode == 0 and r.stdout.strip() == "2.0", r.stderr
    r = size_measure(f, "first-pass-yield")
    assert r.returncode == 0 and r.stdout.strip() == "0.333", r.stderr
    got = f.py("import manager\nprint(json.dumps(manager.velocity(manager.fac.config()), default=str))")
    assert got["env-parks"] == 2.0 and got["first-pass-yield"] == 0.333
