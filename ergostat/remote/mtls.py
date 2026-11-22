"""Mutual TLS for remote systems (SPEC §4c): ``web: mtls:`` (a second listener serving only the remote API, to
clients whose certificate the owner's ``client-ca`` signed) and a remote entry's ``tls:`` (the certificate this
ergostat shows, and the CA it trusts for the remote's). Every file is checked on its own, so the error names it, and
a context that can't be built raises: nothing falls back to no client certificate or to the system's trust."""

from __future__ import annotations

import ipaddress
import ssl
from dataclasses import dataclass
from pathlib import Path

KEYS = {"port", "bind", "cert", "key", "client-ca"}
TLS_KEYS = {"cert", "key", "ca"}


class MtlsError(Exception):
    """A file of a TLS context that could not be read: its key, its path as written, and why."""


@dataclass
class Mtls:
    port: int
    bind: str
    cert: str
    key: str
    client_ca: str


def parse(raw, problems: list[str]) -> Mtls | None:
    """``web.mtls`` as written, or None (with why in ``problems``, each a ``bad-web``)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append("web.mtls: a map (port:, bind:, cert:, key:, client-ca:)")
        return None
    bad = len(problems)
    for k in sorted(set(map(str, raw)) - KEYS):
        problems.append(f"web.mtls: unknown key {k!r} (known: {', '.join(sorted(KEYS))})")
    port = raw.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        problems.append(f"web.mtls.port: a port, 1 to 65535 (not {port!r})")
    bind = str(raw.get("bind") or "0.0.0.0")
    try:
        ipaddress.ip_address(bind)
    except ValueError:
        problems.append(f"web.mtls.bind: {bind!r} is not an address (0.0.0.0, 127.0.0.1, ::)")
    for k in ("cert", "key", "client-ca"):
        if not isinstance(raw.get(k), str) or not raw[k].strip():
            problems.append(f"web.mtls.{k}: the path of a PEM file, required")
    if len(problems) > bad:
        return None
    return Mtls(port, bind, raw["cert"], raw["key"], raw["client-ca"])


def parse_tls(raw, url: str, root: Path, err) -> dict | None:
    """A remote entry's ``tls:``: ``{cert, key[, ca]}`` with each path made absolute, or None after ``err(msg)``."""
    if not isinstance(raw, dict):
        return err("tls: a map of cert:, key: and (optional) ca:")
    if not url.startswith("https://"):
        return err(f"tls: needs an https:// url (not {url})")
    wrong = [f"unknown key {k!r} in tls (known: cert, key, ca)" for k in sorted(set(map(str, raw)) - TLS_KEYS)]
    wrong += [f"tls.{k}: the path of a PEM file, required" for k in ("cert", "key")
              if not isinstance(raw.get(k), str) or not raw[k].strip()]
    if raw.get("ca") is not None and not (isinstance(raw["ca"], str) and raw["ca"].strip()):
        wrong.append("tls.ca: the path of a PEM file")
    for w in wrong:
        err(w)
    return None if wrong else {k: str(path(raw[k], root)) for k in TLS_KEYS if raw.get(k)}


def path(p: str, root: Path | None) -> Path:
    f = Path(p).expanduser()
    return f if f.is_absolute() or root is None else Path(root) / f


def _step(which: str, shown: str, f: Path, load) -> str | None:
    """Why ``load()`` of file ``f`` fails, as ``which shown: why``, or None."""
    if not f.exists():
        return f"{which} {shown}: no such file"
    if f.is_dir():
        return f"{which} {shown}: is a directory, not a PEM file"
    try:
        load()
    except (ssl.SSLError, OSError, ValueError) as e:
        return f"{which} {shown}: {getattr(e, 'reason', None) or getattr(e, 'strerror', None) or e}"
    return None


def _certs(f: Path) -> None:
    """``f`` holds PEM certificates (loaded into a scratch context: never the system's trust)."""
    ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=str(f))


def _server_steps(conf: Mtls, root: Path | None, ctx: ssl.SSLContext) -> list[str]:
    cert, key, ca = path(conf.cert, root), path(conf.key, root), path(conf.client_ca, root)
    out = [_step("web.mtls.cert", conf.cert, cert, lambda: _certs(cert))]
    if out[0] is None:                               # the key is tried against a cert known good: its error is the key's
        out.append(_step("web.mtls.key", conf.key, key, lambda: ctx.load_cert_chain(str(cert), str(key))))
    out.append(_step("web.mtls.client-ca", conf.client_ca, ca, lambda: ctx.load_verify_locations(cafile=str(ca))))
    return [x for x in out if x]


def unreadable(conf: Mtls, root: Path | None) -> list[str]:
    """Each of ``web.mtls``'s files that can't be loaded (``mtls-unreadable``)."""
    return _server_steps(conf, root, ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER))


def server_context(conf: Mtls, root: Path | None) -> ssl.SSLContext:
    """TLS 1.2 at least, a client certificate required, and trusted only when ``client-ca`` signed it."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    bad = _server_steps(conf, root, ctx)
    if bad:
        raise MtlsError(bad[0])
    return ctx


def unreadable_tls(tls: dict) -> list[str]:
    """Each of a remote's ``tls:`` files that can't be loaded (``mtls-unreadable``)."""
    cert, key = Path(tls["cert"]), Path(tls["key"])
    out = [_step("tls.cert", tls["cert"], cert, lambda: _certs(cert))]
    if out[0] is None:
        out.append(_step("tls.key", tls["key"], key,
                         lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_cert_chain(str(cert), str(key))))
    if tls.get("ca"):
        out.append(_step("tls.ca", tls["ca"], Path(tls["ca"]), lambda: _certs(Path(tls["ca"]))))
    return [x for x in out if x]


def client_context(tls: dict, root: Path | None = None) -> ssl.SSLContext:
    """The context a remote is read with: its ``ca`` (else the system's trust), the host name checked, TLS 1.2 at least,
    and this ergostat's certificate. Every file is checked before any context is made; any failure raises."""
    if not isinstance(tls, dict) or not tls.get("cert") or not tls.get("key"):
        raise MtlsError("not a map with cert: and key:")
    tls = {k: str(path(v, root)) for k, v in tls.items() if k in TLS_KEYS and v}
    bad = [b.removeprefix("tls.") for b in unreadable_tls(tls)]
    if bad:
        raise MtlsError(bad[0])
    try:
        ctx = ssl.create_default_context(cafile=tls["ca"]) if tls.get("ca") else ssl.create_default_context()
        ctx.check_hostname = True
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_cert_chain(tls["cert"], tls["key"])
    except (ssl.SSLError, OSError, ValueError) as e:
        raise MtlsError(f"{e}") from None
    return ctx
