# The dev image: run ergostat's suites, benchmarks and corpus runs in a Linux VM with hard limits
# (docs/DEVELOPMENT.md). The build context is only pyproject.toml and uv.lock (.dockerignore): no secrets.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12-slim-trixie
ARG UID=1000
ENV DEBIAN_FRONTEND=noninteractive \
    UV_PYTHON=/usr/local/bin/python3 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_FROZEN=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/opt/uv-cache PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends git zsh bubblewrap procps ca-certificates \
    && rm -rf /var/lib/apt/lists/* && git config --system safe.directory '*'
COPY --from=uv /uv /uvx /usr/local/bin/
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
