"""Scrubbing a report before the owner sees it (SPEC §12m): what is the owner's goes, what is ergostat's stays.

Removed, each replaced by a stand-in that is the same wherever the same thing was (``stock-1``, ``email-2``):

- the words on the owner's denylist (``denylist.txt`` in the state directory's ``reports/`` folder, and
  ``reports-denylist.txt`` in ergostat's home folder; one term a line, ``re:PATTERN`` for a pattern, ``#`` a comment);
- secrets: ``token=...``, ``Authorization: Bearer ...``, well-known key prefixes, long hex and base64 runs;
- URLs (but ergostat's own project), emails, IP addresses and host names;
- file paths: ergostat's own reduced to package-relative (``ergostat/spec/engine.py``), Python's to
  ``python3.12/...``, any other replaced;
- ticket keys (``ABC-123``) and ``@mentions``;
- the names in the model: parts, item kinds (and the ids of their items), systems, sources, agents, parameters,
  templates' uses, pools, contexts; and this machine's user and host names.

Every replacement is logged with the original, its stand-in, the rule and why, so the owner can check the scrubbing;
the log stays in the state directory and is never part of the text to paste."""

from __future__ import annotations

import getpass
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_URL = "https://github.com/danroblewis/ergostat"
PUBLIC_HOSTS = {"github.com", "python.org", "docs.python.org", "example.com", "example.org", "example.net", "localhost"}
PUBLIC_IPS = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}
NOT_TICKETS = {"UTF", "SHA", "ISO", "RFC", "PEP", "HTTP", "TLS", "SSL", "UTC", "GMT", "IPV", "X", "CP", "LATIN", "MD", "PY"}
TLDS = ("com|net|org|io|co|ai|dev|app|cloud|internal|local|localdomain|corp|lan|intra|intranet|svc|cluster|"
        "us|uk|de|fr|nl|se|ch|jp|cn|ru|au|ca|gov|edu|mil|biz|xyz|tech|site|online|example|test|invalid")
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent   # the folder holding the ergostat package
COMMON = {"open", "opened", "closed", "close", "done", "new", "todo", "doing", "review", "reviewed", "ready", "waiting",
          "blocked", "failed", "passed", "running", "queued", "merged", "draft", "drafted", "active", "idle", "title", "name",
          "state", "status", "priority", "owner", "created", "updated", "started", "finished", "cancelled", "canceled",
          "accepted", "rejected", "approved", "denied", "pending", "in-progress", "backlog", "archived", "resolved", "text",
          "kind", "type", "time", "data", "item", "items", "value", "note", "notes", "why", "by", "made", "ran", "error"}
MIN_NAME = 3        # a model's names shorter than this are kept: replacing every "x" would wreck the text

WHY = {
    "denylist": "on the owner's denylist",
    "secret": "looks like a secret (a key, token or password)",
    "url": "a URL (not ergostat's own project)",
    "email": "an email address",
    "ip": "an IP address",
    "host": "a host name",
    "path": "a file path on this machine",
    "ergostat-path": "ergostat's own file, reduced to its path in the package",
    "python-path": "Python's own file, reduced to its path in Python's library",
    "ticket": "looks like a ticket key",
    "mention": "an @mention: a person",
    "user": "this machine's user or host name",
    "name": "a name in the owner's model",
    "item": "an item's id",
}


@dataclass
class Removed:
    original: str
    stand_in: str
    rule: str
    why: str
    count: int = 0
    what: str = ""          # for a model name: what it names (stock, kind, system, ...)

    def as_dict(self) -> dict:
        return {"original": self.original, "stand_in": self.stand_in, "rule": self.rule, "why": self.why,
                "count": self.count, **({"what": self.what} if self.what else {})}


# a piece of text: (its words, whether it is already ours: a stand-in, or ergostat's own words, never scrubbed)
Piece = tuple[str, bool]


@dataclass
class Scrubber:
    names: dict[str, str] = field(default_factory=dict)      # a name in the model → what it is (stock, flow, kind, ...)
    kinds: set[str] = field(default_factory=set)             # item kinds' id prefixes: their ids are items' (ticket/12)
    deny: list[str] = field(default_factory=list)            # the owner's denylist: terms, or re:PATTERN
    public: set[str] = field(default_factory=set)            # names that are ergostat's own (built-in templates' parts)
    removed: dict[tuple[str, str], Removed] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    taken: set[str] = field(default_factory=set)

    def __post_init__(self):
        self._lower = {n.lower(): (n, w) for n, w in self.names.items()}
        self._rules = self._compile()

    # ---- the stand-ins: the same thing, the same stand-in, wherever it was

    def stand_in(self, original: str, rule: str, what: str = "") -> str:
        key = (rule, original if rule in ("path", "ergostat-path", "python-path") else original.lower())
        got = self.removed.get(key)
        if got is None:
            if rule == "ergostat-path":
                s = original_rel(original)
            elif rule == "python-path":
                s = python_rel(original)
            elif rule == "user":
                s = "user" if original == getpass_user() else "this-machine"
            else:
                base = what or {"denylist": "redacted", "mention": "person"}.get(rule, rule)
                while True:
                    self.counters[base] = self.counters.get(base, 0) + 1
                    s = f"{base}-{self.counters[base]}" if base != "event" else f"event.e{self.counters[base]}"   # a type
                    if s.lower() not in self._lower and s not in self.taken:
                        break
            self.taken.add(s)
            got = self.removed[key] = Removed(original, s, rule, WHY[rule], 0, what)
        got.count += 1
        return got.stand_in

    # ---- the rules, in the order they are applied

    def _compile(self):
        rules = []
        for term in self.deny:
            term = term.strip()
            if not term or term.startswith("#"):
                continue
            try:
                rx = re.compile(term[3:], re.I) if term.startswith("re:") else re.compile(
                    r"(?<![\w])" + re.escape(term) + r"(?![\w])", re.I)
            except re.error:
                continue
            rules.append(("denylist", rx, None))
        rules += [
            ("secret", re.compile(r"(?i)\b(?:authorization\s*:\s*(?:bearer|basic|token)\s+|bearer\s+)[^\s'\"]+"), None),
            ("secret", re.compile(r"(?i)\b(?:[a-z_]*(?:token|secret|passwd|password|api[_-]?key|apikey|access[_-]?key|"
                                  r"private[_-]?key|credentials?))\b\s*[:=]\s*['\"]?[^\s'\",;]+"), None),
            ("secret", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}|"
                                  r"xox[abposr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"
                                  r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"), None),
            ("secret", re.compile(r"\b[0-9a-fA-F]{32,}\b"), None),
            ("secret", re.compile(r"(?<![\w/.-])(?=[A-Za-z0-9+/_-]*[0-9])(?=[A-Za-z0-9+/_-]*[A-Z])(?=[A-Za-z0-9+/_-]*[a-z])"
                                  r"[A-Za-z0-9+/_-]{32,}={0,2}(?![\w/.-])"), None),
            ("url", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s'\"<>()\[\]{}`]+"), None),
            ("email", re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b"), None),
            ("path", re.compile(r"(?:~|(?<![\w.~])(?:[A-Za-z]:)?)(?:[\\/][^\s'\"<>:|*?\\/,;()]+)+[\\/]?"), None),
            ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d+)?"), None),
            ("host", re.compile(r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + TLDS + r")\b(?::\d+)?"), None),
            ("ticket", re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b"), None),
            ("mention", re.compile(r"(?<![\w.@])@[A-Za-z][\w-]{1,38}\b"), None),
        ]
        who = [w for w in {getpass_user(), platform.node().split(".")[0]} if w and len(w) >= MIN_NAME]
        if who:
            rules.append(("user", re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, sorted(who, key=len, reverse=True)))
                                             + r")(?![\w-])", re.I), None))
        names = sorted((n for n in self._lower if len(n) >= MIN_NAME and n not in self.public), key=len, reverse=True)
        for chunk in range(0, len(names), 300):            # one pattern a few hundred names: Python's re copes
            part = names[chunk:chunk + 300]
            rules.append(("name", re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, part)) + r")(/[\w.:@#-]+)?(?![\w-])",
                                             re.I), None))
        return rules

    def _replace(self, rule: str, m: re.Match) -> str | None:
        """The stand-in for one match; the match itself to keep it whole (public); None to leave it to later rules."""
        s = m.group(0)
        if rule == "url":
            low = s.lower().rstrip(".,;:")
            if low.startswith(PROJECT_URL.lower()) or re.match(r"https?://(localhost|127\.0\.0\.1)([:/]|$)", low):
                return s                                  # public: kept as it is, and no later rule reads into it
        if rule == "ip" and s.split(":")[0] in PUBLIC_IPS:
            return None
        if rule == "host":
            if s.lower().split(":")[0] in PUBLIC_HOSTS or s.lower().startswith("ergostat."):
                return None
        if rule == "ticket" and m.group(1) in NOT_TICKETS:
            return None
        if rule == "name":
            name, rest = m.group(1), m.group(2)
            original, what = self._lower.get(name.lower(), (name, "name"))
            head = self.stand_in(original, "name", what)
            if rest and what == "kind":
                return head + "/" + self.stand_in(original + rest, "item", "item")
            if rest:                                      # a name then a path: its path scrubbed on its own
                return head + self.scrub(rest)
            return head
        if rule == "path":
            return self.stand_in(s, path_rule(s))
        return self.stand_in(s, rule)

    def pieces(self, pieces: list[Piece]) -> list[Piece]:
        for rule, rx, _ in self._rules:
            out: list[Piece] = []
            for text, ours in pieces:
                if ours or not text:
                    out.append((text, ours))
                    continue
                at = 0
                for m in rx.finditer(text):
                    if m.end() == m.start():
                        continue
                    if rule == "path" and m.group(0).count("/") + m.group(0).count("\\") < 2 and not m.group(0).startswith("~"):
                        continue                          # one slash is no path ("and/or", "1/2")
                    got = self._replace(rule, m)
                    if got is None:
                        continue
                    out.append((text[at:m.start()], False))
                    out.append((got, True))
                    at = m.end()
                out.append((text[at:], False))
            pieces = [p for p in out if p[0]]
        return pieces

    def scrub(self, text: str | None) -> str:
        if not text:
            return text or ""
        return "".join(t for t, _ in self.pieces([(str(text), False)]))

    def join(self, pieces: list[Piece]) -> str:
        return "".join(t for t, _ in self.pieces(pieces))

    # ---- what was removed, and whether any of it is still there

    def log(self) -> list[dict]:
        return [r.as_dict() for r in sorted(self.removed.values(), key=lambda r: (r.rule, r.stand_in))]

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.removed.values():
            out[r.rule] = out.get(r.rule, 0) + 1
        return out

    def leaks(self, text: str) -> list[str]:
        """Originals removed somewhere that are still in this text (as whole words), and denylist terms."""
        found = []
        for r in self.removed.values():
            if r.rule in ("ergostat-path", "python-path") or len(r.original) < MIN_NAME:
                continue
            if re.search(r"(?<![\w-])" + re.escape(r.original) + r"(?![\w-])", text, re.I):
                found.append(r.original)
        for rule, rx, _ in self._rules:
            if rule == "denylist":
                found += [m.group(0) for m in rx.finditer(text)]
        return found

    def seal(self, text: str) -> str:
        """The final pass over the whole text: whatever was removed anywhere, and whatever the denylist names, removed
        here too (a name that reached the text by a way no field's scrubbing saw)."""
        for _ in range(3):
            left = self.leaks(text)
            if not left:
                return text
            for orig in sorted(set(left), key=len, reverse=True):
                prior = next((r for r in self.removed.values() if r.original.lower() == orig.lower()), None)
                s = prior.stand_in if prior else self.stand_in(orig, "denylist")
                if prior:
                    prior.count += 1
                text = re.sub(r"(?<![\w-])" + re.escape(orig) + r"(?![\w-])", s, text, flags=re.I)
        return text


def path_rule(path: str) -> str:
    """Which path it is: one of ergostat's own files (kept, package-relative), one of Python's (kept, from python3.N/),
    or the owner's (replaced)."""
    p = path.replace("\\", "/")
    if "/ergostat/" in p and re.search(r"\.(py|js|md|yaml|css|html)$", p) and (PACKAGE_ROOT / original_rel(p)).exists():
        return "ergostat-path"
    if re.search(r"/lib/python3\.\d+/.+\.py$", p):
        return "python-path"
    return "path"


def original_rel(path: str) -> str:
    p = path.replace("\\", "/")
    i = p.rfind("/ergostat/")
    return p[i + 1:] if i >= 0 else p


def python_rel(path: str) -> str:
    p = path.replace("\\", "/")
    m = re.search(r"python3\.\d+/.*$", p)
    return m.group(0) if m else p


def getpass_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


# ---- what is scrubbed: the model's names, the owner's denylist, and ergostat's own names that stay

def deny_files(state_dir: Path | None) -> list[Path]:
    from ..store import home
    out = [home() / "reports-denylist.txt"]
    if state_dir is not None:
        out.insert(0, Path(state_dir) / "reports" / "denylist.txt")
    return out


def denylist(state_dir: Path | None) -> list[str]:
    terms: list[str] = []
    for f in deny_files(state_dir):
        try:
            terms += [t.strip() for t in f.read_text().splitlines() if t.strip() and not t.strip().startswith("#")]
        except OSError:
            continue
    return terms


_PUBLIC: set[str] | None = None


def public_names() -> set[str]:
    """The names ergostat's own templates give their parts (the modelling loop's model-error, improver, judge): ergostat's
    words, not the owner's, kept."""
    global _PUBLIC
    if _PUBLIC is None:
        import yaml
        got: set[str] = {"ergostat", "owner", "modelling"}
        base = Path(__file__).resolve().parent.parent / "library" / "templates"
        for f in list(base.glob("*.yaml")) + list(base.glob("*/template.yaml")):
            try:
                doc = yaml.safe_load(f.read_text()) or {}
            except Exception:
                continue
            got.add(str(doc.get("template") or f.stem))
            for sec, entries in doc.items():
                if isinstance(entries, dict) and sec not in ("params",):
                    got |= {str(k) for k in entries if "$" not in str(k)}
        _PUBLIC = got
    return _PUBLIC


def model_names(spec) -> tuple[dict[str, str], set[str]]:
    """Every name the owner gave in the model, with what it names; and the id prefixes of their item kinds."""
    names: dict[str, str] = {}
    kinds: set[str] = set()
    if spec is None:
        return names, kinds

    def put(n, what):
        if n and isinstance(n, str) and not n.startswith("ergostat"):
            names.setdefault(n, what)
    for what, table in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries), ("goal", spec.goals),
                        ("block", spec.blocks), ("agent", spec.agents), ("source", spec.sources), ("system", spec.systems),
                        ("parameter", spec.parameters), ("loop", spec.named_loops), ("context", spec.contexts),
                        ("action", spec.actions), ("pool", spec.workspaces), ("use", spec.uses), ("remote", spec.remotes),
                        ("check", spec.claims)):
        for n in table or {}:
            put(n, what)
    for k in (spec.items or {}).values():
        if k.name.startswith("ergostat."):
            continue
        put(k.name, "kind")
        prefix = k.id.split("/", 1)[0] if "/" in k.id else k.id.rstrip("*")
        if prefix and not any(ch in prefix for ch in "*?["):
            put(prefix, "kind")
            names[prefix] = "kind"
            kinds.add(prefix)
        for st in k.states:
            if st.lower() not in COMMON:
                put(st, "state")
        for t in k.on:
            put(t, "event")
        for f in k.show:
            if f.lower() not in COMMON:
                put(f, "field")
    for s in spec.sensors() if callable(getattr(spec, "sensors", None)) else []:
        if s.name not in ("main",):
            put(s.name, "sensor")
    put(spec.name, "model")
    if getattr(spec, "root", None):
        put(Path(spec.root).name, "folder")
    for f in getattr(spec, "files", []) or []:
        put(Path(f).stem, "file")
    return names, kinds


def for_project(p=None, spec=None) -> Scrubber:
    """The scrubber for a project: its model's names, its denylist and the home folder's."""
    spec = spec if spec is not None else getattr(getattr(p, "model", None), "spec", None)
    names, kinds = model_names(spec)
    if p is not None and getattr(p, "model", None) is not None and spec is None:   # an ergostat.toml: its parts' names
        m = p.model
        for what, table in (("stock", getattr(m, "stocks", {})), ("flow", getattr(m, "flows", {})),
                            ("agent", getattr(m, "agents", {}))):
            for n in table or {}:
                names.setdefault(n, what)
        if getattr(m, "name", None):
            names.setdefault(m.name, "model")
    public = public_names()
    names = {n: w for n, w in names.items() if n.lower() not in public}
    return Scrubber(names=names, kinds=kinds, deny=denylist(getattr(p, "dir", None)), public=public)
