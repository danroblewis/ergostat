# The dev image: run ergostat's suites, benchmarks and corpus runs in a Linux VM with hard limits
# (docs/DEVELOPMENT.md). The build context is only pyproject.toml and uv.lock (.dockerignore): no secrets.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12.16-slim-trixie
ARG UID=1000
ENV DEBIAN_FRONTEND=noninteractive \
    UV_PYTHON=/usr/local/bin/python3 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_FROZEN=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/opt/uv-cache PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends git zsh bubblewrap procps ca-certificates \
    && rm -rf /var/lib/apt/lists/* && git config --system safe.directory '*'
COPY --from=uv /uv /uvx /usr/local/bin/
# VictoriaMetrics, the readings' only store (NOTES.md, 2026-11-25): the single-node release, pinned and checked, as
# /usr/local/bin/victoria-metrics (the suites start their own, tests/conftest.py)
ARG TARGETARCH
ARG VM_VERSION=v1.157.0
RUN set -e; case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
      amd64) sum=7b31192da6cf805b8b9244a904b022948e8022a067a822c30cb9f94600d0c387; arch=amd64 ;; \
      arm64) sum=e5368dec72d212dcb2b994345ab872245299000d37197f723123e63a50e573b5; arch=arm64 ;; \
      *) echo "no VictoriaMetrics release here for ${TARGETARCH}" >&2; exit 1 ;; esac; \
    python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/vm.tgz')" \
      "https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/${VM_VERSION}/victoria-metrics-linux-${arch}-${VM_VERSION}.tar.gz"; \
    echo "$sum  /tmp/vm.tgz" | sha256sum -c -; \
    tar -xzf /tmp/vm.tgz -C /tmp victoria-metrics-prod; \
    install -m 0755 /tmp/victoria-metrics-prod /usr/local/bin/victoria-metrics; rm -f /tmp/vm.tgz /tmp/victoria-metrics-prod; \
    victoria-metrics --version
# Chromium and its system libraries, for the version the browser suite runs with
RUN uvx --from playwright==1.63.0 playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u "$UID" dev && mkdir -p /opt/venv /work && chown -R dev /opt/venv /opt/uv-cache /opt/ms-playwright /work
USER dev
WORKDIR /work
# The locked dependencies, with ergostat installed editable from /work (stubs now; the bind mount at run time).
# The cache stays in the image, so `uv run` and `uv run --with playwright==1.63.0` work offline.
COPY --chown=dev pyproject.toml uv.lock ./
RUN python3 -c "import tomllib, pathlib; c = tomllib.load(open('pyproject.toml', 'rb'));\
[(pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True), pathlib.Path(p).touch())\
 for p in [*c['tool']['hatch']['build']['targets']['wheel']['force-include'], 'ergostat/__init__.py']]" \
    && uv sync && uv run --with playwright==1.63.0 python -c "import playwright, pytest, xdist" \
    && uv run --no-project --with pillow --with numpy python -c "import PIL, numpy"
# (pillow and numpy: examples/image-squeeze's bin/py)
ENV UV_OFFLINE=1
