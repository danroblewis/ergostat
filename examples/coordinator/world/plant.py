"""The plant the Coordinator controls, simulated: the work, the workers, the codebase and the owner (05 §1).

Everything here is the world, not the controller. It says what happens when an item is leased, inspected,
accepted, expired or asked about; when a worker stalls; when landed rework is found, and by whom; when the owner
is at the desk, gives a new direction, corrects, answers and prunes; how the Coordinator's harness window fills
and is cut. The controllers (world/policy.py, run as ergostat's blocks by bin/coord.py) only call the actuators
below (lease, inspect, accept, reject, expire, ...) and read what a real deployment could read.

Time is in factory hours (`t`); the world is a function of the clock, stepped in steps of at most STEP. Chance is
drawn from a hash of the seed and what is being decided, so a run is reproduced exactly from its seed and the
same item meets the same luck under either policy.

The numbers are the record's, roughly (docs/proposals/coordinator/02-reference-modes.md, 03): the share of new
work later redone is 0.3 to 0.66 in a direction's first hours and 0.02 to 0.05 later (RM1); rework is found a
median 5 to 15 hours after it lands, a quarter within the hour (RM2); about one run in eight stalls (RM6); the
owner is away for 2 to 8 hours at a time and overnight (RM8); the window fills at 25 to 125k tokens an hour and is
cut at about 965k to 60k, with 70k re-injected (RM9).
"""

from __future__ import annotations

import hashlib
import math

STEP = 1 / 30                      # factory hours: the world moves in steps of two minutes

# The owner's directions (d1): when each is given (factory hours, moved to the owner's next time at the desk) and
# how many items it brings.
DIRECTIONS = [(1.0, 150), (5.5 * 24, 110), (12 * 24 + 2, 160), (19 * 24 + 1, 100), (25 * 24 + 3, 130)]

# Quality: the share of a direction's work that is wrong, against the direction's age (RM1), before learning.
PEAK, FLOOR, TAU_Q = 0.55, 0.04, 16.0
FAST_SHARE = 0.25                  # wrong in a way the tests show (a red test on the mainline, found within the hour)
RUN_MEDIAN, RUN_SIGMA = 1.5, 0.5   # a run's length, lognormal (hours)
P_STALL = 0.12                     # a run that falls silent and never finishes (RM6: 5 of 41 never finished, 7 silent)
QUIET_RATE, QUIET = 0.25, (10 / 60, 45 / 60)   # a sound run's long silences: how often, how long (hours)
DISCOVERY = {"fast": 1.5, "work": 0.035, "owner": 0.07}   # per hour: by the tests, by later work, by the owner
LINES = {"direction": 150, "proposed": 250, "removal": 20}
INITIAL_CODE, INITIAL_FEATURES = 20000, 100
EXPECTED_COST = 200.0              # lines a feature is expected to cost (the capacity analysis: CV8's denominator)
WINDOW, CUT_TO, REINJECT = 965_000, 60_000, 70_000

# What each depth of acceptance catches (u3, 07 LP1): of the defects the tests show, and of the subtle ones.
DEPTHS = ["none", "claims", "tests", "inspection", "deep-review", "hold-point"]
CATCH = {"none": (0.0, 0.0), "claims": (0.30, 0.05), "tests": (0.95, 0.05), "inspection": (0.95, 0.45),
         "deep-review": (0.97, 0.65), "hold-point": (0.97, 0.80)}
CHECK_TIME = {"none": 0.0, "claims": 0.03, "tests": 0.10, "inspection": 0.25, "deep-review": 0.6, "hold-point": 0.0}


class Plant:
    def __init__(self, s: dict):
        self.s = s
        self.by: dict[str, set[str]] = {}
        for i, it in s["items"].items():
            self.by.setdefault(it["state"], set()).add(i)

    # -- the clock and chance --------------------------------------------------------------------------------
    @property
    def t(self) -> float:
        return self.s["t"]

    def u(self, *key) -> float:
        h = hashlib.blake2b(repr((self.s["seed"], *key)).encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") / 2 ** 64

    def chance(self, rate: float, dt: float, *key) -> bool:
        """An event with this rate per hour happens within dt."""
        return rate > 0 and self.u(*key) < 1 - math.exp(-rate * dt)

    def emit(self, type: str, item: str, **data) -> None:
        self.s["feed"].append({"t": self.t, "type": type, "item": item, "data": data})

    def count(self, name: str, n: float = 1.0) -> None:
        m = self.s["m"].setdefault(str(int(self.t)), {})
        m[name] = m.get(name, 0) + n

    def log(self, name: str, value) -> None:
        self.s["log"].setdefault(name, []).append(value)

    # -- the owner (d2): at the desk or away ---------------------------------------------------------------
    def present(self, t: float | None = None) -> bool:
        t = self.t if t is None else t
        day, h = int(t // 24), t % 24
        if day % 7 in (5, 6):                                    # weekends: a morning and an evening
            spans = [(10, 13.5), (20, 23)]
        else:
            spans = [(8.5, 12.5), (13.5, 18.5), (20.5, 23.5)]
            if self.u("afternoon-away", day) < 0.35:             # an afternoon or evening away (RM8: 4 to 8 h)
                spans = [(8.5, 12.5), (12.5 + 4 + 4 * self.u("back", day), 23.5)]
            if self.u("late", day) < 0.3:                         # a late night at the desk
                spans[-1] = (spans[-1][0], 25.5)
        if h < 2 and day > 0:                                    # last night's late spell, past midnight
            prev = self.present_spans_end(day - 1)
            if prev > 24 and h < prev - 24:
                return True
        return any(a <= h < b for a, b in spans)

    def present_spans_end(self, day: int) -> float:
        if day % 7 in (5, 6):
            return 23
        return 25.5 if self.u("late", day) < 0.3 else 23.5

    # -- items -------------------------------------------------------------------------------------------------
    def new_item(self, origin: str, state: str, via: str, **data) -> str:
        self.s["n"] += 1
        i = f"work/{self.s['n']}"
        value = 1.0 if origin == "direction" else round(self.u("value", i), 3)
        lines = round(LINES[origin] * (0.6 + 0.8 * self.u("lines", i)))
        extra = 0 if origin == "removal" else round(lines * self.s["code"]["inflation"])
        lines += extra                                   # what the workers' recipes make them add beyond the need
        it = {"origin": origin, "dir": self.s["dir"]["k"], "value": value, "lines": lines, "extra": extra, "state": state,
              "since": self.t, "attempts": 0, "born": self.t, **data}
        self.s["items"][i] = it
        self.by.setdefault(state, set()).add(i)
        self.emit("work.arrived" if state == "proposed" else "work.directed", i, origin=origin, direction=it["dir"],
                  value=value, lines=lines, via=via)
        self.count(f"in-{via}")
        return i

    def move(self, i: str, state: str, type: str, **data) -> None:
        it = self.s["items"][i]
        self.by.get(it["state"], set()).discard(i)
        it["state"], it["since"] = state, self.t
        self.by.setdefault(state, set()).add(i)
        self.emit(type, i, **data)

    def ids(self, state: str) -> list[str]:
        return sorted(self.by.get(state, ()), key=lambda i: int(i.split("/")[1]))

    def item(self, i: str) -> dict:
        return self.s["items"][i]

    def age_of_direction(self, it: dict) -> float:
        return self.t - self.s["dirs"][it["dir"]]

    # -- quality ---------------------------------------------------------------------------------------------
    def rules_for(self, d: int) -> float:
        """How much of the learning about direction d is in force: corrections written down or held in the
        window for it, and a little of what was learnt on earlier directions (B3, B9)."""
        here = other = 0.0
        for c in self.s["corr"].values():
            if c["state"] in ("lost",):
                continue
            if c["dir"] == d:
                here += 1
            elif c["state"] in ("rule", "retired"):
                other += 1
        return here + 0.3 * min(other, 20)

    def p_wrong(self, it: dict, brief: float) -> float:
        """The chance a run's work on this item is wrong (03's quality of work), at the moment it is leased."""
        age = self.age_of_direction(it)
        base = FLOOR + (PEAK - FLOOR) * math.exp(-age / TAU_Q)
        learnt = 1 / (1 + 0.12 * self.rules_for(it["dir"]))
        cut = self.s["window"].get("last_cut")
        after_cut = 1 + 0.2 * math.exp(-(self.t - cut) / 4) if cut is not None and self.t >= cut else 1.0
        return min(0.9, base * learnt * brief * after_cut)

    # -- actuators: what the Coordinator may do ---------------------------------------------------------------
    def lease(self, i: str, brief: float = 1.0, brief_tokens: int = 960) -> str:
        it = self.item(i)
        it["attempts"] += 1
        r = f"run/{self.s['n_runs'] + 1}"
        self.s["n_runs"] += 1
        dur = RUN_MEDIAN * math.exp(RUN_SIGMA * normal(self.u("dur", r), self.u("dur2", r)))
        stall = self.t + (0.1 + 0.7 * self.u("stall-at", r)) * dur if self.u("stall", r) < P_STALL else None
        self.s["runs"][r] = {"item": i, "start": self.t, "dur": dur, "stall_at": stall, "last": self.t,
                             "quiet_until": None, "p": self.p_wrong(it, brief), "tokens": brief_tokens, "beat": self.t}
        it["run"] = r
        self.move(i, "leased", "work.leased", run=r, attempt=it["attempts"])
        self.count("leased")
        return r

    def end_run(self, r: str) -> dict:
        run = self.s["runs"].pop(r)
        self.item(run["item"]).pop("run", None)
        return run

    def expire(self, r: str, why: str) -> None:
        """The lease of a run is taken back (a stall noticed, or a silence past its lease): the item is ready again."""
        run = self.s["runs"][r]
        i = run["item"]
        if run["stall_at"] is not None and self.t >= run["stall_at"]:
            self.log("stalls", [run["stall_at"], self.t, self.present(run["stall_at"]), self.running()])
            self.count("stalls-noticed")
        else:
            self.count("false-expiries")
        self.end_run(r)
        self.move(i, "ready", "work.expired", via="expired", why=why)

    def dead_letter(self, r: str) -> None:
        run = self.s["runs"][r]
        if run["stall_at"] is not None and self.t >= run["stall_at"]:
            self.log("stalls", [run["stall_at"], self.t, self.present(run["stall_at"]), self.running()])
        i = self.end_run(r)["item"]
        self.move(i, "dead-letter", "work.dead-lettered", attempts=self.item(i)["attempts"])

    def redrive(self, i: str) -> None:
        self.item(i)["attempts"] = 0
        self.move(i, "ready", "work.redriven", via="redriven")

    def admit(self, i: str) -> None:
        self.move(i, "ready", "work.admitted", via="admitted")

    def decline(self, i: str, why: str) -> None:
        self.move(i, "declined", "work.declined", why=why)

    def resurrect(self, i: str) -> None:
        self.move(i, "ready", "work.resurrected", via="resurrected")

    def start_check(self, i: str, depth: str, read_status: bool = True) -> None:
        """Acceptance begins at this depth (u3); a hold point waits for the owner (ask_owner)."""
        it = self.item(i)
        it["check"] = {"depth": depth, "until": self.t + CHECK_TIME[depth], "read": read_status}
        self.emit("work.inspecting", i, depth=depth)

    def check_due(self, i: str) -> bool:
        c = self.item(i).get("check")
        return bool(c) and self.t >= c["until"] and not self.item(i).get("waiting_owner")

    def inspect(self, i: str) -> bool:
        """The verdict of the check under way: True when it found the work wrong. A test whose exit status is not
        read (RM5) shows a failure only when the failure is in the text that was read."""
        it = self.item(i)
        c = it["check"]
        cf, cs = CATCH[c["depth"]]
        if not c["read"]:
            cf = 0.30 if c["depth"] != "none" else 0.0           # the tail of the output, read as text
        self.count("test-runs")
        if not c["read"]:
            self.count("hidden-runs")
        wrong = it.get("wrong")
        caught = bool(wrong) and self.u("catch", i, it["attempts"]) < (cf if wrong == "fast" else cs)
        if wrong and caught:
            self.count("caught")
            self.log("found", [it.get("reported", self.t), self.t, "check", self.age_of_direction(it)])
        return caught

    def accept(self, i: str) -> None:
        it = self.item(i)
        depth = it.pop("check", {}).get("depth", "none")
        lines = it["lines"]
        code = self.s["code"]
        if it.get("reworked"):                                   # a fix replaces what it fixes, and adds a little
            code["lines"] += round(0.1 * lines)
            self.count("lines-reworked", round(0.9 * lines))
            self.count("lines-added", round(0.1 * lines))
            it["reworked"] = False
        elif it["origin"] == "removal":
            took = min(code["low"], 300)
            code["lines"] -= took - lines
            code["low"] -= took
            self.count("lines-removed", took)
            self.count("lines-added", lines)
        else:
            code["lines"] += lines
            self.count("lines-added", lines)
            if it["value"] >= 0.6:
                code["features"] += 1
                it["feature"] = True
                code["low"] += it.get("extra", 0)
            else:
                code["low"] += lines
            # code inflation: each change the AI workers land teaches the next to write a little more (their
            # recipes, examples and standing rules unrevised); consolidation revises them (07 LP10)
            code["inflation"] = min(1.0, code["inflation"] + 0.002)
        it["landed"] = self.t
        self.count("accepted")
        self.count(f"accepted-{it['origin']}")
        if it.get("wrong"):
            self.count("escaped")
            self.s["hidden"].append(i)
            self.count("lines-wrong", lines)
        self.move(i, "accepted", "work.accepted", depth=depth)

    def reject(self, i: str) -> None:
        it = self.item(i)
        depth = it.pop("check", {}).get("depth", "none")
        it["reworked"] = False
        it.pop("wrong", None)
        self.move(i, "ready", "work.rejected", via="rejected", depth=depth)

    def ask_owner(self, i: str, why: str, interrupt: bool = True) -> None:
        """The item waits on the owner (a hold point, or a question about intent): S5's stock."""
        it = self.item(i)
        it["waiting_owner"] = {"since": self.t, "why": why, "interrupt": interrupt}
        self.s["owner"]["queue"].append(i)
        self.emit("work.asked", i, why=why, interrupt="yes" if interrupt else "no")
        self.count("asked")
        if interrupt:
            self.count("interruptions")

    def propose(self, origin: str = "proposed") -> str:
        return self.new_item(origin, "proposed", "proposed")

    def add_removal(self) -> str:
        i = self.new_item("removal", "proposed", "proposed")
        return i

    # -- the observer's side: corrections and what holds them (LP9) -------------------------------------------
    def externalise(self, c: str) -> None:
        cc = self.s["corr"][c]
        cc["state"], cc["written"] = "rule", self.t
        self.count("externalised")
        self.emit("correction.recorded", f"correction/{c}", direction=cc["dir"])

    def retire(self, c: str, why: str) -> None:
        cc = self.s["corr"][c]
        cc["state"], cc["retired"] = "retired", self.t
        self.count("retired")
        self.emit("correction.retired", f"correction/{c}", why=why)

    # -- readings --------------------------------------------------------------------------------------------
    def running(self) -> int:
        return len(self.s["runs"])

    def silence(self, r: str) -> float:
        return self.t - self.s["runs"][r]["last"]

    def stalled(self) -> int:
        return sum(1 for r in self.s["runs"].values() if r["stall_at"] is not None and self.t >= r["stall_at"])

    def undiscovered(self) -> int:
        return len(self.s["hidden"])

    def cv8(self) -> float:
        c = self.s["code"]
        return c["lines"] / max(c["features"], 1) / EXPECTED_COST

    def escaped_share(self, days: float = 7.0) -> tuple[float, int]:
        """CV1: of the work accepted over the window, the share found wrong after it landed (as far as found)."""
        since = self.t - 24 * days
        acc = [it for it in self.s["items"].values() if it.get("landed", -1) >= since and it["origin"] != "removal"]
        found = sum(1 for it in acc if it.get("found_after"))
        return (found / len(acc) if acc else 0.0), len(acc)

    # -- the world moving on ---------------------------------------------------------------------------------
    def step(self, dt: float) -> None:
        self.s["t"] += dt
        t = self.t
        self.directions()
        self.workers(dt)
        self.discovery(dt)
        self.owner_acts(dt)
        self.window(dt)

    def directions(self) -> None:
        d = self.s["dir"]
        nxt = d["k"] + 1
        if nxt < len(DIRECTIONS) and self.t >= DIRECTIONS[nxt][0] and self.present():
            d["k"] = nxt
            self.s["dirs"].append(self.t)
            for _ in range(DIRECTIONS[nxt][1]):
                self.new_item("direction", "ready", "directed")
            self.count("directions")
            self.count("owner-messages", 3)
            self.emit("direction.given", f"direction/{nxt}", items=DIRECTIONS[nxt][1])

    def workers(self, dt: float) -> None:
        for r, run in list(self.s["runs"].items()):
            stalled = run["stall_at"] is not None and self.t >= run["stall_at"]
            if stalled:
                continue
            q = run["quiet_until"]
            if q is not None and self.t < q:
                continue
            if q is None and self.chance(QUIET_RATE, dt, "quiet", r, round(self.t * 30)):
                run["quiet_until"] = self.t + QUIET[0] + (QUIET[1] - QUIET[0]) * self.u("quiet-len", r, round(self.t * 30))
                continue
            run["quiet_until"] = None
            run["last"] = self.t
            run["tokens"] += 120_000 * dt
            if self.t - run["beat"] >= 0.25:                      # transcript lines, coalesced: the lease renewed
                run["beat"] = self.t
                self.emit("work.renewed", run["item"], run=r)
            if self.t >= run["start"] + run["dur"]:
                i = run["item"]
                it = self.item(i)
                wrong = self.u("wrong", i, it["attempts"]) < run["p"]
                it["wrong"] = ("fast" if self.u("fast", i, it["attempts"]) < FAST_SHARE else "subtle") if wrong else None
                it["reported"] = self.t
                self.log("windows", run["tokens"])
                self.end_run(r)
                self.move(i, "reported", "work.reported", run=r)
                self.count("reported")

    def discovery(self, dt: float) -> None:
        """Landed rework found (R1's discovery): by a red test on the mainline soon after, by later work that
        touches it, or by the owner while at the desk."""
        present = self.present()
        keep = []
        for i in self.s["hidden"]:
            it = self.item(i)
            k = round(self.t * 30)
            by = None
            if it["wrong"] == "fast" and self.chance(DISCOVERY["fast"], dt, "d-fast", i, k):
                by = "tests"
            elif self.chance(DISCOVERY["work"], dt, "d-work", i, k):
                by = "work"
            elif present and self.chance(DISCOVERY["owner"], dt, "d-owner", i, k):
                by = "owner"
            if by is None:
                keep.append(i)
                continue
            age = self.t - it["landed"]
            self.log("found", [it["landed"], self.t, by, self.age_of_direction(it)])
            self.count(f"found-by-{by}")
            it["found_after"] = True
            it["reworked"] = True
            it["wrong"] = None
            if it["state"] == "accepted":
                self.move(i, "ready", "work.reopened", via="reopened", found_by=by, age_hours=round(age, 2))
            if by == "tests":
                self.s["incidents"].append(self.t)               # a red mainline: a slip someone may report
            if by == "owner":
                self.correction(it)
        self.s["hidden"] = keep

    def correction(self, it: dict) -> None:
        """The owner corrects (an owner message): a correction about this direction's work. If the same point
        was made before and lost at a cut, it is a repeat."""
        n = len(self.s["corr"]) + 1
        lost = sum(1 for c in self.s["corr"].values() if c["state"] == "lost" and c["dir"] == it["dir"])
        repeat = lost > 0 and self.u("repeat", n) < lost / (lost + 4)
        self.s["corr"][str(n)] = {"t": self.t, "dir": it["dir"], "state": "window", "repeat": repeat,
                                  "checkable": self.u("checkable", n) < 0.6}
        self.count("corrections")
        self.count("owner-messages")
        if repeat:
            self.count("repeats")
        self.emit("correction.said", f"correction/{n}", direction=it["dir"], repeat="yes" if repeat else "no")

    def owner_acts(self, dt: float) -> None:
        o = self.s["owner"]
        present = self.present()
        if present:
            k = round(self.t * 30)
            if self.chance(3.5, dt, "msg", k):                    # the owner's messages mid-work (d3)
                self.count("owner-messages")
                o["decisions"] += 0.25                            # what the extractor proposes from them (RM8)
            if not o["was_present"]:
                o["returned"] = self.t
                self.count("returns")
            # the owner answers what waits for them, quickly when at the desk (RM8: a median 2 to 4 minutes)
            for i in list(o["queue"]):
                w = self.item(i).get("waiting_owner")
                if w is None:
                    o["queue"].remove(i)
                    continue
                if not w["interrupt"] and not o.get("report_read"):      # batched: answered in the handover report
                    continue
                if self.chance(20, dt, "answer", i, k):
                    o["queue"].remove(i)
                    self.item(i).pop("waiting_owner")
                    self.log("answered", [w["since"], self.t])
                    self.count("answered")
                    self.emit("work.answered", i)
            # resurrections: now and then the owner takes back something the factory declined
            if self.by.get("declined") and self.chance(0.05, dt, "resurrect", k):
                self.resurrect(self.ids("declined")[0])
            # pruning (B5, outside the Coordinator): the owner removes a subsystem once the code has been
            # inflated past what its features are worth for long enough (RM3: two weeks late)
            if self.cv8() > 1.35:
                o["bloated_since"] = o.get("bloated_since") or self.t
                if self.t - o["bloated_since"] > 10 * 24:
                    took = round(0.7 * self.s["code"]["low"])
                    self.s["code"]["lines"] -= took
                    self.s["code"]["low"] -= took
                    self.count("lines-removed", took)
                    self.count("lines-pruned", took)
                    self.log("pruned", [self.t, took])
                    self.emit("code.pruned", "codebase/main", lines=took)
                    o["bloated_since"] = None
            else:
                o["bloated_since"] = None
        o["was_present"] = present

    def window(self, dt: float) -> None:
        """The Coordinator's harness window (H5): filled by the work, cut by the harness when nearly full. Under
        the designed policy the Coordinator is ergostat and keeps no window: what fills is each worker's own
        (reported at each run's end), and the record, which is never cut."""
        w = self.s["window"]
        if not w.get("on"):
            return
        k = round(self.t * 30)
        reads = 0.0
        acts = self.s["m"].get(str(int(self.t)), {}).get("accepted", 0)
        inflow = 0.0
        if self.running() or self.present():
            inflow = 6_000 + (14_000 + 4 * 3_500) * self.present() + 5_000 * self.running() + 8_000 * min(acts, 4)
            reads = 13 * inflow / 100_000
        w["tokens"] += inflow * dt
        self.count("context-in", inflow * dt)
        cut = w.get("last_cut")
        burst = 17 * math.exp(-(self.t - cut) / 1.0) if cut is not None and self.t - cut < 4 else 0.0
        if reads and self.chance(reads, dt, "read", k):
            self.count("reads")
            if self.u("reread", k) < 0.57:
                self.count("rereads")
        if burst and self.chance(burst, dt, "burst", k):
            self.count("reads")
            self.count("rereads")
            self.count("rereads-after-cut")
        if w["tokens"] >= WINDOW:
            self.log("cuts", [self.t, w["tokens"]])
            w["tokens"] = CUT_TO + REINJECT
            w["last_cut"] = self.t
            self.count("cuts")
            for c in self.s["corr"].values():                    # held only in the window: gone with the cut (B9)
                if c["state"] == "window":
                    c["state"] = "lost"
                    self.count("lost-at-cut")


def normal(u1: float, u2: float) -> float:
    """A standard normal from two uniforms (Box-Muller)."""
    return math.sqrt(-2 * math.log(max(u1, 1e-12))) * math.cos(2 * math.pi * u2)


def fresh(seed: int = 1, policy: str = "designed") -> dict:
    """A new world: the factory at the start of the record, the first direction an hour away."""
    return {"seed": seed, "policy": policy, "t": 0.0, "n": 0, "n_runs": 0, "items": {}, "runs": {}, "hidden": [],
            "dir": {"k": -1}, "dirs": [], "incidents": [],
            "code": {"lines": INITIAL_CODE, "low": 0, "features": INITIAL_FEATURES, "inflation": 0.0},
            "window": {"on": policy == "harness", "tokens": 128_000 if policy == "harness" else 0, "last_cut": None},
            "corr": {}, "owner": {"queue": [], "decisions": 0.0, "was_present": False},
            "ctrl": {}, "m": {}, "log": {}, "feed": []}
