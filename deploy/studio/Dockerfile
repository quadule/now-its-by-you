# The public studio (songbird studio --public), in a container: docs/WEB-STUDIO.md.
# Built from the checkout's root:  docker compose -f deploy/studio/docker-compose.yml build
# The image holds the program, the songs and the locked dependencies, and the synthesis compiled once
# (so the first visitor doesn't wait for it). Nothing of the host's: no harvested voice, no recordings.

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

# the locked dependencies first (a layer that changes only when uv.lock does), then the program
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY songbird ./songbird
COPY songs ./songs
RUN uv sync --frozen --no-dev

# the synthesis compiled into the image, for every instrument a visitor can choose (about 30 s)
# and the program's fingerprint, so a new image's first start clears previews the old one made
COPY deploy/studio/warm.py deploy/studio/entrypoint.sh /opt/studio/
RUN find songbird songs -type f | LC_ALL=C sort | xargs sha256sum | sha256sum > /opt/studio/program.sha \
    && python /opt/studio/warm.py && chmod -R a+rX /opt/numba-cache /opt/studio && chmod a+rx /opt/studio/entrypoint.sh

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
