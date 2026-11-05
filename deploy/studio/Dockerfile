# The public studio (songbird studio --public), in a container: docs/history/web-studio-server-plan.md.
# Built from the checkout's root:  docker compose -f deploy/studio/docker-compose.yml build
# The image holds the program, the songs and the locked dependencies, and the synthesis compiled once
# (so the first visitor doesn't wait for it). Nothing of the host's: no harvested voice, no recordings.

# ---- the bundle a desktop browser makes the song with (docs/WEB-STUDIO.md, "Made in the visitor's browser"):
# Pyodide (from npm) with numpy, scipy and soundfile (from Pyodide's CDN, checked against its lock), the kernels in
# JS and wasm, and this very program. Node is needed here only; the image below never has it. The C kernels are
# built and committed (web/studio-wasm/wasm/kernels.wasm), so no zig either.
FROM node:22-bookworm-slim AS render
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON=3.12
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY web/studio-wasm/package.json web/studio-wasm/package-lock.json ./web/studio-wasm/
RUN cd web/studio-wasm && npm ci --no-audit --no-fund
# the same program files as the image below (the studio refuses a bundle whose program isn't its own)
COPY songbird ./songbird
COPY web/studio-wasm ./web/studio-wasm
RUN uv run --no-sync python web/studio-wasm/tools/build_render.py /opt/render

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NUMBA_CACHE_DIR=/opt/numba-cache \
    SONGBIRD_THREADS=2

WORKDIR /app

# the locked dependencies first (a layer that changes only when uv.lock does), then the program. With them,
# the web-singing group (pyworld, librosa: measuring a take sung in the browser, docs/WEB-SINGING.md), which
# only this image has, never a packet; pyworld has no Linux wheel, so a compiler is lent for its build and taken
# back in the same layer
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN apt-get update && apt-get install -y --no-install-recommends g++ \
    && uv sync --frozen --no-dev --group web-singing --no-install-project \
    && apt-get purge -y g++ && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY songbird ./songbird
COPY songs ./songs
RUN uv sync --frozen --no-dev --group web-singing
# the measuring tools and the web studio's singing (the kit they measure against is mounted: docker-compose.yml)
COPY tools ./tools
COPY webstudio ./webstudio

# the synthesis compiled into the image, for every instrument a visitor can choose (about 30 s)
# and the program's fingerprint, so a new image's first start clears previews the old one made
COPY deploy/studio/warm.py deploy/studio/entrypoint.sh /opt/studio/
RUN find songbird songs -type f | LC_ALL=C sort | xargs sha256sum | sha256sum > /opt/studio/program.sha \
    && python /opt/studio/warm.py && chmod -R a+rX /opt/numba-cache /opt/studio && chmod a+rx /opt/studio/entrypoint.sh
# the browser's bundle (about 35 MB), served under /render/ (docker-compose.yml: --browser-render)
COPY --from=render /opt/render /opt/studio/render

# no one in particular: the studio runs as this user, on a read-only root, writing only to /data
RUN useradd --system --uid 10001 --home-dir /data --no-create-home songbird \
    && mkdir -p /data && chown songbird /data
USER songbird
ENV SONGBIRD_HOME=/data
VOLUME /data
EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/healthz', timeout=4)"]

ENTRYPOINT ["/opt/studio/entrypoint.sh"]
