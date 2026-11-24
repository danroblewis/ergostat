"""The control view (SPEC §1a): the whole control system as one block diagram, in the notation of
the textbooks (Ogata; Franklin, Powell & Emami-Naeini; Åström & Murray) and of Simulink for its
hierarchy. Worked out from the model, never written, as plain data the page lays out and draws.

What each part of the model becomes:

- A **controller** or **actuator** is a block the model runs (a goal's onoff, a proportional, a
  program, an AI agent, a person), drawn once however many loops it serves. A setting a controller
  steps (a stock moved by a two-way flow only it moves) is the controller's own memory: its value
  is the controller's output u, and a block that reads its goal's error and steps a setting on a
  schedule is integral action, C(z) = K_i T z/(z − 1) (it acts at once on the error it has read).
- A **process** is the part of the world between what the blocks move and what they read. A stock
  whose flows are all inputs (moved by blocks, or disturbances) is an integrator, 1/s, with its
  flows summed in front of it (each a + or −). Anything else (flows that follow others,
  auxiliaries) is not identified, and is grouped by system: outputs that share inputs are one
  multi-input multi-output block, with its inputs and outputs gathered into vectors (Simulink's
  mux and demux), unless drawing them one by one takes fewer lines. Its transfer matrix has a zero only
  where no path inside it leads from the input to the output.
- A **sensor** read by a loop is a block on the feedback path, beneath it (Franklin, Powell & Emami-Naeini's
  standard loop), labelled with what it reads and how often (``sensing.py``): H(s) when the model gives it
  dynamics (a rate over a window: a moving average), a delay e^(−sT) (a sampler on the feedback path) when it
  polls every T, drawn muted when T is under a tenth of the loop's period, and H = 1 when it neither polls nor
  has dynamics.
  A collector, the command or query that turns an outside system into the items a count reads, is drawn
  in front of it, on the same path: the count is only as fresh as the collector.
- A **discrete controller** C(z) takes one input, sampled (a sampler, T), and drives the continuous
  process through a zero-order hold; what else moves its setting adds at a summing junction after it.
- A **goal** is a reference r = its value, compared at a summing junction (e = r − y_m), in the frame of
  the controller that reads its error; a controller that reads the measurement itself is given r beside it (two degrees of
  freedom). A goal whose setpoint another block sets is a cascade: its loop is drawn nested.
- A **disturbance** (a flow nothing in the control system moves, or an input from outside the
  model) enters at the process: at a stock's summing junction, or as an input of the process.
- A block the model runs that reads nothing and is commanded by nothing (the world: customers,
  arrivals) is where a disturbance comes from, not a block of the control system.
- A **system** is a subsystem block when closed, classified by the signals crossing its edge: C (it acts on
  another system's process), P (it is acted on) or its own name (both, or neither); P(s) when every part inside is
  continuous, else P (an operator), with its p outputs by m inputs, disturbances counted, the same open; open, its
  parts are drawn inside its frame, with a port mark where a signal crosses it; drawn alone, what crosses its edge
  are its In and Out ports."""

from __future__ import annotations

from . import rates, sensing
from .library.untrusted import Shown
from .spec.ir import KIND_OF_TYPE, Ref, Spec

WORLD_NOTE = "a block that reads nothing and is commanded by nothing: the world, from the control system's side"


# ---- MathML as nested lists: [tag, child, ...] or [tag, {attrs}, child, ...]; strings are text

def mi(x: str):
    return ["mi", x]


def mn(x) -> list:
    return ["mn", _num(x)]


def mo(x: str):
    return ["mo", x]


def mt(x: str):
    return ["mtext", x]


def row(*xs):
    return ["mrow", *xs]


def frac(a, b):
    return ["mfrac", a, b]


def sym(base: str, sub: str | None = None, arg: str | None = None, bold: bool = False):
    """``C_tuner(z)``: a symbol, its subscript as text (names have hyphens), its argument."""
    b = ["mi", {"mathvariant": "bold"}, base] if bold else mi(base)
    out = ["msub", b, mt(sub)] if sub else b
    return row(out, mo("("), mi(arg), mo(")")) if arg else out


def eq(*xs):
    """Parts joined by =."""
    out: list = []
    for i, x in enumerate(xs):
        if i:
            out.append(mo("="))
        out.append(x)
    return row(*out)


def _signed(terms) -> list:
    """+u_a − d_b as MathML parts, the first sign dropped when it is +."""
    out: list = []
    for i, (sy, name, sg) in enumerate(terms):
        if i or sg < 0:
            out.append(mo("+" if sg > 0 else "−"))
        out.append(sym(sy, name))
    return out


def _num(x) -> str:
    if x is None:
        return "?"
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}"


def _dur(sec: float | None) -> str:
    from .durations import human
    return human(sec) if sec else ""


# ---- the diagram, flat: every part with its system, every wire from a port to a port

class _Diagram:
    def __init__(self, spec: Spec, snap: dict | None):
        self.s, self.snap = spec, snap or {}
        self.nodes: dict[str, dict] = {}
        self.wires: list[dict] = []
        self.prod: dict[str, tuple[str, str]] = {}     # signal key -> (node, port) that produces it
        self.sig: dict[str, dict] = {}                 # signal key -> how it is written
        self.frames: list[dict] = []
        self.shown = Shown(spec)                       # what an untrusted template made: its text marked (SPEC §2a)
        self._classify()

    # -- what each part of the model is to the control system

    def _classify(self) -> None:
        s = self.s
        B = s.blocks
        self.commands: set[tuple[str, str]] = set()    # (commander, commanded)
        for b in B.values():
            for t in b.targets():
                if t.kind == "block" and t.name in B:
                    self.commands.add((b.name, t.name))
            for r in b.inputs.values():
                if r.kind == "block" and r.name in B:
                    self.commands.add((r.name, b.name))
        commanded = {c for _, c in self.commands}
        self.world = {n for n, b in B.items() if b.targets() and not b.reads() and n not in commanded
                      and all(t.kind in ("flow", "auxiliary") for t in b.targets())}
        self.control = [n for n in B if n not in self.world]
        self.collectors = sensing.collectors(s)       # kind -> the sensors that record its items
        self.moved: dict[str, tuple[str, str]] = {}    # "flow.x" / "auxiliary.x" -> (block, its port)
        for n in self.control:
            for port, refs in B[n].outputs.items():
                for t in refs:
                    if t.kind in ("flow", "auxiliary"):
                        self.moved[f"{t.kind}.{t.name}"] = (n, port)
        self.goalvars = {f"{g.of.kind}.{g.of.name}": [] for g in s.goals.values()}
        for g in s.goals.values():
            self.goalvars[f"{g.of.kind}.{g.of.name}"].append(g.name)
        self.knob: dict[str, str] = {}                 # "stock.k" -> the block whose setting it is
        self.knob_flow: dict[str, str] = {}            # its flow -> "stock.k"
        for f in s.flows.values():
            mover = self.moved.get(f"flow.{f.name}")
            if not (mover and f.two_way):
                continue
            for end in (f.target, f.source):
                k = f"stock.{end}"
                if end and end in s.stocks and k not in self.goalvars and k not in self.knob:
                    self.knob[k], self.knob_flow[f.name] = mover[0], k
                    break
        # the setting a block steps; a stepping controller that reads its goal's error on a schedule integrates it
        self.setting_of = {b: k for k, b in self.knob.items()}
        # what each block reads, as signals (a machine block's goal: is said by the onoff ergostat puts in front of it)
        implied_for = {}
        commanding: dict[str, list[str]] = {}          # a block → what it commands; a block → what commands it, in order
        commanded_by: dict[str, list[str]] = {}
        for c, d in sorted(self.commands):
            commanding.setdefault(c, []).append(d)
            commanded_by.setdefault(d, []).append(c)
        for n, b in B.items():
            if b.implied and b.goal:
                for c in commanding.get(n, ()):
                    implied_for.setdefault(c, set()).add(b.goal)
        self.reads: dict[str, list[tuple[str, str]]] = {}   # block -> [(its input's name, signal key)]
        self.error_read: set[str] = set()              # goals whose error a block reads: they get a summing junction
        self.reads_y: dict[str, set[str]] = {}         # goal -> the blocks reading its measurement directly
        for n in self.control:
            b = B[n]
            out = []
            for port, r in b.inputs.items():
                if r.kind == "block":
                    continue
                k = self._read_key(r)
                if all(k != x for _, x in out):
                    out.append((port, k))
            if b.goal and b.goal not in implied_for.get(n, set()):
                out.append(("goal", f"goal.{b.goal}.e"))
            for c in commanded_by.get(n, ()):
                out.append((c, f"cmd.{c}.{n}"))
            for _, sk in out:
                if sk.startswith("goal.") and sk.endswith(".e"):
                    self.error_read.add(sk.split(".")[1])
            self.reads[n] = out
        # who reads each signal: a variable (itself, or its sensor's measurement: meas.<kind>.<name>.<sensor>), an error
        self.readers_of: dict[str, list[str]] = {}
        for n, rs in self.reads.items():
            for _, k in rs:
                var = ".".join(k.split(".")[1:3]) if k.startswith("meas.") else k
                got = self.readers_of.setdefault(var, [])
                if not got or got[-1] != n:
                    got.append(n)
        for g in s.goals.values():
            for n in self.readers_of.get(f"{g.of.kind}.{g.of.name}", ()):
                self.reads_y.setdefault(g.name, set()).add(n)

    def _read_key(self, r: Ref) -> str:
        if r.kind == "goal":
            return f"goal.{r.name}.e"
        var = f"{r.kind}.{r.name}"
        sen = self._sensors(var)
        if sen and self.sensed(var):
            return f"meas.{var}.{r.port if r.port in sen else sen[0]}"
        return var

    def sensed(self, var: str) -> bool:
        """Whether a variable is read through a sensor block: on a feedback path (a process output read back)
        always, so that the loop shows what finds the work; elsewhere (an input read ahead) only when the
        sensor has dynamics of its own."""
        return bool(self._sensors(var)) and (self.sensor_dynamics(var) or not self.is_input(var))

    def meas_key(self, var: str) -> str:
        """What a loop reads of a variable: its sensor's output (y_m), or the variable itself when nothing
        measures it."""
        sen = self._sensors(var)
        return f"meas.{var}.{sen[0]}" if sen and self.sensed(var) else var

    def sensor_dynamics(self, var: str) -> bool:
        """A sensor with dynamics the model says: a rate over a window (an average), not a reading."""
        kind, name = var.split(".", 1)
        t = self.s.measured(kind).get(name)
        return bool(t) and any(x.changes or (x.items and kind == "flow") for x in t.sensors.values() if x.measured or x.manual)

    def sensor_note(self, var: str) -> str:
        """How a variable read with unity gain is measured: said in the panel, not drawn."""
        kind, name = var.split(".", 1)
        t = self.s.measured(kind).get(name)
        sensors = [x for x in (t.sensors.values() if t else []) if x.measured or x.manual]
        if not sensors:
            return ""
        def when(x) -> str:
            return "read by hand" if x.manual else f"sampled every {_dur(x.every)}" if x.every else "on a cron schedule"
        how = ", ".join(f"{x.name} ({when(x)})" for x in sensors)
        return (f"measured with unity gain by its sensor{'s' if len(sensors) > 1 else ''} {how}: y_m = y, "
                "so the feedback path is the wire itself")

    def _sensors(self, var: str) -> list[str]:
        kind, name = var.split(".", 1)
        t = self.s.measured(kind).get(name)
        if not t:
            return []
        return [x.name for x in t.sensors.values() if x.measured or x.manual]

    def comparator_system(self, g) -> str | None:
        """A goal's summing junction sits with the controller that reads its error (Simulink: a subsystem's
        boundary is crossed by signals at its ports, so the comparator goes where its error is used)."""
        readers = sorted(set(self.readers_of.get(f"goal.{g.name}.e", ())))
        return self.s.blocks[readers[0]].system if readers else g.system

    def _system(self, var: str) -> str | None:
        kind, name = var.split(".", 1)
        return self.s.owner(Ref(kind, name))

    def is_input(self, var: str) -> bool:
        """What the processes take in: what blocks move or set, the settings they step, disturbances."""
        return var in self.moved or var in self.knob or self.disturbance(var)

    def disturbance(self, var: str) -> bool:
        kind, name = var.split(".", 1)
        if var in self.moved or var in self.knob:
            return False
        if kind == "flow":
            return not self.s.flows[name].driven_by
        if kind == "auxiliary":
            a = self.s.auxiliaries[name]
            return a.exogenous or not a.driven_by
        return False

    def causes(self, var: str) -> list[tuple[str, int | None]]:
        kind, name = var.split(".", 1)
        s = self.s
        if kind == "stock":
            return [(f"flow.{f.name}", 1 if f.target == name else -1) for f in s.flows_of(name)]
        t = s.flows.get(name) if kind == "flow" else s.auxiliaries.get(name)
        return [(f"{r.kind}.{r.name}", t.polarity.get(str(r))) for r in (t.driven_by if t else [])]

    # -- signals: how each is written, who produces it, who reads it

    def signal(self, key: str) -> dict:
        if key in self.sig:
            return self.sig[key]
        parts = key.split(".")
        if key.startswith("goal.") and key.endswith(".r"):
            out = {"sym": "r", "sub": parts[1], "what": "reference"}
        elif key.startswith("goal.") and key.endswith(".e"):
            out = {"sym": "e", "sub": parts[1], "what": "error"}
        elif key.startswith("meas."):
            out = {"sym": "y", "sub": f"m,{parts[2]}", "what": "measured", "of": parts[1] + "." + parts[2]}
        elif key.startswith("cmd."):
            c = self.s.blocks[parts[1]]
            out = {"sym": "u", "sub": c.goal if c.implied and c.goal else parts[1], "what": "command"}
        elif self.disturbance(key):
            out = {"sym": "d", "sub": parts[1], "what": "disturbance"}
        elif key in self.moved or key in self.knob:
            out = {"sym": "u", "sub": parts[1], "what": "control"}
        else:
            out = {"sym": "y", "sub": parts[1], "what": "output"}
        out["key"] = key
        self.sig[key] = out
        return out

    def node(self, id: str, **kw) -> dict:
        n = self.nodes.get(id)
        if n is None:
            said = self.inferred(kw.get("part"))
            if said and isinstance(kw.get("rows"), list):        # a part a model change added: said, quietly, last
                kw["rows"] = [*kw["rows"], ["origin", said]]
            self.untrusted(f"block.{id[4:]}" if id.startswith("blk:") else kw.get("part"), kw)
            n = self.nodes[id] = {"id": id, "ins": [], "outs": [], **kw}
        return n

    def untrusted(self, ref, kw: dict) -> None:
        """A part an untrusted template made: its words as the panel and the export write them marked (its description
        whole, its name wherever it stands as a word), and its name, marked, first."""
        got = self.shown.parts.get(str(ref))
        if got is None:
            return
        sh, name, where = self.shown, str(ref).split(".", 1)[1], got[1].where
        kw["says"] = sh.names(kw.get("says"))
        kw["rows"] = [["untrusted library", sh.mark(name, where)]] + [
            [k, sh.mark(v, where) if k == "description" else sh.names(v)] for k, v in kw.get("rows") or []]

    def system_says(self, name: str) -> str:
        """A system's description, marked when an untrusted template made it."""
        t = self.s.systems.get(name) or ""
        return self.shown.mark(t, name) if name in self.shown.systems else t

    def inferred(self, ref) -> str | None:
        """"added by ergostat, from model change X" for a part a model change added (``inferred:``, SPEC §12e)."""
        kind, _, name = str(ref or "").partition(".")
        x = {"stock": self.s.stocks, "flow": self.s.flows, "auxiliary": self.s.auxiliaries}.get(kind, {}).get(name)
        v = getattr(x, "inferred", None)
        if not v:
            return None
        return "added by ergostat" + (f", from model change {v.split('/', 1)[1]}" if "/" in v else "")

    def port(self, nid: str, io: str, name: str, side: str | None = None, sign: str | None = None) -> str:
        n = self.nodes[nid]
        pid = f"{nid}|{io}|{name}"
        lst = n["ins" if io == "in" else "outs"]
        if not any(p["id"] == pid for p in lst):
            lst.append({"id": pid, "side": side or ("W" if io == "in" else "E"), **({"sign": sign} if sign else {})})
        return pid

    def produce(self, key: str, nid: str, name: str | None = None, side: str = "E") -> None:
        self.prod[key] = (nid, self.port(nid, "out", name or key, side))

    def source(self, key: str) -> tuple[str, str] | None:
        """The port that produces a signal; a disturbance's or a setpoint's input is made when first read."""
        if key in self.prod:
            return self.prod[key]
        if key.startswith("goal.") and key.endswith(".r"):
            g = self.s.goals[key.split(".")[1]]
            nid = f"ref:{g.name}"
            # it enters where it is compared: its summing junction, or the controller that reads the measurement itself
            readers = sorted(self.reads_y.get(g.name, ())) if g.name not in self.error_read else []
            where = self.s.blocks[readers[0]].system if readers else self.comparator_system(g)
            one_sided = g.hold.op != "=="                # a limit (r ≤ 0), not a setpoint (r = 0.93): drawn and named so
            self.node(nid, kind="input", role="reference", system=where, label=f"r {g.name}",
                      fn={"sym": "r", "sub": g.name, "value": _hold(g)}, loops=[g.name],
                      math=[row(sym("r", g.name), mo(OPS.get(g.hold.op, "=")), mn(g.hold.value))],
                      says=f"the reference input of {g.name}, {'a limit' if one_sided else 'a setpoint'}: r {_hold(g)}" +
                           (f", held within ±{_num(g.tolerance)}" if g.tolerance else "") +
                           (f". {g.of.name} holds while it is within it, and the error e = r − y counts only past it: "
                            "0 inside the limit. An on-off controller serving it says in its own panel when it switches"
                            if one_sided else "") + ".",
                      rows=[["goal", g.name], ["limit" if one_sided else "holds", f"y_{g.of.name} {_hold(g)}"],
                            ["description", g.description]])
            self.produce(key, nid)
            return self.prod[key]
        if not key.startswith(("goal.", "meas.", "cmd.")) and self.disturbance(key):
            kind, name = key.split(".", 1)
            nid = f"dist:{key}"
            mover = next((b for b in self.world if any(f"{t.kind}.{t.name}" == key for t in self.s.blocks[b].targets())), None)
            t = self.s.flows.get(name) if kind == "flow" else self.s.auxiliaries.get(name)
            says = (f"a disturbance d_{name}: an input no block of the control system sets" +
                    (f"; {mover} drives it ({WORLD_NOTE})" if mover else "; nothing in the model drives it") + ".")
            self.node(nid, kind="input", role="disturbance", system=self._system(key), label=f"d {name}",
                      fn={"sym": "d", "sub": name}, math=[sym("d", name)], says=says, part=key,
                      rows=[["signal", f"d_{name}"], ["description", getattr(t, "description", "")], ["now", self.now(key)]])
            self.produce(key, nid)
            return self.prod[key]
        return None

    def wire(self, key: str, dst: str, dport: str, sign: str | None = None) -> None:
        src = self.source(key)
        if src is None:
            return
        var = key.split(".")[0] in ("stock", "flow", "auxiliary")
        note = self.sensor_note(key) if var and not self.sensor_dynamics(key) and dst.startswith(("sum:", "blk:")) else ""
        # a process output read back by a comparator or a controller: the feedback path, drawn beneath
        back = dst.startswith(("sum:", "blk:")) and (key.startswith("meas.") or (var and not self.is_input(key)))
        self.wires.append({"key": key, "source": src[0], "sourcePort": src[1], "target": dst, "targetPort": dport,
                           **({"sign": sign} if sign else {}), **({"note": note} if note else {}),
                           **({"feedback": True} if back else {})})

    def now(self, var: str) -> str:
        kind, name = var.split(".", 1)
        if kind == "flow":
            r = (self.snap.get("flows") or {}).get(name, {}).get("rate")
            return rates.text(r, "", rates.override_of(self.s, name)) if r is not None else ""
        v = (self.snap.get("stocks") or {}).get(name, {}).get("value")
        return _num(v) if v is not None else ""

    # -- building it

    def build(self) -> None:
        s = self.s
        # the blocks of the control system, each once
        for n in self.control:
            self.node(f"blk:{n}", kind="block", system=s.blocks[n].system, label=n, tier=self.tier(n), **self.block_fn(n),
                      **({"alarm": "raised"} if n in (self.snap.get("alarms") or {}) else {}))
        for n in self.control:
            b = s.blocks[n]
            for refs in b.outputs.values():
                for t in refs:
                    if t.kind == "flow" and t.name in self.knob_flow:
                        key = self.knob_flow[t.name]
                    elif t.kind in ("flow", "auxiliary"):
                        key = f"{t.kind}.{t.name}"
                    elif t.kind == "block":
                        key = f"cmd.{n}.{t.name}"
                    elif t.kind == "goal":
                        key = f"goal.{t.name}.r"
                    else:
                        continue
                    self.produce(key, f"blk:{n}", key)
            for c, d in sorted(self.commands):
                if c == n:
                    self.produce(f"cmd.{c}.{d}", f"blk:{n}", f"cmd.{c}.{d}")
        # summing junctions: e = r − y_m, for goals whose error a block reads, and for goals nothing serves
        served = {g for g in s.goals if s.loop(g).controllers or s.loop(g).actuators}
        for g in s.goals.values():
            if g.name in self.error_read or (g.name not in served and g.name not in self.reads_y):
                nid = f"sum:{g.name}"
                ym = sym("y", f"m,{g.of.name}") if self.meas_key(f"{g.of.kind}.{g.of.name}").startswith("meas.") else \
                    sym("y", g.of.name)
                self.node(nid, kind="sum", role="comparator", system=self.comparator_system(g), label=f"Σ {g.name}",
                          loops=[g.name], math=[eq(sym("e", g.name), row(sym("r", g.name), mo("−"), ym))],
                          says=f"compares the reference of {g.name} with what is measured: the error e = r − y_m" +
                               ("" if g.name in served else ". Nothing acts on it: missing feedback") + ".")
                self.produce(f"goal.{g.name}.e", nid, "e")
        # the processes, and the sensors and outputs on them
        self.processes()
        # inputs, wired
        for n in self.control:
            nid = f"blk:{n}"
            for _, key in self.reads[n]:
                if key.startswith("goal.") and key.endswith(".e") and f"sum:{key.split('.')[1]}" not in self.nodes:
                    continue
                self.need(key)
                self.wire(key, nid, self.port(nid, "in", key))
            for gname in sorted(g for g, readers in self.reads_y.items() if n in readers and g not in self.error_read):
                key = f"goal.{gname}.r"                                  # it reads y itself: its setpoint beside it
                self.wire(key, nid, self.port(nid, "in", key))
            k = self.setting_of.get(n)
            if k:                                                        # its setting, moved by others too
                for f in s.flows_of(k.split(".", 1)[1]):
                    fk = f"flow.{f.name}"
                    if self.knob_flow.get(f.name) == k:
                        continue
                    sign = "+" if f.target == k.split(".", 1)[1] else "−"
                    self.wire(fk, nid, self.port(nid, "in", fk, sign=sign), sign)
        for g in s.goals.values():
            nid = f"sum:{g.name}"
            if nid not in self.nodes:
                continue
            self.wire(f"goal.{g.name}.r", nid, self.port(nid, "in", "r", "W", "+"), "+")
            gv = f"{g.of.kind}.{g.of.name}"
            key = self.meas_key(gv)
            self.need(key)
            self.wire(key, nid, self.port(nid, "in", "y", "S", "−"), "−")
        # what each goal holds, out to the right: the outputs the control system is for
        for gv, goals in self.goalvars.items():
            if gv in self.prod or self.source(gv):
                g = self.s.goals[goals[0]]
                nid = f"out:{gv}"
                self.node(nid, kind="output", role="output", system=g.system, label=f"y {gv.split('.', 1)[1]}",
                          fn={"sym": "y", "sub": gv.split(".", 1)[1]}, loops=goals, math=[sym("y", gv.split(".", 1)[1])],
                          says=f"an output the control system is for: {' and '.join(goals)} hold{'s' if len(goals) == 1 else ''} "
                               f"y_{gv.split('.', 1)[1]}.", part=gv,
                          rows=[["holds", ", ".join(f"{x}: {_hold(self.s.goals[x])}" for x in goals)], ["now", self.now(gv)]])
                self.wire(gv, nid, self.port(nid, "in", gv))
        self.cascades()
        self.buses()
        self.mark_loops()
        for n in self.control:
            self.one_input(f"blk:{n}")

    def one_input(self, nid: str) -> None:
        """A transfer-function block has one input, and a discrete one meets the continuous world through a
        sampler and a hold: e → (T) → C(z) → ZOH → Σ → the process, the block's other inputs (what else moves
        its setting) entering at that Σ with their signs: u = ZOH(C(z) e) ± the rest."""
        n = self.nodes[nid]
        fn = n.get("fn") or {}
        if not fn.get("sym") or fn.get("name"):
            return                                     # a nonlinear block: no transfer function, any inputs
        discrete = fn.get("arg") == "z"
        ins = [w for w in self.wires if w["target"] == nid]
        outs = [w for w in self.wires if w["source"] == nid]
        if len(ins) < 2 and not discrete:
            return
        first = next((w for w in ins if w["key"].startswith("goal.") and w["key"].endswith(".e")), ins[0] if ins else None)
        extra = [w for w in ins if w is not first]
        name = nid.split(":", 1)[1]
        system, loops = n.get("system"), list(n.get("loops", []))
        T = self.s.blocks[name].every if name in self.s.blocks else None
        added: list[str] = []
        T_text = _dur(T) or "its period"
        if discrete and first is not None:                     # the sampler: the continuous error read every T
            sid = f"smp:{name}"
            sg = self.signal(first["key"])
            self.node(sid, kind="sampler", role="sampler", system=system, label="T", loops=loops,
                      fn={"sym": None, "T": T_text},
                      says=f"a sampler: {name} reads {sg['sym']}_{sg['sub']} once every {T_text}, so a continuous signal "
                           "becomes a sequence e_k = e(kT).",
                      math=[eq(["msub", mi("e"), mi("k")], row(mi("e"), mo("("), mi("k"), mi("T"), mo(")"))),
                            eq(mi("T"), mt(T_text))], rows=[["samples", f"{sg['sym']}_{sg['sub']}"], ["period", T_text]])
            self.port(sid, "in", "x")
            first["target"], first["targetPort"] = sid, f"{sid}|in|x"
            self.produce(f"samp:{name}", sid, "x[k]")
            self.sig[f"samp:{name}"] = {"key": f"samp:{name}", "sym": sg["sym"], "sub": "k", "what": "sampled"}
            into = nid
            db = n.get("deadband")
            if db:                                             # its dead band: a nonlinearity before the linear law
                did = f"dz:{name}"
                self.node(did, kind="block", role="deadband", system=system, label="dead band", loops=loops,
                          fn={"name": "dead band", "sketch": "deadzone", "kind": "dead zone", "linear": False},
                          says=f"a dead zone: {name} does not step while |e| ≤ {_num(db)}; outside it, the error passes on. "
                               "Not linear: left out of the loop's margins, and said beside them.",
                          math=[eq(["msub", mi("ẽ"), mi("k")], row(mt(f"0 when |e_k| ≤ {_num(db)}, else e_k")))],
                          rows=[["dead band", f"±{_num(db)} of error"], ["of", name]])
                self.wires.append({"key": f"samp:{name}", "source": sid, "sourcePort": self.prod[f"samp:{name}"][1],
                                   "target": did, "targetPort": self.port(did, "in", "e[k]")})
                self.produce(f"dz:{name}", did, "ẽ[k]")
                self.sig[f"dz:{name}"] = {"key": f"dz:{name}", "sym": "ẽ", "sub": "k", "what": "sampled"}
                self.wires.append({"key": f"dz:{name}", "source": did, "sourcePort": self.prod[f"dz:{name}"][1],
                                   "target": nid, "targetPort": self.port(nid, "in", "e[k]")})
                added.append(did)
            else:
                self.wires.append({"key": f"samp:{name}", "source": sid, "sourcePort": self.prod[f"samp:{name}"][1],
                                   "target": into, "targetPort": self.port(into, "in", "e[k]")})
            added.append(sid)
        ports = list(dict.fromkeys(w["sourcePort"] for w in outs))
        knob = self.setting_of.get(name)
        main = next((p for p in ports if knob and p == f"{nid}|out|{knob}"), ports[0] if ports else None)
        for port in ports:
            wires = [w for w in outs if w["sourcePort"] == port]
            key = wires[0]["key"]
            at = (nid, port)
            if discrete:                                       # the hold: the sequence held between samples
                hid = f"zoh:{name}" if port == main else f"zoh:{name}:{key}"
                self.node(hid, kind="block", role="hold", system=system, label="ZOH", loops=loops,
                          fn={"name": "ZOH", "sketch": "zoh", "kind": "zero-order hold", "linear": True},
                          says=f"a zero-order hold: it keeps each value {name} puts out for one period, {T_text}, so the "
                               "continuous process sees a staircase.",
                          math=[eq(["msub", mi("G"), mt("h0")], row(mi("s")), frac(row(mn(1), mo("−"), ["msup", mi("e"),
                                row(mo("−"), mi("s"), mi("T"))]), mi("s"))),
                                eq(row(mi("u"), mo("("), mi("t"), mo(")")), ["msub", mi("u"), mi("k")]),
                                mt(f"for kT ≤ t < (k + 1)T, T = {T_text}")],
                          rows=[["holds", f"the output of {name}"], ["period", T_text]])
                ck = f"ctl:{name}" if port == main else f"ctl:{name}:{key}"
                self.sig[ck] = {"key": ck, "sym": "u", "sub": "k", "what": "sampled"}
                self.wires.append({"key": ck, "source": nid, "sourcePort": port, "target": hid,
                                   "targetPort": self.port(hid, "in", "u[k]")})
                hk = f"held:{name}" if port == main else f"held:{name}:{key}"
                self.produce(hk, hid, "u")
                self.sig[hk] = {"key": hk, "sym": "u", "sub": name, "what": "control"}
                at = self.prod[hk]
                added.append(hid)
            if port == main and extra:                          # the block's other inputs, summed after it
                jid = f"jsum:{name}"
                self.node(jid, kind="sum", role="junction", system=system, label=f"Σ {name}", loops=loops,
                          math=[eq(sym(self.signal(key)["sym"], key.split(".", 1)[1]),
                                   row(sym("u", name), *[x for w in extra for x in (mo(w.get("sign") or "+"),
                                       sym(self.signal(w["key"])["sym"], w["key"].split(".", 1)[1]))]))],
                          says=f"adds to what {name} puts out the other inputs that move "
                               f"{key.split('.', 1)[1]}, each with its sign.")
                hk = f"held:{name}" if discrete else f"ctl:{name}"
                if not discrete:
                    self.sig[hk] = {"key": hk, "sym": "u", "sub": name, "what": "control"}
                self.wires.append({"key": hk, "source": at[0], "sourcePort": at[1], "target": jid,
                                   "targetPort": self.port(jid, "in", "u", "W", "+"), "sign": "+"})
                for i, w in enumerate(extra):
                    sign = w.get("sign") or "+"
                    w["target"], w["targetPort"] = jid, self.port(jid, "in", w["key"], "N" if i % 2 == 0 else "S", sign)
                    w["sign"] = sign
                self.produce(f"jsum:{name}", jid, "y")
                at = self.prod[f"jsum:{name}"]
                self.sig[f"jsum:{name}"] = self.signal(key) | {"key": f"jsum:{name}"}
                added.append(jid)
            if at != (nid, port):
                for w in wires:
                    w["source"], w["sourcePort"] = at
                for k, v in list(self.prod.items()):
                    if v == (nid, port):
                        self.prod[k] = at
        n["ins"] = [p for p in n["ins"] if any(w["targetPort"] == p["id"] for w in self.wires)]
        n["outs"] = [p for p in n["outs"] if any(w["sourcePort"] == p["id"] for w in self.wires)]
        for f in self.frames:                                    # with the block, in its cascade's frame
            if nid in f["members"]:
                f["members"] += added

    def loop_period(self, var: str) -> float:
        """The period a sensor's own is weighed against: the shortest period of the blocks that read it (its
        reading, or the error of a goal on it), else the identified process's time constant and dead time,
        else ten minutes (a person or an AI agent answering what it is given)."""
        goals = [g for g in self.s.goals.values() if f"{g.of.kind}.{g.of.name}" == var]
        readers = {n for k in (var, *(f"goal.{g.name}.e" for g in goals)) for n in self.readers_of.get(k, ())}
        ts = [self.s.blocks[n].every for n in self.reads if n in readers and self.s.blocks[n].every]
        if ts:
            return min(ts)
        for g in goals:
            pr = g.process or {}
            if pr.get("tau") or pr.get("theta"):
                return float(pr.get("tau") or 0) + float(pr.get("theta") or 0)
        return 600.0

    def need(self, key: str) -> None:
        """A measured signal's sensor, made when first read: a block on the feedback path, labelled with what it
        reads and how often (``sensing.reads``). H(s) when it has dynamics of its own (a rate over a window, a
        moving average); a delay e^(−sT), a sampler, when it polls (``slight``, drawn muted, when T is under a
        tenth of the loop's period, which its rows give as a ratio); else H = 1.
        A collector that turns an outside system into the items it counts is drawn in front of it."""
        if not key.startswith("meas.") or key in self.prod:
            return
        _, kind, name, sname = key.split(".", 3)
        var = f"{kind}.{name}"
        nid = f"sen:{var}"
        if nid not in self.nodes:
            t = self.s.measured(kind)[name]
            sensors = [x for x in t.sensors.values() if x.measured or x.manual]
            dyn = self.sensor_dynamics(var)
            ex = next((x for x in sensors if x.changes or x.items), sensors[0]) if dyn else \
                next((x for x in sensors if x.name == sname), sensors[0])
            cols = [c for c in self.collectors.get((ex.items or {}).get("kind") or "", []) if c is not ex]
            reads = sensing.reads(self.s, ex) + (f" (and {len(sensors) - 1} more)" if len(sensors) > 1 else "")
            period = 0.0 if ex.manual or ex.cron else float(ex.every or 0)
            period += max((float(c.every or 0) for c in cols), default=0.0)
            loop_T = self.loop_period(var)
            sampled = not dyn and period > 0                 # it polls: a sampler, whatever its period
            slight = sampled and period < loop_T / 10        # T small against the loop's: the sampler drawn muted
            Tw = sensing.every_words(period)
            rows = [["measures", name], ["reads", reads], ["command", sensing.command(self.s, ex)],
                    ["sensors", ", ".join(x.name for x in sensors)],
                    ["collected by", ", ".join(sensing.reads(self.s, c) for c in cols)], ["now", self.now(var)]]
            if sampled:
                rows.insert(2, ["T / loop", f"{Tw} / {sensing.every_words(loop_T)} = {period / loop_T:.2g}"])
            ym = eq(sym("y", f"m,{name}"), row(sym("H", name, "s" if dyn or sampled else None), sym("y", name)))
            if dyn:
                tau = (ex.changes or ex.items or {}).get("over") or 3600.0
                how = (f"the rate of {name} from its integrator's successive readings, over {_dur(tau)}" if ex.changes
                       else f"the rate of {name}, counted from the record over {_dur(tau)}")
                fn = {"sym": "H", "sub": name, "arg": "s", "expr": f"avg {sensing.every_words(tau)}", "linear": True}
                math = [eq(sym("H", name, "s"), frac(row(mn(1), mo("−"), ["msup", mi("e"), row(mo("−"), mi("s"), mi("τ"))]),
                                                     row(mi("s"), mi("τ")))),
                        row(mt("a moving average over "), mi("τ"), mo("="), mt(_dur(tau))), ym]
                says = (f"the sensor on y_{name}: {how}. A window average lags what it measures by about τ/2 = "
                        f"{_dur(tau / 2)}.")
            elif sampled:
                fn = {"sym": "H", "sub": name, "arg": "s", "expr": "e^(−sT)", "T": Tw, "sampled": True, "linear": True,
                      "slight": slight}
                math = [eq(sym("H", name, "s"), ["msup", mi("e"), row(mo("−"), mi("s"), mi("T"))]), eq(mi("T"), mt(Tw)), ym]
                says = (f"the sensor on y_{name}: it reads {reads}. It polls every {Tw}"
                        + (" (with its collector)" if cols else "") + (
                            f", short against the loop's own period ({sensing.every_words(loop_T)}): its delay of up to T "
                            "is slight, near H = 1, so its sampler is drawn muted." if slight else
                            f", a tenth or more of the loop's own period ({sensing.every_words(loop_T)}): a reading is up "
                            "to T old, T/2 on average, so the feedback path is drawn as a sampler, a delay of up to T."))
            else:
                fn = {"sym": "H", "sub": name, "arg": None, "expr": "1", "linear": True,
                      **({"every": sensing.every_words(ex.every)} if ex.every and not (ex.manual or ex.cron) else {})}
                math = [eq(sym("H", name), mn(1)), eq(sym("y", f"m,{name}"), sym("y", name))]
                says = (f"the sensor on y_{name}: it reads {reads}. What it reads goes back to the loop as it is (H = 1): "
                        "the model gives it no dynamics.")
            fn["reads"] = reads
            self.node(nid, kind="block", role="sensor", system=self._system(var), label=name, fn=fn, math=math,
                      says=says, part=var, rows=rows)
            if cols:
                for c in cols:
                    ck = self.collector(c, var)
                    self.wires.append({"key": ck, "source": self.prod[ck][0], "sourcePort": self.prod[ck][1],
                                       "target": nid, "targetPort": self.port(nid, "in", ck, "E")})
            else:
                self.wire(var, nid, self.port(nid, "in", var, "E"))
        self.produce(key, nid, key, "W")

    def buses(self) -> None:
        """A collector whose records many counts read (three or more): its one signal goes into a bus, a bar with
        a port for each count (Simulink's bus selector), so that its lines leave it apart, one to each sensor."""
        for cid in [n for n in self.nodes if n.startswith("col:")]:
            outs = [w for w in self.wires if w["source"] == cid]
            if len(outs) < 3:
                continue
            bid, ck = f"bus:{cid[4:]}", outs[0]["key"]
            n = self.nodes[cid]
            self.node(bid, kind="demux", role="bus", system=n.get("system"), n=len(outs), label="bus",
                      says=f"a bus: what {n['label']} records, taken to each of the {len(outs)} counts that read it.")
            for w in sorted(outs, key=lambda w: w["target"]):
                key = f"{ck}~{w['target']}"
                self.sig[key] = {**self.sig[ck], "key": key}
                w["key"], w["source"], w["sourcePort"] = key, bid, self.port(bid, "out", key, "W")
            self.wires.append({"key": ck, "source": cid, "sourcePort": self.prod[ck][1], "target": bid,
                               "targetPort": self.port(bid, "in", ck, "E")})

    def collector(self, x, var: str) -> str:
        """The block a collector is: it polls an outside system and records what it saw as items, which a
        sensor counts. Drawn once, however many counts read its kind, with one input: the stock its flow brings
        the items into (the outside system it watches, as the model has it). Its signal's key."""
        cid = f"col:{x.of.name}.{x.name}"
        ck = f"rec:{x.of.name}.{x.name}"
        kinds = sorted(k for k, cs in self.collectors.items() if any(c is x for c in cs))
        if cid not in self.nodes:
            title = x.description if x.description and len(x.description) <= 40 else (
                sensing.what(self.s, x) if x.query else sensing.short(sensing._command(sensing.command(self.s, x))) or x.name)
            what = f"records {' and '.join(kinds)} items" + (f", {sensing.how_often(x)}" if sensing.how_often(x) else "")
            self.node(cid, kind="block", role="collector", system=self.s.owner(x.of), label=title,
                      fn={"name": title, "kind": "collector", "reads": what, "linear": False},
                      says=f"a collector: it polls an outside system and records what it saw as events about "
                           f"{' and '.join(kinds)} items ({sensing.reads(self.s, x)}), which the sensors on the feedback "
                           "path count. A count is only as fresh as it is. It is the sensor on the flow "
                           f"{x.of.name}, which brings the items in; taken to be their collector because of that.",
                      math=[mt(f"records {' and '.join(kinds)} items as events, {sensing.how_often(x) or 'when run'}"),
                            mt("an instrument: it never acts")],
                      rows=[["sensor", f"{x.of.name}.{x.name}"], ["reads", sensing.reads(self.s, x)],
                            ["records", ", ".join(kinds)], ["description", x.description]],
                      part=f"{x.of.kind}.{x.of.name}")
            self.produce(ck, cid, "items", "W")               # on the feedback path: its records go back, leftwards, to the counts
            self.sig[ck] = {"key": ck, "sym": "", "sub": "", "what": "record"}
            # what it watches: the outside system, drawn as the stock its flow brings the items into (one input,
            # however many counts read what it records: their lines leave it as one signal, taken off for each)
            f = self.s.flows.get(x.of.name) if x.of.kind == "flow" else None
            watched = f"stock.{f.target}" if f is not None and f.target and self.source(f"stock.{f.target}") else var
            self.wire(watched, cid, self.port(cid, "in", watched, "E"))
        return ck

    def processes(self) -> None:
        internal = lambda v: not self.is_input(v)                            # noqa: E731
        outs = set()
        for gv in self.goalvars:
            if internal(gv) and gv.split(".")[0] != "goal":
                outs.add(gv)
        for rs in self.reads.values():
            for _, k in rs:
                if k.startswith("meas."):
                    k = ".".join(k.split(".")[1:3])
                if not k.startswith(("goal.", "cmd.")) and internal(k):
                    outs.add(k)
        info: dict[str, tuple[set, set, set]] = {}

        def walk(o: str) -> bool:
            seen, ins, deps, grew = set(), set(), set(), False
            todo = [o]
            while todo:
                x = todo.pop()
                for c, _ in self.causes(x):
                    if not internal(c):
                        ins.add(c)
                    elif c in outs and c != o:
                        deps.add(c)
                    elif c != o and self._system(c) != self._system(o):
                        outs.add(c)
                        deps.add(c)
                        grew = True
                    elif c not in seen and c != o:
                        seen.add(c)
                        todo.append(c)
            info[o] = (seen, ins, deps)
            return grew
        while True:
            if not any([walk(o) for o in sorted(outs)]):
                break
        pure = {o for o in outs if o.startswith("stock.") and not info[o][0] and not info[o][2]}
        rest = sorted(outs - pure)
        parent = {o: o for o in rest}

        def root(x):
            while parent[x] != x:
                x = parent[x]
            return x
        for i, a in enumerate(rest):
            for b in rest[i + 1:]:
                if self._system(a) != self._system(b):
                    continue
                sa, ia, da = info[a]
                sb, ib, db = info[b]
                if sa & sb or ia & ib or a in db or b in da:
                    parent[root(a)] = root(b)
        groups: dict[str, list[str]] = {}
        for o in rest:
            groups.setdefault(root(o), []).append(o)
        for o in sorted(pure):
            self.integrator(o)
        used = set()
        for members in sorted(groups.values()):
            members = sorted(members)
            shared = any(info[a][0] & info[b][0] for i, a in enumerate(members) for b in members[i + 1:])
            ins = sorted({x for o in members for x in info[o][1] | info[o][2]} - set(members))
            apart = sum(len(info[o][1] | info[o][2]) for o in members)
            if len(members) > 1 and (shared or apart > len(ins) + len(members)):
                sysname = self._system(members[0]) or "plant"
                pid = sysname if sysname not in used else f"{sysname}-{len(used)}"
                used.add(pid)
                self.mimo(pid, members, ins, info, shared)
            else:
                for o in members:
                    self.siso(o, sorted(info[o][1] | info[o][2]), info)

    def integrator(self, o: str) -> None:
        """A stock whose flows are all inputs: 1/s, its flows summed in front of it."""
        name = o.split(".", 1)[1]
        st = self.s.stocks[name]
        nid = f"proc:{o}"
        flows = self.causes(o)
        terms = [(self.signal(f)["sym"], f.split(".", 1)[1], sg) for f, sg in flows]
        u = " ".join(("+ " if sg > 0 else "− ") + f"{sy}_{nm}" for sy, nm, sg in terms).removeprefix("+ ")
        self.node(nid, kind="block", role="process", system=st.system, label=name,
                  fn={"sym": "P", "sub": name, "arg": "s", "expr": "1/s", "linear": True},
                  math=[eq(sym("P", name, "s"), frac(mn(1), mi("s"))),
                        eq(sym("y", name), row(mo("∫"), mo("("), *_signed(terms), mo(")"), mi("d"), mi("t")) if flows
                           else mt("no flow modelled"))],
                  says=f"integrator: the sum of its inputs over time, y_{name} = ∫({u}) dt." if flows else
                  f"integrator with no inputs: no flow into or out of {name} is modelled, so the model holds it still"
                  + ("; whatever moves it is seen only in its readings." if st.sensors else "."),
                  part=o, rows=[["output", f"y_{name}"], ["unit", st.unit], ["now", self.now(o)], ["inputs", ", ".join(
                      ("+" if sg > 0 else "−") + f.split(".", 1)[1] for f, sg in flows)], ["description", st.description]])
        self.produce(o, nid, o)
        if not flows:                                  # no flow modelled: it holds its value, nothing to sum
            return
        if len(flows) == 1 and flows[0][1] > 0:
            self.wire(flows[0][0], nid, self.port(nid, "in", flows[0][0]))
            return
        sid = f"psum:{o}"
        self.node(sid, kind="sum", role="process-sum", system=st.system, label=f"Σ {name}",
                  math=[eq(row(mi("q"), mt(" into "), mt(name)),
                           row(*[x for f, sg in flows for x in (mo("+" if sg > 0 else "−"), sym("q", f.split('.',
                                   1)[1]))][(1 if flows[0][1] > 0 else 0):]))],
                  says=f"sums the inputs of the integrator P_{name}, each with its sign.")
        self.produce(f"psum:{o}", sid, "q")
        self.sig[f"psum:{o}"] = {"key": f"psum:{o}", "sym": "", "sub": "", "what": "net flow"}
        self.wire(f"psum:{o}", nid, self.port(nid, "in", "q"))
        # the block's own action into its side, disturbances from above (and below, when there are many)
        ctl = [(f, sg) for f, sg in flows if f in self.moved]
        dist = [(f, sg) for f, sg in flows if f not in self.moved]
        first = ctl[0] if ctl else dist.pop(0)
        if ctl:
            ctl = ctl[1:]
        sides = [first, *ctl, *dist]
        for i, (f, sg) in enumerate(sides):
            side = "W" if i == 0 else "N" if i % 2 else "S"
            sign = "+" if sg > 0 else "−"
            self.wire(f, sid, self.port(sid, "in", f, side, sign), sign)

    def siso(self, o: str, ins: list[str], info) -> None:
        kind, name = o.split(".", 1)
        flows = self.causes(o)
        dist = [(f, sg) for f, sg in flows if self.disturbance(f)]
        if kind == "stock" and dist:                   # what is known drawn as known: d at its own junction, then 1/s
            return self.split_stock(o, [k for k in ins if not any(k == f for f, _ in dist)], flows, dist)
        nid = f"proc:{o}"
        t = self.s.measured(kind)[name]
        static = kind == "auxiliary" or (kind == "flow")
        how = self.structure(o)
        u = row(*[x for i, k in enumerate(ins) for x in ((mo(",") if i else None), sym(self.signal(k)["sym"], k.split(".", 1)[1])) if x])
        self.node(nid, kind="block", role="process", system=t.system, label=name,
                  fn={"sym": "P", "sub": name, "arg": None if static else "s", "expr": "static" if static else "not identified",
                      "linear": False if static else None},
                  math=[eq(sym("y", name), row(sym("P", name, None if static else "s"), mo("("), u, mo(")"))),
                        mt("not identified: " + how)],
                  says=f"the process from what reaches {name} to {name}: {how}. Its dynamics are not identified.", part=o,
                  rows=[["output", f"y_{name}"], ["now", self.now(o)], ["inputs", ", ".join(k.split(".", 1)[1] for k in ins)],
                        ["description", t.description]])
        self.produce(o, nid, o)
        for k in ins:
            self.wire(k, nid, self.port(nid, "in", k))

    def split_stock(self, o: str, ins: list[str], flows, dist) -> None:
        """A stock some of whose flows follow other things (not identified, G) and some are disturbances:
        G(s), then the junction where the disturbances enter, then the integrator."""
        name = o.split(".", 1)[1]
        st = self.s.stocks[name]
        nid, gid, sid = f"proc:{o}", f"gen:{o}", f"psum:{o}"
        driven = [f.split(".", 1)[1] for f, _ in flows if not self.disturbance(f)]
        self.node(nid, kind="block", role="process", system=st.system, label=name,
                  fn={"sym": "P", "sub": name, "arg": "s", "expr": "1/s", "linear": True},
                  math=[eq(sym("P", name, "s"), frac(mn(1), mi("s")))],
                  says=f"integrator: the sum of its inputs over time, y_{name} = ∫ q dt.", part=o,
                  rows=[["output", f"y_{name}"], ["unit", st.unit], ["now", self.now(o)], ["description", st.description]])
        self.produce(o, nid, o)
        self.node(sid, kind="sum", role="process-sum", system=st.system, label=f"Σ {name}",
                  math=[mt(f"the input of P_{name}: what G_{name} puts out, and the disturbances, each with its sign")],
                  says=f"sums the inputs of the integrator P_{name}: {', '.join(driven)} (through G) and the disturbances, "
                       "each with its sign.")
        self.produce(f"psum:{o}", sid, "q")
        self.sig[f"psum:{o}"] = {"key": f"psum:{o}", "sym": "", "sub": "", "what": "net flow"}
        self.wire(f"psum:{o}", nid, self.port(nid, "in", "q"))
        if driven:
            u = row(*[x for i, k in enumerate(ins) for x in ((mo(",") if i else None), sym(self.signal(k)["sym"], k.split(".",
                    1)[1])) if x])
            self.node(gid, kind="block", role="process", system=st.system, label=f"{name} flows",
                      fn={"sym": "G", "sub": name, "arg": "s", "expr": "not identified", "linear": None},
                      math=[eq(sym("q", ", ".join(driven)), row(sym("G", name, "s"), mo("("), u, mo(")"))),
                            mt(f"not identified: how {', '.join(driven)} follow{'s' if len(driven) == 1 else ''} "
                               f"{'its' if len(driven) == 1 else 'their'} inputs")],
                      says=f"the inputs of P_{name} that follow other signals ({', '.join(driven)}): how they follow is not "
                           "identified.",
                      rows=[["outputs", ", ".join(driven)], ["inputs", ", ".join(k.split(".", 1)[1] for k in ins)]])
            for k in ins:
                self.wire(k, gid, self.port(gid, "in", k))
            self.produce(f"gen:{o}", gid, "q")
            self.sig[f"gen:{o}"] = {"key": f"gen:{o}", "sym": "q", "sub": name, "what": "flow"}
            self.wire(f"gen:{o}", sid, self.port(sid, "in", "q", "W", "+"), "+")
        for i, (f, sg) in enumerate(dist):
            side = "W" if not driven and i == 0 else "N" if i % 2 == 0 else "S"
            sign = "+" if sg > 0 else "−"
            self.wire(f, sid, self.port(sid, "in", f, side, sign), sign)

    def structure(self, o: str) -> str:
        kind, name = o.split(".", 1)
        if kind == "auxiliary":
            return "no memory: a static map of its inputs"
        if kind == "flow":
            return "a rate that follows its inputs"
        drv = [c.split(".", 1)[1] for c, _ in self.causes(o)]
        return f"an integrator of {', '.join(drv)}, which follow their own inputs: (1/s)·G(s), G not identified"

    def mimo(self, pid: str, members: list[str], ins: list[str], info, shared: bool) -> None:
        """Outputs that share their inputs: one block, P(s), with vectors in and out."""
        nid = f"proc:{pid}"
        system = self._system(members[0])
        pattern = self.zero_pattern(members, ins, info)
        rowsm = []
        for o in members:
            cells = []
            for i in ins:
                signs = pattern[o].get(i)
                p = sym("P", f"{o.split('.', 1)[1]},{i.split('.', 1)[1]}")
                cells.append(["mtd", mn(0) if not signs else row(mo("+" if signs == {1} else "−"), p)
                              if signs in ({1}, {-1}) else p])
            rowsm.append(["mtr", *cells])
        why = ("its outputs share what is inside it" if shared else
               f"its {len(members)} outputs share their {len(ins)} inputs")
        def vec(ks):
            return ["mrow", mo("["), ["mtable", *[["mtr", ["mtd", sym(self.signal(k)["sym"], k.split(".", 1)[1])]] for k in ks]], mo("]")]
        self.node(nid, kind="block", role="process", system=system, label=pid, mimo=[len(members), len(ins)],
                  inside=sorted(set(members).union(*(info[o][0] for o in members))),      # (correspond.py: what it holds)
                  fn={"sym": "P", "sub": pid, "arg": "s", "expr": f"{len(members)}×{len(ins)}, not identified", "linear": None,
                          "bold": True},
                  math=[eq(sym("y", None, None, True), row(sym("P", None, "s", True), sym("u", None, None, True))),
                        eq(vec(members), row(["mrow", mo("["), ["mtable", *rowsm], mo("]")], vec(ins))),
                        mt(f"each entry not identified; 0 where no path inside {system or 'it'} leads from the input to the "
                           "output (a structural zero); a sign where every path has that sign")],
                  says=f"the process inside {system or 'the model'}, multi-input multi-output: {why}. "
                       "Its dynamics are not identified; the matrix says which input reaches which output.",
                  pattern={o: {i: sorted(v) for i, v in pattern[o].items()} for o in members},
                  rows=[["outputs", ", ".join(o.split(".", 1)[1] for o in members)],
                        ["inputs", ", ".join(i.split(".", 1)[1] for i in ins)], ["why one block", why]])
        mux = dmx = None
        if len(ins) > 1:
            mux = f"mux:{pid}"
            self.node(mux, kind="mux", system=system, n=len(ins), label="mux",
                      says=f"gathers the {len(ins)} inputs of P_{pid} into one vector u.")
            for k in ins:
                self.wire(k, mux, self.port(mux, "in", k))
            self.produce(f"vec-u:{pid}", mux, "u")
            self.sig[f"vec-u:{pid}"] = {"key": f"vec-u:{pid}", "sym": "u", "sub": pid, "what": "vector", "n": len(ins)}
            self.wire(f"vec-u:{pid}", nid, self.port(nid, "in", "u"))
        else:
            for k in ins:
                self.wire(k, nid, self.port(nid, "in", k))
        if len(members) > 1:
            dmx = f"demux:{pid}"
            self.node(dmx, kind="demux", system=system, n=len(members), label="demux",
                      says=f"splits the output vector y of P_{pid} into its {len(members)} signals.")
            self.produce(f"vec-y:{pid}", nid, "y")
            self.sig[f"vec-y:{pid}"] = {"key": f"vec-y:{pid}", "sym": "y", "sub": pid, "what": "vector", "n": len(members)}
            self.wire(f"vec-y:{pid}", dmx, self.port(dmx, "in", "y"))
            for o in members:
                self.produce(o, dmx, o)
        else:
            self.produce(members[0], nid, members[0])

    def zero_pattern(self, members: list[str], ins: list[str], info) -> dict[str, dict[str, set[int]]]:
        """Which input reaches which output of a MIMO process, by reachability through what is inside it (its
        outputs and the parts between them), with the sign of each path (0 where a link's sign is unknown):
        an entry is 0 only where no path leads from the input to the output."""
        inside = set(members).union(*(info[m][0] for m in members))
        cols = set(ins)
        out: dict[str, dict[str, set[int]]] = {}
        for o in members:
            found: dict[str, set[int]] = {}
            seen, todo = {(o, 1)}, [(o, 1)]
            while todo:
                x, sg = todo.pop()
                for c, pol in self.causes(x):
                    s2 = sg * (pol if pol in (1, -1) else 0)
                    if c in cols:
                        found.setdefault(c, set()).add(s2)
                    if c in inside and c != o and (c, s2) not in seen:
                        seen.add((c, s2))
                        todo.append((c, s2))
            out[o] = found
        return out

    def served(self) -> tuple[set[str], dict[str, list[str]]]:
        """Every goal's controllers, and the goals each block serves (as its controller or actuator), in the model's
        order: worked out once per diagram, not once per block (docs/proposals/scale.md, #10)."""
        got = self.__dict__.get("_served")
        if got is None:
            ctl: set[str] = set()
            serves: dict[str, list[str]] = {}
            for g in self.s.goals:
                lp = self.s.loop(g)
                ctl.update(lp.controllers)
                for b in dict.fromkeys([*lp.controllers, *lp.actuators]):
                    serves.setdefault(b, []).append(g)
            got = self._served = (ctl, serves)
        return got

    def tier(self, n: str) -> str | None:
        """Who fills the block, on the ladder (SPEC §9.5): its agent's kind, else a built-in's rung (a rule, or a judge's),
        else its type's; an external block with no agent says nothing of who it is."""
        b = self.s.blocks[n]
        a = self.s.agents.get(b.agent or "")
        if a is not None and a.kind:
            return a.kind
        if b.builtin:
            return b.builtin_rung
        return None if b.type == "external" else KIND_OF_TYPE.get(b.type)

    def pool_row(self, b) -> str:
        """``M``, or ``N now, at most M (stock.S)`` from the snapshot's level of S (``no reading`` without one)."""
        from .leases import poolnow
        if b.pool_now is None:
            return str(b.pool)
        v = (self.snap.get("stocks") or {}).get(b.pool_now.name, {}).get("value")
        return f"{'no reading' if poolnow.unread(v) else f'{poolnow.now(b, v)} now'}, at most {b.pool} ({b.pool_now})"

    def block_fn(self, n: str) -> dict:
        """A block's function: its symbol and what is known of it, and its definition as MathML."""
        s = self.s
        b = s.blocks[n]
        ctl, serves = self.served()
        role = "controller" if any(c == n for c, _ in self.commands) or any(t.kind == "goal" for t in b.targets()) or \
            self.setting_of.get(n) or n in ctl else "actuator"
        T = b.every
        when = f"every {_dur(T)}" if T else ("on a cron schedule" if b.cron else "when commanded" if b.machine else "on every reading")
        kind = {"ai": "AI agent", "program": "program", "person": "person", "external": "external"}.get(b.type, b.type)
        agent = s.agents.get(b.agent) if b.agent else None
        rows = [["block", f"{n} ({b.type}{', on ' + b.agent if b.agent else ''})"], ["runs", when],
                ["reads", ", ".join(r.name + (f".{r.port}" if r.port else "") for r in b.reads())],
                ["drives", ", ".join(t.name for t in b.targets())],
                ["serves", ", ".join(serves.get(n, ()))],
                ["description", b.description]]
        if agent and agent.kind:
            rows.insert(1, ["agent", f"{agent.name} ({agent.kind})"])
        if b.takes:                                        # its pool: written, or its stock's level now (SPEC §9.5)
            rows.insert(rows.index(["runs", when]) + 1, ["pool", self.pool_row(b)])
        knob = self.setting_of.get(n)
        reads_error = any(k.startswith("goal.") and k.endswith(".e") for _, k in self.reads.get(n, []))
        e = next((k.split(".")[1] for _, k in self.reads.get(n, []) if k.startswith("goal.") and k.endswith(".e")), None)
        # integral action only when its error is all it reads: a block that weighs several signals (a program reading
        # two errors and a measurement) is its own nonlinear map that happens to step a setting, not K_i T z/(z − 1)
        only_error = len(self.reads.get(n, [])) == 1
        if knob and reads_error and only_error and b.type not in ("onoff", "compare"):
            g = b.params.get("gain")                                      # the step per unit of error: K_i T
            gain = row(["msub", mi("K"), mi("i")], mo("\u2062"), mn(T) if T else mi("T")) if g is None else mn(g)
            uk, uk1, ek = ["msub", mi("u"), mi("k")], ["msub", mi("u"), row(mi("k"), mo("−"), mn(1))], ["msub", mi("e"), mi("k")]
            # velocity form, acting at once on the error it has just read: u_k = u_(k−1) + g e_k, g z/(z − 1)
            math = [eq(sym("C", n, "z"), frac(row(gain, mo("\u2062"), mi("z")), row(mi("z"), mo("−"), mn(1)))),
                    eq(uk, row(uk1, mo("+"), gain, mo("\u2062"), ek))]
            db, res, lim = b.params.get("deadband"), b.params.get("resolution"), b.params.get("limits")
            math.append(mt(f"integral action: it steps {knob.split('.', 1)[1]} (a setting that keeps its value between steps) "
                           f"by its goal's error e = e_{e}, sampled every {_dur(T) or 'T'}, at once from the error it has just "
                           "read; u is the setting. "
                           + ("K_i is not written (gain: on the block)." if g is None else
                              f"Its gain, written: {_num(g)} a step per unit of error"
                              + (f", K_i = {_num(round(float(g) / T, 4))} per second." if T else "."))
                           + (f" Not linear: no step while |e| ≤ {_num(db)} (its dead band, drawn before it)." if db else "")
                           + (f" The setting is rounded to steps of {_num(res)}." if res else "")
                           + (f" It is kept within [{_num(lim[0])}, {_num(lim[1])}]." if lim else "")))
            extra = ([["dead band", f"±{_num(db)} of error: no step inside it"]] if db else []) + \
                ([["resolution", f"{_num(res)} a step at least"]] if res else []) + \
                ([["limits", f"{_num(lim[0])} to {_num(lim[1])}"]] if lim else [])
            return {"role": role, "fn": {"sym": "C", "sub": n, "arg": "z",
                    "expr": "Kᵢ T z/(z − 1)" if g is None else f"{_num(g)} z/(z − 1)",
                                         "linear": True, "kind": kind},
                    "says": f"integral controller: {n} steps the setting {knob.split('.', 1)[1]} by the error, {when}.",
                    "math": math, "rows": rows + ([["gain", f"{_num(g)} a step per unit of error"]] if g is not None else []) + extra,
                    **({"deadband": db} if db else {})}
        law = (self.snap.get("laws") or {}).get(n) if b.type == "external" else None
        if b.type == "external" and b.law is not None:     # its law declared from the catalogue (§12d): an assumption
            from .control.laws import law as known
            from .spec.explain import law_words
            words = f"{b.law.kind}: {law_words(b)}"
            rows = rows + [["declared", f"{words} (an assumption until tested against the record)"]]
        if law:                                            # an existing controller, its law identified from the record (§12d)
            sk = {"onoff": "relay", "stepper": "zoh", "ratio": "saturation",       # ratio: as a declared HPA is drawn
                  "proportional": "saturation" if law["params"].get("hi") is not None
                  or law["params"].get("lo") is not None else None}.get(law["family"])
            return {"role": role, "identified": True, "says": f"an external controller, its law identified from the record: "
                    f"{law['said']}.", "fn": {"name": n, "sketch": sk, "kind": f"identified {law['family']}", "law": law["short"],
                                              "linear": law["family"] in ("proportional", "pi")},
                    "math": [eq(mi("u"), mt(law["short"])), mt(f"identified, external: {law['said']}")],
                    "rows": rows + [["identified", law["said"]]]}
        if b.type == "external" and b.law is not None:     # drawn as an identified law is, marked declared, not identified
            short, mark = known(b.law).short(), f"declared {b.law.kind}"
            return {"role": role, "declared": mark, "says": f"an external controller, its law declared, an assumption "
                    f"until tested against the record: {words}.", "fn": {"name": n, "kind": mark, "law": short,
                    "sketch": "saturation" if b.law.kind == "kubernetes-hpa" else "ideal-relay", "linear": False},
                    "math": [eq(mi("u"), mt(short)), mt(f"declared, external: {words}")], "rows": rows}
        if b.type == "proportional":
            k = b.params.get("gain")
            sat = [x for x in (b.params.get("min"), b.params.get("max")) if x is not None]
            return {"role": role, "fn": {"sym": "C", "sub": n, "arg": None, "expr": f"K_p = {_num(k)}", "linear": True,
                    "kind": "proportional"},
                    "says": f"proportional controller: u = K_p e{', clamped' if sat else ''}, on every reading.",
                    "math": [eq(sym("C", n), ["msub", mi("K"), mi("p")], mn(k)),
                             eq(mi("u"), row(["msub", mi("K"), mi("p")], mo("⁢"), mi("e")))]
                    + ([mt(f"clamped to [{_num(b.params.get('min'))}, {_num(b.params.get('max'))}]")] if sat else []), "rows": rows}
        if b.type == "delay":
            tau = b.params.get("delay")
            return {"role": role, "fn": {"sym": "D", "sub": n, "arg": "s", "expr": "e^(−sτ)", "linear": True, "kind": "delay"},
                    "says": f"a pure delay of {_dur(tau) if isinstance(tau, int | float) else tau}.",
                    "math": [eq(sym("D", n, "s"), ["msup", mi("e"), row(mo("−"), mi("s"), mi("τ"))]), eq(mi("τ"),
                            mt(str(tau)))], "rows": rows}
        # the rest are not linear: named, with a sketch of the nonlinearity where there is a standard one
        if b.type in ("onoff", "compare", "alarm", "timer"):
            g = s.goals.get(b.goal) if b.goal else None
            until = b.params.get("until")
            y = f"y_{g.of.name}" if g else "its input"
            on = f"while {y} {PAST.get(g.hold.op, '≠')} {_num(g.hold.value)}" if g else "while its input is past its threshold"
            back = _until(until) if until else (_hold(g) if g else "its threshold")
            off = f"once {y} is back to {back}"
            if g:
                rows.insert(0, ["threshold", f"{g.of.name} {_hold(g)}: on above it" if g.hold.op in ("<=", "<") else
                                f"{g.of.name} {_hold(g)}: on below it" if g.hold.op in (">=", ">") else
                                f"{g.of.name} {_hold(g)}: on away from it"])
            # on past its tolerance, or off only at its until: a band (hysteresis); on and off at one threshold: an ideal relay
            band = bool(until) and (not g or back != _hold(g)) or bool(g and g.tolerance)
            if g and band:
                rows.insert(1, ["releases at", f"{g.of.name} {back} (hysteresis)"])
            return {"role": role, "fn": {"sym": None, "sub": None, "name": n, "sketch": "relay" if band else "ideal-relay",
                    "kind": "relay" if b.type == "onoff" else b.type, "linear": False},
                    "says": f"an on-off controller ({'a relay with hysteresis' if band else 'an ideal relay'}): "
                            f"u = 1 {on}, u = 0 {off}.",
                    "math": [eq(mi("u"), row(mo("{"), ["mtable", {"columnalign": "left"},
                                                         ["mtr", ["mtd", mn(1)], ["mtd", mt(on)]],
                                                         ["mtr", ["mtd", mn(0)], ["mtd", mt(off)]]])),
                             mt(f"a static nonlinearity{' with memory' if band else ''}: no transfer function")], "rows": rows}
        if b.type == "limit":
            return {"role": role, "fn": {"name": n, "sketch": "saturation", "kind": "limit", "linear": False},
                    "says": "a saturation: its input, clamped.", "math": [eq(mi("u"), row(mt("sat"), mo("("), mi("x"),
                            mo(")")))], "rows": rows}
        if b.type in ("expr", "lookup", "select", "schedule", "counter"):
            what = {"expr": str(b.params.get("expr", "")), "lookup": "a table, linear between its points",
                    "select": f"the {b.params.get('pick', 'first')} of its inputs", "schedule": "a value by the clock (a table of times)",
                    "counter": "how many times its input became nonzero"}[b.type]
            return {"role": role, "fn": {"name": n, "sketch": "static", "kind": b.type, "linear": False},
                    "says": f"a static map: {what}.", "math": [eq(mi("u"), mt(what)),
                            mt("a static nonlinearity: no transfer function")], "rows": rows}
        sat = b.max is not None
        moves = ", ".join(t.name for t in b.targets())
        does = f"steps the setting {knob.split('.', 1)[1]}" if knob else f"drives {moves}" if moves else "acts"
        return {"role": role, "fn": {"name": n, "sketch": "saturation" if sat else None, "kind": kind, "linear": False,
                                     "max": b.max},
                "says": f"{'an' if kind[0].lower() in 'aeiou' else 'a'} {kind} ({when}): it {does}. "
                        "What it computes is its own: not a transfer function"
                        + (f"; u ∈ [0, {_num(b.max)}] per run" if sat else "") + ".",
                "math": [eq(sym("u", None), row(mi("f"), mo("("), mt("its inputs"), mo(")"))),
                         mt(f"not identified: {kind}, {when}" + (f"; u ∈ [0, {_num(b.max)}] per run" if sat else ""))], "rows": rows}

    def cascades(self) -> None:
        """A goal whose setpoint a block sets: its loop drawn nested, inside a frame of its own."""
        s = self.s
        serves: dict[str, set[str]] = {}
        for g in s.goals:
            lp = s.loop(g)
            for b in [*lp.controllers, *lp.actuators]:
                serves.setdefault(b, set()).add(g)
        for g in s.goals.values():
            src = self.prod.get(f"goal.{g.name}.r")
            if not src or not src[0].startswith("blk:"):
                continue
            lp = s.loop(g.name)
            members = [f"sum:{g.name}"] if f"sum:{g.name}" in self.nodes else []
            members += [f"blk:{b}" for b in dict.fromkeys([*lp.controllers, *lp.actuators]) if serves.get(b) == {g.name}
                        and f"blk:{b}" != src[0]]
            gv = f"{g.of.kind}.{g.of.name}"
            if f"sen:{gv}" in self.nodes:
                members.append(f"sen:{gv}")
            p = self.prod.get(gv)
            if p and p[0].startswith("proc:") and [w for w in self.wires if w["source"] == p[0]] and \
                    all(x["key"] == gv for x in self.wires if x["source"] == p[0]):
                members.append(p[0])
                if f"psum:{gv}" in self.nodes:
                    members.append(f"psum:{gv}")
            if len(members) < 2:
                continue
            self.frames.append({"id": f"casc:{g.name}", "kind": "frame", "frame": "cascade", "goal": g.name,
                                "system": g.system, "members": members, "label": g.name,
                                "fn": {"sym": "T", "sub": g.name, "arg": "s"},
                                "says": f"the inner loop of a cascade: {src[0].split(':', 1)[1]} sets the setpoint of {g.name}, "
                                        "and this loop holds it. "
                                        "Seen from the outer loop it is one block, its closed-loop transfer function T(s).",
                                "math": [eq(sym("T", g.name, "s"), frac(row(mi("C"), mo("⁢"), mi("P")),
                                                                         row(mn(1), mo("+"), mi("C"), mo("⁢"), mi("P"), mo("⁢"),
                                                                                 mi("H"))))]})

    def mark_loops(self) -> None:
        """Each part's loops: the goals whose loop it is in (for the side panel's list, pointed at)."""
        s = self.s
        for g in s.goals:
            lp = s.loop(g)
            mine = {f"sum:{g}", f"ref:{g}", f"out:{s.goals[g].of.kind}.{s.goals[g].of.name}"}
            mine |= {f"blk:{b}" for b in [*lp.controllers, *lp.actuators]}
            for p in lp.through:
                k, _, nm = p.partition(".")
                if k == "block":
                    mine.add(f"blk:{nm}")
                elif p in self.prod:
                    mine.add(self.prod[p][0])
            gv = f"{s.goals[g].of.kind}.{s.goals[g].of.name}"
            mine.add(f"sen:{gv}")
            mine |= {w["source"] for w in self.wires if w["target"] == f"sen:{gv}" and w["source"].startswith("col:")}
            if gv in self.prod:
                mine.add(self.prod[gv][0])
            for v in (*lp.valves, *lp.disturbances):
                if f"flow.{v}" in self.prod:
                    mine.add(self.prod[f"flow.{v}"][0])
            for nid in mine:
                if nid in self.nodes:
                    self.nodes[nid].setdefault("loops", [])
                    if g not in self.nodes[nid]["loops"]:
                        self.nodes[nid]["loops"].append(g)


OPS = {"<=": "≤", ">=": "≥", "==": "=", "<": "<", ">": ">"}
PAST = {"<=": ">", "<": "≥", ">=": "<", ">": "≤", "==": "≠"}       # where a one-sided goal is off


def _until(text) -> str:
    sp = str(text).strip()
    for a, b in OPS.items():
        if sp.startswith(a):
            return f"{b} {sp[len(a):].strip()}"
    return sp


def _hold(g) -> str:
    """A goal's setpoint, written as the textbooks write it: ≤ 0, ≥ 2, = 0.93."""
    return f"{OPS.get(g.hold.op, g.hold.op)} {_num(g.hold.value)}"


# ---- folded by the systems: closed ones as subsystem blocks (C, P or named), open ones as frames, one drawn alone

def _chain(spec: Spec, system: str | None) -> list[str]:
    return list(reversed(spec.chain(system)))         # outermost first


def _effects(spec: Spec) -> dict[str, set[str]]:
    """Each part's causal edges forward: a flow to the stocks it fills or drains, a part to what it drives."""
    out: dict[str, set[str]] = {}
    for f in spec.flows.values():
        out.setdefault(f"flow.{f.name}", set()).update(f"stock.{x}" for x in (f.source, f.target) if x)
    for k, t in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in t.values():
            for r in x.driven_by:
                out.setdefault(f"{r.kind}.{r.name}", set()).add(f"{k}.{x.name}")
    return out


def _classes(d: _Diagram) -> dict[str, dict]:
    """Each system as one block, read from the wires crossing its border (docs/proposals/blocks-levels.md §1), the same
    whether it is drawn closed or open: C when it sends u wires out and none in, P when it takes u wires in and sends
    none out, else named by itself. A u wire is set by a controller inside its source and enters a part of its target
    that reaches one of the target's goals; every other wire is a y wire. Its ports in order: inputs (references and
    signals from other systems), outputs, disturbances (entering from outside or arising inside); p outputs by m inputs,
    disturbances counted, at both levels."""
    if getattr(d, "classes", None) is not None:
        return d.classes
    spec, nodes, fx = d.s, d.nodes, _effects(d.s)
    within = lambda nid, s: s in spec.chain((nodes.get(nid) or {}).get("system"))          # noqa: E731
    inside = lambda var, s: "." in var and spec.inside(Ref(*var.split(".", 1)), s)      # noqa: E731

    def reaches(w: dict, t: str | None, outside: str) -> bool:      # rule (b): into t (None: anything not in outside)
        part = lambda v: inside(v, t) if t else not inside(v, outside)                  # noqa: E731
        b = w["target"][4:] if w["target"].startswith("blk:") else None
        todo = [f"{x.kind}.{x.name}" for x in spec.blocks[b].targets()] if b in spec.blocks else [w["key"]]
        todo = [y for v in todo for y in (v, *fx.get(v, ()))]       # a flow of the source may fill the target's stock
        goals = {str(g.of) for g in spec.goals.values() if part(str(g.of))}
        seen: set[str] = set()
        while todo:
            v = todo.pop()
            if v in seen or not part(v):
                continue
            seen.add(v)
            if v in goals:
                return True
            todo.extend(fx.get(v, ()))
        return False

    out: dict[str, dict] = {}
    for s in spec.systems:
        ports: dict[str, list[str]] = {"in": [], "out": [], "d": []}
        u_in = u_out = False
        for w in d.wires:
            a, b, k = within(w["source"], s), within(w["target"], s), w["key"]
            sg = d.sig.get(k) or d.signal(k)
            if a and b and nodes[w["source"]].get("role") == "disturbance":
                group = "d"
            elif a == b:
                continue
            else:
                group = "out" if a else "d" if sg.get("sym") == "d" else "in"
                if sg.get("sym") == "u":
                    tch = spec.chain(nodes[w["target"]].get("system"))
                    t = next((x for x in tch if spec.within.get(x) in spec.chain(s)[1:] or not spec.within.get(x)), None)
                    if reaches(w, s, s) if b else reaches(w, t, s):
                        u_in, u_out = u_in or b, u_out or a
            if k not in ports[group]:
                ports[group].append(k)
        letter = "C" if u_out and not u_in else "P" if u_in and not u_out else None
        out[s] = {"letter": letter, "p": len(ports["out"]), "m": len(ports["in"]) + len(ports["d"]),
                  "ports": [{"as": g, "key": k} for g in ("in", "out", "d") for k in ports[g]]}
    d.classes = out
    return out


def fold(d: _Diagram, open_: set[str] | None, focus: str | None, keep: set[str] | None = None) -> dict:
    """``keep``: the only nodes drawn (the loops an item or a kind touches); a wire from any other ends at a port."""
    from .fold import default_open, upkeep
    from .remote import box as remote_box
    spec = d.s
    if open_ is None:
        open_ = default_open(spec, focus) if spec.systems else set()
    if "*" in open_:
        open_ = set(spec.systems)
    nodes = d.nodes

    def rep(nid: str) -> str:
        if keep is not None and nid not in keep:
            return "ext"
        ch = _chain(spec, nodes[nid].get("system"))
        if focus:
            if focus not in ch:
                return "ext"
            ch = ch[ch.index(focus) + 1:]
        for s in ch:
            if s not in open_:
                return f"sys:{s}"
        return nid

    reps = {nid: rep(nid) for nid in nodes}
    mixed = {name for nid, n in nodes.items() if not _continuous(n) for name in spec.chain(n.get("system"))}
    arg = lambda name: None if name in mixed else "s"          # noqa: E731  P_lab: an operator, not a transfer function
    cls = _classes(d)

    def sysfn(name: str) -> dict:                              # the same at both levels: closed, and its frame open
        c = cls[name]
        return {"sym": c["letter"] or name, "sub": name if c["letter"] else None, "named": not c["letter"],
                "arg": arg(name), "expr": f"{c['p']}×{c['m']}", "letter": c["letter"], "p": c["p"], "m": c["m"]}
    out: dict[str, dict] = {}
    boxes: dict[str, dict] = {}
    for nid, n in nodes.items():
        r = reps[nid]
        if r == nid:
            out[nid] = {**n, "ins": list(n["ins"]), "outs": list(n["outs"])}
        elif r.startswith("sys:") and r not in boxes:
            name = r.split(":", 1)[1]
            inner = spec.inner_loops(name)
            boxes[r] = {"id": r, "kind": "block", "role": "subsystem", "system": spec.within.get(name), "label": name,
                        "ins": [], "outs": [], "parts": 0, "loops": [],
                        "fn": {**sysfn(name), "linear": None}, "ports": cls[name]["ports"],
                        "says": d.system_says(name) and d.system_says(name) + ". ",
                        "subsystems": spec.subsystems(name), "inner": inner, "system_name": name,
                        "remote": remote_box(spec, name), "upkeep": upkeep(spec, name)}
        if r.startswith("sys:"):
            boxes[r]["parts"] += 1
            boxes[r].setdefault("holds", []).append(nid)          # (correspond.py: what it holds, as drawn)
            for g in n.get("loops", []):
                if g not in boxes[r]["loops"]:
                    boxes[r]["loops"].append(g)
    terms: dict[str, dict] = {}
    edges: list[dict] = []
    seen: set[tuple] = set()

    def box_port(b: str, io: str, key: str) -> str:
        box = boxes[b]
        pid = f"{b}|{io}|{key}"
        lst = box["ins" if io == "in" else "outs"]
        if not any(p["id"] == pid for p in lst):
            lst.append({"id": pid, "side": "W" if io == "in" else "E", "key": key})
        return pid

    def term(key: str, io: str, other: str) -> str:
        tid = f"term:{io}:{key}"
        if tid not in terms:
            sg = d.signal(key) if not key.startswith(("psum:", "vec-", "rec:")) else d.sig.get(key, {"sym": "", "sub": ""})
            ch = spec.chain(nodes[other].get("system")) if other in nodes else []
            terms[tid] = {"id": tid, "kind": "port", "role": "in-port" if io == "in" else "out-port", "label": key,
                          "fn": {"sym": sg.get("sym"), "sub": sg.get("sub")}, "ins": [], "outs": [], "system": focus,
                          "in": ch[0] if ch else None,
                          "says": f"{'an input from' if io == 'in' else 'an output to'} {ch[0] if ch else 'the top level'}, "
                                  f"outside {focus or 'the loops drawn'}: {sg.get('sym') or ''}{'_' + sg['sub'] if sg.get('sub') else ''}.",
                          "port_of": io}
            if io == "in":
                terms[tid]["outs"].append({"id": tid + "|out", "side": "E"})
            else:
                terms[tid]["ins"].append({"id": tid + "|in", "side": "W"})
        return terms[tid]["outs" if io == "in" else "ins"][0]["id"]

    for w in d.wires:
        s0, t0 = reps[w["source"]], reps[w["target"]]
        if s0 == t0 or (s0 == "ext" and t0 == "ext"):
            continue
        e = {**w}
        if s0 == "ext":
            e["source"], e["sourcePort"] = f"term:in:{w['key']}", term(w["key"], "in", w["source"])
        elif s0.startswith("sys:"):
            e["source"], e["sourcePort"] = s0, box_port(s0, "out", w["key"])
        if t0 == "ext":
            e["target"], e["targetPort"] = f"term:out:{w['key']}", term(w["key"], "out", w["target"])
        elif t0.startswith("sys:"):
            e["target"], e["targetPort"] = t0, box_port(t0, "in", w["key"])
        k = (e["sourcePort"], e["targetPort"])
        if k in seen:
            continue
        seen.add(k)
        edges.append(e)
    # between two subsystem blocks, the signals one sends the other are one vector
    bundles: dict[tuple, list[dict]] = {}
    for e in edges:
        if e["source"].startswith("sys:") and e["target"].startswith("sys:"):
            bundles.setdefault((e["source"], e["target"]), []).append(e)
    for (a, b), es in bundles.items():
        if len(es) < 2:
            continue
        keys = sorted(x["key"] for x in es)
        sp, tp = f"{a}|out|vec>{b}", f"{b}|in|vec<{a}"
        for x in es:
            edges.remove(x)
        for box, io, pid in ((a, "outs", sp), (b, "ins", tp)):
            boxes[box][io] = [p for p in boxes[box][io] if p["key"] not in keys or
                              any(e["sourcePort" if io == "outs" else "targetPort"] == p["id"] for e in edges)]
            boxes[box][io].append({"id": pid, "side": "W" if io == "ins" else "E", "key": "vec", "n": len(keys), "keys": keys})
        edges.append({"key": f"vec:{a}>{b}", "source": a, "sourcePort": sp, "target": b, "targetPort": tp, "keys": keys})
        u = cls[a.split(":", 1)[1]]["letter"] == "C"                          # a subsystem's outputs, one vector: u from a C
        d.sig[f"vec:{a}>{b}"] = {"key": f"vec:{a}>{b}", "sym": "u" if u else "y",
                                 "sub": a.split(":", 1)[1], "what": "vector", "n": len(keys)}
    _top_loops(d, cls, boxes, edges, out, _coupled(boxes, edges))
    for i, e in enumerate(edges):
        e["id"] = f"w{i}:{e['sourcePort']}>{e['targetPort']}"
        sg = d.sig.get(e["key"]) or d.signal(e["key"])
        e["signal"] = {k: sg[k] for k in ("sym", "sub", "what", "n") if k in sg}
        if not sg.get("sym") and e["key"].startswith("rec:") and (e["source"] in boxes or e["target"] in boxes):
            e["signal"] = {"sym": "y", "sub": e["key"][4:].split("~")[0].rsplit(".", 1)[0], "what": "record"}  # between systems
    # what each subsystem block computes, now that its inputs and outputs are known
    for b in boxes.values():
        name = b["system_name"]
        fn = b["fn"]
        fn["bold"] = fn["m"] > 1 or fn["p"] > 1
        q, L = (sym(fn["letter"], name, fn["arg"], fn["bold"]), fn["letter"]) if fn["letter"] else (mt(name), name)
        ds = sum(p["as"] == "d" for p in b["ports"])
        what = {"C": "a controller: it acts on another system's process, and nothing outside acts on it",
                "P": "a process: another system acts on it, and it acts on none", None: "a named block: it acts on "
                "another system and is acted on, or neither (it holds only its own loops)"}[fn["letter"]]
        b["math"] = [eq(sym("y", name, None, fn["bold"]), row(q, sym("u", name, None, fn["bold"])) if fn["arg"]
                        else row(q, mo("["), sym("u", name, None, fn["bold"]), mo("]"))),
                     mt(f"the system {name} as one block, {what} (inferred from the signals crossing its edge): "
                        f"{fn['p']} output{'s' if fn['p'] != 1 else ''} by {fn['m']} input{'s' if fn['m'] != 1 else ''} "
                        f"({ds} of them disturbances), with the {len(b['loops'])} "
                        f"loop{'s' if len(b['loops']) != 1 else ''} inside closed. Not identified. " +
                        (f"Every part inside is continuous: a transfer function {L}(s)." if fn["arg"] else
                         f"It holds sampled or nonlinear parts, so it is an operator {L}[u], not a transfer function {L}(s)."))]
        b["says"] = (b["says"] or "") + ("an inner loop: given a setpoint from outside, it holds it. " if b["inner"] else "")
        b["rows"] = [["system", name], ["loops inside", ", ".join(b["loops"])], ["inside", ", ".join(b["subsystems"])],
                     ["inputs", ", ".join(_portkey(p) for p in b["ins"])], ["outputs", ", ".join(_portkey(p) for p in b["outs"])]]
    # where each part is drawn: inside the frame of the innermost open system it is in (or of its cascade)
    def frame_of(system: str | None) -> str | None:
        ch = _chain(spec, system)
        if focus:
            ch = ch[ch.index(focus) + 1:] if focus in ch else []
        inner = [s for s in ch if s in open_]
        return f"frame:{inner[-1]}" if inner else None
    frames: dict[str, dict] = {}
    for n in [*out.values(), *boxes.values()]:
        n["parent"] = frame_of(n.get("system"))
    for t in terms.values():
        t["parent"] = None
    used = {n["parent"] for n in [*out.values(), *boxes.values()] if n.get("parent")}
    for f in list(used):                                   # a frame's own frame
        while f:
            name = f.split(":", 1)[1]
            if f not in frames:
                frames[f] = {"id": f, "kind": "frame", "frame": "system", "label": name, "parent": frame_of(spec.within.get(name)),
                             "fn": sysfn(name), "ports": cls[name]["ports"], "says": d.system_says(name),
                             "inner": spec.inner_loops(name)}
            f = frames[f]["parent"]
    for c in d.frames:
        if all(m in out for m in c["members"]) and len({out[m]["parent"] for m in c["members"]}) == 1:
            fid = c["id"]
            frames[fid] = {k: v for k, v in c.items() if k != "members"}
            frames[fid]["parent"] = out[c["members"][0]]["parent"]
            for m in c["members"]:
                out[m]["parent"] = fid
    node_list = [*out.values(), *boxes.values(), *terms.values()]
    for n in node_list:
        n.setdefault("loops", [])
    return {"kind": "blocks", "nodes": node_list, "edges": edges, "frames": list(frames.values()),
            "open": sorted(open_), "focus": focus,
            "tree": {s: {"within": spec.within.get(s), "description": desc} for s, desc in spec.systems.items()}}


def _coupled(boxes: dict, edges: list[dict]) -> list[tuple[str, str]]:
    """The groups of closed systems drawn as one loop: each C box and the P box its u wires enter."""
    return sorted({(e["source"], e["target"]) for e in edges if e["source"] in boxes and e["target"] in boxes and
                   boxes[e["source"]]["fn"]["letter"] == "C" and boxes[e["target"]]["fn"]["letter"] == "P"})


def _top_loops(d: _Diagram, cls: dict, boxes: dict, edges: list[dict], out: dict, groups: list[tuple[str, str]]) -> None:
    """Each group of closed systems drawn as its loop: here each coupled C and P (_top_loop)."""
    for c, p in groups:
        _top_loop(d, cls, boxes, edges, out, c, p)


def _top_loop(d: _Diagram, cls: dict, boxes: dict, edges: list[dict], out: dict, c: str, p: str) -> None:
    """A C acting on a P drawn as the textbook loop (docs/proposals/blocks-levels.md §2): r, the goals of P that C
    serves, into a summing junction ahead of C; e into C; u from C to P; y out of P, and back through H (the sensors
    that read it) to the junction's minus input; d into P. Where C serves no goal of P, or reads nothing of P, the
    wires stay as they are."""
    spec = d.s
    C, P = c[4:], p[4:]
    back = next((e for e in edges if e["source"] == p and e["target"] == c), None)
    by = lambda g: [spec.blocks[b].system for b in (lambda lp: lp.controllers + lp.actuators)(spec.loop(g))  # noqa: E731
                    if b in spec.blocks]
    goals = [g for g, x in spec.goals.items() if P in spec.chain(x.system) and
             any(C in spec.chain(s) for s in by(g)) and not any(P in spec.chain(s) for s in by(g))]
    if back is None or not goals:
        return
    keys, dk = back.get("keys") or [back["key"]], [x["key"] for x in cls[P]["ports"] if x["as"] == "d"]
    n, m, at = len(goals), len(keys), boxes[p]["system"]
    cp = f"{C}>{P}"                                 # one loop per pair: two Cs on a P, or a C on two Ps, draw two loops
    rid, sid, hid, oid, did, ep = (*(f"{k}:top:{cp}" for k in ("ref", "sum", "h", "out")), f"dist:top:{P}", f"{c}|in|e<{P}")
    hs = [(d.nodes.get((d.prod.get(k) or ("",))[0]) or {}).get("fn", {}).get("expr") or "1" for k in keys]
    H = hs[0] if m == 1 else f"diag({', '.join(hs)})"
    ys = ", ".join(_keyname(k).replace(" (measured)", "") for k in keys)
    sig = {"r": ("r", P, "reference", n), "e": ("e", None, "error", n), "y": ("y", P, "output", m),   # (e and y_m bare, as
           "ym": ("y", "m", "measured", m), "d": ("d", P, "disturbance", len(dk))}                    # the textbooks: by their Σ)
    for k, (s_, sub, what, w) in sig.items():
        d.sig[f"top:{k}:{P if k == 'd' else cp}"] = {"key": f"top:{k}:{P if k == 'd' else cp}", "sym": s_, "sub": sub,
                                                     "what": what, "n": w}
    node = lambda nid, ks=keys, **kw: out.setdefault(nid, {"id": nid, "system": at, "loops": list(goals),  # noqa: E731
                                                           "signals": list(ks), **kw})          # (correspond.py: what it is)
    node(rid, [f"goal.{g}.r" for g in goals], kind="input", role="reference", label=f"r {P}",
         fn={"sym": "r", "sub": P, "bold": n > 1, "value": ", ".join(goals) if n > 1 else f"{goals[0]} {_hold(spec.goals[goals[0]])}"},
         ins=[], outs=[{"id": f"{rid}|out|r", "side": "E"}], math=[sym("r", P, None, n > 1)],
         says=f"the references of {P} that {C} serves, {n}: " + "; ".join(f"{g} {_hold(spec.goals[g])}" for g in goals) + ".",
         rows=[["goals", ", ".join(goals)]])
    node(sid, [f"goal.{g}{x}" for g in goals for x in ("", ".r")], kind="sum", role="comparator", label=f"Σ {P}",
         ins=[{"id": f"{sid}|in|r", "side": "W", "sign": "+"}, {"id": f"{sid}|in|y", "side": "S", "sign": "−"}],
         outs=[{"id": f"{sid}|out|e", "side": "E"}],
         math=[eq(sym("e", P, None, n > 1), row(sym("r", P, None, n > 1), mo("−"), sym("y", f"m,{P}", None, m > 1)))],
         says=f"compares {P}'s references with what is measured of it: e = r − y_m. {C} reads y_m itself ({ys}) "
              "and compares inside: this junction is those comparisons, drawn ahead of it.")
    node(oid, kind="output", role="output", label=f"y {P}", fn={"sym": "y", "sub": P, "bold": m > 1},
         ins=[{"id": f"{oid}|in|y", "side": "W"}], outs=[], math=[sym("y", P, None, m > 1)],
         says=f"what {P} puts out, {m}: {ys}.")
    node(hid, kind="block", role="sensor", label=f"H {P}", fn={"name": f"H_{P} = " + (hs[0] if len(set(hs)) == 1 else f"diag(H_1 … H_{m})"),
         "reads": ("each its own: " if m > 1 else "") + f"the readings of {ys}"},
         ins=[{"id": f"{hid}|in|y", "side": "E"}], outs=[{"id": f"{hid}|out|ym", "side": "W"}],
         math=[eq(sym("H", P, None, m > 1), mt(H))],
         says=f"the sensing of {P}, on the return path: the sensors that read {ys}" +
              (", diagonal: each reads its own output" if m > 1 else "") + ". H = 1 where a sensor adds no dynamics.")
    edges.remove(back)
    boxes[c]["ins"] = [x for x in boxes[c]["ins"] if x["id"] != back["targetPort"]] + [
        {"id": ep, "side": "W", **({"key": "vec", "n": m, "keys": keys} if m > 1 else {"key": keys[0]})}]
    wire = lambda k, a, ap, b, bp, **kw: edges.append({"key": f"top:{k}:{P if k == 'd' else cp}", "source": a,  # noqa: E731
                                                       "sourcePort": ap, "target": b, "targetPort": bp, "keys": keys, **kw})
    wire("r", rid, f"{rid}|out|r", sid, f"{sid}|in|r", sign="+", keys=goals)
    wire("e", sid, f"{sid}|out|e", c, ep)
    wire("y", p, back["sourcePort"], oid, f"{oid}|in|y")
    wire("y", p, back["sourcePort"], hid, f"{hid}|in|y", feedback=True)
    wire("ym", hid, f"{hid}|out|ym", sid, f"{sid}|in|y", sign="−", feedback=True)
    if dk and did not in out:                         # P's disturbance once, however many Cs act on it
        node(did, dk, kind="input", role="disturbance", label=f"d {P}", fn={"sym": "d", "sub": P, "bold": len(dk) > 1},
             ins=[], outs=[{"id": f"{did}|out|d", "side": "E"}], math=[sym("d", P, None, len(dk) > 1)],
             says=f"what enters {P} that no valve sets, {len(dk)}: {', '.join(_keyname(k) for k in dk)}.")
        boxes[p]["ins"].append({"id": f"{p}|in|d", "side": "N", **({"key": "vec", "n": len(dk), "keys": dk}
                                                                    if len(dk) > 1 else {"key": dk[0]})})
        wire("d", did, f"{did}|out|d", p, f"{p}|in|d", keys=dk)


def _continuous(n: dict) -> bool:
    """A part of continuous time: not a sampler, a hold or a discrete controller, and not a block that runs on its
    own schedule (a relay, a program, an AI agent, a person); a process is the world's, continuous."""
    fn = n.get("fn") or {}
    if n.get("kind") == "sampler" or n.get("role") == "hold" or fn.get("arg") == "z":
        return False
    return not (n.get("kind") == "block" and n.get("role") in ("controller", "actuator") and fn.get("name"))


def _portkey(p: dict) -> str:
    if p.get("key") == "vec":
        return ", ".join(_keyname(k) for k in p.get("keys", [])) or f"a vector of {p.get('n')}"
    return _keyname(p.get("key") or "")


def _keyname(k: str) -> str:
    """A signal's key as a reader names it: ``meas.stock.queue.main`` is queue, measured."""
    if k.startswith("meas."):
        return f"{k.split('.')[2]} (measured)"
    if k.startswith("rec:"):
        return f"what {k[4:].split('~')[0].rsplit('.', 1)[0]}'s collector recorded"
    return k.split(".", 1)[-1]


def loop_parts(spec: Spec, goal: str) -> set[str]:
    """A goal's control loop as the model's parts (``kind.name``): what it holds, its controllers and actuators, its
    valves and disturbances, the long way round, and what its sensors read."""
    g, lp = spec.goals[goal], spec.loop(goal)
    return {str(g.of), *(f"block.{b}" for b in [*lp.controllers, *lp.actuators]), *lp.through,
            *(f"flow.{v}" for v in [*lp.valves, *lp.disturbances]), *(s.rsplit(".", 1)[0] for s in lp.sensors)}


def diagram(model, snap: dict | None = None, open_: set[str] | None = None, focus: str | None = None,
            parts: set[str] | None = None) -> dict:
    """The control system of a model as a block diagram, folded by its systems; given ``parts`` (what an item passed
    through, or what a kind touches), only the control loops those meet, each whole, in its systems' frames."""
    spec = spec_of(model)
    if spec is None:
        return {"kind": "blocks", "nodes": [], "edges": [], "frames": [], "open": [], "focus": focus, "tree": {}}
    d = _Diagram(spec, snap)
    d.build()
    identified(d)
    keep = None
    if parts is not None:              # chosen from the model alone: a goal never read yet is touched like any other
        goals = {g for g in spec.goals if loop_parts(spec, g) & parts}
        keep = {nid for nid, n in d.nodes.items() if goals & set(n.get("loops") or ())}
        fed = {w["target"] for w in d.wires if w["source"] in keep}       # (a stock's sum: between its flows and it)
        keep |= fed & {w["source"] for w in d.wires if w["target"] in keep}
        open_, focus = {s for nid in keep for s in spec.chain(d.nodes[nid].get("system"))}, None
    g = fold(d, open_, focus, keep)
    loops = {}
    for name, lp in (snap or {}).get("loops", {}).items():
        if name in spec.goals:
            gl = spec.goals[name]
            loops[name] = {"status": lp.get("status"), "word": lp.get("word"), "stock": gl.of.name, "setpoint": _hold(gl),
                           "value": lp.get("value"), "error": lp.get("error"), "band": lp.get("band", ""),
                           "nodes": sorted(n["id"] for n in g["nodes"] if name in n.get("loops", []))}
    g["loops"] = loops
    return g


def process_text(pr: dict) -> tuple[str, str]:
    """A loop's process as its block shows it, numerator and denominator, time in seconds as the
    textbooks write it: 0.0031 e^(−9s) over 21s + 1."""
    k = f"{float(pr['gain']):.3g}".replace("-", "−")
    th = pr.get("theta") or 0.0
    num = f"{k} e^(−{th:.3g}s)" if th else k
    return (num, "s") if pr["form"] == "integrating" else (num, f"{pr['tau']:.3g}s + 1")


def identified(d: _Diagram) -> None:
    """Each goal's loop marked on the process block that puts out what it holds (the side panel's
    identification of that loop, from u to y, opens there); a process the model declares
    (a goal's ``process:``, accepted from an identification or written) drawn in that block."""
    for name, g in d.s.goals.items():
        y = f"{g.of.kind}.{g.of.name}"
        nid = (d.prod.get(y) or (None,))[0] or ""
        if nid.startswith("demux:"):                     # one output of a multi-input multi-output process
            nid = "proc:" + nid.split(":", 1)[1]
        n = d.nodes.get(nid)
        if n is None or n.get("role") != "process":
            continue
        n.setdefault("y_of", []).append(name)
        pr = g.process
        if not pr:
            continue
        num, den = process_text(pr)
        how = f"identified {pr['identified']}" if pr.get("identified") else "declared"
        if not n.get("mimo"):                            # a matrix keeps its entries; the loop's path is said beside it
            n["fn"] = {**n["fn"], "arg": "s", "expr": f"{num}/({den})", "frac": [num, den], "linear": True,
                       "process_of": name}
        n["math"] = [*n.get("math", []),
                     eq(sym("P", name, "s"), frac(mt(num), mt(den))),
                     mt(f"the loop {name}'s process, from what its controller moves to {g.of.name}, first order with dead time "
                        f"({how}, goal {name}: process:)" if pr["form"] == "fopdt" else
                        f"the loop {name}'s process, an integrator with dead time ({how}, goal {name}: process:)")]
        n["says"] = (n.get("says") or "") + f" Seen from the loop {name}, the whole path from u is P(s) = {num}/({den}), {how}."


def spec_of(model) -> Spec | None:
    """The model's compiled form; an older model's, converted, when it has none."""
    spec = getattr(model, "spec", None)
    if spec is not None:
        return spec
    cached = getattr(model, "_block_spec", None)
    if cached is not None:
        return cached
    try:
        import tempfile
        from pathlib import Path

        from .spec import load
        from .spec.convert import convert
        text, _ = convert(model)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ergostat.yaml"
            p.write_text(text)
            spec = load(p)
    except Exception:
        return None
    try:
        model._block_spec = spec
    except Exception:
        pass
    return spec
