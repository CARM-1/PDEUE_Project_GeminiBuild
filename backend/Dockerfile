# Hardened, non-root, low-memory (512 MB Lightsail) fail-closed PDEUE paper/observation image.
# Build from repository root:
#   docker build -f backend/Dockerfile -t pdeue-paper-node:b2-prep .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/pdeue/backend:/opt/pdeue \
    PDEUE_BACKEND_DIR=/opt/pdeue/backend \
    PDEUE_VENUE_MODE=paper \
    PDEUE_LIVE_TRADING_ENABLED=false \
    PDEUE_GOVERNANCE_MODE=EXECUTIVE_COMMAND \
    PDEUE_GATE_G1_STATUS=HOLD_OBSERVATIONS_ONLY \
    DATABASE_URL=sqlite:////var/lib/pdeue/data/pdeue.db \
    PDEUE_TAPE_DIR=/var/lib/pdeue/tapes

WORKDIR /opt/pdeue/backend

# Install strictly runtime backend dependencies (no Playwright, Chromium, pytest, or dev bloat)
COPY backend/requirements.runtime.txt /tmp/requirements.runtime.txt
RUN pip install --no-cache-dir -r /tmp/requirements.runtime.txt \
    && rm -f /tmp/requirements.runtime.txt \
    && groupadd --system --gid 10001 pdeue \
    && useradd --system --uid 10001 --gid pdeue --home-dir /var/lib/pdeue --shell /usr/sbin/nologin pdeue \
    && install -d -m 0750 -o pdeue -g pdeue /var/lib/pdeue /var/lib/pdeue/data /var/lib/pdeue/tapes

# Copy strictly runtime code and canonical contracts/manuals (NEVER bake a static pdeue.db)
COPY backend/app /opt/pdeue/backend/app
COPY backend/alembic /opt/pdeue/backend/alembic
COPY backend/alembic.ini /opt/pdeue/backend/alembic.ini
COPY backend/scripts /opt/pdeue/backend/scripts
COPY backend/templates /opt/pdeue/backend/templates
COPY contracts/schemas /opt/pdeue/contracts/schemas
COPY contracts/gate_g2 /opt/pdeue/contracts/gate_g2
COPY docs/manuals /opt/pdeue/docs/manuals
COPY fleet_engine.py /opt/pdeue/fleet_engine.py
COPY --chmod=0755 deploy/entrypoint_paper.sh /opt/pdeue/deploy/entrypoint_paper.sh

# Enforce non-root readability and verify zero static SQLite DB files were baked into the image
RUN chmod -R a+rX /opt/pdeue \
    && test ! -e /opt/pdeue/pdeue.db \
    && test ! -e /opt/pdeue/backend/pdeue.db \
    && test ! -e /var/lib/pdeue/data/pdeue.db

USER pdeue
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); sys.exit(0 if r.status == 200 else 1)"]

ENTRYPOINT ["/opt/pdeue/deploy/entrypoint_paper.sh"]
