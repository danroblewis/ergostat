#!/usr/bin/env python3
"""A simulated AWS EC2 event stream, shaped like what EventBridge delivers, with the mess real streams have; usable as
an ergostat collector.

Three ways to run it:

  batch   the whole stream at once, as files: events.jsonl (as delivered) and expected.json (each instance's true
          final state, to score a projection against).
              python3 ec2_stream.py batch --instances 20 --days 3

  tick    one step of a fleet that lives on between runs (its state in --state): the simulation moves on from the
          last tick to now (--speed times faster than the clock), prints the events delivered meanwhile, one ergostat
          event line each, and exits. For an ergostat program block on a timer:
              blocks:
                ec2-feed:
                  type: program
                  run: python3 ec2_stream.py tick --state .ec2-sim.json --speed 60
                  every: 30s

  live    the same fleet, ticking on its own every --every seconds, forever, printing each tick's lines to standard
          output as they are delivered: a long-running program (an ergostat daemon), its output ergostat's to read.
              python3 ec2_stream.py live --speed 60 --every 10

Each line is a light wrapper that says only where the event came from; AWS's event is kept whole in data:

  {"event": "aws.eventbridge", "data": {"id": "...", "detail-type": "EC2 Instance State-change Notification",
   "source": "aws.ec2", "account": "111111111111", "region": "us-east-1", "time": "2026-11-27T09:00:41Z",
   "detail": {"instance-id": "i-0abc...", "state": "running"}}}

What it simulates: a fleet in two accounts and two regions, kept near --instances live instances. Instances launch
(RunInstances, sometimes several in one call), get tagged (CreateTags; some never are), reboot (an API call; the state
stays running), stop and start again (sometimes resized while stopped: ModifyInstanceAttribute) and are terminated;
a few die in pending. Every transition is an "EC2 Instance State-change Notification", every API call an "AWS API
Call via CloudTrail".

The mess, on purpose:
- delivery is not in event-time order: each event is delayed 0-90 s, a few up to 15 min (tick and live hold a late
  event over to a later tick);
- about 2% of events are delivered twice (the same AWS "id");
- about 3% of CloudTrail events lack userIdentity.arn;
- one instance id exists in both accounts, so the id alone is not a key: account + region + instance-id is.

--expected (tick, live) or expected.json (batch): every instance's true state, keyed account/region/instance-id.
Standard library only. The same --seed gives the same fleet.
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import datetime, timezone

ACCOUNTS = ["111111111111", "222222222222"]
REGIONS = ["us-east-1", "eu-west-1"]
TYPES = ["t3.micro", "t3.small", "t3.large", "m6i.large", "c6i.xlarge"]
AMIS = ["ami-0a1b2c3d", "ami-0e4f5a6b", "ami-0c7d8e9f"]
USERS = ["ana", "ben", "cai", "deploy-bot"]
TEAMS = ["q-branch", "mi6-ops", "field"]
ISO = "%Y-%m-%dT%H:%M:%SZ"
HOUR = 3600.0


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime(ISO)


def seconds(s: str) -> float:
    return datetime.strptime(s, ISO).replace(tzinfo=timezone.utc).timestamp()


class Fleet:
    """The fleet and its simulated clock. Each instance has a state, its next step and when that is due;
    ``advance(until)`` runs every step due by then and returns the events they made."""

    def __init__(self, seed: int, size: int, clock: float):
        self.seed, self.size, self.clock, self.ticks = seed, size, clock, 0
        self.instances: dict[str, dict] = {}         # "account/region/id": its truth, its next step and when
        self.held: list[list] = []                   # [deliver at, event]: made, not delivered yet
        self.reused: str | None = None               # the one instance id given out in both accounts
        self.real: float | None = None               # the wall clock at the last tick (tick, live)

    def dump(self) -> dict:
        return dict(vars(self))

    @classmethod
    def load(cls, d: dict) -> "Fleet":
        f = cls(d["seed"], d["size"], d["clock"])
        vars(f).update(d)
        return f

    # ---- the events, in AWS's shapes ----
    def _envelope(self, rng, detail_type, t, account, region, detail, resources=()):
        return {"version": "0", "id": str(uuid.UUID(int=rng.getrandbits(128))), "detail-type": detail_type,
                "source": "aws.ec2", "account": account, "time": iso(t), "region": region,
                "resources": list(resources), "detail": detail}

    def _state(self, rng, out, t, inst, state):
        a, r, i = inst["account"], inst["region"], inst["instance_id"]
        out.append(self._envelope(rng, "EC2 Instance State-change Notification", t, a, r,
                                  {"instance-id": i, "state": state}, [f"arn:aws:ec2:{r}:{a}:instance/{i}"]))
        inst["state"] = state

    def _call(self, rng, out, t, account, region, name, user, request, response=None):
        detail = {"eventVersion": "1.08", "eventSource": "ec2.amazonaws.com", "eventName": name, "awsRegion": region,
                  "userIdentity": {"type": "IAMUser", "arn": f"arn:aws:iam::{account}:user/{user}"},
                  "requestParameters": request, "responseElements": response}
        if rng.random() < 0.03:                      # a few lack a field
            del detail["userIdentity"]["arn"]
        out.append(self._envelope(rng, "AWS API Call via CloudTrail", t, account, region, detail))

    # ---- the simulation ----
    def _launch(self, rng, out, t):
        account, region = rng.choice(ACCOUNTS), rng.choice(REGIONS)
        n = rng.choice([1, 1, 1, 2, 3])
        user, itype, ami = rng.choice(USERS), rng.choice(TYPES), rng.choice(AMIS)
        ids = []
        for _ in range(n):
            other = next((v for v in self.instances.values() if v["account"] != account), None)
            if self.reused is None and other is not None:          # once: an id the other account already has
                self.reused = other["instance_id"]
                ids.append(self.reused)
            else:
                ids.append(f"i-{rng.getrandbits(68):017x}")
        self._call(rng, out, t, account, region, "RunInstances", user,
                   {"instanceType": itype, "imageId": ami, "minCount": n, "maxCount": n},
                   {"instancesSet": {"items": [{"instanceId": i, "instanceType": itype, "imageId": ami} for i in ids]}})
        for i in ids:
            self.instances.setdefault(f"{account}/{region}/{i}", {
                "account": account, "region": region, "instance_id": i, "type": itype, "image": ami,
                "launched_by": user, "launched_at": iso(t), "tags": {}, "state": None, "starts": 1, "reboots": 0,
                "step": "pending", "next": t + rng.uniform(1, 5)})

    def _step(self, rng, out, inst):
        """The instance's step due at inst["next"], and which step is next, and when (none: it is gone)."""
        t, a, r, i, s = inst["next"], inst["account"], inst["region"], inst["instance_id"], inst["step"]
        user, items = inst["launched_by"], {"instancesSet": {"items": [{"instanceId": inst["instance_id"]}]}}
        if s == "pending":
            self._state(rng, out, t, inst, "pending")
            inst["step"], inst["next"] = ("doa" if rng.random() < 0.06 else "running"), t + rng.uniform(15, 60)
        elif s == "doa":                                            # died in pending: no capacity
            self._state(rng, out, t, inst, "shutting-down")
            inst["step"], inst["next"] = "terminated", t + rng.uniform(5, 30)
        elif s == "running":
            self._state(rng, out, t, inst, "running")
            if inst["starts"] == 1 and rng.random() < 0.8:          # tagged soon after launch (most)
                tags = {"Name": f"{rng.choice(['web', 'worker', 'db', 'cache'])}-{rng.randint(1, 99)}",
                        "team": rng.choice(TEAMS)}
                self._call(rng, out, t + rng.uniform(10, 300), a, r, "CreateTags", user,
                           {"resourcesSet": {"items": [{"resourceId": i}]},
                            "tagSet": {"items": [{"key": k, "value": v} for k, v in tags.items()]}})
                inst["tags"].update(tags)
            inst["step"], inst["next"] = "decide", t + rng.expovariate(1 / (10 * HOUR))
        elif s == "decide":
            x = rng.random()
            if x < 0.3:                                             # a reboot: the state stays running
                self._call(rng, out, t, a, r, "RebootInstances", user, items)
                inst["reboots"] += 1
                inst["next"] = t + rng.expovariate(1 / (10 * HOUR))
            elif x < 0.75:                                          # stopped, to be started again
                self._call(rng, out, t, a, r, "StopInstances", user, items)
                self._state(rng, out, t + 2, inst, "stopping")
                inst["step"], inst["next"] = "stopped", t + rng.uniform(20, 90)
            else:                                                   # terminated: the end
                self._call(rng, out, t, a, r, "TerminateInstances", user, items)
                self._state(rng, out, t + 2, inst, "shutting-down")
                inst["step"], inst["next"] = "terminated", t + rng.uniform(30, 120)
        elif s == "stopped":
            self._state(rng, out, t, inst, "stopped")
            if rng.random() < 0.3:                                  # resized while stopped
                new = rng.choice([x for x in TYPES if x != inst["type"]])
                self._call(rng, out, t + 60, a, r, "ModifyInstanceAttribute", user,
                           {"instanceId": i, "instanceType": {"value": new}})
                inst["type"] = new
            inst["step"], inst["next"] = "start", t + rng.uniform(0.2, 6) * HOUR
        elif s == "start":
            self._call(rng, out, t, a, r, "StartInstances", user, items)
            inst["starts"] += 1
            inst["step"], inst["next"] = "pending", t + 2
        elif s == "terminated":
            self._state(rng, out, t, inst, "terminated")
            inst["step"], inst["next"] = None, None

    def advance(self, until: float) -> list[dict]:
        rng = random.Random(f"{self.seed}:{self.ticks}")
        self.ticks += 1
        out: list[dict] = []
        t = self.clock
        while t < until:
            live = sum(1 for v in self.instances.values() if v["step"] is not None)
            t = min(until, t + rng.expovariate(max(self.size - live, 0.3) / HOUR))   # launches keep it near size
            if t < until:
                self._launch(rng, out, t)
            for inst in list(self.instances.values()):              # every step due by then
                while inst["next"] is not None and inst["next"] <= t:
                    self._step(rng, out, inst)
        self.clock = until
        return sorted(out, key=lambda e: e["time"])

    def deliver(self, events: list[dict], by: float) -> list[dict]:
        """What is delivered by ``by``: each event delayed (a few by a lot), about 2% twice; the rest held over."""
        rng = random.Random(f"{self.seed}:deliver:{self.ticks}")
        for e in events:
            at = seconds(e["time"]) + (rng.uniform(0, 90) if rng.random() > 0.02 else rng.uniform(60, 900))
            self.held.append([at, e])
            if rng.random() < 0.02:
                self.held.append([at + rng.uniform(1, 600), e])
        self.held.sort(key=lambda x: x[0])
        due = [e for at, e in self.held if at <= by]
        self.held = [x for x in self.held if x[0] > by]
        return due

    def truth(self) -> dict:
        keep = ("account", "region", "instance_id", "type", "image", "launched_by", "launched_at", "tags", "state",
                "starts", "reboots")
        return {k: {f: v[f] for f in keep} for k, v in sorted(self.instances.items())}


def line(e: dict) -> dict:
    """The light wrapper ergostat records: where it came from, and AWS's event whole."""
    return {"event": "aws.eventbridge", "data": e}



def tick(a) -> list[dict]:
    """One step of the fleet kept in a.state: from its last tick to now, sped up; what was delivered meanwhile."""
    now = time.time()
    try:
        with open(a.state) as fh:
            f = Fleet.load(json.load(fh))
    except FileNotFoundError:
        f = Fleet(a.seed, a.instances, now)
    sim = f.clock + max(0.0, now - (f.real or now)) * a.speed
    due = f.deliver(f.advance(sim), sim)
    f.real = now
    with open(a.state, "w") as fh:
        json.dump(f.dump(), fh)
    if a.expected:
        with open(a.expected, "w") as fh:
            json.dump(f.truth(), fh, indent=2)
    return due


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("batch", help="the whole stream as files")
    t = sub.add_parser("tick", help="one step of a fleet kept in --state; its events to stdout")
    lv = sub.add_parser("live", help="tick forever, printing each tick's lines")
    for p in (b, t, lv):
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--instances", type=int, default=20, help="the live fleet size it keeps near (default 20)")
    b.add_argument("--days", type=float, default=3)
    b.add_argument("--events", default="events.jsonl")
    b.add_argument("--expected", default="expected.json")
    for p in (t, lv):
        p.add_argument("--speed", type=float, default=60, help="simulated seconds per real second (default 60)")
        p.add_argument("--state", default=".ec2-sim.json", help="where the fleet is kept between ticks")
        p.add_argument("--expected", help="also write each instance's true state here, each tick")
    lv.add_argument("--every", type=float, default=10, help="seconds between ticks (default 10)")
    a = ap.parse_args()

    if a.mode == "batch":
        start = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc).timestamp()
        f = Fleet(a.seed, a.instances, start)
        events = f.advance(start + a.days * 86400)
        delivered = f.deliver(events, float("inf"))
        with open(a.events, "w") as out:
            out.writelines(json.dumps(line(e)) + "\n" for e in delivered)
        with open(a.expected, "w") as out:
            json.dump(f.truth(), out, indent=2)
        print(f"{len(delivered)} lines ({len(events)} events) for {len(f.instances)} instances: "
              f"{a.events}, {a.expected}", file=sys.stderr)
    elif a.mode == "tick":
        for e in tick(a):
            print(json.dumps(line(e)))
    else:
        while True:
            for e in tick(a):
                print(json.dumps(line(e)), flush=True)
            time.sleep(a.every)


if __name__ == "__main__":
    main()
