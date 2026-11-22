"""The page behind a public name (SPEC §4d): ``web:`` as written (main file only), and Cloudflare Access's login
checked on every request that came that way.

    web:
      names: [ergostat.example.org]          # the public names the page answers to (a tunnel's hostname)
      access:                                # the Cloudflare Access application in front of them
        team: myteam.cloudflareaccess.com    # its team domain (``myteam`` alone is the same)
        aud: 4714c1358e65fe4b...             # its Application Audience (AUD) tag
        emails: [owner@example.org]          # who may use the page

A request under a public name carries ``Cf-Access-Jwt-Assertion``: a JWT, RS256, signed with one of the team's keys
(``https://TEAM/cdn-cgi/access/certs``). It is verified here with the standard library alone (RSASSA-PKCS1-v1_5 is
one modular power and a comparison), its ``aud``, ``iss`` and ``exp`` checked, and its ``email`` looked up in the
allowlist. Who it names is who answered (``who()``), where a local request is the owner."""

from __future__ import annotations

import base64
import contextvars
import hashlib
import hmac
import json
import math
import re
import threading
import time
import urllib.request
from dataclasses import dataclass, field

CERTS = "https://{team}/cdn-cgi/access/certs"     # where a team's keys are published
REFRESH = 3600.0          # the keys are fetched again at least this often
STALE = 86400.0           # and keys that could not be fetched again for this long are not trusted
RETRY = 30.0              # and an unknown key fetches them again, at most this often
LEEWAY = 30.0             # seconds of clock difference allowed on exp and nbf
HEADERS = ("Cf-Access-Jwt-Assertion", "Cf-Ray", "Cf-Connecting-Ip")   # any one: the request came through Cloudflare
SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")  # DigestInfo's prefix for SHA-256 (RFC 8017 §9.2)
NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

_who: contextvars.ContextVar[str] = contextvars.ContextVar("ergostat_web_who", default="owner")


def who() -> str:
    """Who is answering through the page in this request: the email Access verified, or ``owner`` on this machine."""
    return _who.get()


def acting(name: str) -> contextvars.Token:
    """Who answers, until ``done``: the request's writes record it."""
    return _who.set(name)


def done(token: contextvars.Token) -> None:
    _who.reset(token)


@dataclass
class Web:
    names: list[str] = field(default_factory=list)
    team: str | None = None
    aud: str | None = None
    emails: set[str] = field(default_factory=set)
    open: bool = False        # ``open: read``: the names are public and read only, with no login
    mtls: object = None       # ``mtls:``: the remote API on a listener of its own, over mutual TLS (remote/mtls.py)

    @property
    def issuer(self) -> str:
        return f"https://{self.team}"


def parse(raw, problems: list[str]) -> Web:
    out = Web()
    if raw is None:
        return out
    if not isinstance(raw, dict):
        problems.append("web: a map (names:, access: or open: read)")
        return out
    for k in set(raw) - {"names", "access", "open", "mtls"}:
        problems.append(f"web: unknown key {k!r} (known: names, access, open, mtls)")
    from .remote import mtls
    out.mtls = mtls.parse(raw.get("mtls"), problems)
    names = raw.get("names") or []
    for n in [names] if isinstance(names, str) else names if isinstance(names, list) else [names]:
        if isinstance(n, str) and NAME.match(n.lower()):
            out.names.append(n.lower())
        else:
            problems.append(f"web.names: {n!r} is not a host name (ergostat.example.org: no scheme, port or path)")
    acc = raw.get("access")
    if raw.get("open") is not None:
        out.open = raw["open"] == "read" and acc is None
        if not out.open:
            problems.append("web.open: read (the names public and read only, with no login), and never with access:")
        return out
    if acc is None:
        if out.names:
            problems.append("web.names: a public name needs web.access (team, aud, emails), or open: read (public, read only, "
                            "no login): nothing is served there otherwise")
        return out
    if not isinstance(acc, dict):
        problems.append("web.access: a map (team:, aud:, emails:)")
        return out
    for k in set(acc) - {"team", "aud", "emails"}:
        problems.append(f"web.access: unknown key {k!r} (known: team, aud, emails)")
    team = str(acc.get("team") or "").lower().removeprefix("https://").rstrip("/")
    team = team if "." in team else f"{team}.cloudflareaccess.com" if team else ""
    if NAME.match(team):
        out.team = team
    else:
        problems.append("web.access.team: the Access team domain (myteam.cloudflareaccess.com)")
    if isinstance(acc.get("aud"), str) and acc["aud"].strip():
        out.aud = acc["aud"].strip()
    else:
        problems.append("web.access.aud: the Access application's audience tag (AUD), as text")
    emails = acc.get("emails")
    emails = [emails] if isinstance(emails, str) else emails
    if isinstance(emails, list) and emails and all(isinstance(e, str) and "@" in e for e in emails):
        out.emails = {e.strip().lower() for e in emails}
    else:
        problems.append("web.access.emails: the emails that may use the page, a list")
    return out


def of(spec) -> Web | None:
    return getattr(spec, "web", None)


# ---- the team's keys

_keys: dict[str, tuple[float, float, dict]] = {}       # team → (fetched, last tried, {kid: (n, e)})
_fetching = threading.Lock()                           # one fetch at a time; the others answer from the cache


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _int(s: str) -> int:
    return int.from_bytes(_b64(s), "big")


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read(1 << 20))


def key(team: str, kid: str, now: float | None = None) -> tuple[int, int] | None:
    """The team's key ``kid``: from the cache, fetched again when it is older than REFRESH, or when the key is not
    in it and the last try was RETRY ago or more (a key rotated in; a token naming no key never floods the team).
    One request fetches while the others answer from the cache (a slow team never holds up the page); a failed fetch
    keeps the keys there were, for STALE at most."""
    now = time.time() if now is None else now
    fetched, tried, ks = _keys.get(team, (0.0, 0.0, {}))
    if not ks and _fetching.acquire(timeout=6):        # no keys yet: a fetch under way is waited for, not refused
        _fetching.release()
        fetched, tried, ks = _keys.get(team, (0.0, 0.0, {}))
    if (now - fetched > REFRESH or kid not in ks) and now - tried >= RETRY and _fetching.acquire(blocking=False):
        try:
            _keys[team] = (fetched, now, ks)
            got = fetch(CERTS.format(team=team))
            ks = {k["kid"]: (_int(k["n"]), _int(k["e"])) for k in got.get("keys", [])
                  if k.get("kty") == "RSA" and k.get("kid") and k.get("n") and k.get("e")}
            fetched = now
            _keys[team] = (fetched, now, ks)
        except Exception:                             # unreachable or malformed: the cached keys stand
            pass
        finally:
            _fetching.release()
    return ks.get(kid) if now - fetched <= STALE else None


def rs256_ok(n: int, e: int, signed: bytes, sig: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256 (RFC 8017 §8.2.2): the signature raised to ``e`` mod ``n`` is exactly the padded
    digest of what was signed."""
    k = (n.bit_length() + 7) // 8
    if k < 256 or len(sig) != k or int.from_bytes(sig, "big") >= n:     # keys of 2048 bits or more
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    digest = SHA256_INFO + hashlib.sha256(signed).digest()
    return hmac.compare_digest(em, b"\x00\x01" + b"\xff" * (k - 3 - len(digest)) + b"\x00" + digest)


class Refused(Exception):
    def __init__(self, code: int, why: str):
        super().__init__(why)
        self.code = code


def verify(web: Web | None, jwt: str | None, now: float | None = None) -> str:
    """The email a request's Access token vouches for, or ``Refused``: 401 without a valid token, 403 for an email
    not allowed, or when the project declares no login."""
    if web is not None and web.open:
        raise Refused(403, f"only {', '.join(web.names)} is open (read only, no login): the tunnel must keep that Host")
    if web is None or not (web.team and web.aud and web.emails):
        raise Refused(403, "this page has no login for a public name (web.access in the model)")
    if not jwt:
        raise Refused(401, "a Cloudflare Access login is needed (Cf-Access-Jwt-Assertion)")
    now = time.time() if now is None else now
    try:
        head, body, sig = jwt.split(".")
        h, c = json.loads(_b64(head)), json.loads(_b64(body))
        if h.get("alg") != "RS256" or not isinstance(c, dict):
            raise ValueError
        k = key(web.team, str(h["kid"]), now)
        if k is None or not rs256_ok(*k, f"{head}.{body}".encode(), _b64(sig)):
            raise ValueError
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise Refused(401, "the Access token is not one this team signed") from None
    aud = c.get("aud") if isinstance(c.get("aud"), list) else [c.get("aud")]
    if web.aud not in aud or c.get("iss") != web.issuer:
        raise Refused(401, "the Access token is for another application")
    exp, nbf = c.get("exp"), c.get("nbf", now)
    numbers = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (exp, nbf))
    if not numbers or exp < now - LEEWAY or nbf > now + LEEWAY:
        raise Refused(401, "the Access token has expired")
    email = str(c.get("email") or "").lower()
    if email not in web.emails:
        raise Refused(403, f"{email or 'this login'} may not use this page")
    return email
