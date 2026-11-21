# remote-mtls: the remote API served over mutual TLS on a listener of its own, and remotes read over it
depends-on: []

## Definition of done

Two halves. Each one is checked on the wire with real certificates.

**Serving side (`web: mtls:`).** The page can start a second listener that serves only the remote API (SPEC §4c) over TLS. The client must present a certificate signed by the CA the owner names. It is declared under `web:`, so a machine can set it in `ergostat.local.yaml`:

```yaml
web:
  mtls:
    port: 8796               # required, 1..65535
    bind: 0.0.0.0            # an address; default 0.0.0.0
    cert: ~/.config/ergostat/tls/server.pem
    key: ~/.config/ergostat/tls/server.key
    client-ca: ~/.config/ergostat/tls/clients.pem   # required: whose client certificates are taken
```

- **Parsing.** `ergostat/remote/mtls.py` parses `web.mtls`, called from `webaccess.parse` for the one new key `mtls`. The keys `port`, `bind`, `cert`, `key` and `client-ca` are required except `bind`. An unknown key, a bad port or a bad address is a `bad-web` error. Paths expand `~` and are relative to the model's folder.
- **`check` and unreadable files.** `ergostat check` gives an error, `mtls-unreadable`, for each of `cert`, `key` or `client-ca` that is missing, is a directory, or is not PEM. The test is that `ssl.SSLContext.load_cert_chain` or `load_verify_locations` fails on it. Running as root reads any file, so the tests use those three cases and never use chmod.
- **Server context.** It is built by `mtls.server_context(conf, root)`:
  - `PROTOCOL_TLS_SERVER`, `minimum_version = TLSVersion.TLSv1_2`, `verify_mode = CERT_REQUIRED`;
  - `load_verify_locations(client-ca)` only. It never calls `load_default_certs` and never falls back to the system's trust. A client CA that can't be read raises, and nothing is bound.
- **The listener.** `ergostat/remote/listen.py` starts it from `web.serve()`, beside the loopback page, sharing the page's `Live`. If the context can't be built or the port can't be bound:
  - no port is bound;
  - the loopback page still serves;
  - `serve()` returns the reason on `server.mtls_said`, and `ergostat run` and `ergostat web` print it (`remote API over mutual TLS: not listening: web.mtls.cert ~/…/server.pem: …`).
  - On success they print `remote API over mutual TLS: https://BIND:PORT`.
- **Hard limits.** All three are module constants, not config: `MOST = 16` connections at once, `HANDSHAKE = 10.0` s and `IDLE = 10.0` s.
  - **Slots.** A connection takes a slot without waiting (`BoundedSemaphore(MOST).acquire(blocking=False)`) in `process_request`. With no slot free it is closed at once in the accept thread, never queued. Each connection runs in its own daemon thread named `ergostat-mtls-N`. The slot is released in a `finally` that covers a failed handshake, a timeout, a handler exception and a stop.
  - **Handshake.** It runs in that thread, not in the accept loop: `wrap_socket(..., server_side=True, do_handshake_on_connect=False)`, `settimeout(HANDSHAKE)`, then `do_handshake()`. A stalled handshake never blocks accepting.
  - **After the handshake.** The socket timeout becomes `IDLE`, and the handler's `timeout = IDLE`. A client that goes quiet after the handshake, or between requests, is dropped and its slot comes back.
- **Allowlist.** The listener's handler is a subclass of the page's handler class. It serves an allowlist only:
  - `GET` only. `HEAD`, `POST` and every other method get 405, and never reach the page's routes.
  - The raw path, split on `/` and each segment decoded with `unquote`, must start with exactly the segments `remote` and `v1`. The third segment must be one of `status, model, events, items, counts, readings, series, process`. No segment may be `.`, `..` or empty except a trailing one.
  - Anything else is 404 without calling any page route. This matters: a connection from 127.0.0.1 would otherwise pass the page's `_local()` check and reach `/api/`.
  - Allowed requests go to the existing `_remote()`, so the bearer token, the 10/s rate limit and the 404-when-no-token rule apply as on the page. The client certificate admits the connection and the token names the consumer. The plan claims nothing more about identity.
- **Stopping.** The page server's `shutdown()` and `server_close()` also stop the listener. Stopping:
  - stops accepting;
  - shuts down and closes every open connection, mid-handshake or idle (`SHUT_RDWR`, then `close`);
  - joins each connection thread with a bound (2 s in all);
  - returns within 3 s when connections are open;
  - leaves the port bindable again (`allow_reuse_address`, as the page);
  - leaves no `ergostat-mtls-*` thread alive.

**Reading side (`remotes: NAME: tls:`).** A remote entry may say:

```yaml
remotes:
  incidents:
    url: https://incidents.example.org:8796
    token-file: ~/.config/ergostat/incidents.token
    tls: {cert: ~/.config/ergostat/tls/me.pem, key: ~/.config/ergostat/tls/me.key, ca: ~/.config/ergostat/tls/servers.pem}
```

- **Parsing.** `tls` is added to `compose.KEYS`. `cert` and `key` are required in it, and `ca` is optional. If `ca` is absent, the system's trust is used, as for any https. These are `bad-remote` errors:
  - `tls:` with an `http://` url;
  - a key missing, or an unknown key in `tls`.
- **Unreadable files.** Any of `cert`, `key` or `ca` that is given but missing, a directory or not PEM is an `mtls-unreadable` error at load.
- **Plumbing.** The parsed map is kept as `spec.remotes[name]["tls"]` and as a new `Source.tls` field (`spec/ir.py`, with `"tls"` added to the `ergostat` source keys in `spec/compile.py`). It is passed to `client.get(..., tls=)` by every caller: `cache.refresh`, `readings.answer` (and its refresh thread), `events.follow`, `process.py`, `refresh.once`, `cli/remote.py refresh`, and `compose.one`.
- **Client context.** `mtls.client_context(tls, root)`: `ssl.create_default_context(cafile=ca)` when `ca` is given, else `create_default_context()`; then `check_hostname = True`, `minimum_version = TLSv1_2`, `load_cert_chain(cert, key)`.
  - If any of these raises, `client.get` returns `(0, None, None, "tls: <which file>: <why>")`. It doesn't send the request, and it never retries without the client certificate or with the system's trust.
  - `client.get` without `tls` behaves as it does now.

**Docs and cleanup.**
- SPEC §4c gets the `tls` row in the remote key table, a paragraph on `web: mtls:` (the keys, MOST 16, 10 s handshake, 10 s idle, GET on `/remote/v1/` only, the token still needed, TLS 1.2 at least set on both contexts) and the `mtls-unreadable` code.
- SPEC §4d gets the `web:` key list. docs/proposals/remote-systems.md and docs/GAPS.md drop "mutual TLS" from what is left. The agent guide is updated if it lists the remote keys.
- No claim is made about the TLS 1.1 behaviour on the wire. Modern OpenSSL refuses 1.1 on the client side, so a wire test of it can't fail.

Done also means:
- the acceptance tests below exist and pass;
- the unit suite and the four browser files pass with rc 0;
- ruff is clean;
- origin/main is merged in and both suites are run again after the merge.

## Files to touch

- `ergostat/remote/mtls.py` (new): parse `web.mtls` and `remotes.*.tls`, the readability check, `server_context`, `client_context`
- `ergostat/remote/listen.py` (new): the bounded listener (slots, handshake and idle timeouts, the allowlist handler, stop)
- `ergostat/remote/client.py`: the `tls=` parameter, failing closed
- `ergostat/remote/compose.py`: the `tls` key, the https requirement, passing it to the cache and the source
- `ergostat/remote/cache.py`, `ergostat/remote/readings.py`, `ergostat/remote/events.py`, `ergostat/remote/process.py`, `ergostat/remote/refresh.py`, `ergostat/cli/remote.py`: pass `tls`
- `ergostat/spec/ir.py` (`Source.tls`), `ergostat/spec/compile.py` (the source key, `mtls-unreadable` for `web.mtls`)
- `ergostat/webaccess.py`: the `mtls` key handed to `mtls.parse`
- `ergostat/web/__init__.py`: start the listener in `serve()`, `server.mtls_said`, stop it in `shutdown`/`server_close`
- `ergostat/cli/running.py`: print what `mtls_said` says, in `run` and `web`
- `tests/tlscerts.py` (new helper): makes the certificates with the `openssl` CLI into `tmp_path_factory`, once per session:
  - a CA; a server cert with SAN `IP:127.0.0.1,DNS:localhost`; a wrong-SAN server cert (`DNS:other.example`) from the same CA;
  - a client cert from the CA; a client cert from a second CA.
  - It uses `-extfile`, which OpenSSL and macOS LibreSSL both take. A missing `openssl` fails the tests and never skips them.
- `tests/test_remote_mtls.py` (new)
- `docs/SPEC.md` (§4c, §4d), `docs/proposals/remote-systems.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md` (if it lists remote keys)

## Risks

- **lesson-3, failing open.**
  - Server side: an unreadable `cert`, `key` or `client-ca` must mean no port bound and an error from `check`. It must never mean a listener with no client verification or with the system's trust.
  - Client side: a configured but unreadable `ca` must fail the read, never fall back to `create_default_context()` without a cafile, and never try plain or certless.
  - A context with `check_hostname=False` or `CERT_OPTIONAL` would pass every happy-path test, so wrong-SAN, certless and wrong-CA refusals are each tested.
- **lesson-4, a limit with no ceiling.**
  - The connection cap, the handshake timeout and the idle timeout are hard constants (16, 10 s, 10 s), not config, so no setting can raise them.
  - The risks are a counter that never gives slots back (after a failed handshake or a handler exception), connections past 16 queued instead of closed, and a socket that stalls after the handshake holding a slot for good. All are tested by behaviour, not by counting threads.
- **lesson-6, work running after a stop.** `shutdown()` stops `serve_forever`, but threads blocked in `do_handshake()` or in `recv` after the handshake would go on, holding the port and threads. The stop must close their sockets and join them. It is tested with one connection mid-handshake and one idle after it, with the real 10 s timeouts, so a stop that only waits for them fails the 3 s bound.
- **lesson-8, a guarantee wider than the code.**
  - "Only `/remote/v1/`" must be an allowlist on decoded segments plus GET only. A `startswith("/remote/v1")` passes `/remote/v1x`, and a raw-string check passes `%2e%2e`. Over mTLS from 127.0.0.1 the page's `_local()` would admit `/api/`.
  - TLS 1.2 is claimed only as set on both contexts, and tested on the contexts.
  - "Mutual" is claimed only as "a certificate from `client-ca` is required". The certificate is not tied to the token's consumer, and the docs say so.
- **lesson-9, tests that can't fail.** Each test below says what breaking the code makes it fail. The report must say, for each, that the break was made and the test failed:
  - set `check_hostname=False`;
  - set `CERT_OPTIONAL`;
  - drop the `finally` release;
  - queue instead of close;
  - drop the idle timeout;
  - make stop not close sockets;
  - use `startswith` in the allowlist;
  - fall back to the default context.
- **lesson-10, load-dependent flakes.**
  - Every timing test polls with a deadline (`while time.monotonic() < deadline: … time.sleep(0.05)`) and never uses a fixed sleep for an outcome.
  - The timeout tests monkeypatch `listen.HANDSHAKE` and `listen.IDLE` to 0.5 s, with a 10 s deadline, so they don't depend on a quiet machine.
  - The stop test keeps the real 10 s and bounds the stop at 3 s.
  - A test that fails only under `-n 8` is treated as a race first. Bounds are never raised.
- **lesson-7, merged branches.** Other remote gaps are leased: remote-items-record, remote-process-lines, remote-box-measures, remote-proposals-text, remote-of-remotes. They touch the same `client.get` and `cache.refresh` call sites and `compose.KEYS`. Merge origin/main into the branch and run both suites again before calling it built. Any new caller of `client.get` that main gained must pass `tls`.
- **lesson-13, staying inside the gap.** A failure in a suite outside this change is named in the report with why it is unrelated, and not fixed here.

## Acceptance tests

All are in `tests/test_remote_mtls.py`. The listener tests call `listen.start(handler_cls, "127.0.0.1", 0, ctx)` (port 0, so there is no port race under xdist). The page tests use `web.serve` with a real model folder, a token made by `tokens.issue`, and certificates from `tests/tlscerts.py`.

- `test_a_remote_is_read_over_mutual_tls_end_to_end`: the remote's page serves with `web: mtls:`. `cache.refresh(..., tls={cert, key, ca})` of `https://127.0.0.1:PORT` gets `ok: True` and writes `model.json`. `readings.answer` through a `Source` with `tls` gets a body. `/remote/v1/status` is 200 with the right name. This fails if `tls` is not passed through.
- `test_a_client_without_a_certificate_or_with_another_cas_is_refused`: both get status 0 with a TLS reason. A request with the valid certificate right after is 200. This fails with `CERT_OPTIONAL`/`CERT_NONE`, or if `client-ca` is replaced by the default trust.
- `test_a_server_whose_certificate_names_another_host_is_refused`: the listener uses the wrong-SAN certificate from the same CA. `client.get` with `ca` set returns status 0 with a hostname reason. The right certificate is 200. This fails if `check_hostname` is False.
- `test_both_contexts_require_tls_1_2_and_verification`:
  - `server_context(...)`: `minimum_version >= TLSv1_2` and `verify_mode == CERT_REQUIRED`;
  - `client_context(...)`: `minimum_version >= TLSv1_2`, `check_hostname is True` and `verify_mode == CERT_REQUIRED`.
  - This fails if any line is dropped. It is the only test of the TLS 1.2 claim, which the docs limit accordingly.
- `test_an_unreadable_client_ca_fails_the_read_and_never_uses_the_systems_trust`: `ca` is missing, a directory, or not PEM. `client.get` returns `(0, …, "tls: ca …")` and the listener's request counter stays 0. `ssl.SSLContext.load_default_certs` and `ssl.create_default_context` without a cafile, both monkeypatched to record calls, are never called. A missing or non-PEM client `cert`/`key` does the same. This fails with a fallback to the default context.
- `test_an_unreadable_server_file_binds_nothing_and_the_page_still_serves` (parametrised over `cert`, `key`, `client-ca` × missing, directory, not PEM):
  - `ergostat check` exits non-zero with `mtls-unreadable` naming the key;
  - `web.serve` returns a page whose loopback `/api/status` is 200;
  - connecting to the mtls port is refused;
  - `server.mtls_said` names the key and the reason;
  - the `ergostat web` output (run in-process with `capsys`) prints it.
  - This fails if a listener starts without client verification, or if the page doesn't start.
- `test_mtls_config_is_checked`: a missing `client-ca`, a port of 0 or 70000, a bad `bind` and an unknown key each give `bad-web`. On the remote side, `tls:` with an `http://` url, `tls:` without `key`, and an unknown `tls` key each give `bad-remote`. A good entry puts `tls` on `spec.remotes[name]` and on `spec.sources[name].tls`.
- `test_only_get_of_the_remote_api_is_served`: over mTLS with a valid certificate and token:
  - these are 404 and their body is not the page's `/api/status`: `/remote/v1x/status`, `/remote/v1/../../api/status`, `/remote/v1/%2e%2e/%2e%2e/api/status`, `/remote/v1/status/../../../api/status`, `/remote//v1/status`, `/api/status`, `/`, `/static/app.js`, `/file?path=ergostat.yaml`;
  - `HEAD /remote/v1/status` and `POST /remote/v1/status` are 405;
  - `/remote/v1/status` without the token is 401, and with it is 200.
  - This fails with a prefix match or with routing to the page's `do_GET`.
- `test_connections_past_sixteen_are_closed_at_once`: 16 raw TCP connections are held mid-handshake. A 17th sees EOF or reset within 1 s (polled with a deadline), and there are never more than 16 `ergostat-mtls-*` threads. It also asserts that `listen.MOST == 16` and is a module constant that no config reads. This fails if extra connections are queued or the cap is removed.
- `test_stalled_connections_time_out_and_a_new_client_is_served` (HANDSHAKE and IDLE monkeypatched to 0.5 s):
  - 8 connections stall before the handshake and 8 complete it and send nothing;
  - while they hold the slots, a valid client is refused at once;
  - polling with a 10 s deadline, a valid client is served 200 and the 16 stalled sockets are closed by the server.
  - This fails without the post-handshake idle timeout, or without the handshake timeout.
- `test_slots_come_back_after_failed_handshakes_and_handler_errors`:
  - 20 handshakes without a client certificate, one after another, then a valid request is 200;
  - with `_remote` monkeypatched to raise, 20 requests, then with it restored a valid request is 200.
  - This fails if the release isn't in a `finally`.
- `test_stopping_the_page_with_connections_open_returns_promptly` (real 10 s timeouts):
  - one raw connection is mid-handshake and one is idle after a completed handshake;
  - `server.shutdown(); server_close()` returns within 3 s;
  - a new `listen.start` on the same port succeeds;
  - polling with a 2 s deadline, no `ergostat-mtls-*` thread is alive;
  - both client sockets see EOF.
  - This fails if stop doesn't close and join the open connections.
- `test_a_remote_without_tls_is_read_as_before`: `client.get` without `tls` against the plain loopback page is unchanged (200). This guards against regressions in the existing remote tests.

## Size budget

400 net lines of code outside `tests/` and `docs/`: about 120 in `mtls.py`, 150 in `listen.py`, 30 in `web/__init__.py` and `running.py`, and about 100 to pass `tls` through compose, client, cache, readings, events, process, refresh, the CLI, the IR and compile.

## Notes from the plan review (answer each)

- Page tests and ports (lesson-10): `web.mtls.port` must be 1..65535, so every test going through `web.serve` (end-to-end, unreadable server file, stop) has to use a fixed or probed port, which can race under -n 8. That contradicts the plan's 'port 0, no race' claim. Give these tests a race-free path: let `serve()` or `listen.start` accept a test-only port-0 override and expose the bound port on the server (e.g. `server.mtls_port`), or monkeypatch the parse so it allows 0. Don't use a bind-probe-close-reuse step. For the stop test, rebind the port read back after the first start.
- `test_stalled_connections_time_out...` (lesson-10): with HANDSHAKE/IDLE at 0.5 s, opening 16 connections, finishing 8 handshakes and then checking 'a valid client is refused at once' can take longer than 0.5 s under load, so slots free up before the check and the test flakes. Either drop the at-capacity refusal from this test (`test_connections_past_sixteen` already covers it with real timeouts) or set the patched values high enough (e.g. 3 s) and assert the refusal only after confirming all 16 are held. Keep the 10 s deadline for recovery.
- Allowlist path: strip the query string before splitting (`/remote/v1/items?since=...` must pass and `status?x` must not count as a segment). After decoding, reject any segment that contains `/` or `\` (e.g. `%2F`), and add `/remote/v1/status%2F..%2F..%2Fapi%2Fstatus` to the 404 list.
- Readability check naming the file: `load_cert_chain(cert, key)` alone can't tell which of `cert` and `key` is bad, yet the parametrised test needs `mtls-unreadable` to name the key. Say how each file is checked on its own (e.g. cert through a PEM-certificate load, key through `load_cert_chain` only after the cert passed). Add a mismatched cert/key pair as a fourth case: it must also be `mtls-unreadable` and bind nothing.
- TLS 1.3 refusal timing: under 1.3 a certless client's handshake finishes and the refusal arrives as an alert on the first read, which can show up as an SSLError or a reset. In the refusal tests, assert status 0 and no body, not exact wording. Make sure `client.get` turns ConnectionResetError/SSLError raised during the read into `(0, None, None, reason)` rather than a traceback.
- Stop race (lesson-1/lesson-6): register open sockets under one lock with a `stopping` flag. A connection accepted while a stop is running must see the flag inside the lock and close itself, otherwise it escapes the close-all snapshot. Shut down the underlying fd (`socket.socket.shutdown(sock, SHUT_RDWR)`), not `SSLSocket.shutdown`, which clears `_sslobj` under a thread blocked in `do_handshake`. Read the timeouts as `listen.HANDSHAKE`/`listen.IDLE` at use time, never as default arguments, or the monkeypatching won't take effect.
- Rate limit: check that the requests in `test_only_get` and the end-to-end test stay under the 10/s token limit or are spaced out. A 429 must not hide a wrong 404/200, and the 404/405 paths must be shown never to reach `_remote` (e.g. with a call counter).

## Where it stopped

Built, round 1. All of the definition is in place: 383 net lines of code outside `tests/` and `docs/`
(budget 400). Nobody could be asked, so these choices were made, each the more reversible one:

- **`mtls-unreadable` for `web.mtls` is an error only to `ergostat check`.** When the model loads (run, web) it
  is a finding. An error at load would stop `mdl.load`, and then "the loopback page still serves" could not
  hold. `ergostat check` is the one place `compose.fresh()` is set, so compile asks `compose.checking()`. A
  remote's `tls:` file that can't be read is an error at load, as the definition says.
- **The page tests' port** (plan review, lesson-10): `web.serve(project, port, mtls_port=None)`. The test-only
  override 0 binds any free port, and `server.mtls_port` gives it back. The stop test binds that same port
  again. The unreadable-file test configures a port the test holds bound (and not listening), so nothing
  else can take it. It also checks that `listen.start` is never called. There is no probe-then-reuse step.
- **The stalled test** uses 3 s for `HANDSHAKE` and `IDLE`, not 0.5 s (plan review). It opens the 8
  handshaken connections first and the 8 raw ones after. It checks the refusal only after
  `held() == 16`. Recovery is polled with a 10 s deadline.
- **Allowlist** (plan review): the query and fragment are cut off before splitting. Segments are decoded
  with `unquote`. A segment holding `/` or `\` is refused, and so are `.`, `..` and an empty one (except a
  trailing one). `/remote/v1/status%2F..%2F..%2Fapi%2Fstatus`, `/remote/v1/` and `/remote/v2/status` are in
  the 404 list. Every other method is 405 through `__getattr__`, so none of them is ever 501.
- **Each file is checked on its own** (plan review): `cert` loads as PEM certificates into a scratch
  `SSLContext`. `key` goes through `load_cert_chain` only after the cert passed, so a mismatched pair is
  `web.mtls.key …: KEY_VALUES_MISMATCH` (the fourth parametrised case). `client-ca` goes through
  `load_verify_locations`. A missing file or a directory is caught by name before OpenSSL sees it. On the
  client side every file is checked before any context is made, so a bad file never reaches
  `create_default_context`.
- **TLS 1.3 refusals** (plan review): the refusal tests check status 0 and no body. The one exception is
  the wrong host, which checks for `mismatch`. `client.get` also catches `http.client.HTTPException`, so a
  late alert or a reset gives `(0, None, None, why)` and never a traceback.
- **Stop race** (plan review): sockets are registered under one lock with `stopping`. `process_request`
  checks the flag inside that lock, and the thread starts inside it, so a stop's snapshot never holds an
  unstarted thread. After `wrap_socket` the entry is swapped to the `SSLSocket`. If a stop has begun by
  then, the connection closes itself. Stop calls `socket.socket.shutdown(sock, SHUT_RDWR)` on the fd,
  joins for 2 s in all, and only then closes. `HANDSHAKE` and `IDLE` are read when used: the handler's
  `timeout` is a property.
- **Rate limit** (plan review): in `test_only_get` only three requests reach `_remote` (401, 200, events),
  and a counter shows that none of the 404/405 paths reach it. The end-to-end test makes three requests.
  Each test's consumer name is its own.
- **A hand-written `type: ergostat` source** takes `tls:`, because the key was added to the source keys. A
  `tls:` that is not a map is `bad-remote`. `client.get` with `tls` refuses a non-https url itself.
- **Proxies**: `urllib` honours `HTTPS_PROXY` as it did before. This container sets one, so the test file
  clears the proxy variables for its own tests. How the client treats proxies is not changed here.
- `tests/test_remote.py`'s fake `client.get` gained the `tls=None` parameter, because `readings` now passes
  it.

Not done here:

- origin/main was not merged. This clone has no `origin`, and local `main` has nothing past this branch's
  base. The merge queue has to merge and run the suites again (lesson-7).
- The unit suite and the four browser files were not run whole. This session ran the touched files
  one at a time (the factory runs the suites under the watchdog). The browser run with Playwright was not
  permitted here.
