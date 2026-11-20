"""The page behind a public name (SPEC §4d): a declared name is served only with a Cloudflare Access login for an
allowed email, verified against the team's keys (a local JWKS here, with a key made for the test), for reads too; a
request that came through Cloudflare needs it whatever its Host; any other name is refused; a request on this
machine is the owner, as before; a write made under the public name is recorded as the email's."""

import base64
import functools
import hashlib
import json
import random
import re
import textwrap
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ergostat import model as mdl
from ergostat import webaccess as wa
from ergostat.store import Project
from tests.ports import free_port

NAME = "ergostat.example.org"
TEAM = "myteam.cloudflareaccess.com"
AUD = "a1b2c3d4e5"
MODEL = f"""
name: public
stocks:
  queue: {{}}
web:
  names: [{NAME}]
  access: {{team: myteam, aud: {AUD}, emails: [Owner@Example.org]}}
"""


# ---- a test key, and tokens signed with it

def _prime(bits: int, rng: random.Random) -> int:
    while True:
        n = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(n % p for p in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)) and _probably_prime(n, rng):
            return n


def _probably_prime(n: int, rng: random.Random) -> bool:
    d, r = n - 1, 0
    while d % 2 == 0:
        d, r = d // 2, r + 1
    for _ in range(20):
        x = pow(rng.randrange(2, n - 2), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


@functools.cache
def _key(seed: int) -> tuple[int, int, int]:
    rng, e = random.Random(seed), 65537
    while True:
        p, q = _prime(1024, rng), _prime(1024, rng)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


KEY, OTHER = 1, 2         # the team's key, and one it never had (made when first used: a second or two)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sign(key, data: bytes) -> bytes:
    n, _, d = _key(key)
    k = (n.bit_length() + 7) // 8
    digest = wa.SHA256_INFO + hashlib.sha256(data).digest()
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(digest)) + b"\x00" + digest
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def jwt(key=KEY, kid="k1", alg="RS256", **claims) -> str:
    now = time.time()
    c = {"aud": [AUD], "iss": f"https://{TEAM}", "exp": now + 600, "iat": now, "email": "owner@example.org", **claims}
    head = _b64(json.dumps({"alg": alg, "kid": kid}).encode()) + "." + _b64(json.dumps(c).encode())
    return head + "." + _b64(_sign(key, head.encode()))


def _jwk(kid, key) -> dict:
    n, e, _ = _key(key)
    return {"kty": "RSA", "kid": kid, "alg": "RS256", "n": _b64(n.to_bytes(256, "big")), "e": _b64(e.to_bytes(3, "big"))}


@pytest.fixture(scope="module")
def _certs():
    """The team's keys, served on this machine; ``asked`` counts the fetches."""
    state = {"keys": [], "asked": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            state["asked"] += 1
            body = json.dumps({"keys": state["keys"]} if self.path == f"/{TEAM}/cdn-cgi/access/certs" else {}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{srv.server_address[1]}/{{team}}/cdn-cgi/access/certs"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def certs(_certs, monkeypatch):
    state, where = _certs
    state.update(keys=[_jwk("k1", KEY)], asked=0)
    monkeypatch.setattr(wa, "CERTS", where)
    monkeypatch.setattr(wa, "_keys", {})
    return state


@pytest.fixture(scope="module")
def _page(tmp_path_factory):
    from ergostat.web import serve
    d = tmp_path_factory.mktemp("public")
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(d))
    server, url = serve(p, free_port())
    yield p, url
    server.shutdown()
    server.server_close()


@pytest.fixture
def page(_page, certs):
    return _page


def ask(url: str, path: str, host: str | None = None, token: str | None = None, data: bytes | None = None, **headers):
    h = {**({"Host": host} if host else {}), **({"Cf-Access-Jwt-Assertion": token} if token else {}), **headers}
    req = urllib.request.Request(url + path, data=data, method="POST" if data is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def page_token(body: bytes) -> str:
    return re.search(rb'name="ergostat-token" content="([^"]*)"', body).group(1).decode()


# ---- reads

def test_a_valid_token_for_an_allowed_email_reads_the_page_under_the_public_name(page):
    _, url = page
    for path in ("/", "/api/status", "/static/util.js"):
        assert ask(url, path, NAME, jwt())[0] == 200, path
    assert ask(url, "/api/status", NAME.upper(), jwt(aud=AUD))[0] == 200         # names are any case; aud a string too


@pytest.mark.parametrize("bad", [
    None,
    {"exp": -3600},
    {"aud": ["another-app"]},
    {"iss": "https://otherteam.cloudflareaccess.com"},
    {"key": OTHER},                                                 # signed with a key the team does not have
    {"kid": "nobody"},
    {"alg": "HS256"},
    {"nbf": 3600},
    "not.a.jwt",
], ids=["missing", "expired", "wrong-aud", "wrong-iss", "bad-signature", "unknown-key", "alg", "not-yet", "garbage"])
def test_a_missing_expired_or_foreign_token_is_refused_for_reads_too(page, bad):
    _, url = page
    when = {k: time.time() + v for k, v in (bad or {}).items() if k in ("exp", "nbf")} if isinstance(bad, dict) else {}
    token = jwt(**{**bad, **when}) if isinstance(bad, dict) else bad
    for path in ("/", "/api/status", "/item/x"):
        code, body = ask(url, path, NAME, token)
        assert code == 401 and b"ergostat-token" not in body, path


def test_an_email_not_allowed_is_forbidden(page):
    _, url = page
    assert ask(url, "/api/status", NAME, jwt(email="someone@example.org"))[0] == 403
    assert ask(url, "/api/status", NAME, jwt(email=None))[0] == 403                 # a service token: no email


def test_through_the_tunnel_with_the_host_rewritten_still_needs_the_login(page, tmp_path):
    _, url = page
    local = url.removeprefix("http://")
    assert ask(url, "/api/status", local, None, **{"Cf-Ray": "8f00-LHR"})[0] == 401
    assert ask(url, "/", local, None, **{"Cf-Connecting-Ip": "203.0.113.9"})[0] == 401
    assert ask(url, "/api/status", local, jwt(), **{"Cf-Ray": "8f00-LHR"})[0] == 200


def test_through_the_tunnel_with_no_login_declared_nothing_is_read(tmp_path, certs):
    from ergostat.web import serve
    (tmp_path / "ergostat.yaml").write_text("name: plain\nstocks:\n  queue: {}\n")
    server, url = serve(Project(mdl.load(tmp_path)), free_port())
    try:
        assert ask(url, "/api/status", None, jwt(), **{"Cf-Ray": "8f00-LHR"})[0] == 403
        assert ask(url, "/api/status", NAME, jwt())[0] == 403
        assert ask(url, "/api/status")[0] == 200
    finally:
        server.shutdown()
        server.server_close()


def test_a_foreign_host_is_still_refused(page):
    _, url = page
    for host in ("evil.example.com", f"{NAME}.evil.example.com", f"evil.example.com:{url.rsplit(':', 1)[1]}"):
        assert ask(url, "/api/status", host)[0] == 403, host
        assert ask(url, "/api/status", host, jwt())[0] == 403, host


def test_local_requests_behave_as_today(page):
    p, url = page
    code, body = ask(url, "/")
    assert code == 200
    t = page_token(body)
    assert ask(url, "/api/status")[0] == 200
    code, got = ask(url, "/api/message", data=json.dumps({"text": "hold the queue"}).encode(), **{"X-Ergostat-Token": t})
    assert code == 200 and json.loads(got)["by"] == "owner"
    assert ask(url, "/api/message", data=b"{}", **{"X-Ergostat-Token": "wrong"})[0] == 403
    assert ask(url, "/api/message", data=b"{}", **{"X-Ergostat-Token": t, "Origin": f"https://{NAME}"})[0] == 403


# ---- writes

def test_a_write_under_the_public_name_is_recorded_with_the_email(page):
    p, url = page
    t = page_token(ask(url, "/", NAME, jwt())[1])
    body = json.dumps({"text": "please look at the queue"}).encode()
    hdr = {"X-Ergostat-Token": t, "Origin": f"https://{NAME}", "Sec-Fetch-Site": "same-origin"}
    assert ask(url, "/api/message", NAME, None, body, **hdr)[0] == 401                       # the login, for writes too
    code, got = ask(url, "/api/message", NAME, jwt(), body, **hdr)
    got = json.loads(got)
    assert code == 200 and got["by"] == "owner@example.org"
    ev = p.events.query(n=50, item=got["id"])                                               # and so in the record
    assert ev and "owner@example.org" in json.dumps(ev) and '"owner"' not in json.dumps(ev)
    code, got = ask(url, "/api/message", data=body, **{"X-Ergostat-Token": t})              # and then, locally: the owner
    assert code == 200 and json.loads(got)["by"] == "owner"


def test_a_write_from_another_origin_is_refused_under_the_public_name(page):
    _, url = page
    t = page_token(ask(url, "/", NAME, jwt())[1])
    for origin in ("https://evil.example.com", f"http://{NAME}"):
        assert ask(url, "/api/message", NAME, jwt(), b"{}", **{"X-Ergostat-Token": t, "Origin": origin})[0] == 403
    assert ask(url, "/api/message", NAME, jwt(), b"{}", **{"X-Ergostat-Token": "wrong", "Origin": f"https://{NAME}"})[0] == 403


# ---- the keys, and the configuration

def test_the_keys_are_cached_and_refreshed_at_most_so_often(certs):
    web = wa.parse({"names": [NAME], "access": {"team": TEAM, "aud": AUD, "emails": ["owner@example.org"]}}, [])
    now = time.time()
    assert wa.verify(web, jwt(), now) == "owner@example.org" and certs["asked"] == 1
    assert wa.verify(web, jwt(), now + 10) and certs["asked"] == 1                     # cached
    for i in range(5):                                                                    # an unknown key: one refetch per RETRY
        with pytest.raises(wa.Refused):
            wa.verify(web, jwt(kid="k2", key=OTHER), now + wa.RETRY + i)
    assert certs["asked"] == 2
    certs["keys"].append(_jwk("k2", OTHER))                                               # the team rotates a key in
    assert wa.verify(web, jwt(kid="k2", key=OTHER), now + 2 * wa.RETRY + 5) and certs["asked"] == 3
    later = now + wa.REFRESH + 3 * wa.RETRY                                               # stale keys are fetched again
    assert wa.verify(web, jwt(exp=later + 60), later) and certs["asked"] == 4
    certs["keys"] = []
    wa.CERTS = "http://127.0.0.1:1/{team}"                                                # unreachable: the cached keys stand
    assert wa.verify(web, jwt(exp=now + 3 * wa.REFRESH), now + 3 * wa.REFRESH)


def test_web_as_written_is_checked(tmp_path):
    def problems(raw):
        got: list[str] = []
        return wa.parse(raw, got), got
    web, bad = problems({"names": NAME, "access": {"team": "myteam", "aud": AUD, "emails": "a@b.org"}})
    assert not bad and web.names == [NAME] and web.issuer == f"https://{TEAM}" and web.emails == {"a@b.org"}
    assert any("needs web.access" in m for m in problems({"names": [NAME]})[1])
    assert any("not a host name" in m for m in problems({"names": ["https://x.org"], "access": {}})[1])
    _, bad = problems({"names": [NAME], "access": {"aud": 3, "emails": [], "colour": 1}, "port": 1})
    assert {"team", "aud", "emails", "colour", "port"} <= {w for m in bad for w in re.findall(r"\w+", m)}
    (tmp_path / "ergostat.yaml").write_text("name: x\nstocks:\n  q: {}\nweb:\n  names: [x.example.org]\n")
    with pytest.raises(mdl.ModelError, match="web.access"):
        mdl.load(tmp_path)


def test_files_under_the_public_name_never_include_the_state(page):
    p, url = page
    assert (p.dir / "intake.token").exists()
    assert ask(url, "/file/intake.token", NAME, jwt())[0] == 404                     # the push token stays here
    assert ask(url, "/file/ergostat.yaml", NAME, jwt())[0] == 200                     # the model's files are served
    assert ask(url, "/file/intake.token")[0] == 200                                   # and on this machine, as before


def _calls(monkeypatch):
    """Every write the page's answers make, each recording its ``by``: (module, path, query, the function it calls)."""
    from ergostat.actions import gate
    from ergostat.inbox import answer
    from ergostat.reports import record as reports
    from ergostat.web import actions_api, control_api, intent_api, numbers_api, reports_api, verdicts_api
    seen: list = []

    def rec(*a, by=None, **k):
        seen.append(by)
        return {"id": "x", "state": "s", "work": "w", "item": "i", "data": {"reopened": "r"}, "status": "ok"}
    for mod, name in [(gate, "approve"), (gate, "deny"), (answer, "answer"), (control_api.cp, "accept"),
                      (control_api.cp, "dismiss"), (reports, "mark"), (intent_api.acts, "confirm"), (intent_api.acts, "dismiss"),
                      (intent_api.acts, "supersede"), (intent_api.acts, "retire"), (verdicts_api.record, "overrule"),
                      (verdicts_api.record, "reopen"), (numbers_api.pr, "accept"), (numbers_api.pr, "dismiss")]:
        monkeypatch.setattr(mod, name, rec)
    monkeypatch.setattr(numbers_api.rv, "control_pending", lambda p, spec: [{"id": "loop-1"}])
    ok = {"id": ["ergostat.decision/x"], "item": ["work/1"]}
    calls = [lambda live: actions_api.post(live, "action/a/1/approve", {}),
             lambda live: actions_api.post(live, "action/a/1/deny", {}),
             lambda live: actions_api.answer(live, "inbox/a/1/approve", {}),
             lambda live: control_api.post(live, "control/loop-1/accept"),
             lambda live: control_api.post(live, "control/loop-1/dismiss"),
             lambda live: reports_api.post(live, "report/r/1/reviewed", {}),
             *[lambda live, act=act: intent_api.post(live, f"intent/{act}", ok) for act in ("confirm", "dismiss", "supersede")],
             lambda live: intent_api.post(live, "intent/retire", {"id": ["ergostat.correction/x"]}),
             lambda live: verdicts_api.post(live, "verdict/overrule", ok),
             lambda live: verdicts_api.post(live, "verdict/reopen", ok),
             *[lambda live, act=act, pid=pid: numbers_api.post(live, f"proposals/{pid}/{act}", 3600.0)
               for act in ("accept", "dismiss") for pid in ("loop-1", "p-1")]]
    return calls, seen


def test_every_answer_the_page_records_says_who_made_it(page, monkeypatch):
    """Every write path the page answers, called as a request under the public name would be: each records the
    email, none ``owner``."""
    from types import SimpleNamespace
    p, _ = page
    live = SimpleNamespace(get=lambda: p, reloaded=lambda: None, _lock=threading.Lock(), _kept={})
    calls, seen = _calls(monkeypatch)
    as_who = wa.acting("owner@example.org")
    try:
        for call in calls:
            call(live)
    finally:
        wa.done(as_who)
    assert seen == ["owner@example.org"] * len(calls)
    seen.clear()
    calls[0](live)
    assert seen == ["owner"]                                                          # and on this machine, the owner


def test_an_answer_through_the_login_is_the_owners_own_not_an_agents():
    """The inbox counts an email's answers as a person's (evidence for graduating a class), never as decided without
    the owner."""
    from ergostat.inbox.stats import BY_AGENT, by_person
    assert by_person("owner") and by_person("owner@example.org")
    assert not by_person(BY_AGENT) and not by_person("modeller") and not by_person(None)


# ---- a name declared open: public and read only, with no login

OPEN = f"""
name: open
stocks:
  queue: {{}}
web:
  names: [{NAME}]
  open: read
"""


@pytest.fixture(scope="module")
def open_page(tmp_path_factory):
    from ergostat.web import serve
    d = tmp_path_factory.mktemp("open")
    (d / "ergostat.yaml").write_text(textwrap.dedent(OPEN))
    p = Project(mdl.load(d))
    server, url = serve(p, free_port())
    yield p, url
    server.shutdown()
    server.server_close()


def test_a_name_declared_open_is_read_without_a_login_and_says_so(open_page):
    p, url = open_page
    for hdr in ({}, {"Cf-Ray": "8f00-LHR", "Cf-Connecting-Ip": "203.0.113.9"}):        # through the tunnel too
        assert ask(url, "/api/status", NAME, None, **hdr)[0] == 200
        code, body = ask(url, "/", NAME, None, **hdr)
        assert code == 200 and b'name="ergostat-public" content="read only"' in body
        assert page_token(body) == ""                                                  # no token for writes
    assert ask(url, "/file/intake.token", NAME)[0] == 404                              # the state is never served
    said = [x for x in p.model.problems if "web-public" in str(getattr(x, "code", "")) or "public and read only" in str(x)]
    assert said, p.model.problems


def test_a_name_declared_open_refuses_every_write(open_page):
    p, url = open_page
    t = page_token(ask(url, "/")[1])                                                   # even with this run's token
    body = json.dumps({"text": "hello"}).encode()
    for hdr in ({}, {"Origin": f"https://{NAME}", "Sec-Fetch-Site": "same-origin"}):
        code, got = ask(url, "/api/message", NAME, jwt(), body, **{"X-Ergostat-Token": t, **hdr})
        assert code == 403 and b"read only" in got
    assert ask(url, "/api/message", data=body, **{"X-Ergostat-Token": t})[0] == 200      # on this machine, as before


def test_open_still_refuses_other_names_and_a_rewritten_host(open_page):
    _, url = open_page
    local = url.removeprefix("http://")
    assert ask(url, "/api/status", "evil.example.com")[0] == 403
    code, got = ask(url, "/api/status", local, None, **{"Cf-Ray": "8f00-LHR"})        # the tunnel rewrote the Host
    assert code == 403 and b"keep that Host" in got
    assert ask(url, "/api/status")[0] == 200


def test_open_is_checked():
    def bad(raw):
        got: list[str] = []
        return wa.parse(raw, got), got
    web, said = bad({"names": [NAME], "open": "read"})
    assert web.open and not said
    assert bad({"names": [NAME], "open": True})[1] and bad({"names": [NAME], "open": "read", "access": {}})[1]
    assert any("open: read" in m for m in bad({"names": [NAME]})[1])
