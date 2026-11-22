"""From the merged document to the compiled model, refusing what is wrong (SPEC §12's errors), each
error with the file and line it was written at."""

from __future__ import annotations

import re
import shlex
import sys
import time
from pathlib import Path

from ..durations import DurationError, parse_duration
from . import files
from .equation import FUNCS as FUNCTIONS
from .ir import (
    ACTION,
    BUILTIN,
    CHANGE_CLASSES,
    CLAIM,
    CLAIM_CHECKS,
    CONTEXT,
    INTENT_PORTS,
    JUDGE_MODES,
    JUDGE_PORTS,
    MACHINE,
    MESSAGE,
    MODEL_CHANGE,
    MODEL_MEASURES,
    MODELLING_REQUEST,
    NAME,
    NAMED_ONLY,
    VERDICT,
    WORKSPACE,
    Agent,
    Auxiliary,
    Block,
    ClaimCheck,
    Equation,
    Flow,
    Goal,
    Improve,
    IntentKind,
    IntentPolicy,
    ItemKind,
    Messages,
    NamedLoop,
    Parameter,
    Ref,
    Sensor,
    Setpoint,
    Source,
    Spec,
    Stock,
    action_kind,
    claim_kind,
    is_measure,
    message_kind,
    model_change_kind,
    modelling_request_kind,
    verdict_kind,
    workspace_kind,
)
from .load import SINGULAR, Document, Map, Problem, Where

COMMON = {"system", "description"}
SENSOR_KEYS = {"run", "query", "manual", "items", "builtin", "daemon", "push", "every", "cron", "timeout", "parse", "unit",
               "description", "averages"}
ITEM_SENSOR_KEYS = {"state", "entering", "leaving", "where", "over", "measure", "sum"}
CHANGES = ("rises", "falls", "net", "rest")          # a flow measured from its stock's successive readings (rest: less its other flows)
ITEM_KEYS = COMMON | {"id", "states", "on", "show", "formats", "fold", "lease", "relations", "join", "about"}
STOCK_KEYS = COMMON | {"unit", "limit", "initial", "sensors", "sensor", "cumulative", "inferred", "rate-unit", "observe", "formerly"}
LINK_KEYS = {"cause", "instant", "description", "inferred"}   # a driven-by written out: the cause, and what is said of the link
FLOW_KEYS = COMMON | {"from", "to", "unit", "rate", "sensors", "sensor", "driven-by", "two-way", "equation", "inferred", "formerly",
                      "rate-unit"}
GOAL_KEYS = COMMON | {"stock", "flow", "auxiliary", "variable", "hold", "tolerance", "critical", "owner", "process", "per", "on-stale"}
PROCESS_KEYS = {"gain", "time-constant", "dead-time", "integrating", "identified", "description"}
AUXILIARY_KEYS = COMMON | {"unit", "sensors", "sensor", "driven-by", "exogenous", "equation", "inferred", "formerly"}
PARAMETER_KEYS = COMMON | {"value", "unit", "estimate", "table", "range", "inferred"}
DRIVERS = ("flow", "stock", "auxiliary")             # what a driven-by may name
INFERRED = re.compile(r"^ergostat\.model-change/[0-9a-z-]+$")   # inferred: the model change that added a part
AGENT_KEYS = {"kind", "external", "at-once", "model", "cost", "host", "description"}
AGENT_KINDS = ("person", "ai", "narrow-ai", "decision", "program", "rule")
SOURCE_TYPES = {"prometheus": {"type", "url"}, "command": {"type"}, "ergostat": {"type", "url", "token-file"}}
BLOCK_COMMON = COMMON | {"type", "in", "out", "role", "on-stale"}
MACHINE_COMMON = {"agent", "max", "min", "timeout", "every", "cron", "mode", "takes", "pool", "lease", "on"}
LAW_KEYS = {"gain", "integral-time", "deadband", "resolution", "limits"}   # a machine block's law, when it says it (its params)
TYPE_KEYS = {
    "program": MACHINE_COMMON | LAW_KEYS | {"run", "daemon", "parse", "goal", "until", "review", "workspace", "actions",
                                            "read-only", "network"},
    "ai": MACHINE_COMMON | LAW_KEYS | {"prompt", "model", "run", "parse", "goal", "until", "context", "review",
                                       "workdir", "workspace", "read", "tools", "actions", "read-only", "network"},
    "person": MACHINE_COMMON | LAW_KEYS | {"ask", "goal", "until", "review"},
    "external": {"agent", "identify"},
    "judge": {"every", "accept", "threshold", "hold-out", "windows", "warm-up", "reviewed",              # judge: model (SPEC §12e)
              "judge", "kinds", "model", "max-cost", "held", "within"},                      # judge: intent (SPEC §12i)
    "onoff": {"goal", "until", "min-on", "min-off"},
    "compare": {"above", "below", "back-above", "back-below"},
    "proportional": {"goal", "gain", "min", "max"},
    "limit": {"min", "max", "rate"},
    "delay": {"delay"},
    "schedule": {"table"},
    "lookup": {"table"},
    "select": {"pick"},
    "expr": {"expr"},
    "timer": {"after"},
    "counter": {"reset"},
    "alarm": {"above", "below", "for"},
}
NEEDS = {"program": ["run"], "ai": ["prompt"], "person": ["ask"], "onoff": ["goal"], "proportional": ["goal", "gain"],
         "delay": ["delay"], "schedule": ["table"], "lookup": ["table"], "select": ["pick"], "expr": ["expr"],
         "timer": ["after"]}
ONE_INPUT = ("compare", "limit", "delay", "lookup", "timer", "counter", "alarm")
KIND_RUNS = {"person": {"person", "external"}, "ai": {"ai", "program", "external"}, "narrow-ai": {"ai", "program", "external"},
             "decision": {"program", "external"}, "program": {"program", "external"}, "rule": {"program", "external"}}


CLOCK = {"s", "sec", "second", "min", "minute", "d", "day", "week", "wk"}     # times other than the model's hour


def _clock_words(text: str | None) -> list[str]:
    """The words of a unit that count time in something other than hours (min, s, d, week): a value
    in them would be read as hours. ``ms`` is left alone: it is how a latency is measured, a quantity."""
    from . import equation as eq
    try:
        u = eq.unit(text) if text else None
    except Exception:
        return []
    return sorted(w for w in (u or {}) if w in CLOCK)


class Compiler:
    def __init__(self, doc: Document):
        self.doc = doc
        self.problems: list[Problem] = list(doc.problems)
        self.old: dict[tuple, list] = {}                 # (what was renamed, file) → [first place, how many]

    def err(self, msg: str, where: Where | None, code: str = "", about: str = "") -> None:
        self.problems.append(Problem("error", msg, where, code, about))

    def deprecated(self, what: str, where: Where | None) -> None:
        """An old name, still read: said once per file, with how many times it is used there."""
        k = (what, where.file if where else None)
        if k in self.old:
            self.old[k][1] += 1
        else:
            self.old[k] = [where, 1]

    def renamed(self) -> None:
        say = {"variables": ("variables: is now auxiliaries: (an auxiliary has no memory: it is determined at each moment "
                             "by others; what keeps its value between changes is a stock). Rename the section"),
               "variable-ref": "variable.NAME is now auxiliary.NAME: rename the reference",
               "goal-variable": "a goal's variable: is now auxiliary: rename the key"}
        for (what, _), (where, n) in self.old.items():
            self.problems.append(Problem("finding", say[what] + (f" ({n} places in this file)" if n > 1 else ""), where,
                                        "deprecated-name", ""))

    # ---- small readers

    def formerly(self, m: Map, what: str) -> list[str]:
        """``formerly:`` the names a part had (one, or a list): a rename that keeps its history (SPEC §12e)."""
        v = m.get("formerly")
        if v is None:
            return []
        xs = v if isinstance(v, list) else [v]
        if not all(isinstance(x, str) and NAME.match(x) for x in xs):
            self.err(f"{what}.formerly: the name it had (or a list of them)", m.at("formerly"), "bad-formerly")
            return []
        return [str(x) for x in xs]

    def keys(self, m: Map, allowed: set[str], what: str) -> None:
        for k in m:
            if k not in allowed:
                near = [a for a in sorted(allowed) if a[:2] == str(k)[:2]]
                self.err(f"{what}: unknown key {k!r}" + (f" (did you mean {near[0]}?)" if near else
                         f" (known: {', '.join(sorted(allowed))})"), m.at(k), "unknown-key")

    def number(self, m: Map, key: str, what: str, positive: bool = False):
        v = m.get(key)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int | float) or (positive and v <= 0):
            self.err(f"{what}.{key}: a number" + (" above 0" if positive else ""), m.at(key), "bad-number")
            return None
        return float(v)

    def duration(self, m: Map, key: str, what: str, default=None):
        v = m.get(key)
        if v is None:
            return default
        try:
            return parse_duration(v, f"{what}.{key}")
        except DurationError as e:
            self.err(f"{e} (like 30s, 5m, 2h, 1d)", m.at(key), "bad-duration")
            return default

    def cron(self, m: Map, key: str, what: str):
        v = m.get(key)
        if v is None:
            return None
        from ..cron import Cron, CronError
        try:
            Cron(str(v)).next_after(time.time())
        except CronError as e:
            self.err(f"{what}.cron: {e}", m.at(key), "bad-cron")
            return None
        return str(v)

    def intent_policy(self, m: Map, what: str) -> IntentPolicy:
        """An intent judge's policy (SPEC §12i): ``kinds`` (each item kind it judges: ``at``, the state it is judged in;
        ``accepted``, where it counts as done; ``scope``, ``work``, ``repo``, ``base``, ``reopen-to``), ``model`` (an AI
        judge on it, else the stand-in), ``max-cost`` (dollars a verdict), ``held`` (attention or reopen), ``within``."""
        out = IntentPolicy()
        kinds = m.get("kinds")
        if not isinstance(kinds, Map) or not kinds:
            self.err(f"{what}.kinds: the item kinds it judges, each with at: (the state the work says it is done in): "
                     f"kinds: {{ticket: {{at: review}}}}", m.at("kinds") or m.where, "missing-key")
            kinds = {}
        for kn, km in kinds.items():
            w = f"{what}.kinds.{kn}"
            if isinstance(km, str):                      # kinds: {ticket: review}
                km = {"at": km}
            if not isinstance(km, dict) or not km.get("at"):
                self.err(f"{w}: at: (the state the work is judged in)", kinds.at(kn), "missing-key")
                continue
            if isinstance(km, Map):
                self.keys(km, {"at", "accepted", "scope", "work", "repo", "base", "reopen-to"}, w)

            def strs(v):
                return [str(x) for x in v] if isinstance(v, list) else [str(v)] if v not in (None, "") else []
            repo = km.get("repo")
            if repo is not None and (str(repo).startswith("/") or ".." in str(repo).split("/")):
                self.err(f"{w}.repo: a folder inside the model's, written from it", kinds.at(kn), "bad-path")
                repo = None
            out.kinds[str(kn)] = IntentKind(str(kn), str(km["at"]), strs(km.get("accepted")), strs(km.get("scope")) or [str(kn)],
                                            strs(km.get("work")), None if repo is None else str(repo),
                                            str(km.get("base") or "main"), km.get("reopen-to") and str(km["reopen-to"]))
        if m.get("model") is not None:
            out.model = str(m["model"])
        if m.get("max-cost") is not None:
            v = self.number(m, "max-cost", what)
            if v is not None and v <= 0:
                self.err(f"{what}.max-cost: dollars a verdict, more than 0", m.at("max-cost"), "bad-number")
            elif v is not None:
                out.max_cost = float(v)
        held = m.get("held", "attention")
        if held not in ("attention", "reopen"):
            self.err(f"{what}.held: attention (the verdict needs the owner's attention) or reopen (the work goes back)",
                     m.at("held"), "bad-policy")
        else:
            out.held = str(held)
        if m.get("within") is not None:
            out.within = self.duration(m, "within", what, out.within)
        return out

    def judge_policy(self, m: Map, what: str) -> Improve:
        """A judge block's policy (SPEC §12e): ``accept`` (``owner``, the default, or ``auto``, for every kind or by
        kind), ``threshold`` (a share, ``2%``), ``hold-out`` (a duration), ``windows`` (how the record held out
        is split: ``[1, 2, 4]``, whole, halves and quarters) and ``warm-up`` (how long before each window its replay
        starts, 6h by default)."""
        out = Improve()
        acc = m.get("accept")
        ways = ("owner", "auto")
        if isinstance(acc, str):
            if acc not in ways:
                self.err(f"{what}.accept: owner or auto (or by kind: parameter:, equation:, structure:)", m.at("accept"),
                         "bad-accept")
            else:
                out.accept = {k: (acc if k not in NAMED_ONLY else "owner") for k in out.accept}
        elif isinstance(acc, Map):
            for k, v in acc.items():
                if k not in out.accept or str(v) not in ways:
                    self.err(f"{what}.accept.{k}: a kind of change ({', '.join(out.accept)}) set to owner or auto",
                             acc.at(k), "bad-accept")
                    continue
                out.accept[str(k)] = str(v)
        elif acc is not None:
            self.err(f"{what}.accept: owner or auto, or a map of kind to owner or auto", m.at("accept"), "bad-accept")
        t = m.get("threshold")
        if t is not None:
            try:
                v = float(str(t).strip().removesuffix("%")) / (100.0 if str(t).strip().endswith("%") else 1.0)
                if not 0 < v < 1:
                    raise ValueError
                out.threshold = v
            except ValueError:
                self.err(f"{what}.threshold: a share above 0 and below 1, like 2% or 0.02", m.at("threshold"),
                         "bad-threshold")
        h = self.duration(m, "hold-out", what, None)
        if h is not None:
            if h <= 0:
                self.err(f"{what}.hold-out: a duration above 0", m.at("hold-out"), "bad-duration")
            else:
                out.hold_out = h
        wu = self.duration(m, "warm-up", what, None)
        if wu is not None:
            if wu < 0:
                self.err(f"{what}.warm-up: a duration, 0 or more", m.at("warm-up"), "bad-duration")
            else:
                out.warm_up = wu
        rv = m.get("reviewed")                   # the kinds written only after the reviewer's pass
        if rv is not None:
            ks = [str(k) for k in (rv if isinstance(rv, list) else str(rv).replace(",", " ").split())]
            if any(k not in CHANGE_CLASSES for k in ks):
                self.err(f"{what}.reviewed: kinds of change ({', '.join(CHANGE_CLASSES)})", m.at("reviewed"), "bad-accept")
            else:
                out.reviewed = ks
        w = m.get("windows")
        if w is not None:
            if not isinstance(w, list) or not w or not all(isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 16
                                                            for x in w):
                self.err(f"{what}.windows: how the record held out is split, a list of whole numbers ([1, 2, 4]: whole, "
                         f"halves, quarters)", m.at("windows"), "bad-windows")
            else:
                out.windows = sorted(set(w))
        return out

    def rate_unit(self, m: Map, what: str) -> str | None:
        """``rate-unit:``: how a flow's rate is shown (minute, hour, day or week); display only."""
        from ..rates import UNITS
        v = m.get("rate-unit")
        if v is None:
            return None
        if str(v) not in UNITS:
            self.err(f"{what}.rate-unit: {v!r} is not one of {', '.join(UNITS)} (how its rate is shown; it is kept "
                     "per hour)", m.at("rate-unit"), "bad-value")
            return None
        return str(v)

    def on_stale(self, m: Map, what: str) -> str | None:
        from .observer import POLICIES
        v = m.get("on-stale")
        if v is not None and v not in POLICIES:
            self.err(f"{what}.on-stale: {', '.join(POLICIES)}", m.at("on-stale"), "bad-on-stale")
            return None
        return v

    def text(self, m: Map, key: str, default: str = "") -> str:
        v = m.get(key)
        return default if v is None else str(v)

    def ref(self, raw, where: Where | None, what: str, kinds: tuple[str, ...]) -> Ref | None:
        r = Ref.parse(raw)
        if r is None:
            hint = ""
            if isinstance(raw, str) and NAME.match(raw):
                hint = f": write the kind first, like {kinds[0]}.{raw}"
            elif isinstance(raw, str) and raw[:1] in "+-" and Ref.parse(raw[1:]):
                hint = ": only a driven-by and a machine block's in: carry a sign"
            self.err(f"{what}: {raw!r} is not a reference{hint} (stock.x, flow.x, auxiliary.x, goal.x, block.x, with an "
                     f"optional .port)", where, "bad-ref")
            return None
        if raw.startswith("variable."):
            self.deprecated("variable-ref", where)
        if r.kind not in kinds:
            self.err(f"{what}: {r} is a {r.kind}; here it must be a {' or '.join(kinds)}", where, "wrong-kind")
            return None
        return r

    def refs(self, m: Map, key: str, what: str, kinds: tuple[str, ...], signs: dict[str, int] | None = None) -> dict[str, list[Ref]]:
        """``in`` or ``out``: one reference, a list, or a map of port → reference (or list). With
        ``signs``, a reference may carry its sign (``+stock.x``, ``-auxiliary.y``), recorded there by
        port (SPEC §9, §12a)."""
        raw = m.get(key)
        w = m.at(key)
        if raw is None:
            return {}

        def one(x, at, label: str) -> tuple[Ref | None, int | None]:
            sign = None
            if signs is not None and isinstance(x, str) and x[:1] in "+-" and Ref.parse(x[1:].strip()):
                sign, x = (1 if x[0] == "+" else -1), x[1:].strip()
            return self.ref(x, at, label, kinds), sign

        def keep(port: str, r: Ref, sign: int | None) -> Ref:
            if sign is not None and signs is not None:
                signs[port] = sign
            return r
        if isinstance(raw, str):
            port = "out" if key == "out" else "in"
            r, sign = one(raw, w, f"{what}.{key}")
            return {port: [keep(port, r, sign)]} if r else {}
        if isinstance(raw, list):
            got = [(r, sign) for r, sign in (one(x, w, f"{what}.{key}") for x in raw) if r]
            if key == "out":
                return {"out": [r for r, _ in got]} if got else {}
            ports = [f"in{i + 1}" if len(got) > 1 else "in" for i in range(len(got))]
            return {p: [keep(p, r, sign)] for p, (r, sign) in zip(ports, got, strict=True)}
        if isinstance(raw, dict):
            out = {}
            for port, v in raw.items():
                if not isinstance(port, str) or not NAME.match(port):
                    self.err(f"{what}.{key}: port {port!r}: lowercase letters, digits and -", raw.at(port), "bad-name")
                    continue
                vs = v if isinstance(v, list) else [v]
                got = [one(x, raw.at(port), f"{what}.{key}.{port}") for x in vs]
                out[port] = [keep(port, r, sign) for r, sign in got if r]
            return out
        self.err(f"{what}.{key}: a reference, a list of them, or a map of port names to them", w, "bad-ref")
        return {}

    def driven(self, m: Map, what: str) -> tuple[list[Ref], dict[str, int], set[str], dict[str, str]]:
        """``driven-by``: what it follows, each reference with an optional sign, ``+stock.x`` (it
        rises when x rises) or ``-auxiliary.y`` (it falls when y rises); unsigned: not known. An
        entry may be written out as a map, ``{cause: +flow.x, instant: true}``, to say the dependence
        is immediate (SPEC §7): the third value is those causes; or ``inferred:``, a link ergostat added (§12e), the
        fourth value."""
        raw = m.get("driven-by")
        if raw is None:
            return [], {}, set(), {}
        if not isinstance(raw, str | list | dict):
            self.err(f"{what}.driven-by: a reference or a list of them (+stock.x, -auxiliary.y, flow.z)", m.at("driven-by"),
                     "bad-ref")
            return [], {}, set(), {}
        refs, signs, instant, inferred = [], {}, set(), {}
        for x in raw if isinstance(raw, list) else [raw]:
            now, by = False, None
            if isinstance(x, dict):
                self.keys(x, LINK_KEYS, f"{what}.driven-by")
                by = self.inferred_value(x.get("inferred"), m.at("driven-by"), f"{what}.driven-by")
                now = x.get("instant", False)
                if not isinstance(now, bool):
                    self.err(f"{what}.driven-by.instant: true or false", m.at("driven-by"), "bad-bool")
                    now = False
                if "cause" not in x:
                    self.err(f"{what}.driven-by: a link written out names its cause (cause: +flow.x)", m.at("driven-by"),
                             "missing-key")
                    continue
                x = x["cause"]
            sign = None
            if isinstance(x, str) and x[:1] in "+-":
                sign, x = (1 if x[0] == "+" else -1), x[1:].strip()
            r = self.ref(x, m.at("driven-by"), f"{what}.driven-by", DRIVERS)
            if r is None:
                continue
            refs.append(r)
            if sign is not None:
                signs[str(r)] = sign
            if now:
                instant.add(str(r))
            if by:
                inferred[str(r)] = by
        return refs, signs, instant, inferred

    def inferred_value(self, v, w, what: str) -> str | None:
        """``inferred:``, what ergostat writes on a part (or a link) a model change added (SPEC §12e): the change's
        item, ``ergostat.model-change/<id>``, or ``true`` where it is not known; ``false`` or none, declared."""
        if v is None or v is False:
            return None
        if v is True:
            return "true"
        if isinstance(v, str) and INFERRED.match(v.strip()):
            return v.strip()
        self.err(f"{what}.inferred: the model change that added it ({MODEL_CHANGE}/<id>), or true", w, "bad-inferred")
        return None

    def inferred(self, m: Map, what: str) -> str | None:
        return self.inferred_value(m.get("inferred"), m.at("inferred"), what) if "inferred" in m else None

    def flag(self, m: Map, key: str, what: str) -> bool:
        v = m.get(key, False)
        if not isinstance(v, bool):
            self.err(f"{what}.{key}: true or false", m.at(key), "bad-bool")
            return False
        return v

    # ---- sections

    def sensors(self, owner: Map, of: Ref, what: str) -> dict[str, Sensor]:
        out = {}
        raw = {}
        if "sensor" in owner and "sensors" in owner:
            self.err(f"{what}: sensor: (one) or sensors: (several by name), not both", owner.at("sensor"), "two-sensor-keys")
        if owner.get("sensor") is not None:
            raw = {"main": owner["sensor"]}
            if isinstance(owner["sensor"], Map):
                owner["sensor"].where = owner["sensor"].where or owner.at("sensor")
        elif owner.get("sensors") is not None:
            raw = owner["sensors"]
            if not isinstance(raw, dict):
                self.err(f"{what}.sensors: a map of sensors by name", owner.at("sensors"), "not-a-map")
                return {}
        for name, s in raw.items():
            sw = f"{what} sensor {name}"
            if not isinstance(s, dict):
                self.err(f"{sw}: a map with run:, query: or manual:", owner.at("sensors") or owner.at("sensor"), "not-a-map")
                continue
            if not NAME.match(str(name)):
                self.err(f"{sw}: a name is lowercase letters, digits and -, starting with a letter", s.where, "bad-name")
            counted = s.get("items") is not None
            changes = s.get("changes")
            self.keys(s, SENSOR_KEYS | (ITEM_SENSOR_KEYS if counted else set()) | ({"changes", "over"} if changes is not None
                                                                                  else {"changes"}), sw)
            kinds = [k for k in ("run", "query", "manual", "items", "changes", "builtin", "daemon") if s.get(k) not in (None, False)]
            if len(kinds) != 1:
                self.err(f"{sw}: exactly one of run:, query:, manual:, items:, changes:, builtin: or daemon: (it has "
                         f"{', '.join(kinds) or 'none'})", s.where, "sensor-kind")
            measure = None
            if s.get("builtin") is not None:
                measure = str(s["builtin"])
                if not is_measure(measure):
                    self.err(f"{sw}.builtin: one of ergostat's built-in measures, {', '.join(MODEL_MEASURES)}, or "
                             f"ergostat.trust.contradicted (or contradictions, verified, unchecked, claims), with @BLOCK, "
                             f"@rung:KIND or @model:MODEL when about one, or ergostat.messages.unrouted (or awaiting, "
                             f"received, routed, delivered, answered, missed, reached), or ergostat.intent.false-done (or "
                             f"false-done-tests, accepted, reopened, judged, met, unmet, contradicted, held, unjudged, "
                             f"overruled, cost), with @KIND when about one, or ergostat.leases.held (or expired, dead, "
                             f"overdue), with @KIND or @BLOCK when about one, or ergostat.actions.held (or approved, auto, "
                             f"denied, ran, failed), with @CLASS, or ergostat.workspaces.free (or in-use, held, quarantined), "
                             f"with @POOL, or ergostat.cost.usd (or tokens, cpu, memory, runs), over the last day or with "
                             f"-hour the last hour, with @BLOCK or @model:MODEL when about one, or ergostat.inbox.waiting (or "
                             f"oldest, asked), or ergostat.interventions.waiting (or per-day, trend, standing, chattering, "
                             f"blocked-hours, top-share), or ergostat.upkeep.index-files (or retired-index-files)",
                             s.at("builtin"), "bad-measure")
                    measure = None
                elif of.kind == "flow":
                    self.err(f"{sw}.builtin: the model's measures are levels, read by a stock or an auxiliary",
                             s.at("builtin"), "bad-measure")
                    measure = None
            if changes is not None and (of.kind != "flow" or changes not in CHANGES):
                self.err(f"{sw}.changes: on a flow, one of {', '.join(CHANGES)}: its rate from its stock's own readings (how "
                         f"much they rose, or fell, per hour)", s.at("changes"), "bad-changes")
                changes = None
            q = s.get("query")
            if q is not None:
                if not isinstance(q, dict) or "source" not in q:
                    self.err(f"{sw}.query: a map naming its source: and the source's own fields (promql:)", s.at("query"),
                             "bad-query")
                    q = None
            parse = s.get("parse")
            if parse is not None:
                try:
                    if re.compile(str(parse)).groups != 1:
                        self.err(f"{sw}.parse: one group, around the number: 'cleaned (\\d+)'", s.at("parse"), "bad-parse")
                except re.error as e:
                    self.err(f"{sw}.parse: not a regular expression ({e})", s.at("parse"), "bad-parse")
            averages = None
            if s.get("averages") is not None:
                if of.kind != "flow" or counted or changes is not None:
                    self.err(f"{sw}.averages: on a flow's run:, query: or manual: sensor, the window its reading is an average "
                             f"over (a count of the last ten minutes, per hour: averages: 10m); items: and changes: say theirs "
                             f"with over:", s.at("averages"), "bad-averages")
                else:
                    averages = self.duration(s, "averages", sw, 0.0)
            run = s.get("run") and str(s["run"])
            if measure:                                 # read by ergostat itself, in a process of its own
                run = f"{shlex.quote(sys.executable)} -m ergostat -C . measure {shlex.quote(measure)}"
            out[str(name)] = Sensor(str(name), of, run=run, query=dict(q) if q else None, averages=averages, builtin=measure,
                                    items=self.item_sensor(s, of, sw) if counted else None,
                                    changes={"what": changes, "over": self.duration(s, "over", sw, 3600.0)} if changes else None,
                                    manual=bool(s.get("manual")), every=self.duration(s, "every", sw, 60.0),
                                    cron=self.cron(s, "cron", sw),
                                    timeout=self.duration(s, "timeout", sw, 120.0 if measure else 30.0),
                                    parse=str(parse) if parse is not None else None, unit=self.text(s, "unit"),
                                    description=self.text(s, "description"), where=s.where,
                                    daemon=s.get("daemon"), push=s.get("push") is True)
        return out

    def item_sensor(self, s: Map, of: Ref, sw: str) -> dict | None:
        """``items: ticket`` and how to count them: on a stock, how many are in ``state:`` (or the
        hours the ``oldest`` has been in its state, or the ``age`` of the oldest since it was first seen); on a
        flow, the rate per hour ``entering:`` or ``leaving:`` a state, over the last ``over:``. Kinds and states are
        checked once all are read."""
        q: dict = {"kind": str(s["items"]), "where": {}}
        st = s.get("state")
        if st is not None:
            q["state"] = [str(x) for x in st] if isinstance(st, list) else [str(st)]
        for k in ("entering", "leaving"):
            if s.get(k) is not None:
                q[k] = str(s[k])
        if of.kind != "flow":
            for k in ("entering", "leaving", "over", "sum"):
                if s.get(k) is not None:
                    self.err(f"{sw}.{k}: a stock counts the items in a state (state:); entering:, leaving:, over: and "
                             f"sum: measure a flow", s.at(k), "items-on-stock")
            m = s.get("measure", "count")
            if m not in ("count", "oldest", "age"):
                self.err(f"{sw}.measure: count (how many), oldest (the oldest one's hours in its state) or age (the "
                         f"oldest one's hours since it was first seen)", s.at("measure"), "bad-measure")
            q["measure"] = m
        else:
            if s.get("state") is not None or s.get("measure") is not None:
                self.err(f"{sw}: a flow is measured by items entering: or leaving: a state, not by state: or measure:",
                         s.at("state") or s.at("measure"), "items-on-flow")
            if ("entering" in q) == ("leaving" in q):
                self.err(f"{sw}: on a flow, say entering: or leaving: (the state the items move into or out of)", s.where,
                         "items-on-flow")
            q["over"] = self.duration(s, "over", sw, 3600.0)
            if s.get("sum") is not None:                 # the rate of a field summed over the items moving, not their count
                q["sum"] = str(s["sum"])
        w = s.get("where")
        if w is not None:
            if not isinstance(w, dict):
                self.err(f"{sw}.where: a map of field: value (or a list of values)", s.at("where"), "not-a-map")
            else:
                q["where"] = {str(k): (list(v) if isinstance(v, list) else v) for k, v in w.items()}
                self.where_values(q["where"], w, sw, sw.split(" sensor ")[0].replace(" ", ".", 1))
        q["at"] = s.where
        return q

    def where_values(self, where: dict, w: Map, sw: str, about: str = "") -> None:
        """``where:`` compares typed values (SPEC §6): a number matches a number, never its text. Note each value
        whose meaning changed when it stopped comparing text (a number or a boolean written bare, which once also
        matched a field holding its text); a value YAML read as neither (a date) is compared as its text."""
        for k, v in where.items():
            vals = v if isinstance(v, list) else [v]
            fixed = [x.isoformat() if hasattr(x, "isoformat") else x for x in vals]
            if fixed != vals:
                where[k] = fixed if isinstance(v, list) else fixed[0]
            typed = [x for x in fixed if isinstance(x, bool | int | float)]
            if typed:
                x = typed[0]
                shown = str(x).lower() if isinstance(x, bool) else str(x)
                kind = "a boolean" if isinstance(x, bool) else "a number"
                self.problems.append(Problem(
                    "finding", f"{sw}.where.{k}: {shown} is compared as {kind}: it matches a field holding {kind}"
                    f"{' (1 and 1.0 alike)' if kind == 'a number' else ''}, and no longer a field holding the text "
                    f"{shown!r}; write \"{shown}\" (quoted) if the field holds text", w.at(k) if hasattr(w, "at") else None,
                    "where-typed", about))

    def item_kind(self, name: str, m: Map, what: str) -> ItemKind:
        self.keys(m, ITEM_KEYS, what)
        id = m.get("id")
        if not isinstance(id, str) or "/" not in id or id.startswith("/"):
            self.err(f"{what}.id: which ids are this kind, a pattern with a / in it, like github/pull_request/* "
                     f"(ids without a / are ergostat's own parts)", m.at("id") or m.where, "bad-id")
            id = f"{name}/*"
        states = m.get("states") or []
        if not isinstance(states, list) or not all(isinstance(x, str) and NAME.match(x) for x in states):
            self.err(f"{what}.states: a list of state names (lowercase letters, digits and -); the first is where a new "
                     f"item starts", m.at("states"), "bad-states")
            states = []
        on = m.get("on") or {}
        moves = {}
        if not isinstance(on, dict):
            self.err(f"{what}.on: a map of event type: the state it moves the item to", m.at("on"), "not-a-map")
        else:
            from ..runner import TYPE_NAME
            for ev, st in on.items():
                if not isinstance(ev, str) or not TYPE_NAME.match(ev):
                    self.err(f"{what}.on: {ev!r} is not an event type (lowercase words joined by dots: ticket.opened)",
                             on.at(ev), "bad-type")
                elif str(st) not in states:
                    self.err(f"{what}.on.{ev}: {st!r} is not one of its states ({', '.join(states) or 'none'})", on.at(ev),
                             "unknown-state")
                else:
                    moves[ev] = str(st)
            if moves and not states:
                self.err(f"{what}: on: moves items between states; list them under states:", m.where, "bad-states")
        show = m.get("show") or []
        if not isinstance(show, list):
            self.err(f"{what}.show: a list of field names", m.at("show"), "bad-show")
            show = []
        from .ir import FORMATS
        formats = {}
        raw = m.get("formats") or {}
        if not isinstance(raw, dict):
            self.err(f"{what}.formats: a map of field: format ({', '.join(FORMATS)})", m.at("formats"), "not-a-map")
        else:
            for f, fmt in raw.items():
                if str(fmt) not in FORMATS:
                    self.err(f"{what}.formats.{f}: {fmt!r} is not a format ({', '.join(FORMATS)})", raw.at(f), "bad-format")
                else:
                    formats[str(f)] = str(fmt)
        from .changes import RULES
        rules = {}
        raw = m.get("fold") or {}
        if not isinstance(raw, dict):
            self.err(f"{what}.fold: a map of field: how its events' data folds into it ({', '.join(RULES)})", m.at("fold"),
                     "not-a-map")
        else:
            for f, rule in raw.items():
                if not isinstance(f, str) or not f:
                    self.err(f"{what}.fold: {f!r} is not a field name", raw.at(f), "bad-fold")
                elif str(rule) not in RULES:
                    self.err(f"{what}.fold.{f}: {rule!r} is not a fold rule ({', '.join(RULES)})" + self.suggest(str(rule), RULES),
                             raw.at(f), "bad-fold")
                else:
                    rules[f] = str(rule)
        from ..leases import compile as leases
        from . import joins
        from .relations import compile_relations
        relations = compile_relations(self, m, what, rules)
        about = m.get("about")                       # the field naming the parts it is about (SPEC §5a, *About*)
        if about is not None and (not isinstance(about, str) or not about or about in relations
                                  or rules.get(about, "replace") != "replace"):
            self.err(f"{what}.about: the name of a field (not a relation) holding the parts of the model it is about "
                     f"(goal.x, stock.y), folded by replace: an event that sets it replaces the list", m.at("about"),
                     "bad-about")
            about = None
        return ItemKind(name, id, states=list(states), on=moves, show=[str(x) for x in show], formats=formats,
                        system=self.system("items", name, m), description=self.text(m, "description"), where=m.where,
                        fold=rules, lease=leases.terms(self, m, "lease", what), relations=relations,
                        join=joins.compile_join(self, m, what), about=about)

    def counted(self, spec: Spec) -> None:
        """Sensors that count items name a kind and its states."""
        for s in spec.sensors():
            q = s.items
            if q is None:
                continue
            sw, w = f"sensor {s.of.name}.{s.name}", q.pop("at", None) or s.where
            k = spec.items.get(q["kind"])
            if k is None:
                self.err(f"{sw}.items: {q['kind']!r} is not a kind of item" + self.suggest(q["kind"], spec.items), w,
                         "unknown-ref")
                continue
            for st in [*(q.get("state") or []), *[q[x] for x in ("entering", "leaving") if x in q]]:
                if st not in k.states:
                    self.err(f"{sw}: {st!r} is not a state of {k.name} ({', '.join(k.states) or 'it has none'})", w,
                             "unknown-state")

    def watched(self, spec: Spec) -> None:
        """A flow measured by its stock's changes watches its one stock: it rises by an inflow, falls by
        an outflow, and either way by a two-way flow."""
        for f in spec.flows.values():
            for s in f.sensors.values():
                if not s.changes:
                    continue
                sw, what = f"flow {f.name} sensor {s.name}", s.changes["what"]
                if f.source and f.target:
                    self.err(f"{sw}: changes: reads one stock, and {f.name} runs between two (measure it some other way)",
                             s.where, "bad-changes")
                elif what == "rises" and not f.target or what == "falls" and not f.source:
                    self.err(f"{sw}: changes: {what} measures an {'in' if what == 'rises' else 'out'}flow; {f.name} "
                             f"{'drains' if f.source else 'fills'} its stock ({'falls' if f.source else 'rises'})", s.where,
                             "bad-changes")
                elif what in ("net", "rest") and not f.two_way:
                    self.err(f"{sw}: changes: {what} may read either way: give the flow two-way: true", s.where, "bad-changes")
                elif what == "rest" and sum(1 for g in spec.flows.values() if (f.target or f.source) in (g.source, g.target)
                                            for x in g.sensors.values()
                                            if x.changes and x.changes["what"] == "rest") > 1:
                    self.err(f"{sw}: changes: rest is what the stock's other flows leave; only one of its flows may read it",
                             s.where, "bad-changes")
                elif (st := f.target or f.source) in spec.stocks:
                    if not any(x.measured or x.manual for x in spec.stocks[st].sensors.values()):
                        self.err(f"{sw}: changes: reads stock {st}'s readings, and nothing measures it", s.where, "bad-changes")
                    s.changes["stock"] = st
                    s.changes["sign"] = 1 if f.target else -1     # its direction: into its stock, or out of it

    def claims(self, spec: Spec) -> None:
        """``claims:``: the checks the project declares (SPEC §12g). ``tests`` is the project's test command, run to
        check "tests pass"; any other name is a kind of claim of the project's own, checked by its command."""
        for name, m, what in self.named("claims"):
            self.keys(m, {"run", "in", "says", "timeout", "description"}, what)
            if name in CLAIM_CHECKS and name != "tests":
                self.err(f"{what}: {name} is a built-in check (only tests: takes a command); name it something else",
                         m.where, "reserved-name")
                continue
            if not m.get("run"):
                self.err(f"{what}: run: the command that checks it (exit 0: what was claimed holds)", m.where, "missing-key")
                continue
            says = m.get("says")
            if says is not None:
                try:
                    re.compile(str(says))
                except re.error as e:
                    self.err(f"{what}.says: a pattern over what a claim says ({e})", m.at("says"), "bad-pattern")
                    says = None
            where = str(m.get("in") or ".")
            if where.startswith("/") or ".." in where.split("/"):
                self.err(f"{what}.in: a folder inside the model's, written from it", m.at("in"), "bad-path")
                where = "."
            spec.claims[name] = ClaimCheck(name, str(m["run"]), where, None if says is None else str(says),
                                           self.duration(m, "timeout", what, 600.0), self.text(m, "description"), m.where)

    def messages(self, spec: Spec) -> None:
        """``messages:``: how the owner's messages are routed and what a message about finished work does (SPEC §12h)."""
        m, w = self.doc.messages, self.doc.messages_at
        if m is None:
            return
        if not isinstance(m, dict):
            self.err("messages: a map (classifier:, finished:, follow-up:, reopen-to:, done:, paused:)", w, "not-a-map")
            return
        self.keys(m, {"classifier", "finished", "follow-up", "reopen-to", "done", "paused", "description"}, "messages")
        got = Messages(where=getattr(m, "where", None) or w)
        c = m.get("classifier")
        if c is not None:
            b = spec.blocks.get(str(c).removeprefix("block."))
            if b is None or not b.machine:
                self.err(f"messages.classifier: a machine block (an ai block on a cheap model, or a program) that routes "
                         f"what nothing in a message names; {c!r} is not one" + self.suggest(str(c), spec.blocks),
                         m.at("classifier"), "unknown-ref", f"block.{c}")
            else:
                got.classifier = b.name
        fin = str(m.get("finished") or "follow-up")
        if fin not in ("follow-up", "reopen", "attention"):
            self.err("messages.finished: follow-up (a new item linked to the finished one), reopen (it moves back) or "
                     "attention (it waits for the owner)", m.at("finished"), "bad-value")
            fin = "follow-up"
        got.finished = fin
        fu = m.get("follow-up")
        if fu is not None:
            if str(fu) not in spec.items or str(fu).startswith("ergostat."):
                self.err(f"messages.follow-up: the kind of item a follow-up is made as; {fu!r} is not one of the model's "
                         f"kinds" + self.suggest(str(fu), spec.items), m.at("follow-up"), "unknown-ref")
            else:
                got.follow_up = str(fu)
        for key, attr in (("reopen-to", "reopen_to"), ("done", "done"), ("paused", "paused")):
            raw = m.get(key)
            if raw is None:
                continue
            if not isinstance(raw, dict):
                self.err(f"messages.{key}: a map of item kind to {'a state' if key == 'reopen-to' else 'its states'}",
                         m.at(key), "not-a-map")
                continue
            for kind, v in raw.items():
                k = spec.items.get(str(kind))
                vals = [str(x) for x in (v if isinstance(v, list) else [v])]
                if k is None:
                    self.err(f"messages.{key}: {kind!r} is not an item kind" + self.suggest(str(kind), spec.items),
                             raw.at(kind) if hasattr(raw, "at") else m.at(key), "unknown-ref")
                    continue
                bad = [x for x in vals if x not in k.states]
                if bad or (key == "reopen-to" and len(vals) != 1):
                    self.err(f"messages.{key}.{kind}: {'one of' if key == 'reopen-to' else 'states of'} its states "
                             f"({', '.join(k.states)})", raw.at(kind) if hasattr(raw, "at") else m.at(key), "bad-value")
                    continue
                getattr(got, attr)[str(kind)] = vals[0] if key == "reopen-to" else vals
        spec.messages = got

    def named(self, section: str):
        for name, m in self.doc.sections[section].items():
            what = f"{SINGULAR.get(section, section[:-1])} {name}"
            w = self.doc.defined[(section, name)]
            if not isinstance(name, str) or not NAME.match(name):
                self.err(f"{what}: a name is lowercase letters, digits and -, starting with a letter", w, "bad-name")
                continue
            if not isinstance(m, dict):
                self.err(f"{what}: a map of its keys (block style: one key per line)", w, "not-a-map")
                continue
            if m.where is None:
                m.where = w
            yield name, m, what

    def system(self, section: str, name: str, m: Map) -> str | None:
        return m.get("system") or self.doc.defaults.get((section, name), {}).get("system")

    def run(self) -> Spec:
        d = self.doc
        spec = Spec(d.name, d.root, d.files, purpose=d.purpose)
        spec.uses = dict(d.uses)
        spec.local = dict(d.local)
        spec.template_files = sorted({Path(u["path"]) for u in d.uses.values() if u.get("owners")})
        spec.remotes = dict(d.remotes)                 # each remote system (SPEC §4c): its model's file reloads this one
        spec.remote_files = [Path(r["dir"]) / "model.json" for r in d.remotes.values()]
        if d.keep is not None:
            try:
                spec.keep = parse_duration(d.keep, "keep")
            except DurationError as e:
                self.err(str(e), None, "bad-duration")
        from ..storage import parse as storage
        wrong: list[str] = []
        spec.storage = storage(d.storage, wrong)
        for msg in wrong:
            self.err(msg, None, "bad-storage")
        from ..intake.config import parse as intake
        wrong = []
        spec.intake = intake(d.intake, wrong)
        for msg in wrong:
            self.err(msg, None, "bad-intake")
        from ..webaccess import parse as web
        wrong = []
        spec.web = web(d.web, wrong)
        for msg in wrong:
            self.err(msg, None, "bad-web")
        if d.budget is not None:                       # the day's AI budget (SPEC §9.9): each bad key or value its own error
            from ..costs import budget
            spec.budget, wrong = budget.parse(d.budget)
            for msg in wrong:
                self.err(msg, getattr(d.budget, "where", None), "bad-budget")
        if spec.web.open:
            self.problems.append(Problem("finding", f"web: {', '.join(spec.web.names)} is public and read only, with no login "
                                         "(open: read): anyone who reaches it reads everything the page shows", None, "web-public"))
        for name, m, what in self.named("systems"):
            self.keys(m, {"description", "within", "show"}, what)
            spec.systems[name] = self.text(m, "description")
            if m.get("within") is not None:
                spec.within[name] = str(m["within"])
            if m.get("show") is not None:
                spec.show[name] = [r for rs in self.refs(m, "show", what, ("stock", "flow", "auxiliary")).values() for r in rs]
        for name, parent in list(spec.within.items()):
            w = self.doc.defined[("systems", name)]
            if parent not in spec.systems:
                self.err(f"system {name}.within: {parent!r} is not a system" + self.suggest(parent, spec.systems), w,
                         "unknown-ref", f"system.{parent}")
                del spec.within[name]
            elif name in spec.chain(parent):
                self.err(f"system {name}.within: {parent} is within {name}: systems nest, they do not go round", w,
                         "system-cycle")
                del spec.within[name]
        for name, m, what in self.named("sources"):
            t = m.get("type")
            if t not in SOURCE_TYPES:
                self.err(f"{what}.type: one of {', '.join(SOURCE_TYPES)}", m.at("type"), "bad-type")
                continue
            self.keys(m, SOURCE_TYPES[t], what)
            if t in ("prometheus", "ergostat") and not m.get("url"):
                self.err(f"{what}: a {t} source needs url:", m.where, "missing-key")
            spec.sources[name] = Source(name, t, self.text(m, "url"), m.where, self.text(m, "token-file"))
        for name, m, _ in self.named("items"):
            k = self.item_kind(name, m, f"item kind {name}")
            if k.id.startswith("ergostat."):
                self.err(f"item kind {name}.id: ids starting ergostat. are ergostat's own ({MODEL_CHANGE}/*)", m.at("id") or m.where,
                         "reserved-id")
                continue
            spec.items[name] = k
        spec.items[MODEL_CHANGE] = model_change_kind()       # built in: every change to the model (SPEC §12e)
        spec.items[MODELLING_REQUEST] = modelling_request_kind()   # built in: work for modelling, from what check finds
        spec.items[CLAIM] = claim_kind()                     # built in: what blocks said they did, checked (SPEC §12g)
        spec.items[MESSAGE] = message_kind()                 # built in: the owner's messages, routed (SPEC §12h)
        spec.items[VERDICT] = verdict_kind()                 # built in: the intent judge's verdicts on work (SPEC §12i)
        from ..repair import BLOCKS, FAILURE, failure_kind
        if BLOCKS[0] in self.doc.sections.get("blocks", {}):
            spec.items[FAILURE] = failure_kind()             # built in, under use: repair: failing runs (SPEC §12r)
            if "--approver ai" in str(self.doc.sections["blocks"][BLOCKS[0]].get("run")):
                self.err("use: repair: approver: ai: not yet: a sound allowlist guard is needed (GAPS)",
                         self.doc.defined[("blocks", BLOCKS[0])], "not-yet")
        if any(u.get("template") == "interventions" for u in d.uses.values()):
            from .ir import MODEL_REQUEST, model_request_kind
            spec.items[MODEL_REQUEST] = model_request_kind()  # built in, with the interventions loop (SPEC §12p)
        self.claims(spec)
        from ..decisions.kinds import builtin as intent_kinds
        spec.items.update(intent_kinds())                    # built in: the owner's decisions and corrections (SPEC §5a)
        from ..recipes.uses import context_kind
        spec.items[CONTEXT] = context_kind()                 # built in: each use of a recipe, and its outcome (SPEC §12j)
        from ..reports.kind import builtin as report_kinds
        spec.items.update(report_kinds())                    # built in: reports upstream, for the owner (SPEC §12m)
        self.parameters(spec)
        for name, m, what in self.named("stocks"):
            self.keys(m, STOCK_KEYS, what)
            st = Stock(name, self.text(m, "unit"), self.number(m, "limit", what), self.number(m, "initial", what),
                       self.system("stocks", name, m), self.text(m, "description"),
                       cumulative=self.flag(m, "cumulative", what), inferred=self.inferred(m, what), where=m.where,
                       observe=self.flag(m, "observe", what))
            st.sensors = self.sensors(m, Ref("stock", name), what)
            st.rate_unit = self.rate_unit(m, what)
            st.formerly = self.formerly(m, what)
            spec.stocks[name] = st
        for name, m, what in self.named("flows"):
            self.keys(m, FLOW_KEYS, what)
            if m.get("from") is None and m.get("to") is None:
                self.err(f"{what}: give it from:, to:, or both (the stocks it drains and fills; leaving one out means "
                         f"outside the system)", m.where, "flow-without-ends")
            f = Flow(name, m.get("from") and str(m["from"]), m.get("to") and str(m["to"]), self.text(m, "unit"),
                     self.number(m, "rate", what), self.system("flows", name, m), self.text(m, "description"),
                     two_way=self.flag(m, "two-way", what), inferred=self.inferred(m, what), where=m.where)
            for end, key in ((f.source, "from"), (f.target, "to")):
                if end is not None and end not in d.sections["stocks"]:
                    self.err(f"{what}.{key}: {end!r} is not a stock" + self.suggest(end, d.sections["stocks"]),
                             m.at(key), "unknown-ref", f"stock.{end}")
            f.sensors = self.sensors(m, Ref("flow", name), what)
            f.rate_unit = self.rate_unit(m, what)
            f.driven_by, f.polarity, f.instant, f.inferred_links = self.driven(m, what)
            f.defined = d.defined[("flows", name)]
            f.formerly = self.formerly(m, what)
            spec.flows[name] = f
        for section in ("auxiliaries", "variables"):        # variables: the old name, still read
            for name, m, what in self.named(section):
                what = f"auxiliary {name}"
                if section == "variables":
                    self.deprecated("variables", self.doc.defined[(section, name)])
                    if name in spec.auxiliaries:
                        self.err(f"{what} is defined twice: under auxiliaries: and under variables: (its old name)",
                                 self.doc.defined[(section, name)], "defined-twice", f"auxiliary.{name}")
                        continue
                self.keys(m, AUXILIARY_KEYS, what)
                v = Auxiliary(name, self.text(m, "unit"), self.system(section, name, m), self.text(m, "description"),
                              exogenous=self.flag(m, "exogenous", what), inferred=self.inferred(m, what), where=m.where)
                v.sensors = self.sensors(m, Ref("auxiliary", name), what)
                v.driven_by, v.polarity, v.instant, v.inferred_links = self.driven(m, what)
                v.defined = self.doc.defined[(section, name)]
                v.formerly = self.formerly(m, what)
                if v.exogenous and v.driven_by:
                    self.err(f"{what}: exogenous (an input from outside the model) and driven-by something in it: one or the "
                             f"other", m.at("exogenous"), "exogenous-driven")
                spec.auxiliaries[name] = v
        for name, m, what in self.named("goals"):
            self.keys(m, GOAL_KEYS, what)
            has = [k for k in ("stock", "flow", "auxiliary", "variable") if m.get(k) is not None]
            of = None
            if len(has) != 1:
                self.err(f"{what}: say what it is about with exactly one of stock:, flow: or auxiliary:", m.where, "goal-of")
            else:
                key = has[0]
                k = "auxiliary" if key == "variable" else key
                if key == "variable":
                    self.deprecated("goal-variable", m.at(key))
                target = str(m[key])
                known = {"stock": d.sections["stocks"], "flow": d.sections["flows"],
                         "auxiliary": {**d.sections["variables"], **d.sections["auxiliaries"]}}[k]
                if target not in known:
                    self.err(f"{what}.{key}: {target!r} is not a{'n' if k[0] == 'a' else ''} {k}" + self.suggest(target, known),
                             m.at(key), "unknown-ref", f"{k}.{target}")
                of = Ref(k, target)
            hold = Setpoint.parse(m.get("hold"))
            if hold is None:
                self.err(f"{what}.hold: a setpoint like \"<= 20\", \">= 5\" or \"== 50\", quoted", m.at("hold") or m.where,
                         "bad-setpoint")
            tol = self.number(m, "tolerance", what) or 0.0
            if tol < 0:
                self.err(f"{what}.tolerance: 0 or more", m.at("tolerance"), "bad-number")
            process = self.process(m, what) if m.get("process") is not None else None
            per = self.per(spec, m, of, what, name)
            if of and hold:
                spec.goals[name] = Goal(name, of, hold, tol, bool(m.get("critical")), self.text(m, "owner"),
                                        self.system("goals", name, m), self.text(m, "description"), m.where, process, per,
                                        on_stale=self.on_stale(m, what))
        for name, m, what in self.named("agents"):
            self.keys(m, AGENT_KEYS, what)
            kind = m.get("kind")
            if kind is not None and kind not in AGENT_KINDS:
                self.err(f"{what}.kind: one of {', '.join(AGENT_KINDS)}", m.at("kind"), "bad-kind")
                kind = None
            n = m.get("at-once", 1)
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                self.err(f"{what}.at-once: a whole number, 1 or more", m.at("at-once"), "bad-number")
                n = 1
            spec.agents[name] = Agent(name, kind, bool(m.get("external")), n, m.get("model") and str(m["model"]),
                                      m.get("cost") and str(m["cost"]), m.get("host") and str(m["host"]),
                                      self.text(m, "description"), m.where)
        from ..recipes import compile as recipes
        recipes.contexts(self, spec)                         # contexts: the projection recipes (SPEC §12j)
        for name, m, what in self.named("blocks"):
            b = self.block(name, m, what)
            if b:
                spec.blocks[name] = b
        recipes.blocks(self, spec)                           # a block's context: and review:
        from ..actions import compile as gated
        from ..workspaces import compile as pools
        pools.workspaces(self, spec)                         # workspaces: the pools AI blocks' runs work in (SPEC §12k)
        gated.actions(self, spec)                            # actions: what sessions may ask for, gated (SPEC §12k)
        gated.blocks(self, spec)  # ai: workdir, workspace, read, tools, actions; program: workspace, actions
        from ..inbox import config as notify
        notify.parse(self, spec)                             # notify: each channel a gated action notify.NAME (SPEC §12o)
        if spec.actions:
            spec.items[ACTION] = action_kind()               # built in, when there are any: gated actions asked for
        if spec.workspaces:
            spec.items[WORKSPACE] = workspace_kind()         # built in, when there are any: the pools' workspaces
        from ..leases import compile as leases
        leases.section(self, spec)                           # leases: each tier's terms (SPEC §9.5)
        from ..daemons import config as daemons
        daemons.section(self, spec)                          # daemons: the long-lived runners (SPEC §9.7)
        leases.check(self, spec)                             # what each block takes: its kind gains leased and dead
        from . import triggers
        triggers.check(self, spec)                           # blocks started by an event, and their loops (SPEC §9.3)
        judges = [b for b in spec.blocks.values() if b.type == "judge" and b.params.get("judge", "model") == "model"]
        for b in judges[1:]:
            self.err(f"block {b.name}: one judge of changes to the model at most ({judges[0].name} is one)", b.where,
                     "two-judges")
        intents = [b for b in spec.blocks.values() if b.type == "judge" and b.params.get("judge") == "intent"]
        for b in intents[1:]:
            self.err(f"block {b.name}: one intent judge at most ({intents[0].name} is one)", b.where, "two-judges")
        for b in intents:
            for kn, ik in b.params["intent"].kinds.items():
                k = spec.items.get(kn)
                where = f"block {b.name}.kinds.{kn}"
                if k is None or kn.startswith("ergostat."):
                    own = ", ".join(x for x in spec.items if not x.startswith("ergostat."))
                    self.err(f"{where}: an item kind of the model's own ({own})", b.where, "bad-ref")
                    continue
                for st in [ik.at, *ik.accepted, *([ik.reopen_to] if ik.reopen_to else [])]:
                    if st not in k.states:
                        self.err(f"{where}: {st!r} is not a state of {kn} ({', '.join(k.states) or 'it has none'})", b.where,
                                 "bad-state")
                if not ik.accepted:
                    ik.accepted = [k.states[-1]] if k.states and k.states[-1] != ik.at else []
                if ik.repo is None and "tests" in spec.claims:
                    ik.repo = spec.claims["tests"].in_
        if judges:
            spec.improve = judges[0].params["policy"]
            spec.improve.block = judges[0].name
        self.implied(spec)
        for name, m, what in self.named("loops"):
            self.keys(m, {"through", "goal", "description"}, what)
            through = [r for rs in self.refs(m, "through", what, ("stock", "flow", "auxiliary", "goal", "block")).values()
                       for r in rs]
            goal = m.get("goal")
            if (goal is None) == (not through):
                self.err(f"{what}: name it by the parts it runs through (through: [flow.x, stock.y]) or by the goal it seeks "
                         f"(goal: x), one of the two", m.where, "loop-of")
                continue
            if goal is not None and str(goal) not in spec.goals:
                self.err(f"{what}.goal: {goal!r} is not a goal" + self.suggest(str(goal), spec.goals), m.at("goal"),
                         "unknown-ref", f"goal.{goal}")
                continue
            spec.named_loops[name] = NamedLoop(name, through, goal and str(goal), self.text(m, "description"), m.where)
        for b in spec.blocks.values():                       # an auxiliary a block sets is read as what it was set to
            for t in b.targets():
                v = spec.auxiliaries.get(t.name) if t.kind == "auxiliary" else None
                if v is not None and "set" not in v.sensors:
                    v.sensors["set"] = Sensor("set", Ref("auxiliary", v.name), every=None,
                                              description=f"the value block {b.name} set it to", where=b.where)
        self.messages(spec)
        self.counted(spec)
        from .joins import check_joins
        from .relations import check_relations
        check_relations(self, spec)
        check_joins(self, spec)
        self.references(spec)
        self.equations(spec)
        self.watched(spec)
        self.renamed()
        for x in (*spec.stocks.values(), *spec.flows.values(), *spec.goals.values(), *spec.blocks.values()):
            if x.system and x.system not in spec.systems:      # named by a part, not described: a top-level system
                spec.systems[x.system] = ""
        return spec

    def parameters(self, spec: Spec) -> None:
        """``parameters:``: each a number with its unit (``value: 0.45``, or a duration, ``value: 40s``,
        in hours), to be fitted (``estimate: true``), or a lookup's ``table:``; ``k: 0.45`` for short."""
        from .blocks import TableError, read_table
        for name, m in self.doc.sections["parameters"].items():
            what, w = f"parameter {name}", self.doc.defined[("parameters", name)]
            if not isinstance(name, str) or not NAME.match(name):
                self.err(f"{what}: a name is lowercase letters, digits and -, starting with a letter", w, "bad-name")
                continue
            if name.upper() in FUNCTIONS:
                self.err(f"{what}: {name} is the name of a function; call the parameter something else", w, "bad-name")
                continue
            if not isinstance(m, dict):                    # the short form, k: 0.45
                m2 = Map({"value": m})
                m2.where, m2.lines = w, {"value": w}
                m = m2
            if m.where is None:
                m.where = w
            self.keys(m, PARAMETER_KEYS, what)
            p = Parameter(name, unit=self.text(m, "unit"), estimate=self.flag(m, "estimate", what),
                          description=self.text(m, "description"), system=self.system("parameters", name, m), where=m.where,
                          defined=w, value_at=m.at("value") if "value" in m else None, inferred=self.inferred(m, what))
            v = m.get("value")
            if isinstance(v, str):
                try:
                    p.value = parse_duration(v, f"{what}.value") / 3600.0      # a duration: in hours, the model's time
                    if p.unit and p.unit not in ("h", "hours", "hour"):
                        self.err(f"{what}: a duration ({v}) is a time, in hours; its unit is h (or leave unit: out)",
                                 m.at("unit"), "units")
                    p.unit, p.duration = "h", True
                except DurationError:
                    self.err(f"{what}.value: a number, or a duration like 40s or 2h (read in hours)", m.at("value"),
                             "bad-number")
            elif v is not None:
                p.value = self.number(m, "value", what)
            clock = _clock_words(p.unit) if not p.duration else []
            if clock:
                self.err(f"{what}: its unit ({p.unit}) counts time in {', '.join(clock)}, and the model's time is hours "
                         f"(a rate is per hour, a time in h), so {v} would be read as hours or per hour. Write a time as a "
                         f"duration (value: 30m, read in hours), or the rate per hour (unit: x/h, its value converted)",
                         m.at("unit"), "units")
            if m.get("table") is not None:
                if v is not None:
                    self.err(f"{what}: a value or a table (a lookup), not both", m.at("table"), "bad-table")
                try:
                    p.table = read_table("lookup", m["table"])
                except TableError as e:
                    self.err(f"{what}.table: {e}", m.at("table"), "bad-table")
                if p.estimate:
                    self.err(f"{what}: a table is not estimated (only a value is)", m.at("estimate"), "bad-table")
            if m.get("range") is not None:
                p.range = self.span(m, "range", what, p)
            spec.parameters[name] = p

    def span(self, m: Map, key: str, what: str, p: Parameter) -> tuple[float, float] | None:
        """A parameter's ``range: [low, high]``: what it might be, for sensitivity analysis (SPEC §12b);
        numbers, or durations read in hours as its value is."""
        raw = m.get(key)
        bad = f"{what}.{key}: two values, [low, high], low below high (numbers, or durations like 30s for a time)"
        if p.table:
            self.err(f"{what}: a table has no range (only a value is sampled)", m.at(key), "bad-range")
            return None
        if not isinstance(raw, list) or len(raw) != 2:
            self.err(bad, m.at(key), "bad-range")
            return None
        out = []
        for v in raw:
            if isinstance(v, str):
                try:
                    out.append(parse_duration(v, f"{what}.{key}") / 3600.0)
                    continue
                except DurationError:
                    pass
            if isinstance(v, bool) or not isinstance(v, int | float):
                self.err(bad, m.at(key), "bad-range")
                return None
            out.append(float(v))
        if not out[0] < out[1]:
            self.err(bad, m.at(key), "bad-range")
            return None
        return out[0], out[1]

    def equations(self, spec: Spec) -> None:
        """Each ``equation:`` read, its names resolved (a bare name a parameter, a reference a part),
        a rate written two ways (rate: and equation:) refused, and the order they are worked out in
        found: equations that need each other at once, with no stock or delay between, are an
        algebraic loop."""
        from . import equation as eq
        for section, kind, table in (("flows", "flow", spec.flows), ("auxiliaries", "auxiliary", spec.auxiliaries),
                                     ("variables", "auxiliary", spec.auxiliaries)):
            for name, m in self.doc.sections[section].items():
                x = table.get(name)
                if x is None or not isinstance(m, dict) or m.get("equation") is None:
                    continue
                what, w = f"{kind} {name}.equation", m.at("equation")
                raw = m["equation"]
                if isinstance(raw, int | float) and not isinstance(raw, bool):
                    raw = str(raw)
                try:
                    tree = eq.parse(raw, spec.parameters)
                except eq.EquationError as e:
                    self.err(f"{what}: {e}", w, "bad-equation")
                    continue
                bad = False
                for nm in eq.names(tree):
                    if nm not in spec.parameters:
                        parts = [p for p in nm.split("-") if p]
                        hint = (f"; to subtract, write spaces around the minus: {' - '.join(parts)}"
                                if len(parts) > 1 and all(p in spec.parameters for p in parts) else
                                ": declare it under parameters: (value:, unit:, estimate: true to fit it)"
                                + self.suggest(nm, spec.parameters))
                        self.err(f"{what}: {nm} is not a parameter{hint}", w, "unknown-ref", f"parameter.{nm}")
                        bad = True
                    elif spec.parameters[nm].table and not any(n[0] == "lookup" and n[1] == nm for n in eq.walk(tree)):
                        self.err(f"{what}: {nm} is a lookup (a table): call it, {nm}(x)", w, "bad-equation")
                        bad = True
                for r in eq.refs(tree):
                    k, _, n = r.partition(".")
                    if n not in spec.measured(k):
                        self.err(f"{what}: {r}: {n!r} is not a{'n' if k[0] == 'a' else ''} {k}" + self.suggest(n, spec.measured(k)),
                                 w, "unknown-ref", r)
                        bad = True
                    elif r == f"{kind}.{name}":
                        self.err(f"{what}: it names itself ({r}); what it was a moment ago is a stock", w, "bad-equation")
                        bad = True
                if kind == "flow" and x.rate is not None:
                    self.err(f"{what}: its rate is written twice (rate: and equation:); keep one", w, "two-rates")
                    bad = True
                if kind == "auxiliary" and x.exogenous and eq.refs(tree):
                    self.err(f"{what}: exogenous (from outside the model) and worked out from parts of it: one or the other",
                             w, "exogenous-driven")
                    bad = True
                if not bad:
                    x.equation = Equation(raw.strip(), tree, eq.refs(tree), eq.names(tree), w)
        owned = {f"flow.{f.name}": f.equation for f in spec.flows.values() if f.equation} | \
                {f"auxiliary.{a.name}": a.equation for a in spec.auxiliaries.values() if a.equation}
        state: dict[str, int] = {}

        def visit(n: str, path: list[str]) -> bool:
            state[n] = 1
            for r in eq.instant_refs(owned[n].tree):
                if r not in owned:
                    continue
                if state.get(r) == 1:
                    cyc = path[path.index(r):] + [r]
                    self.err(f"equations {' → '.join(cyc)} need each other at once, with no stock or delay between (an "
                             f"algebraic loop): what one of them depends on a moment later is a stock, or a DELAY1/SMOOTH",
                             owned[r].where, "algebraic-loop")
                    return True
                if state.get(r) is None and visit(r, path + [r]):
                    return True
            state[n] = 2
            return False
        for n in sorted(owned):
            if state.get(n) is None and visit(n, [n]):
                break

    def implied(self, spec: Spec) -> None:
        """A machine block that names a goal runs while that goal is off: ergostat puts the onoff
        block in front of it (one per goal and release point, shared by the blocks that name it),
        so the loop is drawn and run like any other."""
        made: dict[tuple, str] = {}
        for b in list(spec.blocks.values()):
            if not b.machine or not b.goal:
                continue
            if b.goal not in spec.goals:
                continue                                   # reported with the references
            until = b.params.get("until")
            key = (b.goal, str(until) if until else None, b.on_stale)
            if key not in made:
                base = name = f"keep-{b.goal}"
                i = 2
                while name in spec.blocks:
                    name = f"{base}-{i}"
                    i += 1
                params = {"goal": b.goal, **({"until": until} if until else {})}
                spec.blocks[name] = Block(name, "onoff", {}, {"out": []}, params, system=b.system, where=b.where,
                                          implied=True, description=f"implied by {b.name}'s goal: {b.goal}",
                                          on_stale=b.on_stale)
                made[key] = name
            spec.blocks[made[key]].outputs["out"].append(Ref("block", b.name))

    def suggest(self, name: str, among) -> str:
        import difflib
        near = difflib.get_close_matches(name, list(among), n=1)
        return f" (did you mean {near[0]}?)" if near else ""

    def per(self, spec, m, of, what, name) -> str | None:
        """A goal's ``per:`` (SPEC §8): ``item`` or a field, on a stock counted from items; else said, and None."""
        per = m.get("per")
        if per is None:
            return None
        st = spec.stocks.get(of.name) if of and of.kind == "stock" else None
        s = next((x for x in (st.sensors.values() if st else ()) if x.items), None)
        if not isinstance(per, str) or not per:
            self.err(f"{what}.per: item, or the name of a field of its items", m.at("per"), "goal-per")
        elif s is None:
            self.err(f"{what}.per: held per item or group only on a stock counted from items (an items: sensor)",
                     m.at("per"), "goal-per")
        elif per == "item" and (s.items.get("measure") or "count") == "count":
            self.err(f"{what}.per: item: each item counts one; hold each by its age with measure: oldest or age on "
                     f"{of.name}'s sensor, or group them (per: a field)", m.at("per"), "goal-per")
        elif per != "item" and (s.items.get("measure") or "count") == "count" and str(m.get("hold", "")).lstrip()[:1] == ">":
            self.err(f"{what}.per: a floor on each group's count is never broken: a group with no items is no group, so "
                     "none is ever below it. Hold a ceiling (<=), or count what is missing as its own stock",
                     m.at("per"), "goal-per")
        else:
            k = spec.items.get(s.items.get("kind"))
            known = {*k.relations, *k.show, *k.fold, *k.formats, *(s.items.get("where") or {})} if k else set()
            if per != "item" and per.split(".")[0] not in known:
                self.problems.append(Problem("finding", f"{what}.per: {per!r} is neither a relation of {k.name if k else '?'} "
                                             "nor a field its kind shows, folds or matches: an item without it is in no group",
                                             m.at("per"), "goal-per-field", f"goal.{name}"))
            return per
        return None

    def process(self, m: Map, what: str) -> dict | None:
        """A goal's ``process:``: the loop's process, from what its controller moves to what the goal
        holds, first order with dead time (or an integrator), declared or accepted from an
        identification (``identified:``)."""
        pm = m.get("process")
        w = f"{what}.process"
        if not isinstance(pm, dict):
            self.err(f"{w}: a map (gain:, time-constant:, dead-time:)", m.at("process"), "bad-process")
            return None
        self.keys(pm, PROCESS_KEYS, w)
        gain = self.number(pm, "gain", w)
        integrating = bool(pm.get("integrating"))
        tau = self.duration(pm, "time-constant", w) if pm.get("time-constant") is not None else None
        raw = pm.get("dead-time")
        theta = 0.0 if raw in (None, 0, "0", "0s") else self.duration(pm, "dead-time", w, 0.0)
        if gain is None:
            self.err(f"{w}: needs gain:", pm.at("gain") if hasattr(pm, "at") else m.at("process"), "missing-key")
            return None
        if integrating and tau is not None:
            self.err(f"{w}: an integrator has no time-constant:", pm.at("time-constant"), "bad-process")
        if not integrating and tau is None:
            self.err(f"{w}: needs time-constant: (or integrating: true)", m.at("process"), "missing-key")
            return None
        return {"form": "integrating" if integrating else "fopdt", "gain": gain, "tau": tau, "theta": theta,
                "identified": self.text(pm, "identified"), "description": self.text(pm, "description"),
                "where": pm.where if hasattr(pm, "where") else None}

    def block(self, name: str, m: Map, what: str) -> Block | None:
        t = m.get("type")
        if t not in TYPE_KEYS:
            self.err(f"{what}.type: one of {', '.join(BUILTIN)} (built in) or {', '.join(MACHINE)}"
                     + (f"; it says {t!r}" if t is not None else ""), m.at("type") or m.where, "bad-type")
            return None
        allowed = BLOCK_COMMON | TYPE_KEYS[t]
        for k in m:
            if k in allowed:
                continue
            if t in BUILTIN and k in ("agent", "run", "prompt", "ask"):
                self.err(f"{what}: a built-in block ({t}) is computed by ergostat itself: it has no {k}: (no machine "
                         f"runs it)", m.at(k), "builtin-with-machine")
            elif t == "external" and k in ("run", "prompt", "ask"):
                self.err(f"{what}: an external block is performed by something ergostat does not run, so it has no {k}:",
                         m.at(k), "external-with-run")
            elif k == "model" and t != "ai":
                self.err(f"{what}.model: only an ai block names a model", m.at(k), "model-not-ai")
            else:
                self.keys(_one(m, k), allowed, what)
        for k in NEEDS.get(t, []):
            if m.get(k) is None and not (k == "run" and m.get("daemon") is not None):
                self.err(f"{what}: a {t} block needs {k}:", m.where, "missing-key")
        if t == "compare" and m.get("above") is None and m.get("below") is None:
            self.err(f"{what}: a compare block needs above: or below:", m.where, "missing-key")
        if t == "alarm" and m.get("above") is None and m.get("below") is None:
            self.err(f"{what}: an alarm needs above: or below:", m.where, "missing-key")
        if t in ("expr", "select") and m.get("in") is None:
            self.err(f"{what}: a {t} block needs in:", m.where, "missing-key")
        mode = m.get("mode", "auto")
        if mode not in ("auto", "advise"):
            self.err(f"{what}.mode: auto or advise", m.at("mode"), "bad-mode")
        role = m.get("role")
        if role is not None and role not in ("controller", "actuator", "logic"):
            self.err(f"{what}.role: controller, actuator or logic", m.at("role"), "bad-role")
        params = {k: v for k, v in m.items() if k in TYPE_KEYS[t] and (t in BUILTIN or k not in MACHINE_COMMON | {"agent"})}
        for k in ("min", "max"):                           # a machine block's limits, or a built-in's clamp
            if m.get(k) is not None:
                self.number(m, k, what)
        for k in ("gain", "above", "below", "back-above", "back-below", "rate"):
            if m.get(k) is not None:
                self.number(m, k, what)
        if t in MACHINE and m.get("integral-time") is not None:
            params["integral-time"] = self.duration(m, "integral-time", what)
        if t in MACHINE:
            for k in ("deadband", "resolution"):
                if m.get(k) is not None:
                    v = self.number(m, k, what)
                    if v is not None and (v < 0 or (k == "resolution" and v == 0)):
                        self.err(f"{what}.{k}: {'more than 0' if k == 'resolution' else '0 or more'}", m.at(k), "bad-number")
                    params[k] = v
            if m.get("limits") is not None:
                lim = m.get("limits")
                ok = isinstance(lim, list) and len(lim) == 2 and all(isinstance(x, int | float) and not isinstance(x, bool)
                                                                     for x in lim) and lim[0] < lim[1]
                if not ok:
                    self.err(f"{what}.limits: two numbers, the least and the most the setting it steps may take ([5, 95])",
                             m.at("limits"), "bad-number")
                    params.pop("limits", None)
                else:
                    params["limits"] = [float(lim[0]), float(lim[1])]
        for k in ("min-on", "min-off", "delay", "after", "reset", "for"):
            if m.get(k) is not None:
                params[k] = self.duration(m, k, what)
        if t == "external" and m.get("identify") is not None:   # what it reads and sets, to identify its law (SPEC §12d)
            idf, w = m.get("identify"), m.at("identify")
            if not isinstance(idf, dict) or set(idf) != {"input", "output"}:
                self.err(f"{what}.identify: {{input: SIGNAL, output: SIGNAL}}, what it reads and what it sets", w, "bad-ref")
                params.pop("identify", None)
            else:
                got = {k: self.ref(idf[k], w, f"{what}.identify.{k}", ("stock", "flow", "auxiliary")) for k in idf}
                params["identify"] = got if all(got.values()) else None
        if m.get("until") is not None:
            sp = Setpoint.parse(m["until"])
            if sp is None:
                self.err(f"{what}.until: a setpoint like \"<= 15\", quoted", m.at("until"), "bad-setpoint")
            params["until"] = sp
        if t == "select" and m.get("pick") not in (None, "min", "max", "first"):
            self.err(f"{what}.pick: min, max or first", m.at("pick"), "bad-pick")
        if t == "expr" and m.get("expr") is not None:
            from .blocks import ExprError, compile_expr
            try:
                compile_expr(str(m["expr"]))
            except ExprError as e:
                self.err(f"{what}.expr: {e}", m.at("expr"), "bad-expr")
            if m.get("in") is not None and not isinstance(m["in"], dict):
                self.err(f"{what}.in: a map naming each input the expression uses (backlog: stock.backlog)", m.at("in"),
                         "bad-ref")
        if t in ("schedule", "lookup") and m.get("table") is not None:
            from .blocks import TableError, read_table
            try:
                params["table"] = read_table(t, m["table"])
            except TableError as e:
                self.err(f"{what}.table: {e}", m.at("table"), "bad-table")
                params.pop("table", None)
        if t == "ai" and m.get("prompt") is not None:
            p = str(m["prompt"])
            if "\n" not in p and p.endswith((".md", ".txt")) and not files.is_file(self.doc.root / p):
                self.err(f"{what}.prompt: {p} is not a file here", m.at("prompt"), "prompt-missing")
        signs: dict[str, int] = {}
        ins = self.refs(m, "in", what, ("stock", "flow", "auxiliary", "goal", "block"), signs if t in MACHINE or t == "judge" else None)
        for port in list(signs):
            r = (ins.get(port) or [None])[-1]
            if r is not None and r.kind in ("goal", "block"):
                self.err(f"{what}.in.{port}: a sign is written on what a block reads of a stock, flow or auxiliary; how it "
                         f"follows a goal or a block it is commanded by is worked out (SPEC §12a)", m.at("in"), "bad-ref")
                del signs[port]
        outs = self.refs(m, "out", what, ("flow", "auxiliary", "block", "goal"))
        inputs = {}
        for port, refs in ins.items():
            for r in refs:
                inputs[port] = r
        if t == "judge" and m.get("judge", "model") not in JUDGE_MODES:
            self.err(f"{what}.judge: {' or '.join(JUDGE_MODES)} (of changes to the model, or of finished work against "
                     f"the owner's intent)", m.at("judge"), "bad-type")
        if t == "judge" and m.get("judge") == "intent":
            params["intent"] = self.intent_policy(m, what)
            for port, rs in outs.items():
                if port not in INTENT_PORTS or any(r.kind != "flow" for r in rs):
                    self.err(f"{what}.out.{port}: an intent judge reports what it moved on its ports, {', '.join(INTENT_PORTS)}, "
                             f"each a flow (out: {{held: flow.work-held}})", m.at("out"), "bad-ref")
        elif t == "judge":
            for k in ("kinds", "model", "max-cost", "held", "within"):
                if m.get(k) is not None:
                    self.err(f"{what}.{k}: only an intent judge (judge: intent) takes {k}:", m.at(k), "unknown-key")
            params["policy"] = self.judge_policy(m, what)
            for port, rs in outs.items():
                if port not in JUDGE_PORTS or any(r.kind != "flow" for r in rs):
                    self.err(f"{what}.out.{port}: a judge reports what it moved on its ports, {', '.join(JUDGE_PORTS)}, each "
                             f"a flow (out: {{passed: flow.changes-passed}})", m.at("out"), "bad-ref")
        elif t in BUILTIN and any(r.kind == "flow" for rs in outs.values() for r in rs):
            self.err(f"{what}: a built-in block computes a signal; it cannot move a flow. Point it at the block that does "
                     f"(out: block.<worker>)", m.at("out"), "builtin-moves-flow")
        if t in ONE_INPUT and len(inputs) > 1:
            self.err(f"{what}: a {t} block takes one input", m.at("in"), "too-many-inputs")
        if t in ONE_INPUT and not inputs:
            self.err(f"{what}: a {t} block needs in: (the signal it works on)", m.where, "missing-key")
        from ..leases import compile as leases
        from . import triggers
        lease_keys = {"takes": leases.takes(self, m, what), **dict(zip(("pool", "pool_now"), leases.pool(self, m, what), strict=True)),
                      "lease": leases.terms(self, m, "lease", what), "on": triggers.compile_on(self, m, what)} \
            if t in MACHINE else {}
        return Block(name, t, inputs, outs, params, signs=signs, agent=m.get("agent") and str(m["agent"]), role=role,
                     **lease_keys,
                     system=self.system("blocks", name, m), description=self.text(m, "description"),
                     every=self.duration(m, "every", what), cron=self.cron(m, "cron", what),
                     timeout=self.duration(m, "timeout", what, 300.0), max=self.number(m, "max", what) if t in MACHINE else None,
                     min=self.number(m, "min", what) if t in MACHINE else None, mode=mode, where=m.where,
                     on_stale=self.on_stale(m, what))

    def references(self, spec: Spec) -> None:
        """Every reference resolves, to the right kind of thing; one actuator per flow; no algebraic
        loop among the built-ins; agents can run their blocks; units agree."""
        def exists(r: Ref) -> str | None:
            if r.kind == "stock":
                st = spec.stocks.get(r.name)
                if st is None:
                    return f"{r.name!r} is not a stock" + self.suggest(r.name, spec.stocks)
                if r.port and r.port not in st.sensors and not (st.sensors and r.port in ("estimate", "uncertainty")):
                    return f"stock {r.name} has no sensor {r.port!r} (it has: {', '.join(st.sensors) or 'none'})"
            elif r.kind == "flow":
                f = spec.flows.get(r.name)
                if f is None:
                    return f"{r.name!r} is not a flow" + self.suggest(r.name, spec.flows)
                if r.port and r.port not in f.sensors:
                    return f"flow {r.name} has no sensor {r.port!r}"
            elif r.kind == "auxiliary":
                v = spec.auxiliaries.get(r.name)
                if v is None:
                    return f"{r.name!r} is not an auxiliary" + self.suggest(r.name, spec.auxiliaries)
                if r.port and r.port not in v.sensors:
                    return f"auxiliary {r.name} has no sensor {r.port!r}"
            elif r.kind == "goal":
                if r.name not in spec.goals:
                    return f"{r.name!r} is not a goal" + self.suggest(r.name, spec.goals)
                if r.port not in (None, "error", "off"):
                    return f"a goal's ports are .error and .off ({r} names {r.port!r})"
            elif r.kind == "block":
                b = spec.blocks.get(r.name)
                if b is None:
                    return f"{r.name!r} is not a block" + self.suggest(r.name, spec.blocks)
            return None

        for name, refs in spec.show.items():
            for r in refs:
                if (why := exists(r)) is not None:
                    self.err(f"system {name}.show: {why}", self.doc.defined.get(("systems", name)), "unknown-ref", str(r))
        for lp in spec.named_loops.values():
            for r in lp.through:
                if (why := exists(r)) is not None:
                    self.err(f"loop {lp.name}.through: {why}", lp.where, "unknown-ref", str(r))
        for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
            for f in table.values():
                for r in f.driven_by:
                    if (why := exists(r)) is not None:
                        self.err(f"{kind} {f.name}.driven-by: {why}", f.where, "unknown-ref", str(r))
                    elif r == Ref(kind, f.name):
                        self.err(f"{kind} {f.name}.driven-by: it does not drive itself", f.where, "bad-ref")
        setters: dict[str, str] = {}
        for b in spec.blocks.values():
            what = f"block {b.name}"
            w = b.where
            for r in b.inputs.values():
                if (why := exists(r)) is not None:
                    self.err(f"{what}.in: {why}", w, "unknown-ref", str(r))
                elif r.kind == "block" and r.port:
                    src = spec.blocks[r.name]
                    if src.outputs and r.port not in src.outputs:
                        self.err(f"{what}.in: block {r.name} has no output {r.port!r} (it has: {', '.join(src.outputs)})",
                                 w, "unknown-ref", str(r))
            for k, r in (b.params.get("identify") or {}).items() if b.type == "external" else ():
                if (why := exists(r)) is not None:
                    self.err(f"{what}.identify.{k}: {why}", w, "unknown-ref", str(r))
            for r in b.targets():
                if (why := exists(r)) is not None:
                    self.err(f"{what}.out: {why}", w, "unknown-ref", str(r))
                    continue
                if r.kind == "flow":
                    if r.port:
                        self.err(f"{what}.out: a block moves a flow, not its sensor ({r})", w, "wrong-kind")
                    if r.name in setters and setters[r.name] != b.name:
                        self.err(f"{what}.out: flow {r.name} is already set by block {setters[r.name]}; one block sets a "
                                 f"flow (put a select in front, or split the flow)", w, "two-actuators", str(r))
                    setters[r.name] = b.name
                elif r.kind == "auxiliary":
                    if r.port:
                        self.err(f"{what}.out: a block sets an auxiliary, not its sensor ({r})", w, "wrong-kind")
                    if r.name in setters and setters[r.name] != b.name:
                        self.err(f"{what}.out: auxiliary {r.name} is already set by block {setters[r.name]}; one block sets "
                                 f"an auxiliary", w, "two-actuators", str(r))
                    setters[r.name] = b.name
                elif r.kind == "goal" and r.port:
                    self.err(f"{what}.out: a block sets a goal's setpoint (goal.{r.name}), not its .{r.port}", w, "wrong-kind")
                elif r.kind == "block" and r.name == b.name:
                    self.err(f"{what}.out: a block cannot command itself", w, "self-command")
            if b.goal and b.goal not in spec.goals:
                self.err(f"{what}.goal: {b.goal!r} is not a goal" + self.suggest(b.goal, spec.goals), w, "unknown-ref",
                         f"goal.{b.goal}")
            if b.agent:
                a = spec.agents.get(b.agent)
                if a is None:
                    if b.type == "external":
                        spec.agents[b.agent] = Agent(b.agent, external=True)     # an external machine, named in passing
                    else:
                        self.err(f"{what}.agent: {b.agent!r} is not an agent; declare it under agents:, or leave agent: out "
                                 f"(the block then runs here, launched by ergostat)", w, "unknown-ref", f"agent.{b.agent}")
                elif a.kind and b.type not in KIND_RUNS[a.kind]:
                    self.err(f"{what}: a {b.type} block cannot run on {b.agent}, which is a {a.kind}", w, "agent-kind")
                elif a.external and b.type != "external":
                    self.err(f"{what}: {b.agent} is external (ergostat never runs it), so its blocks are type: external", w,
                             "agent-external")
        for f in spec.flows.values():
            for end in (f.source, f.target):
                st = spec.stocks.get(end or "")
                if st and f.unit and st.unit and f.unit != st.unit:
                    self.err(f"flow {f.name} is in {f.unit}, but stock {st.name} is in {st.unit}: what moves a stock is "
                             f"counted in its unit", f.where, "units")
            for s in f.sensors.values():
                unit = f.unit or next((spec.stocks[e].unit for e in (f.source, f.target) if e in spec.stocks), "")
                if s.unit and unit and s.unit not in (unit, f"{unit}/h"):
                    self.err(f"flow {f.name} sensor {s.name} reads {s.unit}, but the flow is in {unit} (per hour)", s.where,
                             "units")
        for st in spec.stocks.values():
            for s in st.sensors.values():
                if s.unit and st.unit and s.unit != st.unit:
                    self.err(f"stock {st.name} sensor {s.name} reads {s.unit}, but the stock is in {st.unit}", s.where, "units")
        for s in spec.sensors():
            if s.query and s.query.get("source") not in spec.sources:
                self.err(f"sensor {s.of.name}.{s.name}: source {s.query.get('source')!r} is not under sources:", s.where,
                         "unknown-ref")
            elif s.query and spec.sources[s.query["source"]].type == "prometheus" and not s.query.get("promql"):
                self.err(f"sensor {s.of.name}.{s.name}: a prometheus query needs promql:", s.where, "missing-key")
            elif s.query and spec.sources[s.query["source"]].type == "ergostat":
                from ..remote.readings import check_query
                why = check_query(s.query)
                if why:
                    self.err(f"sensor {s.of.name}.{s.name}: {why}", s.where, "bad-query")
        self.algebraic(spec)

    def algebraic(self, spec: Spec) -> None:
        """A cycle of built-in blocks with no delay in it has no order to compute in."""
        edges: dict[str, set[str]] = {n: set() for n, b in spec.blocks.items() if b.builtin and b.type != "delay"}
        for n in edges:
            b = spec.blocks[n]
            for t in b.targets():
                if t.kind == "block" and t.name in edges:
                    edges[n].add(t.name)
            for r in b.inputs.values():
                if r.kind == "block" and r.name in edges:
                    edges[r.name].add(n)
        state: dict[str, int] = {}

        def visit(n, path):
            state[n] = 1
            for m in sorted(edges[n]):
                if state.get(m) == 1:
                    cyc = path[path.index(m):] + [m]
                    self.err(f"blocks {' → '.join(cyc)} feed each other with no delay between them (an algebraic loop): "
                             f"put a delay block in the cycle", spec.blocks[m].where, "algebraic-loop")
                    return True
                if state.get(m) is None and visit(m, path + [m]):
                    return True
            state[n] = 2
            return False
        for n in sorted(edges):
            if state.get(n) is None and visit(n, [n]):
                break


def _one(m: Map, k) -> Map:
    one = Map({k: m[k]})
    one.where, one.lines = m.where, {k: m.at(k)}
    return one


def compile_doc(doc: Document) -> tuple[Spec, list[Problem]]:
    c = Compiler(doc)
    spec = c.run()
    return spec, c.problems
