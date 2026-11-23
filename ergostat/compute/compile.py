"""Reading ``compute:`` (SPEC §12k, *Compute pools*) into the spec, every mistake said with where it was written, and
every number that multiplies runs held under a ceiling here (review lesson 4). Called by the spec compiler with
itself, for its ``named``, ``keys``, ``duration`` and ``err``; and a block's ``runs-on:`` (``runs_on``, ``pools_used``).
Nothing is run or reached: a secret's file is only named; the one file read is a ``runs-on`` block's script, for calls."""

from __future__ import annotations

import math
import re

from ..spec.ir import NAME, ComputePool

POOL_KEYS = {"nodes", "backend", "image", "slots", "limits", "repos", "secrets", "labels", "description"}
LIMIT_KEYS = {"cpus", "memory", "pids", "disk", "wall", "network", "log"}
BACKENDS = ("process", "docker")
NETWORKS = ("none", "host")
MAX_NODES = 64                    # a pool's nodes, and all pools' together (one connection each)
MAX_SLOTS = 64                    # runs at once on one node
MAX_RUNS = 256                    # nodes × slots, summed over all pools
MAX_WALL = 86400.0                # a run's wall time: a day
LOG, MAX_LOG = 64 << 20, 1 << 30  # each of a run's output files: 64 MiB unless said, at most 1 GiB
HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")    # a Host of the owner's ~/.ssh/config (never an option)
ADDRESS = re.compile(r"^[0-9.]+$|[:\[\]]")                  # IPv4, IPv6, or a host:port
SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:([kmgt])i?)?b?\s*$", re.IGNORECASE)
SECRET = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")             # an environment variable's name
LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
NODE = "{ssh: HOST} or {connect: [COMMAND, ARG, ...]}"
CALLS = re.compile(r"ERGOSTAT_CMD|ERGOSTAT_SOCKET|\bergostat(?:\s|$)", re.MULTILINE)   # a call back to the engine
MAX_SCRIPT = 8 << 20              # a script is read whole for calls; a larger one counts as calling


def size(v) -> int | None:
    """Bytes, from ``4g``, ``512MiB`` or ``1024`` (bytes); multiples of 1024. None: not a size above 0."""
    if isinstance(v, int) and not isinstance(v, bool):
        return v if v > 0 else None
    m = SIZE.match(v) if isinstance(v, str) else None
    if m is None:
        return None
    n = float(m.group(1)) * 1024 ** " kmgt".index((m.group(2) or " ").lower())
    return (int(n) or None) if math.isfinite(n) else None       # 9…9 overflows to inf: not a size, not a crash


def whole(c, m, key: str, what: str, default: int, most: int, over: str) -> int:
    v = m.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        c.err(f"{what}.{key}: a whole number, 1 or more", m.at(key), "bad-number")
        return default
    if v > most:
        c.err(f"{what}.{key}: at most {most}", m.at(key), over)
        return most
    return v


def nodes(c, m, what: str) -> list[dict]:
    xs = m.get("nodes")
    if not isinstance(xs, list) or not xs:
        c.err(f"{what}.nodes: a list of nodes, each {NODE}", m.at("nodes"), "missing-key" if xs is None else "bad-node")
        return []
    if len(xs) > MAX_NODES:
        c.err(f"{what}.nodes: at most {MAX_NODES} ({len(xs)} here)", m.at("nodes"), "too-many-nodes")
        return []
    out = []
    for i, x in enumerate(xs, 1):
        at, one = getattr(x, "where", None) or m.at("nodes"), f"{what}.nodes[{i}]"
        h = x.get("ssh") if isinstance(x, dict) else None
        if not isinstance(x, dict) or len(x) != 1 or not {"ssh", "connect"} & set(x):
            c.err(f"{one}: {NODE}, one of them", at, "bad-node")
        elif isinstance(h, str) and "@" in h:
            c.err(f"{one}.ssh: a Host name of your ~/.ssh/config, not a user (its User line says that)", at,
                  "node-names-user")
        elif isinstance(h, str) and ADDRESS.search(h):
            c.err(f"{one}.ssh: a Host name of your ~/.ssh/config, not an address (its HostName line says that)", at,
                  "node-names-address")
        elif "ssh" in x:
            if isinstance(h, str) and HOST.fullmatch(h):     # fullmatch: `$` alone lets "node-1\n" by
                out.append({"ssh": h})
            else:
                c.err(f"{one}.ssh: a Host name of your ~/.ssh/config (letters, digits, . _ -)", at, "bad-node")
        elif isinstance(x["connect"], list) and x["connect"] and all(isinstance(a, str) and a for a in x["connect"]):
            out.append({"connect": list(x["connect"])})
        else:
            c.err(f"{one}.connect: the command and its arguments, as a list of words", at, "bad-node")
    return out


def limits(c, m, what: str, backend: str) -> dict:
    lim, out = m.get("limits"), {"log": LOG}
    if lim is None:
        return out
    if not isinstance(lim, dict):
        c.err(f"{what}.limits: a map of {', '.join(sorted(LIMIT_KEYS))}", m.at("limits"), "not-a-map")
        return out
    what = f"{what}.limits"
    c.keys(lim, LIMIT_KEYS, what)
    for k in ("memory", "disk", "log"):
        n = size(lim[k]) if k in lim else None
        if k in lim and n is None:
            c.err(f"{what}.{k}: a size above 0, like 512m, 4g or 1GiB (or a number of bytes)", lim.at(k), "bad-size")
        elif k == "log" and n is not None and n > MAX_LOG:
            c.err(f"{what}.log: at most 1g (each of a run's output files)", lim.at(k), "log-over-cap")
        elif n is not None:
            out[k] = n
    wall = c.duration(lim, "wall", what)
    if wall is not None and not wall <= MAX_WALL:                     # NaN refused too
        c.err(f"{what}.wall: at most a day (1d)", lim.at("wall"), "wall-over-a-day")
    elif wall is not None:
        out["wall"] = wall
    cpus = lim.get("cpus")
    if cpus is not None and (isinstance(cpus, bool) or not isinstance(cpus, int | float) or not math.isfinite(cpus)
                             or cpus <= 0):
        c.err(f"{what}.cpus: a number above 0 (2, or 0.5 for half of one)", lim.at("cpus"), "bad-number")
    elif cpus is not None:
        out["cpus"] = float(cpus)
    if "pids" in lim:
        out["pids"] = whole(c, lim, "pids", what, 1, 1 << 22, "bad-number")
    net = lim.get("network")
    if net is not None and net not in NETWORKS:
        c.err(f"{what}.network: {' or '.join(NETWORKS)}", lim.at("network"), "bad-network")
    elif net == "none" and backend == "process":
        c.err(f"{what}.network: none needs backend: docker (the process backend cannot hold a run off the network, "
              f"and does not pretend to)", lim.at("network"), "network-on-process")
    elif net is not None:
        out["network"] = net
    return out


def table(c, m, key: str, what: str, names: re.Pattern, say: str) -> dict[str, str]:
    v = m.get(key)
    if v is None:
        return {}
    if not isinstance(v, dict) or not all(isinstance(k, str) and names.fullmatch(k) and isinstance(x, str) and x
                                          for k, x in v.items()):
        c.err(f"{what}.{key}: {say}", m.at(key), f"bad-{key}")
        return {}
    return dict(v)


def calls(c, run) -> str | None:
    """What says a command calls ergostat back (``ERGOSTAT_CMD``, ``ERGOSTAT_SOCKET``, ``ergostat ...``), which no node
    can answer yet: in the command as written, or in the file of the model's folder its first word names. A file
    that is there and cannot be read counts as calling (it cannot be shown not to). None: neither says so."""
    text = str(run or "")
    if CALLS.search(text):
        return "its command"
    f = c.doc.root / text.split()[0] if text.split() else None
    try:
        if f is None or not f.is_file():
            return None
        with f.open("rb") as h:
            body = h.read(MAX_SCRIPT + 1)
    except OSError:
        return f"its script {text.split()[0]} (which cannot be read)"
    if len(body) > MAX_SCRIPT:
        return f"its script {text.split()[0]} (over {MAX_SCRIPT >> 20} MiB, so not read whole)"
    return f"its script {text.split()[0]}" if CALLS.search(body.decode("utf-8", "replace")) else None


def runs_on(c, name: str, m, what: str, t: str) -> str | None:
    """A machine block's ``runs-on:``: the pool it names, or None for here (``local``, or none written). A block that
    cannot run on a node is refused at its key, as is a name no pool could have; whether the pool is there is said
    once every pool is read (``pools_used``)."""
    if "runs-on" not in m:
        return None
    v, at = m.get("runs-on"), m.at("runs-on")
    if v == "local":
        return None
    if not isinstance(v, str) or not NAME.fullmatch(v):
        c.err(f"{what}.runs-on: a pool's name (of compute:), or local", at, "bad-runs-on")
    elif t != "program":
        c.err(f"{what}.runs-on: only a program block runs on a pool; an {t} block's runs are here (for now)"
              if t == "ai" else f"{what}.runs-on: a {t} block is not run by a machine, here or on a node", at,
              f"runs-on-{t}")
    elif m.get("daemon") is not None:
        c.err(f"{what}.runs-on: a daemon's block is served by a daemon here (SPEC §9.7); it cannot run on a pool", at,
              "runs-on-daemon")
    elif (why := calls(c, m.get("run"))) is not None:
        c.err(f"{what}.runs-on: {why} calls ergostat (ERGOSTAT_CMD, ERGOSTAT_SOCKET or ergostat ...), which a node "
              f"cannot answer yet; run it here", at, "runs-on-calls")
    else:
        c.__dict__.setdefault("runs_on_at", {})[name] = at
        return v
    return None


def pools_used(c, spec) -> None:
    """Each pool a block's ``runs-on:`` names is there, and all a pool's blocks are in one engine shard (SPEC §9.8):
    a pool's slots are counted in one process. The shards are worked out only from a model with no error yet (one
    with an error is refused already, and its plan may not be made)."""
    at = c.__dict__.get("runs_on_at", {})
    on = {n: b for n, b in sorted(spec.blocks.items()) if b.runs_on}
    for n, b in on.items():
        if b.runs_on not in spec.compute:
            c.err(f"block {n}.runs-on: {b.runs_on!r} is not a pool of compute:" + c.suggest(b.runs_on, spec.compute),
                  at.get(n, b.where), "unknown-pool")
    if not on or any(p.level == "error" for p in c.problems):
        return
    from ..spec.shards import plan
    p, first = plan(spec), {}
    for n, b in on.items():
        f = first.setdefault(b.runs_on, n)
        if p.of(f"block.{n}") != p.of(f"block.{f}"):
            c.err(f"block {n}.runs-on: pool {b.runs_on} is used by block {f} too, in another shard "
                  f"({p.of(f'block.{f}')}, this one {p.of(f'block.{n}')}); a pool's blocks are in one system",
                  at.get(n, b.where), "pool-across-shards")


def compute(c, spec) -> None:
    for name, m, what in c.named("compute"):
        if name == "local":
            c.err(f"{what}: local is not a pool's name (runs-on: local means here)", m.where, "bad-name")
            continue
        c.keys(m, POOL_KEYS, what)
        backend = "process" if m.get("backend") is None else m.get("backend")     # only an absent backend defaults
        if backend not in BACKENDS:
            c.err(f"{what}.backend: {' or '.join(BACKENDS)}", m.at("backend"), "bad-backend")
        image = m.get("image")
        if image is not None and (not isinstance(image, str) or not image):
            c.err(f"{what}.image: the image's name, like ergostat-run:1", m.at("image"), "bad-image")
            image = None
        elif backend == "docker" and image is None:
            c.err(f"{what}: backend: docker needs image: (what each run's container is made from)", m.where,
                  "docker-needs-image")
        spec.compute[name] = ComputePool(
            name, nodes(c, m, what), backend, image, whole(c, m, "slots", what, 1, MAX_SLOTS, "too-many-slots"),
            limits(c, m, what, backend),
            table(c, m, "repos", what, NAME, "a map of a name to the repository's path here"),
            table(c, m, "secrets", what, SECRET, "a map of an environment variable's name (API_TOKEN) to the file "
                                                 "it is read from"),
            table(c, m, "labels", what, LABEL, "a map of a label to the text a node must say for it"),
            c.text(m, "description"), m.where)
    pools = list(spec.compute.values())
    if pools and sum(len(p.nodes) for p in pools) > MAX_NODES:
        c.err(f"compute: at most {MAX_NODES} nodes over all pools ({sum(len(p.nodes) for p in pools)} here)",
              pools[-1].where, "too-many-nodes")
    if pools and sum(len(p.nodes) * p.slots for p in pools) > MAX_RUNS:
        c.err(f"compute: nodes × slots at most {MAX_RUNS} over all pools "
              f"({sum(len(p.nodes) * p.slots for p in pools)} here)", pools[-1].where, "too-many-runs")
