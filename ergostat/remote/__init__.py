"""Remote systems (docs/proposals/remote-systems.md, SPEC §4c): a system run by another ergostat, composed into
this model. The remote serves its model, events, items and measurements read-only (``serve.py``, behind
``tokens.py``; the web side is ``web/remote_api.py``); this side declares it under ``remotes:``, keeps its model
in the state folder (``cache.py``, over ``client.py``), puts its parts in as an external subsystem
(``compose.py``) and reads its measurements in place (``readings.py``); its box shows its measures, marked stale
when not current (``measures.py``). Nothing here runs anything there."""


def remote_of(spec, ref: str) -> str | None:
    """The remote a part (``stock.incidents-open``) was brought in from, or None for the model's own."""
    for name, r in (getattr(spec, "remotes", None) or {}).items():
        if ref in (r.get("parts") or {}):
            return name
    return None


def remote_parts(spec) -> set[str]:
    """Every part (``kind.name``) brought in from a remote: the remote's business, endogenous there and data here
    (SPEC §4c). Its stocks are given, never integrated, in the replay and the projection (``simulate.plan``, unless
    asked for by name); they are left out of the fit's total (``fit.compare``: listed under ``remote``), the
    residuals (``residuals.unread``/``examinable``), what the record has not exercised (``exercised.quiet``), and the
    state's account of each stock's change and of what its loops ask of the owner (``state.py``). Its flows keep
    their equations: the estimate and the equation finder still use them for texts for its owner
    (``numbers/remote_text.py``)."""
    return {p for r in (getattr(spec, "remotes", None) or {}).values() for p in (r.get("parts") or {})}


def attention(spec) -> list[dict]:
    """Each remote that does not answer, or whose readings fail, as the status lists what needs the owner."""
    import time
    from pathlib import Path

    from ..durations import human
    from . import cache
    out = []
    for name, r in (getattr(spec, "remotes", None) or {}).items():
        st = cache.status(Path(r["dir"])) if r.get("dir") else {}
        last = st.get("read") or st.get("answered")
        age = f"; its readings here are {human(time.time() - last)} old" if last else "; nothing of it has been read"
        if st.get("ok") is False:
            since = st.get("failing_since")
            out.append({"level": "warn", "what": f"remote {name}",
                        "says": f"{r['url']} does not answer ({st.get('why')})"
                        + (f" since {human(time.time() - since)} ago" if since else "") + age})
        elif st.get("read_ok") is False:
            out.append({"level": "warn", "what": f"remote {name}", "says": f"its readings fail ({st.get('read_why')})" + age})
    return out


def system_remote(spec, system: str | None) -> str | None:
    """The remote a system belongs to (the remote's own system, or one of its systems inside it), or None."""
    remotes = getattr(spec, "remotes", None) or {}
    if not remotes or not system:
        return None
    for s in spec.chain(system):
        if s in remotes:
            return s
    return None


def box(spec, system: str | None) -> dict | None:
    """What a system's box says when it is a remote's (SPEC §4c): drawn marked remote, with where it runs, the version
    of its model, and how old its readings are (or since when it has not answered)."""
    import time
    from pathlib import Path

    from ..durations import human
    from . import cache
    name = system_remote(spec, system)
    if name is None:
        return None
    r = spec.remotes[name]
    st = cache.status(Path(r["dir"])) if r.get("dir") else {}
    now = time.time()
    last = st.get("read") or st.get("answered")
    if st.get("ok") is False or st.get("read_ok") is False:
        since = st.get("failing_since") or st.get("read_failing_since")
        says = "not answering" + (f" for {human(now - since)}" if since else "")
        says += f" · readings {human(now - last)} old" if last else " · never read"
        state = "unreachable"
    elif last:
        says, state = f"read {human(now - last)} ago", "ok"
    else:
        says, state = "not read yet", "unknown"
    v = r.get("version")
    return {"name": name, "url": r["url"], "version": v, "state": state, "missing": len(r.get("missing") or []), "now": says,
            "says": f"remote · {r['url'].split('://', 1)[-1]}" + (f" · v{v[:7]}" if v else "") + f" · {says}"}
