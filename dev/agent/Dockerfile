# The factory's agent image (dev/agent/README in dev/README.md, "Sessions in containers"): the dev image (Dockerfile
# at the repository's root: Python, uv, the locked dependencies offline, git) with Claude Code's Linux build, for the
# implementor's and the reviewer's sessions. No secret is ever in it: the session token is given at `docker run`.
# Build: docker build -t ergostat-agent:latest dev/agent   (after the dev image: scripts/in_container.sh true)
FROM ergostat-dev:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
USER dev
RUN curl -fsSL https://claude.ai/install.sh | bash && /home/dev/.local/bin/claude --version
ENV PATH=/home/dev/.local/bin:$PATH \
    DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
WORKDIR /work
