## Entry

section: The factory (ergostat on ergostat)

- **The factory's AI sessions in the dev container** (open; from `factory`, `docs/roadmap/overnight/factory.md`): the
  implementor and the reviewer run `claude -p` on the host, held by their pool caps, the daily dollar cap and the load
  interlock, with Claude Code's allowed and disallowed tools (no OS sandbox). Inside the container they would get the
  kernel's limits, but a session there needs three things it lacks: Claude Code itself (the image has no Node and no
  Linux build of it), a sign-in (the host's is in the macOS keychain; a container would need a token,
  `CLAUDE_CODE_OAUTH_TOKEN`, as a secret mounted in), and a way out to the API alone (the container has no network,
  and `--net` opens all of it). ergostat's filtering CONNECT proxy (`ergostat/sandbox/proxy.py`, which can listen on a
  Unix socket) is the right filter, but Docker Desktop on macOS does not carry a host Unix socket into its VM, so the
  proxy would have to run inside Docker: a second service on an `internal: true` network, the only one with a route
  out, allowing `api.anthropic.com:443` (CONNECT, its TLS server name checked). Left: that service, the token's
  handling, Claude Code in the image, and a measured run of one session inside.
