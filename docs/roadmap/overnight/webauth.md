# webauth: the page behind a public name, with a real login

Branch `webauth`, from origin/main at fdf83b9.

## The gap

The owner watches a dev instance through a cloudflared tunnel at a public name. The page (`ergostat/web/server.py`,
`_host_ok`) refuses any Host but `127.0.0.1:PORT`, its guard against DNS rebinding, so the tunnel is set to rewrite
the Host header; then every visitor looks local: reads are open to anyone who reaches the name, and writes fail on
the Origin check.

## Done when

A project may declare the public names its page answers to, and the Cloudflare Access application in front of
them, in its main file (`web: {names: [...], access: {team, aud, emails}}`; `check` refuses a malformed one, and
names without `access`). A request addressed to a declared name, or one that arrived through Cloudflare (it carries
`Cf-Ray`, `Cf-Connecting-Ip` or `Cf-Access-Jwt-Assertion`) whatever its Host, is served only with a valid
`Cf-Access-Jwt-Assertion` (RS256, verified with the standard library against the team's keys, fetched from
`https://<team>/cdn-cgi/access/certs` and cached with a bounded refresh; `aud`, `iss` and `exp` checked) whose
`email` is on the allowlist: otherwise 401 (no or bad token) or 403 (not allowed, or no `web:` declared), for reads
too. A write under a public name needs Origin `https://NAME` besides the page's token, and is recorded with the
email as who made it (where the page's writes say `owner` today). Any other Host is refused as before; local
requests behave exactly as today. No new dependency (`cryptography` is not one; RSA verification is a few lines
of `pow`). SPEC §4 and a new §4d, and a short how-to in docs/DEVELOPMENT.md or SECURITY.md, say how to put an
instance behind cloudflared and Access.

## Acceptance tests (`tests/test_web_access.py`)

- `test_a_valid_token_for_an_allowed_email_reads_the_page_under_the_public_name`
- `test_a_missing_expired_or_foreign_token_is_refused_for_reads_too` (missing, expired, wrong aud, wrong iss, bad
  signature, unknown key, alg other than RS256)
- `test_an_email_not_allowed_is_forbidden`
- `test_through_the_tunnel_with_the_host_rewritten_still_needs_the_login`
- `test_a_foreign_host_is_still_refused`
- `test_local_requests_behave_as_today`
- `test_a_write_under_the_public_name_is_recorded_with_the_email`
- `test_a_write_from_another_origin_is_refused_under_the_public_name`
- `test_the_keys_are_cached_and_refreshed_at_most_so_often`
- `test_web_as_written_is_checked`

## Budget

350 net lines outside `tests/` and `docs/`.
