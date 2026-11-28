"""The compiled model: the five written types (SPEC §5–§10) as plain objects, references resolved,
and what is derived from them (actuators, controllers, loops, disturbances), never written."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .load import Where

BUILTIN = ("onoff", "compare", "proportional", "limit", "delay", "schedule", "lookup", "select", "expr", "timer",
           "counter", "alarm", "budget", "judge")   # judge: ergostat's judge of changes to the model (SPEC §12e), on the program rung
MACHINE = ("program", "ai", "person", "external")
FORMATS = ("image", "markdown", "code", "text", "json", "claude-session")   # how a file an item names is shown
SETPOINT = re.compile(r"^\s*(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
PROJECTION_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")    # a projection's name: a NAME, or with _ (an outside log's)
STATE = re.compile(r"^\S(?:.{0,62}\S)?$")             # a state: any case, kept as written, compared exactly
REF = re.compile(r"^(stock|flow|auxiliary|variable|goal|block)\.([a-z][a-z0-9-]*)(?:\.([a-z][a-z0-9-]*))?$")
OLD_KIND = {"variable": "auxiliary"}     # what a kind was called before (SPEC §7a): still read, with a finding


@dataclass(frozen=True)
class Ref:
    kind: str                  # stock, flow, auxiliary, goal, block
    name: str
    port: str | None = None

    def __str__(self) -> str:
        return f"{self.kind}.{self.name}" + (f".{self.port}" if self.port else "")

    @staticmethod
    def parse(text) -> Ref | None:
        m = REF.match(text) if isinstance(text, str) else None
        return Ref(OLD_KIND.get(m.group(1), m.group(1)), m.group(2), m.group(3)) if m else None

    @staticmethod
    def signed(text) -> tuple[Ref | None, int | None]:
        """``+stock.x`` or ``-auxiliary.y``: a reference with its polarity (+1, -1), or None when
        unsigned (not known)."""
        sign = None
        if isinstance(text, str) and text[:1] in "+-":
            sign, text = (1 if text[0] == "+" else -1), text[1:]
        return Ref.parse(text), sign


def sign_text(sign: int | None) -> str | None:
    """+1, -1, None as the graph and the explanations write them: "+", "-", None (not known)."""
    return None if sign is None else "+" if sign > 0 else "-"


@dataclass
class Setpoint:
    op: str
    value: float

    @staticmethod
    def parse(text) -> Setpoint | None:
        m = SETPOINT.match(str(text)) if isinstance(text, str | int | float) and not isinstance(text, bool) else None
        return Setpoint(m.group(1), float(m.group(2))) if m else None

    def __str__(self) -> str:
        v = int(self.value) if self.value == int(self.value) else self.value
        return f"{self.op} {v}"

    def error(self, y: float, r: float | None = None) -> float:
        """e = r − y: negative when y is too high, positive when too low, 0 on a one-sided
        setpoint's satisfied side."""
        r = self.value if r is None else r
        if self.op in ("<=", "<"):
            return min(0.0, r - y)
        if self.op in (">=", ">"):
            return max(0.0, r - y)
        return r - y

    def outside(self, y: float, band: float = 0.0, r: float | None = None) -> bool:
        r = self.value if r is None else r
        return {"<=": y > r + band, "<": y >= r + band, ">=": y < r - band, ">": y <= r - band}.get(self.op, abs(y - r) > band)


MEASURE = re.compile(r"^ergostat\.model\.([a-z][a-z0-9-]*)$")   # a built-in measure, beside stock.x, flow.x, auxiliary.x
MODEL_MEASURES = {                 # the model's own quality (SPEC §12e), read by a sensor: builtin: ergostat.model.fit
    "ergostat.model.fit": "the scaled error of the model's replay on the reference window (the Fit page's total; lower is "
                          "better)",
    "ergostat.model.unexplained": "the share of the stocks' change over the last hour that their flows do not explain (the "
                                  "residuals), averaged over the stocks that moved",
    "ergostat.model.unidentified-loops": "the goals whose loop closes and whose process the model does not hold (no process:)",
    "ergostat.model.open-findings": "the findings ergostat check reports (structure, signs, control), errors aside",
    # how the improvement loop itself is doing (SPEC §12f, numbers/meta.py), over the last week
    "ergostat.model.accepted-per-day": "changes written to the model a day, over the last week",
    "ergostat.model.regressed": "changes written over the last week that the prediction check flagged for revert",
    "ergostat.model.verified-share": "of the changes the prediction check scored over the last week, the share whose "
                                     "forecasts held",
    "ergostat.model.fit-gained": "what the changes written over the last week lowered the scaled error by, together",
    "ergostat.model.cost-per-accepted": "dollars the blocks that make changes spent over the last week, over the changes "
                                        "written",
    "ergostat.model.reviews-passed": "changes the reviewer passed over the last week",
    "ergostat.model.reviews-revised": "changes the reviewer sent back to their author over the last week",
    "ergostat.model.reviews-rejected": "changes the reviewer rejected over the last week",
    "ergostat.model.review-misses": "changes the reviewer passed that the prediction check later flagged for revert",
}
MODEL_CHANGE = "ergostat.model-change"   # the built-in projection: every change to the model, made, judged and decided
MODEL_CHANGE_STATES = ["made", "checked", "testing", "passed", "accepted", "refused", "failed", "dismissed", "superseded",
                       "verified", "regressed",   # verified, regressed: an accepted change scored again later (SPEC §12f)
                       "inconclusive"]            # the record held out could not tell it from the model as it is
JUDGE_PORTS = ("testing", "passed", "failed", "accepted", "inconclusive")
MODELLING_REQUEST = "ergostat.modelling-request"   # the built-in projection: work for modelling, raised from what check finds
MODELLING_REQUEST_STATES = ["open", "proposed", "held", "answered", "dismissed"]
CLAIM = "ergostat.claim"          # the built-in projection: what a block said it did, checked against the record (SPEC §12g)
CLAIM_STATES = ["made", "verified", "contradicted", "unchecked"]
CLAIM_CHECKS = ("tests", "changed", "state", "exit", "level")   # the built-in checks; a project's claims: adds more
DECISION = "ergostat.decision"    # the built-in projections of the owner's intent (SPEC §5a): what was decided,
CORRECTION = "ergostat.correction"   # and what the owner corrected (decisions/kinds.py)
CONTEXT = "ergostat.context"      # the built-in projection: one use of a context recipe, and its outcome (SPEC §12j)
CONTEXT_MEASURE = re.compile(r"^ergostat\.context\.([a-z][a-z0-9-]*)\.(outcome|cost|uses|succeeded|failed)$")
CONTEXT_MEASURES = {               # how the work a recipe started turned out (SPEC §12j), over the last week
    "ergostat.context.RECIPE.outcome": "of the uses of the recipe whose outcome is known over the last week, the share "
                                       "that succeeded (0 while none is known)",
    "ergostat.context.RECIPE.cost": "the mean cost, in USD, of a session started from the recipe over the last week",
    "ergostat.context.RECIPE.uses": "the recipe's uses over the last week",
    "ergostat.context.RECIPE.succeeded": "uses whose work succeeded over the last week",
    "ergostat.context.RECIPE.failed": "uses whose work failed over the last week",
}
TRUST = re.compile(r"^ergostat\.trust\.(contradicted|contradictions|verified|unchecked|claims)"
                   r"(?:@((?:rung:|model:)?[A-Za-z0-9][A-Za-z0-9._:-]*))?$")   # ergostat.trust.contradicted@developer
TRUST_MEASURES = {                 # how far a block's claims hold (SPEC §12g), over the last week; @WHO narrows them
    "ergostat.trust.contradicted": "of the claims checked over the last week, the share contradicted (0 while none is "
                                   "checked); @BLOCK, @rung:KIND or @model:MODEL for one block, rung or model",
    "ergostat.trust.contradictions": "claims contradicted over the last week",
    "ergostat.trust.verified": "claims verified over the last week",
    "ergostat.trust.unchecked": "claims no check could judge over the last week (recorded, not trusted)",
    "ergostat.trust.claims": "claims made over the last week",
}

MESSAGE = "ergostat.message"      # the built-in projection: the owner's messages, routed to the work they concern (SPEC §12h)
MESSAGE_STATES = ["received", "unrouted", "routed", "delivered", "answered"]   # unrouted: routed by hand later
MESSAGE_MEASURES = {               # how the owner's messages reach the work (SPEC §12h)
    "ergostat.messages.unrouted": "messages that reached no work, now (each needs attention)",
    "ergostat.messages.awaiting": "messages routed to work and not yet delivered to it, now",
    "ergostat.messages.received": "messages received over the last week",
    "ergostat.messages.routed": "messages routed to work over the last week",
    "ergostat.messages.delivered": "messages delivered to work over the last week (to a session, a run's context, or "
                                   "as a follow-up on finished work)",
    "ergostat.messages.answered": "messages the work answered over the last week",
    "ergostat.messages.missed": "messages that did not reach the work before it finished, over the last week: the "
                                "work was reopened or followed up, citing them (work redone)",
    "ergostat.messages.reached": "of the messages received over the last week, the share delivered to work (0 while none "
                                 "is received)",
}

VERDICT = "ergostat.verdict"      # the built-in projection: the intent judge's verdict on a piece of work (SPEC §12i)
VERDICT_STATES = ["asked", "met", "unmet", "contradicted", "unjudged", "overruled", "missed"]
JUDGE_MODES = ("model", "intent")  # a judge block's judge: of changes to the model (SPEC §12e), or of work (§12i)
INTENT_PORTS = ("judged", "met", "held")   # what an intent judge moved on a pass: judged, passed, held back
INTENT = re.compile(r"^ergostat\.intent\.(false-done|false-done-tests|accepted|reopened|judged|met|unmet|contradicted|"
                    r"held|unjudged|overruled|cost)(?:@([A-Za-z0-9][A-Za-z0-9._/-]*))?$")   # ergostat.intent.false-done@hypothesis
INTENT_MEASURES = {                # how far finished work holds to what the owner meant (SPEC §12i); @PROJECTION narrows them
    "ergostat.intent.false-done": "of the work accepted over the last week, the share the owner later reopened, followed "
                                  "up or corrected (0 while none is accepted); @PROJECTION for one projection",
    "ergostat.intent.false-done-tests": "the same had the tests alone decided: of the work that reached its judged state "
                                        "over the last week, the share found not done as meant, by the intent judge (not "
                                        "overruled) or by the owner after it was accepted",
    "ergostat.intent.accepted": "work accepted over the last week (it entered a state where it counts as done)",
    "ergostat.intent.reopened": "of that work, how much the owner reopened, followed up or corrected after accepting it",
    "ergostat.intent.judged": "verdicts the intent judge gave over the last week",
    "ergostat.intent.met": "verdicts that the work is done as meant",
    "ergostat.intent.unmet": "verdicts that the work does not do what it was meant to (its done-when, the owner's words)",
    "ergostat.intent.contradicted": "verdicts that the work contradicts a confirmed decision, a correction or the owner's "
                                    "messages about it",
    "ergostat.intent.held": "work held back: verdicts unmet or contradicted that the owner has not overruled",
    "ergostat.intent.unjudged": "work the judge could not hold to anything (nothing in scope), or whose verdict it could "
                                "not support with evidence",
    "ergostat.intent.overruled": "verdicts the owner overruled (a false alarm, or a pass that was not)",
    "ergostat.intent.cost": "dollars the intent judge spent over the last week",
}

ACTION = "ergostat.action"        # the built-in projection: a gated action an AI session asked for (SPEC §12k)
ACTION_STATES = ["requested", "approved", "ran", "failed", "denied"]
GATES = ("auto", "approve", "deny")   # an action's gate: run at once, held for the owner, or never run
ACTIONS = re.compile(r"^ergostat\.actions\.(held|approved|auto|denied|ran|failed)(?:@([a-z][a-z0-9-]*))?$")
ACTIONS_MEASURES = {               # the gated actions, by how their gates took them (SPEC §12k); @CLASS narrows them
    "ergostat.actions.held": "gated actions waiting for the owner's approval, now (each needs attention); @CLASS for one "
                             "class",
    "ergostat.actions.approved": "gated actions the owner approved over the last week",
    "ergostat.actions.auto": "gated actions their gate let through at once (gate: auto) over the last week",
    "ergostat.actions.denied": "gated actions denied, by their gate (gate: deny) or by the owner, over the last week",
    "ergostat.actions.ran": "gated actions that ran and exited 0 over the last week",
    "ergostat.actions.failed": "gated actions that ran and failed over the last week",
}
INBOX_MEASURES = {                 # what waits on a person (SPEC §12o)
    "ergostat.inbox.waiting": "everything waiting on a person now: held actions, requests, advised commands, step tests, "
                              "model changes",
    "ergostat.inbox.oldest": "hours the oldest of them has waited (0 when none waits)",
    "ergostat.inbox.asked": "how many were asked of a person over the last day: the approval budget",
    "ergostat.interventions.waiting": "interventions waiting now: the inbox's entries and the alarms raised",
    "ergostat.interventions.per-day": "interventions over the last day (suppressed classes at their rate before)",
    "ergostat.interventions.trend": "a rise in the interventions per day the record shows beyond its noise: the lower "
                                    "bound (slope - 2 SE) of their slope over the window, per day per week, or 0",
    "ergostat.interventions.standing": "entries waiting longer than notify's standing (default 24h)",
    "ergostat.interventions.chattering": "classes intervening 3 or more times within a minute over the last day",
    "ergostat.interventions.blocked-hours": "hours the interventions blocked their processes over the last day",
    "ergostat.interventions.top-share": "the share of the interventions over the window from the top class",
}
WORKSPACE = "ergostat.workspace"  # the built-in projection: one workspace of a pool, and whose it is (SPEC §12k)
WORKSPACE_STATES = ["free", "in-use", "held", "quarantined"]
WORKSPACES = re.compile(r"^ergostat\.workspaces\.(free|in-use|held|quarantined)(?:@([a-z][a-z0-9-]*))?$")
WORKSPACES_MEASURES = {            # the workspace pools, now (SPEC §12k); @POOL narrows them
    "ergostat.workspaces.free": "workspaces free to be given to an item, now; @POOL for one pool",
    "ergostat.workspaces.in-use": "workspaces an item's run holds, now",
    "ergostat.workspaces.held": "workspaces kept for an item whose lease ended while it is not finished (under review), "
                                "now",
    "ergostat.workspaces.quarantined": "workspaces found dirty or broken, kept aside for the owner and never reused, now",
}


COST = re.compile(r"^ergostat\.cost\.(usd|tokens|cpu|memory|runs)(-hour)?"
                  r"(?:@((?:model:)?[A-Za-z0-9][A-Za-z0-9._:-]*))?$")   # ergostat.cost.usd@developer (SPEC §9.1)
COST_MEASURES = {                  # what the runs cost (SPEC §9.1), over the last day; -hour: the last hour; @BLOCK narrows
    "ergostat.cost.usd": "dollars the runs' AI sessions cost over the last day (as Claude Code reported them, else "
                         "estimated from their tokens); -hour for the last hour; @BLOCK or @model:MODEL for one",
    "ergostat.cost.tokens": "tokens the runs' AI sessions used over the last day (input, output, cache reads and writes)",
    "ergostat.cost.cpu": "CPU seconds (user and system) of the runs' process trees over the last day",
    "ergostat.cost.memory": "the largest peak memory of one run's process tree over the last day, in MB",
    "ergostat.cost.runs": "runs that ended over the last day",
}


LEASES = re.compile(r"^ergostat\.leases\.(held|expired|dead|overdue)(?:@([a-z][a-z0-9-]*))?$")   # ergostat.leases.dead@ticket
LEASE_MEASURES = {                 # the leases on items (SPEC §9.5); @PROJECTION or @BLOCK narrows them
    "ergostat.leases.held": "leases held now: items a run is working on; @PROJECTION or @BLOCK for one projection or block",
    "ergostat.leases.expired": "leases that expired over the last day: a run silent past its TTL (each needs attention)",
    "ergostat.leases.dead": "dead letters now: items given up on after their attempts (each needs attention)",
    "ergostat.leases.overdue": "leases held now past their expiry, not yet expired: 0 while the watchdog keeps up",
}


BUDGET_MEASURES = {                # the day's AI budget (SPEC §9.9): what runs may still reserve
    "ergostat.budget.left": "dollars of budget.daily left over the last day: daily less what ended runs cost and what "
                            "runs in flight reserved; an error, never a number, when it cannot be worked out",
}
BUDGET_MOST = 10000.0             # the ceiling on budget.daily, in dollars
ERRORS = re.compile(r"^ergostat\.errors\.(level|left)@([a-z0-9][a-z0-9-]{0,63})$")   # an error budget block's (SPEC §9.2)
ERRORS_MEASURES = {
    "ergostat.errors.level@BLOCK": "the check level an error budget block (type: budget) set, 0 the lightest",
    "ergostat.errors.left@BLOCK": "the regressions its budget still allows over its window (below 0: overspent)",
}


@dataclass
class RunBudget:
    """``budget:`` (SPEC §9.9): ``daily``, dollars over the trailing day; ``max_cost``, what a charged run reserves
    before it starts. Checked at compile time and again before every charged run (``problem``)."""
    daily: float
    max_cost: float
    where: Where | None = None

    def problem(self) -> str | None:
        """Why these values are out of bounds, or None."""
        d, m = self.daily, self.max_cost
        if any(isinstance(x, bool) or not isinstance(x, int | float) or x != x for x in (d, m)):
            return "budget: out of bounds: daily and max-cost must be numbers"
        if d > BUDGET_MOST:
            return f"budget.daily: out of bounds: {d:g} is above the ceiling of {BUDGET_MOST:g}"
        if d <= 0:
            return f"budget.daily: out of bounds: {d:g} is not above 0"
        if m <= 0:
            return f"budget.max-cost: out of bounds: {m:g} is not above 0"
        if m > d:
            return f"budget.max-cost: out of bounds: {m:g} is above budget.daily ({d:g})"
        return None


UPKEEP = re.compile(r"^ergostat\.upkeep\.(index-files|retired-index-files|heartbeat-age|stalls|restarts|rollup-due"
                    r"|events-past-keep|measurements-due)$")
UPKEEP_MEASURES = {                # ergostat's own upkeep (SPEC §2a, Upkeep)
    "ergostat.upkeep.index-files": "the live item-index files under the state directory's items folder, now",
    "ergostat.upkeep.retired-index-files": "the retired item-index files (marked, waiting for no process to hold them), now",
    "ergostat.upkeep.heartbeat-age": "seconds since the last pass heartbeat.json gives; no reading without one",
    "ergostat.upkeep.stalls": "ergostat.engine.stalled events over the last hour (the engine's watchdog)",
    "ergostat.upkeep.restarts": "ergostat.engine.restarted events over the last day (the outer watcher)",
    "ergostat.upkeep.rollup-due": "items with events past their roll-up horizon outside a snapshot: what compact would roll",
    "ergostat.upkeep.events-past-keep": "events older than the model's keep that pruning would forget, now",
    "ergostat.upkeep.measurements-due": "measurement rows past storage: measurements: raw, or past their tier's keep, now",
}
STALE_RANGE = (60, 3600)           # the seconds use: upkeep's heartbeat-fresh may give the outer watcher (SPEC §2a)


def stale_ok(x) -> bool:
    """A real number of seconds within ``STALE_RANGE``: never a bool, NaN or infinity (each fails the comparison)."""
    return isinstance(x, int | float) and not isinstance(x, bool) and STALE_RANGE[0] <= x <= STALE_RANGE[1]


def heartbeat_stale(spec) -> float | None:
    """The limit of ``use: upkeep``'s goal ``heartbeat-fresh`` (ergostat's own template), for ``heartbeat.json``; None
    in a model without it, or with one outside ``STALE_RANGE``."""
    for inst, u in (getattr(spec, "uses", None) or {}).items():
        if isinstance(u, dict) and u.get("template") == "upkeep" and not u.get("owners"):
            g = (getattr(spec, "goals", None) or {}).get("heartbeat-fresh")
            if g is not None and g.system == inst and g.hold.op == "<=" and stale_ok(g.hold.value):
                return float(g.hold.value)
    return None


def is_measure(name: str) -> bool:
    """A built-in measure a sensor may read: the model's own (``ergostat.model.*``), trust's (``ergostat.trust.*``,
    with an optional ``@who``), the messages' (``ergostat.messages.*``), a recipe's (``ergostat.context.*``) or the
    intent judge's (``ergostat.intent.*``, with an optional ``@kind``), the leases' (``ergostat.leases.*``, with an optional
    ``@kind`` or ``@block``), the gated actions' (``ergostat.actions.*``, with an
    optional ``@class``), the workspace pools' (``ergostat.workspaces.*``, with an optional ``@pool``) or what the runs
    cost (``ergostat.cost.*``, with an optional ``-hour`` and ``@block``), ergostat's upkeep (``ergostat.upkeep.*``), or
    the day's budget left (``ergostat.budget.left``), or an error budget block's level and budget left
    (``ergostat.errors.level@BLOCK``, ``ergostat.errors.left@BLOCK``)."""
    return (name in MODEL_MEASURES or bool(TRUST.match(name)) or name in MESSAGE_MEASURES or bool(UPKEEP.match(name))
            or bool(ERRORS.match(name))
            or bool(CONTEXT_MEASURE.match(name)) or bool(INTENT.match(name)) or bool(LEASES.match(name))
            or bool(ACTIONS.match(name)) or bool(WORKSPACES.match(name)) or bool(COST.match(name)) or name in INBOX_MEASURES
            or name in BUDGET_MEASURES)


CHANGE_CLASSES = ("parameter", "equation", "structure", "description", "unit", "rename", "redesign",
                  "display")   # what accept: names (SPEC §12e)
NAMED_ONLY = ("rename", "redesign", "display")   # promoted only by name (accept: {rename: auto}), never by accept: auto for every kind


@dataclass
class Improve:
    """The judge block's policy (SPEC §12e): who writes a change it passed, by its kind (``auto``: the judge writes
    it; ``owner``: it waits in the review queue), the least fall in scaled error that counts as better, the least
    record after a change it is judged on, and how that record is shown in windows (1: whole; 2: halves; ...)."""
    accept: dict[str, str] = field(default_factory=lambda: dict.fromkeys(CHANGE_CLASSES, "owner"))
    threshold: float = 0.02
    hold_out: float = 600.0
    windows: list[int] = field(default_factory=lambda: [1, 2, 4])
    warm_up: float = 6 * 3600.0     # each window replayed from this long before it, its stocks and delays warm
    block: str | None = None
    reviewed: list[str] = field(default_factory=list)   # kinds written only after the reviewer's pass (numbers/reviewer.py)


def template_made(x) -> bool:
    """A part (or a finding about one) that a template made: its ``use:`` line stands for it, and only the instance's
    ``with:`` or the template changes it."""
    return bool(getattr(getattr(x, "where", x), "template", None))


def once_made(spec, x) -> bool:
    """A part a ``once`` library template made (``use: modelling``): the template's own system and boundary, never
    the model's."""
    w = getattr(x, "where", None)
    u = (getattr(spec, "uses", None) or {}).get(getattr(w, "instance", None)) if w is not None else None
    return bool(u and u.get("once") and not u.get("owners"))


OWN_TEMPLATES = frozenset({"modelling"})   # the owner's decision: these once templates' goals are upkeep, not the system's


def upkeep_of(spec, x) -> str | None:
    """The template's name when a once library template in ``OWN_TEMPLATES`` made ``x``; else None."""
    if not once_made(spec, x):
        return None
    t = spec.uses[x.where.instance].get("template")
    return t if t in OWN_TEMPLATES else None


def modelling_systems(spec) -> set[str]:
    """The systems ``use: modelling`` made, by their instance's name (as state.attention groups their goals): drawn
    with a dashed frame."""
    return {i for i, u in (getattr(spec, "uses", None) or {}).items() if isinstance(u, dict) and u.get("template") == "modelling"}


def modelling_request_kind() -> ItemKind:
    on = {f"{MODELLING_REQUEST}.raised": "open", f"{MODELLING_REQUEST}.reopened": "open", f"{MODELLING_REQUEST}.proposed": "proposed",
          f"{MODELLING_REQUEST}.held": "held", f"{MODELLING_REQUEST}.answered": "answered",
          f"{MODELLING_REQUEST}.dismissed": "dismissed"}
    return ItemKind(MODELLING_REQUEST, f"{MODELLING_REQUEST}/*", list(MODELLING_REQUEST_STATES), on,
                    ["code", "about", "source", "tier", "change"], {}, None,
                    "work for the modelling subsystem: a finding, a chain finding, a coherence mismatch or a craft note "
                    "check reports, held until it is answered (built in, SPEC §12e)")


def model_change_kind() -> ItemKind:
    on = {f"{MODEL_CHANGE}.{s}": s for s in MODEL_CHANGE_STATES if s != "made"}
    on[f"{MODEL_CHANGE}.made"] = "made"
    return ItemKind(MODEL_CHANGE, f"{MODEL_CHANGE}/*", list(MODEL_CHANGE_STATES), on,
                    ["title", "kind", "made_by", "confidence", "verdict"], {}, None,
                    "every change to the model: made by a block, ergostat's own finders or the owner; checked, judged, "
                    "and accepted or not (built in, SPEC §12e)")


def claim_kind() -> ItemKind:
    on = {f"{CLAIM}.{s}": s for s in CLAIM_STATES}
    return ItemKind(CLAIM, f"{CLAIM}/*", list(CLAIM_STATES), on, ["says", "about", "block", "kind", "why"], {}, None,
                    "what a block said it did (a claim line), checked by ergostat against the record and the world: "
                    "verified, contradicted, or unchecked (built in, SPEC §12g)")


def message_kind() -> ItemKind:
    on = {f"{MESSAGE}.{s}": s for s in MESSAGE_STATES}
    return ItemKind(MESSAGE, f"{MESSAGE}/*", list(MESSAGE_STATES), on, ["text", "by", "matched", "outcome"], {},
                    None, "the owner's messages: received, routed to the work in flight they concern, and delivered to it "
                    "(a running session's next turn, a run's context, a follow-up on finished work), or unrouted "
                    "(built in, SPEC §12h)", fold={"deliveries": "append", "answers": "append"})


def action_kind() -> ItemKind:
    on = {f"{ACTION}.{s}": s for s in ACTION_STATES}
    return ItemKind(ACTION, f"{ACTION}/*", list(ACTION_STATES), on, ["action", "item", "gate", "by", "approved by", "command", "exit"], {},
                    None, "a gated action an AI session or a program asked for: approved by its gate (auto) or the owner, or denied; "
                    "then ran or failed, its output given back (built in, SPEC §12k)", fold={"deliveries": "append"},
                    final={"denied": {"ran": "ran despite denial", "failed": "ran despite denial"}})   # (SPEC §12r)


SESSION = "session"              # the built-in projection for AI sessions, unless the model declares its own (SPEC §12h)
SESSION_STATES = ("running", "ran", "failed", "lost")


def session_kind() -> ItemKind:
    """Every AI session a run starts (``ergostat session``): its transcript, shown as the conversation, its cost and turns.
    Built in so that an ``ai`` block's sessions are items without the model declaring a projection for them."""
    on = {"session.started": "running", "session.ran": "ran", "session.failed": "failed", "session.lost": "lost"}
    return ItemKind(SESSION, f"{SESSION}/*", list(SESSION_STATES), on, ["role", "model", "turns", "cost_usd", "seconds"],
                    {"transcript": "claude-session"}, None,
                    "an AI session a run started: its conversation, model, turns and cost (built in, SPEC §12h)",
                    fold={"messages": "append", "tool_calls": "append", "tool_results": "append", "thinking": "append",
                          "tokens_in": "sum", "tokens_out": "sum"}, finished=["ran", "failed", "lost"], lost=["failed", "lost"])


BYPASS = "ergostat.bypass"        # the built-in projection: the owner's bypass lease on a class (SPEC §12k)


def bypass_kind() -> ItemKind:
    return ItemKind(BYPASS, f"{BYPASS}/*", ["granted", "ended"], {f"{BYPASS}.granted": "granted", f"{BYPASS}.ended": "ended"},
                    ["until", "by", "note", "ended_by"], {}, None, "the owner's bypass on a class of actions gated by "
                    "state: its gate no stricter than under the default state until it ends, at most 24 h (built in, "
                    "SPEC §12k)", sealed=True)


MODEL_REQUEST = "ergostat.model-request"   # the built-in projection: a class of intervention to model away (SPEC §12p)
MODEL_REQUEST_STATES = ["open", "investing", "verifying", "suppressed", "resolved"]


def model_request_kind() -> ItemKind:
    on = {f"{MODEL_REQUEST}.{s}": s for s in ("investing", "resolved", "suppressed")}
    on.update({f"{MODEL_REQUEST}.opened": "open", f"{MODEL_REQUEST}.graduated": "verifying"})
    return ItemKind(MODEL_REQUEST, f"{MODEL_REQUEST}/*", list(MODEL_REQUEST_STATES), on,
                    ["class", "cause", "count", "hours", "rank"], {}, None,
                    "a class of intervention (approvals, requests, alarms, notifications) to model away: its cause and "
                    "candidate remedies; resolved only when its process no longer needs a person (built in, SPEC §12p)")


def workspace_kind() -> ItemKind:
    on = {f"{WORKSPACE}.acquired": "in-use", f"{WORKSPACE}.held": "held", f"{WORKSPACE}.released": "free",
          f"{WORKSPACE}.quarantined": "quarantined", f"{WORKSPACE}.freed": "free"}
    return ItemKind(WORKSPACE, f"{WORKSPACE}/*", list(WORKSPACE_STATES), on, ["pool", "item", "branch", "dir", "why"], {},
                    None, "one workspace of a pool: free, in use by an item's run, held for an item under review, or "
                    "quarantined (dirty or broken, never reused) (built in, SPEC §12k)")


def verdict_kind() -> ItemKind:
    on = {f"{VERDICT}.{s}": s for s in VERDICT_STATES}
    return ItemKind(VERDICT, f"{VERDICT}/*", list(VERDICT_STATES), on, ["work", "verdict", "why", "block"], {}, None,
                    "the intent judge's verdict on a piece of work that said it was done: held to its done-when, the "
                    "confirmed decisions and corrections in its scope and the owner's messages about it; met, unmet, "
                    "contradicted or unjudged, with evidence; overruled by the owner, or missed (built in, SPEC §12i)")


@dataclass
class IntentKind:
    """What an intent judge holds one projection to (SPEC §12i): judged when an item enters ``at`` (the work says it
    is done, its tests passed); counted as accepted when it enters one of ``accepted``; held to the confirmed decisions
    whose scope names one of ``scope`` (or that name no scope), the corrections for ``work`` (kinds of work), and the
    owner's messages about it; its change read from the git repository ``repo`` (its ``commit`` or ``branch`` field,
    against ``base``)."""
    kind: str
    at: str
    accepted: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    work: list[str] = field(default_factory=list)
    repo: str | None = None
    base: str = "main"
    reopen_to: str | None = None


@dataclass
class IntentPolicy:
    """An intent judge's policy (``judge: intent``, SPEC §12i): the projections it judges, how (``model``: an AI on that
    model, else ergostat's free stand-in), at most ``max_cost`` dollars a verdict, and what a verdict that the work is
    not done as meant does (``held``: ``attention``, the default, or ``reopen``)."""
    kinds: dict[str, IntentKind] = field(default_factory=dict)
    model: str | None = None
    max_cost: float = 0.05
    held: str = "attention"
    within: float = 86400.0          # work that entered its judged state longer ago than this is not judged late


@dataclass
class Messages:
    """How the owner's messages are handled (``messages:``, SPEC §12h). ``classifier``: a block that routes a message
    no id or name in it routes (else ergostat's stand-in, matching words); ``finished``: what a message about finished
    work does, ``follow-up`` (a new item linked to it), ``reopen`` (the item moves back) or ``attention`` (it waits for
    the owner); ``follow_up``: the projection a follow-up is made as (else the finished item's own); ``reopen_to``: by kind,
    the state reopening moves an item to (else its projection's first); ``done``: by kind, the states an item is finished in
    (else those the record shows no item leaving)."""
    classifier: str | None = None
    finished: str = "follow-up"
    follow_up: str | None = None
    reopen_to: dict[str, str] = field(default_factory=dict)
    done: dict[str, list[str]] = field(default_factory=dict)
    paused: dict[str, list[str]] = field(default_factory=dict)   # by kind: states an item waits in, held by hand
    where: Where | None = None


@dataclass
class ClaimCheck:
    """A check the project declares (``claims:``, SPEC §12g): ``tests``, the project's test command, which checks
    "tests pass"; any other name, a kind of claim of its own, checked by its command's exit code. ``in``: where the
    command runs (and the repository a claim's commit is taken from), from the model's folder; ``says``: a pattern
    over what a claim says that makes it this projection."""
    name: str
    run: str
    in_: str = "."
    says: str | None = None
    timeout: float = 600.0
    description: str = ""
    where: Where | None = None


@dataclass
class Action:
    """A gated action (``actions:``, SPEC §12k): an outward act an AI session may ask for, through the tools ergostat
    serves it, and never do itself (or a program block, with ``ergostat act``). ``run``: its command template
    (``{name}`` filled with an argument, shell-quoted, or with ``{item}``, ``{branch}``, ``{workdir}``, ``{block}``,
    ``{run}``); ``gate``: ``auto``, ``approve`` or ``deny``; ``cls``: the class it is counted in (its name, else);
    ``args``: name → what it is; ``wait``: how long a session waits for the owner before going on without it;
    ``in_``: where it runs (else the session's working directory); ``fenced``: False for an action that runs once
    approved whatever became of the lease it was asked under (one whose command is safe whenever it runs);
    ``severity`` (1 to 5; None: no ``risk:``) and ``threshold``: its act-risk (``actions/risk.py``). ``gate`` and
    ``threshold`` are the ``normal`` column; ``gates`` and ``thresholds``: each operating column's, defaults filled
    (``risk.schedule``; empty: from ``gate`` and ``threshold``)."""
    name: str
    run: str
    gate: str = "approve"
    cls: str = ""
    args: dict[str, str] = field(default_factory=dict)
    timeout: float = 120.0
    wait: float = 300.0
    in_: str | None = None
    description: str = ""
    where: Where | None = None
    fenced: bool = True
    severity: int | None = None
    threshold: float = 8.0
    gates: dict[str, str] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    reshapes: dict[str, str] = field(default_factory=dict)   # column -> the smaller action asked for there (its cell: approve)
    states: dict[str, str] = field(default_factory=dict)     # a gate by declared state (and else): ``actions/schedule.py``;
                                                             # then ``gate`` is the default state's cell


@dataclass
class WorkspacePool:
    """A pool of workspaces (``workspaces:``, SPEC §12k): directories an AI block's runs work in, one per item. ``type``:
    how a workspace is made (``git``: a worktree of ``repo`` on its own branch, ``branch`` from the item's fields, made
    from ``base``); ``pool``: where they are (else the state directory's ``workspaces/NAME``); ``size``: how many."""
    name: str
    repo: str
    size: int = 2
    branch: str = "{kind}/{id}-{slug}"
    base: str = "HEAD"
    pool: str | None = None
    type: str = "git"
    description: str = ""
    where: Where | None = None


@dataclass
class ComputePool:
    """A pool of nodes runs may execute on (``compute:``, SPEC §12k): each node an SSH ``Host`` name (``ssh``) or a
    command whose standard input and output reach a worker (``connect``); ``slots`` runs at once on each; ``limits``
    each run's (bytes, seconds, ``network``); ``repos`` name → path here, ``secrets`` name → the file it is read from
    (never read at compile), ``labels`` what a node must say it has. Declared only: nothing runs on one yet."""
    name: str
    nodes: list[dict] = field(default_factory=list)      # each {"ssh": HOST} or {"connect": [argv]}
    backend: str = "process"
    image: str | None = None
    slots: int = 1
    limits: dict = field(default_factory=dict)            # cpus, memory, pids, disk, wall, network, log
    repos: dict[str, str] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    description: str = ""
    where: Where | None = None


@dataclass
class Sensor:
    name: str
    of: Ref                    # the stock or flow it measures
    run: str | None = None
    query: dict | None = None
    items: dict | None = None  # counted from the record: kind, state, entering, leaving, where, over, measure
    changes: dict | None = None   # a flow's rate from its stock's own readings: what (rises, falls, net), over, stock
    manual: bool = False
    every: float | None = 60.0
    cron: str | None = None
    timeout: float = 30.0
    parse: str | None = None
    unit: str = ""
    description: str = ""
    where: Where | None = None
    averages: float | None = None    # on a flow: its reading is the average rate over this window (seconds) before it
    builtin: str | None = None  # a built-in measure (MODEL_MEASURES: ergostat.model.fit), read by ergostat (``run`` says how)
    daemon: object = None       # the daemon that reads it (its name in spec.daemons; SPEC §9.7)
    push: bool = False          # its daemon sends its readings by itself (none asked for)
    journal: str | None = None  # a folder of JSONL journals inside the model's root, followed while ergostat runs
    untrusted: bool = False     # made by an untrusted library's template: its schedule bounded (library/bounds.py)
    run_in: str | None = None   # "owner" only when compile proved its run the owner's or ergostat's; else (None too)
    #                             it runs in ergostat.sandbox (library/runs.py)

    @property
    def window(self) -> float:
        """How far back a reading of a flow's rate looks (seconds; 0: the rate at that moment): what
        ``averages:`` says, or the ``over:`` an items or changes sensor counts over."""
        if self.items and self.of.kind == "flow":
            return float(self.items.get("over") or 3600.0)
        if self.changes:
            return float(self.changes.get("over") or 3600.0)
        return float(self.averages or 0.0)

    @property
    def ref(self) -> Ref:
        return Ref(self.of.kind, self.of.name, self.name)

    @property
    def commands(self) -> bool:
        """It reads by a program of the model's own when asked: a command each reading, or a daemon (SPEC §9.7); not a
        push sensor, whose daemon sends readings of its own accord."""
        return bool(self.run or (self.daemon and not self.push))

    @property
    def measured(self) -> bool:
        """Read by ergostat on a schedule (a command, a query, or a count of items), not by hand."""
        return bool(self.run or self.query or self.items or self.changes or (self.daemon and not self.push))

    @property
    def series(self) -> str:
        return f"sensor/{self.of.name}.{self.name}"


@dataclass
class Parameter:
    """A number an equation names (SPEC §7b): declared with its value and unit, to be fitted from
    the record (``estimate: true``), or not known yet (no value). A ``table`` makes it a lookup:
    points, linear between them."""

    name: str
    value: float | None = None
    unit: str = ""
    estimate: bool = False
    table: list[tuple[float, float]] | None = None
    description: str = ""
    system: str | None = None
    where: Where | None = None
    defined: Where | None = None       # the line its name is on
    value_at: Where | None = None      # the line its value is on (what an accepted estimate rewrites)
    duration: bool = False             # its value was written as a duration (40s): an estimate is written back as one
    range: tuple[float, float] | None = None   # what it might be (low, high): sensitivity analysis samples it there
    inferred: str | None = None        # added by ergostat: the model change that added it (ergostat.model-change/<id>), or "true"

    @property
    def provenance(self) -> str:
        """declared (its value is written), or unknown (none is, yet); an estimate is kept apart, in
        the state directory, until it is accepted."""
        return "declared" if self.value is not None or self.table else "unknown"


@dataclass
class Equation:
    """What a flow's rate (per hour) or an auxiliary's value is, as written (``equation:``): its text,
    its tree (spec/equation.py), what it names."""

    text: str
    tree: tuple
    refs: list[str] = field(default_factory=list)          # the parts it names: stock.x, flow.y, auxiliary.z
    parameters: list[str] = field(default_factory=list)    # the parameters it names
    where: Where | None = None


@dataclass
class Stock:
    name: str
    unit: str = ""
    limit: float | None = None
    initial: float | None = None
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    cumulative: bool = False   # a running total that by its nature never drains (spent so far): no outflow is missing
    formerly: list[str] = field(default_factory=list)   # the names it had (a rename keeps its history: SPEC §12e)
    rate_unit: str | None = None       # how its flows' rates are shown (rate-unit: minute, hour, day, week): display only
    inferred: str | None = None        # added by ergostat: the model change that added it (ergostat.model-change/<id>), or "true"
    where: Where | None = None
    observe: bool = False              # estimated between readings, its staleness watched (SPEC §9.6)


@dataclass
class Flow:
    name: str
    source: str | None = None  # from: a stock, or None (outside)
    target: str | None = None  # to
    unit: str = ""
    rate: float | None = None
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    driven_by: list[Ref] = field(default_factory=list)   # what its rate depends on: other flows, stocks (an influence)
    polarity: dict[str, int] = field(default_factory=dict)   # str(ref) → +1 or -1, for the driven-by written with a sign
    instant: set[str] = field(default_factory=set)       # str(ref) of the driven-by declared immediate (instant: true)
    two_way: bool = False      # it may run either way (system dynamics' biflow): a block may move it by a negative amount
    equation: Equation | None = None   # its rate per hour, as an equation of parameters and parts (SPEC §7b)
    rate_unit: str | None = None       # how its rate is shown (rate-unit: minute, hour, day, week): display only, kept per hour
    inferred: str | None = None        # added by ergostat: the model change that added it (ergostat.model-change/<id>), or "true"
    inferred_links: dict[str, str] = field(default_factory=dict)   # str(ref) of a driven-by ergostat added → its inferred:
    formerly: list[str] = field(default_factory=list)   # the names it had (a rename keeps its history: SPEC §12e)
    where: Where | None = None
    defined: Where | None = None       # the line its name is on


@dataclass
class Auxiliary:
    """A quantity without memory (SPEC §7a): determined at each moment by others, through an
    equation that may be unknown, and so measured (a score, a ratio, a share of traffic). System
    dynamics' auxiliary. What has memory, whose value persists and changes only through its flows,
    is a stock, even when it is a setting. Process variable and manipulated variable are roles a
    part plays in a loop, not kinds of quantity."""

    name: str
    unit: str = ""
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    driven_by: list[Ref] = field(default_factory=list)
    polarity: dict[str, int] = field(default_factory=dict)
    instant: set[str] = field(default_factory=set)
    exogenous: bool = False    # an input from outside the model: nothing in it drives it (the weather, the mix of customers)
    equation: Equation | None = None   # its value, as an equation (SPEC §7b); without one it is measured
    inferred: str | None = None        # added by ergostat: the model change that added it (ergostat.model-change/<id>), or "true"
    inferred_links: dict[str, str] = field(default_factory=dict)
    formerly: list[str] = field(default_factory=list)   # the names it had (a rename keeps its history: SPEC §12e)
    where: Where | None = None
    defined: Where | None = None       # the line its name is on


@dataclass
class Goal:
    name: str
    of: Ref                    # stock.x, flow.x or auxiliary.x
    hold: Setpoint
    tolerance: float = 0.0
    critical: bool = False
    owner: str = ""
    system: str | None = None
    description: str = ""
    where: Where | None = None
    process: dict | None = None    # the loop's process, u to y (SPEC §8): form, gain, tau and theta (s), identified
    per: str | None = None         # held by each item (``item``) or each group by a field, of its stock's items (§8)
    on_stale: str | None = None    # what it does while its reading is stale: act, hold or off (SPEC §9.6); None: not watched

    def status(self, y: float, was_off: bool, r: float | None = None) -> str:
        """Off past the setpoint by more than the tolerance; once off, holding again only back
        within the setpoint (for ==, within half the tolerance)."""
        back = self.tolerance / 2 if self.hold.op == "==" else 0.0
        return "off" if self.hold.outside(y, back if was_off else self.tolerance, r) else "holding"


@dataclass
class KnownLaw:
    """An external block's declared law, from the catalogue of known laws (control/laws.py, SPEC §12d): its kind and
    its parameters as checked (numbers as floats, durations in seconds), each one the catalogue names, defaults filled."""
    kind: str
    params: dict


@dataclass
class Block:
    name: str
    type: str
    inputs: dict[str, Ref] = field(default_factory=dict)        # port → reference
    outputs: dict[str, list[Ref]] = field(default_factory=dict)  # port → where it goes
    params: dict = field(default_factory=dict)                   # the type's own keys, as written
    agent: str | None = None
    role: str | None = None
    system: str | None = None
    description: str = ""
    every: float | None = None
    cron: str | None = None
    timeout: float = 300.0
    max: float | None = None
    min: float | None = None
    mode: str = "auto"
    where: Where | None = None
    implied: bool = False      # put in by ergostat (a machine block's goal:), not written
    signs: dict[str, int] = field(default_factory=dict)         # port → +1 or -1, for an input written with a sign (+stock.x)
    takes: Takes | None = None   # the items it works, one run per item, each leased (SPEC §9.5)
    pool: int = 1                # the most runs of it at once, when it takes items (``pool: N``, or ``most:``)
    pool_now: Ref | None = None  # ``pool: {now: stock.S}``: the pool read from S at each dispatch, at most ``pool``
    lease: LeaseTerms = field(default_factory=lambda: LeaseTerms())   # its leases' terms, over its projection's and its tier's
    on_stale: str | None = None  # what it does while a reading it reads is stale: act, hold or off (SPEC §9.6); None: not watched
    on: Trigger | None = None    # the event types that start it, a run per event (SPEC §9.3, *Started by an event*)
    untrusted: bool = False      # made by an untrusted library's template: its runs bounded (library/bounds.py)
    law: KnownLaw | None = None  # an external block's declared law (``law: {kind: ...}``); None when it declares none
    # ``runs-on: POOL``: the compute pool its runs are for (SPEC §12k); None: here. Left out of its plain form while None,
    # so a model that names no pool hashes as it did before the key existed (numbers/version._plain).
    runs_on: str | None = field(default=None, metadata={"unset": None})

    @property
    def builtin(self) -> bool:
        return self.type in BUILTIN

    @property
    def machine(self) -> bool:
        return self.type in MACHINE and self.type != "external"

    @property
    def judge_mode(self) -> str | None:
        """A judge's: ``model`` (changes to the model, SPEC §12e) or ``intent`` (finished work, §12i); else None."""
        return str(self.params.get("judge") or "model") if self.type == "judge" else None

    @property
    def builtin_rung(self) -> str:
        """The rung of a block ergostat computes: a judge is a program, or a narrow AI when an intent judge names a
        model; every other built-in is a rule."""
        if self.type != "judge":
            return "rule"
        pol = self.params.get("intent")
        return "narrow-ai" if pol is not None and getattr(pol, "model", None) else "program"

    @property
    def goal(self) -> str | None:
        g = self.params.get("goal")
        return g if isinstance(g, str) else None

    def targets(self) -> list[Ref]:
        return [r for refs in self.outputs.values() for r in refs]

    def reads(self) -> list[Ref]:
        """Every signal it reads: its inputs, and its goal for the types that take one."""
        out = list(self.inputs.values())
        if self.goal:
            out.append(Ref("goal", self.goal))
        return out


LEASED, DEAD = "leased", "dead"     # the states a taken projection gains (SPEC §9.5): held by a run; given up on after its attempts
WORKED = ("ergostat.failure",)    # the built-in kinds a model's blocks may take and lease (SPEC §12r)


def own_kind(name: str) -> bool:                    # a projection the model's blocks work on: its own, or one of WORKED
    return not name.startswith("ergostat.") or name in WORKED


TIERS = ("person", "ai", "narrow-ai", "decision", "program", "rule")   # the ladder, top to bottom: each has its lease terms
LEASE_TTL = {"person": 8 * 3600.0, "ai": 40 * 60.0, "narrow-ai": 10 * 60.0, "decision": 2 * 60.0, "program": 5 * 60.0,
             "rule": 60.0}               # how long a run may be silent before its lease expires, by tier (SPEC §9.5)
LEASE_ATTEMPTS = 3                  # counted attempts before an item is a dead letter
KIND_OF_TYPE = {"program": "program", "ai": "ai", "person": "person", "external": "program"}   # a block's rung by its type


@dataclass
class LeaseTerms:
    """A lease's terms (SPEC §9.5), as written for a tier, a projection or a block: what is left out is taken from the next."""

    ttl: float | None = None        # seconds a run may go silent before its lease expires
    attempts: int | None = None     # counted attempts before the item is a dead letter


@dataclass
class Daemon:
    """A long-lived process that blocks' runs and sensors' readings are handed to as JSON lines (SPEC §9.7)."""

    name: str
    run: str
    concurrency: int = 10           # the most runs it holds at once
    heartbeat: float | None = None  # restarted when silent this long (no line of any kind); None: never
    restarts: int = 5               # given up after more than this many restarts ...
    within: float = 600.0           # ... within this long
    backoff: tuple = (1.0, 120.0)   # the first restart's wait, doubled each time, at most the second
    stdin_timeout: float = 10.0     # restarted when a write to its standard input waits this long
    warm: bool = False              # concurrency processes, one run each at a time, its CPU the run's (§9.7, Warm)
    recycle: int = 1000             # warm: the most runs one process serves
    where: Where | None = field(default=None, compare=False)
    outlive: bool = False           # kept by a keeper: goes on through an engine restart (§9.7, *outlives its engine*)


@dataclass
class Join:
    """A parent moved on by its children (SPEC §5a, *Join*): to ``to`` once all (or any) of the items naming it by
    ``children`` are in ``states``."""

    children: str                   # the relation the children name it by (parent)
    states: list[str]
    to: str
    all: bool = True                # all of them (a join), else any (the first to start)


@dataclass
class Trigger:
    """What starts a block (SPEC §9.3, *Started by an event*): each event of these types whose data matches ``where``;
    ``emits``, the types its runs may say (the trigger graph's edges, checked for loops)."""

    events: list[str]               # types, or a prefix ending in .*
    where: dict = field(default_factory=dict)
    emits: list[str] = field(default_factory=list)
    max_age: float = 3600.0         # seconds: older events, when looked at, are passed over (trigger.skipped)
    most: int = 60                  # triggered runs a minute that trip its breaker (trigger.tripped)


@dataclass
class Takes:
    """What a block takes (SPEC §9.5): the items of a projection in a state, each leased to a run of its own."""

    kind: str
    at: list[str]                   # the states it takes from (the first: where an item goes back to, by default)
    to: list[str] = field(default_factory=list)   # the states that count as done: the lease's ack (else any state but these)
    where: dict = field(default_factory=dict)     # only items whose fields match (as a sensor's where:)
    unblocked: bool = False         # only items whose predecessors are all finished, the critical first (SPEC §5a, relations)
    order: list[str] = field(default_factory=list)   # fields (-FIELD: highest first): taken by them first, those
                                                     # without one after those with it; the order above among equals
    healthy: Ref | None = None      # ``faults: {healthy: R}``: the shared environment; not healthy, nothing is taken
    hold_by: list[str] = field(default_factory=list)   # ``faults: {hold-by: [F]}``: a value failing together is held
    frozen: Frozen | None = None    # ``frozen: {first: N, urgent: F}``: its next N keep their order (leases/frozen.py)
    lanes: Lanes | None = None      # ``lanes: {apart: F, ...}``: items apart by F run at once (leases/lanes.py)
    areas: Areas | None = None      # ``areas: {touches: F, holding: [S], map: {...}}``: one stream an area (leases/areas.py)


@dataclass(frozen=True)
class Area:
    """One area of a block's ``areas:`` map (SPEC §9.5, *Areas*): the patterns an item's field is matched against, and
    its owner: ``lane`` (one item at a time), ``field`` (the items sharing ``by``'s value) or ``block`` (block ``by``)."""

    name: str
    paths: tuple[str, ...]
    owner: str = "lane"
    by: str = ""


@dataclass(frozen=True)
class Areas:
    """A block's areas (SPEC §9.5): its items' ``touches`` field, the states that hold an area, and the map."""

    touches: str
    holding: tuple[str, ...]
    map: tuple[Area, ...]


@dataclass(frozen=True)
class Lanes:
    """A block's lanes (SPEC §9.5): items whose ``apart`` lists share no entry run at once, one sharing an entry on top
    of a lane ``ahead`` deep at most; ``most`` lanes, each costed ``cpu`` cores and ``memory`` bytes (or more, as
    measured; 0: not declared, so one lane until runs measure it), within ``within_cpu`` and ``within_memory``; a lane
    passed only when left in ``passed`` (needed with ``ahead`` above 0; empty: none passes)."""

    apart: str
    most: int
    within_cpu: float
    within_memory: int
    cpu: float = 0.0
    memory: int = 0
    ahead: int = 0
    passed: tuple = ()


@dataclass(frozen=True)
class Frozen:
    """A block's frozen window (SPEC §9.5): the first ``first`` items it would take keep their order; an item whose
    ``urgent`` field says ``{by, why}`` goes ahead of them, recorded."""

    first: int
    urgent: str = ""


@dataclass
class Relation:
    """A projection's typed relation to other items (SPEC §5a, *Relations*): a field holding the ids it relates to, folded as a
    set. Never enforced: what it says is read, for derived state, the critical path and the Items page's views."""

    name: str                       # the field: blocked_by
    kinds: list[str]                # the projections it may name (a target of another kind is still kept, and said)
    precedence: bool = False        # its targets come first: this item is not ready until each is finished
    inverse: str = ""               # the other direction's name, derived (blocks, children)
    group: bool = False             # a parent: the Graph view groups by it
    remote: str = ""                # names a remote's kind (incidents-incident): the remote; never precedence (§4c)
    there: str = ""                 # the projection's name at that remote (incident)
    # precedence: the target's states (not finished) in which it no longer blocks; the CPM stays finish-to-start
    starts_at: list[str] = field(default_factory=list)
    # a group's: a finished state of the item's: the fields it counts as done work in, for each group's progress
    # (spec/grouptally.py); an item in that state that does not match leaves its group's total
    done_when: dict[str, dict] = field(default_factory=dict)


@dataclass
class Agent:
    name: str
    kind: str | None = None
    external: bool = False
    at_once: int = 1
    model: str | None = None
    cost: str | None = None
    host: str | None = None
    description: str = ""
    where: Where | None = None
    # the system it is defined in (its ``system:``, or its file's ``defaults:``); None: the top level. Left out of its
    # plain form while None, so a model that names none hashes as it did before the key existed (numbers/version._plain)
    system: str | None = field(default=None, metadata={"unset": None})


@dataclass
class ItemKind:
    """A projection (SPEC §5a): which ids are this projection, the states they move through, and the
    event types that move them."""

    name: str
    id: str                    # a glob over ids: github/pull_request/*
    states: list[str] = field(default_factory=list)   # the first is where a new item starts
    on: dict[str, str] = field(default_factory=dict)   # event type → the state it moves the item to
    show: list[str] = field(default_factory=list)      # fields worth a column
    formats: dict[str, str] = field(default_factory=dict)   # field → how its file is shown (FORMATS); else by its extension
    system: str | None = None
    description: str = ""
    where: Where | None = None
    fold: dict[str, str] = field(default_factory=dict)   # field → how plain data folds into it (changes.RULES); else replace
    bounds: dict[str, int] = field(default_factory=dict)   # field → the most values its rule keeps (append: the last N)
    lease: LeaseTerms = field(default_factory=lambda: LeaseTerms())   # the terms of a lease on one of these (SPEC §9.5)
    relations: dict[str, Relation] = field(default_factory=dict)   # field → its relation to other items (SPEC §5a)
    join: list[Join] = field(default_factory=list)     # when its children's states move it on (SPEC §5a, *Join*)
    sealed: bool = False       # only ergostat's own event types fold into it (the repair loop's failures, SPEC §12r)
    final: dict[str, dict] = field(default_factory=dict)   # a state no event leaves: what a move out of it is shown as
    finished: list[str] = field(default_factory=list)   # its finished states, when messages: done: does not name it
    lost: list[str] = field(default_factory=list)       # its finished states that are a loss (scrapped), for yields
    about: str | None = None   # the field naming the model's parts it is about (goal.x, stock.y), folded by replace
    moves_from: dict[str, tuple] = field(default_factory=dict)   # event type → the only states it moves an item out of
    if_unchanged: tuple = ()   # event types applied only to the item as read: their data's `read` is its event count then
    group: str | None = None       # the nav bar menu it is shown in (`group:`), with the others of its group
    attention: str | None = None   # the field whose words, on the latest item having them, go on the attention list
    pipeline: dict | None = None   # its items record stages (ergostat/stages.py): {title, stages, waiting}
    risk: dict | None = None       # risk-score: {at, failed, passed, undone, from, least} (numbers/itemrisk.py); off when None
    query: object = None           # which events it reads (handlers.Value); None: those whose item ``id`` matches
    query_open: bool = False       # its query reads by more than an id glob (its items are not told by their ids)
    key: list | None = None        # the fields that are an object's identity, in order (each kind's solved key: its
    #                                 EventKind.key, its parts joined by /); None: the events' own item
    handlers: dict | None = None   # kind of event → field → handlers.Value; None: on: and fold: (ergostat's own)
    kinds: list = field(default_factory=list)      # its kinds of event (EventKind), in order: the first whose when holds
    declared: dict = field(default_factory=dict)   # field → fields.Field: what an object is (its fields: section)
    own_time: object = None        # the event's own time (handlers.Value; ``time:``); None: the recorded time
    computed: list = field(default_factory=list, compare=False)   # (field, handlers.Value): its from: fields, in order
    ignore: tuple = ()           # the event's paths known not to matter (``ignore:``): the workbench's, never folded
    emit: list = field(default_factory=list, compare=False)    # what it publishes from its objects (emit.Entry, ``emit:``)
    emit_version: str = field(default="", compare=False)       # its definition's version, as what it publishes says
    functions: dict = field(default_factory=dict, repr=False, compare=False)   # the model's fold functions, by name
    memo: dict = field(default_factory=dict, repr=False, compare=False)        # event id → its kind of event
    # its display name (``name:``, a handlers.Value over the folded object's fields): shown, never its identity or
    # address, never folded; None: the key is shown
    display: object = field(default=None, compare=False, metadata={"unset": None})

    match = None                   # (the old syntax's; never set)

    def matches(self, id: str) -> bool:
        """Whether ``id`` may be one of its items: by its id glob (its implied id, or a query that reads by its key's
        prefix); one that reads its events by anything else, or keys them by their data, says so of no id (``open``:
        asked by name, any)."""
        import fnmatch
        return not self.open and fnmatch.fnmatchcase(id, self.id)

    @property
    def open(self) -> bool:
        """Whether its items are not told by an id glob: its query reads by more than one, or its key is not the
        events' item."""
        return self.query_open or not self.by_item

    @property
    def by_item(self) -> bool:
        """Whether its items are the events' own items (no ``key:``, nor a kind's): each item's events are the record's
        by its id."""
        return self.key is None

    def reads(self, e: dict) -> bool:
        """Whether this projection reads event ``e``: its ``query:``; else (and ergostat's own events, a lease, a
        snapshot, always) its item matches ``id``."""
        s = e.get("source")
        if isinstance(s, str) and s.startswith("projection:") and (self.query is None or s not in self.query.text):
            return False                 # a projection's own events (SPEC §5a, *Emitted events*): read when named only
        if self.query is None or str(e.get("type") or "").startswith("ergostat."):
            item = e.get("item")
            import fnmatch
            return isinstance(item, str) and fnmatch.fnmatchcase(item, self.id)
        from .handlers import env_of, evaluate
        return bool(evaluate(self.query, env_of(e, self)))

    def kind_of(self, e: dict):
        """The kind of event that takes ``e``: the first whose ``when:`` holds (None: none does, the remainder)."""
        if self.handlers is None:
            return None
        i = e.get("id")
        if i is not None and i in self.memo:
            return self.memo[i]
        from .handlers import env_of, evaluate
        env = env_of(e, self)
        got = next((k for k in self.kinds if evaluate(k.when, env)), None)
        if i is not None:
            if len(self.memo) > 8192:
                self.memo.clear()
            self.memo[i] = got
        return got

    def keys_of(self, e: dict) -> list[str]:
        """The objects event ``e`` belongs to in this projection (``each(...)`` in a key: several; none: it is not one
        of its objects, or no kind of event takes it)."""
        from .changes import form_of
        parts = None
        if self.handlers is not None and form_of(e) == "data" and not str(e.get("type") or "").startswith("ergostat."):
            k = self.kind_of(e)
            if k is None:
                return []
            if self.key is not None:                 # keyed by its fields: the kind's solved key (none: no key)
                if not k.key:
                    return []
                parts = k.key
        if parts is None:                            # by the events' own item (and ergostat's own events, always)
            item = e.get("item")
            return [item] if isinstance(item, str) and item else []
        from .handlers import env_of, keys_from
        return keys_from(parts, env_of(e, self))

    def definition(self) -> dict:
        """Its reading of events as plain data: query, key, time, fields, and each kind of event's when, key and
        values (the page's and the API's)."""
        return {"query": self.query.text if self.query is not None else None,
                "key": list(self.key) if self.key else "key",
                "time": self.own_time.text if self.own_time is not None else None,
                "fields": {f: d.spec() for f, d in self.declared.items()},
                "events": {k.name: {"when": k.when.text if k.when.tree is not None else k.when.literal,
                                    **({"key": [v.text for v in k.key]} if k.key else {}),
                                    **{f: v.text for f, v in k.fields.items()}} for k in self.kinds}
                if self.handlers is not None else {t: {"state": f"set('{s}')"} for t, s in self.on.items()},
                **({"emit": dict(x.spec() for x in self.emit)} if self.emit else {})}

    def key_of(self, e: dict) -> str | None:
        """The (first) object event ``e`` belongs to in this projection (None: none)."""
        got = self.keys_of(e)
        return got[0] if got else None


@dataclass
class EventKind:
    """A projection's kind of event (SPEC §5a): its name, its ``when:``, its key solved from what it maps to the
    projection's key fields (handlers.Value parts, in the key's order; None: the projection has no key, or the kind
    does not tell ``untold`` of it), and what it tells, field → handlers.Value (``"..."``: a spread)."""

    name: str
    when: object
    key: list | None = None
    fields: dict = field(default_factory=dict)
    where: Where | None = None
    untold: list = field(default_factory=list)


@dataclass
class Source:
    name: str
    type: str
    url: str = ""
    where: Where | None = None
    token_file: str = ""       # an ergostat source (a remote, SPEC §4c): the file holding its token
    tls: dict | None = None    # and its mutual TLS (cert, key, ca), as its remotes: entry says


@dataclass
class Loop:
    """A goal's loop: the goal, what measures it, the blocks serving it, and the flows they set."""

    goal: str
    sensors: list[str]         # stock.x.s references
    controllers: list[str]     # blocks that read the goal (or its stock) and command
    actuators: list[str]       # blocks that set a flow of the goal's stock, reached from the controllers
    valves: list[str]          # those flows
    disturbances: list[str]    # the stock's other flows
    through: list[str] = field(default_factory=list)   # when it closes the long way: the path, part by part

    @property
    def closes(self) -> bool:
        return bool(self.sensors and (self.actuators or self.through))


@dataclass
class NamedLoop:
    """A feedback loop the model names (``loops:``): the loop through every part in ``through``, or
    the one that seeks ``goal``; the shortest such loop takes the name."""

    name: str
    through: list[Ref] = field(default_factory=list)
    goal: str | None = None
    description: str = ""
    where: Where | None = None


@dataclass
class OperatingState:
    """An operating state (SPEC §9.5): rank, pool (None: no cap), trips (goal → unknown-after, None: crossing only)."""
    name: str
    rank: int
    pool: int | None = None
    description: str = ""
    trips: dict[str, float | None] = field(default_factory=dict)
    where: Where | None = None


@dataclass
class Panel:
    """One panel of a declared dashboard (SPEC §4f): its kind, its words, and exactly the parameters its endpoint and
    page address take (``params``, plain data)."""

    panel: str
    title: str = ""
    size: str = "m"
    note: str = ""
    params: dict = field(default_factory=dict)
    where: Where | None = None


@dataclass
class Dashboard:
    """A shared, named dashboard (``dashboards:``, SPEC §4f): one window for all its panels. Display only: it is in
    no version hash, so declaring one changes no structure and no replay."""

    name: str                      # in a system's file: SYSTEM.NAME
    title: str = ""
    description: str = ""
    window: float | None = None    # seconds: the window it opens with (None: the page's)
    panels: list[Panel] = field(default_factory=list)
    system: str | None = None
    where: Where | None = None
    nav: str | None = None         # in the page's navigation, at /d/NAME: its link's words ("": its title)
    page: str | None = None        # the web page's own page it is drawn in place of (dashboards.PAGES)
    projection: str | None = None  # a projection's own (projections.P.dashboards): named P.list or P.show
    role: str | None = None        # of a projection's own: "list" (at /P) or "show" (each of its items, /P/REST)


@dataclass
class Spec:
    name: str
    root: Path
    files: list[Path]
    keep: float = 30 * 86400.0
    storage: object = None                  # storage.Storage: where the record is kept (SPEC §4b)
    intake: object = None                   # intake.config.Intake: who may push events, and the webhooks' mappings
    web: object = None                      # webaccess.Web: the page's public names and their login (SPEC §4d)
    local: dict = field(default_factory=dict)   # each setting ergostat.local.yaml set (web, intake): where (SPEC §2)
    stocks: dict[str, Stock] = field(default_factory=dict)
    flows: dict[str, Flow] = field(default_factory=dict)
    goals: dict[str, Goal] = field(default_factory=dict)
    blocks: dict[str, Block] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    items: dict[str, ItemKind] = field(default_factory=dict)
    functions: dict = field(default_factory=dict, repr=False, compare=False)   # the model's fold functions (handlers.py)
    functions_hash: str = ""                # of their files' text: in the item index's cache key
    auxiliaries: dict[str, Auxiliary] = field(default_factory=dict)
    systems: dict[str, str] = field(default_factory=dict)        # name → description
    purpose: str = ""                                             # what the whole model is for (SPEC §4a)
    within: dict[str, str] = field(default_factory=dict)         # a system → the system it is part of
    show: dict[str, list[Ref]] = field(default_factory=dict)     # a system → the measures its box shows (default: its goals')
    named_loops: dict[str, NamedLoop] = field(default_factory=dict)   # loops: the feedback loops the model names (SPEC §12a)
    parameters: dict[str, Parameter] = field(default_factory=dict)    # the numbers equations name (SPEC §7b)
    improve: Improve = field(default_factory=Improve)                  # the judge block's policy (SPEC §12e)
    claims: dict[str, ClaimCheck] = field(default_factory=dict)       # the checks the project declares (SPEC §12g)
    messages: Messages = field(default_factory=Messages)               # how the owner's messages are routed (SPEC §12h)
    contexts: dict = field(default_factory=dict)                       # name → Recipe: the context recipes (SPEC §12j)
    actions: dict[str, Action] = field(default_factory=dict)           # the gated actions sessions may ask for (SPEC §12k)
    notify: object = None                   # inbox.config.Notify: where what waits on a person is sent (SPEC §12o)
    workspaces: dict[str, WorkspacePool] = field(default_factory=dict)  # the workspace pools (SPEC §12k)
    compute: dict[str, ComputePool] = field(default_factory=dict)      # where runs may execute (SPEC §12k)
    leases: dict[str, LeaseTerms] = field(default_factory=dict)        # tier → its lease terms, over the defaults (SPEC §9.5)
    daemons: dict[str, Daemon] = field(default_factory=dict)           # the long-lived runners (SPEC §9.7)
    operating: dict[str, OperatingState] = field(default_factory=dict)  # the operating states declared (SPEC §9.5)
    uses: dict = field(default_factory=dict)                           # instance → its template, values, stand-ins (SPEC §2a)
    template_files: list[Path] = field(default_factory=list)          # the owner's templates it uses: a change reloads it
    libraries: dict = field(default_factory=dict)                      # each libraries: entry as load read it (SPEC §2a)
    remotes: dict = field(default_factory=dict)                        # remote system → url, version, parts (SPEC §4c)
    remote_files: list[Path] = field(default_factory=list)            # each remote's cached model: a new version reloads it
    belongs: dict = field(default_factory=dict)                        # stock.NAME → its system and short name (belongs.py)
    budget: RunBudget | None = None                                     # the day's AI budget runs reserve from (SPEC §9.9)
    away_after: float = 7200.0       # operating.away-after: no event from the owner this long reads as away (SPEC §12k)
    dashboards: dict[str, Dashboard] = field(default_factory=dict)     # the shared, named dashboards (SPEC §4f)
    outlive_engine: bool = False            # runs: outlive_engine: a run kept by its keeper, never stopped with us (§9.1)

    def lookups(self):
        """The reverse relations, worked out once (``lookups.py``): again when a part was added or removed. Kept
        as a plain attribute, not a field: what a model is (its fields, its hashes, its equality) never includes it."""
        from .lookups import Lookups, stamp
        ix = getattr(self, "_ix", None)
        if ix is None or ix.stamp != stamp(self):
            ix = self._ix = Lookups(self)
        return ix

    def reindex(self) -> None:
        """Forget the lookups: for code that changes a compiled model in place (a part's wiring, a goal's measure)."""
        self._ix = None

    # ---- systems: a tree; a part belongs to one, and to every system that one is within

    def chain(self, system: str | None) -> list[str]:
        """The system and every system it is within, innermost first."""
        out: list[str] = []
        while system and system not in out:
            out.append(system)
            system = self.within.get(system)
        return out

    def subsystems(self, system: str | None) -> list[str]:
        """The systems directly within this one (None: the top level)."""
        return sorted(s for s in self.systems if self.within.get(s) == system)

    def owner(self, r: Ref) -> str | None:
        """The system a referenced part belongs to (a sensor: its stock's or flow's)."""
        t = {"stock": self.stocks, "flow": self.flows, "auxiliary": self.auxiliaries, "goal": self.goals,
             "block": self.blocks}.get(r.kind, {})
        x = t.get(r.name)
        return getattr(x, "system", None) if x else None

    def inside(self, r: Ref, system: str) -> bool:
        """Whether a part is in the system, at any depth (each part's systems worked out once: ``reindex`` after
        moving a part to another system in place)."""
        return system in self._systems_of(self.lookups().kept.setdefault("ir.systems_of", {}), r)

    def _systems_of(self, kept: dict, r: Ref) -> frozenset:
        got = kept.get((r.kind, r.name))
        if got is None:
            got = kept[(r.kind, r.name)] = frozenset(self.chain(self.owner(r)))
        return got

    def interface(self, system: str) -> list[dict]:
        """What crosses the system's boundary, each crossing a port: worked out, never written.

        In: a setpoint (an outside block sets a goal inside: the cascade), a command (to a block
        inside), an action (an outside block moves a flow inside), a signal (something inside
        reads something outside), material (a flow from an outside stock into one inside), an
        influence (a flow inside driven by something outside). Out: the same, the other way."""
        kept = self.lookups().kept
        if "ir.interfaces" not in kept:
            kept["ir.interfaces"] = self._interfaces(kept.setdefault("ir.systems_of", {}))
        return [{**p, "peers": list(p["peers"])} for p in kept["ir.interfaces"].get(system, [])]

    def _interfaces(self, kept: dict) -> dict[str, list[dict]]:
        """Every system's ports in one pass: a pair of parts crosses the boundary of each system one is in and the
        other is not."""
        ports: dict[str, dict[tuple, dict]] = {}

        def systems(r: Ref) -> frozenset:
            return self._systems_of(kept, r)

        def port(system: str, dir: str, kind: str, inner: Ref, outer: Ref) -> None:
            p = ports.setdefault(system, {}).setdefault((dir, kind, str(inner)),
                                                         {"dir": dir, "kind": kind, "part": str(inner), "peers": []})
            if str(outer) not in p["peers"]:
                p["peers"].append(str(outer))

        def cross(a: Ref, b: Ref) -> tuple[frozenset, frozenset]:
            """The systems ``a`` is in and ``b`` is not, and the other way."""
            sa, sb = systems(a), systems(b)
            return sa - sb, sb - sa
        for f in self.flows.values():
            me = Ref("flow", f.name)
            if f.source and f.target:
                src, dst = Ref("stock", f.source), Ref("stock", f.target)
                out_, in_ = cross(src, dst)
                for x in out_:
                    port(x, "out", "material", me, dst)
                for x in in_:
                    port(x, "in", "material", me, src)
            for r in f.driven_by:
                here, there = cross(me, r)
                for x in here:
                    port(x, "in", "influence", me, r)
                for x in there:
                    port(x, "out", "influence", r, me)
        for b in self.blocks.values():
            if b.implied:                                 # its machine block's goal: says the same
                continue
            me = Ref("block", b.name)
            for r in b.reads():
                r = Ref(r.kind, r.name)
                if r.kind == "block":
                    continue
                here, there = cross(me, r)
                for x in here:
                    port(x, "in", "signal", me, r)
                for x in there:
                    port(x, "out", "signal", r, me)
            for t in b.targets():
                t = Ref(t.kind, t.name)
                kind = {"goal": "setpoint", "block": "command", "flow": "action"}.get(t.kind)
                here, there = cross(me, t)
                for x in here if kind else ():
                    port(x, "out", kind, me, t)
                for x in there if kind else ():
                    port(x, "in", kind, t, me)
            for r in b.inputs.values():                  # a block inside reading one outside, or the other way
                if r.kind == "block":
                    o = Ref("block", r.name)
                    here, there = cross(me, o)
                    for x in here:
                        port(x, "in", "command", me, o)
                    for x in there:
                        port(x, "out", "command", o, me)
        return {system: sorted(ps.values(), key=lambda p: (p["dir"] != "in", p["kind"], p["part"])) for system, ps in ports.items()}

    def inner_loops(self, system: str) -> list[str]:
        """Goals inside whose setpoint comes from outside and whose measurement goes back out: the
        system is, seen from outside, one block that holds what it is told (a cascade's inner loop)."""
        ports = self.interface(system)
        set_from_outside = {p["part"].split(".", 1)[1] for p in ports if p["dir"] == "in" and p["kind"] == "setpoint"}
        read_outside = {p["part"] for p in ports if p["dir"] == "out" and p["kind"] == "signal"}
        return [g for g in sorted(set_from_outside) if g in self.goals and
                (str(self.goals[g].of) in read_outside or f"goal.{g}" in read_outside)]

    # ---- lookups: the reverse relations, never written

    def measured(self, kind: str) -> dict:
        """The table of things a sensor may measure, by kind."""
        return {"stock": self.stocks, "flow": self.flows, "auxiliary": self.auxiliaries}.get(kind, {})

    def sensors(self) -> list[Sensor]:
        return [s for t in (*self.stocks.values(), *self.flows.values(), *self.auxiliaries.values()) for s in t.sensors.values()]

    def sensor(self, ref: Ref) -> Sensor | None:
        t = self.measured(ref.kind).get(ref.name)
        return t.sensors.get(ref.port or "") if t else None

    def setter_of(self, auxiliary: str) -> Block | None:
        """The block that states an auxiliary's value each run, when one does."""
        return self.lookups().first_target.get(Ref("auxiliary", auxiliary))

    def flows_of(self, stock: str) -> list[Flow]:
        return list(self.lookups().flows_at.get(stock, ()))

    def actuator_of(self, flow: str) -> Block | None:
        return self.lookups().first_target.get(Ref("flow", flow))

    def commanders_of(self, block: str) -> list[Block]:
        """The blocks that command ``block``: those that output to it, and those whose output it
        reads (the wire may be written on either end)."""
        self.blocks[block]
        ix = self.lookups()
        names = (ix.reads_block.get(block, set()) | ix.sent_from.get(block, set())) - {block}
        return ix.ordered(self, [n for n in names if n in self.blocks])

    def downstream(self, block: str) -> list[Block]:
        """Blocks that read ``block``'s output, and those it outputs to directly."""
        self.blocks[block]
        ix = self.lookups()
        out = ix.sends_to.get(block, set()) | ix.read_from.get(block, set())
        return [self.blocks[n] for n in sorted(out) if n in self.blocks]

    def agent_blocks(self, agent: str) -> list[Block]:
        return list(self.lookups().by_agent.get(agent, ()))

    def role(self, b: Block) -> str:
        if b.role:
            return b.role
        if any(t.kind in ("flow", "auxiliary") for t in b.targets()):
            return "actuator"
        reads_state = any(r.kind in ("goal", "stock", "flow") for r in b.reads())
        commands = any(t.kind in ("block", "goal") for t in b.targets())
        return "controller" if reads_state and commands else "logic"

    def goal_value_ref(self, goal: str) -> Ref:
        return self.goals[goal].of

    def loop(self, goal: str) -> Loop:
        g = self.goals[goal]
        ix = self.lookups()
        lp = ix.loops.get(goal)
        if lp is None:
            lp = ix.loops[goal] = self._loop(goal, g)
        return Loop(lp.goal, list(lp.sensors), list(lp.controllers), list(lp.actuators), list(lp.valves),
                    list(lp.disturbances), list(lp.through))

    def _loop(self, goal: str, g: Goal) -> Loop:
        what = g.of
        t = self.measured(what.kind).get(what.name)
        sensors = [str(s.ref) for s in (t.sensors.values() if t else [])]
        stock_flows = [f.name for f in self.flows_of(what.name)] if what.kind == "stock" else [what.name]
        hit = lambda r: (r.kind == "flow" and what.kind != "auxiliary" and r.name in stock_flows) or \
            (r.kind == "auxiliary" and what.kind == "auxiliary" and r.name == what.name)        # noqa: E731
        # controllers: blocks reading the goal, or its stock or flow directly
        ix = self.lookups()
        ctl = ix.ordered(self, ix.read_by.get(("goal", goal), set()) | ix.read_by.get((what.kind, what.name), set()))
        reach: list[Block] = []
        seen: set[str] = set()
        todo = list(ctl)
        while todo:
            b = todo.pop(0)
            if b.name in seen:
                continue
            seen.add(b.name)
            reach.append(b)
            todo += self.downstream(b.name)
        actuators = [b.name for b in reach if any(hit(t) for t in b.targets())]
        valves = sorted({t.name for b in reach for t in b.targets() if hit(t)})
        controllers = [b.name for b in ctl if b.name not in actuators or any(t.kind == "block" for t in b.targets())]
        if not controllers and actuators:   # an actuator reading the goal itself: it is its own controller
            controllers = [a for a in actuators if a in {b.name for b in ctl}]
        dist = [f for f in stock_flows if f not in valves] if what.kind != "auxiliary" else []
        toward = set()                     # the flows that move the stock toward its goal: the path should end on one
        if what.kind == "stock":
            down = g.hold.op in ("<=", "<")
            either = g.hold.op == "=="     # held at a level: a flow either way moves it toward the goal
            toward = {f"flow.{f.name}" for f in self.flows_of(what.name) if (f.source == what.name) == down or f.two_way or either}
        targets = {f"auxiliary.{what.name}"} if what.kind == "auxiliary" else {f"flow.{f}" for f in stock_flows}
        through = [] if actuators else self.long_way(ctl, targets, what, toward)
        if through:                        # the flow it closes through is its way in, not a disturbance
            dist = [f for f in dist if f"flow.{f}" != through[-1]]
        return Loop(goal, sensors, controllers, actuators, valves, dist, through)

    def readers(self, kind: str, name: str) -> list[Block]:
        """Blocks reading a stock (or a goal on it), a flow, or a goal."""
        ix = self.lookups()
        names = set(ix.read_by.get((kind, name), ()))
        if kind in ("stock", "flow", "auxiliary"):
            for g in ix.goals_on.get((kind, name, None), ()):
                names |= ix.read_by.get(("goal", g), set())
        return ix.ordered(self, names)

    def long_way(self, ctl: list[Block], targets: set[str], what: Ref, toward: set[str] | None = None) -> list[str]:
        """A loop may close through other stocks and other systems: its controller files work into
        a queue, that queue's own loop works it off, and what that work moves drives a flow of the
        goal's stock (``driven-by``). The shortest such path, from the controller to a flow of the
        goal's stock (or to the goal's auxiliary); empty when there is none. ``targets`` and ``toward``
        are references (flow.x, auxiliary.y).

        A controller that steps a setting closes this way too: it moves a two-way flow into a stock
        (the setting, which keeps its value between steps: integral action), and what the goal
        holds is driven by that stock."""
        drives = self.lookups().drives
        start = [f"block.{b.name}" for b in ctl]
        prev: dict[str, str | None] = {s: None for s in start}
        todo = list(start)
        fallback: list[str] = []
        while todo:
            n = todo.pop(0)
            kind, name = n.split(".", 1)
            nxt: list[str] = []
            if n in targets:
                path, at = [], n
                while at is not None:
                    path.append(at)
                    at = prev[at]
                if not toward or n in toward:
                    return path[::-1]
                fallback = fallback or path[::-1]              # it reaches the stock, the wrong way: keep looking
                continue
            if kind == "block":
                b = self.blocks[name]
                nxt += [f"block.{d.name}" for d in self.downstream(name)]
                nxt += [str(Ref(t.kind, t.name)) for t in b.targets() if t.kind in ("flow", "goal", "auxiliary")]
            elif kind == "goal":
                nxt += [f"block.{b.name}" for b in self.readers("goal", name)]
            elif kind == "flow":
                f = self.flows[name]
                nxt += [f"stock.{s}" for s in (f.target, f.source) if s and s != what.name]
                nxt += drives.get(n, [])
            elif kind in ("stock", "auxiliary"):
                nxt += [f"block.{b.name}" for b in self.readers(kind, name)]
                nxt += drives.get(n, [])
            for x in nxt:
                if x not in prev:
                    prev[x] = n
                    todo.append(x)
        return fallback

    def loops(self) -> list[Loop]:
        return [self.loop(g) for g in self.goals]
